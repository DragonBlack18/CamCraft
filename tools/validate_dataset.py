"""Real neural evaluation on manually annotated images. Atomic reports, explicit gate."""
from pathlib import Path
import argparse
import json
import os
import sys
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ.setdefault(name,'1')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--model-dir',type=Path,default=Path(__file__).resolve().parents[1]/'models')
    parser.add_argument('--confidence',type=float,default=.45)
    parser.add_argument('--iou',type=float,default=.5)
    parser.add_argument('--threads',type=int,default=2)
    parser.add_argument('--sweep',action='store_true',help='Só permite conjunto val, nunca test.')
    args=parser.parse_args()
    try:
        from vision_app.quality import evaluate_manifest,acceptance_gate
        from vision_app.detector import YoloXDetector
        from vision_app.model import MODEL_FILE
        from vision_app.settings import AnalysisConfig
        from vision_app.object_registry import atomic_json
        if args.output.exists():raise ValueError('Relatório já existe. Use outro nome.')
        detector=YoloXDetector(args.model_dir/MODEL_FILE,AnalysisConfig(confidence=args.confidence,threads=args.threads,classes='all'))
        result=evaluate_manifest(args.manifest,detector,confidence=args.confidence,iou=args.iou,sweep=args.sweep)
        result['detector_config']=detector.cfg.model_dump()
        result['acceptance']=acceptance_gate(result)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        atomic_json(args.output,result)
        print('[PASS] Avaliação executada. Aprovação do ensaio: '+result['acceptance']['decision'])
        print(json.dumps({'images':result['images'],'results':result['results'],'acceptance':result['acceptance']},ensure_ascii=False,indent=2))
        return 0
    except Exception as exc:
        print('[FAIL] '+str(exc));return 1


if __name__=='__main__':raise SystemExit(main())
