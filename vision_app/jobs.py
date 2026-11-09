"""Bounded cancellable subprocesses for offline evaluation; no shell/network calls."""
from __future__ import annotations
import os
import subprocess
import threading
import time
from pathlib import Path


class ExternalJobs:
    def __init__(self):
        self.lock = threading.Lock()
        self.cancel = threading.Event()
        self.closed = False
        self.process = None

    def run(self, command, log_path: Path, *, timeout=1800):
        with self.lock:
            if self.closed or self.process is not None:
                raise RuntimeError('Outra avaliação está ativa ou o aplicativo foi encerrado.')
            self.cancel.clear()
            log_path.parent.mkdir(parents=True, exist_ok=True)
            stream = log_path.open('wb')
            try:
                environment = os.environ.copy()
                if getattr(__import__('sys'), 'frozen', False):
                    environment['CAMCRAFT_CHILD_LOG'] = str(log_path.resolve())
                process = subprocess.Popen([str(v) for v in command], stdout=stream, stderr=subprocess.STDOUT,
                                           stdin=subprocess.DEVNULL, shell=False, env=environment,
                                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            except BaseException:
                stream.close(); raise
            self.process = process
        began = time.monotonic()
        try:
            while process.poll() is None:
                if self.cancel.wait(.1):
                    raise InterruptedError('Avaliação cancelada; nenhum relatório parcial foi aprovado.')
                if time.monotonic() - began > timeout:
                    raise TimeoutError('Avaliação excedeu o prazo; processo encerrado.')
                if log_path.stat().st_size > 2 * 1024**2:
                    raise RuntimeError('Log excedeu o limite; processo encerrado.')
            if process.returncode != 0:
                raise RuntimeError('Avaliação não concluída. Consulte ' + log_path.name + ' em data/reports.')
            return {'exit_code': process.returncode, 'seconds': time.monotonic()-began, 'log': str(log_path)}
        finally:
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=2)
            stream.close()
            with self.lock:
                self.process = None

    def close(self):
        with self.lock:
            self.closed = True
            process = self.process
            self.cancel.set()
        if process and process.poll() is None:
            try: process.terminate()
            except OSError: pass
            try: process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=2)
