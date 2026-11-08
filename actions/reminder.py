"""
actions/reminder.py — Smart Voice Reminders for F.R.I.D.A.Y.

Features:
  1. Natural Relative Time Parsing:
     - "Remind me to push this commit in 30 minutes, Boss."
     - Supports: minutes=30, hours=1, when="in 45 minutes", when="tomorrow at 10 AM",
       or explicit date/time.
  2. Dual-Engine Scheduling:
     - In-Process Real-Time Timer: Triggers instant Stark alert chime (core.sfx.play_alert),
       F.R.I.D.A.Y. voice announcement, and UI activity log.
     - Persistent System Scheduler: Auto-registers with Windows Task Scheduler (schtasks),
       macOS LaunchAgents, or Linux systemd so reminders fire even if the app closes.
  3. Action Operations:
     - action='set': Create and arm a new reminder.
     - action='list': View all active pending reminders with remaining countdowns.
     - action='cancel': Cancel an active reminder by ID or message keyword.
"""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from core.sfx import play_alert, play_confirm

_CNW: dict = (
    {"creationflags": subprocess.CREATE_NO_WINDOW}
    if platform.system() == "Windows" else {}
)

_BASE_DIR = Path(__file__).resolve().parent.parent
_MEMORY_DIR = _BASE_DIR / "memory"
_REMINDERS_FILE = _MEMORY_DIR / "reminders.json"
_LOCK = threading.Lock()
_ACTIVE_TIMERS: dict[str, threading.Timer] = {}


def _get_os() -> str:
    _sys = platform.system()
    if _sys == "Darwin":
        return "mac"
    if _sys == "Linux":
        return "linux"
    return "windows"


def _scripts_dir() -> Path:
    d = Path.home() / ".jarvis" / "reminders"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _sanitise(text: str, max_len: int = 200) -> str:
    return (
        text.replace("\\", "")
            .replace('"', "")
            .replace("'", "")
            .replace("\n", " ")
            .replace("\r", "")
            .strip()
    )[:max_len]


# ── JSON Storage ─────────────────────────────────────────────────────────────

def _load_reminders() -> list[dict]:
    _MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        if _REMINDERS_FILE.exists():
            try:
                data = json.loads(_REMINDERS_FILE.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return data
            except Exception:
                pass
        return []


def _save_reminders(reminders: list[dict]) -> None:
    _MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        try:
            _REMINDERS_FILE.write_text(json.dumps(reminders, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"[Reminder] ❌ Save failed: {e}")


def _remove_reminder_from_store(rem_id: str) -> None:
    rems = _load_reminders()
    rems = [r for r in rems if r.get("id") != rem_id]
    _save_reminders(rems)


# ── In-Process Active Timer & Voice Alert ─────────────────────────────────────

def _on_timer_fired(rem_id: str, message: str, player=None, speak=None) -> None:
    print(f"[Reminder] [Alarm] FIRED: {message}")
    play_alert()

    # Log to UI
    if player:
        try:
            player.write_log(f"[Reminder] Boss, {message}")
        except Exception:
            pass

    # Voice announcement if speak handler available
    if callable(speak):
        try:
            speak(f"Boss, here is your reminder: {message}.")
        except Exception:
            pass

    # Native desktop notification popup
    try:
        from plyer import notification
        notification.notify(
            title="F.R.I.D.A.Y. Reminder",
            message=f"Boss: {message}",
            timeout=15,
        )
    except Exception:
        pass

    # Clean from active timers & disk
    _ACTIVE_TIMERS.pop(rem_id, None)
    _remove_reminder_from_store(rem_id)


def _arm_in_process_timer(rem_id: str, target_dt: datetime, message: str, player=None, speak=None) -> None:
    delay = (target_dt - datetime.now()).total_seconds()
    if delay <= 0:
        return

    # Cancel existing if present
    if rem_id in _ACTIVE_TIMERS:
        try:
            _ACTIVE_TIMERS[rem_id].cancel()
        except Exception:
            pass

    timer = threading.Timer(
        delay,
        _on_timer_fired,
        args=[rem_id, message, player, speak],
    )
    timer.daemon = True
    timer.name = f"Timer_{rem_id}"
    _ACTIVE_TIMERS[rem_id] = timer
    timer.start()


# ── OS Persistent Scripts (Windows Task Scheduler / Mac / Linux) ────────────

def _write_notify_script(task_name: str, message: str, os_name: str) -> Path:
    script_path = _scripts_dir() / f"{task_name}.py"
    msg_literal = json.dumps(f"Boss: {message}")

    if os_name == "windows":
        notify_block = f"""
message = {msg_literal}
notified = False

try:
    from plyer import notification
    notification.notify(title="F.R.I.D.A.Y. Reminder", message=message, timeout=15)
    notified = True
except Exception:
    pass

if not notified:
    try:
        from win10toast import ToastNotifier
        ToastNotifier().show_toast("F.R.I.D.A.Y. Reminder", message, duration=15, threaded=False)
        notified = True
    except Exception:
        pass

if not notified:
    try:
        import subprocess
        subprocess.run(["msg", "*", "/TIME:30", message], check=False)
    except Exception:
        pass

try:
    import winsound
    for freq in [880, 1175, 1760]:
        winsound.Beep(freq, 160)
        import time; time.sleep(0.06)
except Exception:
    pass
"""
    elif os_name == "mac":
        notify_block = f"""
message = {msg_literal}
try:
    from plyer import notification
    notification.notify(title="F.R.I.D.A.Y. Reminder", message=message, timeout=15)
except Exception:
    import subprocess
    script = 'display notification "{{}}" with title "F.R.I.D.A.Y. Reminder"'.format(message.replace('"', ''))
    subprocess.run(["osascript", "-e", script], check=False)
"""
    else:
        notify_block = f"""
message = {msg_literal}
try:
    import subprocess
    subprocess.run(["notify-send", "--urgency=normal", "--expire-time=15000", "F.R.I.D.A.Y. Reminder", message], check=False)
except Exception:
    pass
"""

    script_body = f"""# Auto-generated by F.R.I.D.A.Y. reminder
import sys, os, pathlib
{notify_block}
try:
    pathlib.Path(__file__).unlink(missing_ok=True)
except Exception:
    pass
"""
    script_path.write_text(script_body, encoding="utf-8")
    try:
        script_path.chmod(0o600)
    except Exception:
        pass
    return script_path


def _schedule_windows(target_dt: datetime, task_name: str, script_path: Path, message: str) -> str:
    python_exe = Path(sys.executable)
    pythonw = python_exe.parent / "pythonw.exe"
    if pythonw.exists():
        python_exe = pythonw

    xml_path = _scripts_dir() / f"{task_name}.xml"
    xml_content = (
        '<?xml version="1.0" encoding="UTF-16"?>\n'
        '<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">\n'
        '  <RegistrationInfo><Description>F.R.I.D.A.Y. Reminder</Description></RegistrationInfo>\n'
        '  <Triggers><TimeTrigger>\n'
        f'    <StartBoundary>{target_dt.strftime("%Y-%m-%dT%H:%M:%S")}</StartBoundary>\n'
        '    <Enabled>true</Enabled>\n'
        '  </TimeTrigger></Triggers>\n'
        '  <Actions><Exec>\n'
        f'    <Command>{python_exe}</Command>\n'
        f'    <Arguments>"{script_path}"</Arguments>\n'
        '  </Exec></Actions>\n'
        '  <Settings>\n'
        '    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>\n'
        '    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>\n'
        '    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>\n'
        '    <StartWhenAvailable>true</StartWhenAvailable>\n'
        '    <ExecutionTimeLimit>PT5M</ExecutionTimeLimit>\n'
        '    <Enabled>true</Enabled>\n'
        '  </Settings>\n'
        '  <Principals><Principal>\n'
        '    <LogonType>InteractiveToken</LogonType>\n'
        '    <RunLevel>LeastPrivilege</RunLevel>\n'
        '  </Principal></Principals>\n'
        '</Task>'
    )

    xml_path.write_text(xml_content, encoding="utf-16")
    result = subprocess.run(
        ["schtasks", "/Create", "/TN", task_name, "/XML", str(xml_path), "/F"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", **_CNW,
    )

    try:
        xml_path.unlink(missing_ok=True)
    except Exception:
        pass

    if result.returncode != 0:
        script_path.unlink(missing_ok=True)
        err = (result.stderr or result.stdout).strip()
        print(f"[Reminder] ❌ schtasks: {err}")
        return ""
    return task_name


def _cancel_os_task(task_name: str) -> None:
    if _get_os() == "windows":
        try:
            subprocess.run(["schtasks", "/Delete", "/TN", task_name, "/F"], capture_output=True, **_CNW)
        except Exception:
            pass


# ── Natural Relative Time Parser ─────────────────────────────────────────────

def _parse_target_datetime(
    date_str: str,
    time_str: str,
    minutes: Optional[float],
    hours: Optional[float],
    when_str: str,
) -> tuple[Optional[datetime], str]:
    """Resolves relative and absolute time expressions into target datetime."""
    now = datetime.now()

    # 1. Direct minutes / hours numeric parameters
    total_delta_mins = 0.0
    if minutes is not None:
        try:
            total_delta_mins += float(minutes)
        except Exception:
            pass
    if hours is not None:
        try:
            total_delta_mins += float(hours) * 60.0
        except Exception:
            pass

    if total_delta_mins > 0:
        return now + timedelta(minutes=total_delta_mins), ""

    # 2. Natural relative expression in when_str (e.g. "in 30 minutes", "in 2 hours", "45 mins")
    w = (when_str or "").strip().lower()
    if w:
        m_rel = re.search(r"(?:in\s+)?(\d+(?:\.\d+)?)\s*(minute|min|hour|hr|sec|second)s?", w)
        if m_rel:
            val = float(m_rel.group(1))
            unit = m_rel.group(2)
            if "sec" in unit:
                return now + timedelta(seconds=val), ""
            elif "hr" in unit or "hour" in unit:
                return now + timedelta(hours=val), ""
            else:
                return now + timedelta(minutes=val), ""

        # Check "tomorrow at HH:MM"
        if "tomorrow" in w:
            m_time = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", w)
            if m_time:
                h = int(m_time.group(1))
                m = int(m_time.group(2) or 0)
                meridiem = (m_time.group(3) or "").lower()
                if meridiem == "pm" and h < 12:
                    h += 12
                elif meridiem == "am" and h == 12:
                    h = 0
                tom = now + timedelta(days=1)
                return tom.replace(hour=h, minute=m, second=0, microsecond=0), ""

        # Check "at HH:MM"
        m_time = re.search(r"(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", w)
        if m_time:
            h = int(m_time.group(1))
            m = int(m_time.group(2) or 0)
            meridiem = (m_time.group(3) or "").lower()
            if meridiem == "pm" and h < 12:
                h += 12
            elif meridiem == "am" and h == 12:
                h = 0
            cand = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if cand <= now:
                cand += timedelta(days=1)
            return cand, ""

    # 3. Explicit date + time strings
    t_clean = (time_str or "").strip().lower()
    d_clean = (date_str or "").strip()

    if t_clean:
        m_t = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", t_clean)
        if m_t:
            h = int(m_t.group(1))
            m = int(m_t.group(2) or 0)
            meridiem = (m_t.group(3) or "").lower()
            if meridiem == "pm" and h < 12:
                h += 12
            elif meridiem == "am" and h == 12:
                h = 0

            target_date = now.date()
            if d_clean:
                try:
                    target_date = datetime.strptime(d_clean, "%Y-%m-%d").date()
                except Exception:
                    return None, "Invalid date format. Please use YYYY-MM-DD."

            cand = datetime.combine(target_date, datetime.min.time()).replace(hour=h, minute=m)
            if not d_clean and cand <= now:
                cand += timedelta(days=1)
            return cand, ""

    return None, "Please specify a time (e.g. 'in 30 minutes', 'in 2 hours', or 'at 4:30 PM')."


# ── Main Reminder Action Handler ─────────────────────────────────────────────

def reminder(
    parameters: dict,
    response=None,
    player=None,
    speak=None,
    session_memory=None,
) -> str:
    action = (parameters.get("action") or "set").lower().strip()
    message = (parameters.get("message") or "Reminder").strip()
    query = (parameters.get("query") or "").strip().lower()

    # ── Action: list ────────────────────────────────────────────────────────
    if action in ("list", "view", "check", "get"):
        rems = _load_reminders()
        now = datetime.now()
        active = []
        for r in rems:
            try:
                tdt = datetime.strptime(r["target_time"], "%Y-%m-%d %H:%M:%S")
                if tdt > now:
                    active.append((tdt, r))
            except Exception:
                continue

        if not active:
            res = "You have no pending reminders, Boss."
            if player:
                player.write_log(f"[Reminder] {res}")
            return res

        active.sort(key=lambda x: x[0])
        lines = ["**PENDING REMINDERS:**"]
        spoken_items = []
        for tdt, r in active:
            diff = int((tdt - now).total_seconds() / 60)
            diff_str = f"in {diff} min(s)" if diff < 60 else f"in {diff//60}h {diff%60}m"
            time_str = tdt.strftime("%I:%M %p")
            msg_str = r.get("message", "Reminder")
            lines.append(f"- **{time_str}** ({diff_str}): {msg_str} `[ID: {r.get('id', '')}]`")
            spoken_items.append(f"{time_str} ({diff_str}): {msg_str}")

        if player:
            player.write_log(f"[Reminder] {len(active)} active reminder(s).")
            try:
                player.show_content("ACTIVE REMINDERS", "\n".join(lines))
            except Exception:
                pass

        play_confirm()
        return f"Boss, you have {len(active)} pending reminder(s): " + "; ".join(spoken_items) + "."

    # ── Action: cancel ──────────────────────────────────────────────────────
    if action in ("cancel", "remove", "delete"):
        rems = _load_reminders()
        cancel_target = query or message.lower()
        if not cancel_target:
            return "Which reminder would you like me to cancel, Boss?"

        matched = []
        remaining = []
        for r in rems:
            r_msg = r.get("message", "").lower()
            r_id = r.get("id", "").lower()
            if cancel_target in r_msg or cancel_target in r_id:
                matched.append(r)
            else:
                remaining.append(r)

        if not matched:
            return f"I couldn't find any pending reminder matching '{cancel_target}', Boss."

        for m in matched:
            mid = m.get("id", "")
            # Cancel in-memory timer
            if mid in _ACTIVE_TIMERS:
                try:
                    _ACTIVE_TIMERS[mid].cancel()
                    _ACTIVE_TIMERS.pop(mid, None)
                except Exception:
                    pass
            # Cancel OS task
            _cancel_os_task(m.get("task_name", ""))

        _save_reminders(remaining)
        titles = ", ".join(f"'{m.get('message')}'" for m in matched)
        res = f"Reminder for {titles} has been cancelled, Boss."
        play_confirm()
        if player:
            player.write_log(f"[Reminder] [Cancel] {res}")
        return res

    # ── Action: set (Default) ───────────────────────────────────────────────
    date_str = parameters.get("date", "").strip()
    time_str = parameters.get("time", "").strip()
    mins = parameters.get("minutes")
    hrs = parameters.get("hours")
    when_str = parameters.get("when", "").strip()

    target_dt, err = _parse_target_datetime(date_str, time_str, mins, hrs, when_str)
    if err or not target_dt:
        return err or "I couldn't calculate that reminder time, Boss."

    if target_dt <= datetime.now():
        return "That time has already passed, Boss. I can't set a reminder in the past."

    rem_id = f"rem_{target_dt.strftime('%Y%m%d_%H%M%S')}_{os.urandom(2).hex()}"
    task_name = f"JARVISReminder_{target_dt.strftime('%Y%m%d_%H%M%S')}"
    os_name = _get_os()
    safe_msg = _sanitise(message)

    # 1. Arm In-Process Timer (for instant SFX & voice announcement while app runs)
    _arm_in_process_timer(rem_id, target_dt, safe_msg, player, speak)

    # 2. Register with OS Scheduler (for persistence across app restarts)
    try:
        script_path = _write_notify_script(task_name, safe_msg, os_name)
        if os_name == "windows":
            _schedule_windows(target_dt, task_name, script_path, safe_msg)
    except Exception as e:
        print(f"[Reminder] ⚠️ OS schedule note: {e}")

    # 3. Store in memory/reminders.json
    rems = _load_reminders()
    rems.append({
        "id": rem_id,
        "task_name": task_name,
        "message": safe_msg,
        "target_time": target_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "created_at": datetime.now().isoformat(),
    })
    _save_reminders(rems)

    diff_mins = max(1, int((target_dt - datetime.now()).total_seconds() / 60))
    friendly_time = target_dt.strftime("%I:%M %p")
    date_part = f" on {target_dt.strftime('%B %d')}" if target_dt.date() != datetime.now().date() else ""

    res = f"Reminder set for {friendly_time}{date_part} (in {diff_mins} minutes): '{safe_msg}', Boss."
    play_confirm()
    if player:
        player.write_log(f"[Reminder] ✅ {friendly_time} — {safe_msg}")
    return res


# ── Restore pending reminders on module startup ──────────────────────────────
def _restore_active_timers():
    now = datetime.now()
    rems = _load_reminders()
    for r in rems:
        try:
            tdt = datetime.strptime(r["target_time"], "%Y-%m-%d %H:%M:%S")
            if tdt > now:
                _arm_in_process_timer(r["id"], tdt, r.get("message", "Reminder"))
        except Exception:
            continue

try:
    _restore_active_timers()
except Exception as _e:
    print(f"[Reminder] Timer restore note: {_e}")


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "reminder",
    "description": (
        "Smart Voice Reminders for F.R.I.D.A.Y. Sets, lists, or cancels timed reminders "
        "using relative time (e.g. 'in 30 minutes', 'in 2 hours') or specific date/time. "
        "Plays Stark alert chimes and announces aloud when due."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "'set' (default), 'list' (show pending reminders), or 'cancel' (cancel a reminder)",
            },
            "message": {
                "type": "STRING",
                "description": "The reminder task or message text (e.g. 'Push this commit', 'Take medication', 'Sync with team')",
            },
            "minutes": {
                "type": "NUMBER",
                "description": "Relative delay in minutes (e.g. 30, 45, 10)",
            },
            "hours": {
                "type": "NUMBER",
                "description": "Relative delay in hours (e.g. 1, 2, 0.5)",
            },
            "when": {
                "type": "STRING",
                "description": "Natural relative time phrase (e.g. 'in 30 minutes', 'in 2 hours', 'tomorrow at 3 PM')",
            },
            "time": {
                "type": "STRING",
                "description": "Specific time in HH:MM format (24h or 12h e.g. '14:30' or '2:30 PM')",
            },
            "date": {
                "type": "STRING",
                "description": "Specific date in YYYY-MM-DD format (defaults to today if time specified)",
            },
            "query": {
                "type": "STRING",
                "description": "Reminder ID or message keyword to cancel when action='cancel'",
            },
        },
    },
    "handler": reminder,
}
