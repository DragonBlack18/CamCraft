import json
import time
from types import SimpleNamespace

from vision_app.evidence import EvidenceWriter
from vision_app.object_registry import ObjectRegistry,InteractionConfig
from vision_app.service import AnalysisService
from vision_app.settings import AnalysisConfig
from vision_foundation.ipc import FramePacket
from vision_foundation.config import CameraConfig
from tests.test_interactions import images,ROI


def test_real_pipeline_comparison_events_before_after_and_avi(tmp_path,store):
    """Real BGR -> interaction state -> SQLite/JPEG/AVI, using empty model outputs.

    Does not assert neural detection accuracy or person attribution.
    """
    cfg=CameraConfig(id='room',kind='demo',source='demo',width=640,height=360,raw_max_width=640,raw_max_height=360)
    reg=ObjectRegistry(tmp_path/'data');empty,present=images()
    reg.create(cfg,'Objeto de integração',ROI,empty,present)
    reg.configure(cfg.id,InteractionConfig(present_seconds=.5,absent_seconds=.8))
    holder={'packet':None}
    camera=SimpleNamespace(config=cfg,latest=lambda **kwargs:holder['packet'])
    evidence=EvidenceWriter(tmp_path/'data'/'evidence',store)
    service=AnalysisService(camera,store,evidence,AnalysisConfig(engine='hog'),tmp_path,registry=reg)
    try:
        for seq in range(32):
            frame=present if seq<9 or seq>=22 else empty
            meta={'generation':1,'loops':0,'width':640,'height':360,'sequence':seq+1,
                  'received_monotonic':time.monotonic(),'received_utc':time.time()}
            packet=FramePacket(meta,frame);holder['packet']=packet
            service._accept({'packet':packet},{'detections':[],'inference_ms':0,'backend':'controlled model output / real reference comparison'})
            time.sleep(.14)
        assert service.latest().metadata['objects'][0]['stable_state']=='PRESENTE'
        assert evidence.flush() and evidence.clips.flush(5)
        store.flush();rows=store.events(limit=1000)
        codes=[e['code'] for e in rows]
        assert codes.count('AUSENCIA_CONFIRMADA')==1 and codes.count('RETORNO_OBSERVADO')==1
        assert 'RETIRADA_PROVAVEL' not in codes
        event=next(e for e in rows if e['code']=='AUSENCIA_CONFIRMADA')
        directory=evidence.directory/event['payload']['evidence_id']
        meta=json.loads((directory/'evento.json').read_text())
        assert len(meta['before_images'])==1
        assert (directory/'clip.avi').is_file() and (directory/'clip.json').is_file()
        assert evidence.failures==0 and evidence.clips.failed==0
    finally:evidence.close()


def test_loop_context_invalidates_object_transition(tmp_path,store):
    cfg=CameraConfig(id='loop',kind='demo',source='demo',width=640,height=360,raw_max_width=640,raw_max_height=360)
    reg=ObjectRegistry(tmp_path/'data');empty,present=images();reg.create(cfg,'Teste',ROI,empty,present)
    reg.configure(cfg.id,InteractionConfig(present_seconds=.5,absent_seconds=.8,clips=False))
    holder={'packet':None};camera=SimpleNamespace(config=cfg,latest=lambda **kw:holder['packet'])
    ev=EvidenceWriter(tmp_path/'e',store)
    service=AnalysisService(camera,store,ev,AnalysisConfig(engine='hog'),tmp_path,registry=reg)
    try:
        for seq in range(17):
            meta={'generation':1,'loops':0 if seq<7 else 1,'width':640,'height':360,'sequence':seq,
                  'received_monotonic':time.monotonic(),'received_utc':time.time()}
            p=FramePacket(meta,present if seq<7 else empty);holder['packet']=p
            service._accept({'packet':p},{'detections':[],'inference_ms':0})
            time.sleep(.12)
        store.flush();codes=[r['code'] for r in store.events()]
        assert 'OBJETO_PRESENTE_INICIAL' in codes and 'OBJETO_AUSENTE_INICIAL' in codes
        assert 'AUSENCIA_CONFIRMADA' not in codes
    finally:ev.close()
