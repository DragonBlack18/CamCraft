"""Versioned, atomic object calibration. References are PNGs, never pickle files."""
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
from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_OBJECTS = 8
PATCH_SIZE = 80
SCENE_SIZE = (320, 180)


def source_signature(camera) -> str:
    """Invalidates calibrations when a profile points at another device or file."""
    values = {k: getattr(camera, k) for k in ('id', 'kind', 'source')}
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def roi_pixels(roi, shape):
    h, w = shape[:2]
    a, b, c, d = roi
    return max(0, int(a*w)), max(0, int(b*h)), min(w, int(round(c*w))), min(h, int(round(d*h)))


def patch(frame, roi):
    a, b, c, d = roi_pixels(roi, frame.shape)
    if c-a < 4 or d-b < 4:
        raise ValueError('Objeto pequeno demais neste quadro.')
    return cv2.GaussianBlur(cv2.resize(frame[b:d, a:c], (PATCH_SIZE, PATCH_SIZE), interpolation=cv2.INTER_AREA), (3, 3), 0)


def scene(frame):
    return cv2.resize(frame, SCENE_SIZE, interpolation=cv2.INTER_AREA)


def atomic_json(path, document):
    tmp = path.with_name('.'+path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with tmp.open('w', encoding='utf-8') as f:
            json.dump(document, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


class InteractionConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool = True
    present_seconds: float = Field(default=1.0, ge=.5, le=10)
    absent_seconds: float = Field(default=1.5, ge=.8, le=15)
    min_observations: int = Field(default=3, ge=3, le=20)
    max_gap_seconds: float = Field(default=1.5, ge=.4, le=5)
    unknown_seconds: float = Field(default=3.0, ge=1, le=20)
    contact_seconds: float = Field(default=.4, ge=.2, le=3)
    association_ttl: float = Field(default=8, ge=2, le=15)
    clips: bool = True


class ObjectSpec(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(pattern=r'^o_[0-9a-f]{16}$')
    name: str = Field(min_length=1, max_length=60)
    camera_id: str
    source_signature: str = Field(pattern=r'^[0-9a-f]{64}$')
    roi: tuple[float, float, float, float]
    class_id: int | None = Field(default=None, ge=1, le=79)
    enabled: bool = True
    reference_dir: str = Field(pattern=r'^r_[0-9a-f]{32}$')
    hashes: dict[str, str]
    width: int = Field(ge=32, le=8192)
    height: int = Field(ge=32, le=8192)
    separation: float = Field(gt=0, le=1)
    created_utc: float
    @model_validator(mode='after')
    def geometry(self):
        if not all(math.isfinite(v) and 0 <= v <= 1 for v in self.roi):
            raise ValueError('Coordenadas inválidas.')
        a,b,c,d = self.roi
        if c <= a or d <= b or (c-a)*(d-b) > .35:
            raise ValueError('Selecione somente o objeto/local (até 35% da imagem).')
        if any(ord(c)<32 for c in self.name) or not self.name.strip():
            raise ValueError('Nome inválido.')
        if set(self.hashes) != {'vazio.png','presente.png','cena.png'}:
            raise ValueError('Referências incompletas.')
        if not all(re.fullmatch('[0-9a-f]{64}', v) for v in self.hashes.values()):
            raise ValueError('Hash de referência inválido.')
        return self


def reference_features(empty, present):
    difference = np.mean(np.abs(present.astype(np.float32)-empty.astype(np.float32)), axis=2)
    mask = cv2.dilate((difference > 14).astype(np.uint8), np.ones((3,3),np.uint8)).astype(bool)
    coverage = float(mask.mean())
    separation = float(difference[mask].mean()/255) if mask.any() else 0.
    return mask, separation, coverage


class ObjectRegistry:
    def __init__(self, directory: Path):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = directory/'objects.json'
        self.refs = directory/'references'; self.refs.mkdir(exist_ok=True)
        self.lock = threading.RLock()
        self.objects: list[ObjectSpec] = []
        self.configs: dict[str, InteractionConfig] = {}
        if self.path.exists():
            data=json.loads(self.path.read_text(encoding='utf-8'))
            if data.get('schema') != 1:
                raise ValueError('Cadastro de objetos incompatível. Arquivo preservado.')
            self.objects=[ObjectSpec.model_validate(v) for v in data['objects']]
            self.configs={k:InteractionConfig.model_validate(v) for k,v in data.get('cameras',{}).items()}
            if len({o.id for o in self.objects}) != len(self.objects):
                raise ValueError('IDs de objetos duplicados.')
            for cam in {o.camera_id for o in self.objects}:
                if len([o for o in self.objects if o.camera_id==cam]) > MAX_OBJECTS:
                    raise ValueError('Limite de objetos excedido no cadastro.')

    def all(self, camera_id):
        with self.lock:return [o.model_copy(deep=True) for o in self.objects if o.camera_id==camera_id]

    def config(self, camera_id):
        with self.lock:return self.configs.get(camera_id, InteractionConfig()).model_copy(deep=True)

    def _save(self, objects=None, configs=None):
        objects = self.objects if objects is None else objects
        configs = self.configs if configs is None else configs
        atomic_json(self.path, {'schema':1, 'objects':[o.model_dump() for o in objects],
            'cameras':{k:v.model_dump() for k,v in configs.items()}})
        self.objects=objects; self.configs=configs

    def configure(self, camera_id, cfg):
        with self.lock:self._save(configs={**self.configs, camera_id:InteractionConfig.model_validate(cfg.model_dump())})

    def set_enabled(self, oid, enabled):
        with self.lock:
            if not any(o.id==oid for o in self.objects):raise ValueError('Objeto não encontrado.')
            rows=[o.model_copy(update={'enabled':bool(enabled)}) if o.id==oid else o for o in self.objects]
            self._save(objects=rows)

    def delete(self, oid):
        with self.lock:
            previous=next((o for o in self.objects if o.id==oid),None)
            if previous is None:raise ValueError('Objeto não encontrado.')
            self._save(objects=[o for o in self.objects if o.id!=oid])
            # Only this app's generated calibration; never event evidence.
            p=self.refs/previous.reference_dir
            if p.is_dir() and not p.is_symlink():shutil.rmtree(p,ignore_errors=True)

    def load(self, spec):
        directory=self.refs/spec.reference_dir
        if directory.is_symlink() or directory.resolve().parent != self.refs.resolve():
            raise ValueError('Caminho de referência inválido.')
        images={}
        for name,digest in spec.hashes.items():
            p=directory/name
            if p.is_symlink() or not p.is_file() or p.stat().st_size>2*1024**2:
                raise ValueError('Referência ausente ou inválida; recadastre o objeto.')
            data=p.read_bytes()
            if hashlib.sha256(data).hexdigest()!=digest:
                raise ValueError('Integridade da referência divergente; recadastre o objeto.')
            image=cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR)
            expected=(SCENE_SIZE[1], SCENE_SIZE[0],3) if name=='cena.png' else (PATCH_SIZE,PATCH_SIZE,3)
            if image is None or image.shape!=expected:
                raise ValueError('Dimensões da referência inválidas.')
            images[name]=image
        return images

    def create(self, camera, name, roi, empty_frame, present_frame, class_id=None, replace_id=None):
        with self.lock:
            old=next((o for o in self.objects if o.id==replace_id and o.camera_id==camera.id),None)
            if replace_id and not old:raise ValueError('Objeto para recalibração não encontrado.')
            rows=self.all(camera.id)
            if old is None and len(rows)>=MAX_OBJECTS:raise ValueError('Limite: 8 objetos por câmera.')
            for image in (empty_frame,present_frame):
                if not isinstance(image,np.ndarray) or image.dtype!=np.uint8 or image.ndim!=3 or image.shape[2]!=3:
                    raise ValueError('Quadros de calibração inválidos.')
            if empty_frame.shape!=present_frame.shape:raise ValueError('A resolução mudou entre as referências.')
            if len(roi)!=4 or not all(math.isfinite(v) and 0<=v<=1 for v in roi):raise ValueError('Área inválida.')
            a,b,c,d=roi_pixels(roi,present_frame.shape)
            if c-a<24 or d-b<24:raise ValueError('Selecione um objeto com pelo menos 24 × 24 pixels reais.')
            for other in rows:
                if old and old.id==other.id:continue
                x,y,z,t=other.roi
                inter=max(0,min(roi[2],z)-max(roi[0],x))*max(0,min(roi[3],t)-max(roi[1],y))
                if inter/max(1e-9,min((roi[2]-roi[0])*(roi[3]-roi[1]),(z-x)*(t-y)))>.35:
                    raise ValueError('Áreas de objetos sobrepostas. Separe os locais monitorados.')
            empty=patch(empty_frame,roi); present=patch(present_frame,roi)
            mask,separation,coverage=reference_features(empty,present)
            if separation<.07 or coverage<.08:
                raise ValueError('Vazio/presente parecidos demais. Aproxime a câmera, ajuste a área ou melhore a luz.')
            # Ensure reference captures differ locally, not because the camera/lights changed.
            s0=scene(empty_frame); s1=scene(present_frame)
            outside=np.ones(s0.shape[:2],bool)
            for area in [roi]+[o.roi for o in rows]:
                x,y,z,t=roi_pixels(area,s0.shape); outside[max(0,y-3):min(180,t+3),max(0,x-3):min(320,z+3)]=False
            diff=np.mean(np.abs(s0.astype(np.float32)-s1.astype(np.float32)),axis=2)
            if outside.mean()<.3 or float(np.mean(diff[outside]))>14:
                raise ValueError('Cena mudou entre as fotos. Afaste as pessoas, mantenha câmera/luz fixas e refaça.')
            refdir='r_'+uuid.uuid4().hex
            dest=self.refs/refdir; dest.mkdir()
            try:
                hashes={}
                for filename,image in [('vazio.png',empty),('presente.png',present),('cena.png',s1)]:
                    ok,data=cv2.imencode('.png',image)
                    if not ok:raise OSError('Não foi possível codificar referência.')
                    content=data.tobytes();(dest/filename).write_bytes(content)
                    hashes[filename]=hashlib.sha256(content).hexdigest()
                spec=ObjectSpec(id=old.id if old else 'o_'+uuid.uuid4().hex[:16],name=name.strip(),camera_id=camera.id,
                    source_signature=source_signature(camera),roi=roi,class_id=class_id,reference_dir=refdir,hashes=hashes,
                    width=present_frame.shape[1],height=present_frame.shape[0],separation=separation,created_utc=time.time())
                self._save(objects=[o for o in self.objects if not old or o.id!=old.id]+[spec])
            except Exception:
                shutil.rmtree(dest,ignore_errors=True);raise
            if old:
                previous=self.refs/old.reference_dir
                if previous.is_dir() and not previous.is_symlink():shutil.rmtree(previous,ignore_errors=True)
            return spec.model_copy(deep=True)
