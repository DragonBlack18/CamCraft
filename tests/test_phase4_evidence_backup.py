from contextlib import closing
import json,sqlite3,time,zipfile
from pathlib import Path
import numpy as np
import pytest
from vision_app.controller import Controller
from vision_app.backup import restore_backup
from vision_app.safe_archive import verify_archive,write_archive
from vision_app.instance import InstanceLock


@pytest.fixture
def app(tmp_path):
    c=Controller(tmp_path/'data',tmp_path/'models')
    yield c
    c.close()


def evidence(app):
    frame=np.full((120,160,3),100,np.uint8)
    meta={'received_monotonic':time.monotonic(),'received_utc':time.time(),'sequence':1,'session':'s'}
    eid=app.evidence.submit('webcam0',frame,frame,meta,[])
    assert app.evidence.flush()
    app.events.emit('webcam0','AUSENCIA_CONFIRMADA','teste',payload={'event_id':'ev1','evidence_id':eid})
    assert app.events.flush()
    row=next(r for r in app.events.events() if r['code']=='AUSENCIA_CONFIRMADA')
    return eid,row


def test_inspect_export_hashes_and_review(app,tmp_path):
    eid,row=evidence(app)
    assert app.evidence_review.inspect(eid)['state']=='VERIFIED'
    app.review_event(row['id'],'INCONCLUSIVO','Não identifica autoria')
    p=tmp_path/'incident.zip';app.evidence_review.export_incident(row['id'],p)
    doc=verify_archive(p);assert doc['kind']=='vision-incident'
    assert 'evidencia/quadro.jpg' in doc['files']
    with zipfile.ZipFile(p) as z:assert len(json.loads(z.read('revisoes.json')))==1


def test_corruption_blocks_verified_export(app,tmp_path):
    eid,row=evidence(app);(app.evidence_review.folder(eid)/'quadro.jpg').write_bytes(b'changed')
    assert app.evidence_review.inspect(eid)['state']=='MODIFIED'
    with pytest.raises(ValueError,match='divergente'):app.evidence_review.export_incident(row['id'],tmp_path/'x.zip')


def test_missing_record_only_requires_explicit_choice(app,tmp_path):
    app.events.emit('webcam0','AUSENCIA_CONFIRMADA','x');app.events.flush();row=app.events.events()[0]
    with pytest.raises(ValueError):app.evidence_review.export_incident(row['id'],tmp_path/'x.zip')
    app.evidence_review.export_incident(row['id'],tmp_path/'x.zip',allow_missing=True)
    assert verify_archive(tmp_path/'x.zip')['metadata']['evidence_state']=='MISSING'


def test_preserved_evidence_survives_retention(app):
    eid,row=evidence(app);app.evidence_review.preserve(eid,True)
    app.evidence.max_bytes=1;app.evidence._retention()
    assert app.evidence_review.inspect(eid)['state']=='VERIFIED'
    assert app.evidence.health()['retention_blocked_by_preserved']
    app.evidence_review.preserve(eid,False);app.evidence._retention()
    assert app.evidence_review.inspect(eid)['state']=='MISSING'


def test_bad_evidence_id_rejected(app):
    with pytest.raises(ValueError):app.evidence_review.inspect('../data')


def test_backup_restore_wal_reviews_dataset(app,tmp_path):
    eid,row=evidence(app);app.review_event(row['id'],'CONFIRMADO')
    image=np.zeros((80,120,3),np.uint8);app.dataset.capture(image,{'session':'s'},camera_id='webcam0')
    p=tmp_path/'backup.zip';app.backup(p)
    result=restore_backup(p,tmp_path/'restored')
    assert 'dataset' in result['restored'] and 'events.sqlite3' in result['restored']
    clone=Controller(tmp_path/'restored',tmp_path/'models')
    try:
        assert clone.reviews.verify_chain()['verified_records']==1
        assert clone.evidence_review.inspect(eid)['state']=='VERIFIED'
        assert len(clone.dataset.list())==1
    finally:clone.close()
    with pytest.raises(ValueError,match='vazio'):restore_backup(p,tmp_path/'restored')


def test_backup_refuses_running_camera_without_touching_files(app,tmp_path):
    app.camera=object()
    try:
        with pytest.raises(ValueError,match='Pare'):app.backup(tmp_path/'backup.zip')
    finally:app.camera=None
    assert not (tmp_path/'backup.zip').exists()


def test_backup_cannot_write_inside_data(app):
    with pytest.raises(ValueError):app.backup(app.directory/'backup.zip')


def test_restore_invalid_kind_and_whitelist(tmp_path):
    p=tmp_path/'bad.zip';write_archive(p,[('data/evil.py',b'bad')],kind='vision-backup')
    with pytest.raises(ValueError):restore_backup(p,tmp_path/'dest')
    assert not (tmp_path/'dest').exists()


def test_destination_instance_lock_prevents_restore(app,tmp_path):
    path=tmp_path/'b.zip';app.backup(path)
    lock=InstanceLock(tmp_path/'new')
    try:
        with pytest.raises(RuntimeError):restore_backup(path,tmp_path/'new')
    finally:lock.close()
