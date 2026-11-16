"""
tests/test_emergency_stop.py — Tests for global emergency stop and shutdown.
"""
from __future__ import annotations

import platform
import time
import pytest

from neo.safety.emergency_stop import (
    EmergencyStop,
    EmergencyStopTriggeredError,
)


@pytest.fixture
def clean_stop() -> EmergencyStop:
    """Provides a fresh, non-triggered EmergencyStop instance for each test."""
    stop = EmergencyStop()
    yield stop
    stop.stop_hotkey_listener()


def test_initial_state(clean_stop: EmergencyStop):
    assert clean_stop.is_stopped() is False
    assert clean_stop.stop_reason == ""
    # check_stop should not raise when not stopped
    clean_stop.check_stop()


def test_trigger_sets_flag_and_raises(clean_stop: EmergencyStop):
    clean_stop.trigger(reason="Test abort triggered")
    assert clean_stop.is_stopped() is True
    assert "Test abort triggered" in clean_stop.stop_reason

    with pytest.raises(EmergencyStopTriggeredError, match="Test abort triggered"):
        clean_stop.check_stop()


def test_reset_rearms_system(clean_stop: EmergencyStop):
    clean_stop.trigger(reason="Temporary halt")
    assert clean_stop.is_stopped() is True

    clean_stop.reset()
    assert clean_stop.is_stopped() is False
    assert clean_stop.stop_reason == ""
    clean_stop.check_stop()  # Should not raise


def test_shutdown_hooks_execution_order(clean_stop: EmergencyStop):
    events = []

    def hook1():
        events.append("hook1")

    def hook2():
        events.append("hook2")

    clean_stop.register_shutdown_hook(hook1)
    clean_stop.register_shutdown_hook(hook2)

    clean_stop.trigger(reason="Testing hooks")

    # LIFO order
    assert events == ["hook2", "hook1"]


def test_shutdown_hook_error_resilience(clean_stop: EmergencyStop):
    events = []

    def failing_hook():
        events.append("failing")
        raise RuntimeError("Hook disaster")

    def normal_hook():
        events.append("normal")

    clean_stop.register_shutdown_hook(normal_hook)
    clean_stop.register_shutdown_hook(failing_hook)

    # Triggering should execute both even if one raises
    clean_stop.trigger(reason="Testing failure resilience")

    assert "failing" in events
    assert "normal" in events


def test_hotkey_listener_start_and_stop(clean_stop: EmergencyStop):
    if platform.system() != "Windows":
        pytest.skip("Windows only test for RegisterHotKey")

    started = clean_stop.start_hotkey_listener()
    assert started is True
    assert clean_stop._listener_running is True

    time.sleep(0.1)
    clean_stop.stop_hotkey_listener()
    assert clean_stop._listener_running is False
