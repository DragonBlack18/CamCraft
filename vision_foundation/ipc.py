"""Single-slot shared memory: no unbounded frame queues and no pickled images.

The parent ALWAYS replaces the complete slot (including locks) after a worker dies.
A process killed while holding a lock can therefore never poison the next session.
All lock acquisitions have deadlines, including the HTTP preview read path.
"""
from __future__ import annotations

import ctypes
import json
from dataclasses import dataclass

import numpy as np

FIELDS = ("sequence", "width", "height", "source_width", "source_height",
          "received_monotonic", "received_utc", "published_monotonic", "jpeg_size",
          "decoded_total", "published_total", "decoded_fps", "published_fps",
          "encode_ms", "brightness", "sharpness", "unchanged_scene_s", "read_ms",
          "sampled_out_total", "loops", "raw_scaled")
INDEX = {s: i for i, s in enumerate(FIELDS)}


@dataclass(frozen=True)
class FramePacket:
    """Phase-2 contract. One coherent copy, timestamped AFTER decode, not at exposure."""
    metadata: dict
    bgr: np.ndarray | None = None
    jpeg: bytes | None = None


class FrameSlot:
    def __init__(self, ctx, max_width: int, max_height: int):
        self.capacity = max_width * max_height * 3
        self.raw = ctx.RawArray(ctypes.c_ubyte, self.capacity)
        self.jpeg_capacity = 4 * 1024 * 1024
        self.jpeg = ctx.RawArray(ctypes.c_ubyte, self.jpeg_capacity)
        self.meta = ctx.RawArray(ctypes.c_double, len(FIELDS))
        self.lock = ctx.Lock()
        self.status_data = ctx.RawArray(ctypes.c_ubyte, 2048)
        self.status_size = ctx.RawValue(ctypes.c_int, 0)
        self.status_lock = ctx.Lock()

    @property
    def allocated_bytes(self) -> int:
        return self.capacity + self.jpeg_capacity + 2048 + len(FIELDS) * 8

    def set_status(self, code: str, backend: str = "", detail: str = ""):
        # Caller only uses fixed diagnostic strings, never camera URLs/exceptions.
        data = json.dumps({"code": code, "backend": backend, "detail": detail}).encode()[:2000]
        if not self.status_lock.acquire(timeout=0.02):
            return
        try:
            np.frombuffer(self.status_data, np.uint8)[:len(data)] = np.frombuffer(data, np.uint8)
            self.status_size.value = len(data)
        finally:
            self.status_lock.release()

    def get_status(self) -> dict:
        if not self.status_lock.acquire(timeout=0.003):
            return {}
        try:
            if not self.status_size.value:
                return {}
            return json.loads(bytes(self.status_data[:self.status_size.value]))
        finally:
            self.status_lock.release()

    def publish(self, frame: np.ndarray, jpeg: bytes, meta: dict) -> bool:
        if frame.nbytes > self.capacity or len(jpeg) > self.jpeg_capacity:
            return False
        if not self.lock.acquire(timeout=0.005):
            return False
        try:
            np.frombuffer(self.raw, np.uint8, frame.size)[:] = frame.reshape(-1)
            np.frombuffer(self.jpeg, np.uint8, len(jpeg))[:] = np.frombuffer(jpeg, np.uint8)
            meta = {**meta, "width": frame.shape[1], "height": frame.shape[0], "jpeg_size": len(jpeg)}
            for key, value in meta.items():
                if key in INDEX:
                    self.meta[INDEX[key]] = value
            return True
        finally:
            self.lock.release()

    def read(self, *, raw: bool = False, jpeg: bool = False) -> FramePacket | None:
        if not self.lock.acquire(timeout=0.01):
            return None
        try:
            meta = dict(zip(FIELDS, self.meta))
            if not meta["sequence"]:
                return None
            frame = None
            jpg = None
            if raw:
                w, h = int(meta["width"]), int(meta["height"])
                frame = np.frombuffer(self.raw, np.uint8, w * h * 3).reshape(h, w, 3).copy()
            if jpeg:
                jpg = np.frombuffer(self.jpeg, np.uint8, int(meta["jpeg_size"])).tobytes()
            return FramePacket(meta, frame, jpg)
        finally:
            self.lock.release()


class StopFlag:
    """Lock-free cooperative stop signal for a worker that may be forcibly killed.

    multiprocessing.Event uses a process-shared condition lock. A terminated worker
    can leave such a lock held. A one-byte flag avoids making parent shutdown depend
    on a lock owned by the failed child. The supported target is ordinary x64 CPython.
    """
    def __init__(self, ctx):
        self.value = ctx.RawValue(ctypes.c_ubyte, 0)

    def set(self):
        self.value.value = 1

    def is_set(self):
        return bool(self.value.value)

    def wait(self, timeout: float):
        import time
        deadline = time.monotonic() + max(0, timeout)
        while not self.is_set():
            left = deadline - time.monotonic()
            if left <= 0:
                return False
            time.sleep(min(0.02, left))
        return True
