"""Bounded sampled evidence clips: 6 s pre-event + up to 2 s post-event.

This is diagnostic sampling, NOT continuous CCTV or original sensor footage.
JPEG/AVI encoding and disk writes run only in this worker. Timings are explicit.
"""
from __future__ import annotations
from collections import deque
import hashlib
import json
import os
import queue
import threading
import time
from pathlib import Path

import cv2
import numpy as np

from .object_registry import atomic_json


class ClipRecorder:
    def __init__(self, directory: Path, store, *,sample_fps=3,pre_seconds=6,post_seconds=2,max_pending=3,access_lock=None):
        self.directory=directory;self.store=store
        self.access_lock=access_lock or threading.RLock()
        self.sample_fps=sample_fps;self.pre_seconds=pre_seconds;self.post_seconds=post_seconds
        self.max_pending=max_pending;self.max_bytes=8*1024**2
        self.frames=queue.Queue(maxsize=2);self.requests=queue.Queue(maxsize=max_pending)
        self.cancel=threading.Event();self.ring=deque(maxlen=32);self.active=[]
        self.context=None;self.last_offer=-1e9;self.lock=threading.Lock()
        self.saved=0;self.failed=0;self.dropped_samples=0;self.dropped_requests=0;self.last_error=''
        self.thread=threading.Thread(target=self._run,name='event-clips',daemon=True);self.thread.start()

    def offer(self,camera_id,frame,metadata):
        if self.cancel.is_set():return
        stamp=float(metadata['received_monotonic'])
        # A session switch must accept its first frame even on a different clock/source.
        context=(camera_id,metadata.get('session'))
        with self.lock:
            if context==getattr(self,'offer_context',None) and stamp-self.last_offer<1/self.sample_fps:return
            self.last_offer=stamp;self.offer_context=context
        if self.frames.full():self.dropped_samples+=1;return
        try:self.frames.put_nowait((camera_id,frame.copy(),dict(metadata)))
        except queue.Full:self.dropped_samples+=1

    def request(self,eid,camera_id,metadata):
        item={'eid':eid,'camera_id':camera_id,'session':metadata.get('session'),
              'stamp':float(metadata['received_monotonic']),'utc':float(metadata['received_utc']),
              'deadline':time.monotonic()+self.post_seconds+.5,'frames':[],'seen':set()}
        try:
            if self.cancel.is_set():return False
            self.requests.put_nowait(item);return True
        except queue.Full:
            self.dropped_requests+=1
            self.store.emit(camera_id,'CLIPE_DESCARTADO','Limite de clipes pendentes; fotos e evento continuam disponíveis.','WARN',{'evidence_id':eid})
            return False

    def _append(self,item,f):
        if f['context']!=(item['camera_id'],item['session']):return
        if not item['stamp']-self.pre_seconds<=f['stamp']<=item['stamp']+self.post_seconds:return
        key=(f['stamp'],f['sequence'])
        if key in item['seen']:return
        item['seen'].add(key);item['frames'].append(f)
        # Both sample count and encoded bytes are bounded independently.
        while len(item['frames'])>32 or sum(len(x['jpeg']) for x in item['frames'])>self.max_bytes:
            item['frames'].pop(0)

    def _sample(self,item):
        cid,frame,meta=item;context=(cid,meta.get('session'))
        if self.context!=context:self.ring.clear();self.context=context
        h,w=frame.shape[:2];ratio=min(1,640/w,360/h)
        size=(max(2,int(w*ratio)//2*2),max(2,int(h*ratio)//2*2))
        out=cv2.resize(frame,size,interpolation=cv2.INTER_AREA)
        stamp=time.strftime('%H:%M:%S',time.localtime(meta['received_utc']))
        cv2.putText(out,stamp+' | amostra '+str(meta.get('sequence','')), (8,20),cv2.FONT_HERSHEY_SIMPLEX,.45,(255,255,255),1,cv2.LINE_AA)
        ok,encoded=cv2.imencode('.jpg',out,[cv2.IMWRITE_JPEG_QUALITY,78])
        if not ok:raise OSError('JPEG de clipe não codificado.')
        f={'context':context,'stamp':float(meta['received_monotonic']),'utc':float(meta['received_utc']),
           'sequence':int(meta['sequence']),'jpeg':encoded.tobytes(),'size':size}
        self.ring.append(f)
        while self.ring and (f['stamp']-self.ring[0]['stamp']>self.pre_seconds+.5 or sum(len(x['jpeg']) for x in self.ring)>self.max_bytes):self.ring.popleft()
        for active in self.active:self._append(active,f)

    def _finish(self,item,reason):
        with self.access_lock:
            self._finish_locked(item,reason)

    def _finish_locked(self,item,reason):
        directory=self.directory/item['eid'];target=directory/'clip.avi';tmp=directory/'.clip.tmp.avi'
        try:
            frames=sorted(item['frames'],key=lambda f:f['stamp'])
            if len(frames)<2:raise ValueError('Amostras insuficientes para clipe.')
            size=frames[0]['size']
            writer=cv2.VideoWriter(str(tmp),cv2.VideoWriter_fourcc(*'MJPG'),self.sample_fps,size)
            try:
                if not writer.isOpened():raise OSError('Encoder MJPG indisponível.')
                for f in frames:
                    image=cv2.imdecode(np.frombuffer(f['jpeg'],np.uint8),cv2.IMREAD_COLOR)
                    if image is None:raise OSError('Amostra de vídeo inválida.')
                    if (image.shape[1],image.shape[0])!=size:image=cv2.resize(image,size)
                    writer.write(image)
            finally:writer.release()
            if not tmp.exists() or tmp.stat().st_size<100:raise OSError('Clipe vazio.')
            # Verify the decoder can actually reopen at least the first frame.
            check=cv2.VideoCapture(str(tmp));ok,_=check.read();check.release()
            if not ok:raise OSError('Clipe gerado não pode ser lido.')
            os.replace(tmp,target)
            digest=hashlib.sha256(target.read_bytes()).hexdigest()
            full_tail=frames[-1]['stamp']>=item['stamp']+self.post_seconds-.6
            document={'evidence_id':item['eid'],'camera_id':item['camera_id'],'session':item['session'],
                'event_frame_utc':item['utc'],'event_monotonic':item['stamp'],'sample_fps':self.sample_fps,
                'encoded_duration_s':len(frames)/self.sample_fps,
                'observed_span_s':frames[-1]['stamp']-frames[0]['stamp'],
                'post_event_complete':full_tail,'completion_reason':reason,'sha256':{'clip.avi':digest},
                'frames':[{'frame_utc':f['utc'],'frame_monotonic':f['stamp'],'sequence':f['sequence']} for f in frames],
                'note':'Vídeo amostrado/anotado sem áudio, não gravação contínua nem original. Reprodução fixa pode comprimir lacunas: consulte os horários de cada amostra.'}
            atomic_json(directory/'clip.json',document)
            self.saved+=1
            self.store.emit(item['camera_id'],'CLIPE_SALVO','Clipe amostrado e horários das amostras gravados.',payload={'evidence_id':item['eid'],'frames':len(frames),'post_event_complete':full_tail})
        except Exception as exc:
            self.failed+=1;self.last_error=type(exc).__name__;tmp.unlink(missing_ok=True)
            self.store.emit(item['camera_id'],'CLIPE_FALHOU','Clipe indisponível; fotos/evento preservados.','WARN',{'evidence_id':item['eid'],'exception_type':type(exc).__name__})
        finally:(directory/'.clip-pendente').unlink(missing_ok=True)

    def _run(self):
        while not self.cancel.is_set() or not self.frames.empty() or not self.requests.empty() or self.active:
            try:
                item=self.frames.get(timeout=.035)
                try:self._sample(item)
                finally:self.frames.task_done()
            except queue.Empty:pass
            except Exception as exc:
                self.failed+=1;self.last_error=type(exc).__name__
            while True:
                try:item=self.requests.get_nowait()
                except queue.Empty:break
                if len(self.active)>=self.max_pending:
                    self.dropped_requests+=1
                    self.store.emit(item['camera_id'],'CLIPE_DESCARTADO','Máximo de clipes em andamento. Fotos preservadas.','WARN',{'evidence_id':item['eid']})
                    (self.directory/item['eid']/'.clip-pendente').unlink(missing_ok=True)
                else:
                    for f in self.ring:self._append(item,f)
                    self.active.append(item)
                self.requests.task_done()
            for item in list(self.active):
                if self.cancel.is_set() or time.monotonic()>=item['deadline']:
                    self._finish(item,'encerramento' if self.cancel.is_set() else 'janela_finalizada')
                    self.active.remove(item)

    def health(self):
        return {'saved':self.saved,'failed':self.failed,'pending':len(self.active)+self.requests.qsize(),
                'dropped_samples':self.dropped_samples,'dropped_requests':self.dropped_requests,
                'healthy':self.thread.is_alive() and not self.failed and not self.dropped_requests}

    def flush(self,timeout=5):
        end=time.monotonic()+timeout
        while (self.frames.unfinished_tasks or self.requests.unfinished_tasks or self.active) and time.monotonic()<end:time.sleep(.02)
        return not (self.frames.unfinished_tasks or self.requests.unfinished_tasks or self.active)

    def close(self):
        self.cancel.set();self.thread.join(timeout=6)
        if self.thread.is_alive():raise RuntimeError('Gravação dos clipes não encerrou no prazo.')
