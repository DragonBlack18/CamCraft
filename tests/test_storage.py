import sqlite3
from vision_foundation.storage import EventStore


def test_persistence_and_filtering(tmp_path):
    p=tmp_path/'events.sqlite3'
    store=EventStore(p)
    for i in range(20):store.emit('a' if i%2 else 'b','TEST','Mensagem',payload={'i':i})
    store.metric('a',{'fps':12})
    assert store.flush()
    assert len(store.events())==20
    assert len(store.events('a'))==10
    assert len(store.events(before=10))==9
    assert store.metrics('a')[0]['fps']==12
    assert store.health()['healthy']
    store.close()
    with sqlite3.connect(p) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    store=EventStore(p)
    assert len(store.events())==20
    store.close()


def test_queue_is_bounded(tmp_path,monkeypatch):
    # Pause a LIVE writer. Closed stores now reject all messages, rather than
    # accepting unpersistable entries into a queue with no consumer.
    import threading
    gate=threading.Event();original=EventStore._writer
    def delayed(store):
        gate.wait(5);original(store)
    monkeypatch.setattr(EventStore,'_writer',delayed)
    store=EventStore(tmp_path/'events.sqlite3',queue_size=2)
    try:
        for _ in range(10):store.emit(None,'TEST','Test')
        assert store.queue.qsize()==2
        assert store.dropped==8
        assert not store.health()['healthy']
    finally:
        gate.set();store.close()
    assert len(store.events())==2


def test_closed_store_rejects_unpersistable_messages(tmp_path):
    store=EventStore(tmp_path/'events.sqlite3',queue_size=2);store.close()
    assert store.emit(None,'AFTER_CLOSE','Not persisted') is False
    assert store.queue.qsize()==0 and store.dropped==1
