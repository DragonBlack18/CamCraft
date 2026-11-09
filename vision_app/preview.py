"""Bounded, independent live preview. No neural inference, disk IO or Tk calls.

One immutable RGB/PIL frame replaces the last. A slow GUI drops intermediate
frames. Camera timestamps, generation and freshness are never synthesized.
"""
from __future__ import annotations
import json
import os
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
import cv2
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field


class PreviewConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    fps: int = Field(default=30, ge=5, le=60)
    max_width: int = Field(default=1280, ge=320, le=1920)
    max_age: float = Field(default=.75, ge=.2, le=2.)
    show_inset: bool = True
    mode: str = Field(default='live', pattern=r'^(live|analysis)$')


class PreviewSettings:
    def __init__(self, directory: Path):
        self.path = directory / 'display.json'
        self.config = PreviewConfig()
        if self.path.exists():
            self.config = PreviewConfig.model_validate_json(self.path.read_text(encoding='utf-8'))

    def put(self, config: PreviewConfig):
        config = PreviewConfig.model_validate(config.model_dump())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix('.tmp')
        with tmp.open('w', encoding='utf-8') as f:
            json.dump(config.model_dump(), f, ensure_ascii=False, indent=2)
            f.flush(); os.fsync(f.fileno())
        os.replace(tmp, self.path)
        self.config = config


@dataclass(frozen=True)
class PreviewFrame:
    key: tuple
    image: Image.Image
    metadata: dict
    prepared_monotonic: float


def context(meta):
    return (meta.get('camera_id'), meta.get('generation'), meta.get('loops'),
            meta.get('width'), meta.get('height'))


def compatible(result, live_meta, now, max_age):
    """An inset must never cross cameras, reconnects, file loops or resolutions."""
    return bool(result is not None and live_meta is not None
        and context(result.metadata) == context(live_meta)
        and 0 <= now-result.metadata['received_monotonic'] <= max_age)


class LivePreview:
    def __init__(self, camera, config: PreviewConfig):
        self.camera = camera
        self.config = config.model_copy(deep=True)
        self.lock = threading.Lock()
        self.cancel = threading.Event()
        self.thread = None
        self.viewport = (960, 540)
        self.frame = None
        self.times = deque(maxlen=180)
        self.build_ms = deque(maxlen=180)
        self.frames = 0
        self.errors = 0

    def configure(self, config: PreviewConfig):
        with self.lock:
            self.config = config.model_copy(deep=True)
            self.frame = None

    def resize(self, width, height):
        # Bounded even when a window manager briefly reports impossible dimensions.
        with self.lock:
            self.viewport = (min(3840, max(1, int(width))), min(2160, max(1, int(height))))

    def start(self):
        if self.thread and self.thread.is_alive(): return
        self.cancel.clear()
        self.thread = threading.Thread(target=self._run, name='live-preview', daemon=True)
        self.thread.start()

    def stop(self):
        self.cancel.set()
        if self.thread and self.thread is not threading.current_thread(): self.thread.join(2)
        if self.thread and self.thread.is_alive():
            raise RuntimeError('Prévia não encerrou no prazo; não abra outra sessão.')
        with self.lock: self.frame = None

    def _run(self):
        last_key = None
        while not self.cancel.is_set():
            began = time.monotonic()
            with self.lock:
                cfg, viewport = self.config, self.viewport
            try:
                meta_packet = self.camera.latest()
                meta = meta_packet.metadata if meta_packet else None
                key = (*context(meta), meta.get('sequence'), viewport, cfg.max_width) if meta else None
                if meta is None or began-meta['received_monotonic'] > cfg.max_age:
                    with self.lock: self.frame = None
                    last_key = None
                elif key != last_key:
                    packet = self.camera.latest(raw=True)
                    if packet is not None and packet.bgr is not None:
                        h,w = packet.bgr.shape[:2]
                        scale = min(viewport[0]/w, viewport[1]/h, cfg.max_width/w, 1.)
                        rw,rh = max(1,int(w*scale)),max(1,int(h*scale))
                        bgr = packet.bgr
                        if (rw,rh)!=(w,h):
                            bgr = cv2.resize(bgr,(rw,rh),interpolation=cv2.INTER_AREA)
                        image = Image.fromarray(cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB))
                        ready = time.monotonic()
                        actual_key = (*context(packet.metadata), packet.metadata['sequence'], viewport, cfg.max_width)
                        result = PreviewFrame(actual_key, image, packet.metadata, ready)
                        if ready-packet.metadata['received_monotonic'] <= cfg.max_age:
                            with self.lock:
                                self.frame = result
                                self.times.append(ready); self.build_ms.append((ready-began)*1000)
                                self.frames += 1
                            last_key = actual_key
                # No unbounded queue and no copy when the source has not advanced.
            except Exception:
                with self.lock:
                    self.errors += 1
                    self.frame = None
                last_key = None
            self.cancel.wait(max(.001, 1/cfg.fps - (time.monotonic()-began)))

    def latest(self):
        with self.lock:
            frame, cfg = self.frame, self.config
        if frame is None or time.monotonic()-frame.metadata['received_monotonic'] > cfg.max_age:
            return None
        return frame

    def snapshot(self):
        with self.lock:
            times = list(self.times); costs = sorted(self.build_ms); frame = self.frame
            return {'frames': self.frames, 'errors': self.errors, 'queue_capacity': 1,
                'prepared_fps': ((len(times)-1)/(times[-1]-times[0])) if len(times)>1 else 0.,
                'build_ms_p95': costs[int(.95*(len(costs)-1))] if costs else None,
                'age_ms': (time.monotonic()-frame.metadata['received_monotonic'])*1000 if frame else None,
                'thread_alive': bool(self.thread and self.thread.is_alive()),
                'note': 'Prepared preview FPS, not sensor FPS or painted screen FPS.'}
