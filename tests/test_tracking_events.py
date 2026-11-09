import numpy as np
import pytest
from vision_app.tracker import Tracker,partial_assignment,iou_matrix,MotionFilter
from vision_app.events import EventEngine,segments_intersect
from vision_app.settings import AnalysisConfig

def det(x=200,score=.9,cls=0,bottom=300):
    return {'box':[x-30,bottom-120,x+30,bottom],'score':score,'class_id':cls}

def conf(**kwargs):return AnalysisConfig(min_hits=2,confirm_seconds=.1,**kwargs)

def test_iou_and_partial_assignment():
    assert iou_matrix([[0,0,10,10]],[[0,0,10,10]])[0,0]==1
    pairs,ur,uc=partial_assignment(np.array([[.1,1e6],[.2,.9]]),.7)
    assert pairs==[(0,0)] and ur==[1] and uc==[1]

def test_partial_matching_does_not_steal_gated_match():
    pairs,_,_=partial_assignment(np.array([[.1,.6],[.6,1e6]]),.65)
    assert pairs==[(0,0)]  # cost .1 + one unmatched is better than two weak .6 assignments

def test_low_scores_do_not_start_tracks():
    t=Tracker(conf())
    for i in range(10):assert t.update([det(score=.2)],i*.1)[0]==[]

def test_temporal_confirmation_and_no_duplicate_observation():
    e=EventEngine(conf());events=[]
    for i in range(20):
        rows,out=e.update([det(200+i)],i*.1,100+i*.1,(480,640,3));events+=out
    assert len(events)==1 and events[0]['code']=='PESSOA_OBSERVADA'
    assert len(rows)==1 and rows[0]['id']==1

def test_isolated_detection_not_recorded():
    e=EventEngine(conf());assert not e.update([det()],0,100,(480,640,3))[1]
    assert not e.update([],2.1,102.1,(480,640,3))[1]

def test_short_occlusion_keeps_id():
    t=Tracker(conf())
    t.update([det()],0);a,_=t.update([det(202)],.2)
    assert a[0].confirmed
    current,expired=t.update([],.4);assert current==[] and expired==[]
    b,_=t.update([det(206)],.6);assert b[0].id==a[0].id

def test_low_score_only_recovers_confirmed_track():
    t=Tracker(conf());t.update([det()],0);t.update([det()],.2)
    rows,_=t.update([det(score=.2)],.4)
    assert rows[0].confirmed and rows[0].id==1
    other=Tracker(conf());other.update([det()],0)
    assert other.update([det(score=.2)],.2)[0]==[]

def test_class_mismatch_does_not_reassign_identity():
    t=Tracker(conf());t.update([det()],0)
    current,_=t.update([det(cls=67)],.2)
    assert current[0].id==2 and current[0].class_id==67

def test_lost_not_exit_not_theft():
    e=EventEngine(conf());e.update([det()],0,100,(480,640,3));e.update([det()],.2,100.2,(480,640,3))
    rows,events=e.update([],3,103,(480,640,3))
    assert rows==[] and [e['code'] for e in events]==['RASTREAMENTO_PERDIDO']

def test_expired_track_gets_new_id():
    t=Tracker(conf());t.update([det()],0);t.update([det()],.2)
    rows,expired=t.update([det()],3)
    assert rows[0].id==2 and expired[0].id==1

def test_session_ids_are_distinct():
    a,b=EventEngine(conf()),EventEngine(conf());assert a.session!=b.session

def test_duplicate_timestamp_rejected():
    t=Tracker(conf());t.update([],1)
    with pytest.raises(ValueError):t.update([],1)

def test_motion_covariance_remains_finite():
    m=MotionFilter([0,0,60,120])
    for i in range(200):m.predict(.2);m.update([i,0,i+60,120])
    assert np.isfinite(m.p).all() and np.linalg.eigvalsh(m.p).min()>0

@pytest.mark.parametrize('positive,expected',[(True,'SAIDA_LINHA'),(False,'ENTRADA_LINHA')])
def test_finite_line_crossing_with_confirmation(positive,expected):
    e=EventEngine(conf(line=(.5,0,.5,1),positive_is_entry=positive));events=[]
    for i,x in enumerate([410,415,420,450,480,520,535,545]):
        _,out=e.update([det(x)],i*.1,100+i*.1,(480,1000,3));events+=out
    assert [v['code'] for v in events]==['PESSOA_OBSERVADA',expected]

def test_line_extension_outside_segment_not_counted():
    e=EventEngine(conf(line=(.5,.4,.5,.8)));events=[]
    for i,x in enumerate([410,415,420,450,480,520,535,545]):
        _,out=e.update([det(x,bottom=150)],i*.1,100+i*.1,(480,1000,3));events+=out
    assert [v['code'] for v in events]==['PESSOA_OBSERVADA']

def test_first_appearance_inside_not_entry():
    e=EventEngine(conf(line=(.5,0,.5,1)));events=[]
    for i in range(10):events+=e.update([det(700)],i*.1,100+i*.1,(480,1000,3))[1]
    assert [v['code'] for v in events]==['PESSOA_OBSERVADA']

def test_crossing_after_observation_gap_not_inferred():
    e=EventEngine(conf(line=(.5,0,.5,1)));events=[]
    for t,x in [(0,470),(.1,470),(.2,470),(1.1,530),(1.2,530)]:events+=e.update([det(x)],t,100+t,(480,1000,3))[1]
    assert not any('LINHA' in ev['code'] for ev in events)

def test_segment_math():
    assert segments_intersect((0,5),(10,5),(5,0),(5,10))
    assert not segments_intersect((0,15),(10,15),(5,0),(5,10))

def test_object_appearance_is_category_not_removal():
    e=EventEngine(conf());e.update([det(cls=67)],0,100,(480,640,3))
    _,out=e.update([det(cls=67)],.2,100.2,(480,640,3))
    assert out[0]['code']=='OBJETO_OBSERVADO' and out[0]['class_name']=='celular'
