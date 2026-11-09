import time
from types import SimpleNamespace
import numpy as np
import pytest
from vision_app.preview import LivePreview,PreviewConfig
from vision_app.settings import AnalysisConfig
from vision_app.service import AnalysisService
from vision_app.evidence import EvidenceWriter
from vision_app.controller import Controller
from vision_foundation.config import CameraConfig
from vision_foundation.supervisor import CameraSession
from vision_foundation.ipc import FramePacket
from tests.conftest import wait_for
from tests.detection_workers import slow_worker


def camera_config():
    return CameraConfig(id='fast',kind='demo',source='demo',width=640,height=480,
        fps=30,publish_fps=30,raw_max_width=640,raw_max_height=480,jpeg_preview=False)


def test_live_preview_independent_of_slow_inference(tmp_path,store):
    cam=CameraSession(camera_config(),store);ev=EvidenceWriter(tmp_path/'e',store)
    ai=AnalysisService(cam,store,ev,AnalysisConfig(engine='regions',adaptive_pacing=False),tmp_path,worker_target=slow_worker)
    preview=LivePreview(cam,PreviewConfig())
    try:
        cam.start();ai.start();preview.start()
        wait_for(lambda:ai.processed>=3,timeout=15)
        start_p=preview.frames;start_i=ai.processed;time.sleep(2)
        painted=preview.frames-start_p;analysed=ai.processed-start_i
        assert painted>=20 and painted>analysed*4
        assert preview.latest() and preview.snapshot()['errors']==0
        ai.process.kill()
        before=preview.frames
        wait_for(lambda:preview.frames>=before+10,timeout=3)
        assert preview.latest()  # still running while inference is restarting
    finally:preview.stop();ai.stop();cam.stop();ev.close()


def test_stale_video_is_not_presented_as_live():
    meta={'camera_id':'x','generation':1,'loops':0,'width':320,'height':240,'sequence':1,
          'received_monotonic':time.monotonic()}
    packet=FramePacket(meta,np.zeros((240,320,3),np.uint8))
    cam=SimpleNamespace(latest=lambda **kw:packet)
    p=LivePreview(cam,PreviewConfig(max_age=.2))
    try:
        p.start();assert wait_for(p.latest,timeout=1)
        time.sleep(.3);assert p.latest() is None
    finally:p.stop()


def test_resize_copy_and_single_slot_bound():
    frame=np.full((480,640,3),7,np.uint8)
    meta={'camera_id':'x','generation':1,'loops':0,'width':640,'height':480,'sequence':1,
          'received_monotonic':time.monotonic()}
    cam=SimpleNamespace(latest=lambda **kw:FramePacket(meta,frame))
    p=LivePreview(cam,PreviewConfig(max_width=320))
    try:
        p.resize(1600,900);p.start();first=wait_for(p.latest)
        assert first.image.size==(320,240)
        assert frame[0,0,0]==7
        before=p.frames;time.sleep(.1);assert p.frames==before
        p.resize(160,120);wait_for(lambda:p.latest() and p.latest().image.size==(160,120))
        assert p.snapshot()['queue_capacity']==1
    finally:p.stop()


def test_pause_and_settings_preserve_capture_pid(tmp_path):
    app=Controller(tmp_path/'data',tmp_path/'models');app.configs.put(camera_config())
    app.settings.put('fast',AnalysisConfig(engine='regions'))
    try:
        app.start('fast');wait_for(lambda:app.analysis.processed>=2)
        pid=app.camera.snapshot()['worker_pid'];generation=app.camera.generation
        app.pause_analysis();assert app.analysis is None
        before=app.preview.frames;wait_for(lambda:app.preview.frames>before+3)
        app.resume_analysis();wait_for(lambda:app.analysis.processed>=1)
        cfg=app.settings.get('fast').model_copy(update={'classes':'people'})
        app.configure_analysis('fast',cfg,app.display.config)
        wait_for(lambda:app.analysis.processed>=1)
        assert app.camera.snapshot()['worker_pid']==pid and app.camera.generation==generation
    finally:app.close()
    assert app.preview is None and app.camera is None


def test_model_missing_does_not_interrupt_camera_only_mode(tmp_path):
    app=Controller(tmp_path/'data',tmp_path/'models');app.configs.put(camera_config())
    try:
        app.start('fast',analyze=False);assert wait_for(lambda:app.preview.latest())
        pid=app.camera.snapshot()['worker_pid']
        with pytest.raises(ValueError):app.resume_analysis()
        assert app.camera.snapshot()['worker_pid']==pid and app.preview.latest()
        assert app.photo() # unanalysed capture is explicitly tagged
        assert app.evidence.flush()
    finally:app.close()
