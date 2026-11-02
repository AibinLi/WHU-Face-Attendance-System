import importlib
import io
import json
import pytest
from PIL import Image


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('ATTENDANCE_DATA',str(tmp_path))
    import server
    importlib.reload(server)
    server.app.config['TESTING']=True
    return server.app.test_client(),server


def test_local_api_and_empty_preview(client):
    c,server=client
    assert c.get('/').status_code==200
    assert c.get('/api/state').get_json()['people']==[]
    assert c.post('/api/sessions',json={'preview':True}).status_code==400
    assert c.get('/api/state',headers={'Host':'untrusted.example'}).status_code==403
    assert c.post('/api/backup',headers={'Origin':'https://untrusted.example'}).status_code==403
    assert c.post('/api/import-local',json={'paths':['../server.py']}).status_code==400
    assert c.get('/media/unknown/example.jpg').status_code==400


def test_export_formula_protection_and_provisional_close(client):
    c,server=client
    s=server.service
    with s.store.transaction() as d:
        d['images'].append(dict(id='reference',kind='gallery',session_id=None,sha256='x'))
        d['faces'].append(dict(id='face',image_id='reference',embedding=[1.,0.],excluded=False,
                               person_id='identity',quality=1.,status='unassigned'))
        d['people'].append(dict(id='identity',name='=HYPERLINK("url")',number=1,avatar='face'))
    response=c.post('/api/sessions',json={'title':'=CMD()','preview':True})
    assert response.status_code==200
    sid=response.get_json()['id']
    assert c.get('/api/sessions/'+sid).get_json()['session']['provisional']
    assert c.post('/api/sessions/'+sid+'/close',json={}).status_code==400
    output=c.get('/api/sessions/'+sid+'/export').data.decode('utf-8-sig')
    assert "'=CMD()" in output and "'=HYPERLINK" in output
    assert '暂未匹配' in output
