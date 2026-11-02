"""Project-local atomic JSON storage with rollback and immutable session galleries."""
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime
import copy
import json
import os
import threading
import uuid


def uid(prefix):
    return prefix + uuid.uuid4().hex[:12]


def now():
    return datetime.now().astimezone().isoformat(timespec='seconds')


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        for directory in ('images', 'faces', 'backups'):
            (self.root / directory).mkdir(exist_ok=True)
        self.path = self.root / 'database.json'
        self.lock = threading.RLock()
        self.data = json.loads(self.path.read_text('utf-8')) if self.path.exists() else dict(
            schema=1, images=[], faces=[], people=[], sessions=[], audit=[],
            settings=dict(threshold=0.36, margin=0.04, cluster_threshold=0.34, confirmed=False))

    @contextmanager
    def transaction(self):
        with self.lock:
            backup = copy.deepcopy(self.data)
            try:
                yield self.data
                temporary = self.path.with_suffix('.tmp')
                temporary.write_text(json.dumps(self.data, ensure_ascii=False, allow_nan=False), 'utf-8')
                os.replace(temporary, self.path)
            except BaseException:
                self.data = backup
                raise

    def backup(self):
        with self.lock:
            target = self.root / 'backups' / (uid('snapshot_') + '.json')
            target.write_text(json.dumps(self.data, ensure_ascii=False), 'utf8')
            return target

    def audit(self, action, details):
        self.data['audit'].append(dict(time=now(), action=action, details=details))


def find(items, identifier):
    for item in items:
        if item['id'] == identifier:
            return item
    raise ValueError('记录不存在，请刷新页面。')
