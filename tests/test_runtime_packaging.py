from pathlib import Path
import sys
import pytest
from vision_app import runtime


def freeze(monkeypatch, tmp_path):
    exe = tmp_path/'Application folder'/'CamCraft.exe'
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b'placeholder')
    unpack = tmp_path/'unpack-temp'
    unpack.mkdir()
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, '_MEIPASS', str(unpack), raising=False)
    monkeypatch.setattr(sys, 'executable', str(exe))
    monkeypatch.delenv('CAMCRAFT_DATA_DIR', raising=False)
    return exe, unpack


def test_portable_data_never_in_temp(monkeypatch, tmp_path):
    exe, unpack = freeze(monkeypatch, tmp_path)
    assert runtime.resource_root() == unpack
    assert runtime.default_data_dir() == exe.parent/'CamCraft-data'
    assert unpack not in runtime.default_data_dir().parents


def test_installed_data_localappdata(monkeypatch, tmp_path):
    exe, unpack = freeze(monkeypatch, tmp_path)
    (exe.parent/'installed.marker').write_text('per-user')
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path/'User profile'/'Local'))
    assert runtime.default_data_dir() == tmp_path/'User profile'/'Local'/'CamCraft'/'data'


def test_installed_without_localappdata_refuses_ephemeral_fallback(monkeypatch, tmp_path):
    exe, _ = freeze(monkeypatch, tmp_path)
    (exe.parent/'installed.marker').touch()
    monkeypatch.delenv('LOCALAPPDATA', raising=False)
    with pytest.raises(RuntimeError): runtime.default_data_dir()


def test_data_override(monkeypatch, tmp_path):
    freeze(monkeypatch, tmp_path)
    monkeypatch.setenv('CAMCRAFT_DATA_DIR', str(tmp_path/'controlled-data'))
    assert runtime.default_data_dir() == tmp_path/'controlled-data'


def test_frozen_tool_uses_its_own_entrypoint(monkeypatch, tmp_path):
    exe, _ = freeze(monkeypatch, tmp_path)
    command = runtime.tool_command('validate-dataset', '--manifest', tmp_path/'a b.json')
    assert command == [str(exe), '--tool', 'validate-dataset', '--manifest', str(tmp_path/'a b.json')]
    assert not any(v.endswith('.py') for v in command)


def test_tool_whitelist():
    with pytest.raises(ValueError): runtime.tool_command('../../arbitrary')


def test_source_tool_command(monkeypatch):
    monkeypatch.delattr(sys, 'frozen', raising=False)
    command = runtime.tool_command('validate-dataset', '--help')
    assert Path(command[1]).is_file()
    assert command[-1] == '--help'


def test_source_default_model_path(monkeypatch):
    monkeypatch.delattr(sys, 'frozen', raising=False)
    monkeypatch.delenv('CAMCRAFT_DATA_DIR', raising=False)
    assert (runtime.resource_root()/'models'/'manifest.json').is_file()
    assert runtime.default_data_dir() == runtime.resource_root()/'data'


def test_distribution_contracts():
    root = runtime.resource_root()
    spec = (root/'packaging'/'camcraft.spec').read_text()
    assert 'onefile' in spec and 'COLLECT' in spec and 'MODEL_SHA256' in spec
    assert 'upx=False' in spec and 'console=False' in spec
    installer = (root/'packaging'/'installer.iss').read_text()
    assert 'PrivilegesRequired=lowest' in installer
    assert 'installed.marker' in installer
    assert '[UninstallDelete]' not in installer
