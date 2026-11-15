"""
core/neo_key_rotator.py — Multi-API Key Pool & Seamless Quota Failover Engine for NEO.

Provides automatic zero-downtime key rotation for Google AI Studio / Gemini API:
1. Multi-Key Pool Discovery:
   - Reads `gemini_api_keys` (list or comma/newline separated string) or `gemini_api_key` from config.
   - Auto-deduplicates and masks keys for privacy.
2. Intelligent Quota Failover:
   - When a 429 / RESOURCE_EXHAUSTED / quota limit error occurs, automatically marks
     the exhausted key on cooldown and rotates to the next available working key in 0ms.
3. Live Session & REST Continuity:
   - Seamlessly supplies active working keys to `main.py` (Live WebSocket) and `core/gemini.py` (REST/one-shot vision).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple

if getattr(sys, "frozen", False):
    _BASE_DIR = Path(sys.executable).parent
else:
    _BASE_DIR = Path(__file__).resolve().parent.parent

_CONFIG_PATH = _BASE_DIR / "config" / "api_keys.json"
_DEFAULT_COOLDOWN_SECONDS = 3600.0  # 1 hour cooldown when quota is exhausted


class GeminiKeyPool:
    """Thread-safe multi-key pool with automatic quota rotation."""

    _instance: Optional["GeminiKeyPool"] = None
    _lock = Lock()

    def __new__(cls) -> "GeminiKeyPool":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._keys: List[str] = []
        self._active_index: int = 0
        self._cooldowns: Dict[str, float] = {}  # key -> monotonic expiry time
        self._pool_lock = Lock()
        self._last_mtime: float = 0.0
        self.reload_keys()
        self._initialized = True

    def _check_disk_sync(self) -> None:
        """Auto-reloads keys from disk if api_keys.json was updated externally."""
        try:
            if _CONFIG_PATH.exists():
                mt = _CONFIG_PATH.stat().st_mtime
                if mt != self._last_mtime:
                    self.reload_keys()
        except Exception:
            pass

    def _parse_keys_from_config(self, data: Dict[str, Any]) -> List[str]:
        """Extracts and deduplicates all valid API keys from config data."""
        raw_candidates: List[str] = []

        # 1. Check array or string under 'gemini_api_keys'
        keys_field = data.get("gemini_api_keys")
        if isinstance(keys_field, list):
            for k in keys_field:
                if isinstance(k, str):
                    raw_candidates.append(k.strip())
        elif isinstance(keys_field, str):
            for part in keys_field.replace("\n", ",").split(","):
                raw_candidates.append(part.strip())

        # 2. Check singular 'gemini_api_key'
        single_field = data.get("gemini_api_key")
        if isinstance(single_field, str):
            for part in single_field.replace("\n", ",").split(","):
                raw_candidates.append(part.strip())
        elif isinstance(single_field, list):
            for k in single_field:
                if isinstance(k, str):
                    raw_candidates.append(k.strip())

        # Clean, validate, and deduplicate
        seen = set()
        clean_keys = []
        for k in raw_candidates:
            if k and len(k) > 15 and k not in seen and not k.startswith("YOUR_GEMINI"):
                seen.add(k)
                clean_keys.append(k)

        return clean_keys

    def reload_keys(self) -> None:
        """Reloads keys from disk while preserving active cooldowns."""
        with self._pool_lock:
            try:
                if _CONFIG_PATH.exists():
                    self._last_mtime = _CONFIG_PATH.stat().st_mtime
                    data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
                    keys = self._parse_keys_from_config(data)
                    if keys:
                        old_active = self._keys[self._active_index] if self._keys and 0 <= self._active_index < len(self._keys) else None
                        self._keys = keys
                        if old_active and old_active in keys:
                            self._active_index = keys.index(old_active)
                        elif self._active_index >= len(self._keys):
                            self._active_index = 0
            except Exception as e:
                print(f"[KeyPool] ⚠️ Failed loading {_CONFIG_PATH}: {e}")

    @staticmethod
    def mask_key(key: str) -> str:
        """Masks key for safe display/logging, e.g. AIzaSy...4xQ."""
        if not key:
            return "NONE"
        if len(key) <= 10:
            return key[:3] + "..." + key[-2:]
        return key[:6] + "..." + key[-4:]

    def get_keys(self) -> List[str]:
        """Returns list of all configured keys."""
        with self._pool_lock:
            self._check_disk_sync()
            return list(self._keys)

    def is_cooling(self, key: str) -> bool:
        """Checks if a key is currently on quota cooldown."""
        with self._pool_lock:
            until = self._cooldowns.get(key, 0.0)
            if until and time.monotonic() < until:
                return True
            self._cooldowns.pop(key, None)
            return False

    def get_active_key(self, auto_advance: bool = True) -> str:
        """
        Returns the current active API key. If current key is cooling and
        auto_advance is True, advances to the first available non-cooling key.
        """
        with self._pool_lock:
            self._check_disk_sync()
            if not self._keys:
                self.reload_keys()

            if not self._keys:
                return ""

            if self._active_index >= len(self._keys):
                self._active_index = 0

            # Check if active key is cooling
            active = self._keys[self._active_index]
            until = self._cooldowns.get(active, 0.0)
            now = time.monotonic()

            if until and now < until and auto_advance:
                # Find next non-cooling key
                for idx in range(len(self._keys)):
                    cand = self._keys[idx]
                    cand_until = self._cooldowns.get(cand, 0.0)
                    if not cand_until or now >= cand_until:
                        self._active_index = idx
                        self._cooldowns.pop(cand, None)
                        self._save_primary_key(cand)
                        return cand

            return active

    def rotate_key(
        self,
        reason: str = "quota_exhausted",
        cooldown_seconds: float = _DEFAULT_COOLDOWN_SECONDS
    ) -> Tuple[bool, str, str]:
        """
        Marks current key as cooling and rotates to the next available key.
        Returns: (success: bool, new_key: str, message: str)
        """
        with self._pool_lock:
            self._check_disk_sync()
            if not self._keys:
                self.reload_keys()

            if not self._keys:
                return False, "", "No Gemini API keys are configured."

            curr_key = self._keys[self._active_index]
            self._cooldowns[curr_key] = time.monotonic() + cooldown_seconds
            masked_prev = self.mask_key(curr_key)

            if len(self._keys) == 1:
                return (
                    False,
                    curr_key,
                    f"Only 1 API key ({masked_prev}) is configured; marked on cooldown due to: {reason}."
                )

            # Look for next available key
            now = time.monotonic()
            best_idx = None
            earliest_cool = float("inf")
            earliest_idx = None

            for step in range(1, len(self._keys)):
                idx = (self._active_index + step) % len(self._keys)
                cand = self._keys[idx]
                until = self._cooldowns.get(cand, 0.0)
                if not until or now >= until:
                    best_idx = idx
                    self._cooldowns.pop(cand, None)
                    break
                if until < earliest_cool:
                    earliest_cool = until
                    earliest_idx = idx

            # If all are cooling, pick the one expiring soonest
            target_idx = best_idx if best_idx is not None else (earliest_idx or 0)
            self._active_index = target_idx
            new_key = self._keys[self._active_index]
            masked_new = self.mask_key(new_key)

            # Persist primary active key to config so restarts keep the rotated key
            self._save_primary_key(new_key)

            msg = (
                f"Rotated key from #{self._active_index} ({masked_prev}) to "
                f"#{target_idx + 1} ({masked_new}) [Reason: {reason}]."
            )
            return True, new_key, msg

    def _save_primary_key(self, primary_key: str) -> None:
        """Updates primary key in config/api_keys.json while preserving all keys."""
        try:
            if _CONFIG_PATH.exists():
                data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
            else:
                data = {}
            data["gemini_api_key"] = primary_key
            data["gemini_api_keys"] = list(self._keys)
            _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            _CONFIG_PATH.write_text(json.dumps(data, indent=4), encoding="utf-8")
        except Exception:
            pass

    def add_keys(self, new_keys: List[str] | str) -> Tuple[int, str]:
        """
        Adds one or more keys to the pool and saves to config/api_keys.json.
        Returns: (added_count: int, message: str)
        """
        if isinstance(new_keys, str):
            candidates = [k.strip() for k in new_keys.replace("\n", ",").split(",") if k.strip()]
        else:
            candidates = [k.strip() for k in new_keys if k and k.strip()]

        with self._pool_lock:
            added = 0
            for k in candidates:
                if len(k) > 15 and k not in self._keys:
                    self._keys.append(k)
                    added += 1

            if self._keys:
                primary = self._keys[self._active_index]
                self._save_primary_key(primary)

            return added, f"Added {added} new key(s). Total in pool: {len(self._keys)}."

    def set_active_index(self, index: int) -> bool:
        """Sets the active key index directly."""
        with self._pool_lock:
            if 0 <= index < len(self._keys):
                self._active_index = index
                self._save_primary_key(self._keys[index])
                return True
            return False

    def remove_key(self, key_or_index: str | int) -> Tuple[bool, str]:
        """Removes a key from the pool and updates config."""
        with self._pool_lock:
            if len(self._keys) <= 1:
                return False, "Cannot remove the only remaining API key in the pool."

            target_key = None
            if isinstance(key_or_index, int):
                if 0 <= key_or_index < len(self._keys):
                    target_key = self._keys[key_or_index]
            else:
                target_key = key_or_index

            if not target_key or target_key not in self._keys:
                return False, "Key not found in pool."

            masked = self.mask_key(target_key)
            self._keys.remove(target_key)
            self._cooldowns.pop(target_key, None)

            if self._active_index >= len(self._keys):
                self._active_index = 0

            primary = self._keys[self._active_index]
            self._save_primary_key(primary)
            return True, f"Removed key {masked}. Total remaining: {len(self._keys)}."

    def get_status(self) -> Dict[str, Any]:
        """Returns comprehensive status of all keys in the pool."""
        with self._pool_lock:
            now = time.monotonic()
            summary = []
            available_cnt = 0
            for i, k in enumerate(self._keys):
                until = self._cooldowns.get(k, 0.0)
                is_cool = bool(until and now < until)
                remain_sec = int(max(0, until - now)) if is_cool else 0
                if not is_cool:
                    available_cnt += 1
                summary.append({
                    "index": i + 1,
                    "masked": self.mask_key(k),
                    "is_active": i == self._active_index,
                    "is_cooling": is_cool,
                    "cooldown_remaining_sec": remain_sec,
                })

            active_key = self._keys[self._active_index] if self._keys else ""
            return {
                "total_keys": len(self._keys),
                "available_keys": available_cnt,
                "cooling_keys": len(self._keys) - available_cnt,
                "active_key_index": self._active_index + 1 if self._keys else 0,
                "active_key_masked": self.mask_key(active_key),
                "keys": summary,
            }


# Global Singleton accessor
key_rotator = GeminiKeyPool()
