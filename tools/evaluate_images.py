"""Evaluate labeled local images. See docs/AVALIACAO_REAL.md for the annotation contract."""
from pathlib import Path
import argparse,json,sys,time,math
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--model-dir',type=Path,default=Path(__file__).resolve().parents[1]/'models')
    p.add_argument('--confidence',type=float,default=.45);p.add_argument('--iou',type=float,default=.5)
    a=p.parse_args()
    try:
        import cv2,numpy as np
        from vision_app.detector import YoloXDetector
        from vision_app.model import MODEL_FILE,MODEL_SHA256
        from vision_app.settings import AnalysisConfig
        from vision_app.evaluation import match_frame,summarize
        from vision_app.classes import NAMES
        data=json.loads(a.manifest.read_text(encoding='utf-8'))
        if data.get('fully_labeled') is not True:raise ValueError('Confirme fully_labeled=true somente com todas as classes de interesse anotadas.')
        rows=data.get('images',[]);classes=data.get('class_ids',[0])
        if not rows or len(rows)>10000:raise ValueError('Use entre 1 e 10.000 imagens rotuladas.')
        if not classes or not all(isinstance(c,int) and 0<=c<80 for c in classes):raise ValueError('class_ids inválidos.')
        if not 0<a.iou<=1:raise ValueError('IoU deve estar entre 0 (exclusivo) e 1.')
        detector=YoloXDetector(a.model_dir/MODEL_FILE,AnalysisConfig(confidence=a.confidence,classes='custom',custom_classes=classes))
        stats=[];per_image=[];seen=set();inference=[]
        for row in rows:
            path=(a.manifest.parent/row['image']).resolve()
            if str(path) in seen:raise ValueError('Imagem duplicada no manifesto.')
            seen.add(str(path))
            frame=cv2.imdecode(np.fromfile(path,dtype=np.uint8),cv2.IMREAD_COLOR)
            if frame is None:raise ValueError('Imagem não pôde ser decodificada: '+path.name)
            truth=row.get('objects');h,w=frame.shape[:2]
            if not isinstance(truth,list):raise ValueError('objects precisa ser uma lista; [] significa imagem negativa anotada.')
            for item in truth:
                b=item['box'];cid=item['class_id']
                if cid not in classes:raise ValueError('Classe anotada fora de class_ids.')
                if len(b)!=4 or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in b):raise ValueError('Caixa inválida.')
                if not 0<=b[0]<b[2]<=w or not 0<=b[1]<b[3]<=h:raise ValueError('Caixa fora da imagem.')
            start=time.perf_counter();pred=detector.detect(frame);inference.append((time.perf_counter()-start)*1000)
            pred=[d for d in pred if d['class_id'] in classes and d['score']>=a.confidence]
            result=match_frame(pred,truth,a.iou);stats.append(result)
            per_image.append({'image':row['image'],'counts':result,'predictions':pred})
        report={'scope':'Detection at fixed threshold; not tracking, event accuracy, COCO mAP or calibrated confidence.',
                'model_sha256':MODEL_SHA256,'detector_config':detector.cfg.model_dump(),'confidence':a.confidence,'iou':a.iou,'class_ids':classes,
                'class_names':{str(c):NAMES[c] for c in classes},'images':len(rows),**summarize(stats),
                'inference_ms':{'median':float(np.median(inference)),'p95':float(np.percentile(inference,95))},'per_image':per_image}
        a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print('[PASS] Avaliação gravada: '+str(a.output));print(json.dumps(report['overall'],indent=2));return 0
    except Exception as exc:print('[FAIL] Avaliação não concluída: '+str(exc));return 1
if __name__=='__main__':raise SystemExit(main())
