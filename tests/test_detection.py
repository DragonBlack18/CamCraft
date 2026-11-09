from pathlib import Path
import numpy as np
import pytest
from vision_app.settings import AnalysisConfig,SettingsStore
from vision_app.detector import preprocess,decode,crop_region,GRID,STRIDES,HogDetector,YoloXDetector
from vision_app.classes import NAMES,allowed
from vision_app.model import MODEL_FILE,verified

def raw_detection(class_id=0,score=.9,center=(240,240),wh=(80,120),index=0):
    out=np.zeros((1,8400,85),np.float32)
    out[0,index,:2]=np.array(center)/STRIDES[index]-GRID[index]
    out[0,index,2:4]=np.log(np.array(wh)/STRIDES[index])
    out[0,index,4]=1;out[0,index,5+class_id]=score
    return out

def test_class_order():
    assert len(NAMES)==80 and NAMES[0]=='pessoa' and NAMES[67]=='celular'
    assert allowed('people')=={0} and 67 in allowed('indoor') and 7 not in allowed('indoor')

def test_letterbox_rgb_float_preserves_scale():
    img=np.zeros((320,640,3),np.uint8);img[:]=(10,20,30)
    blob,r=preprocess(img)
    assert blob.shape==(1,3,640,640) and blob.dtype==np.float32 and r==1
    assert list(blob[0,:,0,0])==[30,20,10]
    assert list(blob[0,:,500,100])==[114,114,114]

@pytest.mark.parametrize('shape',[(720,1280),(480,640),(1080,1920),(1080,480)])
def test_letterbox_aspect(shape):
    h,w=shape;blob,r=preprocess(np.zeros((h,w,3),np.uint8))
    assert blob.shape==(1,3,640,640) and r==min(640/h,640/w)

def test_decode_box_offset_and_scale():
    d=decode(raw_detection(),(320,320,3),2,AnalysisConfig(),offset=(100,50))[0]
    assert d['box']==pytest.approx([200,140,240,200]) and d['class_id']==0
    assert d['score']==pytest.approx(.9)

def test_filter_classes():
    assert decode(raw_detection(67),(640,640,3),1,AnalysisConfig(classes='people'))==[]
    assert decode(raw_detection(67),(640,640,3),1,AnalysisConfig(classes='indoor'))[0]['class_id']==67

def test_nms_class_aware():
    x=raw_detection(index=0)
    y=raw_detection(index=1)
    y[0,1,5]=0;y[0,1,5+67]=.8
    x[0,1]=y[0,1]
    assert len(decode(x,(640,640,3),1,AnalysisConfig()))==2
    x[0,1,5+67]=0;x[0,1,5]=.8
    assert len(decode(x,(640,640,3),1,AnalysisConfig()))==1

def test_nan_filtered_and_shape_rejected():
    x=raw_detection();x[0,0,0]=np.nan
    assert decode(x,(640,640,3),1,AnalysisConfig())==[]
    with pytest.raises(ValueError):decode(np.zeros((1,100,85)),(640,640,3),1,AnalysisConfig())

def test_padding_candidates_not_mapped_outside_frame():
    x=raw_detection(center=(300,550),wh=(20,40))
    assert decode(x,(320,640,3),1,AnalysisConfig())==[]

def test_crop_coordinates():
    frame=np.zeros((480,640,3),np.uint8)
    crop,offset=crop_region(frame,(.25,.25,.75,.75))
    assert crop.shape==(240,320,3) and offset==(160,120)

@pytest.mark.parametrize('values',[
 {'confidence':.1},{'threads':0},{'max_fps':60},{'roi':(.5,.5,.4,.6)},
 {'line':(.5,.5,.5,.5)},{'roi':(0,0,2,1)},{'roi':(0,0,float('nan'),1)}])
def test_invalid_config(values):
    with pytest.raises(ValueError):AnalysisConfig(**values)

def test_settings_atomic_roundtrip(tmp_path):
    store=SettingsStore(tmp_path);cfg=AnalysisConfig(roi=(.1,.1,.9,.9),line=(.5,0,.5,1))
    store.put('abc',cfg);assert SettingsStore(tmp_path).get('abc')==cfg
    store.get('abc').confidence=.8;assert store.get('abc').confidence==.60

def test_corrupt_settings_preserved(tmp_path):
    p=tmp_path/'analysis.json';p.write_text('{bad')
    with pytest.raises(ValueError):SettingsStore(tmp_path)
    assert p.read_text()=='{bad'

def test_hog_real_blank_frame_no_fake_detections():
    d=HogDetector(None,AnalysisConfig(engine='hog'))
    assert d.detect(np.zeros((240,320,3),np.uint8))==[]
    assert d.detect(np.zeros((64,32,3),np.uint8))==[]

def test_real_yolox_execution_when_weights_installed():
    path=Path(__file__).resolve().parents[1]/'models'/MODEL_FILE
    if not verified(path):pytest.skip('Modelo neural não disponível neste ambiente; inferência YOLOX e acurácia real não verificadas.')
    model=YoloXDetector(path,AnalysisConfig())
    result=model.detect(np.full((480,640,3),114,np.uint8))
    assert isinstance(result,list) and len(result)<=100
