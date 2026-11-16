"""
neo/cli.py — Command-Line Interface for NEO Personal Assistant.

Usage:
    python -m neo "Read sales.xlsx and draft summary email"
    python -m neo --model models/gemini-2.5-flash --gui-confirm "Check disk space"
"""
from __future__ import annotations

import argparse
import logging
import sys
import threading
from typing import Optional, Sequence

from neo.brain.agent import NeoAgent
from neo.brain.llm_client import get_llm_client
from neo.config import get_settings, load_settings
from neo.safety.emergency_stop import emergency_stop, setup_emergency_hotkey
from neo.tasks.task_manager import TaskState

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("neo.cli")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="neo",
        description="NEO — Accurate, Deterministic Windows Personal Assistant Agent",
    )
    parser.add_argument(
        "goal",
        type=str,
        help="Natural language instruction for NEO to execute",
    )
    parser.add_argument(
        "--provider",
        type=str,
        default="gemini",
        choices=["gemini", "openai", "mock"],
        help="LLM provider (default: gemini)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Model identifier override (e.g. models/gemini-2.5-flash or gpt-4o)",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=25,
        help="Maximum step budget for the task (default: 25)",
    )
    parser.add_argument(
        "--gui-confirm",
        action="store_true",
        help="Use topmost GUI popup for security confirmations instead of console prompt",
    )
    parser.add_argument(
        "--headless-browser",
        action="store_true",
        help="Run browser automation in headless mode (default: headed)",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    print("=" * 70)
    print(" NEO Personal Assistant Agent")
    print(f" Goal: {args.goal}")
    print(f" Emergency Stop: Press Ctrl+Alt+Shift+Q at any time to halt")
    print("=" * 70)

    # 1. Initialize Emergency Stop Hotkey Listener
    try:
        hotkey_thread = threading.Thread(target=setup_emergency_hotkey, daemon=True)
        hotkey_thread.start()
    except Exception as e:
        logger.warning("Could not register emergency stop global hotkey: %s", e)

    # 2. Configure LLM Client and Agent
    try:
        client = get_llm_client(provider=args.provider, model_name=args.model)
        agent = NeoAgent(
            llm_client=client,
            use_gui_confirmation=args.gui_confirm,
        )
    except Exception as e:
        logger.critical("Failed to initialize NEO Agent: %s", e)
        print(f"\n[!] Initialization Error: {e}")
        return 1

    # 3. Execute Task Loop
    try:
        task_rec = agent.run_task(goal=args.goal, max_steps=args.max_steps)

        print("\n" + "=" * 70)
        if task_rec.state == TaskState.COMPLETED:
            print(f" [✓] GOAL VERIFIED COMPLETED ({task_rec.current_step} steps)")
            print(f" Rationale: {task_rec.final_rationale}")
            print("=" * 70)
            return 0
        elif task_rec.state == TaskState.STOPPED:
            print(f" [!] TASK HALTED BY EMERGENCY STOP")
            print(f" Reason: {task_rec.final_rationale}")
            print("=" * 70)
            return 130
        else:
            print(f" [✗] TASK FAILED ({task_rec.current_step}/{task_rec.max_steps} steps)")
            print(f" Reason: {task_rec.final_rationale}")
            print("=" * 70)
            return 1

    except KeyboardInterrupt:
        print("\n[!] User interrupted with Ctrl+C. Halting NEO.")
        emergency_stop.trigger("KeyboardInterrupt received in CLI")
        return 130
    except Exception as e:
        logger.critical("Fatal error executing task: %s", e, exc_info=True)
        print(f"\n[!] Fatal Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
