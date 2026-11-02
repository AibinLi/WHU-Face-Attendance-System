from pathlib import Path
import hashlib
import io
import json
import time
import cv2
import numpy as np
from .engine import Engine, read_image
from .matching import assign, scores_for, cluster_faces, unit
from .store import Store, uid, now, find


class Service:
    def __init__(self, root):
        self.store = Store(root)
        self.engine = Engine()

    def public_face(self, f):
        return {k: v for k, v in f.items() if k != 'embedding'}

    def state(self):
        with self.store.lock:
            d = self.store.data
            gallery_image_ids = {i['id'] for i in d['images'] if i['kind'] == 'gallery'}
            people = []
            for p in d['people']:
                samples = [self.public_face(f) for f in d['faces'] if f['image_id'] in gallery_image_ids and f.get('person_id') == p['id'] and not f.get('excluded')]
                if samples:
                    people.append(dict(**p, samples=samples))
            sessions = [{k: v for k, v in s.items() if k != 'gallery'} for s in d['sessions']]
            return dict(people=people, images=d['images'], faces=[self.public_face(f) for f in d['faces']],
                        sessions=sessions, settings=d['settings'], provider=self.engine.provider,
                        model='SCRFD-10G · ArcFace R100 + AdaFace IR101 / WebFace12M',
                        local_photos=[str(p.relative_to(Path(__file__).resolve().parents[1] / '原始合照'))
                                      for p in (Path(__file__).resolve().parents[1] / '原始合照').rglob('*')
                                      if p.suffix.lower() in ('.jpg', '.jpeg', '.png', '.webp')])

    def ingest(self, content, name, kind='gallery', session_id=None):
        if kind not in ('gallery', 'attendance'):
            raise ValueError('图片用途无效。')
        if len(content) > 35 * 1024**2:
            raise ValueError('单张图片不能超过 35MB。')
        digest = hashlib.sha256(content).hexdigest()
        # Serialize ingestion with gallery editing and matching; no partially committed images.
        with self.store.lock:
            d = self.store.data
            if d.get('model_id') and d['model_id'] != self.engine.model_id:
                raise ValueError('模型版本与底库特征不一致，请先迁移底库。')
            session = find(d['sessions'], session_id) if kind == 'attendance' else None
            if session and session['closed']:
                raise ValueError('本场考勤已结束，请新建场次。')
            if kind == 'gallery' and d['people']:
                raise ValueError('底库已生成；如需增补参考脸，请在底库中使用手动分组，或先备份后重新建库。')
            existing = next((i for i in d['images'] if i['sha256'] == digest and i['kind'] == kind and i.get('session_id') == session_id), None)
            if existing:
                return dict(image=existing, duplicate=True)
            image_id = uid('img_')
            path = self.store.root / 'images' / (image_id + '.jpg')
            temporary = self.store.root / 'images' / (image_id + '.upload')
            temporary.write_bytes(content)
            try:
                image = read_image(temporary)
            finally:
                temporary.unlink(missing_ok=True)
            start = time.perf_counter()
            extracted = self.engine.extract(image)
            faces = []
            for f in extracted:
                face_id = uid('face_')
                aligned = f.pop('aligned')
                # Keep context in the avatar crop; model uses only the aligned face above.
                x1, y1, x2, y2 = f['bbox']
                pad = max(x2 - x1, y2 - y1) * 0.30
                crop = image[max(0, int(y1 - pad)):min(image.shape[0], int(y2 + pad)),
                             max(0, int(x1 - pad)):min(image.shape[1], int(x2 + pad))]
                crop = cv2.resize(crop, (160, 160), interpolation=cv2.INTER_CUBIC)
                cv2.imencode('.jpg', crop)[1].tofile(str(self.store.root / 'faces' / (face_id + '.jpg')))
                f.update(id=face_id, image_id=image_id, person_id=None, excluded=False,
                         status='unassigned', score=None, margin=None, candidates=[])
                faces.append(f)
            cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 94])[1].tofile(str(path))
            record = dict(id=image_id, name=Path(name).name, kind=kind, session_id=session_id,
                          sha256=digest, width=image.shape[1], height=image.shape[0], faces=len(faces),
                          elapsed=round(time.perf_counter() - start, 2), created=now(),
                          reference_overlap=any(i['sha256'] == digest and i['kind'] == 'gallery' for i in d['images']))
            with self.store.transaction():
                d['model_id'] = self.engine.model_id
                d['images'].append(record)
                d['faces'].extend(faces)
                if session:
                    self._match_image(faces, session)
                self.store.audit('upload', dict(image_id=image_id, count=len(faces), kind=kind))
            return dict(image=record, duplicate=False)

    def _new_person(self, face_ids):
        d = self.store.data
        number = max([p['number'] for p in d['people']] + [0]) + 1
        samples = [find(d['faces'], f) for f in face_ids]
        person = dict(id=uid('p_'), number=number, name='学生%03d' % number,
                      avatar=max(samples, key=lambda f: f['quality'])['id'])
        d['people'].append(person)
        for face in samples:
            face['person_id'] = person['id']
        return person

    def build_gallery(self, threshold=None):
        with self.store.transaction() as d:
            if d['people']:
                raise ValueError('底库已生成，请使用合并、拆分工具修正，避免编号变化。')
            faces = [f for f in d['faces'] if not f['excluded'] and
                     find(d['images'], f['image_id'])['kind'] == 'gallery']
            if not faces:
                raise ValueError('请先上传至少一张能检测到人脸的底库合照。')
            value = float(threshold if threshold is not None else d['settings']['cluster_threshold'])
            if not 0.15 <= value <= 0.85:
                raise ValueError('聚类阈值应在 0.15–0.85 之间。')
            for group in cluster_faces(faces, value):
                self._new_person(group)
            d['settings']['confirmed'] = False
            self.store.audit('build_gallery', dict(threshold=value, count=len(d['people'])))
        return self.state()

    def edit_gallery(self, action, payload):
        with self.store.transaction() as d:
            gallery_image_ids = {i['id'] for i in d['images'] if i['kind'] == 'gallery'}
            if action == 'confirm':
                active = {f['person_id'] for f in d['faces'] if f.get('person_id') and not f['excluded'] and find(d['images'], f['image_id'])['kind'] == 'gallery'}
                if not active:
                    raise ValueError('没有可确认的底库。')
                expected = payload.get('expected')
                if expected and int(expected) != len(active):
                    raise ValueError('当前编号数与填写的班级人数不同，请先检查重复或漏检。')
                d['settings']['confirmed'] = True
                self.store.audit('confirm_gallery', dict(count=len(active), expected=expected))
                return
            if action == 'merge':
                ids = list(dict.fromkeys(payload.get('ids', [])))
                if len(ids) < 2:
                    raise ValueError('请至少选择两个编号。')
                for identity in ids:
                    find(d['people'], identity)
                samples = [f for f in d['faces'] if f['image_id'] in gallery_image_ids and f.get('person_id') in ids and not f['excluded']]
                if len({f['image_id'] for f in samples}) != len(samples):
                    raise ValueError('这些编号在同一照片中同时出现，不能合并；请先排除重复检测框。')
                for f in samples:
                    f['person_id'] = ids[0]
                d['people'][:] = [p for p in d['people'] if p['id'] not in ids[1:]]
            elif action == 'split':
                ids = list(dict.fromkeys(payload.get('face_ids', [])))
                if not ids:
                    raise ValueError('请先选择要拆出的参考脸。')
                samples = [find(d['faces'], identity) for identity in ids]
                if any(find(d['images'], f['image_id'])['kind'] != 'gallery' or f['excluded'] for f in samples):
                    raise ValueError('只能拆分有效的底库参考脸。')
                if len({f['person_id'] for f in samples}) != 1:
                    raise ValueError('一次只能拆分同一个编号的参考脸。')
                self._new_person(ids)
            elif action == 'exclude':
                f = find(d['faces'], payload['face_id'])
                if find(d['images'], f['image_id'])['kind'] != 'gallery':
                    raise ValueError('该操作只用于底库照片。')
                f['excluded'] = bool(payload.get('excluded', True))
            elif action == 'avatar':
                p = find(d['people'], payload['id'])
                f = find(d['faces'], payload['face_id'])
                if f['person_id'] != p['id'] or f['excluded']:
                    raise ValueError('头像必须属于该编号。')
                p['avatar'] = f['id']
            elif action == 'rename':
                p = find(d['people'], payload['id'])
                name = str(payload['name']).strip()
                if not name or len(name) > 40:
                    raise ValueError('名称长度应为 1–40 个字符。')
                p['name'] = name
            else:
                raise ValueError('不支持的底库操作。')
            # Repair avatars after split/exclusion; remove empty people.
            retained = []
            for p in d['people']:
                samples = [f for f in d['faces'] if f['image_id'] in gallery_image_ids and f.get('person_id') == p['id'] and not f['excluded']]
                if samples:
                    if p['avatar'] not in {f['id'] for f in samples}:
                        p['avatar'] = max(samples, key=lambda f: f['quality'])['id']
                    retained.append(p)
            d['people'][:] = retained
            d['settings']['confirmed'] = False
            self.store.audit(action, payload)

    def create_session(self, title, preview=False):
        with self.store.transaction() as d:
            if not d['settings']['confirmed'] and not preview:
                raise ValueError('请先核对并确认底库人数。')
            gallery = []
            for p in d['people']:
                samples = [f for f in d['faces'] if f.get('person_id') == p['id'] and not f['excluded'] and find(d['images'], f['image_id'])['kind'] == 'gallery']
                if samples:
                    gallery.append(dict(**p, templates=[f['embedding'] for f in samples], face_ids=[f['id'] for f in samples]))
            session = dict(id=uid('session_'), title=str(title).strip()[:80] or '课堂考勤',
                           created=now(), closed=False, gallery=gallery, provisional=bool(preview),
                           threshold=d['settings']['threshold'], margin=d['settings']['margin'])
            if not gallery:
                raise ValueError('底库为空，请先导入照片并生成编号。')
            d['sessions'].append(session)
            self.store.audit('create_session', dict(id=session['id']))
            return session['id']

    def _match_image(self, faces, session):
        if not faces:
            return
        gallery = session['gallery']
        scores = scores_for([f['embedding'] for f in faces], [p['templates'] for p in gallery])
        for f, result in zip(faces, assign(scores, session['threshold'], session['margin'])):
            f['person_id'] = gallery[result['index']]['id'] if result['index'] is not None else None
            f.update(status=result['status'], score=result['score'], margin=result['margin'],
                     predicted_person_id=f['person_id'], predicted_status=result['status'],
                     candidates=[dict(id=gallery[c['index']]['id'], name=gallery[c['index']]['name'], score=c['score'], avatar=gallery[c['index']]['avatar']) for c in result['candidates']])

    def session_result(self, session_id):
        with self.store.lock:
            d = self.store.data
            s = find(d['sessions'], session_id)
            images = [i for i in d['images'] if i.get('session_id') == session_id]
            image_ids = {i['id'] for i in images}
            faces = [f for f in d['faces'] if f['image_id'] in image_ids]
            present = {f['person_id'] for f in faces if f['status'] in ('auto', 'manual') and not f['excluded']}
            unresolved = [f for f in faces if f['status'] in ('review', 'unknown') and not f['excluded']]
            possible = {c['id'] for f in unresolved for c in f['candidates'][:2] if c['score'] >= s['threshold']}
            people = []
            for p in s['gallery']:
                status = 'present' if p['id'] in present else ('uncertain' if p['id'] in possible else 'absent')
                people.append(dict(id=p['id'], name=p['name'], number=p['number'], avatar=p['avatar'], status=status))
            counts = dict(expected=len(people), present=len(present), absent=sum(p['status'] == 'absent' for p in people),
                          uncertain=sum(p['status'] == 'uncertain' for p in people), review=len(unresolved),
                          detections=len(faces), automatic=sum(f['status'] == 'auto' for f in faces),
                          manual=sum(f['status'] == 'manual' for f in faces))
            return dict(session={k: v for k, v in s.items() if k != 'gallery'}, counts=counts,
                        people=people, images=images, faces=[self.public_face(f) for f in faces],
                        reference_overlap=any(i['reference_overlap'] for i in images))

    def resolve(self, session_id, face_id, person_id):
        with self.store.transaction() as d:
            s = find(d['sessions'], session_id)
            if s['closed']:
                raise ValueError('本场考勤已结束。')
            f = find(d['faces'], face_id)
            image = find(d['images'], f['image_id'])
            if image.get('session_id') != session_id:
                raise ValueError('人脸不属于本场考勤。')
            if person_id:
                find(s['gallery'], person_id)
                if any(other['id'] != f['id'] and other['image_id'] == f['image_id'] and other.get('person_id') == person_id and other['status'] in ('auto', 'manual') for other in d['faces']):
                    raise ValueError('同一照片已有另一张人脸使用该编号，请先修正另一张人脸。')
                f.update(person_id=person_id, status='manual', excluded=False)
            else:
                f.update(person_id=None, status='ignored', excluded=True)
            self.store.audit('resolve', dict(face_id=face_id, person_id=person_id, session_id=session_id))

    def close_session(self, session_id):
        with self.store.transaction() as d:
            s = find(d['sessions'], session_id)
            result = self.session_result(session_id)
            if s.get('provisional'):
                raise ValueError('预览场次的底库尚未核对，不能生成正式缺席结果。请核对底库后新建正式场次。')
            if not result['images']:
                raise ValueError('请先上传考勤照片。')
            if result['counts']['review']:
                raise ValueError('仍有未识别或冲突人脸，请确认或标为不计入后再结束。')
            s['closed'] = True
            s['ended'] = now()
            self.store.audit('close_session', dict(id=session_id, counts=result['counts']))

    def suggestions(self):
        with self.store.lock:
            d = self.store.data
            gallery_image_ids = {i['id'] for i in d['images'] if i['kind'] == 'gallery'}
            groups = []
            for p in d['people']:
                fs = [f for f in d['faces'] if f['image_id'] in gallery_image_ids and f.get('person_id') == p['id'] and not f['excluded']]
                if fs:
                    groups.append((p, fs, unit(np.mean([f['embedding'] for f in fs], axis=0))))
            candidates = []
            for i, (a, af, ae) in enumerate(groups):
                for b, bf, be in groups[i + 1:]:
                    if {f['image_id'] for f in af} & {f['image_id'] for f in bf}:
                        continue
                    score = float(ae @ be)
                    if score >= 0.28:
                        candidates.append(dict(a=a['id'], b=b['id'], score=round(score, 4)))
            return sorted(candidates, key=lambda c: -c['score'])[:40]
