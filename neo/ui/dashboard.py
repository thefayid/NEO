"""
neo/ui/dashboard.py — Real-Time Local Controller Dashboard and Safety Command Center.

Architectural Guarantees:
1. Live Multi-Panel Visualization:
   - Current stage & step progression indicator.
   - "What Neo Sees": Real-time scaled screenshot preview canvas & active interactive element table.
   - "Planned Action": Action name, target, parameters, and model rationale.
   - Live streaming execution log with colored severity markers.
2. Direct Human-in-the-Loop Controls:
   - Green "Approve" button and Red "Deny" button wired to Confirmation Gates.
   - Prominent, high-priority Red "EMERGENCY STOP" button halting all operations immediately.
   - One-click Voice Input trigger integrating local Whisper transcription.
3. Thread-Safe Architecture:
   - Uses a thread-safe UI update queue; background workers, task managers, and agents can
     dispatch state updates without GUI thread locking or race conditions.
"""
from __future__ import annotations

import io
import json
import logging
import queue
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Union

from neo.safety.emergency_stop import EmergencyStopTriggeredError, emergency_stop
from neo.ui.triggers import GlobalHotkeyManager, VoiceTrigger

logger = logging.getLogger("neo.ui.dashboard")


class NeoDashboard:
    """
    Tkinter-based live local dashboard for monitoring, controlling, and gating NEO agents.
    """

    def __init__(
        self,
        title: str = "NEO Autonomous Controller",
        enable_hotkeys: bool = True,
        on_voice_input: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.title = title
        self.enable_hotkeys = enable_hotkeys
        self.on_voice_input_cb = on_voice_input

        self._queue: queue.Queue = queue.Queue()
        self._running = False
        self._root = None
        self._pending_approval_cb: Optional[Callable[[bool], None]] = None

        self.hotkey_mgr: Optional[GlobalHotkeyManager] = None
        self.voice_trigger = VoiceTrigger()
        self._tk_thread: Optional[threading.Thread] = None

    def start(self, in_thread: bool = False) -> None:
        """Starts the dashboard GUI. If in_thread is True, runs on a daemon background thread."""
        if in_thread:
            self._tk_thread = threading.Thread(target=self._run_gui, daemon=True)
            self._tk_thread.start()
            # Wait briefly for Tk root initialization
            time.sleep(0.3)
        else:
            self._run_gui()

    def _run_gui(self) -> None:
        import tkinter as tk
        from tkinter import ttk, scrolledtext
        from PIL import Image, ImageTk

        self._root = tk.Tk()
        self._root.title(self.title)
        self._root.geometry("1080x720")
        self._root.minsize(960, 640)
        self._root.configure(bg="#18181b")

        # Global Hotkeys
        if self.enable_hotkeys:
            self.hotkey_mgr = GlobalHotkeyManager()
            self.hotkey_mgr.register_default_hotkeys(
                on_stop=self._on_emergency_stop,
                on_focus=self._focus_window,
                on_voice=self._on_voice_trigger_click,
            )
            self.hotkey_mgr.start()

        self._running = True
        self._build_widgets(tk, ttk, scrolledtext, Image, ImageTk)

        # Start periodic queue polling
        self._root.after(50, self._process_queue)
        try:
            self._root.mainloop()
        finally:
            self._running = False
            if self.hotkey_mgr:
                self.hotkey_mgr.stop()

    def _build_widgets(self, tk, ttk, scrolledtext, Image, ImageTk) -> None:
        style = ttk.Style(self._root)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        # 1. Top Header Bar
        top_bar = tk.Frame(self._root, bg="#27272a", height=60, padx=16, pady=10)
        top_bar.pack(fill=tk.X, side=tk.TOP)

        lbl_logo = tk.Label(top_bar, text="NEO AGENT", font=("Segoe UI", 14, "bold"), fg="#38bdf8", bg="#27272a")
        lbl_logo.pack(side=tk.LEFT, padx=(0, 16))

        self.lbl_status = tk.Label(
            top_bar,
            text="STATUS: IDLE",
            font=("Segoe UI", 10, "bold"),
            fg="#10b981",
            bg="#064e3b",
            padx=10,
            pady=4,
            relief=tk.FLAT,
        )
        self.lbl_status.pack(side=tk.LEFT, padx=(0, 20))

        self.lbl_stage = tk.Label(
            top_bar,
            text="Current Stage: [No Active Task]",
            font=("Segoe UI", 11),
            fg="#f4f4f5",
            bg="#27272a",
        )
        self.lbl_stage.pack(side=tk.LEFT)

        # 2. Main Body Split Panes (Left: Vision/Snapshot, Right: Actions/Log)
        body_frame = tk.Frame(self._root, bg="#18181b", padx=12, pady=10)
        body_frame.pack(fill=tk.BOTH, expand=True)

        left_pane = tk.Frame(body_frame, bg="#18181b", width=520)
        left_pane.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))

        right_pane = tk.Frame(body_frame, bg="#18181b", width=520)
        right_pane.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(6, 0))

        # --- Left Pane: What Neo Sees ---
        lbl_vision_title = tk.Label(left_pane, text="WHAT NEO SEES (SCREENSHOT & ELEMENTS)", font=("Segoe UI", 10, "bold"), fg="#a1a1aa", bg="#18181b")
        lbl_vision_title.pack(anchor="w", pady=(0, 4))

        # Screenshot Preview Box
        self.canvas_screen = tk.Canvas(left_pane, bg="#09090b", height=240, highlightthickness=1, highlightbackground="#3f3f46")
        self.canvas_screen.pack(fill=tk.X, pady=(0, 8))
        self.canvas_screen.create_text(250, 120, text="[Screenshot Preview Ready]", fill="#71717a", font=("Segoe UI", 10))

        # Interactive Element Treeview Table
        tree_frame = tk.Frame(left_pane, bg="#18181b")
        tree_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("id", "type", "name", "auto_id", "enabled")
        self.element_tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=8)
        self.element_tree.heading("id", text="ID")
        self.element_tree.heading("type", text="Control Type")
        self.element_tree.heading("name", text="Name / Accessible Text")
        self.element_tree.heading("auto_id", text="Automation ID")
        self.element_tree.heading("enabled", text="Enabled")

        self.element_tree.column("id", width=45, anchor="center")
        self.element_tree.column("type", width=100)
        self.element_tree.column("name", width=180)
        self.element_tree.column("auto_id", width=110)
        self.element_tree.column("enabled", width=65, anchor="center")

        tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.element_tree.yview)
        self.element_tree.configure(yscrollcommand=tree_scroll.set)
        self.element_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # --- Right Pane: Planned Action & Live Log ---
        lbl_action_title = tk.Label(right_pane, text="PLANNED ACTION & REASONING", font=("Segoe UI", 10, "bold"), fg="#a1a1aa", bg="#18181b")
        lbl_action_title.pack(anchor="w", pady=(0, 4))

        self.card_action = tk.Frame(right_pane, bg="#27272a", padx=12, pady=10, relief=tk.FLAT)
        self.card_action.pack(fill=tk.X, pady=(0, 8))

        self.lbl_action_name = tk.Label(self.card_action, text="Action: [Idle]", font=("Segoe UI", 11, "bold"), fg="#38bdf8", bg="#27272a")
        self.lbl_action_name.pack(anchor="w")

        self.lbl_action_details = tk.Label(self.card_action, text="Parameters: {}", font=("Consolas", 9), fg="#e4e4e7", bg="#27272a", justify=tk.LEFT)
        self.lbl_action_details.pack(anchor="w", pady=(4, 2))

        self.lbl_action_thought = tk.Label(self.card_action, text="Thought: Agent is waiting for instructions.", font=("Segoe UI", 9, "italic"), fg="#a1a1aa", bg="#27272a", wraplength=480, justify=tk.LEFT)
        self.lbl_action_thought.pack(anchor="w")

        # Live Execution Log
        lbl_log_title = tk.Label(right_pane, text="LIVE AUDIT LOG", font=("Segoe UI", 10, "bold"), fg="#a1a1aa", bg="#18181b")
        lbl_log_title.pack(anchor="w", pady=(4, 4))

        self.txt_log = scrolledtext.ScrolledText(right_pane, bg="#09090b", fg="#e4e4e7", font=("Consolas", 9), wrap=tk.WORD, height=12)
        self.txt_log.pack(fill=tk.BOTH, expand=True)
        self.txt_log.tag_config("INFO", foreground="#38bdf8")
        self.txt_log.tag_config("SUCCESS", foreground="#34d399")
        self.txt_log.tag_config("WARNING", foreground="#fbbf24")
        self.txt_log.tag_config("ERROR", foreground="#f87171")
        self.txt_log.tag_config("SAFETY", foreground="#ef4444", font=("Consolas", 9, "bold"))

        # 3. Bottom Controls & Emergency Stop Bar
        ctrl_bar = tk.Frame(self._root, bg="#27272a", height=65, padx=16, pady=10)
        ctrl_bar.pack(fill=tk.X, side=tk.BOTTOM)

        # Approve Button
        self.btn_approve = tk.Button(
            ctrl_bar,
            text="✔ APPROVE",
            font=("Segoe UI", 10, "bold"),
            bg="#15803d",
            fg="#ffffff",
            activebackground="#16a34a",
            padx=16,
            pady=6,
            relief=tk.FLAT,
            command=self._on_approve,
            state=tk.DISABLED,
        )
        self.btn_approve.pack(side=tk.LEFT, padx=(0, 10))

        # Deny Button
        self.btn_deny = tk.Button(
            ctrl_bar,
            text="✖ DENY",
            font=("Segoe UI", 10, "bold"),
            bg="#991b1b",
            fg="#ffffff",
            activebackground="#b91c1c",
            padx=16,
            pady=6,
            relief=tk.FLAT,
            command=self._on_deny,
            state=tk.DISABLED,
        )
        self.btn_deny.pack(side=tk.LEFT, padx=(0, 20))

        # Voice Trigger Button
        self.btn_voice = tk.Button(
            ctrl_bar,
            text="🎤 Voice Input",
            font=("Segoe UI", 10),
            bg="#374151",
            fg="#f9fafb",
            activebackground="#4b5563",
            padx=14,
            pady=6,
            relief=tk.FLAT,
            command=self._on_voice_trigger_click,
        )
        self.btn_voice.pack(side=tk.LEFT)

        # BIG RED EMERGENCY STOP BUTTON
        self.btn_stop = tk.Button(
            ctrl_bar,
            text="🛑 EMERGENCY STOP (F12)",
            font=("Segoe UI", 11, "bold"),
            bg="#dc2626",
            fg="#ffffff",
            activebackground="#ef4444",
            padx=20,
            pady=6,
            relief=tk.RAISED,
            command=self._on_emergency_stop,
        )
        self.btn_stop.pack(side=tk.RIGHT)

        self.append_log("NEO Autonomous Controller Dashboard initialized.", level="SUCCESS")

    def _focus_window(self) -> None:
        """Brings the dashboard window to the foreground."""
        if self._root:
            try:
                self._root.lift()
                self._root.focus_force()
            except Exception:
                pass

    def _on_emergency_stop(self) -> None:
        """Triggers emergency stop instantly and updates dashboard state."""
        emergency_stop.trigger("EMERGENCY STOP BUTTON CLICKED ON DASHBOARD")
        self.lbl_status.config(text="STOPPED", fg="#ffffff", bg="#dc2626")
        self.append_log("🛑 EMERGENCY STOP TRIGGERED. All actions halted immediately.", level="SAFETY")

    def _on_approve(self) -> None:
        if self._pending_approval_cb:
            cb = self._pending_approval_cb
            self._pending_approval_cb = None
            self.btn_approve.config(state="disabled")
            self.btn_deny.config(state="disabled")
            self.lbl_status.config(text="RUNNING", fg="#38bdf8", bg="#0c4a6e")
            cb(True)

    def _on_deny(self) -> None:
        if self._pending_approval_cb:
            cb = self._pending_approval_cb
            self._pending_approval_cb = None
            self.btn_approve.config(state="disabled")
            self.btn_deny.config(state="disabled")
            self.lbl_status.config(text="DENIED", fg="#f87171", bg="#450a0a")
            cb(False)

    def _on_voice_trigger_click(self) -> None:
        """Handles voice input button click, invoking Whisper transcription."""
        self.append_log("Voice capture active: Speak your instruction...", level="INFO")
        self.btn_voice.config(text="🎤 Listening...", bg="#8b5cf6")

        def _voice_cb(transcribed_text: str):
            def _gui_update():
                self.btn_voice.config(text="🎤 Voice Input", bg="#374151")
                self.append_log(f"Voice Recognized: '{transcribed_text}'", level="SUCCESS")
                if self.on_voice_input_cb:
                    self.on_voice_input_cb(transcribed_text)
            self._queue.put(_gui_update)

        self.voice_trigger.listen_in_background(callback=_voice_cb, duration_s=4.0)

    # ─────────────────────────────────────────────────────────────────────────
    # Thread-Safe Public State Updating API
    # ─────────────────────────────────────────────────────────────────────────
    def update_stage(self, stage_name: str, current_step: int = 1, max_steps: int = 25) -> None:
        """Updates the top stage and progress indicators."""
        def _update():
            self.lbl_stage.config(text=f"Stage: {stage_name} [Step {current_step}/{max_steps}]")
            self.lbl_status.config(text="RUNNING", fg="#38bdf8", bg="#0c4a6e")
        self._queue.put(_update)

    def update_vision(
        self,
        elements: Sequence[Dict[str, Any]],
        screenshot_path_or_bytes: Optional[Union[str, Path, bytes]] = None,
    ) -> None:
        """Updates the interactive elements table and screenshot canvas."""
        def _update():
            # Clear old rows
            for item in self.element_tree.get_children():
                self.element_tree.delete(item)

            for el in elements:
                self.element_tree.insert(
                    "",
                    "end",
                    values=(
                        el.get("id", ""),
                        el.get("control_type") or el.get("role", ""),
                        el.get("name") or el.get("text", ""),
                        el.get("automation_id", ""),
                        "Yes" if el.get("enabled", True) else "No",
                    ),
                )

            # Render image preview if provided
            if screenshot_path_or_bytes:
                try:
                    from PIL import Image, ImageTk
                    if isinstance(screenshot_path_or_bytes, (str, Path)):
                        img = Image.open(str(screenshot_path_or_bytes))
                    else:
                        img = Image.open(io.BytesIO(screenshot_path_or_bytes))

                    # Resize to fit canvas
                    canvas_w = self.canvas_screen.winfo_width() or 480
                    canvas_h = self.canvas_screen.winfo_height() or 240
                    img.thumbnail((canvas_w, canvas_h))
                    photo = ImageTk.PhotoImage(img)
                    self.canvas_screen.delete("all")
                    self.canvas_screen.create_image(canvas_w // 2, canvas_h // 2, image=photo)
                    self.canvas_screen.image = photo  # keep reference
                except Exception as e:
                    logger.debug("Could not render thumbnail: %s", e)

        self._queue.put(_update)

    def update_planned_action(self, action: str, parameters: Dict[str, Any], thought: str = "") -> None:
        """Updates the Planned Action inspection card."""
        def _update():
            self.lbl_action_name.config(text=f"Action: {action.upper()}")
            param_str = json.dumps(parameters, indent=1) if parameters else "{}"
            if len(param_str) > 120:
                param_str = param_str[:115] + " ... }"
            self.lbl_action_details.config(text=f"Parameters:\n{param_str}")
            self.lbl_action_thought.config(text=f"Thought: {thought}" if thought else "")
        self._queue.put(_update)

    def request_approval(self, action_name: str, reason: str, callback: Callable[[bool], None]) -> None:
        """Activates Approve/Deny buttons and awaits human user input."""
        def _update():
            self._pending_approval_cb = callback
            self.lbl_status.config(text="AWAITING APPROVAL", fg="#fef08a", bg="#854d0e")
            self.btn_approve.config(state="normal")
            self.btn_deny.config(state="normal")
            self.append_log(f"⚠ SECURITY CONFIRMATION REQUIRED for '{action_name}': {reason}", level="WARNING")
        self._queue.put(_update)

    def append_log(self, message: str, level: str = "INFO") -> None:
        """Appends a timestamped log entry to the live audit log."""
        def _update():
            ts = time.strftime("%H:%M:%S")
            entry = f"[{ts}] [{level}] {message}\n"
            self.txt_log.insert(tk.END, entry, level)
            self.txt_log.see(tk.END)
        self._queue.put(_update)

    def _process_queue(self) -> None:
        """Pumps queued callbacks onto the Tkinter main thread."""
        while not self._queue.empty():
            try:
                fn = self._queue.get_nowait()
                fn()
            except Exception as e:
                logger.error("Error processing dashboard queue: %s", e)
        if self._running and self._root:
            self._root.after(50, self._process_queue)

    def close(self) -> None:
        """Gracefully closes the dashboard window."""
        self._running = False
        if self._root:
            try:
                self._root.quit()
                self._root.destroy()
            except Exception:
                pass


def main():
    """Runs the dashboard in standalone interactive demo mode."""
    dashboard = NeoDashboard(title="NEO Autonomous Controller (Demo)")
    dashboard.start(in_thread=True)

    # Send simulated telemetry to demo widgets
    time.sleep(0.5)
    dashboard.update_stage("Web Form Automation", current_step=1, max_steps=5)
    dashboard.update_planned_action("goto", {"url": "https://example.com/intake"}, thought="Navigating to portal")
    dashboard.append_log("Navigating to https://example.com/intake", level="INFO")

    time.sleep(1.0)
    sample_elements = [
        {"id": 1, "role": "heading", "name": "Intake Portal", "automation_id": "title", "enabled": True},
        {"id": 2, "role": "input", "name": "Username", "automation_id": "txtUser", "enabled": True},
        {"id": 3, "role": "button", "name": "Submit", "automation_id": "btnSubmit", "enabled": True},
    ]
    dashboard.update_vision(elements=sample_elements)
    dashboard.update_stage("Web Form Automation", current_step=2, max_steps=5)
    dashboard.update_planned_action("type", {"selector": "#txtUser", "text": "neo_agent"}, thought="Filling username")
    dashboard.append_log("Typed username 'neo_agent' into #txtUser", level="SUCCESS")

    try:
        while dashboard._running:
            time.sleep(0.5)
    except KeyboardInterrupt:
        dashboard.close()


if __name__ == "__main__":
    main()
