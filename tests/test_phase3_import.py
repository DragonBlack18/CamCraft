import importlib.util,json,sqlite3
from pathlib import Path
import pytest
from vision_app.instance import InstanceLock
spec=importlib.util.spec_from_file_location('previous_import',Path(__file__).resolve().parents[1]/'tools'/'import_previous.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def source(tmp_path):
    p=tmp_path/'old'/'data';p.mkdir(parents=True)
    (p/'cameras.json').write_text('{"schema": 1}')
    with sqlite3.connect(p/'events.sqlite3') as db:db.execute('CREATE TABLE test(x)');db.execute('INSERT INTO test VALUES (42)')
    (p/'evidence').mkdir();(p/'evidence'/'saved.txt').write_text('preserve')
    return p


def test_import_new_destination_and_keep_source(tmp_path):
    old=source(tmp_path);new=tmp_path/'new'/'data'
    result=module.import_data(old.parent,new)
    assert 'events.sqlite3' in result
    assert (old/'evidence'/'saved.txt').read_text()=='preserve'
    assert (new/'evidence'/'saved.txt').read_text()=='preserve'
    with sqlite3.connect(new/'events.sqlite3') as db:assert db.execute('SELECT x FROM test').fetchone()[0]==42


def test_import_refuses_overwrite(tmp_path):
    old=source(tmp_path);new=tmp_path/'new';new.mkdir();(new/'cameras.json').write_text('keep')
    with pytest.raises(ValueError,match='Destino'):module.import_data(old,new)
    assert (new/'cameras.json').read_text()=='keep'


def test_import_refuses_running_source(tmp_path):
    old=source(tmp_path);lock=InstanceLock(old)
    try:
        with pytest.raises(RuntimeError):module.import_data(old,tmp_path/'new')
    finally:lock.close()


def test_import_does_not_follow_symlinks(tmp_path):
    old=source(tmp_path)
    try:(old/'evidence'/'link').symlink_to(tmp_path)
    except OSError:pytest.skip('Criação de symlink indisponível nesta conta/plataforma.')
    with pytest.raises(ValueError,match='simbólicos'):module.import_data(old,tmp_path/'new')
