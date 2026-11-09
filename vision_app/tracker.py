"""Independent time-aware, two-pass multi-class tracker (not the upstream ByteTrack).

Inspired by ByteTrack's high/low-confidence association principle (arXiv:2110.06864).
Uses a constant-velocity Kalman filter and gated, partial Hungarian assignment.
No facial identity, ReID, biometric descriptors, or cross-camera identity claims.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np
from scipy.optimize import linear_sum_assignment
from .settings import AnalysisConfig


def iou_matrix(a,b):
    a=np.asarray(a,dtype=float).reshape(-1,4); b=np.asarray(b,dtype=float).reshape(-1,4)
    lt=np.maximum(a[:,None,:2],b[None,:,:2]); rb=np.minimum(a[:,None,2:],b[None,:,2:])
    wh=np.maximum(0,rb-lt); inter=wh[:,:,0]*wh[:,:,1]
    aa=np.prod(np.maximum(0,a[:,2:]-a[:,:2]),axis=1)
    bb=np.prod(np.maximum(0,b[:,2:]-b[:,:2]),axis=1)
    return inter/np.maximum(aa[:,None]+bb[None,:]-inter,1e-9)


def partial_assignment(cost,limit):
    """Gates BEFORE optimization; dummy rows/columns implement truly unmatched choices."""
    cost=np.asarray(cost,dtype=float)
    n,m=cost.shape
    if n==0 or m==0: return [],list(range(n)),list(range(m))
    full=np.full((n+m,m+n),1e6,dtype=float)
    full[:n,:m]=np.where(np.isfinite(cost)&(cost<=limit),cost,1e6)
    full[np.arange(n),m+np.arange(n)]=limit/2+1e-7
    full[n+np.arange(m),np.arange(m)]=limit/2+1e-7
    full[n:,m:]=0
    rows,cols=linear_sum_assignment(full)
    matches=[(int(r),int(c)) for r,c in zip(rows,cols) if r<n and c<m and cost[r,c]<=limit]
    ur=sorted(set(range(n))-{r for r,c in matches}); uc=sorted(set(range(m))-{c for r,c in matches})
    return matches,ur,uc


def measurement(box):
    b=np.asarray(box,dtype=float)
    return np.r_[(b[:2]+b[2:])/2,np.maximum(b[2:]-b[:2],2)]


class MotionFilter:
    def __init__(self,box):
        z=measurement(box)
        self.x=np.r_[z,np.zeros(4)]
        s=max(10,float(z[3]))
        self.p=np.diag([(.1*s)**2]*4+[(.5*s)**2]*4)
        self.h=np.c_[np.eye(4),np.zeros((4,4))]

    def predict(self,dt):
        dt=max(.001,min(float(dt),3))
        f=np.eye(8); f[:4,4:]=np.eye(4)*dt
        s=max(10,float(self.x[3]))
        q=np.diag([(.03*s*dt)**2]*4+[(.15*s*dt)**2]*4)+np.eye(8)*1e-5
        self.x=f@self.x; self.p=f@self.p@f.T+q
        self.x[2:4]=np.maximum(2,self.x[2:4])

    def update(self,box):
        z=measurement(box)
        r=np.eye(4)*(max(2,.05*z[3])**2)
        s=self.h@self.p@self.h.T+r
        k=np.linalg.solve(s,self.h@self.p).T
        self.x+=k@(z-self.h@self.x)
        ikh=np.eye(8)-k@self.h
        self.p=ikh@self.p@ikh.T+k@r@k.T
        self.x[2:4]=np.maximum(2,self.x[2:4])

    def box(self):
        return np.r_[self.x[:2]-self.x[2:4]/2,self.x[:2]+self.x[2:4]/2]


@dataclass
class Track:
    id: int
    class_id: int
    box: list[float]
    score: float
    created: float
    last_seen: float
    filter: MotionFilter
    high_hits: int=1
    confirmed: bool=False
    announced: bool=False
    last_high: float=0.0
    support_since: float=0.0
    trail: list=field(default_factory=list)

    def public(self):
        return {'id':self.id,'class_id':self.class_id,'box':list(map(float,self.box)),
                'score':float(self.score),'confirmed':self.confirmed,'last_seen':self.last_seen}


class Tracker:
    def __init__(self,cfg: AnalysisConfig):
        self.cfg=cfg; self.tracks={}; self.next_id=1; self.last_time=None
        self.overflow_total=0

    def _associate(self,tracks,dets,limit):
        if not tracks or not dets:
            return [],list(range(len(tracks))),list(range(len(dets)))
        predicted=np.array([t.filter.box() for t in tracks])
        boxes=np.array([d['box'] for d in dets])
        iou=iou_matrix(predicted,boxes)
        tc=(predicted[:,:2]+predicted[:,2:])/2
        dc=(boxes[:,:2]+boxes[:,2:])/2
        diag=np.linalg.norm(predicted[:,2:]-predicted[:,:2],axis=1)
        distances=np.linalg.norm(tc[:,None]-dc[None,:],axis=2)/np.maximum(diag[:,None],20)
        cost=.8*(1-iou)+.2*np.minimum(distances,2)
        # Class-consistent association and bounded motion; unrelated boxes cannot match.
        bad=(np.array([t.class_id for t in tracks])[:,None] != np.array([d['class_id'] for d in dets])[None,:])
        bad|=((iou<.01)&(distances>.65))
        cost[bad]=1e6
        return partial_assignment(cost,limit)

    def update(self,detections,timestamp):
        now=float(timestamp)
        if self.last_time is not None and now<=self.last_time:
            raise ValueError('O rastreamento exige timestamps estritamente crescentes.')
        dt=0 if self.last_time is None else now-self.last_time
        self.last_time=now
        expired=[]
        for tid,t in list(self.tracks.items()):
            ttl=self.cfg.lost_seconds if t.confirmed else min(self.cfg.confirmation_gap,self.cfg.lost_seconds)
            if now-t.last_seen>ttl:
                if t.confirmed: expired.append(t)
                del self.tracks[tid]
            else: t.filter.predict(dt)
        valid=[]
        for d in detections:
            b=np.array(d['box'],dtype=float)
            if b.shape!=(4,) or not np.isfinite(b).all() or np.any(b[2:]-b[:2]<2): continue
            s=float(d['score']); c=int(d['class_id'])
            if not np.isfinite(s) or not (self.cfg.low_confidence<=s<=1) or not (0<=c<80):continue
            if c not in self.cfg.class_ids(): continue
            valid.append({'box':b.tolist(),'score':s,'class_id':c})
        valid=sorted(valid,key=lambda d:d['score'],reverse=True)[:self.cfg.max_detections]
        high=[d for d in valid if d['score']>=self.cfg.threshold(d['class_id'])]
        low=[d for d in valid if d['score']<self.cfg.threshold(d['class_id'])]
        tracks=list(self.tracks.values())
        matches,unmatched,unused=self._associate(tracks,high,.78)
        current=[]; matched_ids=set()
        def apply(t,d,high_score):
            gap=now-t.last_seen
            t.filter.update(d['box']); t.box=d['box']; t.score=d['score'];t.last_seen=now
            if high_score:
                if gap>self.cfg.confirmation_gap or t.high_hits==0:
                    t.high_hits=0; t.support_since=now
                t.high_hits+=1; t.last_high=now
            elif not t.confirmed: t.high_hits=0
            if t.high_hits>=self.cfg.min_hits and now-t.support_since>=self.cfg.confirm_seconds:
                t.confirmed=True
            current.append(t);matched_ids.add(t.id)
        for a,b in matches: apply(tracks[a],high[b],True)
        # Low-confidence candidates recover only already-confirmed tracks, never create presence.
        recovery=[tracks[i] for i in unmatched if tracks[i].confirmed
                  and now-tracks[i].last_high <= self.cfg.recovery_seconds]
        matched_low,_,_=self._associate(recovery,low,.66)
        for a,b in matched_low: apply(recovery[a],low[b],False)
        for i in unused:
            d=high[i]
            t=Track(self.next_id,d['class_id'],d['box'],d['score'],now,now,MotionFilter(d['box']),last_high=now,support_since=now)
            self.next_id+=1; self.tracks[t.id]=t; current.append(t);matched_ids.add(t.id)
        for t in tracks:
            if t.id not in matched_ids and not t.confirmed:t.high_hits=0
        # Hard cap prevents a stream of false positives exhausting memory.
        while len(self.tracks)>400:
            victim=min(self.tracks.values(),key=lambda t:(t.confirmed,t.last_seen))
            self.tracks.pop(victim.id)
            self.overflow_total+=1
            if victim.confirmed: expired.append(victim)
            current=[t for t in current if t.id!=victim.id]
        return current,expired
