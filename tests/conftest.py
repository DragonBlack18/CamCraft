import os
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[key]='1'
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import time
import pytest
from vision_foundation.storage import EventStore


def wait_for(predicate, timeout=12, message='condition'):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        value=predicate()
        if value:
            return value
        time.sleep(.05)
    raise AssertionError(f'Timeout waiting for {message}')


@pytest.fixture
def store(tmp_path):
    value=EventStore(tmp_path/'test.sqlite3')
    yield value
    value.close()
