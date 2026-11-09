import hashlib,json,time
from types import SimpleNamespace
import numpy as np
from vision_app.evidence import EvidenceWriter
from vision_app.controller import Controller
from vision_foundation.config import CameraConfig

def test_evidence_pair_sidecar_and_hashes(tmp_path,store):
    writer=EvidenceWriter(tmp_path/'e',store)
    try:
        eid=writer.submit('cam',np.zeros((120,160,3),np.uint8),np.full((120,160,3),50,np.uint8),{'sequence':12},[{'code':'PESSOA_OBSERVADA'}])
        assert writer.flush()
        path=tmp_path/'e'/eid
        meta=json.loads((path/'evento.json').read_text())
        assert meta['metadata']['sequence']==12
        for name,h in meta['sha256'].items():assert hashlib.sha256((path/name).read_bytes()).hexdigest()==h
        assert writer.saved==1 and writer.failures==0
    finally:writer.close()

def test_retention_removes_old_groups(tmp_path,store):
    writer=EvidenceWriter(tmp_path/'e',store,max_files=1)
    try:
        frame=np.zeros((120,160,3),np.uint8)
        first=writer.submit('cam',frame,frame,{},[]);assert writer.flush()
        second=writer.submit('cam',frame,frame,{},[]);assert writer.flush()
        assert not (tmp_path/'e'/first).exists() and (tmp_path/'e'/second/'evento.json').exists()
    finally:writer.close()

def test_low_space_is_reported_not_silent(tmp_path,store,monkeypatch):
    monkeypatch.setattr('vision_app.evidence.shutil.disk_usage',lambda p:SimpleNamespace(free=0))
    writer=EvidenceWriter(tmp_path/'e',store)
    try:
        frame=np.zeros((120,160,3),np.uint8);writer.submit('cam',frame,frame,{},[])
        assert writer.flush() and writer.failures==1
        store.flush();assert any(r['code']=='EVIDENCIA_FALHOU' for r in store.events())
    finally:writer.close()

def test_export_diagnostic_redacts_credentials(tmp_path):
    import zipfile
    c=Controller(tmp_path/'data',tmp_path/'models')
    try:
        c.configs.put(CameraConfig(id='secret',name='Rede',kind='rtsp',source='rtsp://privateuser:swordfish@127.0.0.1:554/api-secret?token=hidden'))
        dest=tmp_path/'diag.zip';c.diagnostic(dest)
        with zipfile.ZipFile(dest) as z:text=b''.join(z.read(n) for n in z.namelist()).decode()
        for secret in ['swordfish','privateuser','api-secret','token=hidden']:assert secret not in text
    finally:c.close()

def test_csv_formula_escaped(tmp_path):
    c=Controller(tmp_path/'data',tmp_path/'models')
    try:
        c.events.emit('=cmd','TEST','=danger',payload={'value':'x'});c.events.flush()
        path=tmp_path/'events.csv';assert c.export_csv(path)==1
        assert "'=cmd" in path.read_text(encoding='utf-8-sig') and "'=danger" in path.read_text(encoding='utf-8-sig')
    finally:c.close()
