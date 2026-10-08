"""Published weeks, stored in a local SQLite database."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DB = DATA / "sold_list.db"
SEED = DATA / "sold_list_seed.db"
HISTORY_VERSION = "2026-10-08-weekly"


def _stamp(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES ('history_version', ?)",
        (HISTORY_VERSION,),
    )


def _seed_is_current() -> bool:
    if not DB.exists():
        return False
    try:
        conn = sqlite3.connect(DB)
        row = conn.execute("SELECT value FROM meta WHERE key = 'history_version'").fetchone()
        conn.close()
    except sqlite3.Error:
        return False
    return bool(row and row[0] == HISTORY_VERSION)


def connect() -> sqlite3.Connection:
    DATA.mkdir(parents=True, exist_ok=True)
    if SEED.exists() and not _seed_is_current():
        DB.write_bytes(SEED.read_bytes())
        conn = sqlite3.connect(DB)
        _stamp(conn)
        conn.commit()
        conn.close()
    conn = sqlite3.connect(DB)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS weeks (
            id INTEGER PRIMARY KEY,
            saved_at TEXT,
            inventory_file TEXT,
            sales_file TEXT,
            vehicle_count INTEGER,
            rows_json TEXT,
            is_current INTEGER
        )
        """
    )
    _stamp(conn)
    conn.commit()
    _import_old_json(conn)
    return conn


def _import_old_json(conn: sqlite3.Connection) -> None:
    if conn.execute("SELECT COUNT(*) FROM weeks").fetchone()[0]:
        return
    current = DATA / "current.json"
    archive = DATA / "archive"
    if current.exists():
        payload = json.loads(current.read_text())
        conn.execute(
            "INSERT INTO weeks (saved_at, inventory_file, sales_file, vehicle_count, rows_json, is_current) VALUES (?, ?, ?, ?, ?, 1)",
            (
                payload.get("saved_at"),
                payload.get("inventory_file"),
                payload.get("sales_file"),
                payload.get("vehicle_count") or len(payload.get("rows") or []),
                json.dumps(payload.get("rows") or []),
            ),
        )
    if archive.exists():
        for path in sorted(archive.glob("*.json")):
            payload = json.loads(path.read_text())
            conn.execute(
                "INSERT INTO weeks (saved_at, inventory_file, sales_file, vehicle_count, rows_json, is_current) VALUES (?, ?, ?, ?, ?, 0)",
                (
                    payload.get("saved_at"),
                    payload.get("inventory_file"),
                    payload.get("sales_file"),
                    payload.get("vehicle_count") or len(payload.get("rows") or []),
                    json.dumps(payload.get("rows") or []),
                ),
            )
    conn.commit()


def _payload(row) -> dict:
    return {
        "id": str(row[0]),
        "saved_at": row[1],
        "inventory_file": row[2],
        "sales_file": row[3],
        "vehicle_count": row[4],
        "rows": json.loads(row[5] or "[]"),
    }


def current_list() -> dict | None:
    conn = connect()
    row = conn.execute(
        "SELECT id, saved_at, inventory_file, sales_file, vehicle_count, rows_json FROM weeks WHERE is_current = 1 ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return _payload(row) if row else None


def archived_lists() -> list[dict]:
    conn = connect()
    rows = conn.execute(
        "SELECT id, saved_at, inventory_file, sales_file, vehicle_count, rows_json FROM weeks WHERE is_current = 0 ORDER BY id DESC"
    ).fetchall()
    conn.close()
    return [_payload(row) for row in rows]


def publish(rows: list[dict], inventory_file: str, sales_file: str) -> dict:
    saved_at = datetime.now().isoformat(timespec="seconds")
    conn = connect()
    conn.execute("UPDATE weeks SET is_current = 0 WHERE is_current = 1")
    conn.execute(
        "INSERT INTO weeks (saved_at, inventory_file, sales_file, vehicle_count, rows_json, is_current) VALUES (?, ?, ?, ?, ?, 1)",
        (saved_at, inventory_file, sales_file, len(rows), json.dumps(rows)),
    )
    conn.commit()
    conn.close()
    return {
        "saved_at": saved_at,
        "inventory_file": inventory_file,
        "sales_file": sales_file,
        "vehicle_count": len(rows),
        "rows": rows,
    }
