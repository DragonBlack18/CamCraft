"""Bounded performance statistics and optional pacing. Never changes confidence."""
from __future__ import annotations
from collections import deque
import math
import threading
import numpy as np


class PerformanceWindow:
    def __init__(self, capacity=240):
        self.samples = deque(maxlen=capacity)
        self.lock = threading.Lock()

    def record(self, *, inference_ms, object_ms, render_ms, age_ms):
        row = {'inference_ms': inference_ms, 'object_ms': object_ms, 'render_ms': render_ms, 'age_ms': age_ms}
        if any(not math.isfinite(v) or v < 0 for v in row.values()):
            return
        with self.lock:
            self.samples.append(row)

    def snapshot(self):
        with self.lock:
            rows = list(self.samples)
        return {'samples': len(rows), 'capacity': self.samples.maxlen,
                'percentiles': {k: {'p50': round(float(np.percentile([r[k] for r in rows], 50)), 2),
                                   'p95': round(float(np.percentile([r[k] for r in rows], 95)), 2)}
                                for k in rows[0]} if rows else {}}


def next_analysis_time(sent, now, max_fps, *, adaptive=False, duty=.75):
    if not 0 < duty <= 1 or max_fps < 1:
        raise ValueError('Parâmetros de ritmo inválidos.')
    work = max(0., now - sent)
    interval = max(1 / max_fps, work / duty) if adaptive else 1 / max_fps
    return max(now, sent + interval)
