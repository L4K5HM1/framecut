# Framecut

**Turn a selected video moment into a captioned vertical short, locally.**

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.1-222222?logo=flask&logoColor=white)
![FFmpeg](https://img.shields.io/badge/FFmpeg-video_processing-007808?logo=ffmpeg&logoColor=white)
![faster-whisper](https://img.shields.io/badge/faster--whisper-local_transcription-7563CC)
![License](https://img.shields.io/badge/License-MIT-green)

Framecut is a local web app for turning YouTube video segments into 1080 × 1920 MP4s. Paste a link, select the clip on a draggable timeline, and export a center-cropped video with optional word-level captions. Flask coordinates background jobs; FFmpeg handles video processing; faster-whisper transcribes speech on your CPU.

**Status:** local, single-user application. No hosted demo, account system, or deployment is included.

## Features

- Load one YouTube video at a time, with playlist parameters removed.
- Preview the source and select a range using draggable handles, keyboard controls, or precise time inputs.
- Preview just the selected section before exporting.
- Export 0.1–180 second clips as 9:16 H.264/AAC MP4s with browser-friendly pixel format and fast-start metadata.
- Add word-by-word burned-in captions using local CPU transcription.
- Follow download, encoding, transcription, and captioning stages without blocking the interface.
- Use a bounded job queue, reusable transcription model, and automatic cleanup of intermediate files.
- Download and review the finished short from the browser.

## Screenshot and demo

<!-- Add an actual UI capture here as docs/interface.png. Do not use a broken image link. -->

**Screenshot placeholder:** add a capture of the editor and selected timeline range here after a local browser smoke test.

**Demo recording placeholder:** a 20–30 second recording showing source loading, timeline selection, and a finished export will be added here. No hosted or recorded demo is currently supplied.

## Requirements

- **Python 3.10+** (Python 3.11 or 3.12 is a straightforward starting point).
- **FFmpeg and ffprobe on PATH**, including the `libx264` encoder and `ass` subtitle filter (libass).
- **Deno on PATH** for current yt-dlp YouTube JavaScript support. The Python `yt-dlp[default]` extra supplies its EJS package; it does not install Deno.
- A modern browser. Internet access is required for video downloads and the first transcription-model download. Subsequent transcription runs locally using cached weights.

Install FFmpeg from its [official download page](https://ffmpeg.org/download.html) and Deno using its [installation instructions](https://docs.deno.com/runtime/getting_started/installation/). On Windows, ensure the directory containing `ffmpeg.exe` and `ffprobe.exe` is on PATH, then open a fresh terminal.

Verify the executables:

```sh
python --version
ffmpeg -version
ffprobe -version
deno --version
```

## Setup

Download or clone this repository, then open a terminal in its root directory.

```sh
git clone https://github.com/L4K5HM1/framecut.git
cd framecut
```

**Windows PowerShell** — activation is not required:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

**macOS / Linux:**

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:5001**. Keep the terminal running while jobs process. Use Ctrl+C to stop the server after jobs finish.

## Use it

1. Paste a YouTube video URL and choose **Load video**.
2. Drag the timeline handles or enter start/end times. Focus a handle and use arrow keys for 0.1-second adjustments; hold Shift for 1-second steps.
3. Choose **Preview selection** to review your range.
4. Enable captions if the source has audio, then select **Export short**.
5. Review the result and select **Download MP4**.

Captions are model-generated and may contain mistakes. Review them before sharing. Only process videos you own or have permission to use.

## How it works

1. **Validate and download.** The API accepts supported YouTube URLs, normalizes the video ID, and queues a yt-dlp download. ffprobe checks the duration and audio availability.
2. **Select.** The browser streams the downloaded source. Timeline controls supply start/end timestamps; the server checks them against the registered source.
3. **Trim and frame.** FFmpeg selects the segment, scales it to cover the target frame, and center-crops it to 1080 × 1920. Off-center subjects may be cropped out; there is no automatic subject tracking.
4. **Transcribe, optionally.** FFmpeg extracts mono 16 kHz audio. A cached faster-whisper `small` model runs with CPU INT8 inference and word timestamps.
5. **Caption and export.** The app writes ASS subtitles and burns them into the video. Temporary audio, subtitle, and intermediate-video files are removed. The finished MP4 becomes available for preview and download.

One worker processes jobs sequentially to control CPU and model memory use. At most four jobs can be active or waiting. Status updates describe stages, not estimated percentages.

## Project layout

| Path | Responsibility |
| --- | --- |
| `app.py` | Flask routes, input checks, job queue, and local file serving |
| `media_pipeline.py` | URL normalization, downloads, FFmpeg, transcription, and ASS captions |
| `templates/index.html` | Accessible editor structure |
| `static/app.js` | Timeline interaction, requests, and status polling |
| `static/styles.css` | Responsive interface styling |
| `tests/` | API regression tests and synthetic-media FFmpeg integration checks |
| `docs/` | Review notes and demo guidance |

`downloads/` and `outputs/` are created automatically and fully ignored by Git. Python caches, virtual environments, local environment files, and logs are also ignored.

## Configuration and limits

Set `WHISPER_MODEL` before starting the app to use a different model, such as `tiny` for a lighter CPU workload. Defaults to `small`. No API key is required.

- Keep the app bound to localhost. The development server is not a public hosting setup.
- Jobs and source registrations are in memory. Restarting the app loses their state; reload a source to use it again.
- Sources and final MP4s remain on disk until you remove them. Stop the app before clearing `downloads/` or `outputs/`.
- Long source downloads can use substantial disk space. Clips are limited to 180 seconds; source duration is not capped.
- Jobs cannot currently be cancelled or resumed. A browser polling failure does not cancel server processing.
- Only the latest 100 job records are retained. FFmpeg and download commands have 30-minute timeouts; model loading/inference has no separate hard timeout.
- Browser source preview depends on the downloaded codec. Final exports use H.264/AAC for broad compatibility.
- Dependency ranges are not a lockfile. yt-dlp is intentionally unpinned because upstream site changes frequently require updates.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Missing FFmpeg / ffprobe | Check both executables are on PATH and restart the terminal. |
| YouTube download fails | Update with `python -m pip install -U "yt-dlp[default]"`; verify Deno is installed; check that the video is publicly available. |
| Caption export fails | Check `ffmpeg -filters` lists `ass`, and inspect the terminal log. |
| First caption job is slow | The model downloads once and CPU transcription can take time. Try `WHISPER_MODEL=tiny`. |
| Source has no audio | Turn captions off; the app disables them automatically when no audio stream is detected. |
| Port 5001 is busy | Use `python -m flask --app app run --host 127.0.0.1 --port 5002`, then open that port. |

## Tests

Install the lightweight test dependencies in your environment:

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Tests mock network downloads and transcription. Where FFmpeg is installed, integration tests generate synthetic media, encode real vertical clips, and burn sample captions. They do not verify live YouTube access or actual model recognition. The FFmpeg checks skip when its executables are unavailable.

## Contributing

For bugs, include your OS, Python/FFmpeg versions, reproduction steps, and relevant terminal error (remove private paths or URLs). For changes, describe the behavior, add a focused regression test where appropriate, and run the existing suite. Never commit downloaded videos, exports, or model weights.

## License

[MIT](LICENSE) — Copyright © 2026 Lakshmi Muppana. This license covers the project code; dependencies and source media retain their own licenses and rights.

## Implementation references

The repository structure and changes were informed by [GitHub's README guidance](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-readmes), [Flask's local-server documentation](https://flask.palletsprojects.com/en/stable/server/), [FFmpeg's filter documentation](https://ffmpeg.org/ffmpeg-filters.html), [faster-whisper](https://github.com/SYSTRAN/faster-whisper), and [yt-dlp's dependency guidance](https://github.com/yt-dlp/yt-dlp#dependencies).
