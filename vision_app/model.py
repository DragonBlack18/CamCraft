"""Verified first-run model download; no executable/pickle deserialization."""
from __future__ import annotations
import hashlib
import os
import ssl
import time
import urllib.request
from pathlib import Path

MODEL_FILE = 'object_detection_yolox_2022nov.onnx'
MODEL_SIZE = 35858002
MODEL_SHA256 = 'c5c2d13e59ae883e6af3b45daea64af4833a4951c92d116ec270d9ddbe998063'
MODEL_URL = 'https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/object_detection_yolox/' + MODEL_FILE
MODEL_MIRROR = 'https://github.com/opencv/opencv_zoo/raw/refs/heads/main/models/object_detection_yolox/' + MODEL_FILE

MODEL_HUGGINGFACE = 'https://huggingface.co/opencv/opencv_zoo/resolve/main/models/object_detection_yolox/' + MODEL_FILE

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()

def verified(path: Path) -> bool:
    return path.is_file() and path.stat().st_size == MODEL_SIZE and sha256(path) == MODEL_SHA256

def ensure_model(directory: Path, progress=None, *, allow_download=True, opener=None) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / MODEL_FILE
    if verified(path):
        if progress: progress('Modelo local verificado.')
        return path
    if path.exists():
        raise ValueError('Modelo existente com tamanho/hash incorreto. Arquivo preservado; mova-o para fora de models e execute Preparar modelo novamente.')
    if not allow_download:
        raise FileNotFoundError('Modelo YOLOX não instalado. Execute Preparar modelo com acesso à internet.')
    opener = opener or urllib.request.urlopen
    partial = directory / (MODEL_FILE + f'.{os.getpid()}.download')
    for url in (MODEL_URL, MODEL_MIRROR, MODEL_HUGGINGFACE):
        try:
            request = urllib.request.Request(url, headers={'User-Agent':'VisionLocal/4.1 model-installer'})
            start = time.monotonic()
            with opener(request, timeout=25, context=ssl.create_default_context()) as response, partial.open('wb') as f:
                total = 0
                while True:
                    if time.monotonic() - start > 300:
                        raise TimeoutError('Tempo limite do download.')
                    block = response.read(256*1024)
                    if not block: break
                    total += len(block)
                    if total > MODEL_SIZE: raise ValueError('Download maior que o modelo esperado.')
                    f.write(block)
                    if progress: progress(f'Baixando modelo: {100*total/MODEL_SIZE:.0f}%')
                f.flush(); os.fsync(f.fileno())
            if not verified(partial):
                raise ValueError('O modelo recebido não corresponde ao SHA-256 oficial.')
            os.replace(partial, path)
            if progress: progress('Modelo baixado e SHA-256 conferido.')
            return path
        except Exception:
            partial.unlink(missing_ok=True)
    raise RuntimeError('Não foi possível baixar/verificar o YOLOX. Confira internet/proxy ou copie o arquivo oficial para models. Nenhuma câmera foi enviada à internet.') from None
