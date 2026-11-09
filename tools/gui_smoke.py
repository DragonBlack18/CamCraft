"""Exercise the actual native window. Synthetic source + real HOG, NOT YOLOX accuracy.
Linux headless: run with DISPLAY=:99 and an Xvfb server. Requires a graphical session.
"""
from __future__ import annotations
import argparse,json,os,sys,time,tempfile,multiprocessing,traceback
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ.setdefault(key,'1')

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    import tkinter as tk
    from PIL import ImageGrab
    from types import SimpleNamespace
    from vision_app.controller import Controller
    from vision_app.ui import Window
    from vision_app.settings import AnalysisConfig
    from vision_foundation.config import CameraConfig
    report={'scope':'Actual Tk window / real HOG / synthetic capture. No neural model or camera hardware tested.', 'checks':[], 'errors':[]}
    heartbeats=[];start=time.monotonic();last=start;stage=0;pause=0
    with tempfile.TemporaryDirectory(prefix='vision_gui_') as data:
        app=Controller(Path(data),Path(__file__).resolve().parents[1]/'models')
        app.configs.put(CameraConfig(id='smoke',name='Teste de captura — SEM PESSOAS',kind='demo',source='demo',width=640,height=480,raw_max_width=640,raw_max_height=480))
        app.settings.put('smoke',AnalysisConfig(engine='hog'))
        root=tk.Tk();w=Window(root,app);w.refresh_sources('smoke')
        def error(exc,val,tb):
            report['errors'].append(''.join(traceback.format_exception(exc,val,tb)));w.close()
        root.report_callback_exception=error
        def photo(name):
            bbox=(root.winfo_rootx(),root.winfo_rooty(),root.winfo_rootx()+root.winfo_width(),root.winfo_rooty()+root.winfo_height())
            ImageGrab.grab(bbox=bbox).save(args.output/name)
        def geometry(mode,p1,p2):
            w.select_geometry(mode)
            a,b,width,height=w.display_bounds
            w.mouse_down(SimpleNamespace(x=a+p1[0]*width,y=b+p1[1]*height))
            w.mouse_up(SimpleNamespace(x=a+p2[0]*width,y=b+p2[1]*height))
        def pulse():
            nonlocal stage,pause,last
            now=time.monotonic();heartbeats.append(now-last);last=now
            try:
                if now-start>55:raise TimeoutError('GUI workflow exceeded timeout')
                ready=app.analysis and app.analysis.processed>=5 and app.analysis.latest() is not None
                if stage==0 and ready and not w.busy:
                    report['checks'].append('native video renders coherent analyzed frame');w.photo();stage=1
                elif stage==1 and app.evidence.saved>=1 and not w.busy:
                    report['checks'].append('manual evidence written');w.task(lambda:(app.export_csv(args.output/'gui-events.csv'),app.diagnostic(args.output/'gui-diagnostic.zip')));stage=2
                elif stage==2 and not w.busy:
                    photo('janela-desktop.png');root.geometry('800x560');pause=now;stage=3
                elif stage==3 and now-pause>.6:
                    
                    for button in w.buttons:
                        assert button.winfo_width()>40 and button.winfo_rootx()+button.winfo_width()<=root.winfo_rootx()+root.winfo_width()
                    photo('janela-compacta.png');report['checks'].append('800x560 and 1100x760 rendered; all toolbar buttons fit');root.geometry('1100x760');pause=now;stage=4
                elif stage==4 and now-pause>.5 and ready and not w.busy:
                    geometry('roi',(.1,.1),(.9,.9));stage=5
                elif stage==5 and ready and not w.busy:
                    assert app.settings.get('smoke').roi is not None
                    report['checks'].append('mouse ROI persists and restarts analysis');geometry('line',(.2,.5),(.8,.5));stage=6
                elif stage==6 and ready and not w.busy:
                    assert app.settings.get('smoke').line is not None
                    report['checks'].append('mouse line persists and restarts analysis');photo('janela-configurada.png');w.history();pause=now;stage=7
                elif stage==7 and now-pause>.8:
                    assert len(w.history_tree.get_children())>0
                    report['checks'].append('history populated from actual SQLite events');w.history_window.destroy();w.stop();stage=8
                elif stage==8 and not w.busy and app.camera is None:
                    assert app.analysis is None
                    report['checks'].append('stop releases analysis and capture');w.start();stage=9
                elif stage==9 and ready and not w.busy:
                    report['checks'].append('start after stop recovers preview');report['analysis']=app.analysis.snapshot();report['camera']=app.camera.snapshot();stage=10;w.close()
                if not w.closed:root.after(20,pulse)
            except Exception:
                report['errors'].append(traceback.format_exc());w.close()
        root.after(100,w.start);root.after(20,pulse)
        root.mainloop();app.close()
    report['completed']=stage==10 and not report['errors'];report['seconds']=time.monotonic()-start
    heartbeats.sort();report['heartbeat_ms']={'p95':heartbeats[int(.95*(len(heartbeats)-1))]*1000,'max':max(heartbeats)*1000}
    (args.output/'gui-smoke.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2));return 0 if report['completed'] else 1
if __name__=='__main__':multiprocessing.freeze_support();raise SystemExit(main())
