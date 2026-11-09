"""Deterministic orchestration test doubles; NEVER used by the production detector."""
import time

def controlled_worker(config,model_path,frames,replies,stop):
    replies.put({'state':'READY','backend':'TEST DOUBLE — not neural inference'})
    last=0
    while not stop.wait(.01):
        p=frames.read(raw=True)
        if p is None or p.metadata['sequence']==last:continue
        last=int(p.metadata['sequence'])
        time.sleep(.05)
        replies.put({'state':'RESULT','request':last,'backend':'TEST DOUBLE — not neural inference','inference_ms':50.,
                     'detections':[{'box':[120.,100.,180.,240.],'score':.9,'class_id':0}]})

def lock_crash_worker(config,model_path,frames,replies,stop):
    replies.put({'state':'READY'})
    replies.lock.acquire()
    while True:time.sleep(1)


def slow_worker(config,model_path,frames,replies,stop):
    """Deliberate 450 ms inference delay; a transport test, NOT a neural model."""
    replies.put({'state':'READY','backend':'TEST / fixed 450 ms, NOT neural'})
    last=0
    while not stop.wait(.005):
        p=frames.read(raw=True)
        if p is None or p.metadata['sequence']==last:continue
        last=int(p.metadata['sequence'])
        if stop.wait(.45):return
        replies.put({'state':'RESULT','request':last,'backend':'TEST / fixed 450 ms, NOT neural',
                     'inference_ms':450.,'detections':[]})


def cpu_busy_worker(config,model_path,frames,replies,stop):
    """450 ms of real OpenCV CPU work per request, with NO neural detections.

    Validates competition for CPU/memory only; it does not emulate YOLOX accuracy.
    """
    import cv2
    import numpy as np
    cv2.setNumThreads(config.get('threads',2))
    data=np.random.default_rng(41).random((1024,1024),dtype=np.float32)
    replies.put({'state':'READY','backend':'TEST CPU blur workload / NOT neural'})
    last=0
    while not stop.wait(.005):
        p=frames.read(raw=True)
        if p is None or p.metadata['sequence']==last:continue
        last=int(p.metadata['sequence']);begin=time.monotonic()
        while not stop.is_set() and time.monotonic()-begin<.45:
            cv2.GaussianBlur(data,(9,9),1.5)
        replies.put({'state':'RESULT','request':last,'backend':'TEST CPU blur workload / NOT neural',
            'inference_ms':(time.monotonic()-begin)*1000,'detections':[]})
