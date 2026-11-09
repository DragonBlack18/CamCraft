"""Conservative temporal event logic. Loss is NOT exit, disappearance is NOT theft."""
from __future__ import annotations
import math
import uuid
from dataclasses import dataclass
from .classes import NAMES
from .tracker import Tracker
from .settings import AnalysisConfig


def side(point,line,margin):
    x,y=point;x1,y1,x2,y2=line
    length=math.hypot(x2-x1,y2-y1)
    d=((x2-x1)*(y-y1)-(y2-y1)*(x-x1))/max(length,1e-9)
    return 1 if d>margin else -1 if d < -margin else 0


def segments_intersect(p,q,a,b):
    def cross(u,v):return u[0]*v[1]-u[1]*v[0]
    r=(q[0]-p[0],q[1]-p[1]);s=(b[0]-a[0],b[1]-a[1])
    den=cross(r,s)
    if abs(den)<1e-8:return False
    ap=(a[0]-p[0],a[1]-p[1])
    t=cross(ap,s)/den;u=cross(ap,r)/den
    return 0<=t<=1 and 0<=u<=1


@dataclass
class Crossing:
    stable: int=0
    pending: int=0
    count: int=0
    stable_point: tuple|None=None
    stable_time: float=0
    eligible: bool=False
    last_cross: float=-1e9


class EventEngine:
    def __init__(self,cfg:AnalysisConfig,session=None):
        self.cfg=cfg
        self.session=session or uuid.uuid4().hex[:12]
        self.tracker=Tracker(cfg); self.crossings={}

    def event(self,code,t,utc,extra=None):
        return {'code':code,'event_id':uuid.uuid4().hex,'session':self.session,
                'track_id':f'{self.session}:{t.id:05d}','local_id':t.id,'class_id':t.class_id,
                'class_name':NAMES[t.class_id],'score':round(t.score,5),'box':t.box,
                'frame_utc':utc,**(extra or {})}

    def update(self,detections,stamp,utc,shape):
        current,expired=self.tracker.update(detections,stamp)
        events=[]
        for t in expired:
            self.crossings.pop(t.id,None)
            if t.announced:
                events.append(self.event('RASTREAMENTO_PERDIDO',t,utc,{'absence_s':stamp-t.last_seen,'conclusion':'Não comprova saída ou retirada.'}))
        h,w=shape[:2]
        line=None if self.cfg.line is None else tuple(v*(w if i%2==0 else h) for i,v in enumerate(self.cfg.line))
        for t in current:
            if not t.confirmed:continue
            if not t.announced:
                t.announced=True
                events.append(self.event('PESSOA_OBSERVADA' if t.class_id==0 else 'OBJETO_OBSERVADO',t,utc))
            if line is None or t.class_id!=0:continue
            point=((t.box[0]+t.box[2])/2,t.box[3])
            s=side(point,line,margin=max(3,.012*min(w,h)))
            c=self.crossings.setdefault(t.id,Crossing())
            if s==0:continue
            if s==c.stable:
                c.pending=0;c.count=0;c.eligible=False
                c.stable_point=point;c.stable_time=stamp
                continue
            if c.pending!=s:
                c.pending=s;c.count=1
                c.eligible=(c.stable!=0 and c.stable_point is not None and stamp-c.stable_time<=.75
                            and segments_intersect(c.stable_point,point,line[:2],line[2:]))
            else:c.count+=1
            if c.count>=2:
                if c.eligible and stamp-c.last_cross>=1:
                    entering=(s==1)==self.cfg.positive_is_entry
                    events.append(self.event('ENTRADA_LINHA' if entering else 'SAIDA_LINHA',t,utc,
                        {'line':self.cfg.line,'direction':'negativo→positivo' if s==1 else 'positivo→negativo',
                         'conclusion':'Cruzamento observado da linha configurada; não é identidade civil.'}))
                    c.last_cross=stamp
                c.stable=s;c.stable_point=point;c.stable_time=stamp;c.pending=0;c.count=0;c.eligible=False
        # Only measured boxes from THIS frame are returned; no ghosts from prediction.
        return [t.public() for t in current],events
