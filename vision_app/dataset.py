"""Human annotations, grouped splits, COCO/YOLO exports. Never labels predictions as truth."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import threading
import time
import uuid
from pathlib import Path

import cv2
import numpy as np

from .classes import NAMES
from .object_registry import atomic_json
from .safe_archive import digest, write_archive
from .evidence_review import json_bytes, read_json

SAMPLE_ID = re.compile(r's_[0-9a-f]{32}')


def validate_boxes(boxes, width, height, class_ids):
    if not isinstance(boxes, list) or len(boxes) > 200:
        raise ValueError('Use uma lista com até 200 caixas.')
    result = []
    for item in boxes:
        cid, box = item.get('class_id'), item.get('box')
        if isinstance(cid, bool) or cid not in class_ids or not isinstance(box, (list, tuple)) or len(box) != 4:
            raise ValueError('Categoria/caixa inválida.')
        if any(isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) for v in box):
            raise ValueError('Coordenadas inválidas.')
        if not (0 <= box[0] < box[2] <= width and 0 <= box[1] < box[3] <= height):
            raise ValueError('Caixa fora dos limites da imagem.')
        result.append({'class_id': int(cid), 'box': [float(v) for v in box]})
    return result


class DatasetStore:
    MAX_SAMPLES = 3000
    MAX_BYTES = 2 * 1024**3

    def __init__(self, directory: Path):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()

    def folder(self, sid):
        if not isinstance(sid, str) or not SAMPLE_ID.fullmatch(sid):
            raise ValueError('ID de amostra inválido.')
        folder = self.directory / sid
        if folder.is_symlink():
            raise ValueError('Amostra não pode ser link simbólico.')
        return folder

    def list(self):
        with self.lock:
            result = []
            for folder in self.directory.glob('s_*'):
                if folder.is_symlink() or not SAMPLE_ID.fullmatch(folder.name):
                    continue
                try:
                    row = read_json(folder / 'sample.json')
                    if row.get('schema') != 1 or row.get('id') != folder.name:
                        raise ValueError('Manifesto incompatível.')
                    result.append(row)
                except (ValueError, OSError, TypeError):
                    result.append({'id': folder.name, 'state': 'INVALID', 'created_utc': 0, 'group': '', 'objects': []})
            return sorted(result, key=lambda row: (row['created_utc'], row['id']))

    def capture(self, frame, metadata, *, camera_id, group=None):
        if frame is None or frame.dtype != np.uint8 or frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError('Amostra precisa de imagem BGR uint8.')
        h, w = frame.shape[:2]
        if w < 16 or h < 16 or w * h > 4096 * 2160:
            raise ValueError('Dimensões da amostra fora do limite.')
        # Source/session, not individual frames, defines the split group.
        group = group or (str(camera_id) + ':' + str(metadata.get('session') or 'manual'))
        if not isinstance(group, str) or not group.strip() or len(group) > 160:
            raise ValueError('Grupo de gravação inválido.')
        ok, encoded = cv2.imencode('.png', frame)
        if not ok:
            raise OSError('Imagem não pôde ser codificada.')
        content = encoded.tobytes(); sha = hashlib.sha256(content).hexdigest()
        with self.lock:
            rows = self.list()
            if len(rows) >= self.MAX_SAMPLES:
                raise ValueError('Limite de amostras atingido. Exporte/arquive o conjunto antes de continuar.')
            if any(row.get('image_sha256') == sha for row in rows):
                raise ValueError('Imagem idêntica já capturada; amostra duplicada não foi adicionada.')
            total = sum(p.stat().st_size for p in self.directory.glob('s_*/image.png') if p.is_file() and not p.is_symlink())
            if total + len(content) > self.MAX_BYTES:
                raise ValueError('Conjunto excede 2 GiB. Nenhuma amostra foi apagada.')
            sid = 's_' + uuid.uuid4().hex
            folder = self.folder(sid); stage = self.directory / ('.pending-' + sid)
            stage.mkdir()
            try:
                (stage / 'image.png').write_bytes(content)
                row = {'schema': 1, 'id': sid, 'created_utc': time.time(), 'camera_id': str(camera_id),
                       'group': group.strip(), 'width': w, 'height': h, 'image_sha256': sha,
                       'state': 'DRAFT', 'objects': [], 'class_ids': [0], 'revision': 0,
                       'source': {k: metadata.get(k) for k in ('session', 'sequence', 'received_utc', 'generation')},
                       'note': 'Imagem capturada, ainda sem rótulos humanos completos. Não é ground truth até revisão explícita.'}
                atomic_json(stage / 'sample.json', row)
                os.replace(stage, folder)
            finally:
                shutil.rmtree(stage, ignore_errors=True)
            return row

    def load(self, sid):
        with self.lock:
            folder = self.folder(sid); row = read_json(folder / 'sample.json')
            if row.get('schema') != 1 or row.get('id') != sid:
                raise ValueError('Manifesto de amostra inválido.')
            path = folder / 'image.png'
            if path.is_symlink() or not path.is_file() or digest(path) != row.get('image_sha256'):
                raise ValueError('Imagem da amostra ausente/divergente.')
            image = cv2.imdecode(np.frombuffer(path.read_bytes(), np.uint8), cv2.IMREAD_COLOR)
            if image is None or image.shape[:2] != (row['height'], row['width']):
                raise ValueError('Dimensões da imagem divergentes.')
            return row, image

    def annotate(self, sid, boxes, *, class_ids, complete, expected_revision, group=None):
        if not isinstance(class_ids, list) or not class_ids or len(set(class_ids)) != len(class_ids):
            raise ValueError('Defina o conjunto de categorias anotadas.')
        if any(isinstance(c, bool) or not isinstance(c, int) or not 0 <= c < 80 for c in class_ids):
            raise ValueError('Categorias precisam estar entre 0 e 79.')
        if not isinstance(complete, bool):
            raise ValueError('Confirmação explícita de anotação necessária.')
        with self.lock:
            row, _ = self.load(sid)
            if row['revision'] != expected_revision:
                raise ValueError('Amostra mudou em outra janela. Recarregue antes de salvar.')
            checked = validate_boxes(boxes, row['width'], row['height'], class_ids)
            group = row['group'] if group is None else group.strip()
            if not group or len(group) > 160:
                raise ValueError('Grupo de gravação inválido.')
            # Keep revision history local; it is not a signed identity record.
            history = self.folder(sid) / 'history'
            history.mkdir(exist_ok=True)
            atomic_json(history / f"r{row['revision']:06}.json", row)
            row.update(objects=checked, class_ids=sorted(class_ids), state='LABELED' if complete else 'DRAFT',
                       group=group, revision=row['revision'] + 1, annotated_utc=time.time())
            atomic_json(self.folder(sid) / 'sample.json', row)
            return row

    def export(self, target, *, split=True, seed='vision-local-v4', class_ids=None):
        with self.lock:
            rows = [r for r in self.list() if r.get('state') == 'LABELED']
            if not rows:
                raise ValueError('Nenhuma amostra foi confirmada como completamente anotada.')
            scopes = {tuple(r['class_ids']) for r in rows}
            if class_ids is None:
                if len(scopes) != 1:
                    raise ValueError('Escopos de anotação diferentes. Exporte separadamente por categorias.')
                class_ids = list(next(iter(scopes)))
            class_ids = sorted(class_ids)
            rows = [r for r in rows if r['class_ids'] == class_ids]
            if not rows:
                raise ValueError('Nenhuma amostra para esse escopo de categorias.')
            hashes = set()
            for row in rows:
                checked, _ = self.load(row['id'])
                validate_boxes(checked['objects'], checked['width'], checked['height'], class_ids)
                if row['image_sha256'] in hashes:
                    raise ValueError('Imagem duplicada no conjunto. Exportação recusada.')
                hashes.add(row['image_sha256'])
            groups = sorted({r['group'] for r in rows}, key=lambda g: hashlib.sha256((seed + ':' + g).encode()).hexdigest())
            if split and len(groups) < 3:
                raise ValueError('Separação exige pelo menos três grupos independentes de gravação. Não divida quadros do mesmo vídeo em grupos diferentes.')
            if split:
                ntest = max(1, int(len(groups) * .2)); nval = max(1, int(len(groups) * .2))
                assignment = {g: 'test' if i < ntest else 'val' if i < ntest + nval else 'train' for i, g in enumerate(groups)}
            else:
                assignment = dict.fromkeys(groups, 'evaluation')
            members, split_rows = [], {}
            remap = {cid: i for i, cid in enumerate(class_ids)}
            for row in rows:
                name = assignment[row['group']]; sid = row['id']; image = f'images/{name}/{sid}.png'
                members.append((image, self.folder(sid) / 'image.png'))
                lines = []
                for obj in row['objects']:
                    x1, y1, x2, y2 = obj['box']; w, h = row['width'], row['height']
                    lines.append(f"{remap[obj['class_id']]} {(x1+x2)/2/w:.8f} {(y1+y2)/2/h:.8f} {(x2-x1)/w:.8f} {(y2-y1)/h:.8f}")
                members.append((f'labels/{name}/{sid}.txt', ('\n'.join(lines) + ('\n' if lines else '')).encode()))
                split_rows.setdefault(name, []).append({**row, 'image': image})
            for name, selected in split_rows.items():
                manifest = {'schema': 1, 'fully_labeled': True, 'split': name, 'class_ids': class_ids,
                            'groups': sorted({r['group'] for r in selected}),
                            'images': [{'image': r['image'], 'objects': r['objects'], 'group': r['group'], 'sha256': r['image_sha256']} for r in selected]}
                members.append((name + '.json', json_bytes(manifest)))
                coco = {'images': [], 'annotations': [], 'categories': [{'id': remap[c] + 1, 'name': NAMES[c]} for c in class_ids]}
                ann_id = 0
                for img_id, r in enumerate(selected, 1):
                    coco['images'].append({'id': img_id, 'file_name': r['image'], 'width': r['width'], 'height': r['height']})
                    for obj in r['objects']:
                        ann_id += 1; x1, y1, x2, y2 = obj['box']
                        coco['annotations'].append({'id': ann_id, 'image_id': img_id, 'category_id': remap[obj['class_id']] + 1,
                                                    'bbox': [x1, y1, x2-x1, y2-y1], 'area': (x2-x1)*(y2-y1), 'iscrowd': 0})
                members.append(('coco_' + name + '.json', json_bytes(coco)))
            overview = {'schema': 1, 'seed': seed, 'class_mapping': {str(remap[c]): {'source_class_id': c, 'name': NAMES[c]} for c in class_ids},
                        'groups': assignment, 'counts': {k: len(v) for k, v in split_rows.items()},
                        'note': 'Grupos independentes são responsabilidade do operador. Sem treino automático; holdout não deve orientar calibração. IDs de categorias COCO exportados são contíguos, não os IDs esparsos oficiais.'}
            members.append(('dataset.json', json_bytes(overview)))
            # JSON is valid YAML: avoids malformed names/path interpolation.
            config = {'path': '.', 'names': [NAMES[c] for c in class_ids]}
            config.update({k: 'images/' + k for k in split_rows})
            members.append(('data.yaml', json_bytes(config)))
            members.append(('LEIA.txt', b'Conjunto de imagens pessoais/local. Anotacoes humanas, nao previsoes. Nao publicar sem autorizacao. COCO e YOLO exportados; adaptador atual requer o grafo YOLOX oficial. Pesos treinados nao sao plug-and-play.\n'))
            return write_archive(Path(target), members, kind='vision-dataset', metadata=overview)
