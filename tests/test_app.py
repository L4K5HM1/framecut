import time
from pathlib import Path
import pytest
import app as web
import media_pipeline as pipeline

@pytest.fixture
def client(tmp_path, monkeypatch):
    downloads = tmp_path / 'downloads'; downloads.mkdir()
    outputs = tmp_path / 'outputs'; outputs.mkdir()
    monkeypatch.setattr(web, 'DOWNLOADS_DIR', downloads)
    monkeypatch.setattr(web, 'OUTPUTS_DIR', outputs)
    web.SOURCES.clear(); web.JOBS.clear()
    web.app.config['TESTING'] = True
    return web.app.test_client()

def source():
    name = 'a' * 32 + '.mp4'
    (web.DOWNLOADS_DIR / name).write_bytes(b'source')
    web.SOURCES[name] = {'duration': 30, 'has_audio': True}
    return name

@pytest.mark.parametrize('url', ['file:///tmp/test', 'https://youtube.com.evil.test/watch?v=abcdefghijk', 'https://youtube.com/playlist?list=abc', 'https://youtube.com@evil.test/watch?v=abcdefghijk', '--help', None])
def test_rejects_bad_url(client, url):
    assert client.post('/api/load', json={'url': url}).status_code == 400

@pytest.mark.parametrize('url', ['https://youtu.be/abcdefghijk', 'https://www.youtube.com/watch?v=abcdefghijk&list=ignore', 'https://youtube.com/shorts/abcdefghijk'])
def test_normalizes_video_url(url):
    assert pipeline.youtube_url(url) == 'https://www.youtube.com/watch?v=abcdefghijk'

def test_json_errors(client):
    assert client.post('/api/load', json=[]).status_code == 400
    assert client.post('/api/load', data='{', content_type='application/json').status_code == 400
    assert client.post('/api/load', data='url=x').status_code == 415
    assert client.post('/api/load', json={}, headers={'Origin': 'https://example.org'}).status_code == 403
    assert client.get('/', headers={'Host':'evil.test'}).status_code == 400

@pytest.mark.parametrize('start,end', [(-1,5),(5,2),(0,31),('NaN',5),(0,'Infinity'),(True,5),(0,.01),('bad',5)])
def test_bad_ranges(client,start,end):
    assert client.post('/api/create_clip',json={'filename':source(),'start':start,'end':end}).status_code==400

def test_traversal_and_unknown_source(client):
    assert client.post('/api/create_clip',json={'filename':'../app.py','start':0,'end':1}).status_code==400
    assert client.post('/api/create_clip',json={'filename':'unknown.mp4','start':0,'end':1}).status_code==404
    assert client.get('/media/unknown.mp4').status_code==404
    assert client.get('/output/app.py').status_code==404

def test_silent_source_and_caption_type(client):
    name=source();web.SOURCES[name]['has_audio']=False
    assert client.post('/api/create_clip',json={'filename':name,'start':0,'end':1,'captions':True}).status_code==400
    assert client.post('/api/create_clip',json={'filename':name,'start':0,'end':1,'captions':'false'}).status_code==400

def wait(client, job):
    for _ in range(100):
        data=client.get('/api/job/'+job).get_json()
        if data['status'] in ('done','error'):return data
        time.sleep(.01)
    raise AssertionError('Worker did not finish')

def test_async_load_and_export(client,monkeypatch):
    def download(url,directory,video_id):
        name=video_id+'.mp4';(directory/name).write_bytes(b'video')
        return {'filename':name,'duration':20,'has_audio':True}
    monkeypatch.setattr(pipeline,'download',download)
    response=client.post('/api/load',json={'url':'https://youtu.be/abcdefghijk'})
    assert response.status_code==202
    loaded=wait(client,response.json['job_id']);assert loaded['status']=='done'
    monkeypatch.setattr(pipeline,'export_clip',lambda *args: args[2]+'.mp4')
    response=client.post('/api/create_clip',json={'filename':loaded['filename'],'start':0,'end':3})
    assert wait(client,response.json['job_id'])['download_url'].endswith('.mp4')

def test_worker_error_recovery(client,monkeypatch):
    def fail(*args):raise RuntimeError('private diagnostic')
    monkeypatch.setattr(pipeline,'download',fail)
    response=client.post('/api/load',json={'url':'https://youtu.be/abcdefghijk'})
    result=wait(client,response.json['job_id'])
    assert result['status']=='error' and 'private diagnostic' not in result['error']

def test_queue_limit(client):
    for _ in range(4):assert web.SLOTS.acquire(False)
    try:assert client.post('/api/load',json={'url':'https://youtu.be/abcdefghijk'}).status_code==429
    finally:
        for _ in range(4):web.SLOTS.release()

def test_page_and_assets(client):
    assert b'Framecut' in client.get('/').data
    assert client.get('/static/app.js').status_code==200
    assert client.get('/api/job/missing').status_code==404

def test_ass_text_and_timestamp(tmp_path):
    path=tmp_path/'captions.ass';pipeline.words_to_ass([(0,1,r'{\b1}Hi'),(1,1,'skip')],path)
    text=path.read_text();assert r'{\b1}' not in text and 'skip' not in text
    assert pipeline.ass_timestamp(59.999)=='0:01:00.00'
