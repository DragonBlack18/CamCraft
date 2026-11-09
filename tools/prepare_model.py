"""Download/verify the exact model and run a real local neural-network smoke test."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse,json,time
import numpy as np
from vision_app.model import ensure_model,MODEL_SHA256
from vision_app.detector import YoloXDetector
from vision_app.settings import AnalysisConfig

def main():
    p=argparse.ArgumentParser();p.add_argument('--offline',action='store_true');p.add_argument('--no-smoke',action='store_true');p.add_argument('--directory',type=Path,default=Path(__file__).resolve().parents[1]/'models');args=p.parse_args()
    try:
        path=ensure_model(args.directory,lambda s:print('[INFO] '+s,flush=True),allow_download=not args.offline)
        if not args.no_smoke:
            model=YoloXDetector(path,AnalysisConfig());start=time.monotonic();rows=model.detect(np.full((480,640,3),114,np.uint8));ms=(time.monotonic()-start)*1000
            print(f'[PASS] Modelo carregado e inferência executada: {ms:.0f} ms. Teste de execução, não medição de acurácia.')
            report={'sha256':MODEL_SHA256,'neural_inference_executed':True,'inference_ms':ms,'detections_on_neutral_frame':len(rows),'accuracy_measured':False}
            target=Path(__file__).resolve().parents[1]/'data'/'reports';target.mkdir(parents=True,exist_ok=True)
            (target/'model-smoke.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print('[PASS] Modelo pronto.');return 0
    except Exception as exc:print('[FAIL] '+str(exc));return 1
if __name__=='__main__':raise SystemExit(main())
