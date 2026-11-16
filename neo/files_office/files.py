"""
neo/files_office/files.py — Level 1 Direct Filesystem Controller.

Architectural Guarantees:
1. Restricted to allowed folders via validate_path() from neo.safety.policy.
2. Defends against path traversal (..), UNC shares (\\\\server\\share), Alternate Data Streams (:),
   and disallowed executable extensions (.exe, .bat, .cmd, .ps1, etc.).
3. Overwrite protection: writing, copying, moving, or renaming over an existing file
   requires ConfirmationGate approval.
4. Safe deletion: deletion moves targets to a recycle repository (.neo_recycle/) inside the
   allowed workspace and requires ConfirmationGate approval (never plain unlinking).
5. Empirical evidence: collects SHA-256 hashes, sizes, line counts, and timestamps.
"""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union

from neo.config import get_settings
from neo.safety.emergency_stop import emergency_stop
from neo.safety.gates import ConfirmationDeniedError, HardStopRequiredError, get_confirmation_gate
from neo.safety.policy import validate_path

logger = logging.getLogger("neo.files_office.files")


@dataclass
class FileResult:
    """Typed result of any filesystem operation."""
    ok: bool
    data: Any = None
    error: Optional[str] = None
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "data": self.data,
            "error": self.error,
            "evidence": self.evidence,
        }


@dataclass
class FileInfo:
    """Metadata for an empirical filesystem entry."""
    path: str
    name: str
    size_bytes: int
    is_dir: bool
    modified_time: float
    sha256: Optional[str] = None


def compute_sha256(path: Path) -> str:
    """Computes SHA-256 checksum in 64KB chunks to avoid memory spikes."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def _request_overwrite_confirmation(target_path: Path, action_name: str) -> Optional[FileResult]:
    """
    If target_path already exists, passes through ConfirmationGate for approval.
    Returns None if approved, or FileResult(ok=False) if denied/hard stop.
    """
    if not target_path.exists():
        return None

    gate = get_confirmation_gate()
    try:
        gate.evaluate_and_gate(
            action_name="delete",
            target=str(target_path),
            element_name=f"Overwrite file: {target_path.name}",
        )
        return None
    except HardStopRequiredError as e:
        return FileResult(
            ok=False,
            error=f"File overwrite blocked by Hard Stop: {e}",
            evidence={"target": str(target_path), "hard_stop": True},
        )
    except ConfirmationDeniedError as e:
        return FileResult(
            ok=False,
            error=f"File overwrite denied by confirmation gate: {e}",
            evidence={"target": str(target_path), "denied": True},
        )


def safe_read_file(
    path: Union[str, Path],
    offset_lines: int = 0,
    max_lines: Optional[int] = None,
    encoding: str = "utf-8",
) -> FileResult:
    """Safely reads text content from an allow-listed file."""
    emergency_stop.check_stop()

    pv = validate_path(path)
    if not pv.is_allowed:
        return FileResult(
            ok=False,
            error=f"Access denied by security policy: {pv.rejection_reason}",
            evidence={"requested_path": str(path), "validation": pv.__dict__},
        )

    resolved_path = Path(pv.resolved_path) if pv.resolved_path else Path(path)
    if not resolved_path.exists():
        return FileResult(
            ok=False,
            error=f"File not found: '{resolved_path}'",
            evidence={"path": str(resolved_path)},
        )

    if resolved_path.is_dir():
        return FileResult(
            ok=False,
            error=f"Target is a directory, not a file: '{resolved_path}'",
            evidence={"path": str(resolved_path)},
        )

    try:
        file_size = resolved_path.stat().st_size
        file_hash = compute_sha256(resolved_path)

        with open(resolved_path, "r", encoding=encoding, errors="replace") as f:
            lines = f.readlines()

        total_lines = len(lines)
        start = max(0, offset_lines)
        end = (start + max_lines) if max_lines is not None else total_lines
        selected_lines = lines[start:end]
        content = "".join(selected_lines)

        return FileResult(
            ok=True,
            data=content,
            evidence={
                "path": str(resolved_path),
                "size_bytes": file_size,
                "sha256": file_hash,
                "total_lines": total_lines,
                "lines_returned": len(selected_lines),
                "offset_lines": start,
            },
        )
    except Exception as e:
        logger.error("Failed reading file '%s': %s", resolved_path, e, exc_info=True)
        return FileResult(ok=False, error=f"File read error: {e}", evidence={"path": str(resolved_path)})


def safe_write_file(
    path: Union[str, Path],
    content: str,
    mode: Literal["write", "append"] = "write",
    encoding: str = "utf-8",
) -> FileResult:
    """
    Safely writes or appends content to an allow-listed file.
    Enforces overwrite confirmation if mode=='write' and the file already exists.
    """
    emergency_stop.check_stop()

    pv = validate_path(path)
    if not pv.is_allowed:
        return FileResult(
            ok=False,
            error=f"Access denied by security policy: {pv.rejection_reason}",
            evidence={"requested_path": str(path), "validation": pv.__dict__},
        )

    resolved_path = Path(pv.resolved_path) if pv.resolved_path else Path(path)

    # Overwrite check
    if mode == "write" and resolved_path.exists():
        ow_gate = _request_overwrite_confirmation(resolved_path, "write")
        if ow_gate is not None:
            return ow_gate

    try:
        resolved_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return FileResult(
            ok=False,
            error=f"Failed to create parent directory '{resolved_path.parent}': {e}",
            evidence={"path": str(resolved_path)},
        )

    open_mode = "w" if mode == "write" else "a"
    try:
        with open(resolved_path, open_mode, encoding=encoding) as f:
            f.write(content)

        new_stat = resolved_path.stat()
        new_hash = compute_sha256(resolved_path)

        return FileResult(
            ok=True,
            data={"path": str(resolved_path), "bytes_written": len(content.encode(encoding))},
            evidence={
                "path": str(resolved_path),
                "mode": mode,
                "size_bytes": new_stat.st_size,
                "sha256": new_hash,
                "modified_time": new_stat.st_mtime,
                "verified": True,
            },
        )
    except Exception as e:
        logger.error("Failed writing to file '%s': %s", resolved_path, e, exc_info=True)
        return FileResult(ok=False, error=f"File write error: {e}", evidence={"path": str(resolved_path)})


def safe_copy_file(src: Union[str, Path], dst: Union[str, Path]) -> FileResult:
    """
    Copies a file to an allow-listed destination.
    Enforces confirmation gate before overwriting an existing destination.
    """
    emergency_stop.check_stop()

    pv_src = validate_path(src)
    if not pv_src.is_allowed:
        return FileResult(ok=False, error=f"Source access denied: {pv_src.rejection_reason}")

    pv_dst = validate_path(dst)
    if not pv_dst.is_allowed:
        return FileResult(ok=False, error=f"Destination access denied: {pv_dst.rejection_reason}")

    src_path = Path(pv_src.resolved_path) if pv_src.resolved_path else Path(src)
    dst_path = Path(pv_dst.resolved_path) if pv_dst.resolved_path else Path(dst)

    if not src_path.exists():
        return FileResult(ok=False, error=f"Source file not found: '{src_path}'")

    if dst_path.exists():
        ow_gate = _request_overwrite_confirmation(dst_path, "copy")
        if ow_gate is not None:
            return ow_gate

    try:
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, dst_path)

        src_hash = compute_sha256(src_path)
        dst_hash = compute_sha256(dst_path)
        verified = (src_hash == dst_hash)

        return FileResult(
            ok=verified,
            data={"src": str(src_path), "dst": str(dst_path)},
            evidence={
                "src_path": str(src_path),
                "dst_path": str(dst_path),
                "src_hash": src_hash,
                "dst_hash": dst_hash,
                "verified": verified,
            },
        )
    except Exception as e:
        logger.error("Failed copying '%s' to '%s': %s", src_path, dst_path, e, exc_info=True)
        return FileResult(ok=False, error=f"Copy error: {e}")


def safe_move_file(src: Union[str, Path], dst: Union[str, Path]) -> FileResult:
    """
    Moves a file to an allow-listed destination.
    Enforces confirmation gate before overwriting an existing destination.
    """
    emergency_stop.check_stop()

    pv_src = validate_path(src)
    if not pv_src.is_allowed:
        return FileResult(ok=False, error=f"Source access denied: {pv_src.rejection_reason}")

    pv_dst = validate_path(dst)
    if not pv_dst.is_allowed:
        return FileResult(ok=False, error=f"Destination access denied: {pv_dst.rejection_reason}")

    src_path = Path(pv_src.resolved_path) if pv_src.resolved_path else Path(src)
    dst_path = Path(pv_dst.resolved_path) if pv_dst.resolved_path else Path(dst)

    if not src_path.exists():
        return FileResult(ok=False, error=f"Source file not found: '{src_path}'")

    if dst_path.exists():
        ow_gate = _request_overwrite_confirmation(dst_path, "move")
        if ow_gate is not None:
            return ow_gate

    try:
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src_path), str(dst_path))

        verified = dst_path.exists() and not src_path.exists()
        return FileResult(
            ok=verified,
            data={"src": str(src_path), "dst": str(dst_path)},
            evidence={"src": str(src_path), "dst": str(dst_path), "verified": verified},
        )
    except Exception as e:
        logger.error("Failed moving '%s' to '%s': %s", src_path, dst_path, e, exc_info=True)
        return FileResult(ok=False, error=f"Move error: {e}")


def safe_rename_file(src: Union[str, Path], new_name: str) -> FileResult:
    """
    Renames a file in-place within its parent directory.
    Enforces confirmation gate before overwriting if the target name exists.
    """
    emergency_stop.check_stop()

    name_clean = Path(new_name).name.strip()
    if not name_clean:
        return FileResult(ok=False, error="New name cannot be empty.")

    pv_src = validate_path(src)
    if not pv_src.is_allowed:
        return FileResult(ok=False, error=f"Access denied: {pv_src.rejection_reason}")

    src_path = Path(pv_src.resolved_path) if pv_src.resolved_path else Path(src)
    if not src_path.exists():
        return FileResult(ok=False, error=f"File not found: '{src_path}'")

    dst_path = src_path.parent / name_clean
    return safe_move_file(src_path, dst_path)


def safe_create_folder(path: Union[str, Path]) -> FileResult:
    """
    Creates a new directory inside an allow-listed folder.
    """
    emergency_stop.check_stop()

    pv = validate_path(path)
    if not pv.is_allowed:
        return FileResult(ok=False, error=f"Access denied: {pv.rejection_reason}")

    target_path = Path(pv.resolved_path) if pv.resolved_path else Path(path)
    try:
        target_path.mkdir(parents=True, exist_ok=True)
        verified = target_path.exists() and target_path.is_dir()
        return FileResult(
            ok=verified,
            data={"path": str(target_path)},
            evidence={"path": str(target_path), "is_dir": True, "verified": verified},
        )
    except Exception as e:
        logger.error("Failed creating folder '%s': %s", target_path, e, exc_info=True)
        return FileResult(ok=False, error=f"Create folder error: {e}")


def safe_list_dir(
    path: Union[str, Path],
    pattern: str = "*",
    recursive: bool = False,
    max_entries: int = 500,
) -> FileResult:
    """Lists files and directories inside an allow-listed folder."""
    emergency_stop.check_stop()

    pv = validate_path(path)
    if not pv.is_allowed:
        return FileResult(
            ok=False,
            error=f"Access denied by security policy: {pv.rejection_reason}",
            evidence={"requested_path": str(path), "validation": pv.__dict__},
        )

    resolved_path = Path(pv.resolved_path) if pv.resolved_path else Path(path)
    if not resolved_path.exists():
        return FileResult(ok=False, error=f"Directory does not exist: '{resolved_path}'")

    if not resolved_path.is_dir():
        return FileResult(ok=False, error=f"Path is not a directory: '{resolved_path}'")

    entries: List[FileInfo] = []
    truncated = False

    try:
        iterator = resolved_path.rglob(pattern) if recursive else resolved_path.glob(pattern)
        for item in iterator:
            if len(entries) >= max_entries:
                truncated = True
                break
            try:
                st = item.stat()
                is_directory = item.is_dir()
                entries.append(
                    FileInfo(
                        path=str(item),
                        name=item.name,
                        size_bytes=st.st_size if not is_directory else 0,
                        is_dir=is_directory,
                        modified_time=st.st_mtime,
                        sha256=None,
                    )
                )
            except Exception:
                continue

        return FileResult(
            ok=True,
            data=[e.__dict__ for e in entries],
            evidence={
                "base_path": str(resolved_path),
                "pattern": pattern,
                "recursive": recursive,
                "count": len(entries),
                "truncated": truncated,
            },
        )
    except Exception as e:
        logger.error("Failed listing directory '%s': %s", resolved_path, e, exc_info=True)
        return FileResult(ok=False, error=f"Directory listing error: {e}")


def safe_search_files(
    base_path: Union[str, Path],
    query: str,
    recursive: bool = True,
    max_results: int = 100,
) -> FileResult:
    """Searches for files matching query substring inside an allow-listed folder."""
    emergency_stop.check_stop()

    query_clean = query.strip().lower()
    if not query_clean:
        return FileResult(ok=False, error="Search query cannot be empty.")

    pattern = f"*{query_clean}*"
    return safe_list_dir(
        path=base_path,
        pattern=pattern,
        recursive=recursive,
        max_entries=max_results,
    )


def safe_file_info(path: Union[str, Path], compute_hash: bool = True) -> FileResult:
    """Returns empirical metadata and SHA-256 for an allow-listed file or folder."""
    emergency_stop.check_stop()

    pv = validate_path(path)
    if not pv.is_allowed:
        return FileResult(ok=False, error=f"Access denied by security policy: {pv.rejection_reason}")

    resolved_path = Path(pv.resolved_path) if pv.resolved_path else Path(path)
    if not resolved_path.exists():
        return FileResult(ok=False, error=f"Path not found: '{resolved_path}'")

    try:
        st = resolved_path.stat()
        is_directory = resolved_path.is_dir()
        file_hash = compute_sha256(resolved_path) if (compute_hash and not is_directory) else None

        info = FileInfo(
            path=str(resolved_path),
            name=resolved_path.name,
            size_bytes=st.st_size if not is_directory else 0,
            is_dir=is_directory,
            modified_time=st.st_mtime,
            sha256=file_hash,
        )

        return FileResult(
            ok=True,
            data=info.__dict__,
            evidence={"path": str(resolved_path), "verified": True},
        )
    except Exception as e:
        logger.error("Failed gathering info for '%s': %s", resolved_path, e, exc_info=True)
        return FileResult(ok=False, error=f"File info error: {e}")


def safe_delete_file(path: Union[str, Path]) -> FileResult:
    """
    Safely deletes a file or directory:
    1. Gated via ConfirmationGate (risky action 'delete', defaults to DENY).
    2. Moves target to a local .neo_recycle/ directory inside the allowed folder
       (timestamped backup) instead of permanently unlinking it.
    """
    emergency_stop.check_stop()

    pv = validate_path(path)
    if not pv.is_allowed:
        return FileResult(ok=False, error=f"Access denied by security policy: {pv.rejection_reason}")

    resolved_path = Path(pv.resolved_path) if pv.resolved_path else Path(path)
    if not resolved_path.exists():
        return FileResult(ok=False, error=f"Target to delete not found: '{resolved_path}'")

    # Gate through ConfirmationGate
    gate = get_confirmation_gate()
    try:
        gate.evaluate_and_gate(
            action_name="delete",
            target=str(resolved_path),
            element_name=f"Delete {resolved_path.name}",
        )
    except HardStopRequiredError as e:
        return FileResult(ok=False, error=f"Deletion blocked by Hard Stop: {e}", evidence={"hard_stop": True})
    except ConfirmationDeniedError as e:
        return FileResult(ok=False, error=f"Deletion denied by confirmation gate: {e}", evidence={"denied": True})

    try:
        # Move to .neo_recycle inside parent directory
        recycle_dir = resolved_path.parent / ".neo_recycle"
        recycle_dir.mkdir(parents=True, exist_ok=True)

        timestamp_suffix = int(time.time() * 1000)
        recycle_target = recycle_dir / f"{resolved_path.stem}_{timestamp_suffix}{resolved_path.suffix}"

        shutil.move(str(resolved_path), str(recycle_target))

        is_gone = not resolved_path.exists()
        return FileResult(
            ok=is_gone,
            data={"path": str(resolved_path), "recycled_to": str(recycle_target)},
            evidence={
                "path": str(resolved_path),
                "recycled_to": str(recycle_target),
                "verified": is_gone,
            },
        )
    except Exception as e:
        logger.error("Failed recycling '%s': %s", resolved_path, e, exc_info=True)
        return FileResult(ok=False, error=f"Recycle delete error: {e}")
