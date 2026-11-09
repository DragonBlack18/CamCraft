from __future__ import annotations

import json
from contextlib import closing
import queue
import sqlite3
import threading
import time
from pathlib import Path


class EventStore:
    """One asynchronous, bounded writer. Capture never waits for SQLite or a slow disk."""
    def __init__(self, path: Path, queue_size: int = 2048):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.queue: queue.Queue = queue.Queue(maxsize=queue_size)
        self.stop_event = threading.Event()
        self.dropped = 0
        self.write_failures = 0
        self.last_write_utc = 0.0
        self.lock = threading.Lock()
        with closing(self.connect()) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=NORMAL")
            db.executescript('''
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY, utc REAL NOT NULL, camera_id TEXT,
                level TEXT NOT NULL, code TEXT NOT NULL, message TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS ix_events_camera_id ON events(camera_id, id);
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY, utc REAL NOT NULL, camera_id TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS ix_metrics_camera_id ON metrics(camera_id, id);
            ''')
        self.thread = threading.Thread(target=self._writer, name="event-writer", daemon=True)
        self.thread.start()

    def connect(self):
        db = sqlite3.connect(self.path, timeout=0.5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA synchronous=NORMAL")
        return db

    def emit(self, camera_id: str | None, code: str, message: str, level="INFO", payload=None):
        return self._enqueue(("event", time.time(), camera_id, level, code, message, json.dumps(payload or {}, ensure_ascii=False)))

    def metric(self, camera_id: str, payload: dict):
        self._enqueue(("metric", time.time(), camera_id, json.dumps(payload, ensure_ascii=False)))

    def _enqueue(self, entry):
        if self.stop_event.is_set():
            with self.lock:self.dropped += 1
            return False
        try:
            self.queue.put_nowait(entry)
            return True
        except queue.Full:
            with self.lock:
                self.dropped += 1
            return False

    def _writer(self):
        db = self.connect()
        last_cleanup = 0.0
        try:
            while not self.stop_event.is_set() or not self.queue.empty():
                batch = []
                try:
                    batch.append(self.queue.get(timeout=0.2))
                except queue.Empty:
                    continue
                while len(batch) < 100:
                    try:
                        batch.append(self.queue.get_nowait())
                    except queue.Empty:
                        break
                try:
                    with db:
                        for entry in batch:
                            if entry[0] == "event":
                                db.execute("INSERT INTO events(utc,camera_id,level,code,message,payload) VALUES (?,?,?,?,?,?)", entry[1:])
                            else:
                                db.execute("INSERT INTO metrics(utc,camera_id,payload) VALUES (?,?,?)", entry[1:])
                        if time.monotonic() - last_cleanup > 60:
                            db.execute("DELETE FROM events WHERE id < COALESCE((SELECT MAX(id) FROM events),0)-49999")
                            db.execute("DELETE FROM metrics WHERE id < COALESCE((SELECT MAX(id) FROM metrics),0)-99999")
                            last_cleanup = time.monotonic()
                    self.last_write_utc = time.time()
                except sqlite3.Error:
                    # Native busy timeout is bounded; a failed transaction is counted, not silently retried forever.
                    self.write_failures += 1
                    with self.lock:
                        self.dropped += len(batch)
                finally:
                    for _ in batch:
                        self.queue.task_done()
        finally:
            try:
                db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except sqlite3.Error:
                pass
            db.close()

    def events(self, camera_id: str | None = None, limit: int = 100, before: int | None = None):
        where, params = [], []
        if camera_id:
            where.append("camera_id=?")
            params.append(camera_id)
        if before is not None:
            where.append("id<?")
            params.append(before)
        query = "SELECT * FROM events" + (" WHERE " + " AND ".join(where) if where else "")
        query += " ORDER BY id DESC LIMIT ?"
        params.append(max(1, min(limit, 1000)))
        with closing(self.connect()) as db:
            rows = [dict(r) for r in db.execute(query, params)]
        for row in rows:
            row["payload"] = json.loads(row["payload"])
        return rows

    def metrics(self, camera_id: str, limit: int = 360):
        with closing(self.connect()) as db:
            rows = db.execute("SELECT utc,payload FROM metrics WHERE camera_id=? ORDER BY id DESC LIMIT ?",
                              (camera_id, max(1, min(limit, 2000)))).fetchall()
        return [{"utc": row["utc"], **json.loads(row["payload"])} for row in reversed(rows)]

    def health(self):
        return {"queue_depth": self.queue.qsize(), "queue_capacity": self.queue.maxsize,
                "dropped_records": self.dropped, "write_failures": self.write_failures,
                "last_write_utc": self.last_write_utc,
                "healthy": self.dropped == 0 and self.write_failures == 0 and self.thread.is_alive()}

    def flush(self, timeout=3):
        until = time.monotonic() + timeout
        while self.queue.unfinished_tasks and time.monotonic() < until:
            time.sleep(0.01)
        return self.queue.unfinished_tasks == 0

    def close(self):
        self.stop_event.set()
        self.thread.join(timeout=4)
        if self.thread.is_alive():
            raise RuntimeError('Gravação do banco não encerrou no prazo; dados pendentes não confirmados.')
