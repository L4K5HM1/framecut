"""Framecut: a single-user, local Flask application."""
from concurrent.futures import ThreadPoolExecutor
import logging
import math
from pathlib import Path
import threading
import uuid

from flask import Flask, abort, jsonify, render_template, request, send_from_directory
from werkzeug.exceptions import HTTPException
import media_pipeline as pipeline

BASE_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = BASE_DIR / 'downloads'
OUTPUTS_DIR = BASE_DIR / 'outputs'
for directory in (DOWNLOADS_DIR, OUTPUTS_DIR):
    directory.mkdir(exist_ok=True)

app = Flask(__name__)
app.config.update(MAX_CONTENT_LENGTH=8192, TRUSTED_HOSTS=['localhost', '127.0.0.1', '[::1]'])
JOBS = {}
SOURCES = {}
LOCK = threading.Lock()
EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix='framecut')
SLOTS = threading.BoundedSemaphore(4)


@app.before_request
def local_requests_only():
    # JSON-only POSTs and a same-origin check prevent unrelated websites submitting jobs.
    origin = request.headers.get('Origin')
    if origin and origin != request.host_url.rstrip('/'):
        abort(403, description='Requests must come from this local app.')
    if request.method == 'POST' and not request.is_json:
        abort(415, description='Send a JSON request body.')


@app.errorhandler(HTTPException)
def http_error(error):
    return jsonify(error=error.description), error.code


def body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, description='Expected a JSON object.')
    return data


def update_job(job_id, **fields):
    with LOCK:
        JOBS[job_id].update(fields)


def submit(work):
    if not SLOTS.acquire(blocking=False):
        abort(429, description='The queue is full. Wait for an existing job to finish.')
    job_id = uuid.uuid4().hex
    with LOCK:
        # Bound completed job metadata; files remain available until manually removed.
        if len(JOBS) >= 100:
            for old in list(JOBS):
                if JOBS[old]['status'] in ('done', 'error'):
                    del JOBS[old]
                    break
        JOBS[job_id] = {'status': 'queued'}

    def worker():
        try:
            result = work(job_id)
            update_job(job_id, status='done', **result)
        except Exception as exc:
            app.logger.exception('Job %s failed', job_id)
            message = str(exc) if isinstance(exc, pipeline.PipelineError) else 'Processing failed. See the terminal log for details.'
            update_job(job_id, status='error', error=message)
        finally:
            SLOTS.release()
    try:
        EXECUTOR.submit(worker)
    except Exception:
        SLOTS.release()
        with LOCK:
            JOBS.pop(job_id, None)
        abort(503, description='The worker is unavailable. Restart the app.')
    return jsonify(job_id=job_id), 202


@app.post('/api/load')
def load_video():
    try:
        url = pipeline.youtube_url(body().get('url'))
    except ValueError as exc:
        abort(400, description=str(exc))

    def work(job_id):
        update_job(job_id, status='downloading')
        result = pipeline.download(url, DOWNLOADS_DIR, uuid.uuid4().hex)
        with LOCK:
            SOURCES[result['filename']] = result
        return {**result, 'stream_url': '/media/' + result['filename']}
    return submit(work)


@app.post('/api/create_clip')
def create_clip():
    data = body()
    filename = data.get('filename')
    if not isinstance(filename, str) or Path(filename).name != filename:
        abort(400, description='Invalid source filename.')
    with LOCK:
        source = SOURCES.get(filename)
    if not source or not (DOWNLOADS_DIR / filename).is_file():
        abort(404, description='Source not found. Load the video again.')
    try:
        if isinstance(data.get('start'), bool) or isinstance(data.get('end'), bool):
            raise ValueError
        start, end = float(data['start']), float(data['end'])
        if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end <= source['duration']):
            raise ValueError
        if end - start < 0.1 or end - start > 180:
            raise ValueError
    except (TypeError, ValueError, KeyError):
        abort(400, description='Choose a valid range within the source, from 0.1 to 180 seconds long.')
    captions = data.get('captions', True)
    if not isinstance(captions, bool):
        abort(400, description='Captions must be true or false.')
    if captions and not source['has_audio']:
        abort(400, description='This video has no audio. Turn off captions to export it.')

    def work(job_id):
        name = pipeline.export_clip(DOWNLOADS_DIR / filename, OUTPUTS_DIR, job_id,
                                    start, end, captions, lambda stage: update_job(job_id, status=stage))
        return {'download_url': '/output/' + name}
    return submit(work)


@app.get('/api/job/<job_id>')
def job_status(job_id):
    with LOCK:
        job = dict(JOBS[job_id]) if job_id in JOBS else None
    if job is None:
        abort(404, description='Job not found. The app may have restarted.')
    return jsonify(job)


@app.get('/media/<filename>')
def media(filename):
    with LOCK:
        known = filename in SOURCES
    if not known:
        abort(404)
    return send_from_directory(DOWNLOADS_DIR, filename, conditional=True)


@app.get('/output/<filename>')
def output(filename):
    if len(filename) != 36 or not filename.endswith('.mp4'):
        abort(404)
    try:
        uuid.UUID(hex=filename[:-4])
    except ValueError:
        abort(404)
    return send_from_directory(OUTPUTS_DIR, filename, conditional=True)


@app.get('/')
def index():
    return render_template('index.html')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    app.run(host='127.0.0.1', port=5001, debug=False)
