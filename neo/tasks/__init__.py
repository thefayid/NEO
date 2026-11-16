"""
neo.tasks — Stage-Based Task State Machine, Resilience Engine, Checkpoints, and Skill Library.
"""
from neo.tasks.checkpoints import (
    RISKY_ACTIONS,
    CheckpointManager,
    CheckpointRecord,
    RollbackResult,
)
from neo.tasks.reports import (
    StageReportItem,
    TaskReport,
    TaskReportGenerator,
)
from neo.tasks.retry_policy import (
    ActionFingerprint,
    BudgetStatus,
    LoopDetectionResult,
    LoopDetector,
    MethodTier,
    RetryDecision,
    RetryPolicy,
    TaskBudgetLimits,
)
from neo.tasks.skills import (
    ReplayResult,
    Routine,
    RoutineReplayer,
    RoutineStep,
    SkillLibrary,
)
from neo.tasks.stages import (
    CustomCheck,
    ElementExistsCheck,
    FileExistsCheck,
    Stage,
    StageCheck,
    StageCheckResult,
    StageStateMachine,
    StageStatus,
    URLContainsCheck,
    ValueEqualsCheck,
)
from neo.tasks.task_manager import (
    StepRecord,
    TaskManager,
    TaskRecord,
    TaskState,
)

__all__ = [
    # Stages
    "Stage",
    "StageStatus",
    "StageStateMachine",
    "StageCheck",
    "StageCheckResult",
    "FileExistsCheck",
    "ValueEqualsCheck",
    "ElementExistsCheck",
    "URLContainsCheck",
    "CustomCheck",
    # Retry & Loops
    "LoopDetector",
    "LoopDetectionResult",
    "ActionFingerprint",
    "RetryPolicy",
    "RetryDecision",
    "MethodTier",
    "TaskBudgetLimits",
    "BudgetStatus",
    # Checkpoints & Rollback
    "CheckpointManager",
    "CheckpointRecord",
    "RollbackResult",
    "RISKY_ACTIONS",
    # Skills & Replay
    "Routine",
    "RoutineStep",
    "SkillLibrary",
    "RoutineReplayer",
    "ReplayResult",
    # Reports
    "TaskReport",
    "TaskReportGenerator",
    "StageReportItem",
    # Task Manager
    "TaskManager",
    "TaskRecord",
    "TaskState",
    "StepRecord",
]
