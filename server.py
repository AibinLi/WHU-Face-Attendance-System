"""Local-only classroom attendance application. Run with .venv/Scripts/python server.py."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import csv
import io
import json
import os
import threading
import traceback
from flask import Flask, request, jsonify, send_from_directory, Response
from werkzeug.exceptions import HTTPException
from attendance.service import Service
from attendance.store import uid, find

ROOT = Path(__file__).resolve().parent
app = Flask(__name__, static_folder=str(ROOT / 'static'), static_url_path='/static')
app.config['MAX_CONTENT_LENGTH'] = 120 * 1024**2
service = Service(Path(os.environ.get('ATTENDANCE_DATA', str(ROOT / 'data'))))
executor = ThreadPoolExecutor(max_workers=1)
jobs = {}
job_lock = threading.Lock()


def warmup():
    def load():
        try:
            with service.engine.lock:
                service.engine.load()
        except Exception as exc:
            print('Model warmup:', exc)
    executor.submit(load)


@app.before_request
def local_only():
    if request.host.split(':')[0] not in ('localhost', '127.0.0.1', '[::1]', '::1'):
        return jsonify(error='仅支持本机访问。'), 403
    if request.method != 'GET':
        origin = request.headers.get('Origin')
        if origin and origin != request.host_url.rstrip('/'):
            return jsonify(error='不允许跨站请求。'), 403


@app.after_request
def headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.errorhandler(Exception)
def error(exc):
    if isinstance(exc, HTTPException):
        return jsonify(error=exc.description), exc.code
    if isinstance(exc, (ValueError, KeyError, TypeError)):
        return jsonify(error=str(exc)), 400
    traceback.print_exc()
    return jsonify(error='操作失败：' + str(exc)), 500


def start_job(work):
    identifier = uid('job_')
    jobs[identifier] = dict(id=identifier, status='running', progress=0, total=0, message='准备中', results=[])
    def run():
        try:
            work(jobs[identifier])
            jobs[identifier]['status'] = 'done'
        except Exception as exc:
            traceback.print_exc()
            jobs[identifier].update(status='error', error=str(exc))
    executor.submit(run)
    return jsonify(job_id=identifier)


@app.route('/', methods=["GET"])
def index():
    return send_from_directory(app.static_folder, 'index.html')


@app.route('/api/state', methods=["GET"])
def state():
    return jsonify(service.state())


@app.route('/api/jobs/<identifier>', methods=["GET"])
def job(identifier):
    if identifier not in jobs:
        raise ValueError('任务不存在。')
    return jsonify(jobs[identifier])


@app.route('/media/<kind>/<identifier>.jpg', methods=["GET"])
def media(kind, identifier):
    if kind not in ('images', 'faces'):
        raise ValueError('无效的图片目录。')
    return send_from_directory(service.store.root / kind, identifier + '.jpg')


@app.route('/api/upload', methods=["POST"])
def upload():
    files = request.files.getlist('files')
    if not files or len(files) > 20:
        raise ValueError('请选择 1–20 张图片。')
    entries = [(file.read(), file.filename) for file in files]
    kind, session_id = request.form.get('kind', 'gallery'), request.form.get('session_id') or None
    def work(job):
        job['total'] = len(entries)
        for i, (content, name) in enumerate(entries):
            job['message'] = '正在处理 ' + name
            result = service.ingest(content, name, kind, session_id)
            job['results'].append(result)
            job['progress'] = i + 1
    return start_job(work)


@app.route('/api/import-local', methods=["POST"])
def import_local():
    body = request.get_json()
    base = (ROOT / '原始合照').resolve()
    paths = []
    for relative in body.get('paths', []):
        path = (base / relative).resolve()
        if base not in path.parents or path.suffix.lower() not in ('.jpg', '.jpeg', '.png', '.webp') or not path.is_file():
            raise ValueError('无效的本地照片路径。')
        paths.append(path)
    if not paths:
        raise ValueError('请选择本地照片。')
    def work(job):
        job['total'] = len(paths)
        for i, path in enumerate(paths):
            job['message'] = '正在处理 ' + path.name
            result = service.ingest(path.read_bytes(), path.name, body.get('kind', 'gallery'), body.get('session_id'))
            job['results'].append(result)
            job['progress'] = i + 1
    return start_job(work)


@app.route('/api/gallery/build', methods=["POST"])
def build():
    threshold = (request.get_json(silent=True) or {}).get('threshold')
    return start_job(lambda job: service.build_gallery(threshold))


@app.route('/api/gallery/edit', methods=["POST"])
def edit():
    body = request.get_json()
    service.edit_gallery(body['action'], body)
    return jsonify(ok=True)


@app.route('/api/gallery/suggestions', methods=["GET"])
def suggestions():
    return jsonify(service.suggestions())


@app.route('/api/backup', methods=["POST"])
def backup():
    return jsonify(name=service.store.backup().name)


@app.route('/api/sessions', methods=["POST"])
def create_session():
    body = request.get_json()
    return jsonify(id=service.create_session(body.get('title', '课堂考勤'), bool(body.get('preview', False))))


@app.route('/api/sessions/<identifier>', methods=["GET"])
def result(identifier):
    return jsonify(service.session_result(identifier))


@app.route('/api/sessions/<identifier>/resolve', methods=["POST"])
def resolve(identifier):
    body = request.get_json()
    service.resolve(identifier, body['face_id'], body.get('person_id'))
    return jsonify(ok=True)


@app.route('/api/sessions/<identifier>/close', methods=["POST"])
def close(identifier):
    service.close_session(identifier)
    return jsonify(ok=True)


@app.route('/api/sessions/<identifier>/export', methods=["GET"])
def export(identifier):
    result = service.session_result(identifier)
    if request.args.get('format') == 'json':
        return Response(json.dumps(result, ensure_ascii=False, indent=2), content_type='application/json',
                        headers={'Content-Disposition': 'attachment; filename="attendance.json"'})
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(['场次', '编号', '姓名', '状态', '结束状态'])
    names = dict(present='已到', absent='缺席' if result['session']['closed'] else '暂未匹配', uncertain='身份待确认')
    for p in result['people']:
        # Protect spreadsheet formula interpretation after optional user renaming.
        name = "'" + p['name'] if p['name'].startswith(('=', '+', '-', '@')) else p['name']
        title = result['session']['title']
        if title.startswith(('=', '+', '-', '@')):
            title = "'" + title
        writer.writerow([title, p['number'], name, names[p['status']], '已结束' if result['session']['closed'] else '进行中'])
    return Response('\ufeff' + buffer.getvalue(), content_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition': 'attachment; filename="attendance.csv"'})


if __name__ == '__main__':
    warmup()
    app.run(host='127.0.0.1', port=int(os.environ.get('PORT', 8765)), debug=False, threaded=True)

