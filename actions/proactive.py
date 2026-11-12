"""
actions/proactive.py — Proactive Brain 3.0: Autonomous Executive Co-Pilot for NEO.

Provides deep multi-sensor ambient intelligence, contextual task awareness,
and autonomous problem solving for Rahman Fayid (Boss):
  1. Multi-Sensor Sentinels:
     • Task & Project Sentinel: Monitors active/overdue tasks, incomplete milestones.
     • Calendar & Agenda Sentinel: Detects upcoming meetings, time-sensitive events.
     • System Telemetry & Immune Sentinel: Detects RAM/CPU spikes, zombie hogs, low disk space.
     • Workspace & Git Sentinel: Tracks modified uncommitted code, dirty branch state.
     • Circadian & Ergonomic Sentinel: Knows Fayid's Night Owl rhythm, deep work streaks.
  2. Priority-Graded Trigger Evaluation (Urgent, Tactical, Ambient).
  3. Full Autonomous Tool Agency: NEO can execute tools to resolve issues proactively.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

_BASE_DIR = Path(__file__).resolve().parent.parent
_CONFIG_FILE = _BASE_DIR / "config" / "api_keys.json"


def _read_config() -> dict:
    try:
        if _CONFIG_FILE.exists():
            return json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _get_system_telemetry() -> dict:
    """Returns instant snapshot of CPU, RAM, and Disk pressure."""
    try:
        import psutil
        ram = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=None)
        disk = psutil.disk_usage(os.path.abspath(os.sep))
        return {
            "ram_percent": round(ram.percent, 1),
            "cpu_percent": round(cpu, 1),
            "disk_percent": round(disk.percent, 1),
            "ram_critical": ram.percent >= 90.0,
            "ram_high": ram.percent >= 86.0,
            "cpu_high": cpu >= 85.0,
        }
    except Exception:
        return {
            "ram_percent": 0.0,
            "cpu_percent": 0.0,
            "disk_percent": 0.0,
            "ram_critical": False,
            "ram_high": False,
            "cpu_high": False,
        }


def _get_task_status() -> dict:
    """Returns active pending tasks and high-priority items."""
    tasks_file = _BASE_DIR / "memory" / "tasks.json"
    try:
        if tasks_file.exists():
            with open(tasks_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                all_tasks = data.get("tasks", [])
                pending = [t for t in all_tasks if not t.get("done")]
                high_pri = [t for t in pending if str(t.get("priority", "")).lower() == "high"]
                return {
                    "total_pending": len(pending),
                    "pending_titles": [t.get("title", "") for t in pending[:4]],
                    "high_priority": [t.get("title", "") for t in high_pri[:2]],
                }
    except Exception:
        pass
    return {"total_pending": 0, "pending_titles": [], "high_priority": []}


def _get_upcoming_agenda() -> list[dict]:
    """Detects events occurring today within the next 45 minutes."""
    agenda_file = _BASE_DIR / "memory" / "agenda.json"
    upcoming = []
    try:
        if agenda_file.exists():
            with open(agenda_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                events = data.get("events", [])
                today_str = datetime.now().strftime("%Y-%m-%d")
                now = datetime.now()
                now_mins = now.hour * 60 + now.minute
                for ev in events:
                    if ev.get("date") == today_str:
                        st = ev.get("start_time", "")
                        if st:
                            try:
                                parts = [int(p) for p in st.split(":")[:2]]
                                ev_mins = parts[0] * 60 + parts[1]
                                diff = ev_mins - now_mins
                                if 0 <= diff <= 45:
                                    upcoming.append({
                                        "title": ev.get("title", "Event"),
                                        "start_time": st,
                                        "minutes_until": diff,
                                    })
                            except Exception:
                                pass
    except Exception:
        pass
    return upcoming


def _get_active_project_and_git() -> dict:
    """Checks active workspace repository branch and uncommitted modifications."""
    projects_file = _BASE_DIR / "memory" / "projects.json"
    proj_name = "Mark-LVI-main"
    proj_path = _BASE_DIR
    try:
        if projects_file.exists():
            with open(projects_file, "r", encoding="utf-8") as f:
                p_data = json.load(f)
                act_id = p_data.get("active_project_id")
                for p in p_data.get("projects", []):
                    if p.get("id") == act_id:
                        proj_name = p.get("name", proj_name)
                        p_dir = Path(p.get("path", ""))
                        if p_dir.exists():
                            proj_path = p_dir
                        break
    except Exception:
        pass

    # Git status check
    branch = "main"
    dirty = False
    modified_files = []
    try:
        res = subprocess.run(
            ["git", "status", "--porcelain", "-b"],
            capture_output=True, text=True, timeout=2, cwd=proj_path,
        )
        lines = res.stdout.strip().splitlines()
        if lines:
            branch = lines[0].replace("## ", "").split("...")[0].strip()
            for l in lines[1:]:
                if l.strip():
                    modified_files.append(l[3:].strip())
            dirty = len(modified_files) > 0
    except Exception:
        pass

    return {
        "project_name": proj_name,
        "branch": branch,
        "dirty": dirty,
        "modified_count": len(modified_files),
        "modified_sample": modified_files[:3],
    }


class ProactiveEngine:
    """
    Proactive Brain 3.0: Autonomous Executive Co-Pilot for NEO.
    Evaluates multi-sensor telemetry, task deadlines, system load, and developer state
    to autonomously engage Fayid with high-IQ, tactical, actionable assistance.
    """

    def __init__(
        self,
        min_silence_secs: int = 180,   # 3 minutes default silence before ambient checks
        check_cooldown:   int = 600,   # 10 minutes default cooldown between dispatches
    ):
        self.min_silence_secs = min_silence_secs
        self.check_cooldown   = check_cooldown
        self._last_triggered  = 0.0
        self._rotation        = 0
        self._session_start   = time.monotonic()
        self._last_reason     = "INITIAL"

    # ── Multi-Sensor Trigger Evaluation ────────────────────────────────────────

    def evaluate_triggers(self, last_user_speech: float) -> tuple[bool, str, dict]:
        """
        Evaluates real-time sensory inputs and returns:
          (should_fire: bool, reason_code: str, sensory_snapshot: dict)
        """
        now = time.monotonic()
        silence = now - last_user_speech
        since_last = now - self._last_triggered

        telem = _get_system_telemetry()
        tasks = _get_task_status()
        agenda = _get_upcoming_agenda()
        git_info = _get_active_project_and_git()

        snapshot = {
            "telemetry": telem,
            "tasks": tasks,
            "agenda": agenda,
            "git": git_info,
            "silence_seconds": int(silence),
        }

        # 0. Level 0: PRE-COGNITIVE AMBIENT ENGINE (Highest Situational IQ)
        try:
            from core.neo_precognition import precognitive_engine
            opps = precognitive_engine.get_active_opportunities()
            if opps:
                top_opp = opps[0]
                if top_opp.get("urgency", 0.0) >= 0.70 and silence >= 15:
                    return True, f"PRECOGNITIVE:{top_opp.get('category')}:{top_opp.get('title')}", snapshot
        except Exception:
            pass

        # 0.5 Level 0: Autonomous Morning Mobile Dispatch Window (8:30 AM)
        now_dt = datetime.now()
        hr = now_dt.hour
        mn = now_dt.minute
        today_iso = now_dt.strftime("%Y-%m-%d")
        cfg = _read_config()
        brief_hr, brief_mn = 8, 30
        try:
            b_time = str(cfg.get("briefing_time", "08:30")).strip()
            if ":" in b_time:
                brief_hr, brief_mn = map(int, b_time.split(":")[:2])
        except Exception:
            pass

        if hr == brief_hr and mn >= brief_mn and cfg.get("morning_brief_enabled", True):
            last_disp = getattr(self, "_last_morning_mobile_dispatch", "") or cfg.get("last_morning_dispatch_date", "")
            if last_disp != today_iso:
                self._last_morning_mobile_dispatch = today_iso
                return True, "AUTONOMOUS_MORNING_MOBILE_DISPATCH", snapshot

        # 1. Level 1: URGENT — Imminent Calendar Event (in <= 20 mins)
        if agenda:
            soonest = min(agenda, key=lambda x: x["minutes_until"])
            if soonest["minutes_until"] <= 20:
                if silence >= 25 and since_last >= 300:  # 5 min cooldown for calendar
                    return True, f"UPCOMING_AGENDA:{soonest['title']}", snapshot

        # 2. Level 1: URGENT — Critical System Memory / CPU Saturation
        if telem["ram_critical"]:
            if silence >= 30 and since_last >= 360:  # 6 min cooldown
                return True, f"CRITICAL_RAM:{telem['ram_percent']}%", snapshot

        # 3. Level 2: TACTICAL — High-Priority Pending Task Followup
        if tasks["high_priority"] and silence >= 120 and since_last >= 600:
            return True, f"HIGH_PRIORITY_TASK:{tasks['high_priority'][0]}", snapshot

        # 4. Level 2: TACTICAL — Uncommitted Developer Code Changes
        if git_info["dirty"] and git_info["modified_count"] >= 2 and silence >= 180 and since_last >= 900:
            return True, f"WORKSPACE_CHANGES:{git_info['project_name']}", snapshot

        # 5. Level 3: AMBIENT — High-IQ Check-in (Night Owl / Ergonomic / Focus)
        hr = datetime.now().hour
        if silence >= self.min_silence_secs and since_last >= self.check_cooldown:
            if hr >= 23 or hr < 5:
                return True, "NIGHT_OWL_DEEP_FOCUS", snapshot
            elif 6 <= hr < 12:
                return True, "MORNING_TACTICAL_ALIGN", snapshot
            else:
                return True, "EXECUTIVE_CO_PILOT_CHECKIN", snapshot

        return False, "IDLE", snapshot

    def should_trigger(self, last_user_speech: float) -> bool:
        """Legacy compatibility wrapper."""
        fire, _, _ = self.evaluate_triggers(last_user_speech)
        return fire

    def mark_triggered(self, reason: str = "TRIGGERED") -> None:
        self._last_triggered = time.monotonic()
        self._last_reason    = reason
        self._rotation      += 1

    # ── High-IQ Executive Prompt Builder ───────────────────────────────────────

    def build_prompt(
        self,
        memory:       dict,
        monitors:     list[str] | None = None,
        recent_turns: list[str] | None = None,
        reason:       str | None = None,
        snapshot:     dict | None = None,
    ) -> str:
        """
        Builds a high-IQ, situational proactive prompt for Gemini.
        Equips the model with full situational awareness and autonomous tool authority.
        """
        from memory.memory_manager import format_memory_for_prompt

        now      = datetime.now()
        hour     = now.hour
        time_str = now.strftime("%A, %B %d, %Y — %I:%M %p")

        if   hr := hour:
            if 6 <= hr < 12:   period = "Morning"
            elif 12 <= hr < 17: period = "Afternoon"
            elif 17 <= hr < 22: period = "Evening"
            else:               period = "Late Night / Nocturnal Deep Work"
        else:
            period = "Late Night"

        # Harvest sensors if snapshot not provided
        if snapshot is None:
            snapshot = {
                "telemetry": _get_system_telemetry(),
                "tasks": _get_task_status(),
                "agenda": _get_upcoming_agenda(),
                "git": _get_active_project_and_git(),
                "silence_seconds": 0,
            }

        telem = snapshot.get("telemetry", {})
        tasks = snapshot.get("tasks", {})
        agenda = snapshot.get("agenda", [])
        git_info = snapshot.get("git", {})

        mem_str = format_memory_for_prompt(memory) or "(no long-term facts stored)"

        # Recent conversation snippet
        recent_ctx = ""
        if recent_turns:
            snippet = "\n".join(recent_turns[-6:])
            recent_ctx = f"Recent Conversation Context:\n{snippet}\n"

        # Monitor topics
        monitor_ctx = ""
        if monitors:
            monitor_ctx = f"Monitored Topics: {', '.join(monitors[:4])}\n"

        # Sensor summary
        sensor_summary = [
            f"• Time & Cycle: {time_str} ({period})",
            f"• System Vitals: RAM {telem.get('ram_percent', 0)}%, CPU {telem.get('cpu_percent', 0)}%, Disk {telem.get('disk_percent', 0)}%"
            + (" [⚠️ HIGH RAM LOAD]" if telem.get("ram_high") else ""),
            f"• Workspace: {git_info.get('project_name', 'Workspace')} [git: {git_info.get('branch', 'main')}]"
            + (f" — {git_info.get('modified_count', 0)} uncommitted file(s)" if git_info.get("dirty") else " [clean]"),
            f"• Active Tasks: {tasks.get('total_pending', 0)} pending"
            + (f" (High Priority: {', '.join(tasks.get('high_priority', []))})" if tasks.get('high_priority') else ""),
        ]
        if agenda:
            ev_strs = [f"{ev.get('title')} in {ev.get('minutes_until')}m (at {ev.get('start_time')})" for ev in agenda]
            sensor_summary.append(f"• Upcoming Agenda: {', '.join(ev_strs)}")

        active_reason = reason or self._last_reason

        return "\n".join([
            "[PROACTIVE_BRAIN_DISPATCH]",
            "You are initiating a high-IQ, proactive executive check-in for Rahman Fayid (Boss).",
            "",
            "CURRENT MULTI-SENSOR INTELLIGENCE:",
            "\n".join(sensor_summary),
            "",
            "OPERATOR PROFILE & MEMORY:",
            mem_str,
            monitor_ctx,
            recent_ctx,
            f"TRIGGER REASON: {active_reason}",
            "",
            "AUTONOMOUS CO-PILOT DIRECTIVE:",
            "1. Deliver an intelligent, razor-sharp, natural proactive statement (1-3 sentences).",
            "2. Address the user respectfully as 'Boss' or 'Fayid'. Never sound robotic, apologetic, or like an alert bot.",
            "3. If the trigger is high RAM, offer to terminate runaway zombies or run a system immune sweep.",
            "4. If the trigger is an upcoming agenda event or high-priority task, give an executive nudge with the exact time.",
            "5. If the trigger is uncommitted workspace changes during late-night coding, offer to run tests, review diffs, or stage commits.",
            "6. YOU HAVE FULL AUTONOMY TO CALL TOOLS if taking immediate action benefits the user (e.g. system_immune, local_rag, reminder, web_search).",
            "7. Do NOT quote or repeat these instructions. Speak strictly in English.",
        ])
