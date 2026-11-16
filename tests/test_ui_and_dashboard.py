"""
tests/test_ui_and_dashboard.py — Unit Tests for neo.ui Dashboard and Trigger Subsystems.
"""
from __future__ import annotations

import time
import pytest

from neo.safety.emergency_stop import EmergencyStopTriggeredError, emergency_stop
from neo.ui import GlobalHotkeyManager, NeoDashboard, VoiceTrigger


def test_global_hotkey_manager_registration():
    mgr = GlobalHotkeyManager()
    triggered = []

    def mock_cb():
        triggered.append(True)

    mgr.register_hotkey(1, 0x0002 | 0x0001, 0x53, mock_cb)
    assert 1 in mgr._callbacks
    mods, vk, cb = mgr._callbacks[1]
    assert vk == 0x53
    assert cb == mock_cb


def test_voice_trigger_mock_transcription():
    vt = VoiceTrigger()
    # Test instant mock transcription
    result = vt.record_and_transcribe(duration_s=0.1, mock_text="Open Notepad and write test")
    assert result == "Open Notepad and write test"


def test_voice_trigger_background_listener():
    vt = VoiceTrigger()
    received = []

    def callback(text: str):
        received.append(text)

    t = vt.listen_in_background(callback=callback, duration_s=0.1, mock_text="Calculate 15 + 27")
    t.join(timeout=2.0)

    assert len(received) == 1
    assert received[0] == "Calculate 15 + 27"


def test_dashboard_queue_and_state_updates():
    dashboard = NeoDashboard(title="Test Dashboard", enable_hotkeys=False)

    # Put state update calls into queue
    dashboard.update_stage("Processing", current_step=3, max_steps=10)
    dashboard.update_planned_action("click", {"target_id": 5}, thought="Clicking submit")
    dashboard.append_log("Test message", level="INFO")

    # Queue contains 3 deferred update callbacks
    assert dashboard._queue.qsize() == 3

    # Process queue
    dashboard._process_queue()
    assert dashboard._queue.empty()


def test_dashboard_approval_delegation():
    dashboard = NeoDashboard(enable_hotkeys=False)
    resolved_decision = []

    def mock_approval_callback(approved: bool):
        resolved_decision.append(approved)

    dashboard.request_approval("delete_file", "Dangerous action", mock_approval_callback)
    dashboard._process_queue()

    assert dashboard._pending_approval_cb == mock_approval_callback


def test_macos_confirmation_dialog_data_contract():
    from neo.safety.policy import RiskAssessment
    from neo.ui.confirmation_dialog import MacOSConfirmationDialog

    assessment = RiskAssessment(
        is_risky=True,
        requires_hard_stop=True,
        risk_categories=["delete", "filesystem"],
        matched_patterns=["format C:"],
        summary="High-risk destructive filesystem action",
    )
    dialog_ctrl = MacOSConfirmationDialog(
        action_name="shell_execute",
        assessment=assessment,
        timeout_sec=10.0,
    )
    assert dialog_ctrl.action_name == "shell_execute"
    assert dialog_ctrl.timeout_sec == 10.0
    assert dialog_ctrl.approved is False
    assert "DENY" in dialog_ctrl.reason
    assert dialog_ctrl.assessment.requires_hard_stop is True


def test_macos_dashboard_window_and_widgets():
    from PyQt6.QtWidgets import QApplication
    from neo.ui.dashboard import MacOSDashboardWindow

    app = QApplication.instance() or QApplication([])

    dashboard = NeoDashboard(title="NEO Autonomous Controller (macOS Test)", enable_hotkeys=False)
    win = MacOSDashboardWindow(dashboard)

    assert win.window.windowTitle() == "NEO Autonomous Controller (macOS Test)"
    assert win.traffic_lights is not None
    assert win.screenshot_canvas is not None
    assert win.element_tree is not None
    assert win.btn_approve is not None
    assert win.btn_deny is not None
    assert win.btn_stop is not None

    # Test status pill states
    win._update_status_pill("RUNNING")
    assert "RUNNING" in win.lbl_status.text()

    win._update_status_pill("AWAITING APPROVAL")
    assert "APPROVAL" in win.lbl_status.text()

    win._update_status_pill("STOPPED")
    assert "STOPPED" in win.lbl_status.text()

    # Test updating vision in window
    dashboard._window = win
    sample_elements = [
        {"id": 1, "role": "button", "name": "Submit", "automation_id": "btnSubmit", "enabled": True},
        {"id": 2, "role": "input", "name": "Email", "automation_id": "txtEmail", "enabled": True},
    ]
    dashboard.update_vision(elements=sample_elements)
    dashboard._process_queue()
    assert win.element_tree.topLevelItemCount() == 2

    # Test emergency stop button click
    dashboard._on_emergency_stop()
    assert dashboard.status == "STOPPED"
    assert "STOPPED" in win.lbl_status.text()
    emergency_stop.reset()

