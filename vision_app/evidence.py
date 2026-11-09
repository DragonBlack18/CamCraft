from __future__ import annotations
import hashlib
import json
import os
import queue
import shutil
import threading
import time
import uuid
from pathlib import Path
import cv2
from .clips import ClipRecorder

class EvidenceWriter:
    """One bounded asynchronous writer. Disk is never on the capture/model/UI path."""
    def __init__(self,directory:Path,store,max_mb=512,max_files=1000):
        self.directory=directory; directory.mkdir(parents=True,exist_ok=True)
        self.store=store;self.max_bytes=max_mb*1024**2;self.max_files=max_files
        self.queue=queue.Queue(maxsize=4);self.cancel=threading.Event()
        self.access_lock=threading.RLock();self.retention_blocked=False
        self.dropped=0;self.failures=0;self.saved=0
        self.last_error=''
        self.clips=ClipRecorder(directory,store,access_lock=self.access_lock)
        for marker in directory.glob('e_*/.clip-pendente'):
            if not marker.parent.is_symlink():
                marker.unlink(missing_ok=True)
                self.store.emit(None,'CLIPE_INTERROMPIDO','Clipe pendente de execução anterior não concluído; fotos preservadas.','WARN',{'evidence_id':marker.parent.name})
        for p in directory.glob('.pending-e_*'):
            if p.is_dir() and not p.is_symlink():shutil.rmtree(p,ignore_errors=True)
        self.thread=threading.Thread(target=self._run,name='evidence-writer',daemon=True)
        self.thread.start()
    def submit(self,camera_id,original,annotated,metadata,events,*,before_images=None,make_clip=False):
        if self.cancel.is_set():return None
        eid='e_'+uuid.uuid4().hex
        # Queue length, frame resolution and max detections are all bounded.
        if self.queue.full():
            self.dropped+=1
            self.store.emit(camera_id,'EVIDENCIA_DESCARTADA','Fila de evidências cheia; evento textual preservado.','WARN')
            return None
        before_images=before_images or {}
        if len(before_images)>8:raise ValueError('Limite de referências anteriores excedido.')
        import re
        if any(not re.fullmatch(r'antes_o_[0-9a-f]{16}\.jpg',name) for name in before_images):raise ValueError('Nome de evidência anterior inválido.')
        copies={}
        for value in before_images.values():
            key=id(value['frame'])
            if key not in copies:copies[key]=value['frame'].copy()
        extras={name:{'frame':copies[id(item['frame'])],'metadata':dict(item['metadata'])} for name,item in before_images.items()}
        item=(eid,camera_id,original.copy(),annotated.copy(),dict(metadata),list(events),extras,bool(make_clip))
        try:self.queue.put_nowait(item)
        except queue.Full:
            self.dropped+=1;return None
        return eid
    def _run(self):
        while not self.cancel.is_set() or not self.queue.empty():
            try:item=self.queue.get(timeout=.1)
            except queue.Empty:continue
            eid,camera_id,raw,annotated,metadata,events,extras,make_clip=item
            temp=self.directory/('.pending-'+eid)
            try:
                if shutil.disk_usage(self.directory).free < 256*1024**2:
                    raise OSError('Pouco espaço livre.')
                temp.mkdir()
                hashes={}
                for filename,frame in [('quadro.jpg',raw),('anotado.jpg',annotated)]+[(name,item['frame']) for name,item in extras.items()]:
                    ok,data=cv2.imencode('.jpg',frame,[cv2.IMWRITE_JPEG_QUALITY,93])
                    if not ok:raise OSError('Falha ao codificar evidência.')
                    content=data.tobytes()
                    (temp/filename).write_bytes(content)
                    hashes[filename]=hashlib.sha256(content).hexdigest()
                document={'evidence_id':eid,'camera_id':camera_id,'created_utc':time.time(),
                    'metadata':metadata,'events':events,'sha256':hashes,
                    'before_images':{name:item['metadata'] for name,item in extras.items()},
                    'clip_requested':make_clip,
                    'note':'quadro.jpg é o quadro decodificado sem caixas, recodificado em JPEG; não é o arquivo bruto do sensor. Horário após decode; score não é probabilidade calibrada.'}
                with (temp/'evento.json').open('w',encoding='utf-8') as f:
                    json.dump(document,f,ensure_ascii=False,indent=2,allow_nan=False);f.flush();os.fsync(f.fileno())
                if make_clip:(temp/'.clip-pendente').touch()
                os.replace(temp,self.directory/eid)
                if make_clip and not self.clips.request(eid,camera_id,metadata):
                    (self.directory/eid/'.clip-pendente').unlink(missing_ok=True)
                self.saved+=1
                self.store.emit(camera_id,'EVIDENCIA_SALVA','Imagens e metadados gravados.',payload={'evidence_id':eid})
                self._retention()
            except Exception as exc:
                self.failures+=1;self.last_error=type(exc).__name__
                self.store.emit(camera_id,'EVIDENCIA_FALHOU','Não foi possível gravar evidência; consulte espaço/permissões.','ERROR',{'evidence_id':eid})
                shutil.rmtree(temp,ignore_errors=True)
            finally:self.queue.task_done()
    def _retention(self):
        with self.access_lock:
            self._retention_locked()

    def _retention_locked(self):
        entries=[];protected_bytes=0;protected_count=0
        for p in self.directory.glob('e_*'):
            if p.is_symlink() or not p.is_dir() or not (p/'evento.json').is_file() or (p/'.clip-pendente').exists():continue
            size=sum(q.stat().st_size for q in p.iterdir() if q.is_file())
            if (p/'.preservada').exists():
                protected_bytes+=size;protected_count+=1
                continue
            entries.append((p.stat().st_mtime,p,size))
        entries.sort();size=sum(s for _,_,s in entries)+protected_bytes;removed=0
        while entries and (len(entries)+protected_count>self.max_files or size>self.max_bytes):
            _,p,s=entries.pop(0);shutil.rmtree(p);size-=s;removed+=1
        self.retention_blocked=protected_count>self.max_files or protected_bytes>self.max_bytes
        if removed:self.store.emit(None,'RETENCAO_EVIDENCIAS','Evidências antigas removidas pelos limites configurados.','WARN',{'count':removed})
    def health(self):
        return {'queue':self.queue.qsize(),'capacity':4,'dropped':self.dropped,'failures':self.failures,
                'saved':self.saved,'retention_blocked_by_preserved':self.retention_blocked,'clips':self.clips.health(),'healthy':not(self.dropped or self.failures) and self.thread.is_alive()}
    def flush(self,timeout=5):
        deadline=time.monotonic()+timeout
        while self.queue.unfinished_tasks and time.monotonic()<deadline:time.sleep(.01)
        return self.queue.unfinished_tasks==0
    def close(self):
        self.cancel.set();self.thread.join(timeout=5)
        if self.thread.is_alive():raise RuntimeError('Gravação das evidências não encerrou no prazo.')
        self.clips.close()
        try:self._retention()
        except OSError:
            self.store.emit(None,'RETENCAO_FALHOU','Limpeza de evidências não concluída no encerramento. Revise permissões/armazenamento.','WARN')
