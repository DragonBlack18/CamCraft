import unicodedata
import cv2
from .classes import NAMES

def ascii_text(value):
    return unicodedata.normalize('NFKD',value).encode('ascii','ignore').decode()

def render(frame,tracks,cfg,objects=None):
    out=frame.copy();h,w=out.shape[:2]
    thick=max(1,round(min(w,h)/400))
    if cfg.roi:
        a,b,c,d=cfg.roi
        cv2.rectangle(out,(int(a*w),int(b*h)),(int(c*w),int(d*h)),(220,190,70),thick)
    if cfg.line:
        a,b,c,d=cfg.line;p=(int(a*w),int(b*h));q=(int(c*w),int(d*h))
        cv2.line(out,p,q,(40,210,240),thick+1)
        cv2.putText(out,'A',p,cv2.FONT_HERSHEY_SIMPLEX,.6,(40,210,240),2)
        cv2.putText(out,'B',q,cv2.FONT_HERSHEY_SIMPLEX,.6,(40,210,240),2)
        import math
        dx,dy=q[0]-p[0],q[1]-p[1];length=max(1,math.hypot(dx,dy));sgn=1 if cfg.positive_is_entry else -1
        mid=((p[0]+q[0])//2,(p[1]+q[1])//2)
        end=(int(mid[0]-dy/length*40*sgn),int(mid[1]+dx/length*40*sgn))
        cv2.arrowedLine(out,mid,end,(40,210,240),thick+1,tipLength=.3)
        cv2.putText(out,'ENTRADA',end,cv2.FONT_HERSHEY_SIMPLEX,.4,(40,210,240),1)
    for t in tracks:
        if not t['confirmed'] and not cfg.show_tentative: continue
        x1,y1,x2,y2=[int(round(x)) for x in t['box']]
        x1=max(0,min(w-1,x1));x2=max(0,min(w-1,x2));y1=max(0,min(h-1,y1));y2=max(0,min(h-1,y2))
        color=(90,210,80) if t['confirmed'] else (140,170,190)
        cv2.rectangle(out,(x1,y1),(x2,y2),color,thick)
        label=ascii_text(f"#{t['id']} {NAMES[t['class_id']]} {t['score']:.2f}"+('' if t['confirmed'] else ' ...'))
        (tw,th),base=cv2.getTextSize(label,cv2.FONT_HERSHEY_SIMPLEX,.48,1)
        y=max(th+6,y1)
        cv2.rectangle(out,(x1,y-th-5),(min(w-1,x1+tw+6),y+base),(18,18,18),-1)
        cv2.putText(out,label,(x1+3,y-2),cv2.FONT_HERSHEY_SIMPLEX,.48,color,1,cv2.LINE_AA)
    for obj in objects or []:
        a,b,c,d=obj['roi']; p=(int(a*w),int(b*h)); q=(int(c*w),int(d*h))
        state=obj['state']
        color=(80,210,100) if state=='PRESENTE' else (60,160,250) if state in ('AUSENTE','OCULTO') else (180,160,190)
        cv2.rectangle(out,p,q,color,thick+1)
        label=ascii_text(obj['name']+' | '+state.replace('_',' '))
        cv2.putText(out,label[:75],(p[0],min(h-8,q[1]+18)),cv2.FONT_HERSHEY_SIMPLEX,.43,color,1,cv2.LINE_AA)
    return out
