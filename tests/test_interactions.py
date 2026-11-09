"""Controlled-image tests exercise real reference comparisons, NOT detector accuracy."""
import json
import time
from pathlib import Path
import cv2
import numpy as np
import pytest

from vision_app.object_registry import ObjectRegistry, InteractionConfig, ObjectSpec, patch, source_signature
from vision_app.interactions import InteractionEngine
from vision_foundation.config import CameraConfig

ROI=(.30,.35,.40,.60)
BOX=[192.,126.,256.,216.]


def images():
    y,x=np.mgrid[:360,:640]
    gray=(105+20*np.sin(x/13)+12*np.cos(y/9)+((x//30+y//30)%2)*12).clip(0,255).astype(np.uint8)
    empty=np.dstack([gray,gray,gray])
    present=empty.copy()
    present[126:216,192:256]=(40,80,220)
    cv2.rectangle(present,(200,134),(247,207),(210,180,40),3)
    cv2.line(present,(200,205),(248,136),(30,220,230),5)
    return empty,present


def track(key,box,cls=0):
    return {'id':key,'box':list(box),'class_id':cls,'score':.92,'confirmed':True}


@pytest.fixture
def registered(tmp_path):
    registry=ObjectRegistry(tmp_path/'data')
    camera=CameraConfig(id='room',name='Sala',kind='demo',source='demo',width=640,height=360,raw_max_width=640,raw_max_height=360)
    empty,present=images()
    spec=registry.create(camera,'Garrafa teste',ROI,empty,present,class_id=39)
    return registry,camera,spec,empty,present


class Run:
    def __init__(self,registered,**kwargs):
        registry,camera,self.spec,self.empty,self.present=registered
        self.engine=InteractionEngine(registry,camera,'s_test',**kwargs)
        self.t=100.;self.sequence=0;self.events=[];self.extras={};self.states=[]
    def step(self,frame,tracks=(),raw=None,dt=.25):
        self.t+=dt;self.sequence+=1
        states,events,extras=self.engine.update(frame,list(tracks),list(raw if raw is not None else tracks),self.t,1700000000+self.t,self.sequence)
        self.events.extend(events);self.extras.update(extras);self.states=states
        return events
    def feed(self,frame,count=9,**kwargs):
        for _ in range(count):self.step(frame,**kwargs)
    @property
    def codes(self):return [e['code'] for e in self.events]


def test_registry_roundtrip_and_hash_check(registered):
    reg,cam,spec,empty,present=registered
    again=ObjectRegistry(reg.directory)
    assert again.all(cam.id)[0]==spec
    refs=again.load(spec)
    assert refs['presente.png'].shape==(80,80,3)
    (again.refs/spec.reference_dir/'vazio.png').write_bytes(b'tampered')
    with pytest.raises(ValueError,match='Integridade'):again.load(spec)


def test_reference_insufficient_separation_rejected(registered):
    reg,cam,spec,empty,present=registered
    with pytest.raises(ValueError,match='parecidos'):
        reg.create(cam,'Sem diferença',ROI,empty,empty,replace_id=spec.id)
    assert reg.all(cam.id)[0]==spec


def test_reference_changed_scene_rejected(registered):
    reg,cam,spec,empty,present=registered
    changed=np.clip(present.astype(int)+45,0,255).astype(np.uint8)
    with pytest.raises(ValueError,match='Cena mudou'):
        reg.create(cam,'Câmera mexida',ROI,empty,changed,replace_id=spec.id)


def test_recalibration_replaces_reference_atomically(registered):
    reg,cam,spec,empty,present=registered
    new=reg.create(cam,'Novo nome',ROI,empty,present,replace_id=spec.id)
    assert new.id==spec.id and new.reference_dir!=spec.reference_dir
    assert not (reg.refs/spec.reference_dir).exists()
    assert len(reg.all(cam.id))==1


def test_registration_preserves_old_json_on_failure(registered,monkeypatch):
    reg,cam,spec,empty,present=registered
    original=reg.path.read_bytes()
    def fail(*args):raise OSError('test disk failure')
    monkeypatch.setattr('vision_app.object_registry.atomic_json',fail)
    with pytest.raises(OSError):reg.create(cam,'Novo',ROI,empty,present,replace_id=spec.id)
    assert reg.path.read_bytes()==original and reg.all(cam.id)[0]==spec
    assert len(list(reg.refs.iterdir()))==1


def test_overlap_rejected(registered):
    reg,cam,spec,empty,present=registered
    with pytest.raises(ValueError,match='sobrepostas'):reg.create(cam,'Duplo',ROI,empty,present)


def test_config_validation(registered):
    reg,cam,*_=registered
    with pytest.raises(ValueError):InteractionConfig(min_observations=1)
    with pytest.raises(ValueError):InteractionConfig(absent_seconds=.1)
    cfg=InteractionConfig(clips=False,absent_seconds=2)
    reg.configure(cam.id,cfg)
    assert ObjectRegistry(reg.directory).config(cam.id)==cfg


def test_disable_delete_does_not_touch_evidence(registered):
    reg,cam,spec,*_=registered
    keep=reg.directory/'evidence';keep.mkdir();(keep/'precious.txt').write_text('keep')
    reg.set_enabled(spec.id,False)
    assert not InteractionEngine(reg,cam,'x').objects
    reg.delete(spec.id)
    assert not reg.all(cam.id) and (keep/'precious.txt').read_text()=='keep'


def test_initial_absence_never_removal(registered):
    run=Run(registered);run.feed(run.empty,20)
    assert run.codes==['OBJETO_AUSENTE_INICIAL']
    assert run.states[0]['state']=='AUSENTE'


def test_absence_and_return_before_images_no_duplicates(registered):
    run=Run(registered);run.feed(run.present,12);run.feed(run.empty,16);run.feed(run.present,16)
    assert run.codes==['OBJETO_PRESENTE_INICIAL','AUSENCIA_CONFIRMADA','RETORNO_OBSERVADO']
    for e in run.events[1:]:
        assert e['actor_track_id'] is None and e['before_image']
        assert e['before_metadata']['frame_monotonic']<e['frame_monotonic']
    assert run.states[0]['state']=='PRESENTE'


def test_detector_misses_are_not_absence(registered):
    run=Run(registered);run.feed(run.present,60,raw=[])
    assert run.codes==['OBJETO_PRESENTE_INICIAL']


def test_one_empty_frame_does_not_confirm_absence(registered):
    run=Run(registered);run.feed(run.present);run.step(run.empty);run.feed(run.present)
    assert run.codes==['OBJETO_PRESENTE_INICIAL']


def test_low_confidence_person_blocks_absence(registered):
    run=Run(registered);run.feed(run.present)
    weak={'box':BOX,'class_id':0,'score':.12}
    run.feed(run.empty,20,raw=[weak])
    assert 'AUSENCIA_CONFIRMADA' not in run.codes and run.states[0]['state']=='OCULTO'
    assert run.codes.count('OBJETO_OCULTO')==1


def test_contact_without_comotion_no_attribution(registered):
    run=Run(registered);run.feed(run.present)
    person=track(1,[140,70,260,320])
    occupied=run.present.copy();cv2.rectangle(occupied,(140,70),(260,320),(45,45,80),-1)
    run.feed(occupied,8,tracks=[person]);run.feed(run.empty,12)
    assert 'INTERACAO_POSSIVEL' in run.codes and 'OBJETO_OCULTO' in run.codes
    assert 'AUSENCIA_CONFIRMADA' in run.codes and 'RETIRADA_PROVAVEL' not in run.codes
    event=next(e for e in run.events if e['code']=='AUSENCIA_CONFIRMADA')
    assert event['actor_track_id'] is None


def test_camera_shift_suspends_not_absence(registered):
    run=Run(registered);run.feed(run.present)
    shifted=cv2.warpAffine(run.present,np.float32([[1,0,22],[0,1,0]]),(640,360))
    run.feed(shifted,12)
    assert run.states[0]['state']=='SUSPENSO'
    assert 'MONITORAMENTO_SUSPENSO' in run.codes and 'AUSENCIA_CONFIRMADA' not in run.codes


def test_lighting_change_suspends_and_restart_is_initial(registered):
    run=Run(registered);run.feed(run.present)
    dark=(run.empty*.25).astype(np.uint8);run.feed(dark,12);run.feed(run.empty,12)
    assert 'MONITORAMENTO_SUSPENSO' in run.codes and 'MONITORAMENTO_RETOMADO' in run.codes
    assert 'OBJETO_AUSENTE_INICIAL' in run.codes and 'AUSENCIA_CONFIRMADA' not in run.codes


def test_minor_global_brightness_change_tolerated(registered):
    run=Run(registered);run.feed(run.present)
    brighter=np.clip(run.present.astype(int)+9,0,255).astype(np.uint8)
    run.feed(brighter,12)
    assert run.states[0]['state']=='PRESENTE' and run.codes==['OBJETO_PRESENTE_INICIAL']


def test_unknown_appearance_does_not_become_absence(registered):
    run=Run(registered);run.feed(run.present)
    unknown=run.empty.copy();unknown[126:216,192:256]=(220,40,150)
    run.feed(unknown,24)
    assert run.codes.count('ALTERACAO_INCONCLUSIVA')==1
    assert 'AUSENCIA_CONFIRMADA' not in run.codes


def test_gap_resets_temporal_evidence(registered):
    run=Run(registered);run.feed(run.present)
    run.step(run.empty,dt=4);run.feed(run.empty,12)
    assert 'MONITORAMENTO_RETOMADO' in run.codes
    assert 'OBJETO_AUSENTE_INICIAL' in run.codes and 'AUSENCIA_CONFIRMADA' not in run.codes


def test_repeated_timestamp_not_counted(registered):
    run=Run(registered);run.step(run.present)
    for _ in range(100):run.step(run.present,dt=0)
    assert not run.events


def test_resolution_change_and_outside_analysis_roi_suspend(registered):
    run=Run(registered);run.feed(cv2.resize(run.present,(320,180)),10)
    assert run.states[0]['state']=='SUSPENSO'
    other=Run(registered,analysis_roi=(0,0,.2,.2));other.feed(other.present)
    assert other.states[0]['state']=='SUSPENSO'


def test_changed_source_and_tamper_reported(registered):
    reg,cam,spec,*_=registered
    changed=cam.model_copy(update={'source':'different'})
    engine=InteractionEngine(reg,changed,'s')
    assert len(engine.load_errors)==1 and not engine.objects
    _,events,_=engine.update(images()[1],[],[],1,100)
    assert events[0]['code']=='MONITORAMENTO_SUSPENSO'
    assert not engine.update(images()[1],[],[],2,101)[1]


def movement_scenario(run,two_people=False,allow_id_switch=False):
    """Scripted boxes + generated pixels; exercises rule gates, not YOLO inference."""
    item=track(10,BOX,39)
    run.feed(run.present,12,tracks=[item])
    person=track(1,[170,60,285,320])
    contact=run.present.copy();cv2.rectangle(contact,(170,60),(285,320),(65,50,60),-1)
    people=[person]
    if two_people:people.append(track(2,[175,60,290,320]))
    run.feed(contact,4,tracks=people+[item])
    for i in range(12):
        # The first 8 frames show the same bound item and the person moving together.
        x=290+i*13
        canvas=run.empty.copy();cv2.rectangle(canvas,(x-15,60),(x+90,320),(65,50,60),-1)
        canvas[126:216,x:x+64]=run.present[126:216,192:256]
        moved=track(11 if allow_id_switch else 10,[x,126,x+64,216],39)
        p=track(1,[x-15,60,x+90,320]);run.step(canvas,tracks=[moved,p])
    run.feed(run.empty,5)


def test_probable_removal_requires_bound_item_and_measured_comotion(registered):
    run=Run(registered);movement_scenario(run)
    assert 'RETIRADA_PROVAVEL' in run.codes, run.events
    event=next(e for e in run.events if e['code']=='RETIRADA_PROVAVEL')
    assert event['association']=='PROVAVEL_NAO_COMPROVADA'
    assert event['actor_track_id']=='s_test:00001' and event['requires_review']
    assert event['association_evidence']['observations']>=3


def test_multiple_people_prevent_attribution(registered):
    run=Run(registered);movement_scenario(run,two_people=True)
    assert 'RETIRADA_PROVAVEL' not in run.codes
    event=next(e for e in run.events if e['code']=='AUSENCIA_CONFIRMADA')
    assert event['actor_track_id'] is None and event['ambiguous_people']


def test_object_id_switch_prevents_attribution(registered):
    run=Run(registered);movement_scenario(run,allow_id_switch=True)
    assert 'RETIRADA_PROVAVEL' not in run.codes and 'AUSENCIA_CONFIRMADA' in run.codes


def test_hog_never_assigns_actor_even_with_scripted_objects(registered):
    run=Run(registered,allow_association=False);movement_scenario(run)
    assert 'RETIRADA_PROVAVEL' not in run.codes


def test_restart_does_not_claim_return(registered):
    run=Run(registered);run.feed(run.empty)
    fresh=Run(registered);fresh.feed(fresh.present)
    assert fresh.codes==['OBJETO_PRESENTE_INICIAL']


def test_monitoring_disabled(registered):
    reg,cam,*_=registered;reg.configure(cam.id,InteractionConfig(enabled=False))
    run=Run(registered);run.feed(run.present);assert not run.events and not run.states
