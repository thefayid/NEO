"""
tests/test_browser_local_site.py — Comprehensive integration tests for neo.browser.

Spins up a lightweight local HTTP test server serving:
- /: Home index
- /forms: Forms with text inputs, password fields (redacted!), checkboxes, selects, and submit button
- /popups: Cookie consent banner with Reject button & modal dialog
- /delayed: Element that appears after 500ms
- /iframe: Nested iframe with interactive elements
- /payment: Sensitive payment/checkout page triggering HardStopRequiredError
"""
from __future__ import annotations

import http.server
import socketserver
import threading
import time
from pathlib import Path
from typing import Generator

import pytest

from neo.browser import (
    BrowserSnapshotRegistry,
    PlaywrightBrowser,
    PopupDismissConfig,
    StaleBrowserSnapshotError,
    dismiss_popups,
)
from neo.config import load_settings
from neo.safety.emergency_stop import emergency_stop
from neo.safety.gates import HardStopRequiredError

# ─────────────────────────────────────────────────────────────────────────────
# Local Test HTTP Server Pages
# ─────────────────────────────────────────────────────────────────────────────
HOME_HTML = """<!DOCTYPE html>
<html>
<head><title>NEO Test Web Suite</title></head>
<body>
  <h1>Welcome to NEO Browser Test Site</h1>
  <nav>
    <a href="/forms" id="linkForms">Forms Test</a>
    <a href="/popups" id="linkPopups">Popups Test</a>
    <a href="/delayed" id="linkDelayed">Delayed Elements</a>
    <a href="/iframe" id="linkIframe">Iframe Page</a>
    <a href="/payment" id="linkPayment">Payment Checkout</a>
  </nav>
  <button id="btnHomeAction">Click Me</button>
  <p id="homeMsg"></p>
  <script>
    document.getElementById('btnHomeAction').addEventListener('click', () => {
      document.getElementById('homeMsg').innerText = 'Action Verified';
    });
  </script>
</body>
</html>
"""

FORMS_HTML = """<!DOCTYPE html>
<html>
<head><title>Form Elements Test</title></head>
<body>
  <h2>Interactive Form</h2>
  <form id="mainForm" onsubmit="event.preventDefault(); document.getElementById('output').innerText = 'Submitted';">
    <label for="username">Username:</label>
    <input type="text" id="username" name="username" value=""><br><br>

    <label for="password">Password:</label>
    <input type="password" id="password" name="password" value=""><br><br>

    <label for="role">Role:</label>
    <select id="role" name="role">
      <option value="user">Standard User</option>
      <option value="admin">Administrator</option>
      <option value="guest">Guest</option>
    </select><br><br>

    <input type="checkbox" id="subscribe" name="subscribe">
    <label for="subscribe">Subscribe to newsletter</label><br><br>

    <button type="submit" id="submitBtn">Submit Form</button>
  </form>
  <div id="output">Ready</div>
</body>
</html>
"""

POPUPS_HTML = """<!DOCTYPE html>
<html>
<head><title>Popups and Cookies</title></head>
<body>
  <h1>Content with Cookie Banner</h1>
  <div id="cookieBanner" class="cookie-banner" style="background:#eee; padding:15px; border:1px solid #ccc;">
    <p>We value your privacy. Manage cookies below.</p>
    <button id="btnReject" onclick="document.getElementById('cookieBanner').style.display='none'; document.getElementById('status').innerText='Rejected';">Reject all</button>
    <button id="btnAccept" onclick="document.getElementById('cookieBanner').style.display='none'; document.getElementById('status').innerText='Accepted';">Accept all</button>
  </div>
  <p id="status">Banner Active</p>
</body>
</html>
"""

DELAYED_HTML = """<!DOCTYPE html>
<html>
<head><title>Delayed Element Test</title></head>
<body>
  <h1>Delayed Content</h1>
  <div id="container">
    <p id="statusMsg">Waiting for delayed action...</p>
  </div>
  <script>
    setTimeout(() => {
      const btn = document.createElement('button');
      btn.id = 'delayedBtn';
      btn.innerText = 'Now Available';
      document.getElementById('container').appendChild(btn);
      document.getElementById('statusMsg').innerText = 'Ready!';
    }, 400);
  </script>
</body>
</html>
"""

IFRAME_PARENT_HTML = """<!DOCTYPE html>
<html>
<head><title>Iframe Container</title></head>
<body>
  <h1>Main Page with Embedded Iframe</h1>
  <iframe id="childFrame" src="/iframe_child" width="400" height="250"></iframe>
</body>
</html>
"""

IFRAME_CHILD_HTML = """<!DOCTYPE html>
<html>
<head><title>Inside Iframe</title></head>
<body>
  <h3>Iframe Child Document</h3>
  <input type="text" id="frameInput" placeholder="Inside Frame">
  <button id="frameBtn" onclick="document.getElementById('frameInput').value='Frame Clicked';">Click Inside Frame</button>
</body>
</html>
"""

PAYMENT_HTML = """<!DOCTYPE html>
<html>
<head><title>Secure Checkout - Payment</title></head>
<body>
  <h1>Checkout & Payment</h1>
  <form id="paymentForm">
    <label for="card">Credit Card Number:</label>
    <input type="text" id="card" placeholder="Card Number"><br>
    <label for="cvv">CVV:</label>
    <input type="text" id="cvv" placeholder="CVV"><br>
    <button type="button" id="payNowBtn">Pay Now $99.00</button>
  </form>
</body>
</html>
"""


class _SiteHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        if path == "/":
            self._send_html(HOME_HTML)
        elif path == "/forms":
            self._send_html(FORMS_HTML)
        elif path == "/popups":
            self._send_html(POPUPS_HTML)
        elif path == "/delayed":
            self._send_html(DELAYED_HTML)
        elif path == "/iframe":
            self._send_html(IFRAME_PARENT_HTML)
        elif path == "/iframe_child":
            self._send_html(IFRAME_CHILD_HTML)
        elif path == "/payment":
            self._send_html(PAYMENT_HTML)
        else:
            self.send_response(404)
            self.end_headers()

    def _send_html(self, content: str) -> None:
        data = content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: Any) -> None:
        pass  # Suppress HTTP access logging in test output


@pytest.fixture(scope="module")
def local_web_server() -> Generator[str, None, None]:
    """Spins up a local HTTP test server on an ephemeral port."""
    server = socketserver.TCPServer(("127.0.0.1", 0), _SiteHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"

    # Allow 127.0.0.1 in NEO domain safety policy
    load_settings(allowed_domains=["127.0.0.1", "localhost"])

    yield base_url
    server.shutdown()
    server.server_close()


@pytest.fixture
def browser_instance():
    """Provides a fresh headless PlaywrightBrowser instance for testing."""
    emergency_stop.reset()
    b = PlaywrightBrowser(headless=True)
    b.start()
    yield b
    b.close()
    emergency_stop.reset()


# ─────────────────────────────────────────────────────────────────────────────
# Test Cases
# ─────────────────────────────────────────────────────────────────────────────
def test_snapshot_navigation_and_elements(browser_instance: PlaywrightBrowser, local_web_server: str):
    """Verifies goto, snapshot creation, numbered element listing, and URL/title capture."""
    b = browser_instance
    res = b.act({"action": "goto", "url": f"{local_web_server}/"})
    assert res.ok is True
    assert res.verified == "true"
    assert "NEO Test Web Suite" in res.evidence["title"]

    snap = b.snapshot()
    assert snap.snapshot_id.startswith("bsnap_")
    assert snap.url.startswith(f"{local_web_server}/")
    assert len(snap.elements) >= 5

    # Check button 'Click Me' presence
    btn = next((el for el in snap.elements if el.text == "Click Me"), None)
    assert btn is not None
    assert btn.tag_name == "button"
    assert btn.role == "button"


def test_forms_typing_select_and_password_redaction(browser_instance: PlaywrightBrowser, local_web_server: str):
    """Verifies typing with readback verification, select_option, and strict password redaction."""
    b = browser_instance
    b.act({"action": "goto", "url": f"{local_web_server}/forms"})
    snap = b.snapshot()

    # 1. Type into username
    user_elem = next(el for el in snap.elements if el.name == "Username:" or el.selector == "#username")
    type_res = b.act({
        "action": "type",
        "snapshot_id": snap.snapshot_id,
        "element_id": user_elem.id,
        "text": "alice_neo",
    })
    assert type_res.ok is True
    assert type_res.verified == "true"
    assert type_res.evidence["readback"] == "alice_neo"

    # 2. Verify password element is flagged and redacted
    pwd_elem = next(el for el in snap.elements if el.is_password)
    assert pwd_elem is not None
    assert pwd_elem.value == "[REDACTED]"

    # 3. Select option in dropdown
    role_elem = next(el for el in snap.elements if el.tag_name == "select" or el.selector == "#role")
    sel_res = b.act({
        "action": "select_option",
        "snapshot_id": snap.snapshot_id,
        "element_id": role_elem.id,
        "value": "admin",
    })
    assert sel_res.ok is True
    assert sel_res.verified == "true"
    assert sel_res.evidence["readback_value"] == "admin"


def test_stale_snapshot_id_rejection(browser_instance: PlaywrightBrowser, local_web_server: str):
    """Verifies that actions referencing obsolete snapshot IDs are rejected with StaleBrowserSnapshotError."""
    b = browser_instance
    b.act({"action": "goto", "url": f"{local_web_server}/forms"})
    snap1 = b.snapshot()

    # Take fresh snapshot -> snap1 is now stale
    snap2 = b.snapshot()
    assert snap1.snapshot_id != snap2.snapshot_id

    # Attempt action using stale snapshot_id
    stale_res = b.act({
        "action": "type",
        "snapshot_id": snap1.snapshot_id,
        "element_id": 1,
        "text": "should_fail",
    })
    assert stale_res.ok is False
    assert stale_res.verified == "false"
    assert "StaleBrowserSnapshotError" in (stale_res.warning or "")


def test_popup_and_cookie_banner_dismissal(browser_instance: PlaywrightBrowser, local_web_server: str):
    """Verifies that cookie banner is detected and automatically rejected by default."""
    b = browser_instance
    b.act({"action": "goto", "url": f"{local_web_server}/popups"})

    # Dismiss routine runs automatically during snapshot
    snap = b.snapshot(auto_dismiss_popups=True)
    assert snap.url.endswith("/popups")

    # Verify banner was clicked/dismissed
    status_text = b.page.locator("#status").inner_text()
    assert status_text == "Rejected"


def test_wait_for_delayed_element(browser_instance: PlaywrightBrowser, local_web_server: str):
    """Verifies condition-based wait_for dynamically resolves delayed DOM elements."""
    b = browser_instance
    b.act({"action": "goto", "url": f"{local_web_server}/delayed"})

    # Wait for #delayedBtn to become visible
    wait_res = b.act({
        "action": "wait_for",
        "condition": "selector_visible",
        "condition_target": "#delayedBtn",
        "timeout_ms": 3000,
    })
    assert wait_res.ok is True
    assert wait_res.verified == "true"

    snap = b.snapshot()
    btn = next((el for el in snap.elements if el.text == "Now Available"), None)
    assert btn is not None


def test_iframe_element_traversal_and_interaction(browser_instance: PlaywrightBrowser, local_web_server: str):
    """Verifies that snapshot traverses nested iframes and actions can interact with them."""
    b = browser_instance
    b.act({"action": "goto", "url": f"{local_web_server}/iframe"})
    snap = b.snapshot()

    # Locate element inside iframe
    iframe_btn = next(
        (el for el in snap.elements if el.frame_url and "iframe_child" in el.frame_url and el.tag_name == "button"),
        None,
    )
    assert iframe_btn is not None
    assert iframe_btn.text == "Click Inside Frame"

    # Click iframe button
    click_res = b.act({
        "action": "click",
        "snapshot_id": snap.snapshot_id,
        "element_id": iframe_btn.id,
    })
    assert click_res.ok is True
    assert click_res.verified == "true"


def test_payment_page_triggers_hard_stop(browser_instance: PlaywrightBrowser, local_web_server: str):
    """Verifies that arriving at or interacting with a payment page triggers HardStopRequiredError."""
    b = browser_instance

    # Navigating to /payment should trigger hard stop
    res = b.act({"action": "goto", "url": f"{local_web_server}/payment"})
    assert res.ok is False
    assert res.verified == "false"
    assert "HardStopRequiredError" in (res.warning or "")
    assert res.evidence.get("hard_stop") is True
