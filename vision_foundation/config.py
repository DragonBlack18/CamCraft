from __future__ import annotations

import base64
import ctypes
import json
import os
import re
import threading
import uuid
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CameraConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12], pattern=r"^[a-zA-Z0-9_-]{1,40}$")
    name: str = Field(default="Câmera", min_length=1, max_length=60)
    kind: Literal["demo", "webcam", "rtsp", "http", "file"] = "webcam"
    source: str = Field(default="0", max_length=2048, repr=False)
    backend: Literal["auto", "dshow", "msmf", "v4l2", "avfoundation", "ffmpeg"] = "auto"
    width: int = Field(default=1280, ge=160, le=3840)
    height: int = Field(default=720, ge=120, le=2160)
    fps: int = Field(default=30, ge=1, le=60)
    publish_fps: int = Field(default=30, ge=1, le=30)
    preview_width: int = Field(default=960, ge=160, le=1920)
    jpeg_quality: int = Field(default=80, ge=40, le=95)
    jpeg_preview: bool = True  # Desktop analysis consumes raw frames; disable redundant JPEG.
    raw_max_width: int = Field(default=1920, ge=320, le=3840)
    raw_max_height: int = Field(default=1080, ge=240, le=2160)
    open_timeout_s: float = Field(default=12, ge=2, le=60)
    read_timeout_s: float = Field(default=6, ge=2, le=30)
    stale_after_s: float = Field(default=2, ge=0.5, le=10)
    reconnect_max_s: float = Field(default=30, ge=2, le=120)
    rtsp_transport: Literal["tcp", "udp"] = "tcp"
    fourcc: Literal["auto", "MJPG", "YUY2"] = "MJPG"
    loop: bool = True
    autostart: bool = False

    @model_validator(mode="after")
    def check_source(self):
        if any(c in self.source for c in ("\n", "\r", "\x00")):
            raise ValueError("A fonte contém caracteres de controle.")
        if self.kind == "webcam":
            if not self.source.isdecimal() or not 0 <= int(self.source) <= 31:
                raise ValueError("Índice de webcam: use um número de 0 a 31.")
            self.source = str(int(self.source))
            if self.backend == "ffmpeg":
                raise ValueError("FFmpeg não é um backend de webcam por índice.")
        elif self.kind in ("rtsp", "http"):
            try:
                p = urlsplit(self.source)
                valid = p.scheme in ({"rtsp", "rtsps"} if self.kind == "rtsp" else {"http", "https"})
                if not valid or not p.hostname or not (p.port is None or 1 <= p.port <= 65535):
                    raise ValueError()
            except ValueError:
                raise ValueError("URL de rede inválida para o tipo selecionado.") from None
            if self.backend not in ("auto", "ffmpeg"):
                raise ValueError("Fontes de rede utilizam o backend FFmpeg.")
        elif self.kind == "file":
            p = Path(self.source).expanduser()
            if p.suffix.lower() not in {".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".ts", ".mjpeg"}:
                raise ValueError("Selecione um arquivo de vídeo suportado, não uma URL.")
            if not p.is_file():
                raise ValueError("Arquivo de vídeo não encontrado neste computador.")
            if self.backend not in ("auto", "ffmpeg"):
                raise ValueError("Arquivos de vídeo utilizam o backend FFmpeg.")
            self.source = str(p.resolve())
        if self.stale_after_s >= self.read_timeout_s:
            raise ValueError("O limite de imagem antiga deve ser menor que o timeout de leitura.")
        return self

    def public(self) -> dict:
        data = self.model_dump(exclude={"source"})
        data["source_display"] = redact_source(self.source, self.kind)
        data["has_source"] = bool(self.source)
        return data


def redact_source(source: str, kind: str = "") -> str:
    if kind == "file":
        # Do not expose the user's home directory in the dashboard/diagnostic export.
        return Path(source.replace("\\", "/")).name
    if kind == "demo":
        return "Gerador local • sem câmera"
    if kind == "webcam":
        return f"Dispositivo {source}"
    try:
        p = urlsplit(source)
        host = p.hostname or "fonte"
        if ":" in host:
            host = f"[{host}]"
        if p.port:
            host += f":{p.port}"
        # Paths themselves may contain API keys, so they are not returned either.
        return urlunsplit((p.scheme, host, "/…", "", ""))
    except ValueError:
        return "Fonte protegida"


def protect(value: str) -> dict:
    if os.name != "nt":
        return {"mode": "file-permissions", "value": value}
    return {"mode": "windows-dpapi", "value": base64.b64encode(_dpapi(value.encode(), False)).decode()}


def unprotect(data: dict) -> str:
    if data["mode"] == "windows-dpapi":
        if os.name != "nt":
            raise ValueError("Esta fonte foi protegida pelo Windows. Cadastre-a novamente no sistema de destino.")
        return _dpapi(base64.b64decode(data["value"]), True).decode()
    return data["value"]


def _dpapi(raw: bytes, decrypt: bool) -> bytes:
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

    buf = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
    source, result = Blob(len(raw), buf), Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if decrypt:
        fn = crypt.CryptUnprotectData
        fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                       ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        ok = fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result))
    else:
        fn = crypt.CryptProtectData
        fn.argtypes = [ctypes.POINTER(Blob), wintypes.LPCWSTR, ctypes.c_void_p,
                       ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        ok = fn(ctypes.byref(source), "Vision Foundation", None, None, None, 1, ctypes.byref(result))
    if not ok:
        raise OSError("Falha ao proteger/desproteger a fonte com a conta atual do Windows.")
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        kernel.LocalFree(ctypes.cast(result.pbData, ctypes.c_void_p))


class ConfigStore:
    """Atomic profile updates. Invalid configuration is never silently overwritten."""
    def __init__(self, directory: Path):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        try:
            directory.chmod(0o700)
        except OSError:
            pass
        self.path = directory / "cameras.json"
        self.lock = threading.RLock()
        self.cameras: dict[str, CameraConfig] = {}
        if self.path.exists():
            obj = json.loads(self.path.read_text(encoding="utf-8"))
            if obj.get("schema") != 1:
                raise ValueError("Versão de cameras.json não suportada; arquivo preservado.")
            for row in obj["cameras"]:
                row = dict(row)
                row["source"] = unprotect(row.pop("source_protected"))
                # Missing local files should not prevent the entire application from starting.
                if row.get("kind") == "file" and not Path(row["source"]).is_file():
                    camera = CameraConfig.model_construct(**row)
                else:
                    camera = CameraConfig.model_validate(row)
                self.cameras[camera.id] = camera
        if len(self.cameras) > 4:
            raise ValueError("Configuração contém mais de quatro fontes; arquivo preservado.")

    def all(self) -> list[CameraConfig]:
        with self.lock:
            return list(self.cameras.values())

    def get(self, camera_id: str) -> CameraConfig:
        with self.lock:
            return self.cameras[camera_id]

    def put(self, config: CameraConfig):
        with self.lock:
            if config.id not in self.cameras and len(self.cameras) >= 4:
                raise ValueError("Limite desta versão: quatro fontes cadastradas.")
            old = dict(self.cameras)
            self.cameras[config.id] = config
            try:
                self._save()
            except Exception:
                self.cameras = old
                raise

    def delete(self, camera_id: str):
        with self.lock:
            old = self.cameras.pop(camera_id)
            try:
                self._save()
            except Exception:
                self.cameras[camera_id] = old
                raise

    def _save(self):
        rows = []
        for c in self.cameras.values():
            row = c.model_dump(exclude={"source"})
            row["source_protected"] = protect(c.source)
            rows.append(row)
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump({"schema": 1, "cameras": rows}, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        try:
            tmp.chmod(0o600)
        except OSError:
            pass
        os.replace(tmp, self.path)
