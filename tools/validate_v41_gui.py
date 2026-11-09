"""Run actual native controls and paint-rate tests with a deliberately slow test worker.
No neural weights, identity recognition or physical camera accuracy are claimed.
"""
from __future__ import annotations
import os,sys,time,json,tempfile,traceback,multiprocessing,argparse
from pathlib import Path
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[key]='1'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--cpu-stress',action='store_true');parser.add_argument('--measure-seconds',type=int,default=15)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    import tkinter as tk
    from PIL import ImageGrab
    import psutil
    import vision_app.controller as module
    from vision_app.controller import Controller
    from vision_app.service import AnalysisService
    from vision_app.settings import AnalysisConfig
    from vision_app.ui import Window
    from vision_foundation.config import CameraConfig
    from tests.detection_workers import slow_worker,cpu_busy_worker
    # Dependency injection is confined to this validation script; production has no fake detector.
    module.AnalysisService=lambda *a,**kw:AnalysisService(*a,**kw,worker_target=cpu_busy_worker if args.cpu_stress else slow_worker)
    report={'scope':'Native Tk + synthetic 720p/30 capture + fixed 450 ms artificial inference delay. Not neural accuracy.',
            'errors':[],'checks':[],'samples':[]}
    if args.cpu_stress:report['scope']='Native Tk + 720p/30 synthetic capture + 450 ms actual OpenCV CPU blur work per analysis; NO neural model.'
    began=time.monotonic();stage=0;mark=began;last=began;beats=[];measuring=False;measure_start=None;initial=None
    with tempfile.TemporaryDirectory(prefix='vision-v41-gui-') as directory:
        app=Controller(Path(directory),Path(directory)/'models')
        app.configs.put(CameraConfig(id='gui',name='Teste 720p / análise artificial',kind='demo',source='demo',
            width=1280,height=720,publish_fps=30,jpeg_preview=False))
        app.settings.put('gui',AnalysisConfig(engine='regions'))
        root=tk.Tk();window=Window(root,app);window.refresh_sources('gui')
        window.root.title('Vision Local 4.1 — TESTE DE FLUIDEZ (sem câmera real)')
        def exception(exc,value,tb):
            report['errors'].append(''.join(traceback.format_exception(exc,value,tb)));window.close()
        root.report_callback_exception=exception
        def photo(name,target=root):
            target.update_idletasks()
            bbox=(target.winfo_rootx(),target.winfo_rooty(),target.winfo_rootx()+target.winfo_width(),target.winfo_rooty()+target.winfo_height())
            ImageGrab.grab(bbox=bbox).save(args.output/name)
        def pulse():
            nonlocal stage,mark,last,measuring,measure_start,initial
            now=time.monotonic();beats.append((now-last)*1000);last=now
            try:
                if now-began>args.measure_seconds+90:raise TimeoutError('Validation exceeded 100 seconds')
                ready=app.analysis and app.analysis.processed>=3 and app.preview and app.preview.latest()
                if stage==0 and ready and not window.busy:
                    # Warm start excluded from measurement.
                    measure_start=now;initial=(app.preview.frames,app.analysis.processed,window.painted_frames)
                    mark=now;stage=1;measuring=True
                elif stage==1:
                    if int((now-mark)*2)>len(report['samples']):
                        proc=psutil.Process();rss=proc.memory_info().rss
                        for child in proc.children(recursive=True):
                            try:rss+=child.memory_info().rss
                            except psutil.Error:pass
                        report['samples'].append({'seconds':now-mark,'rss_process_sum':rss,
                            'preview':app.preview.snapshot(),'analysis':app.analysis.snapshot()})
                    if now-mark>=args.measure_seconds:
                        elapsed=now-measure_start
                        report['benchmark']={'seconds':elapsed,'preview_prepared_fps':(app.preview.frames-initial[0])/elapsed,
                            'gui_painted_fps':(window.painted_frames-initial[2])/elapsed,
                            'analysis_fps':(app.analysis.processed-initial[1])/elapsed,
                            'preview':app.preview.snapshot(),'capture':app.camera.snapshot()}
                        assert report['benchmark']['gui_painted_fps']>18
                        assert report['benchmark']['gui_painted_fps']>report['benchmark']['analysis_fps']*4
                        photo('v41-ao-vivo.png');root.geometry('760x480');mark=now;stage=2
                elif stage==2 and now-mark>.5:
                    for button in window.buttons:
                        assert button.winfo_rootx()+button.winfo_width()<=root.winfo_rootx()+root.winfo_width()
                    photo('v41-compacta.png');root.geometry('1100x760')
                    window.analysis_dialog();mark=now;stage=3
                elif stage==3 and now-mark>.5:
                    dialog=window.controls;photo('v41-controles.png',dialog.root)
                    dialog.set_profile('people');dialog.preset('Menos alarmes')
                    original_pid=app.camera.snapshot()['worker_pid'];report['capture_pid_before']=original_pid
                    dialog.apply();stage=4
                elif stage==4 and not window.busy and not window.controls.root.winfo_exists():
                    assert app.settings.get('gui').classes=='people' and app.settings.get('gui').confidence==.7
                    assert app.camera.snapshot()['worker_pid']==report['capture_pid_before']
                    report['checks'].append('Basic controls apply without reconnecting camera; conservative profile persists')
                    window.toggle_analysis();stage=5
                elif stage==5 and not window.busy and app.analysis is None:
                    mark=now;initial=(app.preview.frames,window.painted_frames);stage=6
                elif stage==6 and now-mark>2:
                    assert app.preview.frames>initial[0]+20 and window.painted_frames>initial[1]+20
                    photo('v41-ia-pausada.png')
                    report['checks'].append('Pause AI leaves live source and GUI running')
                    window.photo();stage=7
                elif stage==7 and not window.busy and app.evidence.saved>0:
                    window.toggle_analysis();stage=8
                elif stage==8 and ready and not window.busy:
                    window.view_mode.set('analysis');window.change_view();mark=now;stage=9
                elif stage==9 and now-mark>1:
                    photo('v41-quadro-ia.png')
                    window.view_mode.set('live');window.change_view()
                    report['checks'].append('Analysis-frame view and raw live view switch; paused photo saved with NOT_ANALYZED marker')
                    window.stop();stage=10
                elif stage==10 and not window.busy and app.camera is None:
                    report['checks'].append('Native window closes workers cleanly')
                    stage=11;window.close()
                if not window.closed:root.after(15,pulse)
            except Exception:
                report['errors'].append(traceback.format_exc());window.close()
        root.after(100,window.start);root.after(15,pulse);root.mainloop();app.close()
    report['completed']=stage==11 and not report['errors'];report['seconds']=time.monotonic()-began
    beats.sort();report['callback_interval_ms']={'p95':beats[int(.95*(len(beats)-1))],'max':max(beats)}
    (args.output/'v41-native-gui.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='samples'},ensure_ascii=False,indent=2))
    return 0 if report['completed'] else 1

if __name__=='__main__':multiprocessing.freeze_support();raise SystemExit(main())
