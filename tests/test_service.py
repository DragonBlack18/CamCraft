import multiprocessing as mp
import time
from types import SimpleNamespace
import numpy as np
import pytest
from vision_app.settings import AnalysisConfig
from vision_app.service import AnalysisService
from vision_app.inference import JsonSlot
from vision_app.evidence import EvidenceWriter
from vision_foundation.config import CameraConfig
from vision_foundation.ipc import FramePacket
from vision_foundation.supervisor import CameraSession
from tests.conftest import wait_for
from tests.detection_workers import controlled_worker,lock_crash_worker

def demo_config():
    return CameraConfig(id='test',kind='demo',source='demo',width=320,height=240,raw_max_width=320,raw_max_height=240,jpeg_preview=False)

def test_json_slot_bounded_and_lock_timeout():
    ctx=mp.get_context('spawn');s=JsonSlot(ctx,128)
    assert s.get() is None and s.put({'ok':True}) and s.get()=={'ok':True}
    with pytest.raises(ValueError):s.put({'big':'x'*200})
    s.lock.acquire()
    t=time.monotonic();assert s.get() is None and time.monotonic()-t<.1
    s.lock.release()

def test_synchronized_frame_and_expired_result_rejected(tmp_path,store):
    meta={'generation':1,'loops':0,'width':320,'height':240,'sequence':2,'received_monotonic':time.monotonic(),'received_utc':time.time()}
    frame=np.full((240,320,3),77,np.uint8)
    packet=FramePacket(meta,frame)
    camera=SimpleNamespace(config=demo_config(),latest=lambda **kw:packet)
    evidence=EvidenceWriter(tmp_path/'e',store)
    service=AnalysisService(camera,store,evidence,AnalysisConfig(engine='hog'),tmp_path)
    try:
        service._accept({'packet':packet},{'detections':[],'inference_ms':10,'backend':'test'})
        result=service.latest()
        assert result.metadata['sequence']==2 and np.array_equal(result.original,frame)
        assert np.array_equal(result.frame,frame)
        service._accept({'packet':FramePacket({**meta,'received_monotonic':time.monotonic()-5},frame)},
                        {'detections':[],'inference_ms':10,'backend':'test'})
        assert service.stale_dropped==1 and service.processed==1
    finally:evidence.close()

def test_generation_change_discards_inflight_result(tmp_path,store):
    meta={'generation':1,'loops':0,'width':320,'height':240,'sequence':2,'received_monotonic':time.monotonic(),'received_utc':time.time()}
    packet=FramePacket(meta,np.zeros((240,320,3),np.uint8))
    camera=SimpleNamespace(config=demo_config(),latest=lambda **kw:FramePacket({**meta,'generation':2}))
    ev=EvidenceWriter(tmp_path/'e',store)
    try:
        s=AnalysisService(camera,store,ev,AnalysisConfig(engine='hog'),tmp_path)
        s._accept({'packet':packet},{'detections':[],'inference_ms':10})
        assert s.processed==0 and s.stale_dropped==1
    finally:ev.close()

def test_integrated_capture_tracking_records_and_worker_recovery(tmp_path,store):
    camera=CameraSession(demo_config(),store);ev=EvidenceWriter(tmp_path/'e',store)
    cfg=AnalysisConfig(engine='hog',min_hits=2,confirm_seconds=.1,max_fps=10)
    s=AnalysisService(camera,store,ev,cfg,tmp_path,worker_target=controlled_worker)
    try:
        camera.start();s.start()
        wait_for(lambda:s.processed>=5,timeout=10)
        assert s.latest() and s.latest().tracks[0]['confirmed']
        assert s.latest().metadata['sequence']>0
        store.flush();assert any(e['code']=='PESSOA_OBSERVADA' for e in store.events())
        assert ev.flush() and ev.saved>=1
        before=s.engine.session;count=s.processed
        s.process.kill()
        wait_for(lambda:s.restarts>=1 and s.processed>=count+4,timeout=12)
        assert s.engine.session!=before and s.snapshot()['state']=='RUNNING'
    finally:s.stop();camera.stop();ev.close()
    assert not s.thread.is_alive()

def test_hog_actual_inference_process_smoke(tmp_path,store):
    camera=CameraSession(demo_config(),store);ev=EvidenceWriter(tmp_path/'e',store)
    s=AnalysisService(camera,store,ev,AnalysisConfig(engine='hog',classes='people'),tmp_path)
    try:
        camera.start();s.start();wait_for(lambda:s.processed>=3,timeout=10)
        assert 'HOG' in s.backend and s.errors==0
    finally:s.stop();camera.stop();ev.close()

def test_model_loading_watchdog_replaces_poisoned_locks(tmp_path,store):
    camera=CameraSession(demo_config(),store);ev=EvidenceWriter(tmp_path/'e',store)
    s=AnalysisService(camera,store,ev,AnalysisConfig(engine='hog'),tmp_path,
                      worker_target=lock_crash_worker,startup_timeout=.8)
    try:
        camera.start();s.start();wait_for(lambda:s.restarts>=1,timeout=6)
        assert s.errors>=1
        start=time.monotonic();s.stop();assert time.monotonic()-start<3
    finally:s.stop();camera.stop();ev.close()

def test_raw_only_capture_does_not_encode_unused_preview(tmp_path,store):
    camera=CameraSession(demo_config(),store)
    try:
        camera.start();packet=wait_for(lambda:camera.latest(raw=True,jpeg=True))
        assert packet.bgr.shape==(240,320,3) and packet.jpeg==b'' and packet.metadata['jpeg_size']==0
    finally:camera.stop()
