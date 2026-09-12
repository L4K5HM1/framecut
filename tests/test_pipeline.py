"""Integration checks use synthetic media; no downloads or speech model required."""
import json
from pathlib import Path
import shutil
import pytest
import media_pipeline as pipeline

@pytest.mark.parametrize('size,captions',[('320x180',False),('90x320',False),('320x180',True)])
def test_real_ffmpeg_export(tmp_path,monkeypatch,size,captions):
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):pytest.skip('FFmpeg not installed')
    # A path containing an apostrophe and spaces exercises the relative ASS-path fix.
    work=tmp_path/"creator's clips";work.mkdir()
    source=work/'source.mp4'
    pipeline.run(['ffmpeg','-nostdin','-y','-f','lavfi','-i',f'color=c=blue:s={size}:r=12:d=1',
                  '-f','lavfi','-i','sine=frequency=440:duration=1','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(source)])
    monkeypatch.setattr(pipeline,'transcribe',lambda audio:[(0,.5,'Test'),(.5,.9,'caption')])
    stages=[]
    output=work/pipeline.export_clip(source,work,'a'*32,0,.8,captions,stages.append)
    data=json.loads(pipeline.run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(output)]))
    video=next(s for s in data['streams'] if s['codec_type']=='video')
    assert (video['width'],video['height'],video['pix_fmt'])==(1080,1920,'yuv420p')
    assert .6<float(data['format']['duration'])<1.1
    assert not list(work.glob('clip-*'))
    assert ('captioning' in stages)==captions
