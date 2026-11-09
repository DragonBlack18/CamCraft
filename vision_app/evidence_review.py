"""Read/verify/preserve evidence without a race against retention."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from .safe_archive import digest, write_archive
from .object_registry import atomic_json

EID = re.compile(r'e_[0-9a-f]{32}')


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8')


def read_json(path, max_bytes=4 * 1024**2):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > max_bytes:
        raise ValueError('Metadados ausentes, inválidos ou acima do limite.')
    return json.loads(path.read_text(encoding='utf-8'))


class EvidenceReview:
    def __init__(self, writer, reviews):
        self.writer = writer
        self.directory = writer.directory
        self.reviews = reviews

    def folder(self, eid):
        if not isinstance(eid, str) or not EID.fullmatch(eid):
            raise ValueError('Identificador de evidência inválido.')
        folder = self.directory / eid
        if folder.is_symlink():
            raise ValueError('Link simbólico não é uma evidência válida.')
        return folder

    def inspect(self, eid):
        with self.writer.access_lock:
            folder = self.folder(eid)
            result = {'evidence_id': eid, 'state': 'MISSING', 'issues': [], 'files': [],
                      'preserved': False, 'metadata': None, 'clip': None}
            if not folder.is_dir():
                result['issues'].append('Evidência ausente: pode não ter sido salva ou ter saído por retenção.')
                return result
            result['preserved'] = (folder / '.preservada').is_file()
            try:
                event = read_json(folder / 'evento.json')
                if event.get('evidence_id') != eid or not isinstance(event.get('sha256'), dict):
                    raise ValueError('Manifesto de evidência incompatível.')
                expected = dict(event['sha256'])
                if not {'quadro.jpg', 'anotado.jpg'} <= expected.keys():
                    raise ValueError('Imagens principais ausentes do manifesto.')
                result['metadata'] = event
                clip = folder / 'clip.json'
                if clip.exists():
                    document = read_json(clip)
                    if document.get('evidence_id') != eid or set(document.get('sha256', {})) != {'clip.avi'}:
                        raise ValueError('Manifesto de clipe incompatível.')
                    expected.update(document['sha256']); result['clip'] = document
                elif (folder / 'clip.avi').exists():
                    result['issues'].append('Clipe sem manifesto verificado.')
                for name, sha in expected.items():
                    if not re.fullmatch(r'(quadro|anotado|antes_o_[0-9a-f]{16})\.jpg|clip\.avi', name):
                        raise ValueError('Nome de evidência não permitido.')
                    path = folder / name
                    if path.is_symlink() or not path.is_file():
                        result['issues'].append('Arquivo ausente/inseguro: ' + name); continue
                    if path.stat().st_size > 128 * 1024**2:
                        raise ValueError('Arquivo de evidência acima do limite.')
                    valid = isinstance(sha, str) and digest(path) == sha
                    result['files'].append({'name': name, 'bytes': path.stat().st_size, 'verified': valid})
                    if not valid:
                        result['issues'].append('SHA-256 divergente: ' + name)
                pending = (folder / '.clip-pendente').exists()
                result['state'] = 'MODIFIED' if result['issues'] else 'PENDING' if pending else 'VERIFIED'
            except (ValueError, OSError, TypeError, KeyError) as exc:
                result['state'] = 'MODIFIED'; result['issues'].append(str(exc))
            result['note'] = 'Hashes verificam arquivos contra metadados locais; não autenticam a pessoa nem provam retirada.'
            return result

    def read_image(self, eid, name):
        with self.writer.access_lock:
            report = self.inspect(eid)
            if report['state'] not in ('VERIFIED', 'PENDING'):
                raise ValueError('Evidência ausente ou divergente. Não foi aberta como verificada.')
            if name not in [f['name'] for f in report['files'] if f['verified']] or not name.endswith('.jpg'):
                raise ValueError('Imagem não registrada.')
            import cv2
            import numpy as np
            image = cv2.imdecode(np.frombuffer((self.folder(eid) / name).read_bytes(), np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError('Imagem inválida.')
            return image

    def preserve(self, eid, enabled):
        with self.writer.access_lock:
            folder = self.folder(eid)
            if not folder.is_dir():
                raise ValueError('Evidência não disponível.')
            marker = folder / '.preservada'
            if enabled:
                atomic_json(marker, {'preserved_utc': time.time(), 'note': 'Excluída da retenção automática pelo operador local.'})
            else:
                marker.unlink(missing_ok=True)
            self.writer.store.emit(None, 'EVIDENCIA_PRESERVADA' if enabled else 'EVIDENCIA_LIBERADA',
                                   'Proteção contra retenção alterada pelo operador.', payload={'evidence_id': eid, 'preserved': bool(enabled)})
        return bool(enabled)

    def export_incident(self, row_id, target, *, allow_missing=False):
        row = self.reviews.get(row_id)
        if row is None:
            raise ValueError('Registro não encontrado.')
        eid = row['payload'].get('evidence_id')
        with self.writer.access_lock:
            report = self.inspect(eid) if eid else {'state': 'MISSING', 'issues': ['Evento sem evidência associada.']}
            if report['state'] == 'PENDING':
                raise ValueError('Clipe ainda em gravação. Tente após a conclusão.')
            if report['state'] == 'MODIFIED':
                raise ValueError('Evidência divergente. Exportação verificada recusada; preserve a pasta para investigação.')
            if report['state'] == 'MISSING' and not allow_missing:
                raise ValueError('Evidência ausente. Selecione exportação somente do registro.')
            members = [('registro.json', json_bytes(row)), ('revisoes.json', json_bytes(self.reviews.reviews(row_id))),
                       ('verificacao.json', json_bytes(report)),
                       ('LEIA.txt', b'Pacote local de observacao. Hashes nao provam autoria; IDs sao temporarios. Fotos e horarios podem ser dados pessoais.\n')]
            if report['state'] == 'VERIFIED':
                folder = self.folder(eid)
                for name in ['evento.json'] + [f['name'] for f in report['files']] + (['clip.json'] if report['clip'] else []):
                    members.append(('evidencia/' + name, folder / name))
            return write_archive(Path(target), members, kind='vision-incident', metadata={'event_row_id': row_id, 'evidence_state': report['state']})
