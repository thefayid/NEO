"""
neo.ui — User Interface, Dashboard Command Center, Confirmation Gates, and Triggers.
"""
from neo.ui.confirmation_dialog import show_confirmation_popup
from neo.ui.dashboard import NeoDashboard
from neo.ui.triggers import GlobalHotkeyManager, VoiceTrigger

__all__ = [
    "NeoDashboard",
    "GlobalHotkeyManager",
    "VoiceTrigger",
    "show_confirmation_popup",
]
