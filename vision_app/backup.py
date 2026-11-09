"""Quiescent full backups, SQLite backup API, verified restore into an empty directory."""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
import time
import zipfile
from contextlib import closing
from pathlib import Path

from .instance import InstanceLock
from .safe_archive import verify_archive, write_archive, MANIFEST

DATA_NAMES = ('cameras.json', 'analysis.json', 'objects.json', 'references', 'evidence', 'events.sqlite3', 'dataset', 'display.json', 'analysis.pre-v4.1.json')


def create_backup(controller, target):
    """Caller owns InstanceLock; operation_lock prevents start/settings during snapshot."""
    target = Path(target).resolve()
    root = controller.directory.resolve()
    if root == target or root in target.parents:
        raise ValueError('Salve o backup fora da pasta data.')
    with controller.operation_lock:
        if controller.camera or controller.analysis:
            raise ValueError('Pare a câmera antes de criar backup consistente.')
        if not controller.evidence.flush(10) or not controller.evidence.clips.flush(10) or not controller.events.flush(10):
            raise OSError('Gravações pendentes não concluídas. Backup não criado.')
        if not controller.events.health()['healthy']:
            raise OSError('Há falhas de armazenamento nesta sessão. Consulte diagnóstico antes do backup.')
        with controller.evidence.access_lock, controller.dataset.lock, tempfile.TemporaryDirectory(prefix='vision-backup-') as tmp:
            snapshot = Path(tmp) / 'events.sqlite3'
            with closing(controller.events.connect()) as src, closing(sqlite3.connect(snapshot)) as dst:
                deadline = time.monotonic() + 30
                def progress(status, remaining, total):
                    if time.monotonic() > deadline:
                        raise TimeoutError('Backup SQLite excedeu prazo.')
                src.backup(dst, pages=128, progress=progress, sleep=.01)
                if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('Backup SQLite inconsistente.')
            members = []
            for name in DATA_NAMES:
                path = root / name
                if name == 'events.sqlite3':
                    members.append(('data/' + name, snapshot)); continue
                if not path.exists():
                    continue
                if path.is_symlink():
                    raise ValueError('Backup não aceita links simbólicos.')
                if path.is_file():
                    members.append(('data/' + name, path)); continue
                for item in sorted(path.rglob('*')):
                    if item.is_symlink():
                        raise ValueError('Backup não aceita links simbólicos.')
                    if item.is_file():
                        if any(p.startswith('.pending-') for p in item.relative_to(root).parts):
                            raise ValueError('Existe escrita pendente; backup recusado.')
                        members.append(('data/' + item.relative_to(root).as_posix(), item))
            metadata = {'created_utc': time.time(), 'application': 'CamCraft 4.2.0',
                        'credentials_included': True, 'encryption': 'ZIP não criptografado; credenciais DPAPI mantêm proteção original no Windows.',
                        'note': 'Contém imagens, anotações e horários. Guarde em local restrito. DPAPI depende de conta/PC compatíveis.'}
            return write_archive(target, members, kind='vision-backup', metadata=metadata)


def restore_backup(archive_path, destination):
    """No overwrite/merge, no symlinks/zip traversal, rollback only newly installed paths."""
    archive_path, destination = Path(archive_path).resolve(), Path(destination).resolve()
    document = verify_archive(archive_path, expected_kind='vision-backup')
    for name in document['files']:
        parts = Path(name).parts
        if len(parts) < 2 or parts[0] != 'data' or parts[1] not in DATA_NAMES:
            raise ValueError('Arquivo não permitido em backup de dados.')
    if 'data/cameras.json' not in document['files'] or 'data/events.sqlite3' not in document['files']:
        raise ValueError('Backup incompleto: faltam banco/câmeras.')
    destination.mkdir(parents=True, exist_ok=True)
    if any(p.name != '.instance.lock' for p in destination.iterdir()):
        raise ValueError('Destino precisa estar vazio. Nenhum dado existente foi sobrescrito.')
    lock = InstanceLock(destination)
    installed = []
    stage = None
    try:
        if any(p.name != '.instance.lock' for p in destination.iterdir()):
            raise ValueError('Destino deixou de estar vazio.')
        # Stage on the same filesystem, separate from the final data directory.
        stage = Path(tempfile.mkdtemp(prefix='.vision-restore-', dir=destination.parent))
        with zipfile.ZipFile(archive_path) as archive:
            for name, item in document['files'].items():
                relative = Path(name).relative_to('data'); target = stage / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(name) as src, target.open('xb') as out:
                    shutil.copyfileobj(src, out, 1024 * 1024)
        from .safe_archive import digest
        for name, item in document['files'].items():
            target = stage / Path(name).relative_to('data')
            if target.stat().st_size != item['bytes'] or digest(target) != item['sha256']:
                raise ValueError('Arquivo mudou entre verificação e restauração.')
        with closing(sqlite3.connect((stage / 'events.sqlite3').as_uri() + '?mode=ro', uri=True)) as db:
            if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Banco restaurado não passou na integridade.')
            if not {'events', 'metrics'} <= {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
                raise ValueError('Banco não corresponde ao aplicativo.')
        for name in ('cameras.json', 'analysis.json', 'objects.json'):
            if (stage / name).exists():
                json.loads((stage / name).read_text(encoding='utf-8'))
        for item in sorted(stage.iterdir()):
            target = destination / item.name
            if target.exists():
                raise FileExistsError('Destino mudou durante a restauração.')
            os.replace(item, target); installed.append(target)
        return {'restored': [p.name for p in installed], 'files_verified': len(document['files']),
                'note': 'Backup de origem preservado. Modelo e ambiente Python não são parte do backup.'}
    except BaseException:
        for path in installed:
            if path.is_dir(): shutil.rmtree(path)
            else: path.unlink(missing_ok=True)
        raise
    finally:
        if stage: shutil.rmtree(stage, ignore_errors=True)
        lock.close()
