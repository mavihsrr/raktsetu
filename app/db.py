"""SQLite persistence. Small and synchronous on purpose (calls are short); guarded by a lock.

Everything the coordinator needs to resume after a pod restart lives here: requests, calls,
and the event log (which doubles as the narration feed for the voice agent + dashboard).
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from datetime import date
from pathlib import Path
from typing import Any

from . import seed

SCHEMA = """
CREATE TABLE IF NOT EXISTS hospitals (
  id TEXT PRIMARY KEY, name TEXT, aliases TEXT, lat REAL, lng REAL
);
CREATE TABLE IF NOT EXISTS banks (
  id TEXT PRIMARY KEY, name TEXT, area TEXT, lat REAL, lng REAL, phone TEXT,
  portal TEXT, portal_updated_days_ago INTEGER, sim TEXT
);
CREATE TABLE IF NOT EXISTS donors (
  id TEXT PRIMARY KEY, name TEXT, gender TEXT, dob TEXT, blood_group TEXT,
  lat REAL, lng REAL, phone TEXT, last_donation TEXT, recall_consent INTEGER, sim TEXT
);
CREATE TABLE IF NOT EXISTS requests (
  id TEXT PRIMARY KEY, created_at REAL, updated_at REAL,
  hospital_id TEXT, blood_group TEXT, component TEXT, units INTEGER,
  deadline_at REAL, status TEXT, wave INTEGER, bank_radius_km REAL, wave2_radius_km REAL,
  donor_radius_km REAL, requested_by TEXT, plan TEXT, agent_cursor INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS calls (
  id TEXT PRIMARY KEY, request_id TEXT, target_type TEXT, target_id TEXT, target_name TEXT, wave INTEGER,
  status TEXT, mode TEXT, distance_km REAL, portal_units INTEGER,
  confirmed_units INTEGER, alt_units INTEGER, alt_group TEXT, hold_hours INTEGER,
  willing TEXT, notes TEXT, attempt_id TEXT, transcript TEXT,
  queued_at REAL, started_at REAL, ended_at REAL
);
CREATE INDEX IF NOT EXISTS calls_req ON calls(request_id);
CREATE TABLE IF NOT EXISTS events (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT, ts REAL, type TEXT,
  payload TEXT, say TEXT
);
CREATE INDEX IF NOT EXISTS events_req ON events(request_id, seq);
"""

JSON_COLS = {"portal", "sim", "plan", "transcript", "payload"}


class DB:
    def __init__(self, path: str):
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            if path != ":memory:":
                self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.executescript(SCHEMA)
            for table, col in (("banks", "portal_updated_at TEXT"), ("banks", "email TEXT"),
                               ("banks", "district TEXT"), ("calls", "phone TEXT"),
                               ("calls", "dial_to TEXT"), ("calls", "route TEXT")):
                have = {r[1] for r in self.conn.execute(f"PRAGMA table_info({table})")}
                if col.split()[0] not in have:
                    self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {col}")

    # ---- generic helpers -------------------------------------------------
    @staticmethod
    def _row(r: sqlite3.Row | None) -> dict | None:
        if r is None:
            return None
        d = dict(r)
        for k in JSON_COLS & d.keys():
            if d[k] is not None:
                d[k] = json.loads(d[k])
        return d

    def q(self, sql: str, args: tuple = ()) -> list[dict]:
        with self.lock:
            return [self._row(r) for r in self.conn.execute(sql, args).fetchall()]

    def one(self, sql: str, args: tuple = ()) -> dict | None:
        with self.lock:
            return self._row(self.conn.execute(sql, args).fetchone())

    def insert(self, table: str, row: dict[str, Any]) -> None:
        row = {k: (json.dumps(v) if k in JSON_COLS and v is not None else v) for k, v in row.items()}
        cols = ",".join(row)
        qs = ",".join("?" for _ in row)
        with self.lock:
            self.conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({qs})", tuple(row.values()))

    def update(self, table: str, id_: str, **fields: Any) -> None:
        if not fields:
            return
        fields = {k: (json.dumps(v) if k in JSON_COLS and v is not None else v) for k, v in fields.items()}
        sets = ",".join(f"{k}=?" for k in fields)
        with self.lock:
            self.conn.execute(f"UPDATE {table} SET {sets} WHERE id=?", (*fields.values(), id_))

    # ---- seed ------------------------------------------------------------
    def seed_if_empty(self, today: date | None = None) -> None:
        today = today or date.today()
        with self.lock:
            # Banks are never seeded: they come live from e-RaktKosh on each request.
            if self.one("SELECT COUNT(*) AS n FROM donors")["n"]:
                return
            for d in seed.donors(today):
                self.insert("donors", {**d, "dob": d["dob"].isoformat(),
                                       "last_donation": d["last_donation"].isoformat() if d["last_donation"] else None,
                                       "recall_consent": int(d["recall_consent"])})

    # ---- events ----------------------------------------------------------
    def add_event(self, request_id: str, type_: str, payload: dict, say: str = "") -> int:
        with self.lock:
            cur = self.conn.execute(
                "INSERT INTO events (request_id, ts, type, payload, say) VALUES (?,?,?,?,?)",
                (request_id, time.time(), type_, json.dumps(payload), say))
            return cur.lastrowid

    def events_after(self, request_id: str | None, seq: int) -> list[dict]:
        if request_id:
            return self.q("SELECT * FROM events WHERE request_id=? AND seq>? ORDER BY seq", (request_id, seq))
        return self.q("SELECT * FROM events WHERE seq>? ORDER BY seq", (seq,))
