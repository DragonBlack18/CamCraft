import json
import numpy as np
import pytest
from vision_app.event_evaluation import evaluate_events
from vision_app.controller import Controller
from vision_app.detector import create_detector
from vision_app.settings import AnalysisConfig


def event(t=10,code='AUSENCIA_CONFIRMADA',actor=None):
    return {'camera_id':'cam','object_id':'o1','code':code,'time_s':t,'actor_track_id':actor}


def test_regions_mode_does_not_fabricate_detections(tmp_path):
    detector=create_detector(tmp_path/'no-model.onnx',AnalysisConfig(engine='regions'))
    assert detector.detect(np.zeros((120,160,3),np.uint8))==[]
    assert 'SEM' in detector.label


def test_event_metrics_one_to_one_duplicates_are_false_positive():
    report=evaluate_events([event(10.1),event(10.2)],[event(10)],monitored_seconds=3600)
    assert (report['tp'],report['fp'],report['fn'])==(1,1,0)
    assert report['precision']==.5 and report['false_events_per_hour']==1


def test_empty_predictions_are_not_100_percent():
    report=evaluate_events([],[event()],monitored_seconds=60)
    assert report['precision'] is None and report['recall']==0 and report['fn']==1


def test_event_names_and_object_ids_must_match():
    report=evaluate_events([event(code='RETORNO_OBSERVADO')],[event()],monitored_seconds=60)
    assert report['tp']==0 and report['fp']==report['fn']==1


def test_actor_abstention_separate_from_wrong_assignment():
    report=evaluate_events([event(10,actor=None),event(20,actor='wrong')],[event(10,actor='a'),event(20,actor='b')],monitored_seconds=100)
    assert report['actor_abstained']==1 and report['actor_wrong']==1


def test_event_metrics_validate_fields():
    with pytest.raises(ValueError):evaluate_events([],[],monitored_seconds=0)
    with pytest.raises(ValueError):evaluate_events([{'time_s':2}],[],monitored_seconds=10)
    with pytest.raises(ValueError):evaluate_events([event(float('nan'))],[],monitored_seconds=10)


def test_review_append_only_preserves_original(tmp_path):
    app=Controller(tmp_path/'data',tmp_path/'models')
    try:
        app.events.emit('cam','AUSENCIA_CONFIRMADA','Teste',payload={'event_id':'evt1','object_id':'obj1'})
        assert app.events.flush()
        row=app.events.events()[0]
        app.review_event(row['id'],'FALSO_POSITIVO');app.events.flush()
        rows=app.events.events()
        assert rows[0]['code']=='REVISAO_EVENTO'
        assert rows[0]['payload']['reviewed_event_id']=='evt1'
        assert rows[1]==row
        with pytest.raises(ValueError):app.review_event(row['id'],'REWRITE')
        with pytest.raises(ValueError):app.review_event(99999,'CONFIRMADO')
    finally:app.close()


def test_event_matching_maximizes_valid_pairs_before_timing_error():
    report=evaluate_events([event(0),event(2)],[event(1.9),event(3.9)],monitored_seconds=10,tolerance_seconds=2)
    assert report['tp']==2 and report['fp']==report['fn']==0
