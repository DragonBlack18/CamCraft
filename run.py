"""Desktop entrypoint. No HTTP server, dashboard, browser, API keys, or telemetry."""
from __future__ import annotations
import argparse
import json
import multiprocessing
import os
import signal
import sys
import time
from pathlib import Path
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
    os.environ.setdefault(key,'1')

def main(argv=None):
    from vision_app.runtime import resource_root, default_data_dir, APP_NAME, VERSION, is_frozen
    root_dir=resource_root()
    p=argparse.ArgumentParser(description=APP_NAME+' '+VERSION+' — câmera e detecção')
    p.add_argument('--data-dir',type=Path,default=default_data_dir())
    p.add_argument('--model-dir',type=Path,default=root_dir/'models')
    p.add_argument('--camera-id',default=None)
    p.add_argument('--demo',action='store_true',help='Fonte sintética; NÃO simula reconhecimento de pessoas.')
    p.add_argument('--camera-only',action='store_true',help='Vídeo fluido sem IA; pode ativar a IA nos controles.')
    mode=p.add_mutually_exclusive_group()
    mode.add_argument('--hog',action='store_true',help='Diagnóstico explícito de pedestres, sem modelo YOLOX.')
    mode.add_argument('--regions',action='store_true',help='Somente referências de objetos cadastrados; não detecta pessoas.')
    p.add_argument('--headless',action='store_true')
    p.add_argument('--seconds',type=int,default=30)
    args=p.parse_args(argv)
    if args.seconds<1:p.error('--seconds deve ser positivo.')
    from vision_app.instance import InstanceLock
    import cv2
    cv2.setNumThreads(1)
    cv2.ocl.setUseOpenCL(False)
    from vision_app.controller import Controller
    from vision_foundation.config import CameraConfig
    lock=None;app=None
    try:
        lock=InstanceLock(args.data_dir);app=Controller(args.data_dir,args.model_dir)
        cid=args.camera_id or app.configs.all()[0].id
        if args.demo:
            cid='demo';app.configs.put(CameraConfig(id=cid,name='Teste de captura — sem pessoas',kind='demo',source='demo',width=640,height=480,raw_max_width=1280,raw_max_height=720))
        if args.hog or args.regions:
            cfg=app.settings.get(cid);cfg.engine='regions' if args.regions else 'hog';app.settings.put(cid,cfg)
        if args.headless:
            app.start(cid, analyze=not args.camera_only);begin=time.monotonic();interrupted=False
            samples=[]
            try:
                import psutil
                proc=psutil.Process()
                while time.monotonic()-begin<args.seconds:
                    time.sleep(.2)
                    if app.analysis:
                        s=app.analysis.snapshot()
                        rss=proc.memory_info().rss
                        for child in proc.children(recursive=True):
                            try:rss+=child.memory_info().rss
                            except psutil.Error:pass
                        samples.append({'elapsed_s':round(time.monotonic()-begin,2),'rss_total':rss,**s})
                        if s['state']=='ERROR':break
            except KeyboardInterrupt:interrupted=True
            report={'analysis':app.analysis.snapshot() if app.analysis else None,'preview':app.preview.snapshot() if app.preview else None,'camera':app.camera.snapshot(),'storage':app.events.health(),
                    'evidence':app.evidence.health(),'seconds':time.monotonic()-begin,'samples':samples,'interrupted':interrupted,
                    'note':'RSS soma processos e pode contar memória compartilhada mais de uma vez. Idade após decodificação, não sensor→tela.'}
            directory=args.data_dir/'reports';directory.mkdir(exist_ok=True)
            path=directory/'headless.json';path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            ok=(report['analysis']['processed']>0 and report['analysis']['state']!='ERROR') if report['analysis'] else bool(report['preview'] and report['preview']['frames']>0)
            print(('[PASS]' if ok else '[FAIL]')+' Execução local. Relatório: '+str(path))
            return 0 if ok else 1
        import tkinter as tk
        from vision_app.ui import Window
        root=tk.Tk();window=Window(root,app);window.refresh_sources(cid)
        window.start_without_analysis=args.camera_only
        if args.demo:root.after(300,window.start)
        def sigint(_sig,_frame):root.after(0,window.close)
        signal.signal(signal.SIGINT,sigint)
        root.mainloop();return 0
    except Exception as exc:
        message='Inicialização não concluída ('+type(exc).__name__+'): '+str(exc)
        print('[FAIL] '+message)
        if is_frozen() and not args.headless:
            try:
                import tkinter.messagebox
                tkinter.messagebox.showerror(APP_NAME, message+'\n\nDados preservados. Verifique permissões da pasta e se outra instância está aberta.')
            except Exception: pass
        return 1
    finally:
        if app:
            try:app.close()
            except Exception:print('[WARN] Encerramento parcial; revise os processos antes de abrir outra instância.')
        if lock:lock.close()

if __name__=='__main__':
    multiprocessing.freeze_support()
    raise SystemExit(main())
