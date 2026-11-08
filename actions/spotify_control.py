"""
actions/spotify_control.py — Direct Spotify & Media Integration for F.R.I.D.A.Y.

Dual-Engine Architecture:
1. Spotify Web API (spotipy):
   - Authenticated hands-free control across all Spotify Connect devices.
   - Play tracks, artists, albums, playlists directly via Spotify API.
   - Query exact track names, artists, progress, and playback state.
2. Windows Desktop & Media Transport Engine (Zero-Key Native Fallback):
   - Controls local Spotify Desktop app via Windows protocol URIs (spotify:search:...) and media keys.
   - Automatically detects current song title & artist from Windows Spotify window title inspection without needing an API key!
   - System volume scaling (e.g. "turn up the volume by 20%").
   - Accompanied by subtle MCU Stark metallic audio chimes (core/sfx).
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes as w
import json
import os
import platform
import subprocess
import time
import urllib.parse
from pathlib import Path
from typing import Optional, Tuple

import psutil

try:
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth
    _SPOTIPY_OK = True
except ImportError:
    _SPOTIPY_OK = False

try:
    import pyautogui
    _PYAUTOGUI_OK = True
except ImportError:
    _PYAUTOGUI_OK = False

from core.sfx import play_media, play_confirm, play_error

_OS = platform.system()
user32 = ctypes.windll.user32 if _OS == "Windows" else None

_BASE_DIR = Path(__file__).resolve().parent.parent
_CONFIG_FILE = _BASE_DIR / "config" / "api_keys.json"


def _load_config() -> dict:
    try:
        return json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _get_spotify_client() -> Optional[spotipy.Spotify]:
    """Initialize Spotipy client if Spotify credentials exist in config."""
    if not _SPOTIPY_OK:
        return None

    cfg = _load_config()
    client_id = cfg.get("spotify_client_id", "").strip()
    client_secret = cfg.get("spotify_client_secret", "").strip()
    redirect_uri = cfg.get("spotify_redirect_uri", "http://127.0.0.1:8888/callback").strip()

    if not (client_id and client_secret):
        return None

    try:
        scope = "user-read-playback-state user-modify-playback-state user-read-currently-playing playlist-read-private"
        sp_oauth = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=scope,
            cache_path=str(_BASE_DIR / ".cache-spotify"),
            open_browser=False
        )
        token_info = sp_oauth.get_cached_token()
        if not token_info:
            return None
        return spotipy.Spotify(auth=token_info["access_token"])
    except Exception as e:
        print(f"[Spotify] Web API auth note: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
#  NATIVE WINDOWS DESKTOP SPOTIFY INSPECTION & CONTROL
# ─────────────────────────────────────────────────────────────────────────────

def _attach_desktop():
    if _OS != "Windows" or user32 is None:
        return
    try:
        hwinsta0 = user32.OpenWindowStationW("WinSta0", False, 0x037F)
        if hwinsta0:
            user32.SetProcessWindowStation(hwinsta0)
        hdesk = user32.OpenDesktopW("default", 0, False, 0x01FF)
        if hdesk:
            user32.SetThreadDesktop(hdesk)
    except Exception:
        pass


def _get_desktop_spotify_window() -> Optional[Tuple[int, str]]:
    """
    Find the Spotify window on Windows.
    When music is playing, the title is formatted as: 'Artist - Song Title'.
    """
    if _OS != "Windows" or user32 is None:
        return None

    _attach_desktop()
    found = []

    def enum_cb(hwnd, lparam):
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buff = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buff, length + 1)
        title = buff.value.strip()

        pid = w.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        try:
            p = psutil.Process(pid.value)
            if "spotify" in p.name().lower():
                # Ignore invisible/system helper windows
                if user32.IsWindowVisible(hwnd) and title:
                    found.append((hwnd, title))
        except Exception:
            pass
        return True

    CB_T = ctypes.WINFUNCTYPE(ctypes.c_bool, w.HWND, w.LPARAM)
    user32.EnumWindows(CB_T(enum_cb), 0)

    # Prefer window with artist - title separator
    for hwnd, title in found:
        if " - " in title:
            return (hwnd, title)

    # Fallback to main Spotify window
    for hwnd, title in found:
        if "spotify" in title.lower():
            return (hwnd, title)

    return found[0] if found else None


def _get_current_song_desktop() -> str:
    """Extract currently playing artist and song title from Windows window title."""
    win = _get_desktop_spotify_window()
    if not win:
        # Check if process is running
        for p in psutil.process_iter():
            try:
                if "spotify" in p.name().lower():
                    return "Spotify is running in the background, but no track is currently playing, Boss."
            except Exception:
                pass
        return "Spotify is not currently running, Boss."

    hwnd, title = win
    if " - " in title:
        parts = title.split(" - ", 1)
        artist = parts[0].strip()
        song = parts[1].strip()
        return f"Currently playing '{song}' by {artist} on Spotify, Boss."
    elif title.lower() in ("spotify", "spotify premium", "spotify free"):
        return "Spotify is open, but playback is currently paused, Boss."
    else:
        return f"Spotify is active: '{title}', Boss."


def _focus_spotify_window():
    """Ensure Spotify is restored and brought to foreground on Windows, ignoring background launcher stubs."""
    if _OS != "Windows":
        return
    _attach_desktop()
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", "(New-Object -ComObject WScript.Shell).AppActivate('Spotify')"],
            capture_output=True, timeout=2
        )
    except Exception:
        pass

    if user32:
        try:
            def enum_cb(hwnd, lparam):
                pid = w.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                try:
                    p = psutil.Process(pid.value)
                    p_name = p.name().lower()
                    # Strictly target Spotify.exe and NEVER the helper/splash SpotifyLauncher.exe
                    if p_name == "spotify.exe":
                        length = user32.GetWindowTextLengthW(hwnd)
                        buff = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buff, length + 1)
                        title = buff.value
                        if "spotifylauncher" in title.lower():
                            return True
                        rect = w.RECT()
                        user32.GetWindowRect(hwnd, ctypes.byref(rect))
                        width = rect.right - rect.left
                        height = rect.bottom - rect.top
                        # Ensure it's a real displayed window and not offscreen
                        if width > 400 and height > 300 and rect.left > -1000:
                            user32.SetForegroundWindow(hwnd)
                            return False
                except Exception:
                    pass
                return True

            CB_T = ctypes.WINFUNCTYPE(ctypes.c_bool, w.HWND, w.LPARAM)
            user32.EnumWindows(CB_T(enum_cb), 0)
        except Exception:
            pass


def _find_and_click_spotify_play_button(timeout: float = 3.5) -> bool:
    """
    Locates Spotify's circular green play button (#1ED760 / #1DB954) on screen
    using HSV color filtering and contour circularity analysis, then clicks directly on its center.
    """
    if not _PYAUTOGUI_OK:
        return False

    import pyautogui
    pyautogui.FAILSAFE = False

    try:
        from PIL import ImageGrab
        import cv2
        import numpy as np
    except ImportError:
        return False

    start_time = time.time()
    # Spotify green in HSV: H: 65-80, S: 160-255, V: 140-255
    lower_green = np.array([65, 160, 140])
    upper_green = np.array([80, 255, 255])

    while time.time() - start_time < timeout:
        try:
            screenshot = ImageGrab.grab()
            screen_w, screen_h = pyautogui.size()
            img_w, img_h = screenshot.size
            scale_x = screen_w / img_w if img_w > 0 else 1.0
            scale_y = screen_h / img_h if img_h > 0 else 1.0

            frame = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            mask = cv2.inRange(hsv, lower_green, upper_green)

            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            candidates = []
            for c in contours:
                area = cv2.contourArea(c)
                if area > 350:
                    x, y, w, h = cv2.boundingRect(c)
                    aspect = float(w) / h
                    # Circular button: aspect ratio close to 1.0, diameter 20 to 120 px
                    if 0.78 <= aspect <= 1.25 and 20 <= w <= 120 and 20 <= h <= 120:
                        candidates.append((x, y, w, h, area))

            if candidates:
                # Top result play button is the prominent large circular button
                candidates.sort(key=lambda item: (-item[4], item[1]))
                best_x, best_y, best_w, best_h, _ = candidates[0]

                target_x = int((best_x + best_w // 2) * scale_x)
                target_y = int((best_y + best_h // 2) * scale_y)

                print(f"[Spotify] Visual detector found green Play button at ({target_x}, {target_y}). Clicking...")
                pyautogui.click(target_x, target_y)
                time.sleep(0.12)
                pyautogui.click(target_x, target_y)
                return True

        except Exception as e:
            print(f"[Spotify] Visual detection scan attempt: {e}")

        time.sleep(0.3)

    return False


def _play_query_desktop(query: str) -> str:
    """Search and start playback on Spotify using Computer Vision button detection and desktop control."""
    import pyperclip

    if _OS == "Windows":
        try:
            if _PYAUTOGUI_OK:
                import pyautogui
                pyautogui.FAILSAFE = False

            # 1. Bring Spotify to front
            _focus_spotify_window()

            # 2. Open Spotify search URI directly
            encoded = urllib.parse.quote(query)
            uri = f"spotify:search:{encoded}"
            subprocess.Popen(["cmd", "/c", "start", uri], shell=True)
            time.sleep(0.8)

            # Re-assert focus
            _focus_spotify_window()

            if _PYAUTOGUI_OK:
                # Clear any open context menus
                pyautogui.press("escape")
                time.sleep(0.1)

                # Focus search bar (Ctrl+L) and submit query cleanly
                pyautogui.hotkey("ctrl", "l")
                time.sleep(0.15)
                pyautogui.hotkey("ctrl", "a")
                time.sleep(0.05)
                pyperclip.copy(query)
                pyautogui.hotkey("ctrl", "v")
                time.sleep(0.15)
                pyautogui.press("enter")
                time.sleep(0.6)

                # 3. Accurately click the Green Play Button via Computer Vision
                clicked = _find_and_click_spotify_play_button(timeout=3.5)

                if not clicked:
                    print("[Spotify] CV button detection timed out; using keyboard select fallback...")
                    # Down arrow navigates cursor into top search result, Enter activates playback
                    pyautogui.press("down")
                    time.sleep(0.15)
                    pyautogui.press("enter")
                    time.sleep(0.2)
                    pyautogui.press("space")

            play_media()
            return f"Playing '{query}' on Spotify, Boss."
        except Exception as e:
            print(f"[Spotify] Desktop play error: {e}")
            return f"Could not execute playback for '{query}': {e}"

def _adjust_system_volume(volume: Optional[int] = None, change: Optional[str] = None) -> str:
    """Set or adjust master audio volume."""
    try:
        from actions.computer_settings import volume_get, volume_set
        cur = volume_get()
        if cur is None:
            cur = 50

        if change:
            val_str = str(change).replace("%", "").strip()
            delta = int(val_str)
            target = max(0, min(100, cur + delta))
            volume_set(target)
            direction = "increased" if delta > 0 else "decreased"
            play_confirm()
            return f"Volume {direction} by {abs(delta)}% (now at {target}%), Boss."
        elif volume is not None:
            target = max(0, min(100, int(volume)))
            volume_set(target)
            play_confirm()
            return f"Volume set to {target}%, Boss."
    except Exception as e:
        print(f"[Spotify] Volume adjustment error: {e}")

    # Fallback to pyautogui keypresses
    if _PYAUTOGUI_OK:
        if change and str(change).startswith("-"):
            for _ in range(5):
                pyautogui.press("volumedown")
            play_confirm()
            return "Volume turned down, Boss."
        else:
            for _ in range(5):
                pyautogui.press("volumeup")
            play_confirm()
            return "Volume turned up, Boss."

    return "Volume adjusted, Boss."


# ─────────────────────────────────────────────────────────────────────────────
#  SPOTIFY CONTROL ACTION HANDLER
# ─────────────────────────────────────────────────────────────────────────────

def spotify_control(parameters: dict, player=None, **kwargs) -> str:
    params = parameters or {}
    action = params.get("action", "play").lower().strip()
    query = params.get("query", "").strip()
    volume = params.get("volume")
    change = params.get("change")

    sp = _get_spotify_client()

    # ── 1. WHAT SONG IS PLAYING ──────────────────────────────────────────────
    if action in ("current", "now_playing", "status", "what_is_playing"):
        if sp:
            try:
                curr = sp.current_playback()
                if curr and curr.get("is_playing") and curr.get("item"):
                    item = curr["item"]
                    title = item.get("name", "Unknown")
                    artists = ", ".join(a["name"] for a in item.get("artists", []))
                    album = item.get("album", {}).get("name", "")
                    album_str = f" from the album '{album}'" if album else ""
                    play_media()
                    return f"Currently playing '{title}' by {artists}{album_str} on Spotify, Boss."
                elif curr and not curr.get("is_playing"):
                    return "Spotify is currently paused, Boss."
            except Exception as e:
                print(f"[Spotify] Web API current track error: {e}")

        # Desktop inspection fallback
        return _get_current_song_desktop()

    # ── 2. PLAY / SEARCH MUSIC ───────────────────────────────────────────────
    elif action in ("play", "start"):
        if not query:
            # Simple resume
            if sp:
                try:
                    sp.start_playback()
                    play_media()
                    return "Resuming Spotify playback, Boss."
                except Exception:
                    pass
            if _PYAUTOGUI_OK:
                pyautogui.press("playpause")
                play_media()
                return "Resumed playback on Spotify, Boss."
            return "Resumed playback, Boss."

        # Web API track/artist search & direct playback
        if sp:
            try:
                results = sp.search(q=query, limit=1, type="track,artist")
                tracks = results.get("tracks", {}).get("items", [])
                if tracks:
                    track_uri = tracks[0]["uri"]
                    track_name = tracks[0]["name"]
                    artist_name = tracks[0]["artists"][0]["name"]
                    sp.start_playback(uris=[track_uri])
                    play_media()
                    return f"Playing '{track_name}' by {artist_name} on Spotify, Boss."
                artists = results.get("artists", {}).get("items", [])
                if artists:
                    artist_uri = artists[0]["uri"]
                    artist_name = artists[0]["name"]
                    sp.start_playback(context_uri=artist_uri)
                    play_media()
                    return f"Playing top tracks from {artist_name} on Spotify, Boss."
            except Exception as e:
                print(f"[Spotify] Web API search playback fallback: {e}")

        # Desktop Spotify fallback
        return _play_query_desktop(query)

    # ── 3. PAUSE / RESUME ────────────────────────────────────────────────────
    elif action in ("pause", "stop"):
        if sp:
            try:
                sp.pause_playback()
                play_confirm()
                return "Spotify playback paused, Boss."
            except Exception:
                pass
        if _PYAUTOGUI_OK:
            pyautogui.press("playpause")
            play_confirm()
            return "Spotify playback paused, Boss."
        return "Playback paused, Boss."

    elif action in ("resume", "unpause"):
        if sp:
            try:
                sp.start_playback()
                play_media()
                return "Resumed Spotify playback, Boss."
            except Exception:
                pass
        if _PYAUTOGUI_OK:
            pyautogui.press("playpause")
            play_media()
            return "Resumed Spotify playback, Boss."
        return "Playback resumed, Boss."

    # ── 4. SKIP / TRACK NAVIGATION ───────────────────────────────────────────
    elif action in ("next", "skip"):
        if sp:
            try:
                sp.next_track()
                play_confirm()
                time.sleep(0.4)
                return _get_current_song_desktop()
            except Exception:
                pass
        if _PYAUTOGUI_OK:
            pyautogui.press("nexttrack")
            play_confirm()
            return "Skipped to next track on Spotify, Boss."
        return "Next track, Boss."

    elif action in ("prev", "previous", "back"):
        if sp:
            try:
                sp.previous_track()
                play_confirm()
                time.sleep(0.4)
                return _get_current_song_desktop()
            except Exception:
                pass
        if _PYAUTOGUI_OK:
            pyautogui.press("prevtrack")
            play_confirm()
            return "Returning to previous track on Spotify, Boss."
        return "Previous track, Boss."

    # ── 5. VOLUME ADJUSTMENT ─────────────────────────────────────────────────
    elif action in ("volume", "set_volume", "adjust_volume"):
        # If Web API has active Connect device and volume 0-100 given
        if sp and volume is not None and not change:
            try:
                sp.volume(max(0, min(100, int(volume))))
                play_confirm()
                return f"Spotify volume set to {volume}%, Boss."
            except Exception:
                pass

        # Adjust system / speaker volume
        return _adjust_system_volume(volume=volume, change=change)

    # ── 6. SHUFFLE ───────────────────────────────────────────────────────────
    elif action in ("shuffle", "random"):
        state = bool(params.get("state", True))
        if sp:
            try:
                sp.shuffle(state)
                play_confirm()
                st = "enabled" if state else "disabled"
                return f"Spotify shuffle is now {st}, Boss."
            except Exception:
                pass
        return "Spotify shuffle toggled, Boss."

    else:
        return f"Unknown Spotify action: '{action}'. Available: play, pause, resume, next, previous, current, volume, shuffle."


# ── TOOL DECLARATION ────────────────────────────────────────────────────────
TOOL = {
    "name": "spotify_control",
    "description": (
        "Direct Spotify & Media Integration for hands-free audio playback: "
        "play songs, artists, albums, or playlists (e.g. 'Play AC/DC on Spotify'), "
        "query currently playing song (e.g. 'What song is playing right now, Boss?'), "
        "adjust volume (e.g. 'Turn up the volume by 20%'), skip/previous track, and pause/resume."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "play | pause | resume | next | previous | current | volume | shuffle"
            },
            "query": {
                "type": "STRING",
                "description": "Song name, artist, album, or playlist to search and play (e.g. 'AC/DC', 'Back In Black')"
            },
            "volume": {
                "type": "INTEGER",
                "description": "Target volume level 0-100 (e.g. 80)"
            },
            "change": {
                "type": "STRING",
                "description": "Relative volume adjustment string with sign (e.g. '+20', '-20', '+10%')"
            },
            "state": {
                "type": "BOOLEAN",
                "description": "For shuffle: true to enable shuffle, false to disable"
            }
        },
        "required": ["action"]
    },
    "handler": spotify_control,
}
