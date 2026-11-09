import hashlib,json,stat,zipfile
from pathlib import Path
import pytest
from vision_app.safe_archive import safe_name,write_archive,verify_archive,MANIFEST

@pytest.mark.parametrize('name',['../escape','/abs','a/../b','a//b','a/./b','C:/x','a\\b','a\x00b','CON','prn.txt','a/NUL.png','a/x.','a/x ','a/a:b','COM1.txt','lpt9'])
def test_reject_unsafe_paths(name):
    with pytest.raises(ValueError):safe_name(name)

@pytest.mark.parametrize('name',['data/events.sqlite3','data/evidence/e_abc/quadro.jpg','registros.json','a/objeto-ç.png'])
def test_safe_portable_paths(name):assert safe_name(name)==name

def test_archive_roundtrip_and_no_overwrite(tmp_path):
    source=tmp_path/'source';source.write_bytes(b'123'*100)
    path=tmp_path/'bundle.zip';result=write_archive(path,[('a/b.bin',source),('meta.json',b'{}')],kind='test')
    assert verify_archive(path,expected_kind='test')['files']==result['files']
    with pytest.raises(FileExistsError):write_archive(path,[],kind='test')
    with pytest.raises(ValueError):verify_archive(path,expected_kind='other')
    assert not list(tmp_path.glob('*.part'))

def test_corruption_is_detected(tmp_path):
    p=tmp_path/'x.zip';write_archive(p,[('a.txt',b'hello')],kind='test')
    with zipfile.ZipFile(p) as z:manifest=z.read(MANIFEST)
    with zipfile.ZipFile(p,'w') as z:z.writestr('a.txt',b'HELLO');z.writestr(MANIFEST,manifest)
    with pytest.raises(ValueError,match='SHA-256'):verify_archive(p)

def test_duplicate_case_insensitive_names_rejected(tmp_path):
    with pytest.raises(ValueError):write_archive(tmp_path/'x.zip',[('A.txt',b'a'),('a.txt',b'b')],kind='test')
    assert not (tmp_path/'x.zip').exists()

def test_zip_symlink_rejected(tmp_path):
    p=tmp_path/'x.zip';info=zipfile.ZipInfo('x');info.external_attr=(stat.S_IFLNK | 0o777)<<16
    with zipfile.ZipFile(p,'w') as z:z.writestr(info,b'/etc/passwd');z.writestr(MANIFEST,b'{}')
    with pytest.raises(ValueError):verify_archive(p)

def test_extra_member_rejected(tmp_path):
    p=tmp_path/'x.zip';write_archive(p,[('a',b'1')],kind='test')
    with zipfile.ZipFile(p,'a') as z:z.writestr('extra',b'x')
    with pytest.raises(ValueError,match='Inventário'):verify_archive(p)

def test_traversal_zip_rejected_before_read(tmp_path):
    p=tmp_path/'x.zip'
    with zipfile.ZipFile(p,'w') as z:z.writestr('../x',b'1');z.writestr(MANIFEST,b'{}')
    with pytest.raises(ValueError):verify_archive(p)
