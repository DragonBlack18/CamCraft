from __future__ import annotations

import multiprocessing as mp
import random
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor

from .capture import worker
from .config import CameraConfig, ConfigStore
from .ipc import FramePacket, FrameSlot, StopFlag
from .storage import EventStore


class CameraSession:
    def __init__(self, config: CameraConfig, store: EventStore, *, worker_target=worker):
        self.config, self.store = config, store
        self.ctx = mp.get_context("spawn")
        self.worker_target = worker_target
        self.lock = threading.RLock()
        self.operation_lock = threading.RLock()
        self.cancel = threading.Event()
        self.thread: threading.Thread | None = None
        self.process = None
        self.worker_stop = None
        self.slot: FrameSlot | None = None
        self.state = "STOPPED"
        self.reason = "Pronto para iniciar."
        self.backend = ""
        self.generation = 0
        self.stable_webcam_backend = None
        self.restarts = 0
        self.forced_terminations = 0
        self.total_decoded_base = 0
        self.total_published_base = 0
        self.total_sampled_base = 0
        self.meta: dict = {}
        self.history = deque(maxlen=3600)
        self.next_retry_utc = None
        self.started_monotonic = None

    def _state(self, state, reason):
        with self.lock:
            changed = self.state != state
            self.state, self.reason = state, reason
        if changed:
            level = "WARN" if state in ("RECONNECTING", "STALE", "ERROR") else "INFO"
            self.store.emit(self.config.id, state, reason, level)

    def start(self):
        with self.operation_lock:
            if self.thread and self.thread.is_alive():
                return
            self.cancel.clear()
            self.started_monotonic = time.monotonic()
            self._state("STARTING", "Abrindo a fonte em processo isolado.")
            self.thread = threading.Thread(target=self._run, name=f"supervisor-{self.config.id}", daemon=True)
            self.thread.start()

    def stop(self):
        with self.operation_lock:
            self.cancel.set()
            if self.worker_stop is not None:
                self.worker_stop.set()
            if self.thread and self.thread is not threading.current_thread():
                self.thread.join(timeout=5)
            if self.thread and self.thread.is_alive():
                self._state("ERROR", "O supervisor não encerrou no prazo. Reinicie o aplicativo.")
                raise RuntimeError("Encerramento do supervisor excedeu o prazo seguro.")
            self._state("STOPPED", "Captura encerrada; dispositivo liberado.")
            with self.lock:
                self.slot = None
                self.meta = {}
                self.next_retry_utc = None

    def restart(self):
        with self.operation_lock:
            self.stop()
            self.start()

    def _dispose_process(self):
        proc = self.process
        if proc is None:
            return
        self.worker_stop.set()
        proc.join(timeout=0.5)
        if proc.is_alive():
            self.forced_terminations += 1
            proc.terminate()
            proc.join(timeout=0.8)
        if proc.is_alive():
            proc.kill()
            proc.join(timeout=0.8)
        if proc.is_alive():
            raise RuntimeError("Sistema operacional não encerrou o worker.")
        with self.lock:
            self.process = None
            proc.close()

    def _run(self):
        failures = 0
        try:
            while not self.cancel.is_set():
                with self.lock:
                    self.generation += 1
                    self.meta = {}
                    self.slot = FrameSlot(self.ctx, self.config.raw_max_width, self.config.raw_max_height)
                    self.worker_stop = StopFlag(self.ctx)
                    slot = self.slot
                    worker_config = self.config.model_dump()
                    if self.stable_webcam_backend:
                        worker_config["backend"] = self.stable_webcam_backend
                    self.process = self.ctx.Process(target=self.worker_target,
                        args=(worker_config, slot, self.worker_stop, self.generation - 1),
                        name=f"capture-{self.config.id}", daemon=True)
                    self.process.start()
                    self.next_retry_utc = None
                self._state("STARTING", "Aguardando o primeiro quadro.")
                start = time.monotonic()
                last_hist = last_persist = 0.0
                got_frame = False
                exit_code = "WORKER_EXIT"
                while not self.cancel.wait(0.05):
                    status = slot.get_status()
                    packet = slot.read()
                    now = time.monotonic()
                    with self.lock:
                        self.backend = status.get("backend") or self.backend
                        if packet:
                            self.meta = packet.metadata
                    code = status.get("code", "")
                    if packet:
                        got_frame = True
                        if self.config.kind == "webcam" and self.config.backend == "auto":
                            self.stable_webcam_backend = {"DSHOW": "dshow", "MSMF": "msmf", "V4L2": "v4l2",
                                                          "AVFOUNDATION": "avfoundation"}.get(self.backend)
                        age = now - packet.metadata["received_monotonic"]
                        if age > self.config.read_timeout_s:
                            exit_code = "READ_TIMEOUT"
                            break
                        if age > self.config.stale_after_s:
                            self._state("STALE", "Quadro antigo: captura sob observação; nenhuma imagem nova confirmada.")
                        else:
                            self._state("ONLINE", "Recebendo quadros atuais.")
                        if now - last_hist >= 1:
                            sample = self.snapshot()
                            with self.lock:
                                self.history.append(sample)
                            last_hist = now
                        if now - last_persist >= 10:
                            self.store.metric(self.config.id, self.snapshot())
                            last_persist = now
                    elif now - start > self.config.open_timeout_s:
                        exit_code = "OPEN_TIMEOUT"
                        break
                    if code in ("EOF", "OPEN_FAILED", "READ_FAILED", "CAPTURE_ERROR"):
                        exit_code = code
                        break
                    if not self.process.is_alive():
                        exit_code = code if code in ("EOF", "OPEN_FAILED", "READ_FAILED", "CAPTURE_ERROR") else "WORKER_EXIT"
                        break
                self._dispose_process()
                with self.lock:
                    if self.meta:
                        self.total_decoded_base += int(self.meta.get("decoded_total", 0))
                        self.total_published_base += int(self.meta.get("published_total", 0))
                        self.total_sampled_base += int(self.meta.get("sampled_out_total", 0))
                    self.meta = {}
                if self.cancel.is_set():
                    break
                if exit_code == "EOF" and self.config.kind == "file" and not self.config.loop:
                    self._state("EOF", "Fim do arquivo. Reinicie para reproduzir novamente.")
                    break
                if got_frame and time.monotonic() - start >= 20:
                    failures = 0
                failures += 1
                self.restarts += 1
                delay = min(self.config.reconnect_max_s, 0.5 * 2 ** min(failures - 1, 8))
                delay *= random.uniform(0.9, 1.1)
                self.store.emit(self.config.id, exit_code, "Fonte interrompida; recuperação supervisionada.", "WARN",
                                {"generation": self.generation, "retry_in_s": round(delay, 2)})
                self._state("RECONNECTING", "Reconectando com espera progressiva, sem bloquear o painel.")
                with self.lock:
                    self.slot = None  # never reuse a lock that might have been held during terminate()
                    self.next_retry_utc = time.time() + delay
                self.cancel.wait(delay)
        except Exception:
            self._state("ERROR", "Falha no supervisor. Pare/inicie a fonte e exporte o diagnóstico.")
        finally:
            try:
                self._dispose_process()
            except Exception:
                self._state("ERROR", "Não foi possível finalizar o processo de captura.")
            if self.cancel.is_set():
                self._state("STOPPED", "Captura encerrada; dispositivo liberado.")

    def snapshot(self) -> dict:
        with self.lock:
            data = dict(self.meta)
            age = max(0, (time.monotonic() - data["received_monotonic"]) * 1000) if data else None
            # These counters describe the application pipeline, NOT sensor/network packet loss.
            data.update(id=self.config.id, name=self.config.name, kind=self.config.kind,
                state=self.state, reason=self.reason, backend=self.backend,
                generation=self.generation, reconnects=self.restarts,
                forced_terminations=self.forced_terminations,
                frame_age_ms=round(age, 1) if age is not None else None,
                total_decoded=self.total_decoded_base + int(data.get("decoded_total", 0)),
                total_published=self.total_published_base + int(data.get("published_total", 0)),
                total_sampled_out=self.total_sampled_base + int(data.get("sampled_out_total", 0)),
                allocated_frame_bytes=self.slot.allocated_bytes if self.slot else 0,
                worker_pid=self.process.pid if self.process is not None else None,
                next_retry_utc=self.next_retry_utc,
                fresh=age is not None and age <= self.config.stale_after_s * 1000 and self.state == "ONLINE")
            return data

    def latest(self, *, raw=False, jpeg=False) -> FramePacket | None:
        with self.lock:
            slot, state, generation = self.slot, self.state, self.generation
        if slot is None or state not in ("ONLINE", "STARTING"):
            return None
        packet = slot.read(raw=raw, jpeg=jpeg)
        if packet is None or time.monotonic() - packet.metadata["received_monotonic"] > self.config.stale_after_s:
            return None
        return FramePacket({**packet.metadata, "camera_id": self.config.id, "generation": generation}, packet.bgr, packet.jpeg)


class CameraManager:
    def __init__(self, configs: ConfigStore, store: EventStore):
        self.configs, self.store = configs, store
        self.lock = threading.RLock()
        self.sessions = {c.id: CameraSession(c, store) for c in configs.all()}

    def get(self, camera_id: str) -> CameraSession:
        with self.lock:
            return self.sessions[camera_id]

    def all(self):
        with self.lock:
            return list(self.sessions.values())

    def start(self, camera_id: str):
        with self.lock:
            session = self.sessions[camera_id]
            for other in self.sessions.values():
                if (other is not session and other.config.kind == session.config.kind == "webcam"
                    and other.config.source == session.config.source and other.thread and other.thread.is_alive()):
                    raise ValueError("Esta webcam já está em uso por outra fonte do painel.")
            session.start()

    def put(self, config: CameraConfig):
        with self.lock:
            old = self.sessions.get(config.id)
            if old and old.thread and old.thread.is_alive():
                raise ValueError("Pare a fonte antes de editar sua configuração.")
            self.configs.put(config)
            self.sessions[config.id] = CameraSession(config, self.store)
            self.store.emit(config.id, "CONFIG_SAVED", "Configuração salva. Endereço e credenciais não registrados.")

    def delete(self, camera_id: str):
        with self.lock:
            self.sessions[camera_id].stop()
            self.configs.delete(camera_id)
            del self.sessions[camera_id]
            self.store.emit(camera_id, "CONFIG_DELETED", "Fonte removida; histórico preservado.")

    def close(self):
        sessions = self.all()
        if sessions:
            with ThreadPoolExecutor(max_workers=4) as executor:
                list(executor.map(lambda s: s.stop(), sessions))
