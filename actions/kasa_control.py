"""
actions/kasa_control.py — TP-Link Kasa & Smart Home Device Automation for F.R.I.D.A.Y.

Features:
- Auto-discovery of local TP-Link Kasa smart bulbs, plugs, and multi-plugs.
- Device Control: turn on/off, dim brightness (0-100), toggle state.
- Graceful standalone operation: discovers devices on the local LAN without hardcoded IP requirements.
- Natural speech: "turn on office lights", "set bedroom lights to 50%", "turn off desk plug".
"""
from __future__ import annotations

import asyncio
import json
import socket
import time
from typing import Any, Dict, List, Optional

from core import outcome

# Port for TP-Link Kasa discovery & communication
KASA_PORT = 9999

# Autodiscovery broadcast encryption/decryption keys for legacy Kasa protocol
INITIAL_KEY = 0xAB

# Cache discovered devices to eliminate 1.5s UDP scan lag on subsequent actions
_DEVICE_CACHE: List[Dict[str, Any]] = []
_CACHE_TIME: float = 0.0
_CACHE_TTL: float = 300.0  # 5 minutes


def _encrypt(data: str) -> bytes:
    key = INITIAL_KEY
    result = bytearray()
    for char in data:
        a = key ^ ord(char)
        key = a
        result.append(a)
    return bytes(result)


def _decrypt(data: bytes) -> str:
    key = INITIAL_KEY
    result = []
    for byte in data:
        a = key ^ byte
        key = byte
        result.append(chr(a))
    return "".join(result)


def _udp_broadcast(payload: str, timeout: float = 2.0) -> List[Dict[str, Any]]:
    """Broadcasts Kasa discovery probe on UDP 9999 and returns found devices."""
    devices = []
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(timeout)

    try:
        enc_data = _encrypt(payload)
        sock.sendto(enc_data, ("255.255.255.255", KASA_PORT))

        while True:
            try:
                raw, (ip, port) = sock.recvfrom(2048)
                dec_str = _decrypt(raw)
                try:
                    data = json.loads(dec_str)
                    sys_info = data.get("system", {}).get("get_sysinfo", {})
                    alias = sys_info.get("alias", "Smart Device")
                    is_on = sys_info.get("relay_state", sys_info.get("light_state", {}).get("on_off", 0)) == 1
                    devices.append({
                        "ip": ip,
                        "alias": alias,
                        "is_on": is_on,
                        "model": sys_info.get("model", "Kasa"),
                        "raw_info": sys_info,
                    })
                except Exception:
                    pass
            except socket.timeout:
                break
    except Exception as e:
        print(f"[Kasa] Discovery error: {e}")
    finally:
        sock.close()

    return devices


def _send_command(ip: str, cmd_dict: dict, timeout: float = 2.0) -> Optional[dict]:
    """Sends TCP JSON command to a specific Kasa device."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((ip, KASA_PORT))
        raw_cmd = json.dumps(cmd_dict)
        # First 4 bytes is length in big endian
        enc_payload = _encrypt(raw_cmd)
        header = len(enc_payload).to_bytes(4, byteorder="big")
        sock.sendall(header + enc_payload)

        # Read response length
        resp_len_bytes = sock.recv(4)
        if len(resp_len_bytes) < 4:
            return None
        resp_len = int.from_bytes(resp_len_bytes, byteorder="big")

        received = bytearray()
        while len(received) < resp_len:
            chunk = sock.recv(min(4096, resp_len - len(received)))
            if not chunk:
                break
            received.extend(chunk)

        dec_resp = _decrypt(bytes(received))
        return json.loads(dec_resp)
    except Exception as e:
        print(f"[Kasa] TCP send to {ip} failed: {e}")
        return None
    finally:
        sock.close()


def kasa_control(parameters: dict, player=None, session_memory=None) -> str:
    global _DEVICE_CACHE, _CACHE_TIME
    params = parameters or {}
    action = str(params.get("action", "scan")).lower().strip()
    target = str(params.get("device_name", "") or params.get("target", "")).lower().strip()
    brightness = params.get("brightness")

    now = time.monotonic()
    is_scan = action in ("scan", "list", "discover")
    cache_valid = bool(_DEVICE_CACHE) and (now - _CACHE_TIME < _CACHE_TTL)

    # Use cache if fresh and not explicitly scanning
    if not is_scan and cache_valid:
        devices = _DEVICE_CACHE
    else:
        discovery_cmd = '{"system":{"get_sysinfo":{}}}'
        devices = _udp_broadcast(discovery_cmd, timeout=1.5)
        if devices:
            _DEVICE_CACHE = devices
            _CACHE_TIME = now

    if is_scan:
        if not devices:
            msg = "No Kasa smart home devices detected on the local network, Boss."
            if player and hasattr(player, "write_log"):
                player.write_log(f"🏠 {msg}")
            return outcome.done("kasa_control", message=msg, count=0)

        lines = [f"Found {len(devices)} Kasa device(s):"]
        for d in devices:
            state = "ON" if d["is_on"] else "OFF"
            lines.append(f"• {d['alias']} ({d['model']}) @ {d['ip']} - [{state}]")
        msg = "\n".join(lines)
        if player and hasattr(player, "write_log"):
            player.write_log(f"🏠 {msg}")
        return outcome.done("kasa_control", devices=[d["alias"] for d in devices], count=len(devices))

    # Match target device
    matched = None
    if target:
        for d in devices:
            if target in d["alias"].lower() or d["alias"].lower() in target:
                matched = d
                break

    # If no target specified or not matched, pick first or all
    targets_to_act = [matched] if matched else devices
    if not targets_to_act:
        return outcome.failed("kasa_control", f"Could not find any Kasa device matching '{target}' on the network, Boss.")

    results = []
    for dev in targets_to_act:
        ip = dev["ip"]
        alias = dev["alias"]

        # Build payload
        if action in ("on", "turn_on"):
            cmd = {"system": {"set_relay_state": {"state": 1}}}
            # Also bulb compatibility
            cmd_bulb = {"smartlife.iot.smartbulb.lightingservice": {"transition_light_state": {"on_off": 1}}}
            _send_command(ip, cmd)
            _send_command(ip, cmd_bulb)
            results.append(f"{alias} turned ON")

        elif action in ("off", "turn_off"):
            cmd = {"system": {"set_relay_state": {"state": 0}}}
            cmd_bulb = {"smartlife.iot.smartbulb.lightingservice": {"transition_light_state": {"on_off": 0}}}
            _send_command(ip, cmd)
            _send_command(ip, cmd_bulb)
            results.append(f"{alias} turned OFF")

        elif action in ("toggle",):
            new_state = 0 if dev["is_on"] else 1
            cmd = {"system": {"set_relay_state": {"state": new_state}}}
            cmd_bulb = {"smartlife.iot.smartbulb.lightingservice": {"transition_light_state": {"on_off": new_state}}}
            _send_command(ip, cmd)
            _send_command(ip, cmd_bulb)
            results.append(f"{alias} toggled to {'ON' if new_state else 'OFF'}")

        elif brightness is not None:
            try:
                b_val = max(1, min(100, int(brightness)))
                cmd = {"smartlife.iot.smartbulb.lightingservice": {"transition_light_state": {"on_off": 1, "brightness": b_val}}}
                _send_command(ip, cmd)
                results.append(f"{alias} brightness set to {b_val}%")
            except Exception:
                pass

    summary = ", ".join(results) if results else "Kasa action processed."
    if player and hasattr(player, "write_log"):
        player.write_log(f"🏠 {summary}")

    return outcome.done("kasa_control", summary=summary, action=action)


TOOL = {
    "name": "kasa_control",
    "description": (
        "Controls TP-Link Kasa smart home devices (smart bulbs, smart plugs, light switches) on your local Wi-Fi. "
        "Supports turning devices on/off, adjusting brightness, toggling, or discovering devices on the network. "
        "Examples: 'turn on the desk lamp', 'turn off all lights', 'dim living room lights to 30%', 'find smart devices'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "'on', 'off', 'toggle', 'scan', 'brightness'"
            },
            "device_name": {
                "type": "STRING",
                "description": "Device name or room (e.g. 'office lamp', 'bedroom', 'desk plug', 'all')"
            },
            "brightness": {
                "type": "INTEGER",
                "description": "Brightness level (1-100) for smart bulbs"
            }
        },
        "required": ["action"]
    },
    "handler": kasa_control,
}

