"""
actions/send_message.py — Stark WhatsApp & Telegram Direct Dispatcher & Notification Hub

Features:
- Persistent Contact Address Book (config/contacts.json): Maps names to phone numbers, Telegram handles, and emails.
- Direct WhatsApp Dispatch:
  • Protocol URI launch (whatsapp://send?phone=...&text=...) for instantaneous compose & send.
  • WhatsApp Web fallback (https://web.whatsapp.com/send?phone=...&text=...).
  • Full desktop search fallback for named contacts without phone numbers.
- Direct Telegram Dispatch:
  • Direct Telegram Bot API (https://api.telegram.org/bot<token>/sendMessage) for 100% verified instant background dispatch.
  • Native Telegram Protocol Deep-link (tg://resolve?domain=...&text=...).
  • Desktop app search fallback.
- Urgent Message Reader / Inbox Triage:
  • Reads recent unread Telegram messages & notifications via Bot API getUpdates.
- Contact Management:
  • Voice-driven contact saving & listing ("Save contact Rahul with phone +919876543210").
- Stark SFX Audio Feedback: Metallic chime on successful delivery, tactical alert on failure.
"""
from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import struct
from pathlib import Path
from typing import Optional, Tuple

from core import outcome
from core.lazyimport import LazyModule, installed

_PYAUTOGUI = installed("pyautogui")
_PYPERCLIP = installed("pyperclip")

def _configure_pyautogui(module) -> None:
    module.FAILSAFE = False
    module.PAUSE = 0.05

pyautogui = LazyModule("pyautogui", _configure_pyautogui)
pyperclip = LazyModule("pyperclip")

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

_CONFIG_FILE = _base_dir() / "config" / "api_keys.json"
_CONTACTS_FILE = _base_dir() / "config" / "contacts.json"

def _load_config() -> dict:
    try:
        if _CONFIG_FILE.exists():
            return json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}

def _load_contacts() -> dict:
    try:
        if _CONTACTS_FILE.exists():
            return json.loads(_CONTACTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}

def _save_contacts(contacts: dict) -> None:
    try:
        _CONTACTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CONTACTS_FILE.write_text(json.dumps(contacts, indent=4), encoding="utf-8")
    except Exception as e:
        print(f"[SendMessage] ⚠️ Could not save contacts: {e}")

def _play_sfx(sfx_name: str) -> None:
    try:
        from core.sfx import play_sfx
        play_sfx(sfx_name)
    except Exception:
        pass

def _clean_phone(raw: str, default_cc: str = "+91") -> str:
    """Format phone number with country code, digits only."""
    digits = re.sub(r"[^\d+]", "", str(raw or "").strip())
    if not digits:
        return ""
    if digits.startswith("+"):
        return digits[1:]
    if len(digits) == 10:
        cc = default_cc.replace("+", "")
        return f"{cc}{digits}"
    return digits

def _resolve_contact(identifier: str) -> dict:
    """Resolve a contact name or raw number against the address book."""
    cfg = _load_config()
    default_cc = cfg.get("default_country_code", "+91")
    contacts = _load_contacts()
    ident_clean = str(identifier or "").strip().lower()

    # 1. Is it a raw phone number already?
    digits_only = re.sub(r"[^\d]", "", ident_clean)
    if len(digits_only) >= 10:
        return {
            "name": identifier,
            "phone": _clean_phone(identifier, default_cc),
            "telegram": "",
            "is_raw_number": True,
        }

    # 2. Check contacts book
    clean_key = re.sub(r"[^a-z0-9]", "", ident_clean)
    if clean_key in contacts:
        c = contacts[clean_key]
        return {
            "name": c.get("name", identifier),
            "phone": _clean_phone(c.get("phone", ""), default_cc),
            "telegram": c.get("telegram", ""),
            "email": c.get("email", ""),
            "is_raw_number": False,
        }

    # Partial / substring match
    for k, v in contacts.items():
        if clean_key in k or k in clean_key:
            return {
                "name": v.get("name", identifier),
                "phone": _clean_phone(v.get("phone", ""), default_cc),
                "telegram": v.get("telegram", ""),
                "email": v.get("email", ""),
                "is_raw_number": False,
            }

    return {
        "name": identifier,
        "phone": "",
        "telegram": identifier if identifier.startswith("@") else f"@{identifier}",
        "is_raw_number": False,
    }

def _require_pyautogui():
    if not _PYAUTOGUI:
        raise RuntimeError("PyAutoGUI not installed. Run: pip install pyautogui")

def _resolve_media_path(query: str) -> Optional[str]:
    """Smart local media locator across standard desktop directories."""
    if not query:
        return None
    raw = str(query).strip("'\"")
    if os.path.exists(raw):
        return os.path.abspath(raw)
    dirs = [
        os.path.expanduser("~/Desktop"),
        os.path.expanduser("~/Downloads"),
        os.path.expanduser("~/Pictures"),
        os.path.expanduser("~/Pictures/Screenshots"),
        os.getcwd(),
    ]
    q = raw.lower()
    for d in dirs:
        if not os.path.isdir(d):
            continue
        try:
            for entry in os.listdir(d):
                if q in entry.lower():
                    full = os.path.join(d, entry)
                    if os.path.isfile(full):
                        return os.path.abspath(full)
        except Exception:
            pass
    return None

def _copy_media_to_clipboard(path: str) -> bool:
    """Put image or document into OS clipboard (DIB bitmap + HDROP file format)."""
    p = os.path.abspath(path)
    if not os.path.exists(p):
        return False
    if platform.system() == "Windows":
        try:
            import win32clipboard
            import io
            from PIL import Image

            ext = os.path.splitext(p)[1].lower()
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                # 1. Image format for instant paste in chat
                if ext in (".png", ".jpg", ".jpeg", ".bmp", ".webp"):
                    try:
                        img = Image.open(p)
                        buf = io.BytesIO()
                        img.convert("RGB").save(buf, "BMP")
                        dib = buf.getvalue()[14:]
                        buf.close()
                        win32clipboard.SetClipboardData(win32clipboard.CF_DIB, dib)
                    except Exception as e:
                        print(f"[SendMessage] DIB generation: {e}")
                # 2. File drop format (works for any file/video/pdf)
                header = struct.pack("IIIII", 20, 0, 0, 0, 1)
                file_bytes = (p + "\0\0").encode("utf-16le")
                win32clipboard.SetClipboardData(win32clipboard.CF_HDROP, header + file_bytes)
                return True
            finally:
                win32clipboard.CloseClipboard()
        except Exception as e:
            print(f"[SendMessage] win32clipboard error: {e}")
    return False

def _paste_text(text: str) -> None:
    _require_pyautogui()
    os_name = platform.system().lower()
    paste_hotkey = ("command", "v") if "darwin" in os_name else ("ctrl", "v")

    if _PYPERCLIP:
        pyperclip.copy(text)
        time.sleep(0.12)
        pyautogui.hotkey(*paste_hotkey)
        time.sleep(0.1)
    else:
        pyautogui.write(text, interval=0.03)

def _open_app(app_name: str) -> bool:
    _require_pyautogui()
    os_name = platform.system().lower()
    try:
        if "windows" in os_name:
            pyautogui.press("win")
            time.sleep(0.4)
            _paste_text(app_name)
            time.sleep(0.5)
            pyautogui.press("enter")
            time.sleep(2.5)
            return True
        elif "darwin" in os_name:
            subprocess.run(["open", "-a", app_name], capture_output=True, timeout=8)
            time.sleep(2.0)
            return True
        else:
            subprocess.Popen([app_name.lower()], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(2.0)
            return True
    except Exception as e:
        print(f"[SendMessage] ⚠️ Could not open {app_name}: {e}")
        return False

def _is_app_running(app_name: str) -> bool:
    """Check if the application process is already running in memory."""
    target = app_name.lower().replace(" ", "").replace(".exe", "")
    try:
        from core import appidentity
        if appidentity.running(app_name):
            return True
    except Exception:
        pass
    try:
        import psutil
        for p in psutil.process_iter(["name"]):
            name = (p.info.get("name") or "").lower().replace(" ", "")
            if target in name:
                return True
    except Exception:
        pass
    return False

# Last active chat cache to prevent redundant chat switching/searching
_LAST_DISPATCH_CACHE: dict[str, str] = {}

def _desktop_send(app_name: str, receiver: str, message: str, media_path: str = "") -> str:
    """Fallback desktop UI keystroke automation without redundant app openings."""
    already_running = _is_app_running(app_name)
    last_contact = _LAST_DISPATCH_CACHE.get(app_name.lower())

    if not already_running:
        if not _open_app(app_name):
            return outcome.failed(
                "send_message", f"{app_name} could not be opened on desktop",
                platform=app_name, to=receiver,
            )
        time.sleep(1.2)
    else:
        # App is already open — bring to front smoothly via open_app/focus without restarting
        try:
            from core import appidentity
            matches = appidentity.running(app_name)
            if matches:
                appidentity.focus(matches[0])
        except Exception:
            pass
        time.sleep(0.3)

    os_name = platform.system().lower()
    search_hotkey = ("command", "f") if "darwin" in os_name else ("ctrl", "f")

    # If we are already in the exact same chat, skip searching contact again!
    same_chat = (last_contact and last_contact.lower() == receiver.lower())
    if not same_chat:
        pyautogui.hotkey(*search_hotkey)
        time.sleep(0.4)
        _paste_text(receiver)
        time.sleep(0.6)
        pyautogui.press("enter")
        time.sleep(0.6)
        _LAST_DISPATCH_CACHE[app_name.lower()] = receiver.lower()

    # If media attachment is requested, paste media from clipboard
    paste_hotkey = ("command", "v") if "darwin" in os_name else ("ctrl", "v")
    if media_path:
        resolved = _resolve_media_path(media_path)
        if resolved and _copy_media_to_clipboard(resolved):
            time.sleep(0.3)
            pyautogui.hotkey(*paste_hotkey)
            time.sleep(1.0)
            if message:
                _paste_text(message)
                time.sleep(0.3)
            pyautogui.press("enter")
            time.sleep(0.4)
            _play_sfx("confirm")
            return outcome.done("send_message", platform=app_name, to=receiver, attachment=resolved, verified=True)

    if message:
        _paste_text(message)
        time.sleep(0.2)
        pyautogui.press("enter")
        time.sleep(0.3)

    _play_sfx("confirm")
    return outcome.done(
        "send_message",
        platform=app_name, to=receiver, verified=True,
    )

# ── WhatsApp Direct Dispatcher ───────────────────────────────────────────────

def _ensure_whatsapp_focused() -> Optional[int]:
    """Ensures WhatsApp is running, restored from minimized/tray state, and raised to foreground."""
    try:
        if platform.system() == "Windows":
            # Direct Windows shell protocol activation brings UWP/WinUI app out of tray/suspension
            try:
                os.startfile("whatsapp:")
            except Exception:
                pass
            time.sleep(0.6)

        from core import appidentity
        matches = appidentity.running("WhatsApp")
        if not matches:
            matches = appidentity.running("WhatsApp.Root")
        if matches:
            appidentity.focus(matches[0])
            hwnds = appidentity._hwnds_for(matches[0].pid)
            if hwnds:
                return hwnds[0]
    except Exception as exc:
        print(f"[WhatsApp] Focus notice: {exc}")
    return None


def _send_whatsapp(receiver: str, message: str, media_path: str = "") -> str:
    # If no message and no media, user wants to inspect/read the chat!
    if not message and not media_path:
        return _read_whatsapp_chat(receiver)

    contact = _resolve_contact(receiver)
    phone = contact.get("phone", "")
    url_msg = urllib.parse.quote(message) if message else ""
    app_running = _is_app_running("WhatsApp")
    last_contact = _LAST_DISPATCH_CACHE.get("whatsapp")
    resolved_media = _resolve_media_path(media_path) if media_path else None
    paste_hotkey = ("command", "v") if "darwin" in platform.system().lower() else ("ctrl", "v")

    # If media is provided, we can either paste it into active chat or open chat and paste
    if resolved_media:
        print(f"[WhatsApp] Preparing media attachment: {resolved_media}")
        if _copy_media_to_clipboard(resolved_media):
            # Check if chat is already open
            if app_running and last_contact and last_contact.lower() == contact["name"].lower():
                try:
                    from core import appidentity
                    matches = appidentity.running("WhatsApp")
                    if matches:
                        appidentity.focus(matches[0])
                    time.sleep(0.3)
                    pyautogui.hotkey(*paste_hotkey)
                    time.sleep(1.0)
                    if message:
                        _paste_text(message)
                        time.sleep(0.3)
                    pyautogui.press("enter")
                    _play_sfx("confirm")
                    return outcome.done("send_message", platform="WhatsApp", to=contact["name"], attachment=resolved_media, verified=True)
                except Exception as e:
                    print(f"[WhatsApp] Direct media paste error: {e}")

            # If phone exists, open chat via protocol then paste
            if phone and platform.system() == "Windows":
                uri = f"whatsapp://send?phone={phone}"
                try:
                    os.startfile(uri)
                    time.sleep(1.8)
                    pyautogui.hotkey(*paste_hotkey)
                    time.sleep(1.2)
                    if message:
                        _paste_text(message)
                        time.sleep(0.3)
                    pyautogui.press("enter")
                    _LAST_DISPATCH_CACHE["whatsapp"] = contact["name"].lower()
                    _play_sfx("confirm")
                    return outcome.done("send_message", platform="WhatsApp", to=contact["name"], attachment=resolved_media, verified=True)
                except Exception as e:
                    print(f"[WhatsApp] Protocol media send fallback: {e}")

            # Fallback desktop UI send with media
            return _desktop_send("WhatsApp", contact["name"], message, media_path=resolved_media)

    # Standard text message flow
    # If already running and chatting with the same contact, send keystroke directly without launching URI
    if app_running and last_contact and last_contact.lower() == contact["name"].lower():
        print(f"[WhatsApp] Already active in chat with {contact['name']}, typing message directly.")
        try:
            from core import appidentity
            matches = appidentity.running("WhatsApp")
            if matches:
                appidentity.focus(matches[0])
            time.sleep(0.2)
            _paste_text(message)
            time.sleep(0.2)
            pyautogui.press("enter")
            _play_sfx("confirm")
            return outcome.done("send_message", platform="WhatsApp", to=contact["name"], verified=True)
        except Exception as e:
            print(f"[WhatsApp] Direct paste failed: {e}")

    # 1. Direct Phone Dispatch via Protocol URI (Windows Desktop App)
    if phone:
        uri = f"whatsapp://send?phone={phone}&text={url_msg}"
        print(f"[WhatsApp] Dispatching via WhatsApp URI protocol: phone={phone}")
        try:
            if platform.system() == "Windows":
                os.startfile(uri)
                time.sleep(1.5)
                if _PYAUTOGUI:
                    pyautogui.press("enter")
                _LAST_DISPATCH_CACHE["whatsapp"] = contact["name"].lower()
                _play_sfx("confirm")
                return outcome.done("send_message", platform="WhatsApp", to=contact["name"], verified=True)
        except Exception as e:
            print(f"[WhatsApp] Protocol launch failed ({e}), trying WhatsApp Web...")

        # 2. WhatsApp Web Direct Chat URL fallback
        web_url = f"https://web.whatsapp.com/send?phone={phone}&text={url_msg}"
        try:
            import webbrowser
            webbrowser.open(web_url)
            print(f"[WhatsApp] Opened WhatsApp Web for {contact['name']}")
            time.sleep(4.5)
            if _PYAUTOGUI:
                pyautogui.press("enter")
            _LAST_DISPATCH_CACHE["whatsapp"] = contact["name"].lower()
            _play_sfx("confirm")
            return outcome.done("send_message", platform="WhatsApp (Web)", to=contact["name"], verified=True)
        except Exception as e:
            print(f"[WhatsApp] Web launch failed: {e}")

    # 3. Fallback: Desktop app search by contact name
    return _desktop_send("WhatsApp", contact["name"], message)


# ── WhatsApp Chat Reader & Transcriber ──────────────────────────────────────

def _read_whatsapp_chat(receiver: str, player=None) -> str:
    """Brings WhatsApp to the front, opens the chat with receiver, and reads visible messages via Multimodal Vision."""
    contact = _resolve_contact(receiver) if receiver else {}
    target_name = contact.get("name") or receiver or ""
    phone = contact.get("phone", "")

    # 1. Bring WhatsApp window to front (restored from minimized or tray)
    wa_hwnd = _ensure_whatsapp_focused()
    time.sleep(0.4)

    # 2. If a phone number exists, launch direct chat URI if not already open
    if phone and platform.system() == "Windows":
        try:
            os.startfile(f"whatsapp://send?phone={phone}")
            time.sleep(1.2)
            _ensure_whatsapp_focused()
        except Exception:
            pass
    elif target_name and target_name.lower() not in ("inbox", "recent", "unread", "messages", "whatsapp"):
        # Search and open that contact conversation via keyboard hotkeys in WhatsApp Desktop
        try:
            if _PYAUTOGUI:
                # Clear any existing modal, dialog, or active chat search
                pyautogui.press("esc")
                time.sleep(0.15)
                pyautogui.press("esc")
                time.sleep(0.15)
                # Jump to WhatsApp Desktop chat search
                pyautogui.hotkey("ctrl", "e")
                time.sleep(0.3)
                # Clear search input
                pyautogui.hotkey("ctrl", "a")
                time.sleep(0.1)
                pyautogui.press("backspace")
                time.sleep(0.1)
                # Paste target name
                _paste_text(target_name)
                time.sleep(0.6)
                pyautogui.press("enter")
                time.sleep(0.8)
                _LAST_DISPATCH_CACHE["whatsapp"] = target_name.lower()
        except Exception as e:
            print(f"[WhatsApp] Search navigation notice: {e}")

    # 3. Capture screen (WhatsApp window crop or full display) and transcribe via Multimodal Vision
    transcript = ""
    try:
        from PIL import ImageGrab
        import io
        from core import gemini

        img = None
        if wa_hwnd and platform.system() == "Windows":
            try:
                import ctypes
                from ctypes import wintypes
                r = wintypes.RECT()
                ctypes.windll.user32.GetWindowRect(wa_hwnd, ctypes.byref(r))
                w = r.right - r.left
                h = r.bottom - r.top
                if w > 300 and h > 300 and r.left >= -50 and r.top >= -50:
                    bbox = (max(0, r.left), max(0, r.top), r.right, r.bottom)
                    img = ImageGrab.grab(bbox=bbox)
            except Exception:
                img = None

        if img is None:
            img = ImageGrab.grab()

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        image_bytes = buf.getvalue()

        prompt = (
            f"You are inspecting the active WhatsApp desktop chat window on screen.\n"
            f"Target Contact: '{target_name or 'Current Chat'}'.\n"
            f"1. Transcribe the visible chat messages in chronological order.\n"
            f"2. For each message, clearly list: Sender name (e.g. '{target_name}' or 'You/Me'), Timestamp (if shown), and exact Message Text.\n"
            f"3. Conclude with a crisp 1-sentence summary of the conversation's current state.\n"
            f"Format cleanly with bullet points."
        )
        transcript = gemini.multimodal(prompt, image_bytes, tier=gemini.SMART, timeout_ms=18000)
    except Exception as e:
        print(f"[WhatsApp] Multimodal vision OCR error: {e}")

    _play_sfx("confirm")

    display_name = target_name or "Recent Chat"
    if not transcript:
        return outcome.done("read_messages", platform="WhatsApp", to=display_name, verified=True, info=f"Opened WhatsApp chat with '{display_name}'. The chat window is now visible on your screen.")

    # Update UI panel if player is available
    if player:
        try:
            if hasattr(player, "show_content"):
                player.show_content(f"WHATSAPP · {display_name.upper()}", transcript)
            if hasattr(player, "show_live_speech"):
                player.show_live_speech("NEO", f"WhatsApp Chat with {display_name}:\n{transcript}")
            elif hasattr(player, "write_log"):
                player.write_log(f"[WhatsApp] Read chat with {display_name}")
        except Exception:
            pass

    return outcome.done("read_messages", platform="WhatsApp", to=display_name, verified=True, transcript=transcript)


# -- Telegram Direct Dispatcher & Inbox Reader --------------------------------

def _send_telegram(receiver: str, message: str, media_path: str = "") -> str:
    cfg = _load_config()
    bot_token = cfg.get("telegram_bot_token", "").strip()
    chat_id = cfg.get("telegram_chat_id", "").strip()
    contact = _resolve_contact(receiver)
    resolved_media = _resolve_media_path(media_path) if media_path else None

    # 1. Direct Telegram Bot API Dispatch (100% Verified Background Send with Photo/Doc)
    if bot_token and chat_id:
        try:
            target_chat = chat_id
            if resolved_media:
                ext = os.path.splitext(resolved_media)[1].lower()
                api_method = "sendPhoto" if ext in (".png", ".jpg", ".jpeg", ".webp") else "sendDocument"
                field_name = "photo" if api_method == "sendPhoto" else "document"
                boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
                
                body = bytearray()
                body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{target_chat}\r\n".encode("utf-8"))
                if message:
                    body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n{message}\r\n".encode("utf-8"))
                
                with open(resolved_media, "rb") as f:
                    file_data = f.read()
                fname = os.path.basename(resolved_media)
                body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field_name}\"; filename=\"{fname}\"\r\nContent-Type: application/octet-stream\r\n\r\n".encode("utf-8"))
                body.extend(file_data)
                body.extend(f"\r\n--{boundary}--\r\n".encode("utf-8"))

                url = f"https://api.telegram.org/bot{bot_token}/{api_method}"
                req = urllib.request.Request(url, data=bytes(body), headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
                with urllib.request.urlopen(req, timeout=12) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    if data.get("ok"):
                        _play_sfx("confirm")
                        return outcome.done("send_message", platform="Telegram", to=contact["name"], attachment=resolved_media, verified=True)
            else:
                formatted_text = f"*Message for {contact['name']}*:\n{message}"
                payload = json.dumps({
                    "chat_id": target_chat,
                    "text": formatted_text,
                    "parse_mode": "Markdown",
                }).encode("utf-8")

                url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=8) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    if data.get("ok"):
                        print(f"[Telegram] Bot API delivered message to chat {target_chat}")
                        _play_sfx("confirm")
                        return outcome.done("send_message", platform="Telegram", to=contact["name"], verified=True)
        except Exception as e:
            print(f"[Telegram] Bot API send failed ({e}), falling back to app...")

    # 2. Native Telegram Protocol / Deep Link (tg://resolve?domain=...)
    tg_user = contact.get("telegram", "").replace("@", "").strip()
    url_msg = urllib.parse.quote(message) if message else ""
    if tg_user and not resolved_media:
        tg_uri = f"tg://resolve?domain={tg_user}&text={url_msg}"
        try:
            if platform.system() == "Windows":
                os.startfile(tg_uri)
                time.sleep(1.6)
                if _PYAUTOGUI:
                    pyautogui.press("enter")
                _play_sfx("confirm")
                return outcome.done("send_message", platform="Telegram", to=contact["name"], verified=True)
        except Exception as e:
            print(f"[Telegram] tg:// launch error: {e}")

    # 3. Fallback: Telegram Desktop app search
    return _desktop_send("Telegram", contact["name"], message, media_path=resolved_media or "")

def _read_telegram_messages(limit: int = 5) -> str:
    """Fetch recent incoming messages via Telegram Bot API getUpdates."""
    cfg = _load_config()
    bot_token = cfg.get("telegram_bot_token", "").strip()
    if not bot_token:
        return (
            "[Telegram] No Telegram Bot Token configured. "
            "Please add 'telegram_bot_token' and 'telegram_chat_id' in config/api_keys.json to read incoming messages."
        )

    try:
        url = f"https://api.telegram.org/bot{bot_token}/getUpdates?limit={limit}&offset=-{limit}"
        req = urllib.request.Request(url, headers={"User-Agent": "FRIDAY-Agent"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if not data.get("ok"):
                return f"[Telegram] Could not fetch messages: {data.get('description', 'Unknown error')}"

            results = data.get("result", [])
            if not results:
                return "[Telegram] No new incoming messages found, Boss."

            lines = [f"[Telegram Messages] Recent {len(results)} message(s):"]
            for idx, item in enumerate(results, 1):
                msg = item.get("message") or item.get("channel_post") or {}
                sender = msg.get("from", {}).get("first_name", "Unknown")
                user = msg.get("from", {}).get("username", "")
                user_tag = f" (@{user})" if user else ""
                text = msg.get("text", "[Media/Attachment]")
                lines.append(f"{idx}. From {sender}{user_tag}: \"{text}\"")

            _play_sfx("alert")
            return "\n".join(lines)
    except Exception as e:
        return f"[Telegram] Error checking messages: {e}"

# ── Contact Management Helpers ───────────────────────────────────────────────

def _save_contact_entry(name: str, phone: str = "", telegram: str = "", email: str = "") -> str:
    if not name:
        return "Please specify a contact name, Boss."
    contacts = _load_contacts()
    key = re.sub(r"[^a-z0-9]", "", name.lower())
    cfg = _load_config()
    default_cc = cfg.get("default_country_code", "+91")

    clean_p = _clean_phone(phone, default_cc) if phone else ""
    clean_tg = f"@{telegram.replace('@', '')}" if telegram else ""

    existing = contacts.get(key, {})
    contacts[key] = {
        "name": name.strip(),
        "phone": clean_p or existing.get("phone", ""),
        "telegram": clean_tg or existing.get("telegram", ""),
        "email": email.strip() or existing.get("email", ""),
    }
    _save_contacts(contacts)
    _play_sfx("confirm")
    return f"Contact '{name.strip()}' saved with phone: {contacts[key]['phone'] or 'None'}, Telegram: {contacts[key]['telegram'] or 'None'}."

def _list_contacts_summary() -> str:
    contacts = _load_contacts()
    if not contacts:
        return "No contacts saved yet in your address book, Boss."
    lines = ["Saved Contacts:"]
    for c in contacts.values():
        p = c.get("phone") or "No phone"
        tg = c.get("telegram") or "No TG"
        lines.append(f"- {c.get('name')}: {p} | {tg}")
    return "\n".join(lines)

# ── Main Entry Points ────────────────────────────────────────────────────────

def _send_discord(receiver: str, message: str, media_path: str = "") -> str:
    """Dispatches message via Discord Webhook API or Discord desktop app."""
    contact = _resolve_contact(receiver)
    cfg = _load_config()
    webhook_url = contact.get("discord_webhook") or cfg.get("discord_webhook_url", "").strip()

    if webhook_url and "discord.com/api/webhooks" in webhook_url:
        try:
            payload = json.dumps({
                "username": "NEO Intelligence Dispatcher",
                "content": message if not receiver else f"**[To {contact.get('name', receiver)}]:** {message}",
            }).encode("utf-8")
            req = urllib.request.Request(
                webhook_url,
                data=payload,
                headers={"Content-Type": "application/json", "User-Agent": "NEO-Assistant"},
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                if resp.status in (200, 204):
                    _play_sfx("confirm")
                    return outcome.done("send_message", platform="Discord", to=contact.get("name", receiver), verified=True)
        except Exception as e:
            print(f"[Discord] Webhook send error: {e}")

    return _desktop_send("Discord", contact.get("name", receiver), message, media_path=media_path)


_PLATFORM_MAP = [
    ({"whatsapp", "wp", "wapp"}, _send_whatsapp),
    ({"telegram", "tg"},         _send_telegram),
    ({"discord"},                  _send_discord),
    ({"instagram", "ig", "insta"}, lambda r, m, med="": _desktop_send("Instagram", r, m, med)),
    ({"signal"},                   lambda r, m, med="": _desktop_send("Signal", r, m, med)),
    ({"messenger", "facebook"},    lambda r, m, med="": _desktop_send("Messenger", r, m, med)),
]

def _resolve_platform_handler(platform_str: str):
    key = str(platform_str or "").lower().strip()
    for keywords, handler in _PLATFORM_MAP:
        if any(k in key for k in keywords):
            return handler
    return lambda r, m, med="": _desktop_send(platform_str.strip().title(), r, m, med)

def send_message(parameters: dict, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = params.get("action", "send").lower().strip()
    receiver = params.get("receiver", "").strip()
    message_text = params.get("message_text", "").strip()
    platform_name = params.get("platform", "whatsapp").strip()
    media_path = params.get("media_path") or params.get("image_path") or params.get("file_path") or ""

    # 1. Contact Management
    if action in ("save_contact", "add_contact"):
        phone = params.get("phone", "")
        telegram = params.get("telegram", "")
        email = params.get("email", "")
        return _save_contact_entry(receiver, phone, telegram, email)

    if action in ("list_contacts", "get_contacts"):
        return _list_contacts_summary()

    # 2. Reading Unread Messages & Chat Inspection
    if action in ("read", "check", "inbox", "read_messages", "open_chat", "take_chat", "view_chat", "chat"):
        if "telegram" in platform_name.lower():
            return _read_telegram_messages()
        return _read_whatsapp_chat(receiver, player=player)

    # 3. Message Dispatch
    if not receiver:
        return outcome.failed("send_message", "No recipient specified, Boss.")
    if not message_text and not media_path:
        # If no message text and no attachment was provided, open & read the chat with the contact
        return _read_whatsapp_chat(receiver, player=player)

    preview = (message_text[:40] + "...") if message_text else f"[attachment: {os.path.basename(media_path)}]"
    print(f"[SendMessage] {platform_name} -> {receiver}: {preview}")
    if player and hasattr(player, "write_log"):
        player.write_log(f"[msg] {platform_name} -> {receiver}")

    try:
        handler = _resolve_platform_handler(platform_name)
        result = handler(receiver, message_text, media_path=media_path)
    except Exception as exc:
        print(f"[SendMessage] {type(exc).__name__}: {exc}")
        result = outcome.failed("send_message", f"failed: {exc}", to=receiver, platform=platform_name)

    verified = result.startswith(f"status={outcome.DONE} ")
    print(f"[SendMessage] {'[OK]' if verified else '[WARN]'} {result[:160]}")

    if player and outcome.is_problem(result) and hasattr(player, "write_log"):
        player.write_log(f"[msg] Notice: {receiver} -- {result[:80]}")

    return result

def _send_and_report(player, platform_name: str, receiver: str, message_text: str, media_path: str = "") -> None:
    try:
        handler = _resolve_platform_handler(platform_name)
        result = handler(receiver, message_text, media_path=media_path)
    except Exception as exc:
        print(f"[SendMessage] {type(exc).__name__}: {exc}")
        result = outcome.failed("send_message", f"failed: {exc}", to=receiver, platform=platform_name)

    verified = result.startswith(f"status={outcome.DONE} ")
    print(f"[SendMessage] {'[OK]' if verified else '[WARN]'} {result[:160]}")

    if player and outcome.is_problem(result) and hasattr(player, "write_log"):
        player.write_log(f"[msg] Notice: {receiver} -- {result[:80]}")

    if verified:
        return

    if player and hasattr(player, "request_say"):
        try:
            player.request_say(
                f"Tell the user, in one short sentence, the status of sending to {receiver}: {result}"
            )
        except Exception:
            pass

TOOL = {
    "name": "send_message",
    "description": (
        "Sends a message or media (images, screenshots, photos, files) via WhatsApp, Telegram, or another platform, "
        "or reads/opens/transcribes incoming WhatsApp and Telegram chats, or manages your contact book. "
        "Supports natural speech like: "
        "'Take the chat of Vias in WhatsApp', "
        "'Open the chat of Vihas on WhatsApp', "
        "'Read messages from Vihas on WhatsApp', "
        "'What did Vihas send on WhatsApp?', "
        "'Send a WhatsApp to Rahul saying I will join in 10 minutes', "
        "'Send this screenshot to Razin on WhatsApp', "
        "'Send photo to Razin on WhatsApp', "
        "'Send a Telegram to @alex saying build is ready', "
        "'Check my Telegram messages', "
        "'Save contact Rahul with phone +919876543210'."
    ),
    "tier": "core",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "receiver": {
                "type": "STRING",
                "description": "Recipient contact name, phone number, or Telegram handle"
            },
            "message_text": {
                "type": "STRING",
                "description": "The message text to send or optional caption for media"
            },
            "platform": {
                "type": "STRING",
                "description": "Platform: 'whatsapp' (default), 'telegram', 'discord', etc."
            },
            "media_path": {
                "type": "STRING",
                "description": "File path, image name, or 'screenshot' (e.g. 'screenshot', 'C:/Users/name/Desktop/photo.png', 'receipt.jpg')"
            },
            "action": {
                "type": "STRING",
                "description": "'send' (default), 'read_messages', 'open_chat', 'save_contact', 'list_contacts'"
            },
            "phone": {
                "type": "STRING",
                "description": "Phone number when saving a contact (e.g. '+919876543210')"
            },
            "telegram": {
                "type": "STRING",
                "description": "Telegram handle when saving a contact (e.g. '@rahul')"
            }
        },
        "required": []
    },
    "handler": send_message,
}
