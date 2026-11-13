"""
core/neo_action_logger.py — Structured Action Audit Logger & Verification Accountability for NEO.

Maintains an immutable, append-only audit trail for every action executed:
Format:
[time] | step | tool called | parameters | result | evidence (screenshot ID or output) | verified: yes/no

Rules:
1. On request ("show log"): print the last N entries.
2. If asked "what did you do?": answer ONLY from the log, never from memory or inference.
3. If an entry is missing, explicitly say so.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parent.parent
_ACTION_LOG_JSON = _BASE_DIR / "memory" / "action_log.json"
_ACTION_LOG_TXT = _BASE_DIR / "memory" / "action_log.txt"


@dataclass
class ActionLogEntry:
    time_str: str
    step: int
    tool_called: str
    parameters: str
    result: str
    evidence: str
    verified: str

    def to_line(self) -> str:
        return (
            f"[{self.time_str}] | {self.step} | {self.tool_called} | "
            f"{self.parameters} | {self.result} | {self.evidence} | "
            f"verified: {self.verified}"
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "time": self.time_str,
            "step": self.step,
            "tool_called": self.tool_called,
            "parameters": self.parameters,
            "result": self.result,
            "evidence": self.evidence,
            "verified": self.verified,
            "formatted_line": self.to_line(),
        }


class NEOActionLogger:
    """
    Structured action audit logger that logs every action in the required format
    and guarantees strict accountability for user queries like 'show log' and 'what did you do?'.
    """

    def __init__(
        self,
        json_path: Optional[Path] = None,
        txt_path: Optional[Path] = None,
    ):
        self.json_path = Path(json_path) if json_path else _ACTION_LOG_JSON
        self.txt_path = Path(txt_path) if txt_path else _ACTION_LOG_TXT
        self._lock = threading.Lock()
        self._step_counter = 0
        self._entries: List[ActionLogEntry] = []
        self._load()

    def _load(self) -> None:
        with self._lock:
            if self.json_path.exists():
                try:
                    with open(self.json_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        raw_entries = data if isinstance(data, list) else data.get("entries", [])
                        for item in raw_entries:
                            entry = ActionLogEntry(
                                time_str=item.get("time", ""),
                                step=int(item.get("step", 0)),
                                tool_called=item.get("tool_called", ""),
                                parameters=item.get("parameters", ""),
                                result=item.get("result", ""),
                                evidence=item.get("evidence", ""),
                                verified=item.get("verified", "no"),
                            )
                            self._entries.append(entry)
                        if self._entries:
                            self._step_counter = max(e.step for e in self._entries)
                except Exception as e:
                    logger.warning(f"[ActionLogger] Load notice: {e}")

    def _persist(self, entry: ActionLogEntry) -> None:
        try:
            self.json_path.parent.mkdir(parents=True, exist_ok=True)
            # Write JSON atomically
            with open(self.json_path, "w", encoding="utf-8") as f:
                json.dump([e.to_dict() for e in self._entries[-500:]], f, indent=2)
            # Append formatted line to TXT log
            with open(self.txt_path, "a", encoding="utf-8") as f:
                f.write(entry.to_line() + "\n")
        except Exception as e:
            logger.warning(f"[ActionLogger] Persist notice: {e}")

    def record_action(
        self,
        tool_called: str,
        parameters: Union[Dict[str, Any], str],
        result: str,
        step: Optional[Union[int, str]] = None,
        evidence: Optional[str] = None,
        verified: Optional[Union[bool, str]] = None,
    ) -> ActionLogEntry:
        """Records an action in the exact required audit log format."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Format parameters string cleanly
        if isinstance(parameters, dict):
            # Clean sensitive or bulky keys if needed
            cleaned = {}
            for k, v in parameters.items():
                if k in ("password", "token", "key", "secret") and v:
                    cleaned[k] = "******"
                else:
                    cleaned[k] = v
            params_str = json.dumps(cleaned, ensure_ascii=False)
        else:
            params_str = str(parameters or "{}").strip()

        # Sanitize single-line representation
        params_str = re.sub(r"\s+", " ", params_str)
        if len(params_str) > 120:
            params_str = params_str[:117] + "..."

        res_str = re.sub(r"\s+", " ", str(result or "").strip())
        if len(res_str) > 120:
            res_str = res_str[:117] + "..."

        # Determine evidence
        if not evidence:
            # Check for screenshot ID in result or params
            m_shot = re.search(r"\b(screenshot_\w+|\w+\.png|\w+\.jpg)\b", f"{params_str} {res_str}")
            if m_shot:
                evidence_str = f"Screenshot ID: {m_shot.group(1)}"
            else:
                out_snippet = res_str[:60] if res_str else "None"
                evidence_str = f"Output: '{out_snippet}'"
        else:
            evidence_str = str(evidence).strip()

        # Determine verification status
        if verified is not None:
            if isinstance(verified, bool):
                ver_str = "yes" if verified else "no"
            else:
                ver_str = "yes" if str(verified).lower() in ("yes", "true", "1") else "no"
        else:
            low_res = res_str.lower()
            if any(fail in low_res for fail in ("fail", "error", "unverified", "timeout", "timed out")):
                ver_str = "no"
            elif any(succ in low_res for succ in ("verified=true", "status=done", "done", "success")):
                ver_str = "yes"
            elif res_str and not res_str.startswith("ERR:"):
                ver_str = "yes"
            else:
                ver_str = "no"

        with self._lock:
            if step is not None:
                try:
                    s_num = int(step)
                except ValueError:
                    self._step_counter += 1
                    s_num = self._step_counter
            else:
                self._step_counter += 1
                s_num = self._step_counter

            entry = ActionLogEntry(
                time_str=now_str,
                step=s_num,
                tool_called=str(tool_called).strip(),
                parameters=params_str,
                result=res_str,
                evidence=evidence_str,
                verified=ver_str,
            )
            self._entries.append(entry)
            if len(self._entries) > 1000:
                self._entries = self._entries[-1000:]
            self._persist(entry)

        return entry

    def get_last_entries(self, n: int = 10) -> List[ActionLogEntry]:
        """Returns the last N log entries."""
        with self._lock:
            return list(self._entries[-n:])

    def format_last_entries(self, n: int = 10) -> str:
        """Returns the last N log entries formatted as line strings."""
        entries = self.get_last_entries(n)
        if not entries:
            return "Action log is currently empty."
        return "\n".join(e.to_line() for e in entries)

    def answer_what_did_you_do(self, limit: int = 10) -> str:
        """
        Answers strictly from the log, never from memory or inference.
        If an entry is missing or the log is empty, explicitly says so.
        """
        with self._lock:
            if not self._entries:
                return (
                    "Based strictly on the verified action log: No actions have been logged in this session. "
                    "The log does not contain any recorded entries."
                )
            entries = self._entries[-limit:]

        lines = [
            f"Here are the verified actions recorded in the log (last {len(entries)}):"
        ]
        for e in entries:
            lines.append(
                f"• Step {e.step} [{e.time_str}]: Tool '{e.tool_called}' with params {e.parameters} → "
                f"Result: {e.result} (Evidence: {e.evidence}, Verified: {e.verified})"
            )
        lines.append("\nNote: Reported strictly from the immutable audit log.")
        return "\n".join(lines)


# Global singleton instance
action_logger = NEOActionLogger()

