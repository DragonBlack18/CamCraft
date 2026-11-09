"""Bounded, path-safe ZIP snapshots. Hashes detect damage, not authorship/signatures."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from typing import Iterable

MAX_FILES = 30000
MAX_TOTAL = 12 * 1024**3
MAX_MEMBER = 1024**3
MANIFEST = 'archive-manifest.json'


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def safe_name(name: str) -> str:
    """Portable names: reject traversal, ADS, Windows devices and alias collisions."""
    if not isinstance(name, str) or not name or '\\' in name or '\x00' in name:
        raise ValueError('Nome de arquivo inseguro.')
    p = PurePosixPath(name)
    if p.is_absolute() or any(part in ('', '.', '..') for part in name.split('/')):
        raise ValueError('Caminho absoluto/relativo inseguro no pacote.')
    for part in p.parts:
        if any(c in part for c in ':<>"|?*') or part.endswith((' ', '.')) or any(ord(c) < 32 for c in part):
            raise ValueError('Nome incompatível com Windows no pacote.')
        if re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', part):
            raise ValueError('Nome reservado pelo Windows.')
    return name


def write_archive(target: Path, members: Iterable[tuple[str, Path | bytes]], *, kind: str, metadata=None) -> dict:
    """Never replace an existing export. Publish only after a streamed hash check."""
    target = Path(target)
    if target.exists():
        raise FileExistsError('O destino já existe; escolha um novo nome.')
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name('.' + target.name + '.' + uuid.uuid4().hex + '.part')
    entries, names, total = {}, set(), 0
    try:
        with zipfile.ZipFile(temp, 'w', zipfile.ZIP_DEFLATED, compresslevel=3) as archive:
            for name, source in members:
                safe_name(name)
                if name.casefold() in names or name.casefold() == MANIFEST.casefold():
                    raise ValueError('Nome repetido/reservado no pacote.')
                if len(entries) >= MAX_FILES:
                    raise ValueError('Pacote excede o limite de arquivos.')
                names.add(name.casefold())
                if isinstance(source, Path):
                    if source.is_symlink() or not source.is_file():
                        raise ValueError('Fonte inválida ou link simbólico.')
                    size = source.stat().st_size
                else:
                    size = len(source)
                if size > MAX_MEMBER or total + size > MAX_TOTAL:
                    raise ValueError('Pacote excede limite de tamanho.')
                h, actual = hashlib.sha256(), 0
                with archive.open(name, 'w', force_zip64=True) as out:
                    if isinstance(source, Path):
                        with source.open('rb') as stream:
                            while chunk := stream.read(1024 * 1024):
                                actual += len(chunk)
                                if actual > size:
                                    raise ValueError('Arquivo mudou durante a exportação.')
                                h.update(chunk); out.write(chunk)
                    else:
                        h.update(source); out.write(source); actual = len(source)
                if actual != size:
                    raise ValueError('Arquivo mudou durante a exportação.')
                total += actual
                entries[name] = {'bytes': actual, 'sha256': h.hexdigest()}
            document = {'schema': 1, 'kind': kind, 'files': entries, 'bytes': total,
                        'metadata': metadata or {},
                        'note': 'SHA-256 detecta divergências em relação ao manifesto. Não é assinatura digital nem prova de autoria.'}
            archive.writestr(MANIFEST, json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False))
        verify_archive(temp, expected_kind=kind)
        # Exclusive create prevents accidental overwrite even if another task creates target.
        with target.open('xb') as out, temp.open('rb') as src:
            try:
                for chunk in iter(lambda: src.read(1024 * 1024), b''):
                    out.write(chunk)
                out.flush(); os.fsync(out.fileno())
            except BaseException:
                out.close(); target.unlink(missing_ok=True); raise
        return document
    finally:
        temp.unlink(missing_ok=True)


def verify_archive(path: Path, *, expected_kind=None) -> dict:
    with zipfile.ZipFile(path) as archive:
        info = archive.infolist()
        if len(info) > MAX_FILES + 1:
            raise ValueError('Pacote contém arquivos demais.')
        names, total = set(), 0
        for item in info:
            safe_name(item.filename)
            folded = item.filename.casefold()
            if folded in names:
                raise ValueError('Nomes duplicados/ambíguos no pacote.')
            names.add(folded)
            if item.is_dir() or stat.S_ISLNK(item.external_attr >> 16) or item.flag_bits & 1:
                raise ValueError('Diretório/link/arquivo criptografado inesperado no pacote.')
            total += item.file_size
            if item.file_size > MAX_MEMBER or total > MAX_TOTAL:
                raise ValueError('Tamanho descompactado acima do limite.')
        if MANIFEST not in archive.namelist() or archive.getinfo(MANIFEST).file_size > 8 * 1024**2:
            raise ValueError('Manifesto ausente ou muito grande.')
        document = json.loads(archive.read(MANIFEST))
        if document.get('schema') != 1 or (expected_kind and document.get('kind') != expected_kind):
            raise ValueError('Formato de pacote incompatível.')
        files = document.get('files')
        if not isinstance(files, dict) or set(files) != set(archive.namelist()) - {MANIFEST}:
            raise ValueError('Inventário do pacote não corresponde aos arquivos.')
        for name, expected in files.items():
            if not isinstance(expected, dict) or expected.get('bytes') != archive.getinfo(name).file_size:
                raise ValueError('Tamanho divergente: ' + name)
            h, count = hashlib.sha256(), 0
            with archive.open(name) as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    count += len(block)
                    if count > MAX_MEMBER:
                        raise ValueError('Membro excedeu o limite.')
                    h.update(block)
            if h.hexdigest() != expected.get('sha256') or count != expected.get('bytes'):
                raise ValueError('SHA-256 divergente: ' + name)
        return document
