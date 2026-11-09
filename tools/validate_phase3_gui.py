"""Native-window integration using a generated AVI + REAL HOG (not neural accuracy)."""
from __future__ import annotations
import argparse,json,multiprocessing,os,sys,tempfile,time,traceback
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ.setdefault(key,'1')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    import cv2
    import tkinter as tk
    from PIL import ImageGrab
    from vision_app.controller import Controller
    from vision_app.ui import Window
    from vision_app.object_ui import calibration
    from vision_app.settings import AnalysisConfig
    from vision_foundation.config import CameraConfig
    from tests.test_interactions import images,ROI
    report={'scope':'Native Tk + generated video/real file decoder + real HOG + real reference engine. No YOLOX or physical camera.',
            'checks':[],'errors':[]};stage=0;pause=0;start=time.monotonic();last=start;beats=[]
    with tempfile.TemporaryDirectory(prefix='vision3_gui_') as td:
        directory=Path(td);path=directory/'scene.avi';empty,present=images()
        writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'MJPG'),12,(640,360))
        if not writer.isOpened():raise RuntimeError('Test video encoder unavailable')
        for i in range(12*20):writer.write(empty if i<48 or 108<=i<156 else present)
        writer.release()
        app=Controller(directory/'data',Path(__file__).resolve().parents[1]/'models')
        app.configs.put(CameraConfig(id='gui3',name='VALIDAÇÃO CONTROLADA — arquivo / HOG',kind='file',source=str(path),loop=True,width=640,height=360,raw_max_width=640,raw_max_height=360))
        app.settings.put('gui3',AnalysisConfig(engine='hog',max_fps=10))
        root=tk.Tk();window=Window(root,app);window.refresh_sources('gui3')
        dialog=None;controls=None
        def fail(exc,value,tb):
            report['errors'].append(''.join(traceback.format_exception(exc,value,tb)));window.close()
        root.report_callback_exception=fail
        def photo(name):
            root.update_idletasks()
            ImageGrab.grab(bbox=(root.winfo_rootx(),root.winfo_rooty(),root.winfo_rootx()+root.winfo_width(),root.winfo_rooty()+root.winfo_height())).save(args.output/name)
        def pulse():
            nonlocal stage,pause,last,dialog,controls
            now=time.monotonic();beats.append(now-last);last=now
            try:
                if now-start>50:raise TimeoutError('Native workflow timeout')
                result=app.analysis.latest() if app.analysis else None
                ready=result is not None and not window.busy
                if stage==0 and ready:
                    assert result.original[170,220,2]<160 # empty reference
                    dialog,controls=calibration(window,ROI,result)
                    controls['name'].set('Objeto de teste local');controls['category'].set('garrafa [39]')
                    # Category display strings may be localized; use available exact label.
                    from vision_app.classes import NAMES
                    controls['category'].set(f'{NAMES[39]} [39]')
                    stage=1
                elif stage==1 and ready and result.original[170,220,2]>180:
                    controls['save']();stage=2
                elif stage==2 and ready and app.objects.all('gui3'):
                    report['checks'].append('native calibration captures occupied reference and persists registry; analysis restarts')
                    stage=3
                elif stage==3 and ready and result.metadata.get('objects') and result.metadata['objects'][0]['state']=='PRESENTE':
                    photo('fase3-janela.png');root.geometry('800x560');pause=now;stage=4
                elif stage==4 and now-pause>.6:
                    for button in window.buttons:
                        assert button.winfo_width()>30
                        assert button.winfo_rootx()+button.winfo_width()<=root.winfo_rootx()+root.winfo_width()
                    photo('fase3-compacta.png');root.geometry('1100x760')
                    report['checks'].append('main camera view at 1100x760 and 800x560; primary controls inside window')
                    stage=5
                elif stage==5 and ready:
                    rows=app.events.events(limit=1000);codes=[r['code'] for r in rows]
                    if 'AUSENCIA_CONFIRMADA' in codes and codes.count('RETORNO_OBSERVADO')>=2 and app.evidence.clips.saved>=2:
                        report['checks'].append('real file playback generated absence and two observed returns; automatic clips saved')
                        window.history();pause=now;stage=6
                elif stage==6 and now-pause>.5:
                    assert window.history_tree.get_children()
                    window.history_window.destroy()
                    dlg,tree=window.object_manager();assert tree.get_children()
                    dlg.destroy();report['checks'].append('native event history and object manager populated')
                    photo('fase3-retorno.png')
                    app.events.flush();report['events']=[{'code':r['code'],'payload':r['payload']} for r in app.events.events(limit=1000)]
                    report['analysis']=app.analysis.snapshot();report['evidence']=app.evidence.health()
                    app.export_csv(args.output/'fase3-gui-eventos.csv')
                    app.diagnostic(args.output/'fase3-gui-diagnostico.zip')
                    report['checks'].append('CSV and diagnostic export work with object metadata')
                    window.stop();stage=7
                elif stage==7 and not window.busy and app.camera is None:
                    report['checks'].append('stop closes detector/capture without freezing native UI');stage=8;window.close()
                if not window.closed:root.after(30,pulse)
            except Exception:
                report['errors'].append(traceback.format_exc());window.close()
        root.after(100,window.start);root.after(30,pulse)
        root.mainloop();app.close()
    report['completed']=stage==8 and not report['errors'];report['seconds']=time.monotonic()-start
    beats.sort();report['ui_heartbeat_ms']={'p95':beats[int(.95*(len(beats)-1))]*1000,'max':max(beats)*1000}
    (args.output/'fase3-gui.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2));return 0 if report['completed'] else 1

if __name__=='__main__':multiprocessing.freeze_support();raise SystemExit(main())
