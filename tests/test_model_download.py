import hashlib
import io
import pytest
from vision_app import model

@pytest.fixture
def tiny(monkeypatch):
    content=b'non-executable-test-model-bytes'
    monkeypatch.setattr(model,'MODEL_SIZE',len(content))
    monkeypatch.setattr(model,'MODEL_SHA256',hashlib.sha256(content).hexdigest())
    return content

def test_verified_download_and_no_second_network_call(tmp_path,tiny):
    calls=[]
    def opener(*args,**kwargs):calls.append(1);return io.BytesIO(tiny)
    p=model.ensure_model(tmp_path,opener=opener)
    assert p.read_bytes()==tiny and model.verified(p)
    assert model.ensure_model(tmp_path,opener=opener)==p and len(calls)==1
    assert not list(tmp_path.glob('*.download'))

def test_wrong_existing_model_preserved(tmp_path,tiny):
    p=tmp_path/model.MODEL_FILE;p.write_bytes(b'broken')
    with pytest.raises(ValueError):model.ensure_model(tmp_path)
    assert p.read_bytes()==b'broken'

def test_download_corruption_rejected(tmp_path,tiny):
    with pytest.raises(RuntimeError):model.ensure_model(tmp_path,opener=lambda *a,**k:io.BytesIO(b'bad'))
    assert not list(tmp_path.iterdir())

def test_download_size_bounded(tmp_path,tiny):
    with pytest.raises(RuntimeError):model.ensure_model(tmp_path,opener=lambda *a,**k:io.BytesIO(tiny*3))
    assert not list(tmp_path.iterdir())

def test_second_url_fallback(tmp_path,tiny):
    calls=[]
    def opener(*a,**k):
        calls.append(1)
        if len(calls)==1:raise OSError('offline')
        return io.BytesIO(tiny)
    assert model.ensure_model(tmp_path,opener=opener).exists() and len(calls)==2

def test_offline_missing(tmp_path):
    with pytest.raises(FileNotFoundError):model.ensure_model(tmp_path,allow_download=False)
