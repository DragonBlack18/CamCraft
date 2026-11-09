import json
from contextlib import closing
import pytest
from vision_app.review import ReviewRepository


def emit(store,i,code='AUSENCIA_CONFIRMADA'):
    store.emit('cam',code,'Objeto '+str(i),payload={'event_id':'event-'+str(i),'object_name':'Item '+str(i)})


def test_stable_pagination_ignores_new_rows(store):
    repo=ReviewRepository(store)
    for i in range(7):emit(store,i)
    store.flush();p=repo.page(limit=3)
    assert [r['id'] for r in p['rows']]==[7,6,5]
    emit(store,8);store.flush()
    q=repo.page(limit=3,before=p['next_before'],ceiling=p['ceiling'])
    assert [r['id'] for r in q['rows']]==[4,3,2]
    assert repo.page(limit=3,before=q['next_before'],ceiling=p['ceiling'])['rows'][0]['id']==1
    assert repo.page()['rows'][0]['id']==8


def test_filters_parameterized_literal_search(store):
    repo=ReviewRepository(store);emit(store,1);emit(store,2,'OTHER');store.flush()
    assert len(repo.page(important_only=True)['rows'])==1
    assert not repo.page(text="' OR 1=1 --")['rows']
    assert not repo.page(text='%')['rows']
    assert len(repo.page(text='Item 1')['rows'])==1
    assert len(repo.page(camera_id='other')['rows'])==0


def test_reviews_transactional_append_only_with_notes(store):
    repo=ReviewRepository(store);emit(store,1);store.flush();original=repo.get(1)
    repo.add(1,'FALSO_POSITIVO',note='Objeto apenas encoberto',operator='Davi')
    repo.add(1,'INCONCLUSIVO',note='Revisão posterior')
    assert repo.get(1)==original
    assert len(repo.reviews(1))==2
    assert repo.page(decision='INCONCLUSIVO',important_only=True)['rows'][0]['id']==1
    assert not repo.page(decision='PENDENTE',important_only=True)['rows']
    assert repo.verify_chain()['verified_records']==2


def test_legacy_phase3_review_remains_visible(store):
    repo=ReviewRepository(store);emit(store,1);store.flush()
    store.emit('cam','REVISAO_EVENTO','old',payload={'reviewed_row_id':1,'review_id':'legacy','decision':'CONFIRMADO'});store.flush()
    assert repo.reviews(1)[0]['legacy_phase3']
    assert repo.page(decision='CONFIRMADO',important_only=True)['rows'][0]['id']==1


def test_chain_detects_modified_body_and_columns(store):
    repo=ReviewRepository(store);emit(store,1);store.flush();repo.add(1,'CONFIRMADO')
    with closing(store.connect()) as db:
        db.execute("UPDATE audit_reviews SET decision='INCONCLUSIVO'");db.commit()
    with pytest.raises(ValueError):repo.verify_chain()


def test_review_snapshot_survives_original_event_retention(store):
    repo=ReviewRepository(store);emit(store,1);store.flush();repo.add(1,'CONFIRMADO')
    with closing(store.connect()) as db:db.execute('DELETE FROM events WHERE id=1');db.commit()
    assert repo.reviews(1)[0]['event_snapshot']['code']=='AUSENCIA_CONFIRMADA'
    assert repo.verify_chain()['verified_records']==1


@pytest.mark.parametrize('decision,note,operator',[('wrong','','x'),('CONFIRMADO','x'*2001,'x'),('CONFIRMADO','','')])
def test_invalid_reviews_rejected(store,decision,note,operator):
    repo=ReviewRepository(store);emit(store,1);store.flush()
    with pytest.raises(ValueError):repo.add(1,decision,note=note,operator=operator)
    assert repo.verify_chain()['verified_records']==0
