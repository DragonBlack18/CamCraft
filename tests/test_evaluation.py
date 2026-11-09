import pytest
from vision_app.evaluation import match_frame,summarize

def d(cid=0,box=(0,0,20,20)):return {'class_id':cid,'box':list(box)}
def test_perfect_and_duplicate():
    a=match_frame([d(),d()],[d()]);assert a[0]=={'tp':1,'fp':1,'fn':0}
    assert summarize([a])['overall']['precision']==.5

def test_wrong_class_not_a_match():
    r=summarize([match_frame([d(1)],[d(0)])]);assert r['overall']['tp']==0 and r['overall']['fp']==r['overall']['fn']==1

def test_negative_and_empty_metrics():
    assert match_frame([],[])=={}
    assert summarize([{}])['overall']['precision'] is None
    assert match_frame([d()],[])[0]['fp']==1
    assert match_frame([],[d()])[0]['fn']==1

@pytest.mark.parametrize('v',[0,-.1,1.01])
def test_iou_limits(v):
    with pytest.raises(ValueError):match_frame([],[],v)

def test_insufficient_overlap():
    assert match_frame([d(box=(30,30,50,50))],[d()])[0]=={'tp':0,'fp':1,'fn':1}
