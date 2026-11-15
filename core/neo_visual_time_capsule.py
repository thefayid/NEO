"""
core/neo_visual_time_capsule.py — Visual Screen Time Capsule & Memory Indexer for NEO.

Provides privacy-first local episodic visual memory:
1. Passive Screen Timeline Recording:
   - Indexes active window title, process name, display index, and OCR text snippets.
   - Automatically stores in SQLite (`memory/neo_brain.db`) with timestamps.
2. Temporal Natural Language Queries:
   - "What was on my screen 30 minutes ago?"
   - "Find that error code I saw earlier."
   - "What website was I looking at this morning?"
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("NEO.VisualTimeCapsule")

_BASE_DIR = Path(__file__).resolve().parent.parent
_DB_PATH = _BASE_DIR / "memory" / "neo_brain.db"


@dataclass
class TimeCapsuleEntry:
    id: int
    timestamp: float
    formatted_time: str
    app_name: str
    window_title: str
    ocr_snippet: str
    display_index: int


class NEOVisualTimeCapsule:
    """Manages recording and temporal retrieval of visual desktop history."""

    _instance: Optional["NEOVisualTimeCapsule"] = None

    def __new__(cls, db_path: Optional[Path] = None) -> "NEOVisualTimeCapsule":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.db_path = db_path or _DB_PATH
            cls._instance._lock = threading.Lock()
            cls._instance._init_db()
        elif db_path is not None:
            cls._instance.db_path = db_path
            cls._instance._init_db()
        return cls._instance

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS visual_time_capsule (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp REAL,
                        app_name TEXT,
                        window_title TEXT,
                        ocr_snippet TEXT,
                        display_index INTEGER DEFAULT 1,
                        metadata TEXT
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_vtc_ts ON visual_time_capsule(timestamp)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_vtc_app ON visual_time_capsule(app_name)")
                conn.commit()
            finally:
                conn.close()

    def record_frame(
        self,
        app_name: str,
        window_title: str,
        ocr_snippet: str = "",
        display_index: int = 1,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Records an active window/screen state into the capsule."""
        ts = time.time()
        meta_json = json.dumps(metadata or {})
        with self._lock:
            conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            try:
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO visual_time_capsule (timestamp, app_name, window_title, ocr_snippet, display_index, metadata)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (ts, app_name.strip(), window_title.strip(), ocr_snippet.strip(), display_index, meta_json),
                )
                conn.commit()
                return cur.lastrowid or -1
            except Exception as e:
                logger.error(f"Failed recording time capsule frame: {e}")
                return -1
            finally:
                conn.close()

    def search_history(
        self,
        query: str,
        limit: int = 8,
        since_seconds: Optional[float] = None,
    ) -> List[TimeCapsuleEntry]:
        """Searches visual memory for keywords in window titles, apps, or OCR text."""
        q_tokens = [w.lower().strip() for w in query.split() if w.strip()]
        if not q_tokens:
            return self.get_timeline(limit=limit)

        min_ts = (time.time() - since_seconds) if since_seconds else 0.0

        with self._lock:
            conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            try:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT id, timestamp, app_name, window_title, ocr_snippet, display_index
                    FROM visual_time_capsule
                    WHERE timestamp >= ?
                    ORDER BY timestamp DESC
                    LIMIT 200
                    """,
                    (min_ts,),
                )
                rows = cur.fetchall()
            finally:
                conn.close()

        scored: List[Tuple[float, sqlite3.Row]] = []
        for r in rows:
            text = f"{r['app_name']} {r['window_title']} {r['ocr_snippet']}".lower()
            matches = sum(1 for tok in q_tokens if tok in text)
            if matches > 0:
                # Recency boost
                recency_hours = (time.time() - r["timestamp"]) / 3600.0
                score = matches / (1.0 + 0.1 * recency_hours)
                scored.append((score, r))

        scored.sort(key=lambda x: x[0], reverse=True)
        results: List[TimeCapsuleEntry] = []
        for _, r in scored[:limit]:
            results.append(TimeCapsuleEntry(
                id=r["id"],
                timestamp=r["timestamp"],
                formatted_time=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r["timestamp"])),
                app_name=r["app_name"],
                window_title=r["window_title"],
                ocr_snippet=r["ocr_snippet"][:300],
                display_index=r["display_index"],
            ))
        return results

    def get_timeline(self, limit: int = 15) -> List[TimeCapsuleEntry]:
        """Returns the most recent desktop state timeline."""
        with self._lock:
            conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            try:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT id, timestamp, app_name, window_title, ocr_snippet, display_index
                    FROM visual_time_capsule
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
                rows = cur.fetchall()
            finally:
                conn.close()

        entries: List[TimeCapsuleEntry] = []
        for r in rows:
            entries.append(TimeCapsuleEntry(
                id=r["id"],
                timestamp=r["timestamp"],
                formatted_time=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r["timestamp"])),
                app_name=r["app_name"],
                window_title=r["window_title"],
                ocr_snippet=r["ocr_snippet"][:300],
                display_index=r["display_index"],
            ))
        return entries


visual_time_capsule = NEOVisualTimeCapsule()
