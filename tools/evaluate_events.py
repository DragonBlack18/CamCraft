"""Evaluate event JSON exports against manual truth; see docs/FASE3_AVALIACAO.md."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from vision_app.event_evaluation import evaluate_events


def main():
    p=argparse.ArgumentParser();p.add_argument('--predictions',type=Path,required=True)
    p.add_argument('--truth',type=Path,required=True);p.add_argument('--seconds',type=float,required=True)
    p.add_argument('--tolerance',type=float,default=2);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    try:
        report=evaluate_events(json.loads(args.predictions.read_text(encoding='utf-8')),json.loads(args.truth.read_text(encoding='utf-8')),
                               monitored_seconds=args.seconds,tolerance_seconds=args.tolerance)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False,indent=2));return 0
    except (ValueError,OSError) as exc:print('[FAIL] '+str(exc));return 1
if __name__=='__main__':raise SystemExit(main())
