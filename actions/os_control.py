"""
actions/os_control.py — Direct Native OS & Shell Automation Tool for NEO.

Provides sub-millisecond, deterministic system execution:
- Snap active windows to left/right halves, quadrants, or center without mouse dragging.
- Tile top two applications 50/50 side-by-side.
- Zero-drift window focus and list active windows.
- Kill hung processes by name or PID.
- Inspect or kill processes hogging network ports (e.g. 3000, 8080).
- Check real-time hardware health (CPU, RAM, Battery, Disk).
- Desktop file utilities (empty recycle bin, open Explorer path, create desktop folder).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict
from core.neo_os_automation import window_manager, resource_manager
from core.neo_win_orchestrator import win_orchestrator
from core import outcome

TOOL = {
    "name": "os_control",
    "description": (
        "Execute direct, sub-millisecond native OS actions with 100% precision without mouse clicks: "
        "snap windows (left/right/maximize/minimize/center), tile two windows side-by-side (50/50), "
        "focus a window by name, kill frozen processes by name or PID, inspect/kill port conflicts, "
        "open Windows settings directly via URI (wifi/bluetooth/sound/display/apps), switch power plans, "
        "navigate virtual desktops, check system health, empty recycle bin, or open file explorer."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "The action to execute: 'snap_window', 'tile_windows', 'list_windows', 'focus_window', "
                    "'close_window', 'kill_process', 'find_port', 'kill_port', 'system_health', "
                    "'empty_recycle_bin', 'open_explorer', 'create_desktop_folder', 'open_settings', "
                    "'power_plan', 'virtual_desktop', 'audio_devices'."
                ),
                "enum": [
                    "snap_window", "tile_windows", "list_windows", "focus_window", "close_window",
                    "kill_process", "find_port", "kill_port", "system_health", "empty_recycle_bin",
                    "open_explorer", "create_desktop_folder", "open_settings", "power_plan",
                    "virtual_desktop", "audio_devices"
                ]
            },
            "position": {
                "type": "STRING",
                "description": "For snap_window: 'left', 'right', 'top', 'bottom', 'top_left', 'top_right', 'bottom_left', 'bottom_right', 'center', 'maximize', 'minimize', 'restore'."
            },
            "mode": {
                "type": "STRING",
                "description": "For tile_windows: 'side_by_side' (default) or 'stacked'."
            },
            "target": {
                "type": "STRING",
                "description": "Window title, process name, or PID for focus_window, close_window, or kill_process."
            },
            "port": {
                "type": "INTEGER",
                "description": "Port number (e.g. 3000, 8080) for find_port or kill_port."
            },
            "path": {
                "type": "STRING",
                "description": "File or folder path for open_explorer."
            },
            "folder_name": {
                "type": "STRING",
                "description": "Folder name to create on Desktop for create_desktop_folder."
            },
            "page": {
                "type": "STRING",
                "description": "Settings page for open_settings: 'wifi', 'bluetooth', 'sound', 'display', 'battery', 'apps', 'storage', 'windows_update', 'clipboard'."
            },
            "plan": {
                "type": "STRING",
                "description": "Power plan for power_plan: 'high_performance', 'balanced', 'power_saver' (or omit to query)."
            },
            "desktop_action": {
                "type": "STRING",
                "description": "Virtual desktop action: 'next', 'prev', 'new', 'close'."
            }
        },
        "required": ["action"]
    }
}


def run(params: Dict[str, Any], player=None) -> str:
    action = (params.get("action") or "system_health").strip().lower()

    if action == "snap_window":
        pos = params.get("position") or "left"
        ok = window_manager.snap_active_window(pos)
        if ok:
            return outcome.done("os_control", snapped=pos, message=f"Snapped active window to {pos}.")
        return outcome.failed("os_control", f"Could not snap window to '{pos}'.")

    elif action == "tile_windows":
        mode = params.get("mode") or "side_by_side"
        ok = window_manager.tile_two_windows(mode)
        if ok:
            return outcome.done("os_control", tiled=mode, message=f"Tiled top two application windows {mode} (50/50).")
        return outcome.failed("os_control", "Could not tile windows. Ensure at least two application windows are open.")

    elif action == "list_windows":
        windows = window_manager.list_windows(only_visible=True)
        summary = [f"{w['title']} ({w['process_name']})" for w in windows[:10]]
        return outcome.done("os_control", count=len(windows), windows=summary)

    elif action == "focus_window":
        target = params.get("target") or ""
        if not target:
            return outcome.failed("os_control", "No window title or process specified.")
        ok = window_manager.focus_window(target)
        if ok:
            return outcome.done("os_control", focused=target, message=f"Focused window '{target}'.")
        return outcome.failed("os_control", f"Window '{target}' not found.")

    elif action == "close_window":
        target = params.get("target") or ""
        if not target:
            return outcome.failed("os_control", "No window title or process specified.")
        ok = window_manager.close_window(target)
        if ok:
            return outcome.done("os_control", closed=target, message=f"Sent close signal to '{target}'.")
        return outcome.failed("os_control", f"Window '{target}' not found.")

    elif action == "kill_process":
        target = params.get("target") or ""
        if not target:
            return outcome.failed("os_control", "No process name or PID specified.")
        res = resource_manager.kill_process(target, force=True)
        if res.get("success"):
            return outcome.done("os_control", killed=res.get("killed"), message=res.get("message"))
        return outcome.failed("os_control", res.get("message") or f"Could not kill process '{target}'.")

    elif action == "find_port":
        port = params.get("port")
        if not port:
            return outcome.failed("os_control", "No port number provided.")
        info = resource_manager.find_process_by_port(int(port))
        if info:
            return outcome.done("os_control", port=port, pid=info.get("pid"), process=info.get("name"), status=info.get("status"))
        return outcome.done("os_control", port=port, listening=False, message=f"Port {port} is completely free.")

    elif action == "kill_port":
        port = params.get("port")
        if not port:
            return outcome.failed("os_control", "No port number provided.")
        ok = resource_manager.kill_process_by_port(int(port))
        if ok:
            return outcome.done("os_control", port=port, freed=True, message=f"Killed process holding port {port}.")
        return outcome.failed("os_control", f"No active process found listening on port {port}.")

    elif action == "system_health":
        health = resource_manager.get_health()
        return outcome.done(
            "os_control",
            cpu=f"{health['cpu_percent']}%",
            memory=f"{health['memory_percent']}% ({health['memory_used_gb']}/{health['memory_total_gb']} GB)",
            disk_free=f"{health['disk_free_gb']} GB",
            battery=f"{health['battery_percent']}%" if health['battery_percent'] is not None else "AC Power"
        )

    elif action == "empty_recycle_bin":
        ok = resource_manager.empty_recycle_bin()
        return outcome.done("os_control", emptied=ok, message="Recycle Bin emptied successfully.")

    elif action == "open_explorer":
        path_str = params.get("path") or str(Path.home())
        ok = resource_manager.open_explorer_path(path_str)
        if ok:
            return outcome.done("os_control", opened=path_str, message=f"Opened File Explorer at '{path_str}'.")
        return outcome.failed("os_control", f"Path does not exist: '{path_str}'.")

    elif action == "create_desktop_folder":
        folder_name = params.get("folder_name") or "New Folder"
        created = resource_manager.create_desktop_folder(folder_name)
        return outcome.done("os_control", created_path=created, message=f"Created folder '{folder_name}' on Desktop.")

    elif action == "open_settings":
        page = params.get("page") or "wifi"
        ok, msg = win_orchestrator.open_settings_page(page)
        if ok:
            return outcome.done("os_control", page=page, message=msg)
        return outcome.failed("os_control", msg)

    elif action == "power_plan":
        plan = params.get("plan")
        if plan:
            ok, msg = win_orchestrator.set_power_scheme(plan)
            if ok:
                return outcome.done("os_control", plan=plan, message=msg)
            return outcome.failed("os_control", msg)
        current = win_orchestrator.get_active_power_scheme()
        return outcome.done("os_control", active_plan=current, message=f"Active Windows power plan is '{current}'.")

    elif action == "virtual_desktop":
        d_act = params.get("desktop_action") or "next"
        ok, msg = win_orchestrator.virtual_desktop(d_act)
        if ok:
            return outcome.done("os_control", desktop_action=d_act, message=msg)
        return outcome.failed("os_control", msg)

    elif action == "audio_devices":
        endpoints = win_orchestrator.list_audio_endpoints()
        summary = [f"#{e['index']}: {e['name']} ({e['inputs']} in, {e['outputs']} out)" for e in endpoints[:10]]
        return outcome.done("os_control", count=len(endpoints), devices=summary)

    return outcome.failed("os_control", f"Unknown action '{action}'.")
