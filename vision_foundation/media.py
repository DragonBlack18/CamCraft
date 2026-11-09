from __future__ import annotations

import hashlib
import json
import shutil
import threading
import time
import uuid
from pathlib import Path

import cv2


class MediaStore:
    """Manual evidence only. Bounded retention: 2 GiB / 2,000 image or clip files."""
    def __init__(self, directory: Path, events):
        self.directory, self.events = directory, events
        directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.active: dict[str, dict] = {}
        self.cancel = threading.Event()
        self.threads: list[threading.Thread] = []
        self.max_bytes = 2 * 1024**3
        self.max_files = 2000
        # Only uncommitted clips owned by this application are disposable.
        # run.py holds the per-directory instance lock before constructing this store.
        removed = 0
        for pending in directory.glob("*_clip_*.part.avi"):
            try:
                pending.unlink()
                removed += 1
            except OSError:
                self.events.emit(None, "MEDIA_TEMP_BUSY", "Clipe temporário não pôde ser removido.", "WARN")
        if removed:
            self.events.emit(None, "MEDIA_RECOVERY", "Clipes temporários incompletos removidos após interrupção.",
                             "WARN", {"count": removed})

    def _space(self):
        if shutil.disk_usage(self.directory).free < 256 * 1024**2:
            raise ValueError("Menos de 256 MiB livres: gravação recusada para proteger o sistema.")

    def _retention(self):
        files = sorted((p for p in self.directory.iterdir() if p.suffix in (".jpg", ".avi") and ".part." not in p.name), key=lambda p: p.stat().st_mtime)
        size = sum(p.stat().st_size for p in files)
        removed = 0
        while files and (len(files) > self.max_files or size > self.max_bytes):
            item = files.pop(0)
            size -= item.stat().st_size
            item.unlink(missing_ok=True)
            item.with_suffix(".json").unlink(missing_ok=True)
            removed += 1
        if removed:
            self.events.emit(None, "MEDIA_RETENTION", "Evidências antigas removidas pelo limite de armazenamento.", "WARN", {"count": removed})

    def snapshot(self, session):
        packet = session.latest(raw=True)
        if packet is None:
            raise ValueError("Não existe quadro atual disponível para salvar.")
        with self.lock:
            self._space()
            ok, encoded = cv2.imencode(".jpg", packet.bgr, [cv2.IMWRITE_JPEG_QUALITY, 95])
            if not ok:
                raise ValueError("Não foi possível codificar a imagem.")
            name = f"{session.config.id}_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
            content = encoded.tobytes()
            path = self.directory / (name + ".jpg")
            path.write_bytes(content)
            meta = {**packet.metadata, "filename": path.name, "sha256": hashlib.sha256(content).hexdigest(),
                    "timestamp_meaning": "UTC imediatamente após decodificação; não é a exposição do sensor."}
            path.with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            self._retention()
        self.events.emit(session.config.id, "SNAPSHOT_SAVED", "Imagem e metadados salvos.", payload={"filename": path.name})
        return {"filename": path.name, "metadata": meta}

    def record(self, session, seconds: int = 10):
        with self.lock:
            if session.config.id in self.active:
                raise ValueError("Já existe um clipe em gravação para esta fonte.")
            if session.latest(raw=True) is None:
                raise ValueError("Inicie uma fonte e aguarde o primeiro quadro.")
            self._space()
            job = {"id": uuid.uuid4().hex[:12], "camera_id": session.config.id, "state": "RECORDING",
                   "seconds": seconds, "started_utc": time.time(), "frames": 0}
            self.active[session.config.id] = job
            thread = threading.Thread(target=self._record, args=(session, job), daemon=True)
            self.threads = [t for t in self.threads if t.is_alive()]
            self.threads.append(thread)
            thread.start()
            return dict(job)

    def _record(self, session, job):
        writer = None
        name = f"{session.config.id}_clip_{job['id']}"
        tmp = self.directory / (name + ".part.avi")
        final = self.directory / (name + ".avi")
        timestamps = []
        fps = min(10, session.config.publish_fps)
        last_uid = None
        generation = None
        reason = "completed"
        start = time.monotonic()
        try:
            while not self.cancel.is_set() and time.monotonic() - start < job["seconds"]:
                tick = time.monotonic()
                packet = session.latest(raw=True)
                if packet is None:
                    reason = "source_unavailable"
                    break
                uid = (packet.metadata["generation"], packet.metadata["sequence"])
                if generation is not None and generation != uid[0]:
                    reason = "source_reconnected"
                    break
                generation = uid[0]
                if uid != last_uid:
                    frame = packet.bgr
                    if writer is None:
                        size = (frame.shape[1], frame.shape[0])
                        writer = cv2.VideoWriter(str(tmp), cv2.VideoWriter_fourcc(*"MJPG"), fps, size)
                        if not writer.isOpened():
                            raise ValueError("Codec MJPG não disponível.")
                    elif frame.shape[1::-1] != size:
                        reason = "resolution_changed"
                        break
                    writer.write(frame)
                    timestamps.append({"frame": len(timestamps), "received_utc": packet.metadata["received_utc"],
                                       "sequence": uid[1], "generation": generation})
                    last_uid = uid
                    job["frames"] = len(timestamps)
                if len(timestamps) % 10 == 0:
                    self._space()
                self.cancel.wait(max(0, 1 / fps - (time.monotonic() - tick)))
            if self.cancel.is_set():
                reason = "application_stopped"
            if writer is not None:
                writer.release()
                writer = None
            if not timestamps:
                raise ValueError("Clipe sem quadros.")
            with self.lock:
                tmp.replace(final)
                # Fixed-rate diagnostic clip, not a forensic/VFR recording. Sidecar preserves real times.
                meta = {"filename": final.name, "camera_id": session.config.id, "frames": len(timestamps),
                        "encoded_fps": fps, "duration_wall_s": time.monotonic() - start, "reason": reason,
                        "timestamps": timestamps, "playback_note": "CFR; gaps can shorten playback. Consult real timestamps.",
                        "sha256": self._hash_file(final)}
                final.with_suffix(".json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
                self._retention()
            job.update(state="DONE", filename=final.name)
            self.events.emit(session.config.id, "CLIP_SAVED", "Clipe de diagnóstico salvo, sem áudio.",
                             payload={"filename": final.name, "frames": len(timestamps), "reason": reason})
        except Exception:
            job["state"] = "ERROR"
            self.events.emit(session.config.id, "CLIP_FAILED", "Falha ao salvar clipe; verifique espaço e codec.", "ERROR")
            # Windows cannot unlink a file while VideoWriter still holds its handle.
            if writer is not None:
                writer.release()
                writer = None
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass  # Startup cleanup can retry; never block the capture pipeline.
        finally:
            if writer is not None:
                writer.release()
            with self.lock:
                self.active.pop(session.config.id, None)

    @staticmethod
    def _hash_file(path):
        with path.open("rb") as file:
            return hashlib.file_digest(file, "sha256").hexdigest()

    def list(self):
        with self.lock:
            paths = sorted((p for p in self.directory.iterdir() if p.suffix in (".jpg", ".avi") and ".part." not in p.name),
                           key=lambda p: p.stat().st_mtime, reverse=True)[:200]
            return [{"filename": p.name, "size": p.stat().st_size, "utc": p.stat().st_mtime,
                     "type": "image" if p.suffix == ".jpg" else "clip"} for p in paths]

    def close(self):
        self.cancel.set()
        for thread in self.threads:
            thread.join(timeout=3)
