"""
db.py — SQLite schema and helpers for camwatch event logging.

Schema:
  events(id, zone_id, zone_label, event_type, ts, snapshot_path)
  event_type: 'absent' | 'present'

Absence periods are derived by pairing each 'absent' event with the next
'present' event for the same zone. An unpaired 'absent' means currently missing.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def init_db(db_path: str) -> None:
    with _connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                zone_id       TEXT    NOT NULL,
                zone_label    TEXT    NOT NULL,
                event_type    TEXT    NOT NULL CHECK(event_type IN ('absent', 'present')),
                ts            DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                snapshot_path TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_zone_ts ON events(zone_id, ts)")
        # Migrate existing DBs that predate the snapshot_path column
        try:
            conn.execute("ALTER TABLE events ADD COLUMN snapshot_path TEXT")
        except Exception:
            pass


def log_event(db_path: str, zone_id: str, zone_label: str, event_type: str,
              ts: datetime | None = None, snapshot_path: str | None = None) -> None:
    ts = ts or datetime.now(timezone.utc)
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO events (zone_id, zone_label, event_type, ts, snapshot_path) VALUES (?, ?, ?, ?, ?)",
            (zone_id, zone_label, event_type, ts.isoformat(), snapshot_path),
        )


def get_current_state(db_path: str) -> dict[str, str]:
    """Return the most recent event_type per zone_id."""
    with _connect(db_path) as conn:
        rows = conn.execute("""
            SELECT zone_id, event_type
            FROM events
            WHERE id IN (
                SELECT MAX(id) FROM events GROUP BY zone_id
            )
        """).fetchall()
    return {row[0]: row[1] for row in rows}


def get_absence_history(db_path: str, limit: int = 200) -> list[dict]:
    """
    Return completed absence periods (most recent first), plus any ongoing ones.
    Each row: zone_id, zone_label, absent_since, absent_snapshot,
              returned_at (None if ongoing), present_snapshot, duration_seconds
    """
    with _connect(db_path) as conn:
        rows = conn.execute("""
            SELECT
                a.zone_id,
                a.zone_label,
                a.ts                                                        AS absent_since,
                a.snapshot_path                                             AS absent_snapshot,
                p.ts                                                        AS returned_at,
                p.snapshot_path                                             AS present_snapshot,
                CASE WHEN p.ts IS NOT NULL
                     THEN ROUND((julianday(p.ts) - julianday(a.ts)) * 86400)
                     ELSE NULL
                END                                                         AS duration_seconds
            FROM events a
            LEFT JOIN events p
                ON  p.zone_id    = a.zone_id
                AND p.event_type = 'present'
                AND p.id = (
                    SELECT MIN(id) FROM events
                    WHERE zone_id    = a.zone_id
                      AND event_type = 'present'
                      AND id > a.id
                )
            WHERE a.event_type = 'absent'
            ORDER BY a.ts DESC
            LIMIT ?
        """, (limit,)).fetchall()

    return [
        {
            "zone_id":          r[0],
            "zone_label":       r[1],
            "absent_since":     r[2],
            "absent_snapshot":  r[3],
            "returned_at":      r[4],
            "present_snapshot": r[5],
            "duration_seconds": r[6],
        }
        for r in rows
    ]


@contextmanager
def _connect(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
