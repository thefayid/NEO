"""
core/neo_brain.py — Lifelong Tri-Tier Memory & Semantic Knowledge Graph Engine for NEO.

Senior Intelligence Architecture (Pillar 2):
1. Tier 1: Working Memory (In-Memory Buffer)
   - Active desktop window & screen focus
   - Recent clipboard snippet buffer
   - Active task / goal context
   - Rolling dialog turn buffer
2. Tier 2: Episodic Memory (Time-Indexed Vector/BM25 Timeline in SQLite)
   - Continuous logging of turns, tool executions, and user events
   - BM25 keyword scoring + exponential time-decay recency weighting
   - Queryable via natural language: "What did I work on yesterday?"
3. Tier 3: Semantic Knowledge Graph (Entity-Relationship Graph in SQLite)
   - Tables: entities (People, Projects, Technologies, Preferences, Rules)
             relations (USES, PREFERS, WORKING_ON, CONFIGURED_WITH, OWNS)
   - Automatic entity extraction and association reinforcement
   - Bidirectional graph traversal and context synthesis
"""
from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import sys
import time
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Dict, List, Optional, Set, Tuple, Union

_BASE_DIR = Path(__file__).resolve().parent.parent
_DB_PATH = _BASE_DIR / "memory" / "neo_brain.db"


def _tokenize(text: str) -> List[str]:
    return [w.lower() for w in re.findall(r"[a-zA-Z0-9_\-\.]{2,}", text)]


# ── 1. Tier 1: Working Memory Buffer ──────────────────────────────────────────

class WorkingMemory:
    """
    Ephemeral active context buffer for the immediate second-by-second session.
    """
    def __init__(self, max_turns: int = 12):
        self.max_turns = max_turns
        self.active_window: str = ""
        self.clipboard_snippet: str = ""
        self.current_goal: str = ""
        self.recent_turns: List[Dict[str, str]] = []
        self._lock = Lock()

    def update_environment(self, active_window: str = "", clipboard: str = ""):
        with self._lock:
            if active_window:
                self.active_window = active_window
            if clipboard:
                self.clipboard_snippet = clipboard[:240]

    def set_active_goal(self, goal: str):
        with self._lock:
            self.current_goal = goal

    def add_turn(self, role: str, content: str):
        with self._lock:
            self.recent_turns.append({
                "role": role,
                "content": content,
                "timestamp": time.time()
            })
            if len(self.recent_turns) > self.max_turns:
                self.recent_turns.pop(0)

    def get_summary(self) -> Dict[str, object]:
        with self._lock:
            return {
                "active_window": self.active_window,
                "clipboard_snippet": self.clipboard_snippet,
                "current_goal": self.current_goal,
                "turn_count": len(self.recent_turns),
            }


# ── 2. Tier 2 & Tier 3: SQLite Persistent Brain (Episodic & Knowledge Graph) ──

class NeoBrainStore:
    """
    Unified SQLite persistent store for Episodic Events and Semantic Knowledge Graph.
    """
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or _DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._init_db()

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _get_connection(self):
        return self.connection()

    def _init_db(self):
        with self._lock, self._get_connection() as conn:
            # 1. Episodic timeline
            conn.execute("""
                CREATE TABLE IF NOT EXISTS episodic_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL,
                    session_id TEXT,
                    event_type TEXT,
                    content TEXT,
                    tokens TEXT,
                    metadata TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_episodic_ts ON episodic_events(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_episodic_type ON episodic_events(event_type)")

            # 2. Knowledge Graph: Entities
            conn.execute("""
                CREATE TABLE IF NOT EXISTS entities (
                    id TEXT PRIMARY KEY,
                    name TEXT UNIQUE,
                    entity_type TEXT,
                    attributes TEXT,
                    mention_count INTEGER DEFAULT 1,
                    created_at REAL,
                    updated_at REAL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type)")

            # 3. Knowledge Graph: Relations
            conn.execute("""
                CREATE TABLE IF NOT EXISTS relations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id TEXT,
                    target_id TEXT,
                    relation_type TEXT,
                    weight REAL DEFAULT 1.0,
                    context TEXT,
                    created_at REAL,
                    UNIQUE(source_id, target_id, relation_type)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_rel_source ON relations(source_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_rel_target ON relations(target_id)")


# ── 3. Episodic Memory Timeline Engine ─────────────────────────────────────────

class EpisodicMemory:
    """
    Time-indexed event timeline supporting hybrid BM25 / Recency scoring.
    """
    def __init__(self, store: NeoBrainStore):
        self.store = store

    def log_event(
        self,
        event_type: str,
        content: str,
        session_id: str = "default",
        metadata: Optional[Dict] = None,
    ) -> int:
        if not content.strip():
            return -1

        now = time.time()
        tokens_json = json.dumps(_tokenize(content))
        meta_json = json.dumps(metadata or {})

        with self.store._lock, self.store._get_connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO episodic_events (timestamp, session_id, event_type, content, tokens, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (now, session_id, event_type, content.strip(), tokens_json, meta_json)
            )
            return cur.lastrowid

    def query_events(
        self,
        query: str,
        limit: int = 5,
        event_type: Optional[str] = None,
        max_age_hours: Optional[float] = None,
    ) -> List[Dict]:
        query_tokens = set(_tokenize(query))
        if not query_tokens:
            # Fallback to recent events
            with self.store._lock, self.store._get_connection() as conn:
                cur = conn.execute(
                    "SELECT * FROM episodic_events ORDER BY timestamp DESC LIMIT ?",
                    (limit,)
                )
                return [dict(r) for r in cur.fetchall()]

        # Compute query over events
        now = time.time()
        min_ts = (now - max_age_hours * 3600.0) if max_age_hours else 0.0

        with self.store._lock, self.store._get_connection() as conn:
            if event_type:
                cur = conn.execute(
                    "SELECT * FROM episodic_events WHERE timestamp >= ? AND event_type = ? ORDER BY timestamp DESC LIMIT 200",
                    (min_ts, event_type)
                )
            else:
                cur = conn.execute(
                    "SELECT * FROM episodic_events WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT 200",
                    (min_ts,)
                )
            rows = [dict(r) for r in cur.fetchall()]

        scored: List[Tuple[float, Dict]] = []
        for r in rows:
            tokens = set(json.loads(r.get("tokens") or "[]"))
            overlap = len(query_tokens.intersection(tokens))
            if overlap == 0:
                continue

            # BM25-style term match
            score = float(overlap) / (math.log(len(tokens) + 1.5) + 1.0)

            # Recency boost (exponential decay over 48 hours)
            age_hours = (now - r["timestamp"]) / 3600.0
            recency_weight = math.exp(-0.015 * min(age_hours, 168.0))
            final_score = score * (1.0 + 0.4 * recency_weight)

            scored.append((final_score, r))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored[:limit]]


# ── 4. Semantic Knowledge Graph Engine ─────────────────────────────────────────

class SemanticKnowledgeGraph:
    """
    Entity-Relationship Knowledge Graph for permanent domain & personal facts.
    """
    def __init__(self, store: NeoBrainStore):
        self.store = store

    @staticmethod
    def slugify(name: str) -> str:
        clean = re.sub(r"[^\w\s-]", "", str(name or "").lower()).strip()
        return re.sub(r"[-\s]+", "_", clean)[:48] or "entity"

    def upsert_entity(
        self,
        name: str,
        entity_type: str = "GENERAL",
        attributes: Optional[Dict] = None,
    ) -> str:
        entity_id = self.slugify(name)
        now = time.time()

        with self.store._lock, self.store._get_connection() as conn:
            cur = conn.execute("SELECT * FROM entities WHERE id = ?", (entity_id,))
            row = cur.fetchone()
            if row:
                existing_attrs = json.loads(row["attributes"] or "{}")
                if attributes:
                    existing_attrs.update(attributes)
                conn.execute(
                    """
                    UPDATE entities
                    SET mention_count = mention_count + 1,
                        updated_at = ?,
                        attributes = ?
                    WHERE id = ?
                    """,
                    (now, json.dumps(existing_attrs), entity_id)
                )
            else:
                conn.execute(
                    """
                    INSERT INTO entities (id, name, entity_type, attributes, mention_count, created_at, updated_at)
                    VALUES (?, ?, ?, ?, 1, ?, ?)
                    """,
                    (entity_id, name.strip(), entity_type.upper(), json.dumps(attributes or {}), now, now)
                )
        return entity_id

    def add_relation(
        self,
        source_name: str,
        target_name: str,
        relation_type: str = "ASSOCIATED_WITH",
        weight: float = 1.0,
        context: str = "",
    ):
        src_id = self.upsert_entity(source_name)
        tgt_id = self.upsert_entity(target_name)
        now = time.time()

        with self.store._lock, self.store._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO relations (source_id, target_id, relation_type, weight, context, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id, target_id, relation_type)
                DO UPDATE SET weight = weight + 0.5, context = ?, created_at = ?
                """,
                (src_id, tgt_id, relation_type.upper(), weight, context, now, context, now)
            )

    def extract_from_text(self, text: str) -> List[Tuple[str, str, str]]:
        """
        Extracts entity relationships from prose using pattern heuristics.
        Returns list of (source, relation, target).
        """
        extracted = []
        lower = text.strip()

        # Preference patterns: "I prefer X over Y", "I love/like X", "I use X"
        pref_match = re.search(r"\b(?:i\s+prefer|i\s+like|i\s+love)\s+([a-zA-Z0-9_\-\s]{2,24})", lower, re.I)
        if pref_match:
            item = pref_match.group(1).strip()
            self.upsert_entity("user", "PERSON")
            self.upsert_entity(item, "PREFERENCE")
            self.add_relation("user", item, "PREFERS", context=text[:100])
            extracted.append(("user", "PREFERS", item))

        # Project patterns: "working on X", "building X", "project X"
        proj_match = re.search(r"\b(?:working\s+on|building|developing|project)\s+([a-zA-Z0-9_\-\s]{2,24})", lower, re.I)
        if proj_match:
            proj = proj_match.group(1).strip()
            self.upsert_entity("user", "PERSON")
            self.upsert_entity(proj, "PROJECT")
            self.add_relation("user", proj, "WORKING_ON", context=text[:100])
            extracted.append(("user", "WORKING_ON", proj))

        # Technology patterns: "uses X", "built with X", "in X"
        tech_words = ("python", "pyqt6", "react", "typescript", "gemini", "ollama", "sqlite", "docker", "rust", "c++")
        for tech in tech_words:
            if re.search(rf"\b{re.escape(tech)}\b", lower, re.I):
                self.upsert_entity(tech, "TECHNOLOGY")
                self.add_relation("user", tech, "USES", context=text[:100])
                extracted.append(("user", "USES", tech))

        return extracted

    def get_related_entities(self, name: str, depth: int = 1) -> List[Dict]:
        entity_id = self.slugify(name)
        with self.store._lock, self.store._get_connection() as conn:
            cur = conn.execute(
                """
                SELECT r.relation_type, r.weight, r.context, e.name as target_name, e.entity_type
                FROM relations r
                JOIN entities e ON r.target_id = e.id
                WHERE r.source_id = ?
                ORDER BY r.weight DESC LIMIT 20
                """,
                (entity_id,)
            )
            return [dict(row) for row in cur.fetchall()]

    def search_entities(self, query: str, limit: int = 5) -> List[Dict]:
        q_clean = f"%{query.strip().lower()}%"
        with self.store._lock, self.store._get_connection() as conn:
            cur = conn.execute(
                "SELECT * FROM entities WHERE lower(name) LIKE ? OR lower(id) LIKE ? ORDER BY mention_count DESC LIMIT ?",
                (q_clean, q_clean, limit)
            )
            return [dict(row) for row in cur.fetchall()]


# ── 5. Tri-Tier Unified Brain Facade ──────────────────────────────────────────

class NeoBrain:
    """
    Central Brain orchestrator coordinating Working Memory,
    Episodic Timeline, and Semantic Knowledge Graph.
    """
    def __init__(self, db_path: Optional[Path] = None):
        self.store = NeoBrainStore(db_path)
        self.working = WorkingMemory()
        self.episodic = EpisodicMemory(self.store)
        self.graph = SemanticKnowledgeGraph(self.store)

    def learn_interaction(self, user_prompt: str, assistant_reply: str, session_id: str = "main"):
        """Ingests turn into Working, Episodic, and Semantic memory."""
        # 1. Working memory
        self.working.add_turn("user", user_prompt)
        self.working.add_turn("assistant", assistant_reply)

        # 2. Episodic memory
        self.episodic.log_event("USER_PROMPT", user_prompt, session_id=session_id)
        self.episodic.log_event("ASSISTANT_REPLY", assistant_reply, session_id=session_id)

        # 3. Knowledge Graph extraction
        self.graph.extract_from_text(user_prompt)

    def synthesize_intelligence_prompt(self, current_prompt: str) -> str:
        """
        Synthesizes relevant context across all 3 tiers to inject into system reasoning.
        """
        lines = ["[NEO INTELLIGENCE CONTEXT]"]

        # Working context
        summary = self.working.get_summary()
        if summary.get("active_window"):
            lines.append(f"• Active Desktop Focus: {summary['active_window']}")
        if summary.get("current_goal"):
            lines.append(f"• Current Active Goal: {summary['current_goal']}")

        # Relevant episodic memories
        events = self.episodic.query_events(current_prompt, limit=3)
        if events:
            lines.append("• Recent Episodic Context:")
            for ev in events:
                content_snip = ev["content"][:100] + ("..." if len(ev["content"]) > 100 else "")
                lines.append(f"  - [{ev['event_type']}]: {content_snip}")

        # Relevant Knowledge Graph entities
        entities = self.graph.search_entities(current_prompt, limit=3)
        if entities:
            lines.append("• Known Entity Relationships:")
            for ent in entities:
                related = self.graph.get_related_entities(ent["name"])
                rel_str = ", ".join([f"{r['relation_type']} {r['target_name']}" for r in related[:3]])
                lines.append(f"  - {ent['name']} ({ent['entity_type']}): {rel_str or 'Indexed'}")

        return "\n".join(lines)


# Singleton Brain Instance
brain = NeoBrain()
