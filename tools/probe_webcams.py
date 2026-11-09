"""Opt-in device probe. Each index has its own killable process and bounded timeout."""
import argparse
import multiprocessing as mp
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from vision_foundation.config import CameraConfig
from vision_foundation.storage import EventStore
from vision_foundation.supervisor import CameraSession
import tempfile
import time


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--max-index',type=int,default=3,choices=range(0,16))
    parser.add_argument('--backend',default='auto',choices=['auto','dshow','msmf','v4l2','avfoundation'])
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='vision-probe-') as path:
        store=EventStore(Path(path)/'probe.sqlite3')
        for index in range(args.max_index+1):
            s=CameraSession(CameraConfig(kind='webcam',source=str(index),backend=args.backend,open_timeout_s=4),store)
            try:
                s.start();deadline=time.monotonic()+6
                while time.monotonic()<deadline and not s.snapshot()['fresh']:time.sleep(.1)
                state=s.snapshot()
                print(f"[{'PASS' if state['fresh'] else 'FAIL'}] index={index} backend={state['backend']} "
                      f"size={state.get('source_width','?')}x{state.get('source_height','?')}")
            finally:s.stop()
        store.close()


if __name__=='__main__':
    mp.freeze_support()
    main()
