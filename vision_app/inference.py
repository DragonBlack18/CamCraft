"""Killable model process. Single outstanding request, bounded JSON reply slot."""
from __future__ import annotations
import ctypes
import json
import time
from pathlib import Path
import numpy as np
from .detector import create_detector
from .settings import AnalysisConfig

class JsonSlot:
    def __init__(self,ctx,capacity=131072):
        self.capacity=capacity
        self.data=ctx.RawArray(ctypes.c_ubyte,capacity)
        self.length=ctx.RawValue(ctypes.c_int,0)
        self.lock=ctx.Lock()
    def put(self,obj):
        data=json.dumps(obj,ensure_ascii=False,allow_nan=False).encode()
        if len(data)>self.capacity:raise ValueError('Resultado excede a capacidade do IPC.')
        if not self.lock.acquire(timeout=.05):return False
        try:
            np.frombuffer(self.data,np.uint8)[:len(data)]=np.frombuffer(data,np.uint8)
            self.length.value=len(data)
        finally:self.lock.release()
        return True
    def get(self):
        if not self.lock.acquire(timeout=.005):return None
        try:
            if self.length.value<=0:return None
            return json.loads(bytes(self.data[:self.length.value]))
        finally:self.lock.release()


def inference_worker(config_data,model_path,frames,replies,stop):
    try:
        replies.put({'state':'LOADING'})
        cfg=AnalysisConfig.model_validate(config_data)
        detector=create_detector(Path(model_path),cfg)
        replies.put({'state':'READY','backend':detector.label})
        last=0
        while not stop.wait(.005):
            meta=frames.read()
            if meta is None or int(meta.metadata['sequence'])==last:continue
            packet=frames.read(raw=True)
            if packet is None:continue
            request=int(packet.metadata['sequence'])
            if request==last:continue
            last=request
            begin=time.monotonic()
            detections=detector.detect(packet.bgr)
            reply={'state':'RESULT','request':request,'detections':detections,
                   'inference_ms':(time.monotonic()-begin)*1000,'backend':detector.label}
            # Never abandon a completed result due to a transient read lock.
            while not stop.is_set() and not replies.put(reply):stop.wait(.005)
    except Exception as exc:
        # Exception classes only; native error strings can contain sensitive filesystem paths.
        replies.put({'state':'ERROR','code':type(exc).__name__,
                     'message':'A análise falhou. Verifique modelo, memória e dependências; exporte o diagnóstico.'})
