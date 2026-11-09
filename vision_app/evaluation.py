"""Per-class detection metrics at one confidence/IoU threshold, NOT COCO mAP."""
from collections import defaultdict
import numpy as np
from .tracker import iou_matrix,partial_assignment

def match_frame(predictions,truth,iou_threshold=.5):
    if not 0<iou_threshold<=1:raise ValueError('IoU fora do intervalo (0, 1].')
    results={}
    classes={int(v['class_id']) for v in predictions+truth}
    for cid in sorted(classes):
        p=[d for d in predictions if int(d['class_id'])==cid]
        g=[d for d in truth if int(d['class_id'])==cid]
        overlap=iou_matrix([d['box'] for d in p],[d['box'] for d in g])
        # Maximize the number of valid one-to-one matches before IoU quality.
        # Dummy assignment penalties must not sacrifice two valid matches for one perfect match.
        cost=np.where(overlap>=iou_threshold,(1-overlap)/(len(p)+len(g)+1),2.)
        matches,up,ug=partial_assignment(cost,1.)
        results[cid]={'tp':len(matches),'fp':len(up),'fn':len(ug)}
    return results

def summarize(rows):
    counts=defaultdict(lambda:{'tp':0,'fp':0,'fn':0})
    for row in rows:
        for cid,values in row.items():
            for key in ('tp','fp','fn'):counts[cid][key]+=values[key]
    def metrics(c):
        tp,fp,fn=c['tp'],c['fp'],c['fn']
        return {**c,'precision':tp/(tp+fp) if tp+fp else None,'recall':tp/(tp+fn) if tp+fn else None,
                'f1':2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None}
    total={key:sum(v[key] for v in counts.values()) for key in ('tp','fp','fn')}
    return {'overall':metrics(total),'per_class':{str(k):metrics(v) for k,v in sorted(counts.items())}}
