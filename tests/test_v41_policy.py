import json,time
from types import SimpleNamespace
import numpy as np
import pytest
from vision_app.settings import AnalysisConfig,SettingsStore
from vision_app.classes import allowed
from vision_app.detector import decode
from vision_app.tracker import Tracker
from vision_app.render import render
from vision_app.preview import PreviewConfig,PreviewSettings,compatible
from tests.test_detection import raw_detection
from tests.test_tracking_events import det


def test_indoor_default_excludes_vehicles_not_relabels():
    cfg=AnalysisConfig()
    assert cfg.classes=='bedroom' and 2 not in cfg.class_ids()
    pred=raw_detection(class_id=2,score=.95)
    pred[0,0,5]=.8  # person is runner-up; do not promote it because car is disabled
    assert decode(pred,(640,640,3),1,cfg)==[]
    all_cfg=AnalysisConfig(classes='all',class_margin=0)
    assert decode(pred,(640,640,3),1,all_cfg)[0]['class_id']==2


def test_vehicle_not_recorded_even_from_external_worker():
    tracker=Tracker(AnalysisConfig(min_hits=2,confirm_seconds=.1))
    for i in range(20):assert tracker.update([det(cls=2)],i*.1)==([],[])


def test_allowed_profile_never_promotes_runnerup():
    p=raw_detection(class_id=67,score=.9);p[0,0,5]=.85
    assert decode(p,(640,640,3),1,AnalysisConfig(classes='people',class_margin=0))==[]


def test_uncertain_categories_rejected_even_with_high_confidence():
    p=raw_detection(class_id=0,score=.9);p[0,0,5+59]=.87
    assert decode(p,(640,640,3),1,AnalysisConfig())==[]
    assert len(decode(p,(640,640,3),1,AnalysisConfig(class_margin=0)))==1


def test_margin_does_not_modify_raw_model_score():
    d=decode(raw_detection(score=.8),(640,640,3),1,AnalysisConfig())[0]
    assert d['score']==pytest.approx(.8)


def test_overrides_are_enforced_in_tracker_not_only_display():
    c=AnalysisConfig(class_thresholds={0:.85},min_hits=2,confirm_seconds=.1)
    t=Tracker(c)
    for i in range(5):assert t.update([det(score=.8)],i*.1)[0]==[]
    assert t.update([det(score=.9)],.6)[0]


def test_strict_default_hides_unconfirmed_labels():
    frame=np.zeros((240,320,3),np.uint8)
    track={'id':1,'class_id':0,'box':[10,20,80,120],'score':.9,'confirmed':False}
    assert np.array_equal(render(frame,[track],AnalysisConfig()),frame)
    assert not np.array_equal(render(frame,[track],AnalysisConfig(show_tentative=True)),frame)


def test_weak_scores_cannot_keep_confirmed_label_alive_forever():
    t=Tracker(AnalysisConfig(min_hits=2,confirm_seconds=.1,recovery_seconds=.3))
    t.update([det()],0);assert t.update([det()],.2)[0][0].confirmed
    assert t.update([det(score=.2)],.3)[0]
    assert t.update([det(score=.2)],.6)[0]==[]


def test_slow_but_regular_inference_can_confirm():
    t=Tracker(AnalysisConfig(max_fps=10,min_hits=3,confirm_seconds=.55))
    for stamp in (0.,1.,2.):rows,_=t.update([det()],stamp)
    assert rows[0].confirmed


def test_confirmation_duration_restarts_after_missed_detection():
    t=Tracker(AnalysisConfig(min_hits=2,confirm_seconds=.5))
    t.update([det()],0);t.update([],1)
    rows,_=t.update([det()],1.1);assert not rows[0].confirmed
    rows,_=t.update([det()],1.2);assert not rows[0].confirmed
    rows,_=t.update([det()],1.7);assert rows[0].confirmed


@pytest.mark.parametrize('values',[{'custom_classes':[99]},{'classes':'custom','custom_classes':[]},
    {'class_thresholds':{0:.01}},{'class_thresholds':{80:.8}}, {'class_thresholds':{0:float('nan')}},
    {'class_margin':1.1},{'recovery_seconds':6},{'confirmation_gap':0}])
def test_invalid_extended_settings(values):
    with pytest.raises(ValueError):AnalysisConfig(**values)


def test_custom_categories_and_overrides_roundtrip(tmp_path):
    c=AnalysisConfig(classes='custom',custom_classes=[67,0,67],class_thresholds={67:.8})
    s=SettingsStore(tmp_path);s.put('x',c)
    got=SettingsStore(tmp_path).get('x')
    assert got.class_ids()=={0,67} and got.threshold(67)==.8 and got.threshold(0)==.6


def test_old_configuration_migrated_once_with_backup(tmp_path):
    original=json.dumps({'schema':2,'cameras':{'x':{'classes':'all','confidence':.45}}})
    p=tmp_path/'analysis.json';p.write_text(original)
    s=SettingsStore(tmp_path)
    assert s.get('x').classes=='bedroom' and s.get('x').confidence==.45
    assert (tmp_path/'analysis.pre-v4.1.json').read_text()==original
    assert s.migration_notice and json.loads(p.read_text())['schema']==3
    s.put('x',AnalysisConfig(classes='all'))
    assert SettingsStore(tmp_path).get('x').classes=='all'
    assert (tmp_path/'analysis.pre-v4.1.json').read_text()==original


def test_explicit_legacy_people_profile_preserved(tmp_path):
    (tmp_path/'analysis.json').write_text(json.dumps({'schema':2,'cameras':{'x':{'classes':'people'}}}))
    assert SettingsStore(tmp_path).get('x').classes=='people'


def test_display_preferences_roundtrip(tmp_path):
    store=PreviewSettings(tmp_path);assert store.config.fps==30
    store.put(PreviewConfig(fps=20,max_width=640,show_inset=False))
    assert PreviewSettings(tmp_path).config.max_width==640


@pytest.mark.parametrize('values',[{'fps':100},{'max_width':9999},{'max_age':0},{'mode':'fake'}])
def test_display_preferences_reject_invalid(values):
    with pytest.raises(ValueError):PreviewConfig(**values)


def test_inset_not_mixed_across_source_or_generation():
    meta={'camera_id':'a','generation':1,'loops':0,'width':640,'height':480,'received_monotonic':10}
    result=SimpleNamespace(metadata=meta)
    assert compatible(result,meta,10.2,2)
    for key,value in [('camera_id','b'),('generation',2),('loops',1),('width',320)]:
        assert not compatible(result,{**meta,key:value},10.2,2)
    assert not compatible(result,meta,13,2)
    assert not compatible(result,meta,9,2)


def test_reuse_model_missing_or_wrong_hash_never_copies(tmp_path):
    from tools.reuse_model import reuse
    src=tmp_path/'old';dst=tmp_path/'new';src.mkdir()
    assert reuse(src,dst)=='NOT_FOUND'
    (src/'models').mkdir()
    from vision_app.model import MODEL_FILE
    (src/'models'/MODEL_FILE).write_bytes(b'not a model')
    with pytest.raises(ValueError):reuse(src,dst)
    assert not (dst/MODEL_FILE).exists()
    assert (src/'models'/MODEL_FILE).read_bytes()==b'not a model'


def test_reuse_verified_model_atomic_with_controlled_verifier(tmp_path,monkeypatch):
    import tools.reuse_model as module
    from vision_app.model import MODEL_FILE
    src=tmp_path/'old';(src/'models').mkdir(parents=True);(src/'data').mkdir()
    content=b'unit-test-only file; not neural weights'
    (src/'models'/MODEL_FILE).write_bytes(content)
    monkeypatch.setattr(module,'verified',lambda path:path.is_file() and path.read_bytes()==content)
    dst=tmp_path/'new'
    assert module.reuse(src/'data',dst)=='COPIED_VERIFIED'
    assert module.reuse(src,dst)=='ALREADY_VERIFIED'
    assert (src/'models'/MODEL_FILE).read_bytes()==content
