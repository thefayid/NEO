"""
neo/safety/policy.py — Security Policies, Allow-Lists, and Risky-Action Detection.

Enforces:
1. Allow-lists:
   - Applications: normalized allow-list checked against process/binary basenames.
   - Folders: path traversal defense (.., symlinks resolving outside, UNC paths, ADS).
   - Domains: strict hostname allow-list against http/https URLs.
2. Risky-Action Detection:
   - Categories: delete, send, pay, buy, install, uninstall, format, shutdown, sign_out, permission_changes.
   - Multi-surface inspection: element names, window titles, and typed text.
3. Hard Stop Identification:
   - Identifies non-bypassable operations requiring manual human control
     (payments, OTP, passwords, CAPTCHA, UAC, final submit/confirm buttons).
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
from urllib.parse import urlparse

from neo.config import get_settings

logger = logging.getLogger("neo.safety.policy")

# ─────────────────────────────────────────────────────────────────────────────
# Disallowed File Extensions & Dangerous Schemes
# ─────────────────────────────────────────────────────────────────────────────
DISALLOWED_EXECUTABLE_EXTENSIONS: Set[str] = {
    ".exe", ".bat", ".cmd", ".ps1", ".vbs", ".js", ".wsf",
    ".scr", ".msi", ".com", ".pif", ".reg", ".hta", ".cpl",
    ".jar", ".vbe", ".jse", ".msc",
}

DISALLOWED_URI_SCHEMES: Set[str] = {
    "file", "javascript", "data", "vbscript", "shell", "powershell", "cmd",
}

DEFAULT_ALLOWED_DOMAINS: Set[str] = {
    "google.com",
    "github.com",
    "microsoft.com",
    "bing.com",
    "wikipedia.org",
    "stackoverflow.com",
    "python.org",
}


# ─────────────────────────────────────────────────────────────────────────────
# Risky Action & Hard Stop Regex Definitions
# ─────────────────────────────────────────────────────────────────────────────
RISKY_PATTERNS: Dict[str, re.Pattern] = {
    "delete": re.compile(
        r"\b(delete|remove|erase|destroy|wipe|trash|shred|drop\s+table|rmdir|del)\b",
        re.IGNORECASE,
    ),
    "send": re.compile(
        r"\b(send|submit|post|publish|dispatch|mail|email|push|broadcast)\b",
        re.IGNORECASE,
    ),
    "pay": re.compile(
        r"\b(pay|payment|checkout|wire|transfer|billing|invoice|deposit|withdraw)\b",
        re.IGNORECASE,
    ),
    "buy": re.compile(
        r"\b(buy|purchase|order|subscribe|upgrade\s+plan)\b",
        re.IGNORECASE,
    ),
    "install": re.compile(
        r"\b(install|setup|provision|deploy|download\s+and\s+run)\b",
        re.IGNORECASE,
    ),
    "uninstall": re.compile(
        r"\b(uninstall|deprovision|decommission|remove\s+program)\b",
        re.IGNORECASE,
    ),
    "format": re.compile(
        r"\b(format|repartition|fdisk|mkfs|diskpart)\b",
        re.IGNORECASE,
    ),
    "shutdown": re.compile(
        r"\b(shutdown|power\s*off|reboot|restart\s+system|halt)\b",
        re.IGNORECASE,
    ),
    "sign_out": re.compile(
        r"\b(sign\s*out|log\s*off|lock\s+workstation|switch\s+user)\b",
        re.IGNORECASE,
    ),
    "permission_changes": re.compile(
        r"\b(grant|revoke|chmod|chown|takeown|icacls|set-acl|elevat(e|ion)|runas|administrator\s+privilege)\b",
        re.IGNORECASE,
    ),
}

HARD_STOP_PATTERNS: Dict[str, re.Pattern] = {
    "payment": re.compile(
        r"\b(pay\s+now|checkout|complete\s+order|place\s+order|credit\s*card|debit\s*card|cvv|billing\s*info|make\s+payment)\b",
        re.IGNORECASE,
    ),
    "otp": re.compile(
        r"\b(otp|one[- ]time\s*password|2fa|mfa|authenticator\s*code|verification\s*code|sms\s*code|security\s*code)\b",
        re.IGNORECASE,
    ),
    "password": re.compile(
        r"\b(password|passcode|pin|secret\s*key|master\s*password|credential)\b",
        re.IGNORECASE,
    ),
    "captcha": re.compile(
        r"\b(captcha|recaptcha|hcaptcha|turnstile|cloudflare|verify\s+you\s+are\s+human|bot\s+detection|puzzle)\b",
        re.IGNORECASE,
    ),
    "uac": re.compile(
        r"\b(user\s*account\s*control|consent\.exe|credentialuibroker\.exe|run\s+as\s+administrator|elevation)\b",
        re.IGNORECASE,
    ),
    "final_confirm": re.compile(
        r"\b(confirm\s+purchase|place\s+order|final\s+submit|transfer\s+now|delete\s+account|permanently\s+delete|erase\s+all)\b",
        re.IGNORECASE,
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# Data Models
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class PathValidationResult:
    """Outcome of a file/folder allow-list check."""
    is_allowed: bool
    resolved_path: Optional[str] = None
    reason: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)

    @property
    def rejection_reason(self) -> str:
        return self.reason


@dataclass
class DomainValidationResult:
    """Outcome of a domain allow-list check."""
    is_allowed: bool
    domain: Optional[str] = None
    reason: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)

    @property
    def rejection_reason(self) -> str:
        return self.reason


@dataclass
class RiskAssessment:
    """Outcome of action risk analysis across element name, window title, and text."""
    is_risky: bool
    requires_hard_stop: bool
    risk_categories: List[str] = field(default_factory=list)
    hard_stop_categories: List[str] = field(default_factory=list)
    matched_patterns: List[str] = field(default_factory=list)
    summary: str = "Action is non-risky."
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_risky": self.is_risky,
            "requires_hard_stop": self.requires_hard_stop,
            "risk_categories": self.risk_categories,
            "hard_stop_categories": self.hard_stop_categories,
            "matched_patterns": self.matched_patterns,
            "summary": self.summary,
            "evidence": self.evidence,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Allow-List Validators
# ─────────────────────────────────────────────────────────────────────────────
def is_app_allowed(app_name: str, allowed_apps: Optional[Sequence[str]] = None) -> bool:
    """
    Checks if an application binary or executable name is in the allow-list.
    Normalizes names (e.g. 'notepad.exe', 'Notepad') case-insensitively.
    """
    if not app_name or not app_name.strip():
        return False

    clean = Path(app_name.strip()).name.lower()
    allowed_list = allowed_apps if allowed_apps is not None else get_settings().allowed_apps
    allowed_lower = {a.strip().lower() for a in allowed_list}

    # Match exact filename or filename without extension
    stem = Path(clean).stem.lower()
    return clean in allowed_lower or stem in allowed_lower or (clean + ".exe") in allowed_lower


def validate_path(
    target_path: Union[str, Path],
    allowed_folders: Optional[Sequence[Union[str, Path]]] = None,
    allow_executables: bool = False,
) -> PathValidationResult:
    """
    Validates a file or directory path against allowed folder policies.
    Guarantees defenses against:
    - Path traversal (e.g. '..\\..\\secret.txt').
    - Symlinks pointing outside allowed directories.
    - UNC remote share paths (e.g. '\\\\attacker\\share').
    - NTFS Alternate Data Streams (ADS) (e.g. 'file.txt:hidden.exe').
    - Disallowed executable extensions.
    """
    if target_path is None:
        return PathValidationResult(is_allowed=False, reason="Target path is empty.")

    clean_str = str(target_path).strip()
    if not clean_str:
        return PathValidationResult(is_allowed=False, reason="Target path is empty.")

    # 1. Defend against UNC paths
    if clean_str.startswith(("\\\\", "//")):
        return PathValidationResult(
            is_allowed=False,
            reason="UNC remote share paths ('\\\\') are strictly prohibited.",
            evidence={"target": clean_str},
        )

    # 2. Defend against Alternate Data Streams (ADS)
    # Windows drive letters (C:) have colon at index 1; colons elsewhere indicate ADS
    name_part = Path(clean_str).name
    if ":" in name_part:
        return PathValidationResult(
            is_allowed=False,
            reason=f"Alternate Data Stream (ADS) detected in '{name_part}'. Access is blocked.",
            evidence={"target": clean_str},
        )

    # 3. Defend against disallowed executable extensions
    ext = Path(clean_str).suffix.lower()
    if not allow_executables and ext in DISALLOWED_EXECUTABLE_EXTENSIONS:
        return PathValidationResult(
            is_allowed=False,
            reason=f"Executable file extension '{ext}' is disallowed.",
            evidence={"target": clean_str, "extension": ext},
        )

    # 4. Resolve symlinks and relative traversal segments
    try:
        resolved = Path(clean_str).resolve(strict=False)
    except Exception as e:
        return PathValidationResult(
            is_allowed=False,
            reason=f"Path resolution error: {e}",
            evidence={"target": clean_str},
        )

    folders_list = allowed_folders if allowed_folders is not None else get_settings().allowed_folders
    if not folders_list:
        return PathValidationResult(
            is_allowed=False,
            reason="No allowed folders configured.",
            evidence={"target": str(resolved)},
        )

    # Check if resolved path is contained within at least one allowed directory
    is_within = False
    matched_folder = ""
    for folder in folders_list:
        try:
            folder_res = Path(folder).resolve(strict=False)
            if resolved == folder_res or resolved.is_relative_to(folder_res):
                is_within = True
                matched_folder = str(folder_res)
                break
        except Exception:
            continue

    if not is_within:
        return PathValidationResult(
            is_allowed=False,
            resolved_path=str(resolved),
            reason=f"Path '{resolved}' is outside allowed folders.",
            evidence={"resolved": str(resolved), "target": clean_str},
        )

    return PathValidationResult(
        is_allowed=True,
        resolved_path=str(resolved),
        reason="Path is valid and contained within allowed folder.",
        evidence={"resolved": str(resolved), "allowed_folder": matched_folder},
    )


def validate_domain(
    url: str,
    allowed_domains: Optional[Sequence[str]] = None,
) -> DomainValidationResult:
    """
    Validates a URL against domain allow-list policies.
    Guarantees:
    - Only 'http' and 'https' schemes are permitted (blocks 'javascript:', 'file:', 'data:').
    - Exact hostname or true subdomain match (blocks prefix spoofing like 'attacker-google.com').
    """
    if not url or not url.strip():
        return DomainValidationResult(is_allowed=False, reason="URL is empty.")

    clean_url = url.strip()
    try:
        parsed = urlparse(clean_url)
    except Exception as e:
        return DomainValidationResult(is_allowed=False, reason=f"URL parsing failed: {e}")

    # Check scheme
    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        return DomainValidationResult(
            is_allowed=False,
            reason=f"Blocked scheme '{scheme}:'. Only http and https URLs are permitted.",
            evidence={"url": clean_url, "scheme": scheme},
        )

    hostname = (parsed.hostname or "").lower().strip()
    if not hostname:
        return DomainValidationResult(
            is_allowed=False,
            reason="No valid hostname found in URL.",
            evidence={"url": clean_url},
        )

    if allowed_domains is not None:
        domains = set(allowed_domains)
    else:
        try:
            settings_domains = get_settings().allowed_domains
            domains = set(settings_domains) if settings_domains else DEFAULT_ALLOWED_DOMAINS
        except Exception:
            domains = DEFAULT_ALLOWED_DOMAINS
    domains_lower = {d.strip().lower() for d in domains}

    # Strict domain and subdomain matching
    matched = False
    for allowed_d in domains_lower:
        if hostname == allowed_d or hostname.endswith("." + allowed_d):
            matched = True
            break

    if not matched:
        return DomainValidationResult(
            is_allowed=False,
            domain=hostname,
            reason=f"Domain '{hostname}' is not in the allowed domains whitelist.",
            evidence={"hostname": hostname, "url": clean_url},
        )

    return DomainValidationResult(
        is_allowed=True,
        domain=hostname,
        reason=f"Domain '{hostname}' is allowed.",
        evidence={"hostname": hostname, "url": clean_url},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Risky Action & Hard Stop Detector
# ─────────────────────────────────────────────────────────────────────────────
def detect_risks(
    element_name: Optional[str] = None,
    window_title: Optional[str] = None,
    typed_text: Optional[str] = None,
    action_name: Optional[str] = None,
    target: Optional[str] = None,
) -> RiskAssessment:
    """
    Inspects multiple surfaces (element name, window title, typed text, action name, target)
    to classify risky operations and identify non-bypassable hard stops.
    """
    surfaces: Dict[str, str] = {}
    if element_name:
        surfaces["element_name"] = element_name
    if window_title:
        surfaces["window_title"] = window_title
    if typed_text:
        surfaces["typed_text"] = typed_text
    if target:
        surfaces["target"] = target
    if action_name:
        surfaces["action_name"] = action_name

    combined_text = " | ".join(surfaces.values())

    risk_categories: List[str] = []
    hard_stop_categories: List[str] = []
    matched_patterns: List[str] = []

    # 1. Evaluate Hard Stops (Non-bypassable gates)
    for cat, pattern in HARD_STOP_PATTERNS.items():
        m = pattern.search(combined_text)
        if m:
            hard_stop_categories.append(cat)
            matched_patterns.append(f"hard_stop:{cat}:{m.group(0)}")

    # 2. Evaluate General Risky Action Categories
    for cat, pattern in RISKY_PATTERNS.items():
        m = pattern.search(combined_text)
        if m:
            risk_categories.append(cat)
            matched_patterns.append(f"risky:{cat}:{m.group(0)}")

    is_risky = len(risk_categories) > 0 or len(hard_stop_categories) > 0
    requires_hard_stop = len(hard_stop_categories) > 0

    if requires_hard_stop:
        summary = (
            f"CRITICAL HARD STOP: Action matches sensitive categories "
            f"[{', '.join(hard_stop_categories)}]. Immediate human control required."
        )
    elif is_risky:
        summary = (
            f"RISKY ACTION DETECTED: Action matches categories "
            f"[{', '.join(risk_categories)}]. Confirmation gate required."
        )
    else:
        summary = "Action is standard and non-risky."

    return RiskAssessment(
        is_risky=is_risky,
        requires_hard_stop=requires_hard_stop,
        risk_categories=risk_categories,
        hard_stop_categories=hard_stop_categories,
        matched_patterns=matched_patterns,
        summary=summary,
        evidence={"surfaces": surfaces, "combined_text": combined_text},
    )
