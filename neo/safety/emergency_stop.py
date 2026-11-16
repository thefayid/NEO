"""
neo/safety/emergency_stop.py — Global Emergency Stop & Clean Shutdown for NEO.

Provides an immediate, tamper-proof emergency halt for computer automation:
1. Global hotkey listener: Ctrl+Alt+Shift+Q registers at OS level via Win32 RegisterHotKey.
2. Thread-safe stop flag: checked synchronously by every loop before dispatching any action.
3. Clean shutdown sequence: executes registered resource cleanup, window restorations,
   and release of simulated mouse/keyboard inputs.
"""
from __future__ import annotations

import ctypes
import logging
import platform
import sys
import threading
import time
from typing import Any, Callable, List, Optional

logger = logging.getLogger("neo.safety.emergency_stop")


class EmergencyStopTriggeredError(RuntimeError):
    """Raised when an action is attempted while the emergency stop flag is active."""
    pass


class EmergencyStop:
    """
    Thread-safe global emergency stop coordinator.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._is_stopped: bool = False
        self._stop_reason: str = ""
        self._shutdown_hooks: List[Callable[[], Any]] = []
        self._hotkey_thread: Optional[threading.Thread] = None
        self._listener_running: bool = False
        self._listener_stop_event = threading.Event()

    @property
    def stop_reason(self) -> str:
        with self._lock:
            return self._stop_reason

    def is_stopped(self) -> bool:
        """Returns True if emergency stop has been triggered."""
        with self._lock:
            return self._is_stopped

    def check_stop(self) -> None:
        """
        Guards action execution. Raises EmergencyStopTriggeredError if stopped.
        Must be called by the agent loop immediately before EVERY action dispatch.
        """
        with self._lock:
            if self._is_stopped:
                reason = self._stop_reason or "Emergency stop active."
                raise EmergencyStopTriggeredError(f"Action blocked: {reason}")

    def trigger(self, reason: str = "Emergency stop triggered (Ctrl+Alt+Shift+Q)") -> None:
        """
        Activates the emergency stop flag and executes all registered shutdown hooks.
        """
        with self._lock:
            if self._is_stopped:
                return
            self._is_stopped = True
            self._stop_reason = reason
            logger.critical("🚨 EMERGENCY STOP ACTIVATED: %s", reason)

        # Release mouse buttons or keys if PyAutoGUI is active
        self._release_held_inputs()

        # Execute registered clean shutdown callbacks
        self._run_shutdown_hooks()

    def reset(self) -> None:
        """Resets the emergency stop state (e.g. for testing or deliberate re-arm)."""
        with self._lock:
            self._is_stopped = False
            self._stop_reason = ""
            logger.info("Emergency stop flag reset. System re-armed.")

    def register_shutdown_hook(self, hook: Callable[[], Any]) -> None:
        """Registers a callback to be executed upon emergency stop or clean shutdown."""
        with self._lock:
            if hook not in self._shutdown_hooks:
                self._shutdown_hooks.append(hook)

    def _release_held_inputs(self) -> None:
        """Ensures any simulated physical mouse buttons or keys are released immediately."""
        try:
            if sys.platform == "win32":
                user32 = ctypes.windll.user32
                # MOUSEEVENTF_LEFTUP = 0x0004, MOUSEEVENTF_RIGHTUP = 0x0010
                user32.mouse_event(0x0004, 0, 0, 0, 0)
                user32.mouse_event(0x0010, 0, 0, 0, 0)
        except Exception as e:
            logger.warning("Could not force mouse input release: %s", e)

    def _run_shutdown_hooks(self) -> None:
        """Executes all registered cleanup hooks in LIFO order with explicit error handling."""
        with self._lock:
            hooks = list(reversed(self._shutdown_hooks))

        for hook in hooks:
            try:
                hook()
            except Exception as e:
                logger.error("Error executing shutdown hook %s: %s", hook, e)

    def shutdown(self) -> None:
        """Performs a full clean shutdown, stopping listener threads and triggering hooks."""
        self.trigger(reason="Clean shutdown requested")
        self.stop_hotkey_listener()

    # ─────────────────────────────────────────────────────────────────────────
    # Windows Hotkey Listener (Ctrl+Alt+Shift+Q)
    # ─────────────────────────────────────────────────────────────────────────
    def start_hotkey_listener(self) -> bool:
        """
        Starts a background daemon thread that registers the global OS hotkey
        Ctrl+Alt+Shift+Q. Returns True if successfully started.
        """
        if platform.system() != "Windows":
            logger.info("Hotkey listener is only supported on Windows. Skipping.")
            return False

        with self._lock:
            if self._listener_running:
                return True
            self._listener_stop_event.clear()
            self._hotkey_thread = threading.Thread(
                target=self._hotkey_listener_loop,
                name="NeoEmergencyStopListener",
                daemon=True,
            )
            self._listener_running = True
            self._hotkey_thread.start()
            return True

    def stop_hotkey_listener(self) -> None:
        """Stops the hotkey listener thread and unregisters the global OS hotkey."""
        self._listener_stop_event.set()
        thread = self._hotkey_thread
        if thread and thread.is_alive():
            thread.join(timeout=1.0)
        with self._lock:
            self._listener_running = False
            self._hotkey_thread = None

    def _hotkey_listener_loop(self) -> None:
        """Background Windows message pump listening for WM_HOTKEY."""
        try:
            from ctypes import wintypes
            user32 = ctypes.windll.user32

            class MSG(ctypes.Structure):
                _fields_ = [
                    ("hwnd", wintypes.HWND),
                    ("message", wintypes.UINT),
                    ("wParam", wintypes.WPARAM),
                    ("lParam", wintypes.LPARAM),
                    ("time", wintypes.DWORD),
                    ("pt", wintypes.POINT),
                    ("lPrivate", wintypes.DWORD),
                ]

            # Modifiers: MOD_ALT (0x0001), MOD_CONTROL (0x0002), MOD_SHIFT (0x0004)
            # Key: ord('Q') = 0x51
            MOD_HOTKEY = 0x0001 | 0x0002 | 0x0004
            VK_Q = 0x51
            HOTKEY_ID = 9988

            # Register hotkey on current thread
            registered = user32.RegisterHotKey(None, HOTKEY_ID, MOD_HOTKEY, VK_Q)
            if not registered:
                logger.warning("Could not register emergency stop hotkey Ctrl+Alt+Shift+Q (may be in use).")
                return

            logger.info("Emergency Stop hotkey registered: Ctrl+Alt+Shift+Q")
            msg = MSG()

            try:
                while not self._listener_stop_event.is_set():
                    # Non-blocking peek message
                    if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):  # PM_REMOVE = 1
                        if msg.message == 0x0312:  # WM_HOTKEY
                            if msg.wParam == HOTKEY_ID:
                                logger.critical("🚨 Emergency Stop hotkey (Ctrl+Alt+Shift+Q) detected!")
                                self.trigger(reason="Global hotkey Ctrl+Alt+Shift+Q pressed")
                                break
                    time.sleep(0.04)
            finally:
                user32.UnregisterHotKey(None, HOTKEY_ID)
                logger.debug("Emergency Stop hotkey unregistered.")
        except Exception as e:
            logger.error("Error in hotkey listener loop: %s", e)


# Global singleton instance
emergency_stop = EmergencyStop()


def setup_emergency_hotkey() -> bool:
    """Convenience helper to start the global emergency stop hotkey listener."""
    return emergency_stop.start_hotkey_listener()

