import hashlib
import json
import time
from pathlib import Path

import cv2
import numpy as np
import pytest

from vision_app.clips import ClipRecorder
from vision_app.evidence import EvidenceWriter
from tests.conftest import wait_for


def test_before_after_evidence_preserves_different_frame_times(tmp_path,store):
    w=EvidenceWriter(tmp_path/'evidence',store)
    try:
        before=np.full((120,160,3),70,np.uint8);after=np.full_like(before,170)
        extras={'antes_o_0123456789abcdef.jpg':{'frame':before,'metadata':{'sequence':11,'frame_utc':100.,'state':'PRESENTE'}}}
        eid=w.submit('room',after,after,{'sequence':25,'received_utc':110},[{'code':'AUSENCIA_CONFIRMADA'}],before_images=extras)
        assert w.flush()
        directory=w.directory/eid
        doc=json.loads((directory/'evento.json').read_text())
        assert doc['before_images']['antes_o_0123456789abcdef.jpg']['sequence']==11
        assert doc['metadata']['sequence']==25
        assert len(doc['sha256'])==3
        for name,digest in doc['sha256'].items():assert hashlib.sha256((directory/name).read_bytes()).hexdigest()==digest
    finally:w.close()


def test_extra_evidence_rejects_path_injection(tmp_path,store):
    w=EvidenceWriter(tmp_path/'evidence',store)
    try:
        frame=np.zeros((60,100,3),np.uint8)
        with pytest.raises(ValueError):w.submit('room',frame,frame,{},[],before_images={'../bad.jpg':{'frame':frame,'metadata':{}}})
    finally:w.close()


def offer(recorder,session,base,count=5,camera='room'):
    for i in range(count):
        meta={'session':session,'sequence':i+1,'received_monotonic':base+i*.14,'received_utc':1700000000+i*.14}
        frame=np.full((120,160,3),40+i*20,np.uint8)
        recorder.offer(camera,frame,meta)
        time.sleep(.05)
    wait_for(lambda:recorder.frames.unfinished_tasks==0)
    return meta


def test_actual_avi_pre_and_post_frames_hash_and_timeline(tmp_path,store):
    rec=ClipRecorder(tmp_path,store,sample_fps=10,pre_seconds=2,post_seconds=.4)
    eid='e_'+'a'*32;directory=tmp_path/eid;directory.mkdir();(directory/'.clip-pendente').touch()
    base=time.monotonic()-1
    try:
        meta=offer(rec,'session1',base)
        assert rec.request(eid,'room',meta)
        offer(rec,'session1',base+.70,3)
        assert rec.flush(3) and rec.saved==1 and rec.failed==0
        doc=json.loads((directory/'clip.json').read_text())
        assert len(doc['frames'])>=5
        assert min(f['frame_monotonic'] for f in doc['frames'])<meta['received_monotonic']
        assert max(f['frame_monotonic'] for f in doc['frames'])>meta['received_monotonic']
        assert hashlib.sha256((directory/'clip.avi').read_bytes()).hexdigest()==doc['sha256']['clip.avi']
        cap=cv2.VideoCapture(str(directory/'clip.avi'));count=0
        while True:
            ok,frame=cap.read()
            if not ok:break
            count+=1;assert frame.shape==(120,160,3)
        cap.release();assert count==len(doc['frames'])
        assert not (directory/'.clip-pendente').exists()
    finally:rec.close()


def test_clip_sessions_never_mixed(tmp_path,store):
    rec=ClipRecorder(tmp_path,store,sample_fps=10,pre_seconds=2,post_seconds=.1)
    eid='e_'+'b'*32;directory=tmp_path/eid;directory.mkdir()
    try:
        offer(rec,'old',time.monotonic()-2)
        meta=offer(rec,'new',time.monotonic()-.7)
        assert rec.request(eid,'room',meta)
        assert rec.flush(3)
        doc=json.loads((directory/'clip.json').read_text())
        assert doc['session']=='new'
        assert len(doc['frames'])==5
    finally:rec.close()


def test_closing_completes_partial_clip(tmp_path,store):
    rec=ClipRecorder(tmp_path,store,sample_fps=10,post_seconds=2)
    directory=tmp_path/('e_'+'c'*32);directory.mkdir()
    meta=offer(rec,'s',time.monotonic()-.7)
    assert rec.request(directory.name,'room',meta)
    rec.close()
    doc=json.loads((directory/'clip.json').read_text())
    assert not doc['post_event_complete'] and doc['completion_reason']=='encerramento'


def test_clip_missing_frames_does_not_fabricate_video(tmp_path,store):
    rec=ClipRecorder(tmp_path,store,post_seconds=.05)
    directory=tmp_path/('e_'+'d'*32);directory.mkdir();(directory/'.clip-pendente').touch()
    try:
        assert rec.request(directory.name,'room',{'session':'none','received_monotonic':time.monotonic(),'received_utc':time.time()})
        assert rec.flush(2);assert rec.failed==1 and not (directory/'clip.avi').exists()
        store.flush();assert any(e['code']=='CLIPE_FALHOU' for e in store.events())
    finally:rec.close()


def test_crashed_clip_marker_recovered_on_start(tmp_path,store):
    directory=tmp_path/('e_'+'e'*32);directory.mkdir();(directory/'.clip-pendente').touch()
    w=EvidenceWriter(tmp_path,store)
    try:
        assert not (directory/'.clip-pendente').exists()
        store.flush();assert any(e['code']=='CLIPE_INTERROMPIDO' for e in store.events())
    finally:w.close()
