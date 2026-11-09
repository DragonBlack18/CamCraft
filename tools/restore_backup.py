"""Restore a verified backup into an EMPTY data folder, never overwrite or merge."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from vision_app.backup import restore_backup


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive',type=Path,required=True);p.add_argument('--destination',type=Path,required=True)
    a=p.parse_args()
    try:
        print(json.dumps(restore_backup(a.archive,a.destination),ensure_ascii=False,indent=2));print('[PASS] Backup restaurado e verificado.');return 0
    except Exception as e:print('[FAIL] '+str(e));return 1

if __name__=='__main__':raise SystemExit(main())
