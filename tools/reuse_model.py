"""Reuse ONLY the verified official ONNX from an older local installation."""
from __future__ import annotations
import argparse,os,shutil,sys,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from vision_app.model import MODEL_FILE,verified


def reuse(source:Path,destination:Path):
    source=source.resolve()
    base=source.parent if source.name=='data' else source
    old=base/'models'/MODEL_FILE
    target=destination/MODEL_FILE
    if verified(target):return 'ALREADY_VERIFIED'
    if target.exists():raise ValueError('Modelo no destino não confere. Arquivo preservado.')
    if not old.is_file():return 'NOT_FOUND'
    if old.is_symlink() or not verified(old):raise ValueError('Modelo anterior não corresponde ao hash oficial; não foi copiado.')
    destination.mkdir(parents=True,exist_ok=True)
    tmp=destination/(MODEL_FILE+'.'+uuid.uuid4().hex+'.copy')
    try:
        shutil.copy2(old,tmp)
        if not verified(tmp):raise ValueError('Modelo mudou durante a cópia.')
        os.replace(tmp,target)
    finally:tmp.unlink(missing_ok=True)
    return 'COPIED_VERIFIED'


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True)
    p.add_argument('--destination',type=Path,default=Path(__file__).resolve().parents[1]/'models')
    args=p.parse_args()
    try:
        result=reuse(args.source,args.destination)
        print('[INFO] Modelo anterior: '+result+'. Dados de origem preservados.')
        return 0
    except (ValueError,OSError) as exc:
        print('[WARN] '+str(exc));return 1
if __name__=='__main__':raise SystemExit(main())
