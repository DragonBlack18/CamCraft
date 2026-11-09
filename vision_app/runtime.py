"""Resource and persistent-data paths for source, portable and installed execution.

Only immutable resources may live in the onefile extraction directory. Camera
configuration, databases and evidence must never be written into that directory.
"""
from __future__ import annotations
import os
from pathlib import Path
import sys

APP_NAME = 'CamCraft'
VERSION = '4.2.0'
TOOLS = {
    'validate-dataset': 'tools.validate_dataset',
    'import-previous': 'tools.import_previous',
    'restore-backup': 'tools.restore_backup',
}


def is_frozen() -> bool:
    return bool(getattr(sys, 'frozen', False))


def resource_root() -> Path:
    if is_frozen():
        root = getattr(sys, '_MEIPASS', None)
        if not root:
            raise RuntimeError('Distribuição incompleta: diretório de recursos não encontrado.')
        return Path(root).resolve()
    return Path(__file__).resolve().parents[1]


def default_data_dir() -> Path:
    override = os.environ.get('CAMCRAFT_DATA_DIR', '').strip()
    if override:
        return Path(override).expanduser().resolve()
    if not is_frozen():
        return resource_root() / 'data'
    application_dir = Path(sys.executable).resolve().parent
    if (application_dir / 'installed.marker').is_file():
        local = os.environ.get('LOCALAPPDATA', '').strip()
        if not local:
            raise RuntimeError('LOCALAPPDATA indisponível; não é seguro escolher uma pasta temporária para seus dados.')
        return Path(local).resolve() / 'CamCraft' / 'data'
    return application_dir / 'CamCraft-data'


def tool_command(name: str, *arguments: object) -> list[str]:
    if name not in TOOLS:
        raise ValueError('Ferramenta interna não permitida: ' + name)
    args = [str(value) for value in arguments]
    if is_frozen():
        return [sys.executable, '--tool', name, *args]
    script = resource_root().joinpath(*TOOLS[name].split('.')).with_suffix('.py')
    if not script.is_file():
        raise RuntimeError('Ferramenta não encontrada: ' + name)
    return [sys.executable, str(script), *args]
