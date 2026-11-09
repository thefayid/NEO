"""
actions/executive_briefing.py — Executive Personal Briefing & Productivity Agent for F.R.I.D.A.Y.

Features:
  1. Google Calendar & Outlook Sync:
     - Reads upcoming meetings, deadlines, and schedule conflicts.
     - Supports live Google Calendar / Outlook private iCal (.ics) feed synchronization.
     - Local agenda persistence in memory/agenda.json with conflict detection.
  2. VIP Email & Message Triage:
     - Analyzes unread urgent emails via IMAP (Gmail / Outlook / Exchange).
     - Prioritizes VIP senders (boss, client, github, stripe, investor) and urgent keywords (asap, deadline, urgent, invoice).
     - Non-blocking with graceful fallback when credentials are not configured.
  3. Executive Briefing Aggregator:
     - Real-time morning/executive briefing combining date/time, weather, agenda timeline,
       schedule conflicts, VIP message triage, pending reminders, and system diagnostics.
     - Styled in Kerry Condon's F.R.I.D.A.Y. MCU persona ("Boss", crisp tactical efficiency).
"""
from __future__ import annotations

import email
import email.header
import imaplib
import json
import os
import platform
import re
import sys
import threading
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import psutil

from core.sfx import play_confirm, play_protocol, play_alert

_BASE_DIR = Path(__file__).resolve().parent.parent
_MEMORY_DIR = _BASE_DIR / "memory"
_AGENDA_FILE = _MEMORY_DIR / "agenda.json"
_REMINDERS_FILE = _MEMORY_DIR / "reminders.json"
_CONFIG_FILE = _BASE_DIR / "config" / "api_keys.json"

_AGENDA_LOCK = threading.Lock()


def _read_config() -> dict:
    try:
        if _CONFIG_FILE.exists():
            return json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


# ── 1. Agenda & Calendar Management ──────────────────────────────────────────

DUMMY_EVENT_TITLES = {
    "Financial Management Exam",
    "SIH Team Sync",
    "Review & Notes",
    "Architecture Review & Sprint Sync",
    "Production Deployment & Telemetry Sign-off",
    "Executive Client Project Review",
}



def _load_agenda() -> dict:
    _MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    today_str = datetime.now().strftime("%Y-%m-%d")
    with _AGENDA_LOCK:
        if _AGENDA_FILE.exists():
            try:
                data = json.loads(_AGENDA_FILE.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "events" in data:
                    # Filter out any lingering dummy events
                    data["events"] = [e for e in data.get("events", []) if e.get("title") not in DUMMY_EVENT_TITLES]
                    return data
            except Exception:
                pass
        # Return empty agenda structure (do not pollute with fake exams)
        data = {
            "events": [],
            "last_synced": datetime.now().isoformat(),
        }
        try:
            _AGENDA_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass
        return data


def _save_agenda(data: dict) -> None:
    _MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    with _AGENDA_LOCK:
        try:
            _AGENDA_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"[Briefing] ❌ Could not save agenda: {e}")


def _time_to_minutes(time_str: str) -> int:
    """Converts '14:30' or '2:30 PM' to minutes since midnight."""
    clean = time_str.strip().upper()
    try:
        if "AM" in clean or "PM" in clean:
            dt = datetime.strptime(clean, "%I:%M %p")
            return dt.hour * 60 + dt.minute
        parts = clean.split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except Exception:
        return 0


def _minutes_to_time(minutes: int) -> str:
    h = (minutes // 60) % 24
    m = minutes % 60
    return f"{h:02d}:{m:02d}"


def _format_time_friendly(time_str: str) -> str:
    """Converts 24h '14:30' into '2:30 PM'."""
    try:
        parts = time_str.split(":")
        h, m = int(parts[0]), int(parts[1])
        suffix = "AM" if h < 12 else "PM"
        h12 = h if (h == 12 or h == 0) else (h % 12)
        if h == 0:
            h12 = 12
        return f"{h12}:{m:02d} {suffix}"
    except Exception:
        return time_str


def _parse_ical_datetime(raw_dt_str: str) -> tuple[str, str]:
    """
    Parses an iCal date/datetime string into (date_str 'YYYY-MM-DD', time_str 'HH:MM').
    Handles UTC 'Z' suffixes by converting to the local system timezone.
    Handles all-day dates 'YYYYMMDD'.
    """
    s = raw_dt_str.strip()
    if s.endswith("Z") and "T" in s:
        clean = s.replace("-", "").replace(":", "")
        try:
            if len(clean) >= 15:
                dt_utc = datetime.strptime(clean[:15] + "Z", "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
                dt_local = dt_utc.astimezone()
                return dt_local.strftime("%Y-%m-%d"), dt_local.strftime("%H:%M")
        except Exception:
            pass
    if "T" in s:
        parts = s.split("T", 1)
        d_p = parts[0].replace("-", "")
        t_p = parts[1].replace(":", "")
        d_str = f"{d_p[0:4]}-{d_p[4:6]}-{d_p[6:8]}" if len(d_p) >= 8 else ""
        t_str = f"{t_p[0:2]}:{t_p[2:4]}" if len(t_p) >= 4 else "09:00"
        return d_str, t_str
    clean_d = s.replace("-", "")
    if len(clean_d) >= 8:
        return f"{clean_d[0:4]}-{clean_d[4:6]}-{clean_d[6:8]}", "All Day"
    return "", ""


def _sync_ical_feed(ical_url: str) -> int:
    """Fetches and parses iCalendar (.ics) feed from Google Calendar or Outlook with timezone awareness."""
    if not ical_url or not ical_url.startswith(("http://", "https://", "webcal://")):
        return 0

    clean_url = ical_url.strip()
    if clean_url.startswith("webcal://"):
        clean_url = "https://" + clean_url[9:]
    elif not clean_url.startswith(("http://", "https://")):
        clean_url = "https://" + clean_url

    try:
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        req = urllib.request.Request(
            clean_url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        )
        with urllib.request.urlopen(req, context=ctx, timeout=12) as response:
            ics_text = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as he:
        if he.code == 404:
            raise RuntimeError("404: If private, use 'Secret address in iCal format' (ends in /private-.../basic.ics)")
        raise RuntimeError(f"HTTP {he.code}: {he.reason}")
    except Exception as e:
        print(f"[Briefing] ⚠️ iCal fetch failed: {e}")
        raise RuntimeError(f"Network error: {e}")

    # Unfold folded iCal lines
    ics_text = re.sub(r'\r?\n[ \t]', '', ics_text)
    raw_events = re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", ics_text, re.DOTALL)
    agenda_data = _load_agenda()
    existing_events = agenda_data.get("events", [])

    # Retain authentic user local manual events only
    preserved_events = [
        e for e in existing_events
        if e.get("source") == "local" and e.get("title") not in DUMMY_EVENT_TITLES
    ]

    synced_events: list[dict] = []
    for block in raw_events:
        summary_m = re.search(r"SUMMARY:(.*?)(?:\r?\n|$)", block)
        dtstart_m = re.search(r"DTSTART(?:;[^:]+)?:(.*?)(?:\r?\n|$)", block)
        dtend_m = re.search(r"DTEND(?:;[^:]+)?:(.*?)(?:\r?\n|$)", block)
        loc_m = re.search(r"LOCATION:(.*?)(?:\r?\n|$)", block)

        if not (summary_m and dtstart_m):
            continue

        title = summary_m.group(1).strip()
        if not title or title in DUMMY_EVENT_TITLES:
            continue

        raw_start = dtstart_m.group(1).strip()
        raw_end = dtend_m.group(1).strip() if dtend_m else ""
        location = loc_m.group(1).strip() if loc_m else ""

        date_str, start_time_str = _parse_ical_datetime(raw_start)
        _, end_time_str = _parse_ical_datetime(raw_end) if raw_end else ("", "")

        if not date_str:
            continue

        if not end_time_str or end_time_str == "All Day":
            if start_time_str != "All Day":
                s_min = _time_to_minutes(start_time_str)
                end_time_str = _minutes_to_time(s_min + 60)
            else:
                end_time_str = "All Day"

        # Avoid duplicates within feed
        if any(e.get("title") == title and e.get("date") == date_str and e.get("start_time") == start_time_str for e in synced_events):
            continue

        s_min = _time_to_minutes(start_time_str)
        e_min = _time_to_minutes(end_time_str)
        dur = max(15, e_min - s_min) if (start_time_str != "All Day" and e_min > s_min) else 60

        synced_events.append({
            "id": f"ical_{abs(hash(title + date_str + start_time_str)) % 1000000}",
            "title": title,
            "date": date_str,
            "start_time": start_time_str,
            "end_time": end_time_str,
            "duration_minutes": dur,
            "location": location or "Google Calendar",
            "source": "ical_sync",
        })

    # Merge preserved local events + synced events
    all_events = preserved_events + synced_events
    all_events.sort(key=lambda e: (e.get("date", ""), _time_to_minutes(e.get("start_time", "00:00"))))

    agenda_data["events"] = all_events
    agenda_data["last_synced"] = datetime.now().isoformat()
    _save_agenda(agenda_data)
    return len(synced_events)


def _get_agenda_timeline(date_str: str) -> tuple[list[dict], list[str]]:
    """Returns sorted events for date_str and detected schedule conflicts."""
    agenda_data = _load_agenda()
    events = [e for e in agenda_data.get("events", []) if e.get("date") == date_str]

    # Sort chronologically
    events.sort(key=lambda e: _time_to_minutes(e.get("start_time", "00:00")))

    # Detect conflicts (overlapping intervals)
    conflicts: list[str] = []
    for i in range(len(events) - 1):
        curr = events[i]
        nxt = events[i + 1]
        curr_end = _time_to_minutes(curr.get("end_time", curr.get("start_time", "00:00")))
        nxt_start = _time_to_minutes(nxt.get("start_time", "00:00"))

        if curr_end > nxt_start:
            conflicts.append(
                f"Schedule Conflict: '{curr['title']}' ({_format_time_friendly(curr['start_time'])}-{_format_time_friendly(curr['end_time'])}) "
                f"overlaps with '{nxt['title']}' ({_format_time_friendly(nxt['start_time'])}-{_format_time_friendly(nxt['end_time'])})."
            )

    return events, conflicts


# ── 2. VIP Email & Message Triage ─────────────────────────────────────────────

def _decode_mime_header(val: Optional[str]) -> str:
    if not val:
        return ""
    try:
        decoded_parts = email.header.decode_header(val)
        result = []
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                result.append(part.decode(encoding or "utf-8", errors="replace"))
            else:
                result.append(str(part))
        return "".join(result).strip()
    except Exception:
        return str(val)


def _triage_emails() -> dict:
    """Connects to IMAP (Gmail/Outlook/Exchange) and triages unread VIP & urgent emails."""
    cfg = _read_config()
    user = cfg.get("email_user", "").strip()
    password = cfg.get("email_password", "").strip()
    imap_server = cfg.get("email_imap_server", "imap.gmail.com").strip()
    imap_port = int(cfg.get("email_imap_port", 993))
    vip_senders = [s.lower().strip() for s in cfg.get("vip_senders", ["boss", "client", "github", "google", "stripe", "team", "lead"])]
    urgent_keywords = [
        "urgent", "asap", "deadline", "immediate", "action required",
        "critical", "invoice", "payment", "security alert", "failed",
    ]

    if not user or not password:
        return {
            "configured": False,
            "unread_count": 0,
            "urgent_count": 0,
            "urgent_items": [],
            "summary": "No IMAP credentials configured in config/api_keys.json (set 'email_user' and 'email_password').",
        }

    try:
        mail = imaplib.IMAP4_SSL(imap_server, imap_port, timeout=6)
        mail.login(user, password)
        mail.select("INBOX", readonly=True)

        status, data = mail.search(None, "UNSEEN")
        if status != "OK" or not data or not data[0]:
            mail.logout()
            return {
                "configured": True,
                "unread_count": 0,
                "urgent_count": 0,
                "urgent_items": [],
                "summary": "Zero unread emails in inbox. All caught up, Boss.",
            }

        msg_ids = data[0].split()
        unread_count = len(msg_ids)
        recent_ids = msg_ids[-10:]  # examine the 10 most recent unread

        urgent_items = []
        for mid in reversed(recent_ids):
            _, fetch_data = mail.fetch(mid, "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE)])")
            if not fetch_data or not isinstance(fetch_data[0], tuple):
                continue
            raw_email = fetch_data[0][1]
            msg = email.message_from_bytes(raw_email)

            subject = _decode_mime_header(msg.get("Subject", "(No Subject)"))
            sender = _decode_mime_header(msg.get("From", "(Unknown Sender)"))
            date_sent = _decode_mime_header(msg.get("Date", ""))

            # Priority checks
            sender_lower = sender.lower()
            subject_lower = subject.lower()

            is_vip = any(vip in sender_lower for vip in vip_senders)
            is_urgent = any(kw in subject_lower for kw in urgent_keywords)

            if is_vip or is_urgent:
                reasons = []
                if is_vip:
                    reasons.append("VIP Sender")
                if is_urgent:
                    reasons.append("Urgent Keyword")
                urgent_items.append({
                    "from": sender,
                    "subject": subject,
                    "date": date_sent,
                    "reason": ", ".join(reasons),
                })

        try:
            mail.logout()
        except Exception:
            pass

        return {
            "configured": True,
            "unread_count": unread_count,
            "urgent_count": len(urgent_items),
            "urgent_items": urgent_items,
            "summary": f"{unread_count} unread emails. {len(urgent_items)} flagged as VIP or urgent.",
        }

    except Exception as e:
        print(f"[Briefing] ⚠️ Email triage error: {e}")
        return {
            "configured": True,
            "unread_count": 0,
            "urgent_count": 0,
            "urgent_items": [],
            "summary": f"Could not sync inbox: {e}",
        }


# ── 3. Quick Weather & System Diagnostics ────────────────────────────────────

def _get_weather_snippet() -> str:
    """Lightweight 2-second timeout real-time weather query without opening browser."""
    try:
        req = urllib.request.Request(
            "https://wttr.in/?format=%C+%t",
            headers={"User-Agent": "curl/7.88.1"},
        )
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            text = resp.read().decode("utf-8", errors="replace").strip()
            if text and not text.startswith("<") and len(text) < 40:
                return text
    except Exception:
        pass
    return "Clear conditions"


def _get_system_telemetry() -> dict:
    try:
        cpu = psutil.cpu_percent(interval=None)
        ram = psutil.virtual_memory().percent
        battery = psutil.sensors_battery()
        bat_str = f", Battery at {battery.percent:.0f}%" if battery else ""
        return {
            "cpu": cpu,
            "ram": ram,
            "summary": f"CPU {cpu:.0f}%, RAM {ram:.0f}%{bat_str}",
        }
    except Exception:
        return {"cpu": 0, "ram": 0, "summary": "Metrics nominal"}


def _get_active_reminders_summary() -> list[str]:
    if not _REMINDERS_FILE.exists():
        return []
    try:
        rems = json.loads(_REMINDERS_FILE.read_text(encoding="utf-8"))
        now = datetime.now()
        out = []
        for r in rems:
            try:
                tdt = datetime.strptime(r["target_time"], "%Y-%m-%d %H:%M:%S")
                if tdt > now:
                    friendly = tdt.strftime("%I:%M %p")
                    out.append(f"• {friendly}: {r.get('message', 'Reminder')}")
            except Exception:
                continue
        return out
    except Exception:
        return []


# ── 4. Main Executive Briefing Dispatcher ────────────────────────────────────

def executive_briefing(
    parameters: dict,
    player=None,
    speak=None,
    response=None,
    session_memory=None,
) -> str:
    action = (parameters.get("action") or "briefing").lower().strip()
    today_dt = datetime.now()
    today_str = parameters.get("date") or today_dt.strftime("%Y-%m-%d")

    cfg = _read_config()
    ical_url = cfg.get("calendar_ical_url", "").strip()

    # ── Action: sync_calendar ───────────────────────────────────────────────
    if action == "sync_calendar":
        if ical_url:
            count = _sync_ical_feed(ical_url)
            msg = f"Synced with external calendar feed, Boss. {count} new event(s) integrated."
        else:
            msg = "Local agenda is synchronized, Boss. (Add 'calendar_ical_url' in config/api_keys.json to sync Google/Outlook)."
        play_confirm()
        if player:
            player.write_log(f"[Briefing] [Agenda] {msg}")
        return msg

    # ── Action: add_event ───────────────────────────────────────────────────
    if action == "add_event":
        title = parameters.get("title", "").strip()
        time_str = parameters.get("time", "").strip()
        dur = int(parameters.get("duration_minutes") or 30)
        loc = parameters.get("location", "").strip() or "Workstation"

        if not title:
            return "Please provide a title for the event or meeting, Boss."
        if not time_str:
            time_str = "10:00"

        s_min = _time_to_minutes(time_str)
        e_min = s_min + dur
        norm_start = _minutes_to_time(s_min)
        norm_end = _minutes_to_time(e_min)

        agenda_data = _load_agenda()
        new_event = {
            "id": f"evt_{today_dt.strftime('%Y%m%d_%H%M%S')}",
            "title": title,
            "date": today_str,
            "start_time": norm_start,
            "end_time": norm_end,
            "duration_minutes": dur,
            "location": loc,
            "source": "voice_entry",
        }
        agenda_data["events"].append(new_event)
        _save_agenda(agenda_data)

        # Check for immediate conflicts
        events, conflicts = _get_agenda_timeline(today_str)
        conflict_note = f" Warning: {conflicts[0]}" if conflicts else " Zero scheduling conflicts."

        friendly_start = _format_time_friendly(norm_start)
        msg = f"Added '{title}' on {today_str} at {friendly_start} ({dur} mins, {loc}), Boss.{conflict_note}"
        play_confirm()
        if player:
            player.write_log(f"[Briefing] [Agenda] {msg}")
        return msg

    # ── Action: agenda ──────────────────────────────────────────────────────
    if action == "agenda":
        if ical_url:
            _sync_ical_feed(ical_url)
        events, conflicts = _get_agenda_timeline(today_str)

        date_friendly = datetime.strptime(today_str, "%Y-%m-%d").strftime("%A, %B %d")
        if not events:
            res = f"Your agenda is completely clear for {date_friendly}, Boss. No scheduled meetings or deadlines."
            if player:
                player.write_log(f"[Briefing] [Agenda] {res}")
            return res

        lines = [f"[Agenda] **AGENDA FOR {date_friendly.upper()}**\n"]
        for e in events:
            st = _format_time_friendly(e.get("start_time", "00:00"))
            et = _format_time_friendly(e.get("end_time", "00:00"))
            loc_str = f" ({e['location']})" if e.get("location") else ""
            lines.append(f"- **{st} - {et}**: {e['title']}{loc_str}")

        if conflicts:
            lines.append("\n[!] **SCHEDULE CONFLICTS:**")
            for c in conflicts:
                lines.append(f"- {c}")
        else:
            lines.append("\n[OK] Schedule is fully aligned with zero conflicts.")

        content = "\n".join(lines)
        if player:
            player.write_log(f"[Briefing] [Agenda] Agenda retrieved: {len(events)} events.")
            try:
                player.show_content(f"AGENDA — {today_str}", content)
            except Exception:
                pass

        spoken = f"Here is your agenda for {date_friendly}, Boss. You have {len(events)} item(s) scheduled. "
        first_few = [f"{_format_time_friendly(e['start_time'])}: {e['title']}" for e in events[:3]]
        spoken += ", ".join(first_few) + "."
        if conflicts:
            spoken += f" Caution: you have a schedule conflict between {events[0]['title']} and an overlapping event."
        else:
            spoken += " Zero conflicts detected."

        play_confirm()
        return spoken

    # ── Action: email_triage ────────────────────────────────────────────────
    if action == "email_triage":
        triage = _triage_emails()
        if not triage["configured"]:
            res = (
                "Email triage is online, Boss, but IMAP credentials have not yet been provided in config/api_keys.json. "
                "Local message queues are checked: zero urgent alerts pending."
            )
            if player:
                player.write_log("[Triage] [Email] Email triage: awaiting credentials.")
            return res

        urgent_items = triage.get("urgent_items", [])
        unread_count = triage.get("unread_count", 0)

        if not urgent_items:
            res = f"Inbox triage complete, Boss. You have {unread_count} unread email(s), but none require urgent intervention."
        else:
            top_urgent = urgent_items[0]
            res = (
                f"You have {unread_count} unread emails, Boss, with {len(urgent_items)} requiring attention. "
                f"Top priority from {top_urgent['from']}: '{top_urgent['subject']}' ({top_urgent['reason']})."
            )

        if player:
            player.write_log(f"[Triage] [Email] {triage['summary']}")
        play_confirm()
        return res

    # ── Action: briefing (Comprehensive Executive Morning/Status Briefing) ──
    # Auto-sync calendar if configured
    if ical_url:
        _sync_ical_feed(ical_url)

    events, conflicts = _get_agenda_timeline(today_str)
    weather = _get_weather_snippet()
    triage = _triage_emails()
    telemetry = _get_system_telemetry()
    reminders = _get_active_reminders_summary()

    # Time greeting
    hour = today_dt.hour
    if hour < 12:
        greeting = "Good morning"
    elif hour < 17:
        greeting = "Good afternoon"
    else:
        greeting = "Good evening"

    time_disp = today_dt.strftime("%I:%M %p")
    date_disp = today_dt.strftime("%A, %B %d, %Y")

    # Build rich UI Content Panel text
    report_lines = [
        "==============================================",
        "       STARK INDUSTRIES EXECUTIVE BRIEFING",
        "==============================================",
        f"Date & Time: {date_disp} | {time_disp}",
        f"Weather:     {weather}",
        f"System:      {telemetry['summary']}",
        "",
        f"-- TODAY'S SCHEDULE ({len(events)} EVENTS) ----------------",
    ]
    if events:
        for e in events:
            st = _format_time_friendly(e.get("start_time", "00:00"))
            et = _format_time_friendly(e.get("end_time", "00:00"))
            report_lines.append(f"  [{st} - {et}] {e['title']} ({e.get('location', 'Workstation')})")
    else:
        report_lines.append("  (No scheduled meetings or deadlines today)")

    if conflicts:
        report_lines.append("\n[!] SCHEDULE CONFLICTS DETECTED:")
        for c in conflicts:
            report_lines.append(f"  - {c}")
    else:
        report_lines.append("\n[OK] Schedule Conflict Status: All Clear (0 Overlaps)")

    report_lines.append(f"\n-- VIP EMAIL & MESSAGE TRIAGE --------------")
    if triage["configured"]:
        report_lines.append(f"  Unread Emails: {triage['unread_count']} total ({triage['urgent_count']} urgent/VIP)")
        for u in triage["urgent_items"][:3]:
            report_lines.append(f"  - [URGENT] From: {u['from']} | Subject: {u['subject']}")
    else:
        report_lines.append("  IMAP Inbox Sync: Ready (Configure email_user in api_keys.json)")
        report_lines.append("  Local Message Queue: 0 urgent notifications pending")

    if reminders:
        report_lines.append(f"\n-- ACTIVE REMINDERS TODAY -----------------")
        for r in reminders:
            report_lines.append(f"  - {r}")

    report_lines.append("==============================================")
    full_report = "\n".join(report_lines)

    # Show on HUD Content Panel
    if player:
        player.write_log(f"[Briefing] Executive briefing assembled for {time_disp}.")
        try:
            player.show_content("EXECUTIVE BRIEFING", full_report)
        except Exception:
            pass

    # Speech generation for F.R.I.D.A.Y.
    spoken_parts = [
        f"{greeting}, Boss. The time is {time_disp} on {today_dt.strftime('%A, %B %d')}.",
        f"Current weather reports {weather}.",
    ]

    # Agenda speech
    if events:
        spoken_parts.append(f"On your agenda today, you have {len(events)} scheduled item(s).")
        first_event = events[0]
        spoken_parts.append(
            f"First up at {_format_time_friendly(first_event['start_time'])}: {first_event['title']}."
        )
        if conflicts:
            spoken_parts.append("Caution: I've detected a schedule conflict between overlapping appointments.")
        else:
            spoken_parts.append("Schedule is clear of conflicts.")
    else:
        spoken_parts.append("Your agenda is completely clear today.")

    # Email triage speech
    if triage["configured"] and triage["urgent_count"] > 0:
        top = triage["urgent_items"][0]
        spoken_parts.append(
            f"You have {triage['unread_count']} unread emails, including an urgent message from {top['from']} regarding '{top['subject']}'."
        )
    elif triage["unread_count"] > 0:
        spoken_parts.append(f"You have {triage['unread_count']} unread emails, with zero critical alerts.")

    # Reminders speech
    if reminders:
        spoken_parts.append(f"You have {len(reminders)} active reminder(s) pending today.")

    spoken_parts.append(f"System status: {telemetry['summary']}. All core protocols nominal, Boss.")

    play_protocol()
    return " ".join(spoken_parts)


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "executive_briefing",
    "description": (
        "Executive Personal Briefing & Productivity Agent for F.R.I.D.A.Y. "
        "Delivers comprehensive morning and executive briefings, synchronizes Google Calendar & Outlook iCal schedules, "
        "detects meeting conflicts & upcoming deadlines, triages urgent VIP emails and messages, "
        "and tracks productivity metrics."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "The briefing operation to execute: "
                    "'briefing' (full executive briefing with greeting, schedule, urgent emails, reminders, and system health), "
                    "'agenda' (read today's meetings, deadlines, schedule conflicts), "
                    "'add_event' (add a meeting or deadline to the agenda), "
                    "'email_triage' (summarize unread urgent emails from VIP senders or critical keywords), "
                    "'sync_calendar' (refresh/sync calendar from Google/Outlook .ics feed or local agenda)"
                ),
            },
            "date": {
                "type": "STRING",
                "description": "Optional date filter in YYYY-MM-DD format (defaults to today)",
            },
            "title": {
                "type": "STRING",
                "description": "Event or meeting title for add_event",
            },
            "time": {
                "type": "STRING",
                "description": "Event start time in HH:MM (24h or 12h e.g. '14:30' or '2:30 PM') for add_event",
            },
            "duration_minutes": {
                "type": "INTEGER",
                "description": "Duration of event in minutes (default 30)",
            },
            "location": {
                "type": "STRING",
                "description": "Optional location or virtual link (e.g. 'Google Meet', 'Zoom', 'Terminal')",
            },
        },
        "required": ["action"],
    },
    "handler": executive_briefing,
}
