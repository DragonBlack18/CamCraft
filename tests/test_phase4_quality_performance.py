import hashlib,json,sys,threading,time
from pathlib import Path
import cv2
import numpy as np
import pytest
from vision_app.quality import evaluate_manifest,acceptance_gate
from vision_app.performance import PerformanceWindow,next_analysis_time
from vision_app.jobs import ExternalJobs


class FakeDetector:
    def detect(self,frame):
        return [{'class_id':0,'score':.8,'box':[10,10,30,30]}] if frame[0,0,0]>50 else []


def manifest(tmp_path,split='test'):
    rows=[]
    for i in range(4):
        frame=np.full((80,120,3),100 if i%2 else 10,np.uint8);frame[0,1]=i
        ok,data=cv2.imencode('.png',frame);p=tmp_path/f'{i}.png';p.write_bytes(data.tobytes())
        rows.append({'image':p.name,'objects':[{'class_id':0,'box':[10,10,30,30]}] if i%2 else [],'group':'g'+str(i)})
    p=tmp_path/'m.json';p.write_text(json.dumps({'fully_labeled':True,'class_ids':[0],'split':split,'images':rows}))
    return p


def test_evaluation_counts_positives_negatives_and_no_fake_gate(tmp_path):
    report=evaluate_manifest(manifest(tmp_path),FakeDetector())
    assert report['positive_images']==2 and report['negative_images']==2
    assert report['results']['0.45']['overall']['tp']==2
    assert report['results']['0.45']['overall']['precision']==1
    gate=acceptance_gate(report);assert gate['decision']=='NOT_ACCEPTED' and not gate['checks']['sample_count']
    assert acceptance_gate(report,min_images=4,min_positive=2,min_negative=2,min_class_objects=2)['decision']=='PASS'


def test_sweep_never_tunes_on_test(tmp_path):
    with pytest.raises(ValueError,match='split val'):evaluate_manifest(manifest(tmp_path,'test'),FakeDetector(),sweep=True)
    r=evaluate_manifest(manifest(tmp_path,'val'),FakeDetector(),sweep=True)
    assert len(r['results'])==7 and acceptance_gate(r)['decision']=='NOT_ACCEPTED'


def test_duplicate_images_cannot_inflate_sample_size(tmp_path):
    p=manifest(tmp_path);data=json.loads(p.read_text());data['images'].append(data['images'][0]);p.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='repetida'):evaluate_manifest(p,FakeDetector())


def test_unannotated_scope_or_external_paths_rejected(tmp_path):
    p=manifest(tmp_path);d=json.loads(p.read_text());d['fully_labeled']=False;p.write_text(json.dumps(d))
    with pytest.raises(ValueError):evaluate_manifest(p,FakeDetector())
    d['fully_labeled']=True;d['images'][0]['image']='../x.png';p.write_text(json.dumps(d))
    with pytest.raises(ValueError):evaluate_manifest(p,FakeDetector())


def test_cancel_evaluation_no_report(tmp_path):
    with pytest.raises(InterruptedError):evaluate_manifest(manifest(tmp_path),FakeDetector(),cancelled=lambda:True)


def test_frame_matching_prefers_maximum_cardinality(monkeypatch):
    from vision_app import evaluation
    monkeypatch.setattr(evaluation,'iou_matrix',lambda a,b:np.array([[.99,.51],[.51,0.0]]))
    d={'class_id':0,'box':[0,0,20,20]}
    assert evaluation.match_frame([d,d],[d,d])[0]['tp']==2


def test_bounded_stats_and_invalid_values():
    p=PerformanceWindow(capacity=5)
    for i in range(30):p.record(inference_ms=i,object_ms=2,render_ms=3,age_ms=4)
    p.record(inference_ms=float('nan'),object_ms=2,render_ms=3,age_ms=4)
    assert p.snapshot()['samples']==5 and p.snapshot()['percentiles']['inference_ms']['p50']==27


def test_pacing_bounds_and_never_changes_threshold():
    assert next_analysis_time(1,1.2,10,adaptive=False)==1.2
    assert next_analysis_time(1,1.2,10,adaptive=True,duty=.5)==pytest.approx(1.4)
    assert next_analysis_time(1,1.01,10,adaptive=True)==1.1
    with pytest.raises(ValueError):next_analysis_time(1,2,10,duty=0)


def test_jobs_complete_fail_and_timeout(tmp_path):
    jobs=ExternalJobs()
    assert jobs.run([sys.executable,'-c','print("ok")'],tmp_path/'ok.log')['exit_code']==0
    with pytest.raises(RuntimeError):jobs.run([sys.executable,'-c','raise SystemExit(1)'],tmp_path/'bad.log')
    with pytest.raises(TimeoutError):jobs.run([sys.executable,'-c','import time;time.sleep(5)'],tmp_path/'timeout.log',timeout=.2)
    assert jobs.process is None
    jobs.close()
    with pytest.raises(RuntimeError):jobs.run([sys.executable,'-c','print(1)'],tmp_path/'closed.log')


def test_job_cancel_terminates_child(tmp_path):
    jobs=ExternalJobs();errors=[]
    def work():
        try:jobs.run([sys.executable,'-c','import time;time.sleep(10)'],tmp_path/'cancel.log')
        except Exception as e:errors.append(e)
    t=threading.Thread(target=work);t.start()
    for _ in range(100):
        if jobs.process is not None:break
        time.sleep(.01)
    jobs.cancel.set();t.join(3)
    assert not t.is_alive() and isinstance(errors[0],InterruptedError) and jobs.process is None


def test_gate_rejects_missing_requested_class(tmp_path):
    report=evaluate_manifest(manifest(tmp_path),FakeDetector())
    report['classes'].append(39)
    gate=acceptance_gate(report,min_images=4,min_positive=2,min_negative=2,min_class_objects=2)
    assert gate['decision']=='NOT_ACCEPTED'
    assert not gate['class_checks']['39']['labeled_objects']


def test_gate_does_not_hide_weak_class_behind_overall_average(tmp_path):
    report=evaluate_manifest(manifest(tmp_path),FakeDetector())
    report['classes'].append(39)
    report['results']['0.45']['per_class']['39']={'tp':5,'fp':10,'fn':5,'precision':1/3,'recall':.5}
    gate=acceptance_gate(report,min_images=4,min_positive=2,min_negative=2,min_class_objects=2)
    assert gate['checks']['precision'] and gate['checks']['recall']
    assert gate['decision']=='NOT_ACCEPTED' and not gate['checks']['all_requested_classes']


def test_gate_needs_minimum_examples_per_class(tmp_path):
    report=evaluate_manifest(manifest(tmp_path),FakeDetector())
    gate=acceptance_gate(report,min_images=4,min_positive=2,min_negative=2)
    assert gate['decision']=='NOT_ACCEPTED' and not gate['class_checks']['0']['labeled_objects']
