"""Native Tk integration: generated video, real capture/reference engine, review and annotation."""
from __future__ import annotations
import argparse,json,multiprocessing,os,sys,tempfile,time,traceback
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ.setdefault(key,'1')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    import cv2,numpy as np,tkinter as tk
    from PIL import ImageGrab
    from vision_app.controller import Controller
    from vision_app.ui import Window
    from vision_app.review_ui import DetailWindow
    from vision_app.dataset_ui import DatasetWindow
    from vision_app.settings import AnalysisConfig
    from vision_foundation.config import CameraConfig
    from tests.test_interactions import images,ROI
    report={'scope':'Native Tk / generated AVI / real OpenCV decoding / production reference-only mode. NO YOLOX or physical camera.',
            'checks':[],'errors':[]};stage=0;pause=0;start=time.monotonic();last=start;beats=[]
    details=annotator=None;row=None;selected_eid=None
    with tempfile.TemporaryDirectory(prefix='vision4_gui_') as temp:
        directory=Path(temp);video=directory/'scene.avi';empty,present=images()
        writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'MJPG'),12,(640,360))
        if not writer.isOpened():raise RuntimeError('Encoder unavailable')
        for i in range(12*16):writer.write(present if i<60 or i>=120 else empty)
        writer.release()
        app=Controller(directory/'data',Path(__file__).resolve().parents[1]/'models')
        config=CameraConfig(id='gui4',name='TESTE LOCAL — vídeo gerado / referências',kind='file',source=str(video),loop=True,width=640,height=360,raw_max_width=640,raw_max_height=360)
        app.configs.put(config);app.settings.put(config.id,AnalysisConfig(engine='regions',max_fps=10))
        app.objects.create(config,'Objeto de validação',ROI,empty,present)
        root=tk.Tk();window=Window(root,app);window.refresh_sources(config.id)
        def photo(widget,name):
            widget.lift();widget.update_idletasks()
            ImageGrab.grab(bbox=(widget.winfo_rootx(),widget.winfo_rooty(),widget.winfo_rootx()+widget.winfo_width(),widget.winfo_rooty()+widget.winfo_height())).save(args.output/name)
        def fail(exc,value,tb):
            report['errors'].append(''.join(traceback.format_exception(exc,value,tb)));window.close()
        root.report_callback_exception=fail
        def pulse():
            nonlocal stage,pause,last,details,annotator,row,selected_eid
            now=time.monotonic();beats.append(now-last);last=now
            try:
                if now-start>90:raise TimeoutError('GUI workflow timeout at stage '+str(stage))
                result=app.analysis.latest() if app.analysis else None
                ready=result is not None and not window.busy
                if stage==0 and ready and result.metadata.get('objects'):
                    if result.metadata['objects'][0]['state']=='PRESENTE':
                        photo(root,'fase4-camera.png');root.geometry('800x560');pause=now;stage=1
                elif stage==1 and now-pause>.6:
                    for button in window.buttons:
                        assert button.winfo_rootx()+button.winfo_width()<=root.winfo_rootx()+root.winfo_width()
                    photo(root,'fase4-compacta.png');root.geometry('1100x760')
                    report['checks'].append('Main camera window at 1100x760 and 800x560; controls fit')
                    stage=2
                elif stage==2 and ready:
                    rows=app.events.events(limit=1000)
                    candidates=[r for r in rows if r['code']=='AUSENCIA_CONFIRMADA' and r['payload'].get('evidence_id')]
                    if candidates and app.evidence.clips.saved>0:
                        row=candidates[0];selected_eid=row['payload']['evidence_id']
                        if app.evidence_review.inspect(selected_eid)['state']=='VERIFIED':
                            window.history();stage=3
                elif stage==3 and not window.busy and window.history_tree.get_children():
                    photo(window.history_window,'fase4-registros.png')
                    report['checks'].append('History browser loads filtered, paginated real events')
                    details=DetailWindow(window,row);stage=4
                elif stage==4 and not window.busy and details.report:
                    assert details.report['state']=='VERIFIED'
                    assert len(details.images)>=2
                    photo(details.root,'fase4-evidencias.png')
                    details.note.set('Teste automatizado: ausência observada em vídeo gerado, sem atribuição a pessoas.')
                    details.review('INCONCLUSIVO');stage=5
                elif stage==5 and not window.busy:
                    assert app.reviews.reviews(row['id'])[-1]['decision']=='INCONCLUSIVO'
                    assert 'INCONCLUSIVO' in details.data.get('1.0','end')
                    assert len(details.notebook.tabs())==len(details.images)+1
                    details.preserve(True);stage=6
                elif stage==6 and not window.busy:
                    assert app.evidence_review.inspect(selected_eid)['preserved']
                    assert len(details.notebook.tabs())==len(details.images)+1
                    app.evidence_review.export_incident(row['id'],args.output/'gui-ocorrencia.zip')
                    report['checks'].append('Before/after images verified; review with note and preservation persisted; incident export verified')
                    details.root.destroy();window.history_window.destroy()
                    annotator=DatasetWindow(window);stage=7
                elif stage==7 and ready and result.metadata.get('objects') and result.metadata['objects'][0]['state']=='PRESENTE':
                    annotator.capture();stage=8
                elif stage==8 and not window.busy and annotator.row is not None:
                    # Real native mouse events; add a box in original frame coordinates.
                    annotator.root.update_idletasks();annotator.draw()
                    x,y,sx,sy=annotator.bounds
                    annotator.category.set('garrafa [39]')
                    for evt,a,b in [('<ButtonPress-1>',192,126),('<B1-Motion>',256,216),('<ButtonRelease-1>',256,216)]:
                        annotator.canvas.event_generate(evt,x=int(x+a*sx),y=int(y+b*sy))
                    assert len(annotator.boxes)==1
                    annotator.scope.set('39');annotator.complete.set(True)
                    photo(annotator.root,'fase4-anotacao.png')
                    annotator.save();stage=9
                elif stage==9 and not window.busy:
                    rows=app.dataset.list();assert len(rows)==1 and rows[0]['state']=='LABELED'
                    app.dataset.export(args.output/'gui-amostras.zip',split=False)
                    report['checks'].append('Sample capture, native mouse rectangle, human confirmation, annotation persistence and dataset export')
                    annotator.root.destroy();window.stop();stage=10
                elif stage==10 and not window.busy and app.camera is None:
                    app.backup(args.output/'gui-backup.zip')
                    from vision_app.backup import restore_backup
                    restore_backup(args.output/'gui-backup.zip',directory/'restored')
                    clone=Controller(directory/'restored',directory/'models')
                    try:
                        assert len(clone.dataset.list())==1
                        assert clone.reviews.verify_chain()['verified_records']==1
                        assert clone.evidence_review.inspect(selected_eid)['preserved']
                    finally:clone.close()
                    report['checks'].append('Stop, full backup, verified restore into a fresh folder and reload of reviews/images/dataset')
                    report['integrity']=app.integrity();stage=11;window.close()
                if not window.closed:root.after(40,pulse)
            except Exception:
                report['errors'].append(traceback.format_exc());window.close()
        root.after(100,window.start);root.after(40,pulse)
        root.mainloop();app.close()
    report['completed']=stage==11 and not report['errors'];report['seconds']=time.monotonic()-start
    beats.sort();report['ui_heartbeat_ms']={'p95':beats[int(.95*(len(beats)-1))]*1000,'max':max(beats)*1000}
    (args.output/'native-gui.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2));return 0 if report['completed'] else 1

if __name__=='__main__':multiprocessing.freeze_support();raise SystemExit(main())
