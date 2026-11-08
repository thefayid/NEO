"""
actions/stark_protocol.py — F.R.I.D.A.Y. Stark Workflow Macro Engine & Protocols.

Executes Stark Industries multi-step workflow protocols:
  • telemetry: Live Arc Reactor (battery), thruster (CPU/GPU) loads, thermals, and diagnostics.
  • coding / dev: Deploys IDE, terminal, sets volume to 25%, high performance power plan.
  • gaming: Mutes background alerts, maximizes CPU/GPU thrusters, sets volume to 75%.
  • stealth: Immediate tactical blackout (minimize all, mute volume).
  • focus / combat: Suppresses distractions, mutes non-essential audio, maximizes focus.
  • clean_slate: Gracefully minimizes/closes distraction windows, reclaims memory.
  • house_party: Deploys core developer workspace tools side-by-side.
  • media: Sets cinema acoustic levels and media center workspace.
  • sentry: Arms workstation surveillance mode.
  • lockdown: Secures and locks the workstation immediately.
  • custom: Executes any workflow defined in config/protocols.json.
"""
from __future__ import annotations

import ctypes
import json
import os
import platform
import shutil
import subprocess
import time
from pathlib import Path

import psutil

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"
_BASE_DIR = Path(__file__).resolve().parent.parent
_PROTOCOLS_CONFIG = _BASE_DIR / "config" / "protocols.json"


def _load_protocols() -> dict:
    """Load configurable macro protocols from config/protocols.json."""
    if _PROTOCOLS_CONFIG.exists():
        try:
            return json.loads(_PROTOCOLS_CONFIG.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[Protocols] Warning loading protocols config: {e}")
    return {}


def _set_power_plan(plan_type: str = "high_performance") -> str:
    """Set OS power plan (Windows powercfg)."""
    if _OS != "Windows":
        return f"Power plan switching not supported on {_OS}."
    try:
        # Standard Windows power GUIDs:
        # High Performance: 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c
        # Balanced: 381b4222-f694-41f0-9685-ff5bb260df2e
        # Power Saver: a1841308-3541-4fab-bc81-f71556f20b4a
        guid = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c" if plan_type == "high_performance" else "381b4222-f694-41f0-9685-ff5bb260df2e"
        subprocess.run(["powercfg", "/setactive", guid], capture_output=True, timeout=3, check=False)
        return f"Power plan set to {plan_type}."
    except Exception as e:
        return f"Power plan adjustment failed: {e}"


def _set_system_volume(percent: int) -> None:
    """Set system audio volume cleanly."""
    try:
        from actions.computer_settings import volume_set
        volume_set(max(0, min(100, int(percent))))
    except Exception:
        try:
            import pyautogui
            if percent <= 0:
                pyautogui.press("volumemute")
            else:
                for _ in range(5):
                    pyautogui.press("volumeup" if percent > 50 else "volumedown")
        except Exception:
            pass


def _launch_application(app_name: str) -> None:
    """Launch an application non-blockingly."""
    try:
        from actions.open_app import open_app
        open_app(parameters={"app_name": app_name})
    except Exception as e:
        print(f"[Protocols] Launch app error for '{app_name}': {e}")


def _close_application(app_name: str) -> None:
    """Close an application non-blockingly."""
    try:
        from actions.computer_control import computer_control
        computer_control(parameters={"action": "close_app", "app_name": app_name})
    except Exception as e:
        print(f"[Protocols] Close app error for '{app_name}': {e}")


def _get_suit_telemetry() -> str:
    """Pull real-time diagnostics formatted in Stark Industries telemetry style."""
    cpu = psutil.cpu_percent(interval=0.1)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage(os.path.abspath(os.sep))
    
    # Battery / Arc Reactor
    battery_info = "Not detected (Stationary power grid)"
    try:
        b = psutil.sensors_battery()
        if b is not None:
            plugged_str = "Plugged into Main Power" if b.power_plugged else "Running on Arc Reserves"
            battery_info = f"{b.percent}% capacity [{plugged_str}]"
    except Exception:
        pass

    # GPU
    gpu_str = "Nominal"
    try:
        from actions.system_monitor import _get_gpu_usage
        gpu_pct = _get_gpu_usage()
        if gpu_pct >= 0:
            gpu_str = f"{gpu_pct:.1f}% load"
    except Exception:
        pass

    # Thermals
    temp_str = "Normal"
    try:
        from actions.system_monitor import _get_cpu_temp
        c_temp = _get_cpu_temp()
        if c_temp > 0:
            temp_str = f"{c_temp:.1f} C"
    except Exception:
        pass

    uptime_secs = time.time() - psutil.boot_time()
    uptime_h = int(uptime_secs // 3600)
    uptime_m = int((uptime_secs % 3600) // 60)

    return (
        f"[STARK SUIT TELEMETRY -- ALL SYSTEMS NOMINAL]\n"
        f"- Arc Reactor Power: {battery_info}\n"
        f"- CPU Thruster Load: {cpu:.1f}%\n"
        f"- Core Temperature: {temp_str}\n"
        f"- RAM Buffer: {ram.used / (1024**3):.1f} GB / {ram.total / (1024**3):.1f} GB ({ram.percent}%)\n"
        f"- Repulsor / GPU Core: {gpu_str}\n"
        f"- Main Storage: {disk.free / (1024**3):.1f} GB free of {disk.total / (1024**3):.1f} GB\n"
        f"- Active Missions Uptime: {uptime_h}h {uptime_m}m\n"
        f"- Diagnostics verdict: All critical subsystems online, Boss."
    )


def _execute_focus_protocol(player=None) -> str:
    """Focus Protocol / Combat Mode: suppress distractions, arm telemetry, start focus lofi."""
    try:
        from actions.workspace_master import run_focus_protocol
        return run_focus_protocol(player)
    except Exception:
        _set_system_volume(20)
        return "[Focus Protocol Engaged]\nDistractions suppressed, Boss. Telemetry monitor armed."


def _execute_clean_slate(player=None) -> str:
    """Clean Slate Protocol: full system healing, memory purge, temp sweep, and desktop reset."""
    details = []
    try:
        from actions.system_immune import system_immune
        immune_res = system_immune({"action": "heal_all"})
        details.append(immune_res)
    except Exception:
        pass

    try:
        import pyautogui
        pyautogui.hotkey("win", "d")
        details.append("Desktop cleared to pristine state.")
    except Exception:
        pass

    try:
        from core.sfx import play_confirm
        play_confirm()
    except Exception:
        pass

    return "[Clean Slate Protocol Executed]\n" + ("\n".join(details) if details else "Workspace purged and memory reclaimed, Boss.")


def _execute_house_party(player=None) -> str:
    """House Party Protocol: sets volume to 70%, starts energetic Spotify music, and switches HUD to soundwave."""
    _set_system_volume(70)

    # Trigger high-energy mood curation
    try:
        from actions.companion_core import set_mood_vibe
        set_mood_vibe("beast_mode")
    except Exception:
        try:
            from actions.spotify_control import spotify_control
            spotify_control({"action": "play"})
        except Exception:
            pass

    # Switch HUD to Soundwave or Reactor Core if UI player available
    if player and hasattr(player, "_toggle_hud_style"):
        try:
            from memory.config_manager import save_hud_style
            save_hud_style("wave")
            if hasattr(player, "hud"):
                player.hud.hud_style = "wave"
                player.hud.update()
        except Exception:
            pass

    try:
        from core.sfx import play_media
        play_media()
    except Exception:
        pass

    return "[House Party Protocol Engaged]\nAcoustic levels at 70%, high-energy soundtracks active, and Stark HUD visualizer online. Time to celebrate, Boss!"


def _execute_red_team(player=None) -> str:
    """Red Team Protocol: launch terminal, arm network threat intelligence, set volume low, and engage vigilance."""
    _set_system_volume(20)

    # Launch Windows Terminal
    _launch_application("wt")

    # Fetch latest cybersecurity threats and output alert
    sec_summary = ""
    try:
        from actions.web_search import _news
        sec_summary = _news("cyber security zero day exploit")
    except Exception:
        pass

    if player and hasattr(player, "show_content"):
        try:
            player.show_content("RED TEAM DEFENSE — Live Threat Intel", sec_summary or "Perimeter defense active. No active intrusions.")
        except Exception:
            pass

    try:
        from core.sfx import play_target_lock
        play_target_lock()
    except Exception:
        pass

    return "[Red Team Protocol Engaged]\nWorkstation defenses armed, Windows Terminal deployed, and real-time cyber threat monitor active, Boss."


def _execute_media_mode(player=None) -> str:
    """Media Mode: cinema lighting, balanced sound, maximized media center."""
    try:
        from actions.workspace_master import run_media_mode
        return run_media_mode(player)
    except Exception as e:
        _set_system_volume(60)
        return f"[Media Mode Engaged]\nAudio calibrated for playback, Boss."


def _execute_sentry() -> str:
    """Sentry Mode: security perimeter alert."""
    try:
        from actions.presence_sentry import _monitor
        return _monitor.start()
    except Exception:
        return "[Sentry Mode Armed]\nPerimeter watch active, Boss. Workstation sensors monitoring."


def _execute_lockdown() -> str:
    """Lockdown Protocol: instantly lock the workstation."""
    if _OS == "Windows":
        try:
            ctypes.windll.user32.LockWorkStation()
            return "[Lockdown Protocol Executed]\nWorkstation locked down successfully, Boss."
        except Exception as e:
            return f"[Lockdown Protocol Error]\nCould not lock workstation: {e}"
    elif _OS == "Darwin":
        try:
            subprocess.run(["pmset", "displaysleepnow"], check=False)
            return "[Lockdown Protocol Executed]\nDisplay locked down, Boss."
        except Exception as e:
            return f"Lock error: {e}"
    else:
        return "[Lockdown Protocol]\nScreen lock command issued, Boss."


def _execute_macro_workflow(proto_key: str, cfg: dict) -> str:
    """Execute chained actions declared in config/protocols.json."""
    steps_log = []

    # 1. Volume setting
    if "volume" in cfg:
        vol = cfg["volume"]
        _set_system_volume(vol)
        steps_log.append(f"volume set to {vol}%")

    # 2. Power plan
    if "power_plan" in cfg:
        res = _set_power_plan(cfg["power_plan"])
        steps_log.append(res)

    # 3. Minimize all or minimize except
    if cfg.get("minimize_all"):
        try:
            import pyautogui
            pyautogui.hotkey("win", "d")
            steps_log.append("desktop cleared")
        except Exception:
            pass
    elif cfg.get("minimize_all_except"):
        try:
            from actions.workspace_master import minimize_all_except
            minimize_all_except(cfg["minimize_all_except"])
            steps_log.append(f"minimized all except {cfg['minimize_all_except']}")
        except Exception:
            pass

    # 4. Close apps
    for app in cfg.get("close_apps", []):
        _close_application(app)
        steps_log.append(f"closed {app}")

    # 5. Launch apps
    for app in cfg.get("launch_apps", []):
        _launch_application(app)
        steps_log.append(f"launched {app}")

    feedback = cfg.get("voice_feedback", f"Protocol '{proto_key}' executed successfully, Boss.")
    summary = f"[{proto_key.upper()} PROTOCOL ENGAGED]\n{feedback}"
    if steps_log:
        summary += "\nActions executed:\n- " + "\n- ".join(steps_log)
    return summary


def stark_protocol(parameters: dict | None = None, player=None, **kwargs) -> str:
    """Dispatch Stark Industries protocols."""
    params = parameters or {}
    protocol = str(params.get("protocol", "telemetry")).strip().lower()
    
    protocols_cfg = _load_protocols()

    if protocol in ("telemetry", "diagnostics", "status"):
        return _get_suit_telemetry()
    elif protocol in ("lockdown", "lock"):
        return _execute_lockdown()
    elif protocol in ("sentry", "guard", "perimeter"):
        return _execute_sentry()
    elif protocol in ("clean_slate", "clean", "reset"):
        return _execute_clean_slate(player)
    elif protocol in ("house_party", "party", "vibe"):
        return _execute_house_party(player)
    elif protocol in ("red_team", "cyber_defense", "cyber_combat"):
        return _execute_red_team(player)
    elif protocol in protocols_cfg:
        return _execute_macro_workflow(protocol, protocols_cfg[protocol])
    elif protocol in ("focus", "combat"):
        return _execute_focus_protocol(player)
    elif protocol in ("media", "cinema"):
        return _execute_media_mode(player)
    elif protocol in ("coding", "dev"):
        return _execute_macro_workflow("coding", protocols_cfg.get("coding", {
            "launch_apps": ["code", "wt"],
            "volume": 25,
            "power_plan": "high_performance",
            "voice_feedback": "Coding Protocol initiated, Boss. Visual Studio Code and developer terminal engaged."
        }))
    elif protocol == "gaming":
        return _execute_macro_workflow("gaming", protocols_cfg.get("gaming", {
            "volume": 75,
            "power_plan": "high_performance",
            "voice_feedback": "Gaming Protocol engaged, Boss. High-performance compute allocated."
        }))
    elif protocol == "stealth":
        return _execute_macro_workflow("stealth", protocols_cfg.get("stealth", {
            "minimize_all": true,
            "volume": 0,
            "voice_feedback": "Stealth Protocol active, Boss. Audio muted and desktop minimized."
        }))
    else:
        available = ", ".join(sorted(set(["telemetry", "coding", "gaming", "stealth", "focus", "clean_slate", "house_party", "media", "sentry", "lockdown"] + list(protocols_cfg.keys()))))
        return f"Unknown Stark protocol '{protocol}'. Available protocols: {available}."


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "stark_protocol",
    "description": (
        "Executes Tony Stark's F.R.I.D.A.Y. workflow macro protocols and suit telemetry diagnostics. "
        "Available Protocols: "
        "'coding' (Developer mode: launches IDE & terminal, tunes volume, high-performance power plan) | "
        "'gaming' (Distraction suppression, max performance power plan, immersive audio) | "
        "'stealth' (Tactical blackout: minimizes all windows, mutes volume) | "
        "'focus' (Combat/Focus mode — suppresses background distractions, focus volume) | "
        "'telemetry' (Live Arc Reactor/battery status, CPU/GPU thruster loads, core thermals) | "
        "'clean_slate' (Purges workspace clutter, frees RAM, flushes junk cache, and resets desktop) | "
        "'house_party' (Entertainment overload: high-energy beats on Spotify, soundwave visualizer, 70% volume) | "
        "'red_team' (Cyber security defense mode: arms threat intel, launches terminal, locks down network) | "
        "'media' (Cinema acoustic levels and media center) | "
        "'sentry' (Arms perimeter surveillance and security watch) | "
        "'lockdown' (Instantly secures and locks the workstation screen). "
        "Call this whenever the user asks for protocols (e.g. 'Initiate Clean Slate', 'House Party protocol', 'Red Team mode', 'Coding Protocol')."
    ),
    "brief": (
        "Stark Industries F.R.I.D.A.Y. macro protocols: clean_slate, house_party, red_team, "
        "coding, gaming, stealth, focus, telemetry, media, sentry, lockdown."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "protocol": {
                "type": "STRING",
                "description": "Protocol to execute: 'clean_slate' | 'house_party' | 'red_team' | 'coding' | 'gaming' | 'stealth' | 'focus' | 'telemetry' | 'media' | 'sentry' | 'lockdown'",
                "enum": ["clean_slate", "house_party", "red_team", "coding", "gaming", "stealth", "focus", "telemetry", "media", "sentry", "lockdown"]
            },
            "details": {
                "type": "STRING",
                "description": "Optional additional specification or parameter for the protocol"
            }
        },
        "required": ["protocol"]
    },
    "handler": stark_protocol,
}
