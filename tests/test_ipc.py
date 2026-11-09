import multiprocessing as mp
import time
import numpy as np
from vision_foundation.ipc import FrameSlot


def test_coherent_roundtrip_and_independent_copy():
    slot=FrameSlot(mp.get_context('spawn'),320,240)
    image=np.full((240,320,3),127,np.uint8)
    assert slot.publish(image,b'jpeg',{'sequence':1,'received_monotonic':time.monotonic()})
    packet=slot.read(raw=True,jpeg=True)
    assert packet.metadata['sequence']==1 and packet.jpeg==b'jpeg'
    assert np.array_equal(packet.bgr,image)
    packet.bgr[:]=0
    assert slot.read(raw=True).bgr.mean()==127


def test_only_latest_and_fixed_memory():
    slot=FrameSlot(mp.get_context('spawn'),320,240)
    allocated=slot.allocated_bytes
    for seq in range(1,101):
        image=np.full((240,320,3),seq,np.uint8)
        assert slot.publish(image,b'j',{'sequence':seq})
    packet=slot.read(raw=True)
    assert packet.metadata['sequence']==100
    assert packet.bgr.mean()==100
    assert slot.allocated_bytes==allocated


def test_deadline_when_lock_is_held():
    slot=FrameSlot(mp.get_context('spawn'),320,240)
    slot.lock.acquire()
    start=time.monotonic()
    try:assert slot.read(raw=True) is None
    finally:slot.lock.release()
    assert time.monotonic()-start < .2


def test_oversize_rejected():
    slot=FrameSlot(mp.get_context('spawn'),320,240)
    assert not slot.publish(np.zeros((500,500,3),np.uint8),b'x',{'sequence':1})
    assert slot.read() is None


def test_structured_status():
    slot=FrameSlot(mp.get_context('spawn'),320,240)
    slot.set_status('RUNNING','SYNTHETIC')
    assert slot.get_status()=={'code':'RUNNING','backend':'SYNTHETIC','detail':''}
