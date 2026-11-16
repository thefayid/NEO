"""
neo/ui/confirmation_dialog.py — High-Security Modal Confirmation Popup.

Architectural Guarantees:
1. Always modal and topmost (never obscured by other apps).
2. Live countdown timer with strict auto-deny when time expires.
3. Defaults to DENY on window close, escape key, timeout, or error.
4. Clean dark-mode visual presentation displaying exact risk evidence.
"""
from __future__ import annotations

import ctypes
import logging
import threading
import time
from typing import Any, Optional, Tuple

from neo.safety.policy import RiskAssessment

logger = logging.getLogger("neo.ui.confirmation")


def show_confirmation_popup(
    action_name: str,
    assessment: RiskAssessment,
    timeout_sec: float = 30.0,
) -> Tuple[bool, str]:
    """
    Displays a modal confirmation dialog requesting human approval.
    Blocks the calling thread until the user decides or until timeout_sec expires.
    TIMEOUTS STRICTLY DEFAULT TO DENY.
    
    Returns:
        (approved: bool, reason: str)
    """
    result = {"approved": False, "reason": "Default deny", "completed": False}

    try:
        import tkinter as tk
        from tkinter import ttk
    except ImportError as e:
        logger.warning("Tkinter unavailable for confirmation dialog: %s. Falling back to native Windows dialog.", e)
        return _fallback_native_dialog(action_name, assessment, timeout_sec)

    try:
        root = tk.Tk()
        root.title("NEO Security Confirmation Gate")
        root.geometry("520x360")
        root.minsize(480, 320)
        root.configure(bg="#18181b")

        # Keep on top of all windows
        root.attributes("-topmost", True)
        try:
            root.lift()
            root.focus_force()
        except Exception:
            pass

        # Styling
        style = ttk.Style(root)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        # Frame container
        main_frame = tk.Frame(root, bg="#18181b", padx=20, pady=16)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Header with Alert Icon
        header_color = "#ef4444" if assessment.requires_hard_stop else "#f59e0b"
        header_text = "HARD STOP: USER TAKEOVER REQUIRED" if assessment.requires_hard_stop else "SECURITY CONFIRMATION REQUIRED"

        lbl_header = tk.Label(
            main_frame,
            text=f"⚠  {header_text}",
            font=("Segoe UI", 12, "bold"),
            fg=header_color,
            bg="#18181b",
        )
        lbl_header.pack(anchor="w", pady=(0, 8))

        # Action banner
        lbl_action = tk.Label(
            main_frame,
            text=f"Action: {action_name.upper()}",
            font=("Segoe UI", 11, "bold"),
            fg="#f4f4f5",
            bg="#27272a",
            padx=10,
            pady=6,
            relief=tk.FLAT,
        )
        lbl_action.pack(fill=tk.X, pady=(0, 10))

        # Risk description
        lbl_desc = tk.Label(
            main_frame,
            text=f"Reason: {assessment.summary}",
            font=("Segoe UI", 9),
            fg="#d4d4d8",
            bg="#18181b",
            wraplength=470,
            justify=tk.LEFT,
        )
        lbl_desc.pack(anchor="w", pady=(0, 6))

        if assessment.matched_patterns:
            patterns_str = ", ".join(assessment.matched_patterns[:4])
            lbl_patterns = tk.Label(
                main_frame,
                text=f"Matched Risk Rules: {patterns_str}",
                font=("Consolas", 8),
                fg="#a1a1aa",
                bg="#18181b",
                wraplength=470,
                justify=tk.LEFT,
            )
            lbl_patterns.pack(anchor="w", pady=(0, 8))

        # Countdown Timer Label
        time_left = [int(timeout_sec)]
        lbl_timer = tk.Label(
            main_frame,
            text=f"Time remaining: {time_left[0]}s (Default: DENY)",
            font=("Segoe UI", 9, "bold"),
            fg="#fbbf24",
            bg="#18181b",
        )
        lbl_timer.pack(anchor="w", pady=(0, 14))

        def on_approve():
            result["approved"] = True
            result["reason"] = "User explicitly approved via GUI confirmation dialog."
            result["completed"] = True
            root.destroy()

        def on_deny():
            result["approved"] = False
            result["reason"] = "User explicitly denied via GUI confirmation dialog."
            result["completed"] = True
            root.destroy()

        def on_close():
            result["approved"] = False
            result["reason"] = "Confirmation dialog closed by user. Defaulted to DENY."
            result["completed"] = True
            root.destroy()

        def tick():
            time_left[0] -= 1
            if time_left[0] <= 0:
                result["approved"] = False
                result["reason"] = f"Confirmation dialog timed out after {timeout_sec:.0f}s. Defaulted to DENY."
                result["completed"] = True
                root.destroy()
            else:
                lbl_timer.config(text=f"Time remaining: {time_left[0]}s (Default: DENY)")
                root.after(1000, tick)

        root.protocol("WM_DELETE_WINDOW", on_close)
        root.bind("<Escape>", lambda e: on_close())

        # Buttons Frame
        btn_frame = tk.Frame(main_frame, bg="#18181b")
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=(10, 0))

        btn_deny = tk.Button(
            btn_frame,
            text="✕  Deny Action (Esc)",
            font=("Segoe UI", 10, "bold"),
            bg="#dc2626",
            fg="#ffffff",
            activebackground="#b91c1c",
            activeforeground="#ffffff",
            relief=tk.FLAT,
            padx=16,
            pady=6,
            command=on_deny,
            cursor="hand2",
        )
        btn_deny.pack(side=tk.RIGHT, padx=(8, 0))
        btn_deny.focus_set()  # Default focus on Deny for security

        btn_approve = tk.Button(
            btn_frame,
            text="✓  Approve Action",
            font=("Segoe UI", 10),
            bg="#16a34a",
            fg="#ffffff",
            activebackground="#15803d",
            activeforeground="#ffffff",
            relief=tk.FLAT,
            padx=16,
            pady=6,
            command=on_approve,
            cursor="hand2",
        )
        btn_approve.pack(side=tk.RIGHT)

        # Start timer and main loop
        root.after(1000, tick)
        root.mainloop()

        return result["approved"], result["reason"]

    except Exception as e:
        logger.error("Error creating Tkinter confirmation popup: %s. Falling back to native dialog.", e)
        return _fallback_native_dialog(action_name, assessment, timeout_sec)


def _fallback_native_dialog(
    action_name: str,
    assessment: RiskAssessment,
    timeout_sec: float,
) -> Tuple[bool, str]:
    """
    Fallback native Win32 MessageBox with timeout using user32.MessageBoxTimeoutW.
    """
    try:
        user32 = ctypes.windll.user32
        MB_YESNO = 0x00000004
        MB_ICONWARNING = 0x00000030
        MB_DEFBUTTON2 = 0x00000100  # Default to NO
        MB_TOPMOST = 0x00040000
        IDYES = 6
        IDNO = 7
        MB_TIMEDOUT = 32000

        msg = (
            f"NEO SECURITY CONFIRMATION REQUIRED\n\n"
            f"Action: {action_name.upper()}\n"
            f"Reason: {assessment.summary}\n\n"
            f"Do you approve this action?\n"
            f"(Times out in {int(timeout_sec)}s -> defaults to NO)"
        )
        title = "NEO Security Gate"

        timeout_ms = int(timeout_sec * 1000)
        ret = user32.MessageBoxTimeoutW(
            None,
            msg,
            title,
            MB_YESNO | MB_ICONWARNING | MB_DEFBUTTON2 | MB_TOPMOST,
            0,
            timeout_ms,
        )

        if ret == IDYES:
            return True, "User approved via native Windows MessageBox."
        elif ret == MB_TIMEDOUT:
            return False, f"Confirmation timed out after {timeout_sec:.0f}s. Defaulted to DENY."
        else:
            return False, "User denied via native Windows MessageBox."

    except Exception as e:
        logger.error("Native Windows MessageBox failed: %s. Defaulting to DENY.", e)
        return False, f"All confirmation dialogs failed: {e}. Defaulted to DENY."
