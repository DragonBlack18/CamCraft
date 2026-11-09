"""Acquisition -> one in-flight inference -> temporal events -> latest display frame.

The parent retains the exact input frame while the isolated model executes. Boxes
are never painted on another frame. No cross-process Queue transports images.
"""
from __future__ import annotations
import multiprocessing as mp
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from .events import EventEngine
from .interactions import InteractionEngine, MESSAGES, MAJOR_EVENTS
from .object_registry import ObjectRegistry
from .inference import JsonSlot,inference_worker
from .model import MODEL_FILE
from .render import render
from .settings import AnalysisConfig
from .performance import PerformanceWindow,next_analysis_time
from vision_foundation.ipc import FrameSlot,StopFlag

@dataclass(frozen=True)
class AnalysisResult:
    id: int
    frame: object
    original: object
    tracks: list
    metadata: dict

class AnalysisService:
    def __init__(self,camera,store,evidence,cfg:AnalysisConfig,model_dir:Path,
                 *,worker_target=inference_worker,startup_timeout=45,registry=None):
        self.camera=camera;self.store=store;self.evidence=evidence;self.cfg=cfg.model_copy(deep=True)
        self.model_path=model_dir/MODEL_FILE;self.worker_target=worker_target;self.startup_timeout=startup_timeout
        self.ctx=mp.get_context('spawn');self.cancel=threading.Event();self.lock=threading.RLock()
        self.thread=None;self.process=None;self.stop_flag=None;self.input=None;self.reply=None
        self.state='STOPPED';self.reason='Pronto.';self.latest_result=None
        self.processed=0;self.stale_dropped=0;self.skipped=0;self.restarts=0;self.inference_ms=0.
        self.backend='';self.times=deque(maxlen=120);self.errors=0;self.event_count=0
        self.engine=None;self.last_context=None;self.last_uid=None;self.request=0
        self.registry=registry
        self.interactions=None;self.object_ms=0.
        self.performance=PerformanceWindow()

    def _state(self,state,reason):
        with self.lock:self.state=state;self.reason=reason

    def start(self):
        if self.thread and self.thread.is_alive():return
        self.cancel.clear();self.thread=threading.Thread(target=self._run,name='analysis-service',daemon=True)
        self.thread.start()

    def stop(self):
        self.cancel.set()
        if self.thread and self.thread is not threading.current_thread():self.thread.join(timeout=5)
        if self.thread and self.thread.is_alive():
            raise RuntimeError('A análise não encerrou no prazo; não inicie outra sessão.')
        with self.lock:self.latest_result=None
        self._state('STOPPED','Análise encerrada.')

    def _new_session(self,reason):
        self.engine=EventEngine(self.cfg)
        self.interactions=InteractionEngine(self.registry,self.camera.config,self.engine.session,self.cfg.roi,
            allow_association=self.cfg.engine=='yolox' and self.cfg.classes!='people') if self.registry else None
        self.last_context=None;self.last_uid=None
        with self.lock:self.latest_result=None
        self.store.emit(self.camera.config.id,'SESSAO_ANALISE','Nova sessão de acompanhamento: '+reason,
                        payload={'session':self.engine.session,'engine':self.cfg.engine})

    def _spawn(self):
        # Recreate buffers AND their locks; never reuse IPC held by a killed worker.
        self.input=FrameSlot(self.ctx,self.camera.config.raw_max_width,self.camera.config.raw_max_height)
        self.reply=JsonSlot(self.ctx);self.stop_flag=StopFlag(self.ctx)
        proc=self.ctx.Process(target=self.worker_target,args=(self.cfg.model_dump(),str(self.model_path),
            self.input,self.reply,self.stop_flag),name='vision-inference',daemon=True)
        with self.lock:self.process=proc
        proc.start()
        self._state('LOADING','Carregando o detector local...')

    def _dispose(self):
        with self.lock:proc=self.process
        if proc is None:return
        self.stop_flag.set();proc.join(timeout=.25)
        if proc.is_alive():proc.terminate();proc.join(timeout=.6)
        if proc.is_alive():proc.kill();proc.join(timeout=.6)
        if proc.is_alive():raise RuntimeError('Processo de análise não encerrou.')
        with self.lock:self.process=None
        proc.close()

    def _context(self,meta):
        return (int(meta['generation']),int(meta['loops']),int(meta['width']),int(meta['height']))

    def _accept(self,pending,reply):
        packet=pending['packet'];meta=packet.metadata;now=time.monotonic()
        live=self.camera.latest()
        if live is None or self._context(live.metadata)!=self._context(meta) or now-meta['received_monotonic']>self.cfg.max_frame_age:
            self.stale_dropped+=1
            self._state('LATE','Resultado descartado: quadro antigo ou fonte interrompida.')
            return
        context=self._context(meta)
        if context!=self.last_context:
            self._new_session('início, reconexão, repetição de arquivo ou mudança de resolução')
            self.last_context=context
        if self.last_uid is not None and self.last_uid[0]==context:
            self.skipped+=max(0,int(meta['sequence'])-self.last_uid[1]-1)
        self.last_uid=(context,int(meta['sequence']))
        tracks,events=self.engine.update(reply['detections'],meta['received_monotonic'],meta['received_utc'],packet.bgr.shape)
        objects=[];before_images={}
        if self.interactions:
            objects,object_events,before_images=self.interactions.update(packet.bgr,tracks,reply['detections'],
                meta['received_monotonic'],meta['received_utc'],int(meta['sequence']))
            events.extend(object_events);self.object_ms=self.interactions.last_ms
        render_begin=time.monotonic()
        annotated=render(packet.bgr,tracks,self.cfg,objects)
        render_ms=(time.monotonic()-render_begin)*1000
        self.processed+=1;self.inference_ms=float(reply['inference_ms']);self.backend=reply.get('backend','')
        now=time.monotonic();self.times.append(now)
        self.performance.record(inference_ms=self.inference_ms,object_ms=self.object_ms,render_ms=render_ms,age_ms=(now-meta['received_monotonic'])*1000)
        result_meta={**meta,'session':self.engine.session,'inference_ms':self.inference_ms,
            'engine':self.cfg.engine,'backend':self.backend,'accepted_monotonic':now,
            'result_age_ms':(now-meta['received_monotonic'])*1000,'tracks':tracks,
            'confidence_threshold':self.cfg.confidence,'roi':self.cfg.roi,'line':self.cfg.line,
            'objects':objects,'object_analysis_ms':round(self.object_ms,3),
            'raw_people':[d for d in reply['detections'] if d['class_id']==0]}
        if self.interactions and self.interactions.objects and self.interactions.config.clips and self.cfg.save_evidence:
            self.evidence.clips.offer(self.camera.config.id,annotated,result_meta)
        # One evidence pair per analyzed frame (not one full-frame copy for each detection).
        evidence_id=None
        visual_events=[e for e in events if e['code']!='RASTREAMENTO_PERDIDO']
        if visual_events and self.cfg.save_evidence:
            evidence_id=self.evidence.submit(self.camera.config.id,packet.bgr,annotated,result_meta,visual_events,
                before_images=before_images,make_clip=bool(self.interactions and self.interactions.config.clips
                    and any(e['code'] in MAJOR_EVENTS for e in visual_events)))
        for event in events:
            self.event_count+=1
            payload={**event,'sequence':int(meta['sequence']),'generation':int(meta['generation']),
                     'evidence_id':evidence_id if event in visual_events else None}
            messages={'PESSOA_OBSERVADA':'Pessoa confirmada por observações temporais.',
                'OBJETO_OBSERVADO':'Categoria de objeto confirmada por observações temporais.',
                'RASTREAMENTO_PERDIDO':'Rastreamento perdido; não comprova saída ou retirada.',
                'ENTRADA_LINHA':'Cruzamento na direção de entrada configurada.',
                'SAIDA_LINHA':'Cruzamento na direção de saída configurada.'}
            self.store.emit(self.camera.config.id,event['code'],messages.get(event['code'],MESSAGES.get(event['code'],'Evento do monitoramento de objetos.')),payload=payload)
        with self.lock:
            self.latest_result=AnalysisResult(self.processed,annotated,packet.bgr,tracks,result_meta)
        self._state('RUNNING','Detecção local ativa.')

    def _run(self):
        failures=0;last_metrics=0.
        try:
            while not self.cancel.is_set():
                self._spawn();self._new_session('detector iniciado')
                pending=None;last_sent=None;ready=False;began=time.monotonic();next_send=0.;last_good=began
                processed_at_start=self.processed
                failure=''
                while not self.cancel.wait(.01):
                    now=time.monotonic();reply=self.reply.get()
                    if reply and reply.get('state')=='ERROR':
                        failure='MODEL_ERROR'
                        self._state('ERROR',reply.get('message','Falha no detector.'))
                        break
                    if reply and reply.get('state') in ('READY','RESULT'):
                        ready=True;self.backend=reply.get('backend',self.backend)
                    if not self.process.is_alive():failure='WORKER_EXIT';break
                    if not ready and now-began>self.startup_timeout:failure='MODEL_LOAD_TIMEOUT';break
                    if pending is not None:
                        if reply and reply.get('state')=='RESULT' and reply.get('request')==pending['request']:
                            self._accept(pending,reply)
                            next_send=next_analysis_time(pending['sent'],time.monotonic(),self.cfg.max_fps,adaptive=self.cfg.adaptive_pacing,duty=self.cfg.duty_cycle)
                            pending=None
                            if self.state=='RUNNING':last_good=now
                        elif now-pending['sent']>self.cfg.watchdog_seconds:
                            failure='INFERENCE_TIMEOUT';break
                    if ready and pending is None and now>=next_send:
                        packet=self.camera.latest(raw=True)
                        if packet is None:
                            self._state('WAITING','Aguardando quadros atuais da câmera.')
                            if self.latest_result is not None and now-last_good>self.cfg.max_frame_age:
                                self._new_session('interrupção da fonte; nenhuma saída foi presumida')
                            continue
                        uid=(*self._context(packet.metadata),int(packet.metadata['sequence']))
                        if uid==last_sent:continue
                        if now-packet.metadata['received_monotonic']>self.cfg.max_frame_age:
                            self.stale_dropped+=1;last_sent=uid;continue
                        self.request+=1
                        job_meta={**packet.metadata,'sequence':self.request}
                        if self.input.publish(packet.bgr,b'',job_meta):
                            pending={'packet':packet,'request':self.request,'sent':now};last_sent=uid
                    if now-last_metrics>=10:
                        self.store.metric(self.camera.config.id,{'analysis':self.snapshot()})
                        last_metrics=now
                self._dispose()
                if self.cancel.is_set():break
                # A recovered worker that stayed productive is not an eternal crash streak.
                if time.monotonic()-began>=30 and self.processed-processed_at_start>=10:
                    failures=0
                failures+=1;self.errors+=1
                with self.lock:self.latest_result=None
                self.store.emit(self.camera.config.id,failure or 'ANALYSIS_FAILED','Análise interrompida; nenhum resultado antigo é tratado como atual.','ERROR')
                if failure=='MODEL_ERROR' or failures>=3:
                    self._state('ERROR','Detector indisponível. Pare, confira o modelo e exporte o diagnóstico.');break
                self.restarts+=1
                self._state('RECOVERING','Reiniciando o processo de análise com nova sessão de IDs.')
                self.cancel.wait(min(4,failures))
        except Exception as exc:
            self.errors+=1
            self._state('ERROR','Falha interna de análise ('+type(exc).__name__+'). Exporte o diagnóstico.')
            self.store.emit(self.camera.config.id,'ANALYSIS_EXCEPTION','Falha no coordenador de análise.','ERROR',{'exception_type':type(exc).__name__})
        finally:
            self._dispose()
            self.store.emit(self.camera.config.id,'SESSAO_ENCERRADA','Sessão de análise encerrada; não equivale à saída das pessoas.')
            if self.cancel.is_set():self._state('STOPPED','Análise encerrada.')

    def latest(self):
        with self.lock:result=self.latest_result
        if result is None:return None
        if time.monotonic()-result.metadata['received_monotonic']>self.cfg.max_frame_age:return None
        return result

    def snapshot(self):
        with self.lock:
            r=self.latest_result
            times=list(self.times)
            fps=(len(times)-1)/(times[-1]-times[0]) if len(times)>1 and times[-1]>times[0] else 0
            return {'state':self.state,'reason':self.reason,'backend':self.backend,'processed':self.processed,
                'inference_ms':round(self.inference_ms,2),'analysis_fps':round(fps,2),
                'age_ms':round((time.monotonic()-r.metadata['received_monotonic'])*1000,1) if r else None,
                'stale_dropped':self.stale_dropped,'skipped_capture_frames':self.skipped,
                'restarts':self.restarts,'errors':self.errors,'events':self.event_count,
                'worker_pid':self.process.pid if self.process else None,
                'confirmed_visible':sum(bool(t['confirmed']) for t in r.tracks) if r and time.monotonic()-r.metadata['received_monotonic']<=self.cfg.max_frame_age else 0,
                'session':self.engine.session if self.engine else None,
                'objects':r.metadata.get('objects',[]) if r else [],'object_analysis_ms':round(self.object_ms,2),
                'object_load_errors':self.interactions.load_errors if self.interactions else [],
                'performance':self.performance.snapshot(),'adaptive_pacing':self.cfg.adaptive_pacing,
                'thread_alive':bool(self.thread and self.thread.is_alive())}
