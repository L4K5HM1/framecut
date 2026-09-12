"""Local download, video encoding, and caption helpers for Framecut."""
import json
import logging
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
from urllib.parse import parse_qs, urlsplit

LOGGER = logging.getLogger(__name__)
_MODEL = None
_MODEL_LOCK = threading.Lock()


class PipelineError(Exception):
    """An actionable message safe to show in the browser."""


def youtube_url(value):
    """Normalize supported video links, discarding playlist and other parameters."""
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError('Enter a YouTube video URL.')
    try:
        url = urlsplit(value.strip())
        if url.scheme not in ('http', 'https') or url.username or url.password or url.port:
            raise ValueError
        if url.hostname == 'youtu.be':
            video_id = url.path.lstrip('/')
        elif url.hostname in ('youtube.com', 'www.youtube.com', 'm.youtube.com'):
            parts = url.path.strip('/').split('/')
            video_id = (parse_qs(url.query).get('v', [''])[0] if url.path == '/watch'
                        else parts[1] if len(parts) == 2 and parts[0] in ('shorts', 'embed', 'live') else '')
        else:
            raise ValueError
        if not re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id):
            raise ValueError
    except ValueError as exc:
        raise ValueError('Use a youtube.com/watch or youtu.be video link.') from exc
    return 'https://www.youtube.com/watch?v=' + video_id


def run(command, *, cwd=None, timeout=1800):
    """Execute an argument list without a shell; keep tool diagnostics in logs."""
    try:
        result = subprocess.run(command, cwd=cwd, capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=timeout, check=True)
        return result.stdout
    except FileNotFoundError as exc:
        raise PipelineError(f'{Path(command[0]).name} is missing. Check the setup instructions.') from exc
    except subprocess.TimeoutExpired as exc:
        raise PipelineError('Processing timed out. Try a shorter source or clip.') from exc
    except subprocess.CalledProcessError as exc:
        LOGGER.error('Tool failed: %s\n%s', Path(command[0]).name, exc.stderr[-6000:])
        raise PipelineError('Media processing failed. Check the terminal log and installed dependencies.') from exc


def probe(path):
    data = json.loads(run(['ffprobe', '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(path)], timeout=30))
    duration = float(data.get('format', {}).get('duration', 0))
    streams = data.get('streams', [])
    if not math.isfinite(duration) or duration <= 0 or not any(s['codec_type'] == 'video' for s in streams):
        raise PipelineError('The source does not contain a usable video stream.')
    return {'duration': duration, 'has_audio': any(s['codec_type'] == 'audio' for s in streams)}


def download(url, directory, video_id):
    """Download exactly one video into a private temporary directory."""
    with tempfile.TemporaryDirectory(prefix='load-', dir=directory) as work:
        run([sys.executable, '-m', 'yt_dlp', '--ignore-config', '--no-playlist',
             '--no-progress', '--socket-timeout', '30', '--retries', '3',
             '-f', 'bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b',
             '--merge-output-format', 'mp4', '--remux-video', 'mp4',
             '-o', str(Path(work) / 'source.%(ext)s'), '--', url])
        source = Path(work) / 'source.mp4'
        if not source.is_file():
            raise PipelineError('The download finished without a playable MP4 file.')
        metadata = probe(source)
        filename = video_id + '.mp4'
        source.replace(Path(directory) / filename)
        return {'filename': filename, **metadata}


def build_crop_filter():
    """Fit both landscape and tall sources into a centered, square-pixel 9:16 frame."""
    return 'scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1'


def transcribe(audio_path):
    global _MODEL
    # Serialize inference and reuse the model rather than reloading it for every export.
    with _MODEL_LOCK:
        if _MODEL is None:
            from faster_whisper import WhisperModel
            _MODEL = WhisperModel(os.environ.get('WHISPER_MODEL', 'small'), device='cpu', compute_type='int8')
        segments, _ = _MODEL.transcribe(str(audio_path), word_timestamps=True)
        return [(word.start, word.end, word.word.strip())
                for segment in segments for word in (segment.words or [])]


def ass_timestamp(seconds):
    centiseconds = max(0, round(seconds * 100))
    hours, rest = divmod(centiseconds, 360000)
    minutes, rest = divmod(rest, 6000)
    secs, cs = divmod(rest, 100)
    return f'{hours}:{minutes:02}:{secs:02}.{cs:02}'


def words_to_ass(words, path):
    header = '''[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,80,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,4,0,2,60,60,180,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    lines = [header]
    for start, end, word in words:
        if end <= start or not word.strip():
            continue
        # Prevent transcript text from being interpreted as ASS formatting commands.
        text = word.replace('\\', '／').replace('{', '(').replace('}', ')').replace('\n', ' ').replace('\r', ' ')
        lines.append(f'Dialogue: 0,{ass_timestamp(start)},{ass_timestamp(end)},Default,,0,0,0,,{text}')
    Path(path).write_text('\n'.join(lines), encoding='utf-8')


def export_clip(source, outputs, job_id, start, end, captions, update):
    final = Path(outputs) / (job_id + '.mp4')
    # Relative ASS paths inside this working directory avoid Windows drive-letter escaping.
    with tempfile.TemporaryDirectory(prefix='clip-', dir=outputs) as work:
        work = Path(work)
        update('encoding')
        run(['ffmpeg', '-nostdin', '-y', '-ss', str(start), '-i', str(source),
             '-t', str(end - start), '-map', '0:v:0', '-map', '0:a:0?',
             '-vf', build_crop_filter(), '-c:v', 'libx264', '-preset', 'veryfast',
             '-crf', '20', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '160k',
             '-movflags', '+faststart', str(work / 'vertical.mp4')])
        if captions:
            update('transcribing')
            run(['ffmpeg', '-nostdin', '-y', '-i', str(work / 'vertical.mp4'),
                 '-vn', '-ac', '1', '-ar', '16000', str(work / 'audio.wav')])
            words_to_ass(transcribe(work / 'audio.wav'), work / 'captions.ass')
            update('captioning')
            run(['ffmpeg', '-nostdin', '-y', '-i', 'vertical.mp4', '-vf', 'ass=captions.ass',
                 '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p',
                 '-c:a', 'copy', '-movflags', '+faststart', 'final.mp4'], cwd=work)
            (work / 'final.mp4').replace(final)
        else:
            (work / 'vertical.mp4').replace(final)
    return final.name
