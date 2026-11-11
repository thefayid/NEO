"""
actions/deep_thought_action.py — Cortex Beta Deep Reasoning Engine for NEO.

Auto-discovered by core/action_loader.py. Exposes asynchronous deep reasoning,
multi-step cognitive logic, algorithmic architecture, and mathematical proofs to
Cortex Alpha (Gemini Live Stream) and the Voice Assistant.
"""
from __future__ import annotations

import threading
from typing import Any, Dict, Optional
from core.neo_central_coordinator import central_core


def _run_background_reasoning(query: str, context: str, player: Any, speak: Any) -> None:
    """Worker running deep reasoning asynchronously so Cortex Alpha audio reflex never freezes."""
    try:
        res = central_core.dispatch_deep_reasoning(query, context)
        solution = res.get("solution", "")
        summary = res.get("summary", "")

        # 1. Update UI content card and Chat transcript
        if player:
            try:
                if hasattr(player, "show_content"):
                    player.show_content("CORTEX BETA · DEEP REASONING", solution)
            except Exception:
                pass

            try:
                if hasattr(player, "_on_live_speech"):
                    player._on_live_speech("Cortex Beta", f"**Deep Analysis for:** *{query[:80]}*\n\n{solution}")
                elif hasattr(player, "write_log"):
                    player.write_log(f"🧠 CORTEX BETA: {summary}")
            except Exception:
                pass

        # 2. Executive audio summary via Cortex Alpha
        if speak and summary:
            try:
                speak(f"Boss, Cortex Beta finished reasoning: {summary}")
            except Exception:
                pass
        elif player and hasattr(player, "speak_text") and summary:
            try:
                player.speak_text(f"Boss, Cortex Beta finished reasoning: {summary}")
            except Exception:
                pass

    except Exception as e:
        err_msg = f"Cortex Beta reasoning encountered an error: {e}"
        print(f"[Cortex Beta] Error: {e}")
        if player and hasattr(player, "write_log"):
            player.write_log(err_msg)


def cortex_deep_reasoning(parameters: dict, player: Any = None, speak: Any = None, **kwargs) -> str:
    """
    Non-blocking tool handler invoked by Cortex Alpha (Gemini Live).
    Immediately returns an acoustic acknowledgment while dispatching Cortex Beta in background.
    """
    query = str(parameters.get("query", "")).strip()
    context = str(parameters.get("context", "")).strip()

    if not query:
        return "Please specify a query, problem, or architectural question for Cortex Beta to reason through."

    # Launch Cortex Beta reasoning asynchronously
    worker = threading.Thread(
        target=_run_background_reasoning,
        args=(query, context, player, speak),
        daemon=True,
        name="CortexBetaReasoningWorker"
    )
    worker.start()

    return (
        f"Cortex Beta deep reasoning dispatched for: '{query[:60]}...'. "
        "Audio reflex stream remains responsive; full solution will appear on screen momentarily."
    )


TOOL = {
    "name": "cortex_deep_reasoning",
    "description": (
        "Dispatches deep multi-step thinking, complex code analysis, architectural design, "
        "algorithmic debugging, or mathematical proofs to Cortex Beta (Gemini Deep Thinking Engine). "
        "Use whenever the user asks for deep reasoning, step-by-step logic, code architecture, "
        "algorithm design, or complex problem solving that requires deep cognitive thought."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "query": {
                "type": "STRING",
                "description": "The complex query, coding problem, math challenge, or architectural question to reason through."
            },
            "context": {
                "type": "STRING",
                "description": "Optional background, code snippet, error traceback, or system context."
            }
        },
        "required": ["query"]
    },
    "behavior": "NON_BLOCKING",
    "scheduling": "WHEN_IDLE",
    "handler": cortex_deep_reasoning,
}

