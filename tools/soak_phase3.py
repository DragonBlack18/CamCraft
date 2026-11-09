"""Real video capture + reference-only inference process + eight object slots.

Uses generated footage. Does not measure neural recognition accuracy/performance.
"""
from __future__ import annotations
import argparse,json,multiprocessing,os,sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ.setdefault(key,'1')


def main():
    p=argparse.ArgumentParser();p.add_argument('--seconds',type=int,default=45);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    import cv2,numpy as np,psutil
    from tests.test_interactions import images
    from vision_app.controller import Controller
    from vision_app.settings import AnalysisConfig
    from vision_foundation.config import CameraConfig
    empty,_=images();present=empty.copy();rois=[]
    for row in range(2):
        for col in range(4):
            x=50+col*140;y=60+row*160;w=65;h=75
            present[y:y+h,x:x+w]=(35,60,220)
            cv2.rectangle(present,(x+7,y+7),(x+w-8,y+h-8),(220,180,40),3)
            cv2.line(present,(x+8,y+h-10),(x+w-10,y+8),(20,230,230),4)
            rois.append((x/640,y/360,(x+w)/640,(y+h)/360))
    report={'scope':'Generated AVI / real file capture / reference-only production mode / 8 calibrated objects. No YOLOX or physical camera.'}
    with tempfile.TemporaryDirectory(prefix='phase3_soak_') as td:
        root=Path(td);video=root/'sequence.avi'
        writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'MJPG'),15,(640,360))
        if not writer.isOpened():raise RuntimeError('No MJPG encoder')
        for i in range(15*12):writer.write(present if i<60 or i>=120 else empty)
        writer.release()
        app=Controller(root/'data',Path(__file__).resolve().parents[1]/'models')
        cfg=CameraConfig(id='load',name='8 objetos / ensaio controlado',kind='file',source=str(video),width=640,height=360,raw_max_width=640,raw_max_height=360,loop=True)
        app.configs.put(cfg);app.settings.put(cfg.id,AnalysisConfig(engine='regions',max_fps=10))
        for i,roi in enumerate(rois):
            only_empty=present.copy();x1,y1,x2,y2=[round(v*(640 if j%2==0 else 360)) for j,v in enumerate(roi)]
            only_empty[y1:y2,x1:x2]=empty[y1:y2,x1:x2]
            app.objects.create(cfg,f'Objeto {i+1}',roi,only_empty,present)
        samples=[];killed=False;start=time.monotonic();proc=psutil.Process()
        try:
            app.start(cfg.id)
            while time.monotonic()-start<args.seconds:
                time.sleep(.2);elapsed=time.monotonic()-start
                if not killed and elapsed>args.seconds/2 and app.analysis.process:
                    app.analysis.process.kill();killed=True
                s=app.analysis.snapshot();rss=proc.memory_info().rss
                for child in proc.children(recursive=True):
                    try:rss+=child.memory_info().rss
                    except psutil.Error:pass
                samples.append({'elapsed':elapsed,'rss_sum':rss,**s})
                if s['state']=='ERROR':break
            app.stop();app.evidence.flush();app.evidence.clips.flush(5);app.events.flush()
            records=app.events.events(limit=1000)
            report.update(seconds=time.monotonic()-start,samples=samples,injected_worker_failure=killed,
                evidence=app.evidence.health(),storage=app.events.health(),
                event_counts={c:sum(e['code']==c for e in records) for c in sorted({r['code'] for r in records})})
            running=[s for s in samples if s['state']=='RUNNING']
            report['summary']={'processed':samples[-1]['processed'],'restarts':samples[-1]['restarts'],
                'peak_rss_sum_mib':max(s['rss_sum'] for s in samples)/1024**2,
                'object_ms_p95':float(np.percentile([s['object_analysis_ms'] for s in running],95)),
                'age_after_decode_ms_p95':float(np.percentile([s['age_ms'] for s in running if s['age_ms'] is not None],95)),
                'median_analysis_fps':float(np.median([s['analysis_fps'] for s in running]))}
            report['passed']=bool(report['summary']['processed']>100 and report['summary']['restarts']==1 and
                report['storage']['healthy'] and app.evidence.failures==0 and app.evidence.clips.failed==0 and
                report['event_counts'].get('AUSENCIA_CONFIRMADA',0)>=8 and report['event_counts'].get('RETORNO_OBSERVADO',0)>=8)
        finally:app.close()
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='samples'},indent=2,ensure_ascii=False))
    return 0 if report.get('passed') else 1
if __name__=='__main__':multiprocessing.freeze_support();raise SystemExit(main())
