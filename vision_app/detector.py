"""OpenCV Zoo YOLOX-S adapter. Independent implementation using documented preprocessing.

Reference: OpenCV Zoo object_detection_yolox (Apache-2.0). Its exported graph
expects RGB float32 0..255, top-left letterbox 114, and explicit grid decoding.
This is NOT interchangeable with arbitrary YOLO ONNX exports.
"""
from __future__ import annotations
import math
from pathlib import Path
import cv2
import numpy as np
from .classes import allowed
from .model import verified
from .settings import AnalysisConfig


def crop_region(frame, roi):
    h,w = frame.shape[:2]
    if roi is None: return frame, (0,0)
    x1,y1,x2,y2 = roi
    a,b = max(0,int(x1*w)), max(0,int(y1*h))
    c,d = min(w,max(a+1,int(x2*w))), min(h,max(b+1,int(y2*h)))
    return frame[b:d,a:c], (a,b)


def preprocess(frame: np.ndarray):
    if frame is None or frame.ndim != 3 or frame.shape[2] != 3 or frame.size == 0:
        raise ValueError('Quadro BGR inválido.')
    h,w = frame.shape[:2]
    ratio = min(640/w,640/h)
    resized = cv2.resize(frame, (max(1,int(w*ratio)),max(1,int(h*ratio))), interpolation=cv2.INTER_LINEAR)
    # Color conversion is mandatory for the OpenCV Zoo graph.
    padded = np.full((640,640,3),114,np.uint8)
    padded[:resized.shape[0], :resized.shape[1]] = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    return np.ascontiguousarray(padded.transpose(2,0,1)[None], dtype=np.float32), ratio


def anchors():
    grid,strides = [],[]
    for stride in (8,16,32):
        y,x = np.mgrid[:640//stride,:640//stride]
        g = np.stack((x,y),axis=-1).reshape(-1,2)
        grid.append(g); strides.append(np.full((len(g),1),stride))
    return np.concatenate(grid).astype(np.float32), np.concatenate(strides).astype(np.float32)

GRID, STRIDES = anchors()


def decode(outputs, frame_shape, ratio, cfg: AnalysisConfig, offset=(0,0)) -> list[dict]:
    out = np.asarray(outputs)
    if out.shape != (1,8400,85):
        raise ValueError(f'Saída incompatível com o YOLOX verificado: {out.shape}')
    p = out[0]
    finite = np.isfinite(p).all(axis=1)
    scores = p[:,4,None] * p[:,5:]
    classes = scores.argmax(axis=1)
    values = scores[np.arange(len(p)),classes]
    mask = finite & (values >= cfg.low_confidence) & np.isin(classes, list(cfg.class_ids()))
    # Reject ambiguous competing classes before applying the allow-list. Never choose
    # a lower-ranked allowed category to relabel a disallowed winner (e.g. car -> person).
    if cfg.class_margin > 0:
        top_two = np.partition(scores, -2, axis=1)[:, -2:]
        dominance = (top_two[:, 1] - top_two[:, 0]) / np.maximum(top_two[:, 1], 1e-8)
        mask &= dominance >= cfg.class_margin
    indices = np.flatnonzero(mask)
    if not len(indices): return []
    # Bound NMS work on adversarial/noisy input; strongest candidates first.
    indices = indices[np.argsort(values[indices])[::-1][:2000]]
    center = (p[indices,:2] + GRID[indices]) * STRIDES[indices]
    wh = np.exp(np.clip(p[indices,2:4],-10,10)) * STRIDES[indices]
    xy = (center - wh/2)/ratio
    wh = wh/ratio
    boxes = np.c_[xy,wh]
    scores_v = np.clip(values[indices],0,1)
    classes_v = classes[indices]
    keep = cv2.dnn.NMSBoxesBatched(boxes.tolist(),scores_v.tolist(),classes_v.tolist(),cfg.low_confidence,cfg.nms_iou)
    result = []
    h,w = frame_shape[:2]
    for k in np.asarray(keep,dtype=int).reshape(-1):
        x,y,bw,bh = boxes[k]
        x1,y1 = max(0,float(x)),max(0,float(y))
        x2,y2 = min(w,float(x+bw)),min(h,float(y+bh))
        if x2-x1 < 3 or y2-y1 < 3: continue
        result.append({'box':[x1+offset[0],y1+offset[1],x2+offset[0],y2+offset[1]],
                       'score':float(scores_v[k]),'class_id':int(classes_v[k])})
    return sorted(result,key=lambda d:d['score'],reverse=True)[:cfg.max_detections]


class YoloXDetector:
    label = 'YOLOX-S / OpenCV CPU'
    def __init__(self, path: Path, cfg: AnalysisConfig):
        if not verified(path):
            raise FileNotFoundError('Modelo YOLOX ausente ou hash inválido. Prepare o modelo antes de iniciar.')
        self.cfg=cfg
        cv2.setNumThreads(cfg.threads)
        cv2.setUseOptimized(True)
        self.net=cv2.dnn.readNetFromONNX(str(path))
        self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)

    def detect(self, frame):
        crop, offset = crop_region(frame,self.cfg.roi)
        blob,ratio = preprocess(crop)
        self.net.setInput(blob)
        output = self.net.forward()
        return decode(output,crop.shape,ratio,self.cfg,offset)


class HogDetector:
    """Explicit diagnostic-only fallback. NOT an object detector and no silent fallback."""
    label = 'HOG diagnóstico / apenas pedestres'
    def __init__(self, path, cfg):
        self.cfg=cfg
        cv2.setNumThreads(cfg.threads)
        self.hog=cv2.HOGDescriptor()
        self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

    def detect(self, frame):
        crop,offset = crop_region(frame,self.cfg.roi)
        h,w=crop.shape[:2]
        ratio=min(1,640/w,480/h)
        if ratio<1: crop=cv2.resize(crop,(int(w*ratio),int(h*ratio)))
        if crop.shape[0]<128 or crop.shape[1]<64: return []
        boxes,weights=self.hog.detectMultiScale(crop,winStride=(8,8),padding=(8,8),scale=1.08)
        if not len(boxes): return []
        # SVM margin mapped only for common tracker threshold; NOT a calibrated probability.
        scores=[1/(1+math.exp(-max(-20,min(20,float(v))))) for v in weights]
        keep=cv2.dnn.NMSBoxes(boxes.tolist(),scores,self.cfg.confidence,.4)
        result=[]
        for k in np.asarray(keep,dtype=int).reshape(-1):
            x,y,bw,bh=boxes[k]
            result.append({'box':[float(x/ratio+offset[0]),float(y/ratio+offset[1]),float((x+bw)/ratio+offset[0]),float((y+bh)/ratio+offset[1])],
                           'score':scores[k],'class_id':0})
        return result[:self.cfg.max_detections]


class RegionOnlyDetector:
    """Explicit reference-only mode. No person/object neural detections are fabricated."""
    label = 'Referencias locais / SEM deteccao de pessoas'
    def __init__(self,path,cfg):
        self.cfg=cfg;cv2.setNumThreads(cfg.threads)
    def detect(self,frame):
        if frame is None or frame.ndim!=3:raise ValueError('Quadro inválido.')
        return []


def create_detector(path, cfg):
    if cfg.engine=='regions':return RegionOnlyDetector(path,cfg)
    return HogDetector(path,cfg) if cfg.engine=='hog' else YoloXDetector(path,cfg)
