"""Killable acquisition worker; the capture thread never waits for disk or HTTP.

A local latest-frame reference separates native decode from JPEG encoding and quality
sampling. Both the local reference and the interprocess slot are bounded to one frame.
"""
from __future__ import annotations

import os
import platform
import threading
import time
from collections import deque
from dataclasses import dataclass, field

import cv2
import numpy as np

from .config import CameraConfig
from .ipc import FrameSlot


def fit(frame: np.ndarray, max_width: int, max_height: int) -> np.ndarray:
    scale = min(1.0, max_width / frame.shape[1], max_height / frame.shape[0])
    if scale == 1:
        return np.ascontiguousarray(frame)
    return cv2.resize(frame, (max(1, int(frame.shape[1] * scale)), max(1, int(frame.shape[0] * scale))),
                      interpolation=cv2.INTER_AREA)


def backends_for(config: CameraConfig, generation: int = 0) -> int:
    values = {"dshow": cv2.CAP_DSHOW, "msmf": cv2.CAP_MSMF, "v4l2": cv2.CAP_V4L2,
              "avfoundation": cv2.CAP_AVFOUNDATION, "ffmpeg": cv2.CAP_FFMPEG}
    if config.backend != "auto":
        return values[config.backend]
    if config.kind in ("rtsp", "http", "file"):
        return cv2.CAP_FFMPEG
    choices = {"Windows": [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY],
               "Linux": [cv2.CAP_V4L2, cv2.CAP_ANY],
               "Darwin": [cv2.CAP_AVFOUNDATION, cv2.CAP_ANY]}.get(platform.system(), [cv2.CAP_ANY])
    return choices[generation % len(choices)]


def open_capture(config: CameraConfig, generation: int = 0):
    backend = backends_for(config, generation)
    cap = cv2.VideoCapture()
    if config.kind == "webcam":
        cap.open(int(config.source), backend)
        if cap.isOpened():
            if config.fourcc != "auto":
                cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*config.fourcc))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.height)
            cap.set(cv2.CAP_PROP_FPS, config.fps)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # best effort, never relied upon for correctness
    else:
        options = ["threads;1"]
        if config.kind == "rtsp":
            options.append(f"rtsp_transport;{config.rtsp_transport}")
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "|".join(options)
        args = [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, int(config.open_timeout_s * 1000),
                cv2.CAP_PROP_READ_TIMEOUT_MSEC, int(config.read_timeout_s * 1000)]
        cap.open(config.source, backend, args)
    return cap


def demo_frame(width: int, height: int, sequence: int) -> np.ndarray:
    frame = np.full((height, width, 3), (26, 22, 17), dtype=np.uint8)
    for x in range(0, width, 80):
        cv2.line(frame, (x, 0), (x, height), (42, 37, 29), 1)
    for y in range(0, height, 80):
        cv2.line(frame, (0, y), (width, y), (42, 37, 29), 1)
    x = int((sequence * 5) % max(1, width - 100))
    y = int(height * (0.5 + 0.20 * np.sin(sequence / 35)))
    cv2.rectangle(frame, (x, y - 35), (min(width - 1, x + 90), min(height - 1, y + 35)), (166, 194, 43), -1)
    cv2.putText(frame, "VISION / SOURCE TEST", (24, 45), cv2.FONT_HERSHEY_SIMPLEX,
                min(0.85, width / 900), (230, 237, 238), 2, cv2.LINE_AA)
    cv2.putText(frame, f"FRAME {sequence:07d}", (24, 85), cv2.FONT_HERSHEY_SIMPLEX,
                0.55, (179, 194, 199), 1, cv2.LINE_AA)
    cv2.putText(frame, time.strftime("%Y-%m-%d %H:%M:%S"), (24, height - 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (230, 237, 238), 1, cv2.LINE_AA)
    return frame


@dataclass
class Latest:
    lock: threading.Lock = field(default_factory=threading.Lock)
    frame: np.ndarray | None = None
    sequence: int = 0
    monotonic: float = 0
    utc: float = 0
    read_ms: float = 0
    fps: float = 0
    loops: int = 0
    ended: bool = False
    failed: bool = False
    backend: str = ""


def acquire(config: CameraConfig, slot: FrameSlot, latest: Latest, stop, generation: int):
    cap = None
    recent = deque(maxlen=120)
    deadline = time.monotonic()
    try:
        if config.kind == "demo":
            latest.backend = "SYNTHETIC"
            source_fps = config.fps
        else:
            cap = open_capture(config, generation)
            if not cap.isOpened():
                latest.failed = True
                slot.set_status("OPEN_FAILED", detail="Verifique fonte, credenciais, permissões e backend.")
                return
            latest.backend = cap.getBackendName()
            source_fps = cap.get(cv2.CAP_PROP_FPS)
            if not 0 < source_fps <= 240:
                source_fps = config.fps
        slot.set_status("OPEN", latest.backend)
        failures = 0
        while not stop.is_set():
            before = time.monotonic()
            if config.kind == "demo":
                frame = demo_frame(config.width, config.height, latest.sequence + 1)
                ok = True
            else:
                ok, frame = cap.read()
            now = time.monotonic()
            if not ok or frame is None or frame.size == 0:
                if config.kind == "file":
                    if config.loop and latest.sequence > 0 and failures == 0:
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        latest.loops += 1
                        failures += 1
                        deadline = time.monotonic()
                        continue
                    slot.set_status("EOF" if latest.sequence else "READ_FAILED", latest.backend)
                    latest.failed = not bool(latest.sequence)
                    return
                failures += 1
                if failures >= 5:
                    latest.failed = True
                    slot.set_status("READ_FAILED", latest.backend, "A fonte deixou de fornecer quadros.")
                    return
                stop.wait(0.05)
                continue
            failures = 0
            recent.append(now)
            rate = (len(recent) - 1) / (recent[-1] - recent[0]) if len(recent) > 1 and recent[-1] > recent[0] else 0
            with latest.lock:
                latest.frame = frame
                latest.sequence += 1
                latest.monotonic = now
                latest.utc = time.time()
                latest.read_ms = (now - before) * 1000
                latest.fps = rate
            # File playback follows source time, not CPU speed. Live reads are NOT throttled.
            if config.kind in ("file", "demo"):
                deadline += 1 / source_fps
                if deadline < now - 1:
                    deadline = now
                stop.wait(max(0, deadline - time.monotonic()))
    except Exception:
        latest.failed = True
        slot.set_status("CAPTURE_ERROR", latest.backend, "Falha nativa de captura; detalhes da fonte não foram registrados.")
    finally:
        latest.ended = True
        if cap is not None:
            cap.release()  # a hung native release is contained inside this killable process


def worker(config_data: dict, slot: FrameSlot, stop, generation: int = 0):
    # Native FFmpeg/OpenCV diagnostics may contain passwords. Never send them to console/log.
    # Structured diagnostic codes above replace those messages.
    try:
        fd = os.open(os.devnull, os.O_WRONLY)
        os.dup2(fd, 2)
        os.close(fd)
    except OSError:
        pass
    os.environ["OPENCV_LOG_LEVEL"] = "SILENT"
    os.environ["OPENCV_FFMPEG_THREADS"] = "1"
    cv2.setNumThreads(1)
    cv2.ocl.setUseOpenCL(False)
    config = CameraConfig.model_validate(config_data)
    slot.set_status("OPENING")
    latest = Latest()
    thread = threading.Thread(target=acquire, args=(config, slot, latest, stop, generation), daemon=True)
    thread.start()
    last_sequence = published = sampled_out = 0
    quality_at = 0.0
    brightness = sharpness = unchanged_s = 0.0
    previous_thumb = None
    last_change = time.monotonic()
    pub_times = deque(maxlen=60)
    while not stop.is_set():
        tick = time.monotonic()
        with latest.lock:
            seq, frame = latest.sequence, latest.frame
            received, utc, read_ms, decode_fps, loops = latest.monotonic, latest.utc, latest.read_ms, latest.fps, latest.loops
        if frame is not None and seq != last_sequence:
            h, w = frame.shape[:2]
            if frame.ndim == 2:
                frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
            elif frame.shape[2] == 4:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            raw = fit(frame, config.raw_max_width, config.raw_max_height)
            if tick - quality_at >= 1:
                gray = cv2.cvtColor(fit(raw, 320, 240), cv2.COLOR_BGR2GRAY)
                brightness = float(gray.mean())
                sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
                thumb = cv2.resize(gray, (32, 24))
                if previous_thumb is None or float(cv2.absdiff(thumb, previous_thumb).mean()) > 0.15:
                    last_change = tick
                unchanged_s = tick - last_change
                previous_thumb, quality_at = thumb, tick
            start = time.monotonic()
            if config.jpeg_preview:
                preview = fit(raw, config.preview_width, 2160)
                ok, encoded = cv2.imencode(".jpg", preview, [cv2.IMWRITE_JPEG_QUALITY, config.jpeg_quality])
            else:
                ok, encoded = True, np.empty(0, dtype=np.uint8)
            encode_ms = (time.monotonic() - start) * 1000
            if ok:
                published_at = time.monotonic()
                candidate_times = (*pub_times, published_at)[-60:]
                pub_fps = ((len(candidate_times) - 1) / (candidate_times[-1] - candidate_times[0])
                           if len(candidate_times) > 1 else 0)
                skipped = max(0, seq - last_sequence - 1)
                meta = dict(sequence=seq, source_width=w, source_height=h,
                            received_monotonic=received, received_utc=utc,
                            published_monotonic=time.monotonic(), decoded_total=seq,
                            published_total=published + 1, decoded_fps=decode_fps,
                            published_fps=pub_fps, encode_ms=encode_ms, brightness=brightness,
                            sharpness=sharpness, unchanged_scene_s=unchanged_s, read_ms=read_ms,
                            sampled_out_total=sampled_out + skipped, loops=loops,
                            raw_scaled=int(raw.shape[:2] != (h, w)))
                if slot.publish(raw, encoded.tobytes(), meta):
                    pub_times.append(published_at)
                    published += 1
                    sampled_out += skipped
                    last_sequence = seq
                    if not latest.ended:
                        slot.set_status("RUNNING", latest.backend)
        if latest.ended and seq == last_sequence:
            break
        stop.wait(max(0.001, 1 / config.publish_fps - (time.monotonic() - tick)))
    # Never join an unresponsive capture thread indefinitely.
    stop.set()
    thread.join(timeout=0.3)
