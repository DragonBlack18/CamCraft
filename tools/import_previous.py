"""Non-destructive import into a NEW installation. Both applications must be closed."""
from __future__ import annotations
import argparse,hashlib,json,os,shutil,sqlite3,sys,uuid
from pathlib import Path
from contextlib import closing
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from vision_app.instance import InstanceLock

NAMES=('cameras.json','analysis.json','objects.json','references','evidence','events.sqlite3','dataset','display.json','analysis.pre-v4.1.json')


def import_data(source:Path,destination:Path):
    source=source.resolve();destination=destination.resolve()
    if (source/'data').is_dir():source=source/'data'
    if not source.is_dir():raise ValueError('Pasta de dados de origem não encontrada.')
    if source==destination or source in destination.parents or destination in source.parents:
        raise ValueError('Origem e destino precisam ser pastas independentes.')
    destination.mkdir(parents=True,exist_ok=True)
    if any((destination/name).exists() for name in NAMES):
        raise ValueError('Destino já contém dados. Use uma nova pasta; nenhum dado será sobrescrito.')
    src_lock=dst_lock=None;stage=destination/('.import-'+uuid.uuid4().hex);stage.mkdir()
    installed=[]
    try:
        src_lock=InstanceLock(source);dst_lock=InstanceLock(destination)
        for name in NAMES:
            original=source/name
            if not original.exists():continue
            if original.is_symlink() or (original.is_dir() and any(p.is_symlink() for p in original.rglob('*'))):
                raise ValueError('Importação não aceita links simbólicos em '+name)
            if name=='events.sqlite3':
                # SQLite backup API includes committed WAL content without copying live journals.
                uri=original.as_uri()+'?mode=ro'
                with closing(sqlite3.connect(uri,uri=True)) as src, closing(sqlite3.connect(stage/name)) as dst:
                    src.backup(dst)
                    if dst.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Banco de origem inválido.')
            elif original.is_dir():shutil.copytree(original,stage/name)
            else:
                if name.endswith('.json'):json.loads(original.read_text(encoding='utf-8'))
                shutil.copy2(original,stage/name)
        if not (stage/'cameras.json').exists():raise ValueError('Origem não contém cameras.json.')
        for item in sorted(stage.iterdir()):
            os.replace(item,destination/item.name);installed.append(destination/item.name)
        return [p.name for p in installed]
    except Exception:
        # Only newly imported paths in the previously empty destination may be rolled back.
        for p in installed:
            if p.is_dir():shutil.rmtree(p)
            else:p.unlink(missing_ok=True)
        raise
    finally:
        if dst_lock:dst_lock.close()
        if src_lock:src_lock.close()
        shutil.rmtree(stage,ignore_errors=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True)
    p.add_argument('--destination',type=Path,default=__import__('vision_app.runtime',fromlist=['default_data_dir']).default_data_dir());args=p.parse_args()
    try:
        files=import_data(args.source,args.destination);print('[PASS] Dados importados: '+', '.join(files))
        print('Origem preservada. Credenciais DPAPI só são utilizáveis na conta/PC compatível. Pesos do modelo e .venv não foram copiados.');return 0
    except (OSError,ValueError,RuntimeError,sqlite3.Error) as exc:print('[FAIL] '+str(exc));return 1
if __name__=='__main__':raise SystemExit(main())
