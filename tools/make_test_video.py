import argparse
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import cv2
from vision_foundation.capture import demo_frame


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=Path('data/test-video.avi'));p.add_argument('--seconds',type=int,default=10)
    a=p.parse_args();a.output.parent.mkdir(parents=True,exist_ok=True)
    w=cv2.VideoWriter(str(a.output),cv2.VideoWriter_fourcc(*'MJPG'),30,(640,360))
    if not w.isOpened():raise RuntimeError('MJPG encoder unavailable')
    try:
        for i in range(a.seconds*30):w.write(demo_frame(640,360,i+1))
    finally:w.release()
    print('[PASS]',a.output.resolve())


if __name__=='__main__':main()
