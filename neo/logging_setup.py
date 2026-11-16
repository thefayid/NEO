"""
neo/logging_setup.py — Structured JSON-Lines Step Logging for NEO.

Records detailed telemetry for every execution step:
- timestamp: ISO 8601 UTC timestamp
- task_id: Identifier of the overarching user goal or workflow
- stage: Current execution stage ('plan', 'execute', 'verify', 'reflect')
- llm_decision: The chosen tool, reasoning, or decision payload from the LLM
- action: The executed action name from the fixed whitelist
- parameters: Key-value dictionary of action parameters
- result: The outcome returned by execution
- evidence: Empirical proof gathered (window HWND, DOM property, UI state diff)
- duration: Wall-clock execution time in seconds
"""
from __future__ import annotations

import contextlib
import json
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Union


@dataclass
class StepRecord:
    """Represents a single deterministic execution step in the JSON-lines audit trail."""
    timestamp: str
    task_id: str
    stage: str
    llm_decision: Optional[Any]
    action: str
    parameters: Dict[str, Any]
    result: Optional[Any]
    evidence: Optional[Any]
    duration: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str, ensure_ascii=False)


@dataclass
class StepContext:
    """Mutable context passed into the step_context context manager."""
    task_id: str
    stage: str
    action: str
    parameters: Dict[str, Any]
    llm_decision: Optional[Any] = None
    result: Optional[Any] = None
    evidence: Optional[Any] = None


class StepLogger:
    """Thread-safe JSON-lines step execution logger."""

    def __init__(self, log_path: Union[str, Path] = "logs/neo_steps.jsonl"):
        self.log_path = Path(log_path).resolve()
        self._lock = threading.Lock()
        self._ensure_log_dir()

    def _ensure_log_dir(self) -> None:
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    def log_step(
        self,
        task_id: str,
        stage: str,
        action: str,
        parameters: Optional[Dict[str, Any]] = None,
        result: Optional[Any] = None,
        evidence: Optional[Any] = None,
        duration: float = 0.0,
        llm_decision: Optional[Any] = None,
        timestamp: Optional[str] = None,
    ) -> StepRecord:
        """Constructs and appends a StepRecord to the JSON-lines log file."""
        if timestamp is None:
            timestamp = datetime.now(timezone.utc).isoformat()

        record = StepRecord(
            timestamp=timestamp,
            task_id=task_id,
            stage=stage,
            llm_decision=llm_decision,
            action=action,
            parameters=parameters or {},
            result=result,
            evidence=evidence,
            duration=round(max(0.0, float(duration)), 4),
        )

        line = record.to_json() + "\n"
        with self._lock:
            self._ensure_log_dir()
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(line)

        return record

    @contextlib.contextmanager
    def step_context(
        self,
        task_id: str,
        stage: str,
        action: str,
        parameters: Optional[Dict[str, Any]] = None,
        llm_decision: Optional[Any] = None,
    ) -> Generator[StepContext, None, None]:
        """
        Context manager that automatically tracks execution duration
        and writes the completed StepRecord upon exit.
        """
        ctx = StepContext(
            task_id=task_id,
            stage=stage,
            action=action,
            parameters=parameters or {},
            llm_decision=llm_decision,
        )
        start_time = time.perf_counter()
        start_ts = datetime.now(timezone.utc).isoformat()
        try:
            yield ctx
        finally:
            elapsed = time.perf_counter() - start_time
            self.log_step(
                task_id=ctx.task_id,
                stage=ctx.stage,
                action=ctx.action,
                parameters=ctx.parameters,
                result=ctx.result,
                evidence=ctx.evidence,
                duration=elapsed,
                llm_decision=ctx.llm_decision,
                timestamp=start_ts,
            )

    def read_records(self, task_id: Optional[str] = None) -> List[StepRecord]:
        """Reads back records from the JSON-lines file, optionally filtered by task_id."""
        with self._lock:
            if not self.log_path.exists():
                return []
            records: List[StepRecord] = []
            with open(self.log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        rec = StepRecord(
                            timestamp=data.get("timestamp", ""),
                            task_id=data.get("task_id", ""),
                            stage=data.get("stage", ""),
                            llm_decision=data.get("llm_decision"),
                            action=data.get("action", ""),
                            parameters=data.get("parameters", {}),
                            result=data.get("result"),
                            evidence=data.get("evidence"),
                            duration=float(data.get("duration", 0.0)),
                        )
                        if task_id is None or rec.task_id == task_id:
                            records.append(rec)
                    except Exception:
                        continue
            return records

    def clear(self) -> None:
        """Clears the log file."""
        with self._lock:
            if self.log_path.exists():
                try:
                    self.log_path.unlink()
                except Exception:
                    pass


_global_logger: Optional[StepLogger] = None


def get_step_logger(log_path: Optional[Union[str, Path]] = None) -> StepLogger:
    """Retrieves or initializes the global StepLogger instance."""
    global _global_logger
    if _global_logger is None or (log_path is not None and Path(log_path).resolve() != _global_logger.log_path):
        from neo.config import get_settings
        target_path = log_path or get_settings().log_path
        _global_logger = StepLogger(target_path)
    return _global_logger
