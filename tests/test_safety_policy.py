"""
tests/test_safety_policy.py — Unit tests for neo/safety/policy.py.

Verifies:
- Path allow-list escapes: traversal (..), symlinks pointing outside, UNC paths, ADS streams.
- Disallowed file extensions (.exe, .bat, .ps1, etc.).
- Domain allow-list checks and prefix spoofing defenses.
- Risky-action detector covering all 10 categories across element names, window titles, and typed text.
- Hard-stop detection for payments, OTP, passwords, CAPTCHA, UAC, and final submit/confirm buttons.
"""
from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from neo.safety.policy import (
    detect_risks,
    is_app_allowed,
    validate_domain,
    validate_path,
)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Allow-List & Escapes Tests
# ─────────────────────────────────────────────────────────────────────────────
def test_path_allowlist_valid():
    """Verifies standard valid files inside allowed folder are permitted."""
    with TemporaryDirectory() as tmpdir:
        safe_file = Path(tmpdir) / "notes.txt"
        safe_file.write_text("hello world")

        res = validate_path(str(safe_file), allowed_folders=[tmpdir])
        assert res.is_allowed is True
        assert res.resolved_path == str(safe_file.resolve())


def test_path_allowlist_traversal_escape():
    """Verifies that relative path traversal (..\\) escaping allowed folders is blocked."""
    with TemporaryDirectory() as safe_dir, TemporaryDirectory() as outside_dir:
        outside_file = Path(outside_dir) / "secret.txt"
        outside_file.write_text("secret")

        # Construct traversal path starting in safe_dir but escaping to outside_dir
        rel_traversal = os.path.relpath(str(outside_file), safe_dir)
        traversal_path = os.path.join(safe_dir, rel_traversal)

        res = validate_path(traversal_path, allowed_folders=[safe_dir])
        assert res.is_allowed is False
        assert "outside allowed folders" in res.reason


def test_path_allowlist_unc_escape():
    """Verifies that UNC network share paths (\\\\server\\share) are strictly blocked."""
    unc_path = r"\\attacker.com\share\payload.txt"
    res = validate_path(unc_path, allowed_folders=[r"C:\safe"])
    assert res.is_allowed is False
    assert "UNC remote share paths" in res.reason


def test_path_allowlist_alternate_data_stream_escape():
    """Verifies that NTFS Alternate Data Streams (ADS) are detected and blocked."""
    ads_path = r"C:\safe\document.txt:hidden_payload.exe"
    res = validate_path(ads_path, allowed_folders=[r"C:\safe"])
    assert res.is_allowed is False
    assert "Alternate Data Stream" in res.reason


def test_path_allowlist_disallowed_executable_extensions():
    """Verifies that executable extensions (.exe, .bat, .cmd, .ps1, .vbs) are blocked."""
    with TemporaryDirectory() as safe_dir:
        for ext in (".exe", ".bat", ".cmd", ".ps1", ".vbs", ".msi", ".reg"):
            target = os.path.join(safe_dir, f"script{ext}")
            res = validate_path(target, allowed_folders=[safe_dir], allow_executables=False)
            assert res.is_allowed is False
            assert "extension" in res.reason.lower()


def test_path_allowlist_symlink_escape():
    """Verifies that symlinks created inside an allowed folder pointing outside are blocked."""
    with TemporaryDirectory() as safe_dir, TemporaryDirectory() as outside_dir:
        outside_target = Path(outside_dir) / "target.txt"
        outside_target.write_text("outside data")

        symlink_path = Path(safe_dir) / "link_to_outside.txt"
        try:
            os.symlink(str(outside_target), str(symlink_path))
        except (OSError, NotImplementedError):
            pytest.skip("Symlink creation not supported without admin/dev rights on this environment.")

        res = validate_path(str(symlink_path), allowed_folders=[safe_dir])
        assert res.is_allowed is False
        assert "outside allowed folders" in res.reason


def test_domain_allowlist_validation():
    """Verifies URL scheme and domain allow-listing including subdomain and spoofing defenses."""
    allowed = ["google.com", "github.com"]

    # Valid exact and subdomains
    assert validate_domain("https://google.com/search?q=test", allowed).is_allowed is True
    assert validate_domain("https://api.github.com/repos", allowed).is_allowed is True
    assert validate_domain("http://mail.google.com", allowed).is_allowed is True

    # Prefix/suffix domain spoofing attempts
    res_spoof1 = validate_domain("https://attacker-google.com", allowed)
    assert res_spoof1.is_allowed is False
    assert "not in the allowed domains" in res_spoof1.reason

    res_spoof2 = validate_domain("https://github.com.attacker.com", allowed)
    assert res_spoof2.is_allowed is False

    # Blocked dangerous schemes
    assert validate_domain("javascript:alert(1)", allowed).is_allowed is False
    assert validate_domain("data:text/html,evil", allowed).is_allowed is False
    assert validate_domain("file:///C:/Windows/System32", allowed).is_allowed is False


def test_app_allowlist():
    """Verifies normalized application allow-list matching."""
    allowed = ["notepad.exe", "calc.exe", "code.exe"]
    assert is_app_allowed("notepad.exe", allowed) is True
    assert is_app_allowed("Notepad", allowed) is True
    assert is_app_allowed(r"C:\Windows\System32\calc.exe", allowed) is True
    assert is_app_allowed("powershell.exe", allowed) is False
    assert is_app_allowed("cmd.exe", allowed) is False


# ─────────────────────────────────────────────────────────────────────────────
# 2. Risky-Action Detection Tests (All 10 Categories)
# ─────────────────────────────────────────────────────────────────────────────
def test_risky_detector_delete():
    # Element name
    r1 = detect_risks(element_name="Delete Repository")
    assert r1.is_risky is True
    assert "delete" in r1.risk_categories

    # Typed text
    r2 = detect_risks(typed_text="rmdir /s /q C:\\data")
    assert r2.is_risky is True
    assert "delete" in r2.risk_categories


def test_risky_detector_send():
    r = detect_risks(element_name="Send Email Broadcast")
    assert r.is_risky is True
    assert "send" in r.risk_categories


def test_risky_detector_pay_and_buy():
    r1 = detect_risks(element_name="Pay Invoice")
    assert r1.is_risky is True
    assert "pay" in r1.risk_categories

    r2 = detect_risks(element_name="Buy Yearly Subscription")
    assert r2.is_risky is True
    assert "buy" in r2.risk_categories


def test_risky_detector_install_and_uninstall():
    r1 = detect_risks(window_title="Setup and Install Wizard")
    assert r1.is_risky is True
    assert "install" in r1.risk_categories

    r2 = detect_risks(typed_text="pip uninstall package")
    assert r2.is_risky is True
    assert "uninstall" in r2.risk_categories


def test_risky_detector_format():
    r = detect_risks(typed_text="format D: /fs:NTFS")
    assert r.is_risky is True
    assert "format" in r.risk_categories


def test_risky_detector_shutdown_and_signout():
    r1 = detect_risks(typed_text="shutdown /s /t 0")
    assert r1.is_risky is True
    assert "shutdown" in r1.risk_categories

    r2 = detect_risks(element_name="Sign Out of Account")
    assert r2.is_risky is True
    assert "sign_out" in r2.risk_categories


def test_risky_detector_permission_changes():
    r = detect_risks(typed_text="icacls file.txt /grant Everyone:F")
    assert r.is_risky is True
    assert "permission_changes" in r.risk_categories


# ─────────────────────────────────────────────────────────────────────────────
# 3. Hard Stop Detection Tests
# ─────────────────────────────────────────────────────────────────────────────
def test_hard_stop_detection_payments():
    r = detect_risks(element_name="Complete Order and Checkout")
    assert r.requires_hard_stop is True
    assert "payment" in r.hard_stop_categories


def test_hard_stop_detection_otp():
    r = detect_risks(window_title="Enter One-Time Password (2FA)")
    assert r.requires_hard_stop is True
    assert "otp" in r.hard_stop_categories


def test_hard_stop_detection_passwords():
    r = detect_risks(element_name="Master Password Input")
    assert r.requires_hard_stop is True
    assert "password" in r.hard_stop_categories


def test_hard_stop_detection_captcha():
    r = detect_risks(element_name="Verify you are human - Cloudflare Turnstile")
    assert r.requires_hard_stop is True
    assert "captcha" in r.hard_stop_categories


def test_hard_stop_detection_uac():
    r = detect_risks(window_title="User Account Control - Consent Prompt")
    assert r.requires_hard_stop is True
    assert "uac" in r.hard_stop_categories


def test_hard_stop_detection_final_confirm():
    r = detect_risks(element_name="Permanently Delete Account")
    assert r.requires_hard_stop is True
    assert "final_confirm" in r.hard_stop_categories


def test_standard_non_risky_action():
    r = detect_risks(
        element_name="Scroll Down",
        window_title="Calculator",
        action_name="scroll",
    )
    assert r.is_risky is False
    assert r.requires_hard_stop is False
    assert len(r.risk_categories) == 0
