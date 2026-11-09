"""Validate an exported incident/dataset/backup without extracting it."""
import argparse,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from vision_app.safe_archive import verify_archive


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('archive',type=Path);a=p.parse_args()
    try:
        d=verify_archive(a.archive);print(f"[PASS] {d['kind']}: {len(d['files'])} arquivos. Hash não é assinatura digital.");return 0
    except Exception as e:print('[FAIL] '+str(e));return 1

if __name__=='__main__':raise SystemExit(main())
