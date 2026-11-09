"""Independent labeled evaluation and explicit acceptance gate. No implicit training."""
from __future__ import annotations

import hashlib
import json
import math
import time
from pathlib import Path

import cv2
import numpy as np

from .dataset import validate_boxes
from .evaluation import match_frame, summarize
from .model import MODEL_SHA256


def evaluate_manifest(manifest_path, detector, *, confidence=.45, iou=.5, sweep=False, cancelled=None):
    path = Path(manifest_path).resolve()
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('fully_labeled') is not True:
        raise ValueError('Conjunto não confirmado como completamente anotado.')
    split = data.get('split', 'evaluation')
    if sweep and split != 'val':
        raise ValueError('Calibração de limiar exige split val; não ajuste no conjunto de teste.')
    if not math.isfinite(confidence) or not .25 <= confidence <= .9 or not 0 < iou <= 1:
        raise ValueError('Limiar/IoU inválido.')
    classes = data.get('class_ids')
    if not isinstance(classes, list) or not classes or len(classes) != len(set(classes)) or any(isinstance(c, bool) or not isinstance(c, int) or not 0 <= c < 80 for c in classes):
        raise ValueError('Escopo de categorias inválido.')
    images = data.get('images')
    if not isinstance(images, list) or not 1 <= len(images) <= 10000:
        raise ValueError('Use entre 1 e 10.000 imagens.')
    thresholds = [.25, .35, .45, .55, .65, .75, .85] if sweep else [confidence]
    values = {t: [] for t in thresholds}
    details, durations, hashes, groups = [], [], set(), set()
    positives = negatives = truth_objects = 0
    for row in images:
        if cancelled and cancelled():
            raise InterruptedError('Avaliação cancelada pelo operador.')
        from .safe_archive import safe_name
        safe_name(row['image'])
        file = (path.parent / row['image']).resolve()
        if path.parent not in file.parents or file.is_symlink() or not file.is_file() or file.stat().st_size > 32 * 1024**2:
            raise ValueError('Imagem fora do conjunto ou acima do limite.')
        raw = file.read_bytes(); sha = hashlib.sha256(raw).hexdigest()
        if sha in hashes:
            raise ValueError('Imagem repetida: avaliação recusada.')
        if row.get('sha256') and sha != row['sha256']:
            raise ValueError('Imagem diverge do SHA-256 anotado.')
        hashes.add(sha)
        frame = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError('Imagem não pôde ser decodificada.')
        truth = validate_boxes(row.get('objects'), frame.shape[1], frame.shape[0], classes)
        positives += bool(truth); negatives += not bool(truth); truth_objects += len(truth)
        group = row.get('group')
        if group: groups.add(group)
        began = time.perf_counter(); predictions = detector.detect(frame); durations.append((time.perf_counter() - began) * 1000)
        predictions = [p for p in predictions if p['class_id'] in classes]
        for threshold in thresholds:
            counts = match_frame([p for p in predictions if p['score'] >= threshold], truth, iou)
            values[threshold].append(counts)
        details.append({'image': row['image'], 'sha256': sha, 'group': group,
                        'truth_objects': len(truth), 'predictions': predictions})
    results = {str(t): summarize(v) for t, v in values.items()}
    return {'schema': 1, 'kind': 'vision-detection-evaluation', 'created_utc': time.time(),
            'split': split, 'calibration_sweep': sweep, 'confidence': None if sweep else confidence, 'iou': iou,
            'model_sha256': MODEL_SHA256, 'dataset_manifest_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'classes': classes, 'images': len(images), 'positive_images': positives, 'negative_images': negatives,
            'truth_objects': truth_objects, 'groups': sorted(groups), 'results': results,
            'inference_ms': {'p50': float(np.percentile(durations, 50)), 'p95': float(np.percentile(durations, 95))},
            'per_image': details,
            'note': 'Precision/recall de detecção em imagens rotuladas. Não mede rastreamento, ações, autoria, mAP, latência câmera→tela ou garantia em produção.'}


def acceptance_gate(report, *, min_images=100, min_positive=20, min_negative=20, min_groups=3,
                    min_precision=.95, min_recall=.90, max_inference_p95_ms=500, min_class_objects=5):
    """Provisional, configurable acceptance policy. Insufficient data is NOT a pass."""
    if report.get('kind') != 'vision-detection-evaluation' or report.get('schema') != 1:
        raise ValueError('Relatório incompatível.')
    thresholds = report.get('results', {})
    metrics = next(iter(thresholds.values())) if len(thresholds) == 1 else {}
    overall = metrics.get('overall', {})
    per_class = metrics.get('per_class', {})
    class_checks = {}
    for cid in report.get('classes', []):
        row = per_class.get(str(cid), {})
        class_checks[str(cid)] = {
            'labeled_objects': row.get('tp', 0) + row.get('fn', 0) >= min_class_objects,
            'precision': row.get('precision') is not None and row['precision'] >= min_precision,
            'recall': row.get('recall') is not None and row['recall'] >= min_recall}
    checks = {'independent_test_split': report.get('split') == 'test' and not report.get('calibration_sweep'),
              'sample_count': report.get('images', 0) >= min_images,
              'positive_images': report.get('positive_images', 0) >= min_positive,
              'negative_images': report.get('negative_images', 0) >= min_negative,
              'independent_groups': len(report.get('groups', [])) >= min_groups,
              'precision': overall.get('precision') is not None and overall['precision'] >= min_precision,
              'recall': overall.get('recall') is not None and overall['recall'] >= min_recall,
              'inference_p95': report.get('inference_ms', {}).get('p95', float('inf')) <= max_inference_p95_ms,
              'all_requested_classes': bool(class_checks) and all(all(c.values()) for c in class_checks.values())}
    return {'decision': 'PASS' if all(checks.values()) else 'NOT_ACCEPTED', 'checks': checks, 'class_checks': class_checks,
            'policy': {'min_images': min_images, 'min_positive': min_positive, 'min_negative': min_negative,
                       'min_groups': min_groups, 'min_precision': min_precision, 'min_recall': min_recall,
                       'max_inference_p95_ms': max_inference_p95_ms, 'min_class_objects': min_class_objects},
            'note': 'Critério configurável para este ensaio, não certificação de segurança. Falta de dados impede aprovação. Associação de retirada requer avaliação separada de eventos.'}
