"""Test-only workers, never reachable from the production HTTP API."""
import time
from vision_foundation.capture import worker


def hang_then_recover(config, slot, stop, generation):
    if generation==0:
        slot.set_status('OPENING')
        while True:
            time.sleep(10)
    worker(config,slot,stop,generation)


def poison_then_recover(config,slot,stop,generation):
    if generation==0:
        slot.lock.acquire()
        while True:
            time.sleep(10)
    worker(config,slot,stop,generation)


def crash_then_recover(config,slot,stop,generation):
    if generation==0:
        import os
        os._exit(37)
    worker(config,slot,stop,generation)
