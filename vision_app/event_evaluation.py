"""Event-level matching on manually annotated truth. No metrics without labels."""
from __future__ import annotations
import math
import numpy as np
from .tracker import partial_assignment


def evaluate_events(predictions,ground_truth,*,tolerance_seconds=2.,monitored_seconds):
    if not math.isfinite(monitored_seconds) or monitored_seconds<=0:raise ValueError('Tempo monitorado deve ser positivo.')
    if not math.isfinite(tolerance_seconds) or not 0<tolerance_seconds<=60:raise ValueError('Tolerância inválida.')
    if len(predictions)>5000 or len(ground_truth)>5000:raise ValueError('Divida a avaliação em até 5.000 eventos por arquivo.')
    def checked(items):
        rows=[]
        for item in items:
            if not isinstance(item,dict) or any(k not in item for k in ('camera_id','object_id','code','time_s')):
                raise ValueError('Cada evento precisa de camera_id, object_id, code e time_s.')
            stamp=float(item['time_s'])
            if not math.isfinite(stamp) or stamp<0:raise ValueError('Tempo de evento inválido.')
            rows.append({**item,'time_s':stamp})
        return rows
    predictions=checked(predictions);ground_truth=checked(ground_truth)
    group=lambda r:(r['camera_id'],r['object_id'],r['code'])
    keys=sorted({group(r) for r in predictions+ground_truth})
    details=[];tp=fp=fn=actor_correct=actor_wrong=actor_abstain=0;latencies=[]
    for key in keys:
        p=[r for r in predictions if group(r)==key];g=[r for r in ground_truth if group(r)==key]
        # Group-level limit bounds the Hungarian matrix, including dummy slots.
        if len(p)+len(g)>1000:raise ValueError('Muitos eventos no mesmo grupo; divida o vídeo em janelas menores.')
        cost=np.array([[abs(a['time_s']-b['time_s']) for b in g] for a in p],float).reshape(len(p),len(g))
        # Prefer maximum cardinality first, then minimum timestamp error.
        normalized=np.where(cost<=tolerance_seconds,cost/(tolerance_seconds*(len(p)+len(g)+1)),2.)
        matches,unmatched_p,unmatched_g=partial_assignment(normalized,1.)
        tp+=len(matches);fp+=len(unmatched_p);fn+=len(unmatched_g)
        for i,j in matches:
            latency=p[i]['time_s']-g[j]['time_s'];latencies.append(latency)
            # Only evaluate attribution when truth supplies a session-local track ID.
            expected=g[j].get('actor_track_id');observed=p[i].get('actor_track_id')
            if expected is not None:
                if observed is None:actor_abstain+=1
                elif observed==expected:actor_correct+=1
                else:actor_wrong+=1
        details.append({'camera_id':key[0],'object_id':key[1],'code':key[2],
                        'tp':len(matches),'fp':len(unmatched_p),'fn':len(unmatched_g)})
    precision=tp/(tp+fp) if tp+fp else None;recall=tp/(tp+fn) if tp+fn else None
    f1=2*precision*recall/(precision+recall) if precision is not None and recall is not None and precision+recall else (0. if tp+fp+fn else None)
    return {'tp':tp,'fp':fp,'fn':fn,'precision':precision,'recall':recall,'f1':f1,
        'false_events_per_hour':fp*3600/monitored_seconds,'monitored_seconds':monitored_seconds,
        'tolerance_seconds':tolerance_seconds,'median_latency_s':float(np.median(latencies)) if latencies else None,
        'actor_correct':actor_correct,'actor_wrong':actor_wrong,'actor_abstained':actor_abstain,
        'groups':details,'note':'Eventos agrupados por câmera/objeto/código, associação um a um. Precisão sem previsões é null, não 100%. Não mede verdade sem rótulos humanos.'}
