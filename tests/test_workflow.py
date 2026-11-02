import io
from pathlib import Path
import numpy as np
import pytest
from PIL import Image
from attendance.service import Service


def image_bytes(color):
    out = io.BytesIO()
    Image.new('RGB', (150, 150), color).save(out, format='PNG')
    return out.getvalue()


def fake_face():
    return dict(bbox=[20, 20, 90, 95], landmarks=[[0, 0]] * 5,
                quality=.8, detection_score=.99, face_size=70, sharpness=100,
                embedding=[1., 0.], aligned=np.zeros((112, 112, 3), dtype=np.uint8))


def test_workflow_dedup_snapshot_and_reopen(tmp_path):
    s = Service(tmp_path)
    s.engine.extract = lambda image: [fake_face()]
    first = s.ingest(image_bytes('red'), 'reference.png')
    assert s.ingest(image_bytes('red'), 'reference-again.png')['duplicate']
    s.build_gallery()
    with pytest.raises(ValueError, match='确认底库'):
        s.create_session('test')
    s.edit_gallery('confirm', {'expected': 1})
    identity = s.store.data['people'][0]['id']
    session = s.create_session('test')
    one = s.ingest(image_bytes('blue'), 'first.png', 'attendance', session)
    two = s.ingest(image_bytes('green'), 'second.png', 'attendance', session)
    result = s.session_result(session)
    assert result['counts']['present'] == 1
    assert result['counts']['automatic'] == 2
    assert len(result['images']) == 2
    assert not result['reference_overlap']
    assert len(s.state()['people'][0]['samples']) == 1
    # Gallery edits must not rename or change past session membership.
    s.edit_gallery('rename', {'id': identity, 'name': 'changed'})
    assert s.session_result(session)['people'][0]['name'] == '学生001'
    face = next(f for f in result['faces'] if f['image_id'] == one['image']['id'])
    s.resolve(session, face['id'], None)
    assert s.session_result(session)['counts']['present'] == 1
    s.close_session(session)
    with pytest.raises(ValueError, match='已结束'):
        s.ingest(image_bytes('white'), 'third.png', 'attendance', session)
    reopened = Service(tmp_path)
    assert reopened.session_result(session)['session']['closed']
    assert reopened.session_result(session)['counts']['present'] == 1


def test_same_photo_manual_collision_rejected(tmp_path):
    s = Service(tmp_path)
    s.engine.extract = lambda image: [fake_face()]
    s.ingest(image_bytes('red'), 'reference.png')
    s.build_gallery(); s.edit_gallery('confirm', {})
    session = s.create_session('test')
    s.engine.extract = lambda image: [fake_face(), fake_face()]
    s.ingest(image_bytes('blue'), 'probe.png', 'attendance', session)
    result = s.session_result(session)
    pending = next(f for f in result['faces'] if f['status'] != 'auto')
    with pytest.raises(ValueError, match='已有另一张人脸'):
        s.resolve(session, pending['id'], s.store.data['people'][0]['id'])
    with pytest.raises(ValueError, match='未识别或冲突'):
        s.close_session(session)


def test_failed_transaction_rolls_back(tmp_path):
    s = Service(tmp_path)
    with pytest.raises(RuntimeError):
        with s.store.transaction() as d:
            d['people'].append({'id': 'broken'})
            raise RuntimeError('failure')
    assert not s.store.data['people']


def test_preview_cannot_be_closed_as_verified_attendance(tmp_path):
    s=Service(tmp_path)
    s.engine.extract=lambda image:[fake_face()]
    s.ingest(image_bytes('red'),'reference.png')
    s.build_gallery()
    sid=s.create_session('unverified',preview=True)
    s.ingest(image_bytes('blue'),'probe.png','attendance',sid)
    with pytest.raises(ValueError,match='不能生成正式'):
        s.close_session(sid)
    assert not s.store.data['settings']['confirmed']
