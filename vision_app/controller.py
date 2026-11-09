from __future__ import annotations
import csv
import json
import os
import platform
import sys
import threading
import time
import zipfile
from pathlib import Path
from vision_foundation.config import CameraConfig,ConfigStore
from vision_foundation.storage import EventStore
from vision_foundation.supervisor import CameraSession
from .settings import SettingsStore,AnalysisConfig
from .service import AnalysisService
from .evidence import EvidenceWriter
from .model import MODEL_FILE,MODEL_SHA256,verified
from .object_registry import ObjectRegistry
from .review import ReviewRepository
from .evidence_review import EvidenceReview
from .dataset import DatasetStore
from .jobs import ExternalJobs
from .preview import LivePreview,PreviewSettings

class Controller:
    def __init__(self,directory:Path,model_dir:Path):
        import cv2
        cv2.setNumThreads(1)
        self.directory=directory;self.model_dir=model_dir
        self.configs=ConfigStore(directory);self.settings=SettingsStore(directory)
        self.objects=ObjectRegistry(directory)
        self.display=PreviewSettings(directory);self.preview=None
        self.events=EventStore(directory/'events.sqlite3')
        self.evidence=EvidenceWriter(directory/'evidence',self.events)
        self.reviews=ReviewRepository(self.events)
        self.evidence_review=EvidenceReview(self.evidence,self.reviews)
        self.dataset=DatasetStore(directory/'dataset')
        self.jobs=ExternalJobs()
        if not self.configs.all():self.configs.put(CameraConfig(id='webcam0',name='Webcam 0',kind='webcam',source='0'))
        self.camera=None;self.analysis=None;self.operation_lock=threading.RLock();self.closed=False
    def start(self,camera_id, *, analyze=True):
        with self.operation_lock:
            if self.closed:raise RuntimeError('Aplicativo encerrado.')
            self.stop()
            camera=self.configs.get(camera_id);cfg=self.settings.get(camera_id)
            if analyze and cfg.engine=='yolox' and not verified(self.model_dir/MODEL_FILE):
                raise ValueError('Modelo YOLOX ausente ou alterado. Nos executáveis CamCraft ele deve estar incluído: reinstale o pacote íntegro. No código-fonte, use Preparar modelo.')
            self.evidence.max_bytes=cfg.evidence_limit_mb*1024**2;self.evidence.max_files=cfg.evidence_limit_files
            self.camera=CameraSession(camera.model_copy(update={"jpeg_preview":False}),self.events)
            self.preview=LivePreview(self.camera,self.display.config)
            self.camera.start();self.preview.start()
            if analyze:
                self.analysis=AnalysisService(self.camera,self.events,self.evidence,cfg,self.model_dir,registry=self.objects)
                self.analysis.start()
    def stop(self):
        with self.operation_lock:
            if self.preview:self.preview.stop()
            if self.analysis:self.analysis.stop()
            if self.camera:self.camera.stop()
            self.analysis=None;self.camera=None;self.preview=None
    def pause_analysis(self):
        with self.operation_lock:
            if self.analysis:
                self.analysis.stop();self.analysis=None
            if self.camera:
                self.events.emit(self.camera.config.id,'ANALISE_PAUSADA',
                    'IA pausada pelo operador. Vídeo continua; nenhum evento de visão é inferido.')

    def resume_analysis(self):
        with self.operation_lock:
            if self.camera is None:raise ValueError('Inicie a câmera primeiro.')
            if self.analysis:return
            cfg=self.settings.get(self.camera.config.id)
            if cfg.engine=='yolox' and not verified(self.model_dir/MODEL_FILE):
                raise ValueError('Modelo não disponível. Use Mais > Preparar / verificar modelo. No EXE, reinstale o pacote se estiver incompleto. O vídeo permanece ativo.')
            self.analysis=AnalysisService(self.camera,self.events,self.evidence,cfg,self.model_dir,registry=self.objects)
            self.analysis.start()

    def configure_analysis(self,cid,cfg,display_cfg):
        """Restart ONLY analysis; preserve the live acquisition process and frame sequence."""
        with self.operation_lock:
            self.settings.put(cid,cfg)
            self.display.put(display_cfg)
            if self.preview:self.preview.configure(display_cfg)
            if self.camera and self.camera.config.id==cid and self.analysis:
                self.pause_analysis();self.resume_analysis()

    def calibration_frame(self):
        result=self.analysis.latest() if self.analysis else None
        if result is None:raise ValueError('Não há quadro atual. Inicie a câmera e aguarde a análise.')
        return result

    def register_object(self,name,roi,empty_result,present_result,class_id=None,replace_id=None):
        with self.operation_lock:
            if not self.camera or not self.analysis:raise ValueError('Câmera não está ativa.')
            cid=self.camera.config.id
            for key in ('session','generation','loops','width','height'):
                if empty_result.metadata.get(key)!=present_result.metadata.get(key):
                    raise ValueError('A câmera/sessão mudou durante a calibração. Refazer as duas referências.')
            if self.analysis.engine is None or present_result.metadata['session']!=self.analysis.engine.session:
                raise ValueError('A sessão mudou. Refazer a calibração.')
            if time.monotonic()-present_result.metadata['received_monotonic']>3:
                raise ValueError('Referência presente está antiga. Capture-a novamente.')
            from .interactions import fraction_covered
            from .object_registry import roi_pixels
            box=roi_pixels(roi,present_result.original.shape)
            for result in (empty_result,present_result):
                blockers=result.metadata.get('raw_people',result.tracks)
                if any(t['class_id']==0 and fraction_covered(box,t['box'])>.05 for t in blockers):
                    raise ValueError('Pessoa sobre a região nas referências. Afaste-se e capture novamente.')
            spec=self.objects.create(self.camera.config,name,roi,empty_result.original,present_result.original,class_id,replace_id)
            self.events.emit(cid,'OBJETO_CALIBRADO','Referências vazio/presente salvas e verificadas.',
                payload={'object_id':spec.id,'object_name':spec.name,'roi':list(spec.roi),'separation':spec.separation})
            self.start(cid)
            return spec.id

    def object_enabled(self,cid,oid,enabled):
        with self.operation_lock:
            self.objects.set_enabled(oid,enabled)
            if self.camera and self.camera.config.id==cid:self.start(cid)

    def remove_object(self,cid,oid):
        with self.operation_lock:
            self.objects.delete(oid)
            self.events.emit(cid,'OBJETO_REMOVIDO_CADASTRO','Cadastro removido; registros e evidências preservados.',payload={'object_id':oid})
            if self.camera and self.camera.config.id==cid:self.start(cid)

    def configure_interactions(self,cid,cfg):
        with self.operation_lock:
            self.objects.configure(cid,cfg)
            if self.camera and self.camera.config.id==cid:self.start(cid)

    def review_event(self,event_row_id,decision,note='',operator='operador local'):
        with self.operation_lock:
            return self.reviews.add(event_row_id,decision,note=note,operator=operator)

    def capture_sample(self):
        with self.operation_lock:
            result=self.calibration_frame()
            return self.dataset.capture(result.original,result.metadata,camera_id=self.camera.config.id)

    def backup(self,path):
        from .backup import create_backup
        return create_backup(self,path)

    def integrity(self):
        from contextlib import closing
        if not self.events.flush(5):raise OSError('Há gravações pendentes.')
        with closing(self.events.connect()) as db:
            check=[r[0] for r in db.execute('PRAGMA quick_check')]
        return {'database':check,'review_chain':self.reviews.verify_chain(),
                'storage':self.events.health(),'evidence':self.evidence.health()}

    def photo(self):
        result=self.analysis.latest() if self.analysis else None
        if result is None:
            packet=self.camera.latest(raw=True) if self.camera else None
            if packet is None:raise ValueError('Não há quadro atual para salvar.')
            from types import SimpleNamespace
            result=SimpleNamespace(original=packet.bgr,frame=packet.bgr,
                metadata={**packet.metadata,'engine':'none','analysis_status':'NOT_ANALYZED','tracks':[]})
        eid=self.evidence.submit(self.camera.config.id,result.original,result.frame,result.metadata,[])
        if eid is None:raise ValueError('Fila de evidências cheia. Aguarde o término das gravações.')
        self.events.emit(self.camera.config.id,'FOTO_SOLICITADA','Foto solicitada; aguarde EVIDENCIA_SALVA.',payload={'evidence_id':eid})
        return eid
    def export_csv(self,path:Path):
        def safe(v):
            v=str(v)
            return "'"+v if v.lstrip().startswith(('=','+','-','@')) else v
        self.events.flush()
        before=None;count=0
        with path.open('w',encoding='utf-8-sig',newline='') as f:
            out=csv.writer(f,delimiter=';')
            out.writerow(['id','UTC_registro','camera','evento','mensagem','dados_JSON'])
            while True:
                rows=self.events.events(limit=1000,before=before)
                if not rows:break
                for r in rows:
                    out.writerow([r['id'],time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime(r['utc'])),safe(r['camera_id'] or ''),r['code'],safe(r['message']),safe(json.dumps(r['payload'],ensure_ascii=False))])
                    count+=1
                before=rows[-1]['id']
        return count
    def diagnostic(self,path:Path):
        import importlib.metadata
        document={'application':'CamCraft 4.2.0','utc':time.time(),
            'platform':platform.platform(),'python':sys.version.split()[0],
            'camera':self.camera.snapshot() if self.camera else None,
            'analysis':self.analysis.snapshot() if self.analysis else None,
            'live_preview':self.preview.snapshot() if self.preview else None,
            'display':self.display.config.model_dump(),
            'event_storage':self.events.health(),'evidence_storage':self.evidence.health(),
            'review_integrity':self.reviews.verify_chain(),
            'dataset_samples':len(self.dataset.list()),
            'profiles':[c.public() for c in self.configs.all()],
            'settings':{c.id:self.settings.get(c.id).model_dump() for c in self.configs.all()},
            'model':{'filename':MODEL_FILE,'expected_sha256':MODEL_SHA256,'verified':verified(self.model_dir/MODEL_FILE)},
            'objects':{c.id:[o.model_dump(exclude={'hashes','source_signature'}) for o in self.objects.all(c.id)] for c in self.configs.all()},
            'interaction_settings':{c.id:self.objects.config(c.id).model_dump() for c in self.configs.all()},'packages':{}}
        for name in ('opencv-python-headless','numpy','scipy','Pillow','pydantic','psutil'):
            try:document['packages'][name]=importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:document['packages'][name]='not installed'
        with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
            z.writestr('diagnostico.json',json.dumps(document,ensure_ascii=False,indent=2))
            z.writestr('eventos_recentes.json',json.dumps(self.events.events(limit=1000),ensure_ascii=False,indent=2))
            z.writestr('LEIA.txt','Sem fotos, vídeos ou credenciais de câmera. Eventos podem conter nomes de categorias, horários e IDs temporários. Revise antes de compartilhar.')
        return str(path)
    def close(self):
        with self.operation_lock:
            if self.closed:return
            self.jobs.close();self.stop();self.evidence.close();self.events.close();self.closed=True
