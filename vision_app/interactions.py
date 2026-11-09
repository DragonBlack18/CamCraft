"""Conservative, explainable fixed-camera object state and interaction engine.

A slot matches explicit occupied/empty references. Detector disappearance is NEVER
an absence signal. Person association additionally requires a bound object track,
appearance agreement, unique recent contact and measured co-motion. No identity,
intent, theft or legal conclusion is inferred. Scores are not probabilities.
"""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass, field
import math
import time
import uuid

import cv2
import numpy as np
from .object_registry import patch, scene, roi_pixels, reference_features, source_signature

MESSAGES = {
    'OBJETO_PRESENTE_INICIAL':'Referência ocupada observada; estado inicial, sem inferir uma devolução.',
    'OBJETO_AUSENTE_INICIAL':'Local vazio no início; não houve retirada observada nesta sessão.',
    'INTERACAO_POSSIVEL':'Pessoa próxima do local monitorado; não comprova contato ou retirada.',
    'OBJETO_OCULTO':'Região encoberta; confirmação de ausência suspensa.',
    'AUSENCIA_CONFIRMADA':'Local corresponde à referência vazia em observações consecutivas; autoria não atribuída.',
    'RETIRADA_PROVAVEL':'Ausência e deslocamento compatível com uma trajetória de pessoa; associação provável, revisar evidências.',
    'RETORNO_OBSERVADO':'Aparência cadastrada voltou ao local; não comprova identidade física do item nem quem o devolveu.',
    'ALTERACAO_INCONCLUSIVA':'A região não corresponde de forma suficiente ao vazio nem ao objeto cadastrado.',
    'MONITORAMENTO_SUSPENSO':'Geometria, iluminação ou visibilidade inadequadas; eventos do objeto suspensos.',
    'MONITORAMENTO_RETOMADO':'Condições visuais restabelecidas; novo estado inicial, sem inferir mudanças durante a lacuna.',
}
MAJOR_EVENTS = {'AUSENCIA_CONFIRMADA','RETIRADA_PROVAVEL','RETORNO_OBSERVADO','ALTERACAO_INCONCLUSIVA'}


def overlap_area(a,b):
    return max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))


def fraction_covered(box, covering):
    return overlap_area(box,covering)/max(1,(box[2]-box[0])*(box[3]-box[1]))


def center(box):
    return np.array([(box[0]+box[2])/2,(box[1]+box[3])/2],np.float32)


def expand(box, factor=.45):
    x,y,z,t=box;w=z-x;h=t-y
    return (x-w*factor,y-h*factor,z+w*factor,t+h*factor)


def small_frame(frame, maximum=960):
    h,w=frame.shape[:2];r=min(1,maximum/w,540/h)
    return frame.copy() if r==1 else cv2.resize(frame,(int(w*r),int(h*r)),interpolation=cv2.INTER_AREA)


@dataclass
class Contact:
    first: float
    last: float
    count: int=1
    touched: bool=False


@dataclass
class Runtime:
    spec: object
    references: dict
    mask: object
    separation: float
    stable: str | None=None
    state: str='INICIALIZANDO'
    pending: str | None=None
    pending_since: float=0
    pending_count: int=0
    last_stamp: float | None=None
    unknown_since: float | None=None
    unknown_logged: bool=False
    occluded_logged: bool=False
    suspended: bool=False
    suspension_reason: str=''
    contacts: dict=field(default_factory=dict)
    announced_contacts: set=field(default_factory=set)
    ambiguous: bool=False
    bound_id: int | None=None
    bind_candidate: int | None=None
    bind_hits: int=0
    motion: dict=field(default_factory=dict)
    proof: dict | None=None
    before: dict | None=None
    before_stamp: float=-1e9
    metrics: dict=field(default_factory=dict)

    def clear_transition(self):
        self.pending=None;self.pending_count=0

    def clear_interaction(self):
        self.contacts.clear();self.motion.clear();self.proof=None
        self.announced_contacts.clear();self.ambiguous=False

    def reset(self):
        self.stable=None;self.state='INICIALIZANDO';self.clear_transition()
        self.clear_interaction();self.bound_id=None;self.bind_candidate=None;self.bind_hits=0
        self.before=None;self.unknown_since=None;self.unknown_logged=False;self.occluded_logged=False


class InteractionEngine:
    def __init__(self, registry, camera, session, analysis_roi=None, *,allow_association=True):
        self.config=registry.config(camera.id)
        self.session=session;self.camera_id=camera.id;self.analysis_roi=analysis_roi
        self.allow_association=allow_association
        self.objects=[];self.load_errors=[];self.last_ms=0.;self._reported_errors=False
        if not self.config.enabled:return
        for spec in registry.all(camera.id):
            if not spec.enabled:continue
            try:
                if spec.source_signature!=source_signature(camera):
                    raise ValueError('Fonte alterada desde o cadastro; recalibre o objeto.')
                refs=registry.load(spec)
                mask,separation,_=reference_features(refs['vazio.png'],refs['presente.png'])
                if separation<.07:raise ValueError('Referências sem separação visual suficiente.')
                self.objects.append(Runtime(spec,refs,mask,separation))
            except (ValueError,OSError) as exc:
                self.load_errors.append({'object_id':spec.id,'object_name':spec.name,'reason':str(exc)})
        self._reported_errors=False

    def event(self,r,code,utc,stamp,sequence,**extra):
        return {'event_id':uuid.uuid4().hex,'code':code,'session':self.session,'object_id':r.spec.id,
            'object_name':r.spec.name,'class_name':r.spec.name,'registered_class_id':r.spec.class_id,
            'roi':list(r.spec.roi),'frame_utc':utc,'frame_monotonic':stamp,'sequence':sequence,
            'actor_track_id':None,'association':'NAO_ATRIBUIDA','requires_review':code in MAJOR_EVENTS,
            'measurements':dict(r.metrics),'conclusion':MESSAGES[code],**extra}

    def _guard(self,r,current_scene,tracks,shape):
        if shape[1]!=r.spec.width or shape[0]!=r.spec.height:
            return False,'RESOLUCAO_ALTERADA',0.,{}
        # A crop that excludes a registered slot cannot provide safe person occlusion data.
        if self.analysis_roi:
            a,b,c,d=self.analysis_roi;x,y,z,t=r.spec.roi
            if a>x or b>y or c<z or d<t:return False,'OBJETO_FORA_DA_AREA_DE_ANALISE',0.,{}
        reference=r.references['cena.png']
        previous=cv2.cvtColor(reference,cv2.COLOR_BGR2GRAY).astype(np.float32)
        current=cv2.cvtColor(current_scene,cv2.COLOR_BGR2GRAY).astype(np.float32)
        mask=np.ones(current.shape,np.uint8)
        for obj in self.objects:
            a,b,c,d=roi_pixels(obj.spec.roi,current_scene.shape)
            mask[max(0,b-3):min(180,d+3),max(0,a-3):min(320,c+3)]=0
        h,w=shape[:2]
        for t in tracks:
            if t['class_id']!=0:continue
            a,b,c,d=t['box']
            a,b,c,d=int(a*320/w)-3,int(b*180/h)-3,int(c*320/w)+3,int(d*180/h)+3
            mask[max(0,b):min(180,d),max(0,a):min(320,c)]=0
        usable=mask.astype(bool)
        if usable.mean()<.25:return False,'CENA_MUITO_ENCOBERTA',0.,{}
        delta=float(np.median((current-previous)[usable]))
        residual=float(np.mean(np.abs((current-previous-delta)[usable]))/255)
        metrics={'background_delta':round(delta,2),'background_residual':round(residual,4)}
        if abs(delta)>25:return False,'ILUMINACAO_ALTERADA',delta,metrics
        if np.mean(current[usable]<6)>.75:return False,'IMAGEM_ESCURA',delta,metrics
        # Phase correlation is a guard, not automatic image registration.
        # We do NOT warp references or silently learn a moved camera as normal.
        p=(previous-float(np.mean(previous[usable])))*mask
        c=(current-float(np.mean(current[usable])))*mask
        if np.std(previous[usable])>8:
            shift,response=cv2.phaseCorrelate(p,c)
            metrics.update(shift_pixels_320=[round(float(x),2) for x in shift],shift_response=round(float(response),3))
            if response>.25 and math.hypot(*shift)>2.0:
                return False,'CAMERA_DESLOCADA',delta,metrics
            lp=cv2.Laplacian(previous,cv2.CV_32F)
            lc=cv2.Laplacian(current,cv2.CV_32F)
            baseline=float(np.var(lp[usable])); observed=float(np.var(lc[usable]))
            if baseline>40 and observed<baseline*.12:return False,'DESFOQUE_FORTE',delta,metrics
        if residual>.065:return False,'CENA_ALTERADA',delta,metrics
        return True,'OK',delta,metrics

    def _appearance(self,r,frame,box):
        h,w=frame.shape[:2];a,b,c,d=[int(v) for v in box]
        a=max(0,a);b=max(0,b);c=min(w,c);d=min(h,d)
        if c-a<12 or d-b<12:return 0.
        # Tight calibration is important: matching checks shape AND color.
        query=cv2.resize(frame[b:d,a:c],(80,80),interpolation=cv2.INTER_AREA)
        query=cv2.GaussianBlur(query,(3,3),0)
        ref=r.references['presente.png']
        color=float(np.mean(np.abs(query.astype(np.float32)-ref.astype(np.float32))[r.mask])/255)
        gray=cv2.cvtColor(query,cv2.COLOR_BGR2GRAY);base=cv2.cvtColor(ref,cv2.COLOR_BGR2GRAY)
        if np.std(base)>5 and np.std(gray)>5:
            corr=float(cv2.matchTemplate(gray,base,cv2.TM_CCOEFF_NORMED)[0,0])
            if not math.isfinite(corr):return 0.
        else:corr=1. if color<.045 else 0.
        return max(0.,min(1.,.55*max(0,corr)+.45*max(0,1-color/.3)))

    def _associations(self,r,frame,tracks,box,stamp,utc,sequence):
        events=[];cfg=self.config
        confirmed=[t for t in tracks if t.get('confirmed')]
        people=[t for t in confirmed if t['class_id']==0]
        near=[p for p in people if overlap_area(expand(box),p['box'])>0]
        for p in near:
            key=p['id'];ct=r.contacts.get(key)
            if ct is None or stamp-ct.last>cfg.max_gap_seconds:
                ct=Contact(stamp,stamp);r.contacts[key]=ct
            else:ct.count+=1;ct.last=stamp
            ct.touched=ct.touched or fraction_covered(box,p['box'])>.08
            if ct.count>=3 and stamp-ct.first>=cfg.contact_seconds and key not in r.announced_contacts:
                r.announced_contacts.add(key)
                events.append(self.event(r,'INTERACAO_POSSIVEL',utc,stamp,sequence,
                    nearby_track_id=f'{self.session}:{key:05d}',association='SOMENTE_PROXIMIDADE'))
        r.contacts={k:v for k,v in r.contacts.items() if stamp-v.last<=cfg.association_ttl}
        r.motion={k:v for k,v in r.motion.items() if k in r.contacts}
        r.announced_contacts.intersection_update(r.contacts)
        touched=[k for k,c in r.contacts.items() if c.touched and c.count>=3 and c.last-c.first>=cfg.contact_seconds]
        if len(near)>1 or len(touched)>1:r.ambiguous=True
        if not r.contacts:r.ambiguous=False;r.proof=None;r.motion.clear()
        if not self.allow_association:return events
        objects=[t for t in confirmed if t['class_id']!=0 and (r.spec.class_id is None or t['class_id']==r.spec.class_id)]
        if r.stable in (None,'PRESENTE') and r.bound_id is None:
            matches=[t for t in objects if fraction_covered(box,t['box'])>.35 and
                     fraction_covered(t['box'],expand(box,.12))>.65 and self._appearance(r,frame,t['box'])>=.78]
            if len(matches)==1:
                key=matches[0]['id'];r.bind_hits=r.bind_hits+1 if r.bind_candidate==key else 1;r.bind_candidate=key
                if r.bind_hits>=2:r.bound_id=key
            else:r.bind_candidate=None;r.bind_hits=0
        candidate=next((t for t in objects if t['id']==r.bound_id),None)
        if candidate is None:return events
        # Movement evidence requires the SAME bound item track outside its registered slot.
        if fraction_covered(candidate['box'],box)>.15:return events
        visual=self._appearance(r,frame,candidate['box'])
        if visual<.78:return events
        associates=[p for p in people if p['id'] in touched and overlap_area(expand(p['box'],.12),candidate['box'])>0]
        if len(associates)!=1 or r.ambiguous:return events
        person=associates[0];pid=person['id']
        samples=r.motion.setdefault(pid,deque(maxlen=12))
        if samples and stamp-samples[-1][0]>cfg.max_gap_seconds:samples.clear()
        samples.append((stamp,center(candidate['box']),center(person['box'])))
        if len(samples)<3 or stamp-samples[0][0]<.4:return events
        dt,old_o,old_p=samples[0];_,new_o,new_p=samples[-1]
        do=new_o-old_o;dp=new_p-old_p
        no=float(np.linalg.norm(do));np_=float(np.linalg.norm(dp))
        if min(no,np_)<max(6,frame.shape[1]*.012):return events
        cosine=float(do@dp/(no*np_))
        offsets=np.array([o-p for _,o,p in samples]);scatter=float(np.max(np.linalg.norm(offsets-offsets.mean(axis=0),axis=1)))
        limit=max(12, math.hypot(person['box'][2]-person['box'][0],person['box'][3]-person['box'][1])*.18)
        if cosine>.65 and scatter<limit:
            r.proof={'person_id':pid,'object_track_id':candidate['id'],'stamp':stamp,
                     'appearance_score':round(visual,3),'motion_cosine':round(cosine,3),
                     'observations':len(samples),'duration_seconds':round(stamp-dt,3)}
        return events

    def _classify(self,r,frame,delta):
        current=np.clip(patch(frame,r.spec.roi).astype(np.float32)-delta,0,255)
        mask=r.mask
        de=float(np.mean(np.abs(current-r.references['vazio.png'].astype(np.float32))[mask])/255)
        dp=float(np.mean(np.abs(current-r.references['presente.png'].astype(np.float32))[mask])/255)
        threshold=min(.18,max(.025,r.separation*.42))
        margin=r.separation*.35
        measurements={'distance_empty':round(de,4),'distance_present':round(dp,4),
                      'max_distance':round(threshold,4),'required_margin':round(margin,4)}
        if dp<=threshold and de-dp>=margin:return 'PRESENTE',measurements
        if de<=threshold and dp-de>=margin:return 'AUSENTE',measurements
        return 'DESCONHECIDO',measurements

    def update(self,frame,tracks,raw_detections,stamp,utc,sequence=0):
        began=time.perf_counter();events=[];before_images={};states=[]
        if not self._reported_errors:
            for err in self.load_errors:
                events.append({'code':'MONITORAMENTO_SUSPENSO','event_id':uuid.uuid4().hex,'session':self.session,
                    'frame_utc':utc,'sequence':sequence,'actor_track_id':None,'association':'NAO_ATRIBUIDA',**err})
            self._reported_errors=True
        if not self.objects:
            self.last_ms=(time.perf_counter()-began)*1000;return states,events,before_images
        current_scene=scene(frame)
        cached_small=None
        # Even a weak/unconfirmed person detection can block an unsafe absence conclusion.
        blockers=[d for d in raw_detections if d.get('class_id')==0 and d.get('score',0)>=.1]
        people_boxes=blockers or [t for t in tracks if t['class_id']==0]
        for r in self.objects:
            box=roi_pixels(r.spec.roi,frame.shape)
            if r.last_stamp is not None and stamp<=r.last_stamp:
                states.append(self._public(r));continue
            gap=r.last_stamp is not None and stamp-r.last_stamp>self.config.max_gap_seconds
            r.last_stamp=stamp
            if gap:
                r.reset()
                events.append(self.event(r,'MONITORAMENTO_RETOMADO',utc,stamp,sequence,reason='LACUNA_ENTRE_OBSERVACOES'))
            valid,reason,delta,guard_metrics=self._guard(r,current_scene,people_boxes,frame.shape)
            if not valid:
                if not r.suspended or r.suspension_reason!=reason:
                    events.append(self.event(r,'MONITORAMENTO_SUSPENSO',utc,stamp,sequence,reason=reason))
                r.reset();r.suspended=True;r.suspension_reason=reason;r.state='SUSPENSO';r.metrics=guard_metrics
                states.append(self._public(r));continue
            if r.suspended:
                r.reset();r.suspended=False;r.suspension_reason=''
                events.append(self.event(r,'MONITORAMENTO_RETOMADO',utc,stamp,sequence,reason='CENA_VALIDA_NOVAMENTE'))
            events.extend(self._associations(r,frame,tracks,box,stamp,utc,sequence))
            occluded=any(fraction_covered(box,t['box'])>.12 for t in people_boxes)
            # Other large detected objects covering a slot are occlusion, not empty evidence.
            for d in raw_detections:
                if d.get('class_id')==0 or d.get('score',0)<.25:continue
                area=max(1,(d['box'][2]-d['box'][0])*(d['box'][3]-d['box'][1]))
                if area>3*(box[2]-box[0])*(box[3]-box[1]) and fraction_covered(box,d['box'])>.6:occluded=True
            if occluded:
                if not r.occluded_logged:
                    events.append(self.event(r,'OBJETO_OCULTO',utc,stamp,sequence));r.occluded_logged=True
                r.state='OCULTO';r.clear_transition();r.unknown_since=None
                states.append(self._public(r));continue
            r.occluded_logged=False
            observed,metrics=self._classify(r,frame,delta);r.metrics={**guard_metrics,**metrics}
            if observed=='DESCONHECIDO':
                r.clear_transition();r.state='ALTERACAO_INCONCLUSIVA'
                if r.unknown_since is None:r.unknown_since=stamp
                if stamp-r.unknown_since>=self.config.unknown_seconds and not r.unknown_logged:
                    e=self.event(r,'ALTERACAO_INCONCLUSIVA',utc,stamp,sequence,previous_state=r.stable)
                    self._attach_before(r,e,before_images);events.append(e);r.unknown_logged=True
                states.append(self._public(r));continue
            r.unknown_since=None;r.unknown_logged=False
            if observed!=r.pending:
                r.pending=observed;r.pending_since=stamp;r.pending_count=1
            else:r.pending_count+=1
            duration=self.config.present_seconds if observed=='PRESENTE' else self.config.absent_seconds
            confirmed=r.pending_count>=self.config.min_observations and stamp-r.pending_since>=duration
            r.state=r.stable if observed==r.stable else 'VERIFICANDO_'+observed
            if confirmed and observed!=r.stable:
                previous=r.stable
                if previous is None:
                    code='OBJETO_PRESENTE_INICIAL' if observed=='PRESENTE' else 'OBJETO_AUSENTE_INICIAL'
                elif observed=='PRESENTE':code='RETORNO_OBSERVADO'
                else:code='AUSENCIA_CONFIRMADA'
                extra={'previous_state':previous,'new_state':observed,'observations':r.pending_count,
                       'confirmation_seconds':round(stamp-r.pending_since,3),
                       'nearby_track_ids':[f'{self.session}:{k:05d}' for k in sorted(r.contacts)],
                       'ambiguous_people':r.ambiguous}
                proof=r.proof
                if code=='AUSENCIA_CONFIRMADA' and self.allow_association and proof and not r.ambiguous and stamp-proof['stamp']<=self.config.association_ttl:
                    code='RETIRADA_PROVAVEL';extra.update(actor_track_id=f"{self.session}:{proof['person_id']:05d}",
                        association='PROVAVEL_NAO_COMPROVADA',association_evidence=dict(proof))
                e=self.event(r,code,utc,stamp,sequence,**extra)
                self._attach_before(r,e,before_images);events.append(e)
                r.stable=observed;r.state=observed;r.clear_interaction();r.before=None
                if observed=='PRESENTE':r.bound_id=None;r.bind_candidate=None;r.bind_hits=0
            if confirmed and observed==r.stable and stamp-r.before_stamp>=.5:
                if cached_small is None:cached_small=small_frame(frame)
                r.before={'frame':cached_small,'metadata':{'frame_utc':utc,'frame_monotonic':stamp,
                    'sequence':sequence,'session':self.session,'state':r.stable,'object_id':r.spec.id}}
                r.before_stamp=stamp
            states.append(self._public(r))
        self.last_ms=(time.perf_counter()-began)*1000
        return states,events,before_images

    def _attach_before(self,r,event,images):
        if r.before and event['code'] in MAJOR_EVENTS:
            filename='antes_'+r.spec.id+'.jpg'
            images[filename]=r.before
            event['before_image']=filename;event['before_metadata']=dict(r.before['metadata'])
        else:event['before_image']=None

    def _public(self,r):
        return {'id':r.spec.id,'name':r.spec.name,'roi':list(r.spec.roi),'state':r.state,
                'stable_state':r.stable,'reason':r.suspension_reason,'measurements':dict(r.metrics),
                'bound_track_id':r.bound_id,'ambiguous_people':r.ambiguous}
