import multiprocessing as mp
import time
import cv2
import numpy as np
import pytest
from vision_foundation.capture import fit,backends_for
from vision_foundation.config import CameraConfig
from vision_foundation.supervisor import CameraSession
from .conftest import wait_for
from .fault_workers import hang_then_recover,poison_then_recover,crash_then_recover


def demo_config(**kwargs):
    return CameraConfig(kind='demo',source='demo',width=640,height=360,raw_max_width=640,
        raw_max_height=360,fps=30,publish_fps=10,open_timeout_s=3,**kwargs)


def test_fit_aspect_no_upscale():
    f=np.zeros((720,1280,3),np.uint8)
    assert fit(f,640,480).shape==(360,640,3)
    assert fit(f,1920,1080).shape==f.shape


def test_windows_backend_fallback(monkeypatch):
    monkeypatch.setattr('vision_foundation.capture.platform.system',lambda:'Windows')
    c=CameraConfig()
    assert [backends_for(c,i) for i in range(3)]==[cv2.CAP_DSHOW,cv2.CAP_MSMF,cv2.CAP_ANY]


def test_live_demo_slow_consumer_and_clean_stop(store):
    session=CameraSession(demo_config(),store)
    try:
        session.start()
        a=wait_for(lambda:session.latest(raw=True,jpeg=True))
        first=a.metadata['sequence']
        time.sleep(1.2)
        b=session.latest(raw=True,jpeg=True)
        assert b.metadata['sequence']-first>20
        assert time.monotonic()-b.metadata['received_monotonic']<.5
        assert b.metadata['sampled_out_total']>0
        assert cv2.imdecode(np.frombuffer(b.jpeg,np.uint8),cv2.IMREAD_COLOR) is not None
        assert session.snapshot()['fresh']
        assert b.bgr.shape==(360,640,3)
    finally:session.stop()
    assert session.process is None and session.snapshot()['state']=='STOPPED'
    assert session.latest(raw=True) is None


@pytest.mark.parametrize('worker',[hang_then_recover,poison_then_recover,crash_then_recover])
def test_watchdog_and_recovery(store,worker):
    session=CameraSession(demo_config(),store,worker_target=worker)
    try:
        session.start()
        wait_for(lambda:session.snapshot()['fresh'] and session.generation>=2,timeout=15)
        assert session.restarts>=1
        assert session.latest(jpeg=True).jpeg
        if worker!=crash_then_recover:assert session.forced_terminations>=1
    finally:session.stop()


def test_external_kill_recovery(store):
    session=CameraSession(demo_config(),store)
    try:
        session.start();wait_for(lambda:session.snapshot()['fresh'])
        old=session.process.pid
        session.process.terminate()
        wait_for(lambda:session.generation>=2 and session.snapshot()['fresh'],timeout=12)
        assert session.process.pid!=old
    finally:session.stop()


def test_repeated_start_stop(store):
    # This test checks idempotency, not startup deadlines. Allow slow CI spawn.
    session=CameraSession(demo_config().model_copy(update={'open_timeout_s': 8}),store)
    for _ in range(3):
        session.start();session.start()
        wait_for(lambda:session.snapshot()['fresh'])
        session.stop();session.stop()
        assert session.process is None
    assert session.generation==3


def write_video(path,seconds=2):
    writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'MJPG'),15,(320,240))
    assert writer.isOpened()
    for i in range(int(seconds*15)):
        frame=np.full((240,320,3),i%240,np.uint8)
        cv2.putText(frame,str(i),(50,100),cv2.FONT_HERSHEY_SIMPLEX,1,(255,255,255),2)
        writer.write(frame)
    writer.release()


def test_real_video_file_realtime_eof(store,tmp_path):
    path=tmp_path/'input.avi';write_video(path)
    config=CameraConfig(kind='file',source=str(path),loop=False,raw_max_width=320,raw_max_height=240)
    session=CameraSession(config,store)
    try:
        start=time.monotonic();session.start()
        wait_for(lambda:session.snapshot()['fresh'])
        wait_for(lambda:session.snapshot()['state']=='EOF',timeout=12)
        assert time.monotonic()-start>=1.5
        assert session.restarts==0
        assert session.snapshot()['total_decoded']>=20
    finally:session.stop()


def test_real_video_file_loops(store,tmp_path):
    path=tmp_path/'loop.avi';write_video(path,1)
    session=CameraSession(CameraConfig(kind='file',source=str(path),loop=True,raw_max_width=320,raw_max_height=240),store)
    try:
        session.start();wait_for(lambda:session.snapshot().get('loops',0)>=2,timeout=10)
        assert session.snapshot()['fresh']
    finally:session.stop()
