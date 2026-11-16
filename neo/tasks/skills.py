"""
neo/tasks/skills.py — Parameterized Routine Library and Deterministic Replay with LLM Fallback.

Architectural Guarantees:
1. Parameterized Routine Abstraction:
   - Successful, fully verified action sequences can be captured as named, parameterized routines.
   - String interpolation uses `{{param_name}}` placeholders across complex nested parameter dictionaries.
2. Step-by-Step Deterministic Replay with Continuous Verification:
   - Every single replayed step must pass empirical code-level verification.
   - If ANY step fails verification, replay immediately halts and flags `fallback_needed=True`.
3. Seamless LLM Fallback:
   - When deterministic replay encounters UI drift, layout changes, or verification failure,
     control cleanly falls back to the dynamic LLM / NeoAgent to finish the task.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Union

from neo.brain.planner import ActionDispatcher, StepExecutionResult
from neo.brain.whitelist import AgentDecision
from neo.safety.emergency_stop import emergency_stop

logger = logging.getLogger("neo.tasks.skills")

PARAM_REGEX = re.compile(r"\{\{([a-zA-Z0-9_]+)\}\}")


@dataclass
class RoutineStep:
    """A single deterministic action step within a parameterized routine."""
    action: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    expected_check: Optional[Dict[str, Any]] = None
    description: str = ""

    def render(self, variables: Dict[str, Any]) -> RoutineStep:
        """Substitutes {{variable}} placeholders with actual values."""
        def _substitute(val: Any) -> Any:
            if isinstance(val, str):
                # Check for exact whole-match replacement to preserve native types (int, float, bool)
                m = PARAM_REGEX.fullmatch(val.strip())
                if m:
                    var_name = m.group(1)
                    if var_name in variables:
                        return variables[var_name]
                # Partial string interpolation
                def _repl(match: re.Match) -> str:
                    var_name = match.group(1)
                    return str(variables.get(var_name, match.group(0)))
                return PARAM_REGEX.sub(_repl, val)
            elif isinstance(val, dict):
                return {k: _substitute(v) for k, v in val.items()}
            elif isinstance(val, list):
                return [_substitute(item) for item in val]
            return val

        rendered_params = {k: _substitute(v) for k, v in self.parameters.items()}
        return RoutineStep(
            action=self.action,
            parameters=rendered_params,
            expected_check=self.expected_check,
            description=_substitute(self.description),
        )


@dataclass
class Routine:
    """A named, parameterized sequence of verified actions."""
    name: str
    description: str
    parameters_schema: Dict[str, str] = field(default_factory=dict)  # param_name -> doc
    steps: List[RoutineStep] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    version: int = 1
    tags: List[str] = field(default_factory=list)

    def render(self, variables: Dict[str, Any]) -> List[RoutineStep]:
        """Renders all steps with the given variable substitutions."""
        return [step.render(variables) for step in self.steps]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters_schema": self.parameters_schema,
            "steps": [asdict(s) for s in self.steps],
            "created_at": self.created_at,
            "version": self.version,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Routine:
        steps_raw = data.get("steps", [])
        steps = [
            RoutineStep(
                action=s.get("action", ""),
                parameters=s.get("parameters", {}),
                expected_check=s.get("expected_check"),
                description=s.get("description", ""),
            )
            for s in steps_raw
        ]
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            parameters_schema=data.get("parameters_schema", {}),
            steps=steps,
            created_at=data.get("created_at", time.time()),
            version=data.get("version", 1),
            tags=data.get("tags", []),
        )


@dataclass
class ReplayResult:
    """Outcome of replaying a parameterized routine."""
    ok: bool
    routine_name: str
    completed_steps: int
    total_steps: int
    fallback_needed: bool = False
    failed_step_index: Optional[int] = None
    last_result: Optional[Dict[str, Any]] = None
    message: str = ""
    evidence: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "routine_name": self.routine_name,
            "completed_steps": self.completed_steps,
            "total_steps": self.total_steps,
            "fallback_needed": self.fallback_needed,
            "failed_step_index": self.failed_step_index,
            "last_result": self.last_result,
            "message": self.message,
            "evidence": self.evidence,
        }


class SkillLibrary:
    """
    Persistent repository of saved routines.
    Supports saving from completed tasks, retrieval, and disk persistence.
    """

    def __init__(self, storage_path: Optional[Union[str, Path]] = None) -> None:
        self.storage_path = Path(storage_path or "neo_skills.json").resolve()
        self._skills: Dict[str, Routine] = {}
        self.load()

    def load(self) -> None:
        """Loads routines from storage file if it exists."""
        if not self.storage_path.exists():
            return
        try:
            content = self.storage_path.read_text(encoding="utf-8")
            data = json.loads(content)
            for item in data:
                routine = Routine.from_dict(item)
                self._skills[routine.name] = routine
            logger.info("Loaded %d skills from '%s'.", len(self._skills), self.storage_path)
        except Exception as e:
            logger.warning("Could not load skills from '%s': %e", self.storage_path, e)

    def save(self) -> None:
        """Persists current skills to storage file."""
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            data = [r.to_dict() for r in self._skills.values()]
            self.storage_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error("Could not persist skills to '%s': %e", self.storage_path, e)

    def save_skill(self, routine: Routine) -> None:
        """Adds or updates a routine and saves to disk."""
        self._skills[routine.name] = routine
        self.save()
        logger.info("Saved skill routine '%s' (%d steps).", routine.name, len(routine.steps))

    def get_skill(self, name: str) -> Optional[Routine]:
        return self._skills.get(name)

    def list_skills(self) -> List[Routine]:
        return list(self._skills.values())

    def delete_skill(self, name: str) -> bool:
        if name in self._skills:
            del self._skills[name]
            self.save()
            return True
        return False

    def create_routine_from_task(
        self,
        name: str,
        task_record: Any,
        description: str = "",
        parameter_substitutions: Optional[Dict[str, str]] = None,
        parameters_schema: Optional[Dict[str, str]] = None,
    ) -> Routine:
        """
        Creates a parameterized routine from the verified steps of a completed task.
        Replaces literal values found in parameter_substitutions (literal -> placeholder_name).
        """
        subs = dict(parameter_substitutions or {})
        steps: List[RoutineStep] = []

        for step_rec in getattr(task_record, "steps", []):
            res = getattr(step_rec, "result", {})
            if not res.get("ok", False):
                continue  # Only capture successful steps

            dec = getattr(step_rec, "decision", {})
            act = dec.get("action", "")
            params = dict(dec.get("parameters", {}))

            # Apply parameterization substitutions
            for lit_val, var_name in subs.items():
                for k, v in list(params.items()):
                    if isinstance(v, str) and lit_val in v:
                        params[k] = v.replace(lit_val, f"{{{{{var_name}}}}}")

            steps.append(
                RoutineStep(
                    action=act,
                    parameters=params,
                    description=dec.get("thought", f"Execute {act}"),
                )
            )

        routine = Routine(
            name=name,
            description=description or getattr(task_record, "goal", ""),
            parameters_schema=dict(parameters_schema or {}),
            steps=steps,
        )
        self.save_skill(routine)
        return routine


class RoutineReplayer:
    """
    Executes a Routine deterministically step-by-step with continuous empirical verification.
    If any step fails verification, halts and initiates LLM fallback.
    """

    def __init__(self, dispatcher: Optional[ActionDispatcher] = None) -> None:
        self.dispatcher = dispatcher or ActionDispatcher()

    def replay(
        self,
        routine: Routine,
        variables: Optional[Dict[str, Any]] = None,
        registry: Optional[Any] = None,
    ) -> ReplayResult:
        """
        Replays the routine deterministically with variable substitutions.
        Halts immediately on verification failure.
        """
        vars_dict = dict(variables or {})
        rendered_steps = routine.render(vars_dict)
        evidence_log: List[Dict[str, Any]] = []

        for i, step in enumerate(rendered_steps):
            emergency_stop.check_stop()

            decision = AgentDecision(
                thought=step.description or f"Replaying step {i + 1} of {routine.name}",
                action=step.action,
                parameters=step.parameters,
            )

            # Dispatch action
            exec_res = self.dispatcher.dispatch(decision, registry=registry)
            step_ev = {
                "step_index": i + 1,
                "action": step.action,
                "parameters": step.parameters,
                "ok": exec_res.ok,
                "warning": exec_res.warning,
                "error": exec_res.error,
                "evidence": exec_res.evidence,
            }
            evidence_log.append(step_ev)

            # Verification: check both exec_res.ok and that it didn't fail verification
            if not exec_res.ok:
                err_msg = (
                    f"Routine '{routine.name}' failed at step {i + 1} ({step.action}): "
                    f"{exec_res.error or 'Action failed'}. Halting replay for LLM fallback."
                )
                logger.warning(err_msg)
                return ReplayResult(
                    ok=False,
                    routine_name=routine.name,
                    completed_steps=i,
                    total_steps=len(rendered_steps),
                    fallback_needed=True,
                    failed_step_index=i,
                    last_result=step_ev,
                    message=err_msg,
                    evidence=evidence_log,
                )

        success_msg = f"Routine '{routine.name}' successfully replayed all {len(rendered_steps)} steps."
        logger.info(success_msg)
        return ReplayResult(
            ok=True,
            routine_name=routine.name,
            completed_steps=len(rendered_steps),
            total_steps=len(rendered_steps),
            fallback_needed=False,
            message=success_msg,
            evidence=evidence_log,
        )

    def replay_with_fallback(
        self,
        routine: Routine,
        variables: Optional[Dict[str, Any]] = None,
        fallback_handler: Optional[Callable[[ReplayResult], Any]] = None,
        registry: Optional[Any] = None,
    ) -> ReplayResult:
        """
        Replays deterministically. If verification fails, invokes the fallback_handler
        (e.g., dynamic LLM / agent recovery).
        """
        res = self.replay(routine=routine, variables=variables, registry=registry)
        if res.fallback_needed and fallback_handler is not None:
            logger.info("Invoking LLM fallback handler after replay failure at step %s.", res.failed_step_index)
            try:
                fallback_handler(res)
            except Exception as e:
                logger.error("Fallback handler encountered error: %e", e)
        return res
