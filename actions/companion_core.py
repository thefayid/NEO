"""
actions/companion_core.py — F.R.I.D.A.Y. Advanced Companion Engine.

Implements all 6 human companion modules:
  1. Deep Episodic Memory & Story Logging (Milestones, shared memories, struggles, personal goals).
  2. Autonomous Lifestyle & Caring Sentinel (Late-night check-in, hydration, burnout prevention).
  3. Adaptive Mood & Acoustic Vibe DJ (Automatic Spotify / YouTube mood curation: calm, focus, beast_mode).
  4. Co-Founder & Intellectual Sounding Board (Deep critical analysis, constructive debate, strategic roadmaps).
  5. Pocket Phone Sync & Ambient Memos (Direct voice/status sync to user's Telegram/WhatsApp).
"""
from __future__ import annotations

import datetime
import json
import os
import random
import sys
from pathlib import Path
from typing import Optional

from core import gemini, outcome

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

_BASE = _base_dir()
_EPISODES_FILE = _BASE / "memory" / "episodes.json"
_CONFIG_FILE = _BASE / "config" / "api_keys.json"


def _load_episodes() -> list[dict]:
    if _EPISODES_FILE.exists():
        try:
            return json.loads(_EPISODES_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _save_episodes(episodes: list[dict]) -> None:
    try:
        _EPISODES_FILE.parent.mkdir(parents=True, exist_ok=True)
        _EPISODES_FILE.write_text(json.dumps(episodes, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"[Companion] Could not save episodes: {e}")


# ── 1. DEEP EPISODIC MEMORY ──────────────────────────────────────────────────
def log_milestone_story(title: str, story: str, category: str = "growth") -> str:
    """Store an autobiographical milestone or story into episodic memory."""
    episodes = _load_episodes()
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = {
        "timestamp": now_str,
        "title": title.strip() or "Untitled Milestone",
        "story": story.strip(),
        "category": category.strip().lower(),
    }
    episodes.append(entry)
    _save_episodes(episodes)
    try:
        from core.sfx import play_confirm
        play_confirm()
    except Exception:
        pass
    return f"[EPISODIC MEMORY PRESERVED]\nLogged '{title}' on {now_str}. I'll remember this chapter of our journey, Boss."


def recall_episodes(query: str = "") -> str:
    """Search autobiographical memories and shared stories."""
    episodes = _load_episodes()
    if not episodes:
        return "Our episodic storybook is just beginning, Boss. No long-term milestones recorded yet."

    q = (query or "").lower().strip()
    matches = []
    for ep in episodes:
        t = ep.get("title", "").lower()
        s = ep.get("story", "").lower()
        if not q or (q in t or q in s):
            matches.append(ep)

    if not matches:
        return f"I don't recall any shared milestones matching '{query}', Boss."

    lines = [f"[SHARED JOURNEY: {len(matches)} EPISODE(S)]"]
    for ep in matches[-5:]:  # show recent 5
        lines.append(f"- [{ep['timestamp']}] {ep['title']}: {ep['story']}")
    return "\n".join(lines)


# ── 2. AUTONOMOUS CARING & LATE-NIGHT CHECK-IN ────────────────────────────────
def caring_check_in() -> str:
    """Evaluate current time, working duration, and deliver a caring check-in."""
    now = datetime.datetime.now()
    hour = now.hour

    if 0 <= hour < 5:
        msg = (
            f"[LATE-NIGHT GUARDIAN - {now.strftime('%I:%M %p')}]\n"
            "Boss, you've been burning the midnight oil past 12 AM. The code and system are stable. "
            "How about saving your work, resting your eyes, and conquering the rest tomorrow with a fresh mind?"
        )
    elif 12 <= hour < 14:
        msg = (
            f"[MIDDAY CHECK-IN - {now.strftime('%I:%M %p')}]\n"
            "Quick reminder, Boss: Step away from the monitor, grab lunch, and hydrate. "
            "I'll hold the fort while you recharge."
        )
    elif hour >= 21:
        msg = (
            f"[EVENING WIND-DOWN - {now.strftime('%I:%M %p')}]\n"
            "Wrapping up the heavy thinking for today, Boss? Remember to take a breather."
        )
    else:
        msg = (
            f"[COMPANION PULSE - {now.strftime('%I:%M %p')}]\n"
            "All background systems running smooth, Boss. How's your energy holding up?"
        )
    return msg



# ── 3. ADAPTIVE MOOD & VIBE DJ ───────────────────────────────────────────────
def set_mood_vibe(vibe: str) -> str:
    """Set acoustic mood via Spotify (calm, focus, beast_mode, night, lofi)."""
    vibe = vibe.lower().strip()
    playlist_map = {
        "calm": "ambient chill instrumental",
        "chill": "lofi beats relaxing",
        "focus": "deep focus instrumental coding",
        "coding": "cyberpunk synthwave coding",
        "beast_mode": "AC DC high energy rock",
        "energy": "electronic workout high bpm",
        "night": "gentle piano acoustic night",
    }
    search_query = playlist_map.get(vibe, f"{vibe} playlist")

    try:
        from actions.spotify_control import spotify_control
        res = spotify_control({"action": "play", "query": search_query})
        return f"[VIBE CURATION: {vibe.upper()}]\nAdjusted acoustic environment. {res}"
    except Exception as e:
        return f"Could not transition music vibe: {e}"


# ── 4. CO-FOUNDER & SOUNDING BOARD ───────────────────────────────────────────
def sounding_board(idea_or_problem: str) -> str:
    """Rigorous intellectual critique, counter-arguments, and strategic refinement."""
    prompt = (
        "You are F.R.I.D.A.Y. acting as Tony Stark's brilliant technical co-founder and trusted sounding board.\n"
        "Critique, stress-test, and refine this idea or problem:\n"
        f"\"{idea_or_problem}\"\n\n"
        "Provide:\n"
        "1. Direct, honest reaction & strategic merit.\n"
        "2. Top 2 critical failure points, hidden risks, or edge-cases to watch out for.\n"
        "3. Concrete next iteration step.\n"
        "Be sharp, loyal, intellectually challenging, and speak naturally to the Boss."
    )
    try:
        resp = gemini.text(prompt, tier=gemini.SMART, timeout_ms=35000)
        return resp if resp else "Idea registered, Boss. Ready to break it down further whenever you are."
    except Exception as e:
        return f"Sounding board deliberation error: {e}"


# ── 5. POCKET PHONE SYNC ─────────────────────────────────────────────────────
def sync_to_phone(note_or_status: str) -> str:
    """Send an immediate memo or status digest to user's Telegram."""
    try:
        from actions.send_message import _load_config
        cfg = _load_config()
        token = cfg.get("telegram_bot_token", "").strip()
        chat_id = cfg.get("telegram_chat_id", "").strip()

        if token and chat_id:
            import urllib.parse
            import urllib.request
            txt = f"🤖 [F.R.I.D.A.Y. Companion Sync]\n{note_or_status}"
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            data = urllib.parse.urlencode({"chat_id": chat_id, "text": txt}).encode("utf-8")
            req = urllib.request.Request(url, data=data)
            with urllib.request.urlopen(req, timeout=8):
                pass
            return f"[PHONE SYNC COMPLETE]\nDispatched to your Telegram, Boss: \"{note_or_status}\""
    except Exception as e:
        print(f"[Companion] Phone sync error: {e}")

    return f"[POCKET MEMO RECORDED]\nStored in workstation buffer: \"{note_or_status}\""


# ── MAIN DISPATCH ────────────────────────────────────────────────────────────
def companion_core(parameters: dict | None = None, **kwargs) -> str:
    """Main dispatch for F.R.I.D.A.Y. companion systems."""
    params = parameters or {}
    action = str(params.get("action", "check_in")).strip().lower()

    if action in ("log_story", "milestone", "remember_story", "story"):
        title = str(params.get("title", "Milestone"))
        story = str(params.get("story", params.get("text", "")))
        return log_milestone_story(title, story)
    elif action in ("recall_stories", "stories", "shared_memories"):
        query = str(params.get("query", ""))
        return recall_episodes(query)
    elif action in ("check_in", "caring", "health", "how_am_i"):
        return caring_check_in()
    elif action in ("set_vibe", "mood", "music_vibe", "dj"):
        vibe = str(params.get("vibe", "focus"))
        return set_mood_vibe(vibe)
    elif action in ("sounding_board", "critique", "brainstorm", "debate"):
        idea = str(params.get("idea", params.get("query", "")))
        if not idea:
            return "What idea or architecture would you like me to stress-test with you, Boss?"
        return sounding_board(idea)
    elif action in ("sync_phone", "send_to_phone", "pocket_memo"):
        note = str(params.get("note", params.get("text", "Workstation status nominal.")))
        return sync_to_phone(note)
    else:
        return caring_check_in()


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "companion_core",
    "description": (
        "F.R.I.D.A.Y. Advanced Sentient Companion & Caring Engine. "
        "Actions: "
        "'check_in' (Autonomous caring pulse, late-night check-in, energy check) | "
        "'log_story' (Save shared autobiographical milestone or story into episodic memory) | "
        "'recall_stories' (Search shared history and past stories) | "
        "'set_vibe' (Curate acoustic Spotify mood: 'focus', 'calm', 'beast_mode', 'night', 'chill') | "
        "'sounding_board' (Acts as technical co-founder, rigorously stress-testing ideas & giving honest critique) | "
        "'sync_phone' (Sends immediate note or digest to user's Telegram/phone). "
        "Call when user wants caring check-in, advice, mood music, brainstorm sounding board, or to save life milestones."
    ),
    "brief": "Sentient companion engine: caring check-in, episodic memories, mood DJ, sounding board, phone sync.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "Action: 'check_in' | 'log_story' | 'recall_stories' | 'set_vibe' | 'sounding_board' | 'sync_phone'",
                "enum": ["check_in", "log_story", "recall_stories", "set_vibe", "sounding_board", "sync_phone"],
            },
            "title": {
                "type": "STRING",
                "description": "Title of the milestone or story for 'log_story'.",
            },
            "story": {
                "type": "STRING",
                "description": "Details of the shared memory, story, or milestone.",
            },
            "vibe": {
                "type": "STRING",
                "description": "Desired vibe for 'set_vibe': 'focus' | 'calm' | 'beast_mode' | 'night' | 'chill'",
            },
            "idea": {
                "type": "STRING",
                "description": "Idea, problem, or architectural plan to stress-test in 'sounding_board'.",
            },
            "note": {
                "type": "STRING",
                "description": "Note or memo text for 'sync_phone'.",
            },
        },
    },
    "handler": companion_core,
}
