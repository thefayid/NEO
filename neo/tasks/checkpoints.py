"""
neo/tasks/checkpoints.py — Pre-Execution Checkpoint Creation and Deterministic Rollback.

Architectural Guarantees:
1. Automatic Risky Action Checkpointing:
   - Before executing risky actions (file writes, deletes, moves, renames, clipboard modifications),
     snapshots are taken of affected targets and system states.
2. Complete Bidirectional File Restoration:
   - If a file existed prior to the step, its exact byte content is preserved and restored on rollback.
   - If a file did NOT exist prior to the step (i.e. was newly created by the risky action),
     it is deleted during rollback to return the filesystem to its pristine initial state.
3. Clipboard and Active Window State Preservation:
   - Preserves clipboard text and attempts restoration on rollback.
4. Typed Results:
   - Every operation returns structured `CheckpointRecord` and `RollbackResult` models.
"""
from __future__ import annotations

import logging
import os
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from neo.tools.system_info import clipboard_get, clipboard_set

logger = logging.getLogger("neo.tasks.checkpoints")

# Risky actions requiring automatic checkpoint creation
RISKY_ACTIONS = {
    "file_write",
    "file_delete",
    "file_move",
    "file_rename",
    "file_copy",
    "clipboard_set",
}


@dataclass
class CheckpointRecord:
    """Structured snapshot of target files and system states before a risky action."""
    checkpoint_id: str
    action_name: str
    created_at: float
    description: str
    # file_path -> bytes if file existed, or None if file did NOT exist before the checkpoint
    file_snapshots: Dict[str, Optional[bytes]] = field(default_factory=dict)
    clipboard_text: Optional[str] = None
    active_window_hwnd: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "action_name": self.action_name,
            "created_at": self.created_at,
            "description": self.description,
            "files_tracked": list(self.file_snapshots.keys()),
            "clipboard_tracked": self.clipboard_text is not None,
            "active_window_hwnd": self.active_window_hwnd,
            "metadata": self.metadata,
        }


@dataclass
class RollbackResult:
    """Outcome of attempting to roll back state to a checkpoint."""
    ok: bool
    checkpoint_id: str
    restored_files: List[str] = field(default_factory=list)
    removed_files: List[str] = field(default_factory=list)
    clipboard_restored: bool = False
    errors: List[str] = field(default_factory=list)
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "checkpoint_id": self.checkpoint_id,
            "restored_files": self.restored_files,
            "removed_files": self.removed_files,
            "clipboard_restored": self.clipboard_restored,
            "errors": self.errors,
            "message": self.message,
        }


class CheckpointManager:
    """
    Manages the lifecycle of system state checkpoints, enabling safe execution
    of destructive or modifying actions with deterministic rollback capabilities.
    """

    def __init__(self, storage_dir: Optional[Union[str, Path]] = None) -> None:
        self.storage_dir = Path(storage_dir or ".neo_checkpoints").resolve()
        self._checkpoints: Dict[str, CheckpointRecord] = {}
        self._checkpoint_stack: List[str] = []

    def create_checkpoint(
        self,
        action_name: str,
        file_paths: Sequence[Union[str, Path]] = (),
        capture_clipboard: bool = True,
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CheckpointRecord:
        """
        Creates a structured checkpoint capturing the current content of specified files,
        the clipboard text, and the active foreground window.
        """
        checkpoint_id = f"chk_{uuid.uuid4().hex[:10]}"
        file_snaps: Dict[str, Optional[bytes]] = {}

        for p in file_paths:
            path_obj = Path(p).resolve()
            path_str = str(path_obj)
            if path_obj.exists() and path_obj.is_file():
                try:
                    file_snaps[path_str] = path_obj.read_bytes()
                except Exception as e:
                    logger.warning("Could not snapshot file '%s': %e", path_str, e)
                    file_snaps[path_str] = None
            else:
                # File did not exist; if the action creates it, rollback will delete it
                file_snaps[path_str] = None

        # Capture clipboard
        clip_text: Optional[str] = None
        if capture_clipboard:
            try:
                res = clipboard_get()
                if res.ok and res.data is not None:
                    clip_text = str(res.data)
            except Exception as e:
                logger.debug("Clipboard capture failed: %e", e)

        # Capture active window
        active_hwnd: Optional[int] = None
        try:
            from neo.windows.core import foreground
            fg_res = foreground()
            if fg_res.ok and fg_res.data:
                active_hwnd = fg_res.data.hwnd
        except Exception:
            pass

        rec = CheckpointRecord(
            checkpoint_id=checkpoint_id,
            action_name=action_name,
            created_at=time.time(),
            description=description or f"Checkpoint prior to '{action_name}'",
            file_snapshots=file_snaps,
            clipboard_text=clip_text,
            active_window_hwnd=active_hwnd,
            metadata=dict(metadata or {}),
        )

        self._checkpoints[checkpoint_id] = rec
        self._checkpoint_stack.append(checkpoint_id)
        logger.info(
            "Created Checkpoint '%s' before action '%s' (%d files tracked).",
            checkpoint_id, action_name, len(file_snaps)
        )
        return rec

    def auto_checkpoint(
        self,
        action: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Optional[CheckpointRecord]:
        """
        Automatically analyzes the action and parameters. If risky, creates a checkpoint.
        """
        act_clean = action.strip().lower()
        if act_clean not in RISKY_ACTIONS:
            return None

        params = dict(parameters or {})
        files_to_track: List[str] = []

        # Extract file paths from common parameter names
        for key in ("path", "destination", "source", "target_path", "file_path"):
            val = params.get(key)
            if val and isinstance(val, (str, Path)):
                files_to_track.append(str(val))

        capture_clip = (act_clean == "clipboard_set")
        return self.create_checkpoint(
            action_name=act_clean,
            file_paths=files_to_track,
            capture_clipboard=capture_clip,
            description=f"Auto-checkpoint before risky action '{act_clean}'",
            metadata={"parameters": params},
        )

    def rollback(self, checkpoint_id: Optional[str] = None) -> RollbackResult:
        """
        Reverts system changes to the specified checkpoint (or the most recent if omitted).
        """
        if checkpoint_id is None:
            if not self._checkpoint_stack:
                return RollbackResult(
                    ok=False,
                    checkpoint_id="none",
                    errors=["No checkpoints available to rollback."],
                    message="Rollback failed: stack is empty.",
                )
            checkpoint_id = self._checkpoint_stack[-1]

        rec = self._checkpoints.get(checkpoint_id)
        if not rec:
            return RollbackResult(
                ok=False,
                checkpoint_id=checkpoint_id,
                errors=[f"Checkpoint '{checkpoint_id}' not found."],
                message="Rollback failed: unknown checkpoint ID.",
            )

        restored_files: List[str] = []
        removed_files: List[str] = []
        errors: List[str] = []

        # 1. Restore files
        for path_str, orig_bytes in rec.file_snapshots.items():
            p = Path(path_str)
            try:
                if orig_bytes is not None:
                    # File existed before -> restore original content
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_bytes(orig_bytes)
                    restored_files.append(path_str)
                else:
                    # File did not exist before -> delete if it was created
                    if p.exists():
                        if p.is_file():
                            p.unlink()
                        elif p.is_dir():
                            shutil.rmtree(p, ignore_errors=True)
                        removed_files.append(path_str)
            except Exception as e:
                err = f"Failed to restore file '{path_str}': {e}"
                logger.error(err)
                errors.append(err)

        # 2. Restore clipboard
        clipboard_restored = False
        if rec.clipboard_text is not None:
            try:
                set_res = clipboard_set(rec.clipboard_text)
                clipboard_restored = set_res.ok
                if not set_res.ok:
                    errors.append(f"Clipboard restore failed: {set_res.error}")
            except Exception as e:
                errors.append(f"Exception during clipboard restore: {e}")

        # 3. Restore active window focus
        if rec.active_window_hwnd:
            try:
                from neo.windows.core import focus_window
                # Attempt to refocus window by HWND or pass silently
                import win32gui
                if win32gui.IsWindow(rec.active_window_hwnd):
                    win32gui.SetForegroundWindow(rec.active_window_hwnd)
            except Exception:
                pass

        # Pop from stack if this was the latest
        if self._checkpoint_stack and self._checkpoint_stack[-1] == checkpoint_id:
            self._checkpoint_stack.pop()

        all_ok = len(errors) == 0
        msg = (
            f"Rollback to '{checkpoint_id}' "
            f"{'SUCCEEDED' if all_ok else 'FAILED with errors'}. "
            f"Restored {len(restored_files)} files, removed {len(removed_files)} created files, "
            f"clipboard restored={clipboard_restored}."
        )
        logger.info(msg)
        return RollbackResult(
            ok=all_ok,
            checkpoint_id=checkpoint_id,
            restored_files=restored_files,
            removed_files=removed_files,
            clipboard_restored=clipboard_restored,
            errors=errors,
            message=msg,
        )

    def discard(self, checkpoint_id: str) -> bool:
        """Discards a checkpoint when an action is successfully verified."""
        if checkpoint_id in self._checkpoints:
            del self._checkpoints[checkpoint_id]
            if checkpoint_id in self._checkpoint_stack:
                self._checkpoint_stack.remove(checkpoint_id)
            return True
        return False

    def clear(self) -> None:
        """Clears all stored checkpoints."""
        self._checkpoints.clear()
        self._checkpoint_stack.clear()
