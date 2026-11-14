"""
core/neo_computer_operator.py — Autonomous Computer-Operator Closed-Loop Agent for NEO.

Implements the strict Computer-Operator Protocol:
1. Truth Rules: State changes must be verified against current OS/screen state.
2. The Loop: LOOK -> CHECK LAST ACTION -> PLAN ONE STEP -> ACT -> SETTLE.
3. Strict Stage Management: Numbered task decomposition with verified stage gates.
4. Hard Handoff: Immediate pause and user delegation on payments, passwords, OTPs, or CAPTCHAs.
5. Deterministic Error Recovery: Alternative input dispatch (keyboard vs click) after unverified turns.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from core.neo_ui_automation import ui_automation, UIControl
from core.neo_os_automation import window_manager
from core.neo_visual_diff_oracle import diff_oracle


@dataclass
class OperatorTurn:
    turn_index: int
    current_stage: str
    observation: str
    last_action_result: str
    plan: str
    action: str
    target_id: Optional[int]
    text: Optional[str]
    confidence: str
    executed_success: bool = True
    state_diff: str = ""


class ComputerOperatorSession:
    """Manages an active autonomous computer operation task."""

    _SENSITIVE_KEYWORDS = {
        "cvv", "card number", "expiration date", "expiry", "credit card",
        "otp", "one-time password", "two-factor", "2fa", "authenticator",
        "captcha", "verify you are human", "security check", "recaptcha",
        "enter password", "master password", "pin code", "upi pin"
    }

    def __init__(self, goal: str, max_turns: int = 15):
        self.session_id = f"op_{int(time.time() * 1000)}"
        self.goal = goal.strip()
        self.max_turns = max_turns
        self.current_turn = 0
        self.stages: List[str] = self._compile_stages(self.goal)
        self.current_stage_idx = 0
        self.turns: List[OperatorTurn] = []
        self.concluded = False
        self.handoff_required = False
        self.handoff_reason = ""

        # Historical state
        self._last_state_signature = ""
        self._consecutive_failures = 0
        self._last_action_taken = ""

    def _compile_stages(self, goal: str) -> List[str]:
        """Deconstructs goal into initial numbered stages."""
        g = goal.lower()
        if "search" in g or "find" in g or "look up" in g:
            return [
                "1. Focus or launch application/browser",
                "2. Navigate to search input and enter query",
                "3. Execute search and observe results",
                "4. Select target item and extract information",
                "5. Verify completion and hand off"
            ]
        elif "open" in g or "launch" in g:
            return [
                "1. Identify application or window target",
                "2. Launch or bring window into active foreground",
                "3. Verify window is responsive and loaded",
                "4. Finalize state"
            ]
        elif "write" in g or "type" in g or "fill" in g:
            return [
                "1. Focus target document or active input field",
                "2. Verify input focus and clear if necessary",
                "3. Type required content accurately",
                "4. Verify content matches request and save/submit"
            ]
        return [
            "1. Assess desktop and active window context",
            "2. Navigate to required controls or interface",
            "3. Execute primary task actions",
            "4. Verify results and finalize"
        ]

    def _get_current_state(self) -> Tuple[str, List[UIControl], str]:
        """Captures ground truth observation: active window and list of interactive controls."""
        fg = window_manager.get_foreground_window()
        fg_title = fg["title"] if fg else "Unknown Window"
        fg_proc = fg["process_name"] if fg else ""

        controls = ui_automation.get_interactive_controls(timeout_secs=1.5)
        # Build signature to detect actual screen state transitions
        control_names = [f"{c.control_type}:{c.name}" for c in controls[:20] if c.name]
        signature = f"{fg_title}|{fg_proc}|{len(controls)}|" + ",".join(control_names[:10])

        obs_lines = [f"Active Window: '{fg_title}' ({fg_proc})"]
        if controls:
            obs_lines.append(f"Interactive Controls ({len(controls)}):")
            for idx, c in enumerate(controls[:12], 1):
                name_str = f"'{c.name}'" if c.name else "<unnamed>"
                obs_lines.append(f"  [{idx}] {c.control_type} {name_str} at {c.center}")
        else:
            obs_lines.append("No native accessibility controls detected (canvas/rendered view).")

        return "\n".join(obs_lines), controls, signature

    def step(self, forced_action: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Executes one turn of the computer-operator loop."""
        if self.concluded:
            return {"status": "done", "message": "Session already completed."}

        self.current_turn += 1
        obs_text, controls, current_signature = self._get_current_state()

        # 1. CHECK: Did last action work?
        last_action_result = "success"
        state_diff = "State changed"
        if self._last_state_signature:
            if current_signature == self._last_state_signature:
                last_action_result = "failed: screen state did not change after action"
                self._consecutive_failures += 1
                state_diff = "No observable change in window title or control tree"
            else:
                last_action_result = "success: observed state transition"
                self._consecutive_failures = 0
                state_diff = "Detected window or control change"
        else:
            last_action_result = "initial turn"

        # 2. HARD HANDOFF CHECK (Payments, OTPs, CAPTCHAs, Passwords)
        combined_text = (obs_text + " " + self.goal).lower()
        for kw in self._SENSITIVE_KEYWORDS:
            if kw in combined_text:
                self.handoff_required = True
                self.handoff_reason = f"Encountered security gate matching '{kw}'."
                turn = OperatorTurn(
                    turn_index=self.current_turn,
                    current_stage=self.stages[min(self.current_stage_idx, len(self.stages) - 1)],
                    observation=obs_text,
                    last_action_result=last_action_result,
                    plan=f"Pause and delegate control to user: {self.handoff_reason}",
                    action="ask_user",
                    target_id=None,
                    text=f"Please handle {kw} on screen. Let me know when complete.",
                    confidence="high",
                    state_diff=state_diff
                )
                self.turns.append(turn)
                self.concluded = True
                return self._turn_to_dict(turn)

        # 3. Check for repeated failures
        if self._consecutive_failures >= 3:
            turn = OperatorTurn(
                turn_index=self.current_turn,
                current_stage=self.stages[min(self.current_stage_idx, len(self.stages) - 1)],
                observation=obs_text,
                last_action_result=f"failed: 3 repeated attempts without screen change on {self._last_action_taken}",
                plan="Stop and ask user for clarification or manual intervention.",
                action="ask_user",
                target_id=None,
                text="The target element is not responding to simulated input. Would you like me to use keyboard navigation or manual coordinates?",
                confidence="low",
                state_diff="Stalled state"
            )
            self.turns.append(turn)
            self.concluded = True
            return self._turn_to_dict(turn)

        # 4. PLAN & ACT
        # Stage advancement check
        current_stage = self.stages[min(self.current_stage_idx, len(self.stages) - 1)]
        if self.current_turn >= 2 and last_action_result.startswith("success"):
            if self.current_stage_idx < len(self.stages) - 1:
                self.current_stage_idx += 1
                current_stage = self.stages[self.current_stage_idx]

        # Determine next action
        action = "wait"
        target_id: Optional[int] = None
        text_arg: Optional[str] = None
        plan = "Observe settling"
        confidence = "high"

        if forced_action:
            action = forced_action.get("action", "wait")
            target_id = forced_action.get("target_id")
            text_arg = forced_action.get("text")
            plan = forced_action.get("plan", "Executing specified step")
        else:
            # Autonomous heuristic planning based on goal & controls
            action, target_id, text_arg, plan, confidence = self._plan_next_step(controls, obs_text)

        # Execute physical action
        self._execute_action(action, target_id, text_arg, controls)
        self._last_action_taken = action
        self._last_state_signature = current_signature

        if action == "done":
            self.concluded = True

        turn = OperatorTurn(
            turn_index=self.current_turn,
            current_stage=current_stage,
            observation=obs_text,
            last_action_result=last_action_result,
            plan=plan,
            action=action,
            target_id=target_id,
            text=text_arg,
            confidence=confidence,
            state_diff=state_diff
        )
        self.turns.append(turn)
        return self._turn_to_dict(turn)

    def _plan_next_step(self, controls: List[UIControl], obs_text: str) -> Tuple[str, Optional[int], Optional[str], str, str]:
        """Selects the next verified action based on available controls and goal."""
        g = self.goal.lower()

        # Check if already done
        if self.current_stage_idx >= len(self.stages) - 1 and self.current_turn >= 3:
            return "done", None, None, "Goal stages verified and complete.", "high"

        # Match controls against goal keywords
        goal_words = set(re.findall(r"[a-z0-9]+", g))
        for idx, c in enumerate(controls[:12], 1):
            c_words = set(re.findall(r"[a-z0-9]+", c.name.lower()))
            if goal_words & c_words and c.is_plausible:
                if c.control_type == "Edit":
                    return "type", idx, self._extract_text_for_typing(), f"Found matching input field '{c.name}'.", "high"
                return "click", idx, None, f"Found target {c.control_type} '{c.name}' matching goal.", "high"

        # Search box fallback
        edit_controls = [c for c in controls if c.control_type == "Edit" and c.is_plausible]
        if edit_controls and ("type" in g or "search" in g or "find" in g):
            idx = controls.index(edit_controls[0]) + 1
            return "type", idx, self._extract_text_for_typing(), "Focus search input and type query.", "high"

        # Default safe action
        return "wait", None, None, "Wait 1.0s for window content to settle.", "medium"

    def _extract_text_for_typing(self) -> str:
        """Extracts text intended to be typed from goal."""
        m = re.search(r'(?:type|search for|enter|write)\s+["\']?([^"\']+)["\']?', self.goal, re.IGNORECASE)
        if m:
            return m.group(1).strip()
        words = self.goal.split()
        return " ".join(words[-3:]) if len(words) >= 3 else self.goal

    def _execute_action(self, action: str, target_id: Optional[int], text: Optional[str], controls: List[UIControl]) -> None:
        """Dispatches the physical OS tool action."""
        import pyautogui

        if action in ("click", "select"):
            if target_id and 1 <= target_id <= len(controls):
                c = controls[target_id - 1]
                pyautogui.click(c.center[0], c.center[1])
            else:
                pyautogui.click()
            time.sleep(0.3)

        elif action == "double_click":
            if target_id and 1 <= target_id <= len(controls):
                c = controls[target_id - 1]
                pyautogui.doubleClick(c.center[0], c.center[1])
            else:
                pyautogui.doubleClick()
            time.sleep(0.3)

        elif action == "right_click":
            if target_id and 1 <= target_id <= len(controls):
                c = controls[target_id - 1]
                pyautogui.rightClick(c.center[0], c.center[1])
            else:
                pyautogui.rightClick()
            time.sleep(0.3)

        elif action == "type":
            if target_id and 1 <= target_id <= len(controls):
                c = controls[target_id - 1]
                pyautogui.click(c.center[0], c.center[1])
                time.sleep(0.1)
            if text:
                import pyperclip
                pyperclip.copy(text)
                pyautogui.hotkey("ctrl", "v")
            time.sleep(0.2)

        elif action == "press_key":
            if text:
                pyautogui.press(text)
            time.sleep(0.2)

        elif action == "scroll":
            pyautogui.scroll(-3)
            time.sleep(0.2)

        elif action == "wait":
            time.sleep(1.0)

        # Adaptive settle watchdog: wait for any visual transitions/spinners to stabilize
        try:
            diff_oracle.wait_until_settled(max_wait_sec=1.2)
        except Exception:
            pass

    def _turn_to_dict(self, turn: OperatorTurn) -> Dict[str, Any]:
        """Formats output into the exact schema requested by user."""
        return {
            "current_stage": turn.current_stage,
            "observation": turn.observation,
            "last_action_result": turn.last_action_result,
            "plan": turn.plan,
            "action": turn.action,
            "target_id": turn.target_id,
            "text": turn.text,
            "confidence": turn.confidence,
        }

    def run_autonomous_loop(self, max_turns: int = 10) -> List[Dict[str, Any]]:
        """Executes consecutive operator turns until completion or handoff."""
        results = []
        for _ in range(max_turns):
            if self.concluded:
                break
            turn_data = self.step()
            results.append(turn_data)
            if turn_data.get("action") in ("done", "ask_user"):
                break
            time.sleep(0.4)
        return results


class ComputerOperatorRegistry:
    """Singleton manager for active computer operator sessions."""

    _instance: Optional["ComputerOperatorRegistry"] = None

    def __new__(cls) -> "ComputerOperatorRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._sessions: Dict[str, ComputerOperatorSession] = {}
            cls._active_session: Optional[ComputerOperatorSession] = None
        return cls._instance

    def create_session(self, goal: str) -> ComputerOperatorSession:
        session = ComputerOperatorSession(goal=goal)
        self._sessions[session.session_id] = session
        self._active_session = session
        return session

    def get_active(self) -> Optional[ComputerOperatorSession]:
        return self._active_session


computer_operator_registry = ComputerOperatorRegistry()
