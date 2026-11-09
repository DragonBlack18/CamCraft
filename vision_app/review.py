"""Stable keyset history and transactional local review, without changing observations."""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import time
import uuid
from contextlib import closing

from .interactions import MAJOR_EVENTS

DECISIONS = ('CONFIRMADO', 'FALSO_POSITIVO', 'INCONCLUSIVO')


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def unpack(row):
    if row is None:
        return None
    result = dict(row)
    result['payload'] = json.loads(result['payload'])
    return result


class ReviewRepository:
    def __init__(self, store):
        self.store = store
        with closing(store.connect()) as db:
            db.executescript('''
                CREATE INDEX IF NOT EXISTS ix_events_code_id ON events(code,id);
                CREATE INDEX IF NOT EXISTS ix_events_utc_id ON events(utc,id);
                CREATE INDEX IF NOT EXISTS ix_legacy_review_target ON events(json_extract(payload,'$.reviewed_row_id'),id) WHERE code='REVISAO_EVENTO';
                CREATE TABLE IF NOT EXISTS audit_reviews(
                    id INTEGER PRIMARY KEY AUTOINCREMENT, review_id TEXT NOT NULL UNIQUE,
                    event_row_id INTEGER NOT NULL, event_key TEXT NOT NULL,
                    utc REAL NOT NULL, decision TEXT NOT NULL, operator TEXT NOT NULL,
                    note TEXT NOT NULL, event_snapshot TEXT NOT NULL,
                    previous_hash TEXT NOT NULL, record_hash TEXT NOT NULL,
                    body TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS ix_review_event ON audit_reviews(event_row_id,id);
            ''')

    def page(self, *, camera_id=None, code=None, text='', since=None, until=None,
             before=None, ceiling=None, limit=100, important_only=False, decision=None):
        limit = max(1, min(int(limit), 200))
        if decision is not None and decision not in (*DECISIONS, 'PENDENTE'):
            raise ValueError('Filtro de revisão inválido.')
        for value in (since, until):
            if value is not None and not math.isfinite(value):
                raise ValueError('Horário inválido.')
        if since is not None and until is not None and since > until:
            raise ValueError('Intervalo de datas invertido.')
        if len(text) > 160:
            raise ValueError('Busca muito longa.')
        with closing(self.store.connect()) as db:
            if ceiling is None:
                ceiling = db.execute('SELECT COALESCE(MAX(id),0) FROM events').fetchone()[0]
            where, args = ['e.id<=?'], [int(ceiling)]
            for field, op, val in [('camera_id', '=', camera_id), ('code', '=', code), ('utc', '>=', since),
                                   ('utc', '<=', until), ('id', '<', before)]:
                if val is not None:
                    where.append(f'e.{field}{op}?'); args.append(val)
            if text:
                escaped = text.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
                where.append("(e.message LIKE ? ESCAPE '\\' OR e.payload LIKE ? ESCAPE '\\')")
                args.extend(['%' + escaped + '%'] * 2)
            if important_only:
                codes = sorted(MAJOR_EVENTS)
                where.append('e.code IN (' + ','.join('?' for _ in codes) + ')'); args.extend(codes)
            # Correlated index lookups avoid loading all reviews into Python.
            review_expr = "(SELECT r.decision FROM audit_reviews r WHERE r.event_row_id=e.id AND r.event_key=COALESCE(json_extract(e.payload,'$.event_id'),'row:'||e.id) ORDER BY r.id DESC LIMIT 1)"
            legacy_expr = "(SELECT json_extract(l.payload,'$.decision') FROM events l WHERE l.code='REVISAO_EVENTO' AND json_extract(l.payload,'$.reviewed_row_id')=e.id ORDER BY l.id DESC LIMIT 1)"
            review_expr = 'COALESCE(' + review_expr + ',' + legacy_expr + ')'
            if decision:
                where.append(('COALESCE(' + review_expr + ",'PENDENTE')=?")); args.append(decision)
            query = 'SELECT e.*, ' + review_expr + ' AS review_decision FROM events e WHERE '
            query += ' AND '.join(where) + ' ORDER BY e.id DESC LIMIT ?'
            rows = [unpack(r) for r in db.execute(query, (*args, limit + 1))]
        more = len(rows) > limit
        return {'rows': rows[:limit], 'ceiling': ceiling,
                'next_before': rows[limit - 1]['id'] if more else None}

    def get(self, row_id):
        with closing(self.store.connect()) as db:
            return unpack(db.execute('SELECT * FROM events WHERE id=?', (int(row_id),)).fetchone())

    def reviews(self, row_id):
        with closing(self.store.connect()) as db:
            rows = [json.loads(r['body']) for r in db.execute(
                'SELECT body FROM audit_reviews WHERE event_row_id=? ORDER BY id', (int(row_id),))]
            # Preserve visible compatibility with phase 3 append-only review events.
            legacy = db.execute("SELECT utc,payload FROM events WHERE code='REVISAO_EVENTO' AND json_extract(payload,'$.reviewed_row_id')=? ORDER BY id", (int(row_id),))
            known = {r['review_id'] for r in rows}
            for r in legacy:
                data = json.loads(r['payload'])
                if data.get('review_id') not in known:
                    rows.append({'legacy_phase3': True, 'utc': r['utc'], **data})
        return sorted(rows, key=lambda r: r.get('utc', 0))

    def add(self, row_id, decision, *, note='', operator='operador local'):
        if decision not in DECISIONS:
            raise ValueError('Decisão de revisão inválida.')
        note, operator = note.strip(), operator.strip()
        if len(note) > 2000 or not operator or len(operator) > 80:
            raise ValueError('Use observação de até 2.000 caracteres e operador de até 80.')
        if not self.store.flush():
            raise OSError('Os registros pendentes não foram confirmados.')
        with closing(self.store.connect()) as db:
            db.execute('PRAGMA busy_timeout=2000')
            try:
                db.execute('BEGIN IMMEDIATE')
                row = unpack(db.execute('SELECT * FROM events WHERE id=?', (int(row_id),)).fetchone())
                if row is None or row['code'] not in MAJOR_EVENTS:
                    raise ValueError('Evento não disponível para revisão.')
                prior = db.execute('SELECT record_hash FROM audit_reviews ORDER BY id DESC LIMIT 1').fetchone()
                previous = prior[0] if prior else '0' * 64
                event_key = row['payload'].get('event_id') or 'row:' + str(row['id'])
                body = {'review_id': uuid.uuid4().hex, 'event_row_id': row['id'], 'event_key': event_key,
                        'utc': time.time(), 'decision': decision, 'operator': operator, 'note': note,
                        'event_snapshot': row, 'previous_hash': previous,
                        'identity_note': 'Nome informado localmente, sem autenticação de identidade.'}
                text = canonical(body)
                digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
                db.execute('INSERT INTO audit_reviews(review_id,event_row_id,event_key,utc,decision,operator,note,event_snapshot,previous_hash,record_hash,body) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                           (body['review_id'], row['id'], event_key, body['utc'], decision, operator, note, canonical(row), previous, digest, text))
                payload = {'review_id': body['review_id'], 'reviewed_row_id': row['id'], 'reviewed_event_id': event_key,
                           'object_id': row['payload'].get('object_id'), 'object_name': row['payload'].get('object_name'),
                           'decision': decision, 'operator': operator, 'note': note, 'record_hash': digest}
                db.execute('INSERT INTO events(utc,camera_id,level,code,message,payload) VALUES (?,?,?,?,?,?)',
                           (body['utc'], row['camera_id'], 'INFO', 'REVISAO_EVENTO',
                            'Revisão humana adicionada; observação original preservada.', canonical(payload)))
                db.commit()
            except BaseException:
                db.rollback(); raise
        return decision

    def verify_chain(self):
        previous, count = '0' * 64, 0
        with closing(self.store.connect()) as db:
            for row in db.execute('SELECT * FROM audit_reviews ORDER BY id'):
                body = json.loads(row['body'])
                if row['previous_hash'] != previous or body['previous_hash'] != previous:
                    raise ValueError('Cadeia de revisões interrompida.')
                if hashlib.sha256(canonical(body).encode()).hexdigest() != row['record_hash']:
                    raise ValueError('Conteúdo de revisão divergente.')
                for key in ('review_id', 'event_row_id', 'event_key', 'utc', 'decision', 'operator', 'note'):
                    if body[key] != row[key]:
                        raise ValueError('Coluna de revisão alterada: ' + key)
                if canonical(body['event_snapshot']) != row['event_snapshot']:
                    raise ValueError('Snapshot de revisão divergente.')
                previous = row['record_hash']; count += 1
        return {'verified_records': count, 'head_sha256': previous,
                'note': 'Encadeamento local, sem assinatura ou âncora externa. Administradores podem reescrever toda a cadeia.'}
