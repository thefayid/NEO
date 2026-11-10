"""
core/tasks_db.py — Shared Zero-Data-Loss Task Engine persistence.
Provides atomic writes, deduplication, and helper functions for memory/tasks.json.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

_TASKS_FILE = Path(__file__).resolve().parent.parent / "memory" / "tasks.json"


def get_tasks_file_path() -> Path:
    return _TASKS_FILE


def load_tasks() -> List[Dict]:
    """Loads tasks directly from disk without touching or resetting user state."""
    _TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if _TASKS_FILE.exists():
        try:
            with open(_TASKS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "tasks" in data:
                    tasks = data.get("tasks")
                    if isinstance(tasks, list):
                        return tasks
        except Exception:
            pass
    return []


def write_tasks(tasks: List[Dict]) -> bool:
    """Atomic write with physical fsync to prevent loss across abrupt exits."""
    try:
        _TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp_file = _TASKS_FILE.with_suffix(".tmp")
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump({"tasks": tasks}, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_file, _TASKS_FILE)
        return True
    except Exception:
        try:
            with open(_TASKS_FILE, "w", encoding="utf-8") as f:
                json.dump({"tasks": tasks}, f, indent=2, ensure_ascii=False)
            return True
        except Exception:
            return False


def add_task(
    title: str,
    category: str = "Engineering",
    priority: str = "High",
    due_date: str = "Today",
    notes: str = "",
    done: bool = False
) -> Dict:
    """Inserts a new task atomically at the top of the task engine registry."""
    tasks = load_tasks()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    new_task = {
        "id": f"task_{int(time.time() * 1000)}",
        "title": title.strip(),
        "category": category,
        "priority": priority,
        "due_date": due_date,
        "done": done,
        "created_at": now_str,
        "notes": notes.strip(),
    }
    # If task with identical title already exists, return existing
    existing = next((t for t in tasks if t.get("title", "").strip().lower() == title.strip().lower()), None)
    if existing:
        return existing

    tasks.insert(0, new_task)
    write_tasks(tasks)
    return new_task
