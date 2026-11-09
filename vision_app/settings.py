from __future__ import annotations
import json
import math
import os
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

class AnalysisConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    engine: Literal['yolox', 'hog', 'regions'] = 'yolox'
    classes: Literal['all', 'people', 'indoor', 'bedroom', 'custom'] = 'bedroom'
    custom_classes: tuple[int, ...] = (0,)
    class_thresholds: dict[int, float] = Field(default_factory=dict)
    class_margin: float = Field(default=0.15, ge=0.0, le=0.9)
    show_tentative: bool = False
    recovery_seconds: float = Field(default=1.25, ge=0.0, le=5.0)
    confirmation_gap: float = Field(default=2.5, ge=0.2, le=5.0)
    confidence: float = Field(default=0.60, ge=0.25, le=0.95)
    low_confidence: float = Field(default=0.1, ge=0.05, le=0.2)
    nms_iou: float = Field(default=0.45, ge=0.2, le=0.8)
    adaptive_pacing: bool = True
    duty_cycle: float = Field(default=0.65, ge=0.3, le=1.0)
    max_fps: int = Field(default=8, ge=1, le=30)
    threads: int = Field(default=2, ge=1, le=8)
    max_detections: int = Field(default=100, ge=1, le=200)
    min_hits: int = Field(default=3, ge=2, le=10)
    confirm_seconds: float = Field(default=0.55, ge=0.1, le=3)
    lost_seconds: float = Field(default=2.0, ge=0.5, le=10)
    max_frame_age: float = Field(default=2.0, ge=0.5, le=5)
    watchdog_seconds: float = Field(default=15, ge=3, le=60)
    roi: tuple[float, float, float, float] | None = None
    line: tuple[float, float, float, float] | None = None
    positive_is_entry: bool = True
    save_evidence: bool = True
    evidence_limit_mb: int = Field(default=512, ge=50, le=10240)
    evidence_limit_files: int = Field(default=1000, ge=20, le=10000)

    def class_ids(self):
        from .classes import allowed
        return allowed(self.classes, self.custom_classes)

    def threshold(self, class_id: int) -> float:
        return self.class_thresholds.get(class_id, self.confidence)

    @model_validator(mode='after')
    def geometry(self):
        if any(not 0 <= c < 80 for c in self.custom_classes):
            raise ValueError('Categoria fora do intervalo 0–79.')
        if self.classes == 'custom' and not self.custom_classes:
            raise ValueError('Selecione pelo menos uma categoria ou pause a IA.')
        self.custom_classes = tuple(sorted(set(self.custom_classes)))
        if any(not 0 <= c < 80 or not math.isfinite(v) or not .25 <= v <= .95
               for c, v in self.class_thresholds.items()):
            raise ValueError('Limiar por categoria deve ficar entre 0,25 e 0,95.')

        for name in ('roi', 'line'):
            val = getattr(self, name)
            if val and (not all(math.isfinite(v) and 0 <= v <= 1 for v in val)):
                raise ValueError('Coordenadas devem ficar entre 0 e 1.')
        if self.roi:
            x1, y1, x2, y2 = self.roi
            if x2 - x1 < .04 or y2 - y1 < .04:
                raise ValueError('A área deve ter largura e altura de pelo menos 4% da imagem.')
        if self.line:
            x1, y1, x2, y2 = self.line
            if math.hypot(x2-x1, y2-y1) < .08:
                raise ValueError('A linha é muito curta.')
        return self

class SettingsStore:
    def __init__(self, directory: Path):
        self.path = directory / 'analysis.json'
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self.rows = {}
        self.migration_notice = None
        if self.path.exists():
            obj = json.loads(self.path.read_text(encoding='utf-8'))
            if obj.get('schema') not in (2, 3):
                raise ValueError('Configuração de análise incompatível; arquivo preservado.')
            # Preserve the original before applying the explicitly documented v4.1 safety migration.
            # Legacy 'all' was the default, not an informed indoor profile. Do not keep vehicles enabled silently.
            legacy = obj.get('schema') == 2
            for k, value in obj['cameras'].items():
                value = dict(value)
                if legacy and value.get('classes', 'all') == 'all':
                    value['classes'] = 'bedroom'
                self.rows[k] = AnalysisConfig.model_validate(value)
            if legacy:
                backup = self.directory / 'analysis.pre-v4.1.json'
                if not backup.exists():
                    with backup.open('x', encoding='utf-8') as f:
                        f.write(self.path.read_text(encoding='utf-8'))
                self.migration_notice = ('Configuração v4 preservada em analysis.pre-v4.1.json. '
                    'O perfil antigo Todas foi convertido em Quarto; demais parâmetros preservados. '
                    'Controles permite reativar categorias explicitamente.')
                self._save()


    def get(self, key: str) -> AnalysisConfig:
        return self.rows.get(key, AnalysisConfig()).model_copy(deep=True)

    def put(self, key: str, config: AnalysisConfig):
        old = dict(self.rows)
        self.rows[key] = config.model_copy(deep=True)
        try:
            self._save()
        except Exception:
            self.rows = old
            raise

    def _save(self):
        tmp = self.path.with_suffix('.tmp')
        with tmp.open('w', encoding='utf-8') as f:
            json.dump({'schema': 3, 'cameras': {k:v.model_dump() for k,v in self.rows.items()}}, f, ensure_ascii=False, indent=2)
            f.flush(); os.fsync(f.fileno())
        os.replace(tmp, self.path)
