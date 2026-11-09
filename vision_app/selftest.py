"""Exercise the real frozen application without a camera, network or external Python.

This is an integration/package test, not an accuracy benchmark. It deliberately
uses a neutral image and synthetic video and never accesses a physical camera.
"""
from __future__ import annotations
import argparse
from contextlib import ExitStack
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import tempfile
import time
import traceback


def _observe_current_result(service, seen: set) -> None:
    """Record only fresh, accepted neural results, not a lucky final sample.

    `latest()` intentionally hides old results. A CPU worker can be productive
    while between results at the exact end of an arbitrary observation window.
    Keep freshness checks enabled and require two distinct observed results.
    """
    result = service.latest()
    if result is None:
        return
    if result.metadata.get('engine') != 'yolox':
        raise RuntimeError('Package test received a non-neural result')
    seen.add((result.metadata.get('session'), result.id))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--seconds', type=float, default=15)
    args = parser.parse_args(argv)
    if not 2 <= args.seconds <= 120:
        parser.error('--seconds deve estar entre 2 e 120.')
    from .runtime import resource_root, default_data_dir, is_frozen, VERSION, tool_command
    report = {
        'application': 'CamCraft', 'version': VERSION, 'passed': False,
        'scope': 'Package integration. Real YOLOX on neutral/synthetic images; no accuracy or physical-camera claim.',
        'runtime': {'frozen': is_frozen(), 'executable': sys.executable,
                    'resources': str(resource_root()), 'default_data': str(default_data_dir()),
                    'platform': platform.platform(), 'python': sys.version},
        'no_external_python_on_path': shutil.which('python') is None and shutil.which('python3') is None,
        'checks': {}, 'errors': [],
    }
    began = time.monotonic()
    root = app = window = None

    def cleanup_runtime():
        nonlocal root, app
        if window is not None:
            window.closed = True
        try:
            if root is not None:
                try:
                    root.destroy()
                finally:
                    root = None
        finally:
            if app is not None:
                app.close()
                app = None
    # urllib is not used by the test. Reject any accidental Python networking;
    # the real model has to be present in the distribution and pass its hash.
    import socket
    original_connect = socket.socket.connect
    def reject_network(_socket, _address):
        raise OSError('Self-test offline: network access is prohibited')
    socket.socket.connect = reject_network
    try:
        import cv2
        import numpy as np
        import tkinter as tk
        from PIL import Image, ImageTk
        from .model import MODEL_FILE, MODEL_SHA256, verified
        from .detector import YoloXDetector
        from .settings import AnalysisConfig
        from .controller import Controller
        from .ui import Window
        from vision_foundation.config import CameraConfig
        model = resource_root() / 'models' / MODEL_FILE
        if not verified(model):
            raise RuntimeError('Included ONNX model missing or hash mismatch')
        report['checks']['model_sha256'] = MODEL_SHA256
        start = time.monotonic()
        detector = YoloXDetector(model, AnalysisConfig(classes='indoor', threads=2))
        predictions = detector.detect(np.full((480,640,3), 114, dtype=np.uint8))
        report['checks']['real_neural_inference'] = {'passed': True, 'seconds': time.monotonic()-start,
                                                     'predictions_on_neutral_image': len(predictions)}
        del detector
        with ExitStack() as resources:
            scratch = Path(resources.enter_context(tempfile.TemporaryDirectory(prefix='CamCraft self test ')))
            # LIFO cleanup closes the database/processes BEFORE deleting their
            # working directory. Windows refuses to remove files still in use.
            resources.callback(cleanup_runtime)
            # Native codec write/read covers the actual bundled video decoder.
            video = scratch / 'codec test.avi'
            writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*'MJPG'), 10, (96,64))
            if not writer.isOpened():
                raise RuntimeError('MJPG writer unavailable')
            for i in range(10):
                writer.write(np.full((64,96,3), i*20, dtype=np.uint8))
            writer.release()
            reader = cv2.VideoCapture(str(video), cv2.CAP_FFMPEG)
            ok, frame = reader.read(); reader.release()
            if not ok or frame.shape[:2] != (64,96):
                raise RuntimeError('Bundled FFmpeg decoder failed')
            report['checks']['video_codec_roundtrip'] = True
            app = Controller(scratch/'data', model.parent)
            app.configs.put(CameraConfig(id='selftest', name='CamCraft package test', kind='demo', source='demo',
                                         width=640, height=480, fps=30, publish_fps=30,
                                         raw_max_width=640, raw_max_height=480, jpeg_preview=False))
            app.settings.put('selftest', AnalysisConfig(engine='yolox', classes='indoor', threads=2))
            root = tk.Tk()
            errors = []
            root.report_callback_exception = lambda typ, value, tb: errors.append(''.join(traceback.format_exception(typ,value,tb)))
            window = Window(root, app)
            window.refresh_sources('selftest')
            root.geometry('900x620')
            root.update()
            photo = ImageTk.PhotoImage(Image.new('RGB', (16,16)), master=root)
            if photo.width() != 16:
                raise RuntimeError('Pillow/Tk photo bridge failed')
            app.start('selftest')
            seen_results = set()
            deadline = time.monotonic()+args.seconds
            while time.monotonic() < deadline:
                root.update()
                _observe_current_result(app.analysis, seen_results)
                if errors:
                    raise RuntimeError(errors[-1])
                time.sleep(.01)
            report['checks']['capture'] = app.camera.snapshot()
            report['checks']['analysis'] = app.analysis.snapshot()
            report['checks']['preview'] = app.preview.snapshot()
            report['checks']['gui_painted_frames'] = window.painted_frames
            report['checks']['fresh_neural_results_observed'] = len(seen_results)
            if app.analysis.processed < 2 or len(seen_results) < 2:
                raise RuntimeError('Frozen neural worker did not produce two observable fresh results')
            if app.preview.frames < 2 or window.painted_frames < 2:
                raise RuntimeError('Native preview failed to render')
            if report['checks']['analysis']['state'] == 'ERROR':
                raise RuntimeError('Analysis worker reported ERROR')
            # Pausing analysis must preserve the capture PID and its advancing preview.
            camera_pid = app.camera.snapshot()['worker_pid']
            app.pause_analysis()
            preview_before = app.preview.frames
            end = time.monotonic() + .8
            while time.monotonic() < end:
                root.update(); time.sleep(.01)
            if app.analysis is not None or app.preview.frames <= preview_before:
                raise RuntimeError('Pausing analysis interrupted the live preview')
            app.resume_analysis()
            resumed_results = set()
            end = time.monotonic() + 20
            while time.monotonic() < end:
                root.update(); time.sleep(.01)
                if errors:
                    raise RuntimeError(errors[-1])
                _observe_current_result(app.analysis, resumed_results)
                if len(resumed_results) >= 2:
                    break
            if (app.camera.snapshot()['worker_pid'] != camera_pid or
                    app.analysis.processed < 2 or len(resumed_results) < 2):
                raise RuntimeError('Analysis resume failed or reconnected the camera')
            report['checks']['fresh_neural_results_after_resume'] = len(resumed_results)
            report['checks']['pause_resume_keeps_camera'] = True
            eid = app.photo()
            if not app.evidence.flush(10) or not (scratch/'data'/'evidence'/eid/'evento.json').is_file():
                raise RuntimeError('Evidence was not persisted')
            if not app.events.flush(10):
                raise RuntimeError('SQLite writes did not finish')
            integrity = app.integrity()
            if integrity['database'] != ['ok']:
                raise RuntimeError('SQLite integrity check failed')
            report['checks']['evidence'] = app.evidence.health()
            report['checks']['database_integrity'] = integrity['database']
            report['checks']['frozen_internal_tool'] = app.jobs.run(
                tool_command('validate-dataset', '--help'), scratch/'tool.log', timeout=60)
            if 'manifest' not in (scratch/'tool.log').read_text(encoding='utf-8', errors='replace'):
                raise RuntimeError('Internal evaluator command/log channel failed')
        report['checks']['shutdown'] = True
        report['checks']['python_network_blocked'] = True
        report['passed'] = True
    except BaseException:
        report['errors'].append(traceback.format_exc())
    finally:
        socket.socket.connect = original_connect
        try:
            cleanup_runtime()
        except Exception:
            report['errors'].append(traceback.format_exc())
            report['passed'] = False
        report['seconds'] = time.monotonic()-began
        args.report = args.report.resolve()
        args.report.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.report.with_suffix(args.report.suffix+'.tmp')
        temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
        os.replace(temporary, args.report)
    return 0 if report['passed'] else 1
