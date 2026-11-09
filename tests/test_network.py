import contextlib
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

import cv2
import numpy as np

from vision_foundation.config import CameraConfig
from vision_foundation.supervisor import CameraSession
from .conftest import wait_for


class MjpegFixture:
    def __init__(self):
        self.live=threading.Event();self.live.set()
        self.closed=threading.Event()
        self.connections=0
        fixture=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                if not fixture.live.is_set():
                    self.send_error(503);return
                fixture.connections+=1
                self.send_response(200)
                self.send_header('Content-Type','multipart/x-mixed-replace; boundary=frame')
                self.end_headers()
                seq=0
                try:
                    while fixture.live.is_set() and not fixture.closed.is_set():
                        frame=np.full((240,320,3),seq%220,np.uint8)
                        cv2.putText(frame,str(seq),(40,100),cv2.FONT_HERSHEY_SIMPLEX,1,(255,255,255),2)
                        ok,jpg=cv2.imencode('.jpg',frame)
                        data=jpg.tobytes()
                        self.wfile.write(b'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: '+str(len(data)).encode()+b'\r\n\r\n'+data+b'\r\n')
                        self.wfile.flush();seq+=1;time.sleep(1/20)
                except (BrokenPipeError,ConnectionResetError,OSError):pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.server.daemon_threads=True
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
    @property
    def url(self):return f'http://127.0.0.1:{self.server.server_port}/stream'
    def close(self):
        self.closed.set();self.server.shutdown();self.server.server_close();self.thread.join(2)


def test_real_http_mjpeg_disconnect_reconnect(store):
    source=MjpegFixture()
    session=CameraSession(CameraConfig(kind='http',source=source.url,open_timeout_s=6,read_timeout_s=3,
                                      stale_after_s=1,raw_max_width=320,raw_max_height=240),store)
    try:
        session.start();wait_for(lambda:session.snapshot()['fresh'],timeout=20)
        assert session.backend=='FFMPEG'
        first=session.generation
        source.live.clear()
        wait_for(lambda:session.restarts>=1,timeout=15)
        source.live.set()
        wait_for(lambda:session.generation>first and session.snapshot()['fresh'],timeout=20)
        assert source.connections>=2
        assert session.latest(raw=True).bgr.shape==(240,320,3)
    finally:
        session.stop();source.close()


def test_unreachable_rtsp_bounded_and_other_camera_unaffected(store):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    bad=CameraSession(CameraConfig(id='bad',kind='rtsp',source=f'rtsp://user:secret@127.0.0.1:{port}/live',
                                  open_timeout_s=3,read_timeout_s=3,stale_after_s=1),store)
    good=CameraSession(CameraConfig(id='good',kind='demo',source='demo',width=320,height=240,
                                   raw_max_width=320,raw_max_height=240),store)
    try:
        bad.start();good.start()
        wait_for(lambda:good.snapshot()['fresh'])
        wait_for(lambda:bad.restarts>=1,timeout=10)
        assert good.snapshot()['fresh']
        begin=time.monotonic()
        for _ in range(100):good.snapshot();bad.snapshot()
        assert time.monotonic()-begin<1
        store.flush()
        assert 'secret' not in str(store.events())
    finally:
        begin=time.monotonic();bad.stop();good.stop()
        assert time.monotonic()-begin<5
