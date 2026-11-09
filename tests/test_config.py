import json
import os
import pytest
from pydantic import ValidationError
from vision_foundation.config import CameraConfig,ConfigStore,redact_source,protect,unprotect


@pytest.mark.parametrize('index',['0','1','31'])
def test_webcam_indices(index):
    assert CameraConfig(source=index).source==index


@pytest.mark.parametrize('payload',[
    {'kind':'webcam','source':'-1'}, {'kind':'webcam','source':'32'},
    {'kind':'rtsp','source':'http://camera/live'},
    {'kind':'http','source':'file:///etc/passwd'},
    {'kind':'rtsp','source':'rtsp://'},
    {'kind':'rtsp','source':'rtsp://host:99999/live'},
    {'kind':'rtsp','source':'rtsp://host/live\npassword'},
    {'kind':'file','source':'not-present.mp4'},
    {'kind':'webcam','source':'0','backend':'ffmpeg'},
    {'kind':'webcam','stale_after_s':6,'read_timeout_s':4},
    {'id':'../escape'}, {'publish_fps':300}, {'width':99999}, {'unknown':1}
])
def test_invalid_profiles(payload):
    with pytest.raises(ValidationError):CameraConfig(**payload)


@pytest.mark.parametrize('url',[
    'rtsp://user:secret@10.0.0.1:554/token-private?auth=supersecret',
    'rtsp://user:secret@[::1]:554/token-private?auth=supersecret',
    'https://user:secret@camera/token-private?auth=supersecret',
])
def test_redaction(url):
    public=redact_source(url,'rtsp')
    for secret in ('user','secret','private','auth'):
        assert secret not in public


def test_protect_roundtrip():
    secret='rtsp://operator:p@ssword@camera/live'
    assert unprotect(protect(secret))==secret


def test_store_atomic_and_reload(tmp_path):
    store=ConfigStore(tmp_path)
    c=CameraConfig(id='cam',kind='rtsp',source='rtsp://user:secret@camera/live')
    store.put(c)
    assert ConfigStore(tmp_path).get('cam').source==c.source
    assert 'secret' not in str(store.get('cam').public())
    if os.name!='nt': assert store.path.stat().st_mode & 0o777 == 0o600
    store.delete('cam')
    assert ConfigStore(tmp_path).all()==[]


def test_store_rejects_over_capacity(tmp_path):
    store=ConfigStore(tmp_path)
    for i in range(4):store.put(CameraConfig(id=f'cam{i}'))
    with pytest.raises(ValueError):store.put(CameraConfig(id='cam4'))
    assert len(ConfigStore(tmp_path).all())==4


def test_invalid_config_preserved(tmp_path):
    p=tmp_path/'cameras.json';p.write_text('{broken')
    with pytest.raises(json.JSONDecodeError):ConfigStore(tmp_path)
    assert p.read_text()=='{broken'


def test_webcam_index_is_canonical():
    assert CameraConfig(kind="webcam", source="00").source == "0"

def test_file_path_normalized_and_backend_validated(tmp_path, monkeypatch):
    path = tmp_path / "test.avi"
    path.write_bytes(b"placeholder")
    monkeypatch.chdir(tmp_path)
    assert CameraConfig(kind="file", source="test.avi").source == str(path)
    with pytest.raises(ValueError):
        CameraConfig(kind="file", source=str(path), backend="dshow")
