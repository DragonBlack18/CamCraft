import json,zipfile
import numpy as np
import pytest
from vision_app.dataset import DatasetStore,validate_boxes
from vision_app.safe_archive import verify_archive


def sample(store,i=1,group=None):
    image=np.full((80,120,3),i,np.uint8);image[10:30,10:30]=(10,20,200)
    return store.capture(image,{'session':'session'+str(i),'sequence':i},camera_id='cam',group=group)


def labeled(store,i,group=None,boxes=None):
    r=sample(store,i,group)
    return store.annotate(r['id'],boxes if boxes is not None else [{'class_id':0,'box':[10,10,30,30]}],class_ids=[0],complete=True,expected_revision=0)


def test_capture_and_explicit_negative(tmp_path):
    s=DatasetStore(tmp_path);r=sample(s);assert r['state']=='DRAFT'
    r=s.annotate(r['id'],[],class_ids=[0],complete=True,expected_revision=0)
    assert r['state']=='LABELED' and r['objects']==[] and r['revision']==1
    assert (s.folder(r['id'])/'history/r000000.json').is_file()


def test_duplicates_and_revision_conflicts(tmp_path):
    s=DatasetStore(tmp_path);r=labeled(s,1)
    with pytest.raises(ValueError,match='idêntica'):sample(s,1)
    with pytest.raises(ValueError,match='mudou'):s.annotate(r['id'],[],class_ids=[0],complete=True,expected_revision=0)


def test_corrupt_image_cannot_export(tmp_path):
    s=DatasetStore(tmp_path/'data');r=labeled(s,1);(s.folder(r['id'])/'image.png').write_bytes(b'bad')
    with pytest.raises(ValueError):s.export(tmp_path/'out.zip',split=False)


def test_export_groups_no_leakage_three_formats(tmp_path):
    s=DatasetStore(tmp_path/'data')
    for i in range(6):labeled(s,i+1,group='recording-'+str(i//2))
    target=tmp_path/'d.zip';s.export(target)
    assert verify_archive(target)['kind']=='vision-dataset'
    with zipfile.ZipFile(target) as z:
        groups=[]
        for split in ['train','val','test']:
            m=json.loads(z.read(split+'.json'));groups.append(set(m['groups']))
            assert len(m['images'])==2
            coco=json.loads(z.read('coco_'+split+'.json'));assert len(coco['annotations'])==2
            assert coco['categories'][0]['id']==1
            image=m['images'][0]['image'];label=image.replace('images/','labels/').replace('.png','.txt')
            assert z.read(label).startswith(b'0 ')
        assert not groups[0]&groups[1] and not groups[0]&groups[2] and not groups[1]&groups[2]


def test_evaluation_export_omits_drafts_and_retains_negatives(tmp_path):
    s=DatasetStore(tmp_path/'data');sample(s,1);labeled(s,2,boxes=[])
    s.export(tmp_path/'d.zip',split=False)
    with zipfile.ZipFile(tmp_path/'d.zip') as z:
        m=json.loads(z.read('evaluation.json'));assert len(m['images'])==1 and m['images'][0]['objects']==[]


def test_split_requires_independent_groups(tmp_path):
    s=DatasetStore(tmp_path/'data');labeled(s,1);labeled(s,2)
    with pytest.raises(ValueError,match='três grupos'):s.export(tmp_path/'d.zip')


@pytest.mark.parametrize('box',[[0,0,200,20],[10,10,10,20],[-1,0,20,20],[0,float('nan'),10,10]])
def test_invalid_boxes(box):
    with pytest.raises(ValueError):validate_boxes([{'class_id':0,'box':box}],100,100,[0])


def test_scope_must_cover_each_box(tmp_path):
    s=DatasetStore(tmp_path);r=sample(s)
    with pytest.raises(ValueError):s.annotate(r['id'],[{'class_id':39,'box':[10,10,30,30]}],class_ids=[0],complete=True,expected_revision=0)
