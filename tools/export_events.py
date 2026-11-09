"""Read-only event export for manual evaluation. Use a common UTC origin for truth."""
import argparse,json,sqlite3,sys
from pathlib import Path
from contextlib import closing
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from vision_app.interactions import MAJOR_EVENTS


def main():
    p=argparse.ArgumentParser();p.add_argument('--db',type=Path,required=True)
    p.add_argument('--origin-utc',type=float,default=0);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    try:
        output=[]
        with closing(sqlite3.connect(args.db.resolve().as_uri()+'?mode=ro',uri=True)) as db:
            for cid,code,payload in db.execute('SELECT camera_id,code,payload FROM events ORDER BY id'):
                if code not in MAJOR_EVENTS:continue
                v=json.loads(payload);stamp=float(v.get('frame_utc',0))-args.origin_utc
                if stamp<0:continue
                output.append({'camera_id':cid,'object_id':v.get('object_id'),'code':code,'time_s':stamp,
                    'actor_track_id':v.get('actor_track_id'),'event_id':v.get('event_id')})
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
        print('[PASS] '+str(len(output))+' eventos exportados. Use a mesma origem temporal nos rótulos manuais.');return 0
    except (ValueError,OSError,sqlite3.Error) as exc:print('[FAIL] '+str(exc));return 1
if __name__=='__main__':raise SystemExit(main())
