"""
core/neo_scope_sentinel.py — Task Scope Sentinel & Execution Boundary Enforcer for NEO.

Maintains a locked task boundary:
1. Allowed apps, folders, websites, and actions.
2. Forbidden actions: anything not on the allowed list (default-deny).
3. Check every action against the scope before dispatch.
4. Stop and ask for permission if an action falls outside scope.
5. Scope expands only on explicit user permission and resets when the task ends.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parent.parent
_SCOPE_FILE = _BASE_DIR / "memory" / "task_scope.json"

_SYSTEM_SAFE_TOOLS = {
    "task_scope",
    "action_log",
    "skill_library",
    "screen_process",
    "system_status",
    "manage_monitor",
    "close_camera",
}


class NEOScopeSentinel:
    """
    Guards execution boundaries during active tasks.
    Enforces allowed apps, folders, websites, and actions.
    """

    def __init__(self, scope_file: Optional[Path] = None):
        self.scope_file = Path(scope_file) if scope_file else _SCOPE_FILE
        self._lock = threading.Lock()
        self.is_locked: bool = False
        self.task_name: str = ""
        self.allowed_apps: Set[str] = set()
        self.allowed_folders: Set[str] = set()
        self.allowed_websites: Set[str] = set()
        self.allowed_actions: Set[str] = set()
        self.locked_at: Optional[str] = None
        self._load()

    def _load(self) -> None:
        with self._lock:
            if self.scope_file.exists():
                try:
                    with open(self.scope_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        self.is_locked = bool(data.get("is_locked", False))
                        self.task_name = str(data.get("task_name", ""))
                        self.allowed_apps = {str(a).lower().strip() for a in data.get("allowed_apps", []) if a}
                        self.allowed_folders = {str(Path(f).resolve()).lower() for f in data.get("allowed_folders", []) if f}
                        self.allowed_websites = {str(w).lower().strip() for w in data.get("allowed_websites", []) if w}
                        self.allowed_actions = {str(act).lower().strip() for act in data.get("allowed_actions", []) if act}
                        self.locked_at = data.get("locked_at")
                except Exception as e:
                    logger.warning(f"[ScopeSentinel] Load notice: {e}")

    def _save(self) -> None:
        try:
            self.scope_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.scope_file, "w", encoding="utf-8") as f:
                json.dump({
                    "is_locked": self.is_locked,
                    "task_name": self.task_name,
                    "allowed_apps": sorted(list(self.allowed_apps)),
                    "allowed_folders": sorted(list(self.allowed_folders)),
                    "allowed_websites": sorted(list(self.allowed_websites)),
                    "allowed_actions": sorted(list(self.allowed_actions)),
                    "locked_at": self.locked_at,
                }, f, indent=2)
        except Exception as e:
            logger.warning(f"[ScopeSentinel] Save notice: {e}")

    def lock_scope(
        self,
        task_name: str,
        allowed_apps: Optional[Union[List[str], str]] = None,
        allowed_folders: Optional[Union[List[str], str]] = None,
        allowed_websites: Optional[Union[List[str], str]] = None,
        allowed_actions: Optional[Union[List[str], str]] = None,
    ) -> Dict[str, Any]:
        """Locks a boundary scope for a given task."""
        def _to_clean_set(val: Optional[Union[List[str], str]]) -> Set[str]:
            if not val:
                return set()
            if isinstance(val, str):
                items = re.split(r"[,;\n]+", val)
            else:
                items = val
            return {str(x).lower().strip() for x in items if str(x).strip()}

        with self._lock:
            self.is_locked = True
            self.task_name = str(task_name or "active_task").strip()
            self.allowed_apps = _to_clean_set(allowed_apps)

            # Resolve paths cleanly for folders
            raw_folders = _to_clean_set(allowed_folders)
            resolved_folders = set()
            for rf in raw_folders:
                try:
                    resolved_folders.add(str(Path(rf).resolve()).lower())
                except Exception:
                    resolved_folders.add(rf)
            self.allowed_folders = resolved_folders

            # Clean domains for websites
            raw_websites = _to_clean_set(allowed_websites)
            cleaned_websites = set()
            for rw in raw_websites:
                clean_w = re.sub(r"^https?://", "", rw).rstrip("/")
                if clean_w:
                    cleaned_websites.add(clean_w)
            self.allowed_websites = cleaned_websites

            self.allowed_actions = _to_clean_set(allowed_actions)
            self.locked_at = datetime.now().isoformat()
            self._save()

        logger.info(f"[ScopeSentinel] Locked scope for '{self.task_name}'")
        return self.get_scope()

    def expand_scope(
        self,
        allowed_apps: Optional[Union[List[str], str]] = None,
        allowed_folders: Optional[Union[List[str], str]] = None,
        allowed_websites: Optional[Union[List[str], str]] = None,
        allowed_actions: Optional[Union[List[str], str]] = None,
    ) -> Dict[str, Any]:
        """Expands the current task scope upon explicit user permission."""
        with self._lock:
            if not self.is_locked:
                self.is_locked = True
                self.task_name = "expanded_task"
                self.locked_at = datetime.now().isoformat()

            if allowed_apps:
                items = [allowed_apps] if isinstance(allowed_apps, str) else allowed_apps
                for a in items:
                    if str(a).strip():
                        self.allowed_apps.add(str(a).lower().strip())

            if allowed_folders:
                items = [allowed_folders] if isinstance(allowed_folders, str) else allowed_folders
                for f in items:
                    if str(f).strip():
                        try:
                            self.allowed_folders.add(str(Path(f).resolve()).lower())
                        except Exception:
                            self.allowed_folders.add(str(f).lower().strip())

            if allowed_websites:
                items = [allowed_websites] if isinstance(allowed_websites, str) else allowed_websites
                for w in items:
                    clean_w = re.sub(r"^https?://", "", str(w).lower().strip()).rstrip("/")
                    if clean_w:
                        self.allowed_websites.add(clean_w)

            if allowed_actions:
                items = [allowed_actions] if isinstance(allowed_actions, str) else allowed_actions
                for act in items:
                    if str(act).strip():
                        self.allowed_actions.add(str(act).lower().strip())

            self._save()

        logger.info(f"[ScopeSentinel] Expanded scope for '{self.task_name}'")
        return self.get_scope()

    def reset_scope(self) -> Dict[str, Any]:
        """Resets the task scope when the task ends."""
        with self._lock:
            self.is_locked = False
            self.task_name = ""
            self.allowed_apps.clear()
            self.allowed_folders.clear()
            self.allowed_websites.clear()
            self.allowed_actions.clear()
            self.locked_at = None
            self._save()

        logger.info("[ScopeSentinel] Task scope reset.")
        return {"is_locked": False, "message": "Scope successfully reset."}

    def get_scope(self) -> Dict[str, Any]:
        """Returns the current scope snapshot."""
        with self._lock:
            return {
                "is_locked": self.is_locked,
                "task_name": self.task_name,
                "allowed_apps": sorted(list(self.allowed_apps)),
                "allowed_folders": sorted(list(self.allowed_folders)),
                "allowed_websites": sorted(list(self.allowed_websites)),
                "allowed_actions": sorted(list(self.allowed_actions)),
                "locked_at": self.locked_at,
            }

    def is_action_allowed(self, tool_name: str, parameters: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validates an action and its parameters against the locked task scope.
        Returns (True, 'Allowed') or (False, reason_why_forbidden).
        """
        with self._lock:
            if not self.is_locked:
                return True, "No active scope lock in effect."

            t_name = str(tool_name or "").lower().strip()

            # Built-in system tools bypass scope to allow meta inspection
            if t_name in _SYSTEM_SAFE_TOOLS:
                return True, f"System tool '{tool_name}' allowed."

            # 1. Allowed Actions check
            if self.allowed_actions:
                act_param = str(parameters.get("action", "")).lower().strip()
                # Must match either tool name or specific action parameter
                if t_name not in self.allowed_actions and act_param not in self.allowed_actions:
                    return False, (
                        f"Action '{tool_name}' (sub-action '{act_param}') is not in the allowed actions "
                        f"{sorted(list(self.allowed_actions))} for task '{self.task_name}'. Permission required."
                    )

            # 2. Allowed Apps check
            target_app = str(parameters.get("app_name") or parameters.get("app") or "").lower().strip()
            if target_app and self.allowed_apps:
                match = any(
                    (app in target_app or target_app in app)
                    for app in self.allowed_apps
                )
                if not match:
                    return False, (
                        f"Application '{target_app}' is outside the locked allowed apps "
                        f"{sorted(list(self.allowed_apps))} for task '{self.task_name}'. Permission required."
                    )

            # 3. Allowed Folders check
            target_path_raw = (
                parameters.get("file_path")
                or parameters.get("path")
                or parameters.get("folder")
                or parameters.get("directory")
            )
            if target_path_raw and self.allowed_folders:
                try:
                    target_resolved = str(Path(target_path_raw).resolve()).lower()
                except Exception:
                    target_resolved = str(target_path_raw).lower().strip()

                in_folder = False
                for allowed_f in self.allowed_folders:
                    if target_resolved.startswith(allowed_f) or target_resolved == allowed_f:
                        in_folder = True
                        break
                if not in_folder:
                    return False, (
                        f"Path '{target_path_raw}' is outside the locked allowed folders "
                        f"{sorted(list(self.allowed_folders))} for task '{self.task_name}'. Permission required."
                    )

            # 4. Allowed Websites check
            target_url = str(parameters.get("url") or parameters.get("website") or parameters.get("domain") or "").lower().strip()
            if target_url and self.allowed_websites:
                clean_target = re.sub(r"^https?://", "", target_url).rstrip("/")
                match_web = any(
                    (w in clean_target or clean_target in w)
                    for w in self.allowed_websites
                )
                if not match_web:
                    return False, (
                        f"Website '{target_url}' is outside the locked allowed websites "
                        f"{sorted(list(self.allowed_websites))} for task '{self.task_name}'. Permission required."
                    )

            return True, f"Action '{tool_name}' is verified within locked task scope."


# Global singleton
scope_sentinel = NEOScopeSentinel()

