"""
actions/knowledge_memory.py — Stark Persistent Knowledge Graph & Memory Engine for F.R.I.D.A.Y.

Enables permanent, cross-session voice memory and entity-relationship indexing:
- Voice Fact Storage: "Remember that Krishnakiran is working on the Edunet team portal."
- Natural Memory Recall: "Who is working on the Edunet team portal?", "What is my server IP?"
- Memory Inventory: "What do you remember about my projects?", "List everything you remember about me."
- Entity & Relationship Inference: Auto-classifies into projects, relationships, preferences, identity, or notes.
- Stark SFX feedback on storage & recall.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from core import outcome

def _base_dir() -> Path:
    import sys
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

_MEMORY_FILE = _base_dir() / "memory" / "long_term.json"

def _play_sfx(sfx_name: str) -> None:
    try:
        from core.sfx import play_sfx
        play_sfx(sfx_name)
    except Exception:
        pass

def _load_memory() -> dict:
    try:
        if _MEMORY_FILE.exists():
            return json.loads(_MEMORY_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[KnowledgeMemory] Load error: {e}")
    return {
        "identity": {},
        "preferences": {},
        "projects": {},
        "relationships": {},
        "wishes": {},
        "notes": {},
    }

def _save_memory(data: dict) -> None:
    try:
        _MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        _MEMORY_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"[KnowledgeMemory] Save error: {e}")

def _infer_category(key: str, fact: str) -> str:
    combined = (f"{key} {fact}").lower()
    if any(w in combined for w in ("project", "repo", "code", "portal", "app", "website", "server", "deploy", "build", "bug", "feature", "edunet")):
        return "projects"
    if any(w in combined for w in ("colleague", "friend", "team", "lead", "boss", "sister", "brother", "wife", "husband", "mom", "dad", "partner", "krishna")):
        return "relationships"
    if any(w in combined for w in ("like", "favorite", "favourite", "prefer", "color", "colour", "music", "food", "sport", "hobby")):
        return "preferences"
    if any(w in combined for w in ("plan", "future", "buy", "travel", "goal", "wish", "dream")):
        return "wishes"
    if any(w in combined for w in ("name", "birthday", "age", "city", "live in", "nationality", "job")):
        return "identity"
    return "notes"

def _slugify(text: str) -> str:
    clean = re.sub(r"[^\w\s-]", "", str(text or "").lower()).strip()
    return re.sub(r"[-\s]+", "_", clean)[:40] or "fact"

def store_fact(fact: str, key: str = "", category: str = "") -> str:
    """Store a fact into long-term memory."""
    if not fact:
        return "No fact was provided to remember, Boss."

    mem = _load_memory()
    today = datetime.now().strftime("%Y-%m-%d")

    # If key wasn't explicitly given, extract from fact
    if not key:
        words = [w for w in fact.split() if len(w) > 3 and w.lower() not in ("that", "this", "with", "from", "working", "about")]
        key = "_".join(words[:3]) if words else "note"
    key = _slugify(key)

    if not category or category not in ("identity", "preferences", "projects", "relationships", "wishes", "notes"):
        category = _infer_category(key, fact)

    if category not in mem or not isinstance(mem[category], dict):
        mem[category] = {}

    mem[category][key] = {
        "value": fact.strip(),
        "updated": today
    }
    _save_memory(mem)
    _play_sfx("confirm")
    print(f"[KnowledgeMemory] Stored: [{category}] {key} -> {fact}")
    return f"Understood, Boss. Stored in memory under {category}: '{fact}'."

def recall_facts(query: str = "") -> str:
    """Search and recall facts from long-term memory."""
    mem = _load_memory()
    q = (query or "").strip().lower()

    matches = []
    for cat, items in mem.items():
        if not isinstance(items, dict):
            continue
        for key, entry in items.items():
            if not isinstance(entry, dict):
                continue
            val = str(entry.get("value", "")).strip()
            if not val:
                continue
            updated = entry.get("updated", "")
            # If query is empty, return all; otherwise search key, category, value
            if not q or (q in key.lower() or q in val.lower() or q in cat.lower()):
                matches.append((cat, key, val, updated))

    if not matches:
        if q:
            return f"I found no stored memories matching '{query}', Boss."
        return "I have no memories stored in long-term memory yet, Boss."

    _play_sfx("confirm")
    lines = [f"Found {len(matches)} relevant memory record(s):"]
    for cat, key, val, updated in matches[:8]:
        date_str = f" (saved {updated})" if updated else ""
        lines.append(f"- [{cat.capitalize()}] {val}{date_str}")
    return "\n".join(lines)

def forget_fact(query: str) -> str:
    """Delete a memory entry by key or query."""
    if not query:
        return "Please specify what fact or key to forget, Boss."

    mem = _load_memory()
    q = query.strip().lower()
    deleted = []

    for cat, items in mem.items():
        if not isinstance(items, dict):
            continue
        to_remove = []
        for key, entry in items.items():
            val = str(entry.get("value", "") if isinstance(entry, dict) else entry).lower()
            if q in key.lower() or q in val:
                to_remove.append(key)
        for k in to_remove:
            del items[k]
            deleted.append(f"{cat}/{k}")

    if deleted:
        _save_memory(mem)
        _play_sfx("confirm")
        return f"Forgotten from memory: {', '.join(deleted)}, Boss."
    return f"No memories found matching '{query}' to forget, Boss."

def list_all_memories() -> str:
    """List full structured inventory of memories."""
    mem = _load_memory()
    sections = []
    total = 0

    for cat in ("identity", "projects", "relationships", "preferences", "wishes", "notes"):
        items = mem.get(cat, {})
        if isinstance(items, dict) and items:
            cat_lines = [f"\n[{cat.upper()}]:"]
            for k, entry in items.items():
                val = entry.get("value", "") if isinstance(entry, dict) else entry
                cat_lines.append(f"  - {k.replace('_', ' ').title()}: {val}")
                total += 1
            sections.append("\n".join(cat_lines))

    if not total:
        return "Your long-term memory is currently empty, Boss."

    _play_sfx("confirm")
    return f"Stored Long-Term Knowledge ({total} total entries):" + "".join(sections)

def knowledge_memory(parameters: dict, player=None, **kwargs) -> str:
    params = parameters or {}
    action = params.get("action", "recall").lower().strip()
    fact = params.get("fact", "") or params.get("value", "") or params.get("message", "")
    query = params.get("query", "") or params.get("key", "") or fact
    category = params.get("category", "")
    key = params.get("key", "")

    if action in ("store", "remember", "save", "add"):
        return store_fact(fact=fact or query, key=key, category=category)

    if action in ("recall", "query", "search", "get", "find"):
        return recall_facts(query=query)

    if action in ("list", "all", "inventory", "show"):
        return list_all_memories()

    if action in ("forget", "delete", "remove"):
        return forget_fact(query=query)

    return f"Unknown memory action: '{action}'. Available: remember, recall, list, forget."

TOOL = {
    "name": "knowledge_memory",
    "description": (
        "Persistent Knowledge Graph & Long-Term Memory for F.R.I.D.A.Y. "
        "Allows storing, searching, and managing facts, project notes, team members, "
        "credentials, and personal context permanently across restarts. "
        "Supports actions: 'remember' (store fact), 'recall' (search memory), 'list' (inventory all memories), 'forget'."
    ),
    "tier": "core",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "'remember' (store new fact), 'recall' (search memories), 'list' (list all memories), 'forget'"
            },
            "fact": {
                "type": "STRING",
                "description": "The information or fact to remember (e.g. 'Krishnakiran is working on the Edunet team portal')"
            },
            "query": {
                "type": "STRING",
                "description": "Keyword or topic to search or recall from memory (e.g. 'Edunet', 'server IP', 'Krishnakiran')"
            },
            "category": {
                "type": "STRING",
                "description": "Optional category: 'projects', 'relationships', 'preferences', 'wishes', 'identity', 'notes'"
            },
            "key": {
                "type": "STRING",
                "description": "Optional short identifier key (e.g. 'edunet_portal_lead')"
            }
        },
        "required": ["action"]
    },
    "handler": knowledge_memory,
}
