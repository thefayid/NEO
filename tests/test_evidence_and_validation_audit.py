"""
tests/test_evidence_and_validation_audit.py — Unit tests verifying code-level fixes
for evidence collection, LLM output validation, and state/snapshot staleness guards.
"""
import time
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from neo.brain.planner import ActionDispatcher, StepExecutionResult
from neo.brain.schema import (
    BrainValidationError,
    LLMReply,
    validate_llm_reply,
)
from neo.brain.whitelist import AgentDecision
from neo.browser import (
    BrowserActionRequest,
    BrowserActionResult,
    BrowserElement,
    BrowserSnapshot,
    BrowserSnapshotRegistry,
    execute_browser_action,
)
from neo.vision.click_xy import click_xy
from neo.windows.actions import ActionRequest, ActionResult, execute_action
from neo.windows.uia_snapshot import SnapshotRegistry, UIAElement, UIASnapshot


# ─────────────────────────────────────────────────────────────────────────────
# 1. neo/browser/actions.py Auditing Tests
# ─────────────────────────────────────────────────────────────────────────────
class TestBrowserActionAudits:
    def test_browser_click_no_observable_change_returns_warning(self):
        """Click that causes no navigation and no DOM change returns verified='false' with warning."""
        reg = BrowserSnapshotRegistry()
        elem = BrowserElement(
            id=1,
            snapshot_id="snap_b1",
            role="button",
            name="Inert Button",
            text="Inert Button",
            value="",
            enabled=True,
            in_viewport=True,
            tag_name="button",
        )
        snap = BrowserSnapshot(
            snapshot_id="snap_b1",
            url="https://example.com/page",
            title="Page",
            elements=[elem],
            timestamp=time.time(),
            duration_ms=1.0,
            total_elements_scanned=1,
        )
        mock_locator = MagicMock()
        # Mock DOM evaluation returning identical state before and after click
        mock_locator.evaluate.return_value = {"html": "<button>Inert Button</button>", "inputs": ""}
        reg.register(snap, {1: mock_locator})

        mock_page = MagicMock()
        mock_page.url = "https://example.com/page"
        mock_page.title.return_value = "Page"

        res = execute_browser_action(
            mock_page,
            {"action": "click", "snapshot_id": "snap_b1", "element_id": 1},
            registry=reg,
        )
        assert res.ok is True
        assert res.verified == "false"
        assert res.warning is not None
        assert "no observable effect" in res.warning.lower()

    def test_browser_click_on_disabled_element_rejected(self):
        """Click on a disabled browser element must immediately return ok=False."""
        reg = BrowserSnapshotRegistry()
        elem = BrowserElement(
            id=2,
            snapshot_id="snap_b2",
            role="button",
            name="Disabled Submit",
            text="Disabled Submit",
            value="",
            enabled=False,  # DISABLED!
            in_viewport=True,
            tag_name="button",
        )
        snap = BrowserSnapshot(
            snapshot_id="snap_b2",
            url="https://example.com/page",
            title="Page",
            elements=[elem],
            timestamp=time.time(),
            duration_ms=1.0,
            total_elements_scanned=1,
        )
        mock_locator = MagicMock()
        reg.register(snap, {2: mock_locator})

        mock_page = MagicMock()
        mock_page.url = "https://example.com/page"
        mock_page.title.return_value = "Page"

        res = execute_browser_action(
            mock_page,
            {"action": "click", "snapshot_id": "snap_b2", "element_id": 2},
            registry=reg,
        )
        assert res.ok is False
        assert res.verified == "false"
        assert "disabled" in (res.warning or "").lower()

    def test_browser_type_readback_failure_returns_ok_false(self):
        """When typed text is not reflected in input readback, ok must be False."""
        reg = BrowserSnapshotRegistry()
        elem = BrowserElement(
            id=3,
            snapshot_id="snap_b3",
            role="textbox",
            name="Search",
            text="",
            value="",
            enabled=True,
            in_viewport=True,
            tag_name="input",
        )
        snap = BrowserSnapshot(
            snapshot_id="snap_b3",
            url="https://example.com/page",
            title="Page",
            elements=[elem],
            timestamp=time.time(),
            duration_ms=1.0,
            total_elements_scanned=1,
        )
        mock_locator = MagicMock()
        mock_locator.input_value.return_value = "Old Unchanged Value"
        reg.register(snap, {3: mock_locator})

        mock_page = MagicMock()
        mock_page.url = "https://example.com/page"
        mock_page.title.return_value = "Page"

        res = execute_browser_action(
            mock_page,
            {"action": "type", "snapshot_id": "snap_b3", "element_id": 3, "text": "New Query"},
            registry=reg,
        )
        assert res.ok is False
        assert res.verified == "false"
        assert "not reflected in element readback" in (res.warning or "")

    def test_browser_select_option_mismatch_returns_ok_false(self):
        """When chosen select option does not match readback value, ok must be False."""
        reg = BrowserSnapshotRegistry()
        elem = BrowserElement(
            id=4,
            snapshot_id="snap_b4",
            role="combobox",
            name="Country",
            text="",
            value="US",
            enabled=True,
            in_viewport=True,
            tag_name="select",
        )
        snap = BrowserSnapshot(
            snapshot_id="snap_b4",
            url="https://example.com/page",
            title="Page",
            elements=[elem],
            timestamp=time.time(),
            duration_ms=1.0,
            total_elements_scanned=1,
        )
        mock_locator = MagicMock()
        mock_locator.input_value.return_value = "US"  # Did not change to CA
        reg.register(snap, {4: mock_locator})

        mock_page = MagicMock()
        mock_page.url = "https://example.com/page"
        mock_page.title.return_value = "Page"

        res = execute_browser_action(
            mock_page,
            {"action": "select_option", "snapshot_id": "snap_b4", "element_id": 4, "value": "CA"},
            registry=reg,
        )
        assert res.ok is False
        assert res.verified == "false"
        assert "did not match" in (res.warning or "").lower()

    def test_browser_goto_http_error_returns_ok_false(self):
        """HTTP error codes (>= 400) return ok=False, verified='false'."""
        mock_page = MagicMock()
        mock_page.url = "https://example.com/404"
        mock_page.title.return_value = "Not Found"

        mock_resp = MagicMock()
        mock_resp.status = 404
        mock_page.goto.return_value = mock_resp

        with patch("neo.browser.actions.validate_domain") as mock_val:
            mock_val.return_value = MagicMock(is_allowed=True)
            res = execute_browser_action(
                mock_page,
                {"action": "goto", "url": "https://example.com/404"},
            )
            assert res.ok is False
            assert res.verified == "false"
            assert "404" in (res.warning or "")

    def test_browser_go_back_no_navigation_returns_ok_false(self):
        """go_back when URL does not change returns ok=False."""
        mock_page = MagicMock()
        mock_page.url = "https://example.com/stay"
        mock_page.go_back.return_value = None

        res = execute_browser_action(
            mock_page,
            {"action": "go_back"},
        )
        assert res.ok is False
        assert res.verified == "false"
        assert "did not change the page URL" in (res.warning or "")


# ─────────────────────────────────────────────────────────────────────────────
# 2. neo/windows/actions.py Auditing Tests
# ─────────────────────────────────────────────────────────────────────────────
class TestWindowsActionAudits:
    def test_collapsed_bounding_box_does_not_click_zero_coords(self):
        """Collapsed (0, 0, 0, 0) bounding boxes must not resolve to (0, 0) coordinates."""
        reg = SnapshotRegistry()
        elem = UIAElement(
            id=1,
            snapshot_id="snap_w1",
            control_type="Button",
            name="Hidden Offscreen",
            automation_id="btnHidden",
            enabled=True,
            value=None,
            bounding_rect=(0, 0, 0, 0),  # Collapsed zero-size rect
        )
        snap = UIASnapshot(
            snapshot_id="snap_w1",
            hwnd=111,
            window_title="Test App",
            elements=[elem],
            is_sparse=False,
            timestamp=time.time(),
            total_elements_scanned=1,
            duration_ms=1.0,
        )
        mock_wrapper = MagicMock()
        del mock_wrapper.iface_invoke
        del mock_wrapper.iface_toggle
        del mock_wrapper.iface_selection_item
        reg.register(snap, {1: mock_wrapper})

        res = execute_action(
            {"action": "click", "snapshot_id": "snap_w1", "element_id": 1},
            registry=reg,
        )
        assert res.ok is False
        assert res.verified == "false"
        assert "no valid coordinates" in (res.warning or "").lower()

    def test_windows_click_on_disabled_element_rejected(self):
        """Click on disabled UIA element returns ok=False and disabled warning."""
        reg = SnapshotRegistry()
        elem = UIAElement(
            id=2,
            snapshot_id="snap_w2",
            control_type="Button",
            name="Disabled Save",
            automation_id="btnSave",
            enabled=False,  # DISABLED
            value=None,
            bounding_rect=(10, 10, 100, 50),
        )
        snap = UIASnapshot(
            snapshot_id="snap_w2",
            hwnd=111,
            window_title="Test App",
            elements=[elem],
            is_sparse=False,
            timestamp=time.time(),
            total_elements_scanned=1,
            duration_ms=1.0,
        )
        mock_wrapper = MagicMock()
        reg.register(snap, {2: mock_wrapper})

        res = execute_action(
            {"action": "click", "snapshot_id": "snap_w2", "element_id": 2},
            registry=reg,
        )
        assert res.ok is False
        assert res.verified == "false"
        assert "disabled" in (res.warning or "").lower()

    def test_windows_set_text_readback_failure_returns_ok_false(self):
        """When set_text readback does not match expected text, ok must be False."""
        reg = SnapshotRegistry()
        elem = UIAElement(
            id=3,
            snapshot_id="snap_w3",
            control_type="Edit",
            name="Name Field",
            automation_id="txtName",
            enabled=True,
            value="",
            bounding_rect=(10, 10, 100, 30),
        )
        snap = UIASnapshot(
            snapshot_id="snap_w3",
            hwnd=111,
            window_title="Test App",
            elements=[elem],
            is_sparse=False,
            timestamp=time.time(),
            total_elements_scanned=1,
            duration_ms=1.0,
        )
        mock_wrapper = MagicMock()
        mock_wrapper.iface_value.SetValue = MagicMock()
        mock_wrapper.is_password.return_value = False
        del mock_wrapper.element_info
        mock_wrapper.window_text.return_value = "Old Name"

        reg.register(snap, {3: mock_wrapper})

        with patch("neo.windows.actions.extract_element_value", return_value="Old Name"):
            res = execute_action(
                {"action": "set_text", "snapshot_id": "snap_w3", "element_id": 3, "text": "Target Name", "settle_timeout": 0.1},
                registry=reg,
            )
            assert res.ok is False
            assert res.verified == "false"
            assert "does not match expected text" in (res.warning or "")

    def test_windows_select_unconfirmed_returns_ok_false(self):
        """When select does not confirm is_selected, ok must be False."""
        reg = SnapshotRegistry()
        elem = UIAElement(
            id=4,
            snapshot_id="snap_w4",
            control_type="RadioButton",
            name="Option B",
            automation_id="rbB",
            enabled=True,
            value=None,
            bounding_rect=(10, 10, 100, 30),
        )
        snap = UIASnapshot(
            snapshot_id="snap_w4",
            hwnd=111,
            window_title="Test App",
            elements=[elem],
            is_sparse=False,
            timestamp=time.time(),
            total_elements_scanned=1,
            duration_ms=1.0,
        )
        mock_wrapper = MagicMock()
        mock_wrapper.iface_selection_item.Select = MagicMock()
        mock_wrapper.iface_selection_item.CurrentIsSelected = 0  # Unselected!
        reg.register(snap, {4: mock_wrapper})

        res = execute_action(
            {"action": "select", "snapshot_id": "snap_w4", "element_id": 4, "settle_timeout": 0.1},
            registry=reg,
        )
        assert res.ok is False
        assert res.verified == "false"
        assert "did not confirm selected state" in (res.warning or "")


# ─────────────────────────────────────────────────────────────────────────────
# 3. neo/vision/click_xy.py Auditing Tests
# ─────────────────────────────────────────────────────────────────────────────
class TestVisionActionAudits:
    def test_click_xy_rejects_negative_coords(self):
        """Level 5 click_xy rejects negative coordinates."""
        res = click_xy(
            x=-50,
            y=100,
            reason="UIA tree is completely sparse",
            exhaustion_evidence={"uia_sparse": True},
        )
        assert res.ok is False
        assert res.verified == "false"
        assert "cannot be negative" in (res.warning or "")


# ─────────────────────────────────────────────────────────────────────────────
# 4. neo/brain/schema.py & planner.py Auditing Tests
# ─────────────────────────────────────────────────────────────────────────────
class TestBrainValidationAudits:
    def test_validate_llm_reply_rejects_acting_on_disabled_element(self):
        """LLM proposing an action on a disabled element is rejected at schema validation."""
        elem = UIAElement(
            id=5,
            snapshot_id="snap_brain1",
            control_type="Button",
            name="Disabled Confirm",
            automation_id="btnConfirm",
            enabled=False,  # DISABLED
            value=None,
            bounding_rect=(10, 10, 100, 30),
        )
        snap = UIASnapshot(
            snapshot_id="snap_brain1",
            hwnd=999,
            window_title="Active Form",
            elements=[elem],
            is_sparse=False,
            timestamp=time.time(),
            total_elements_scanned=1,
            duration_ms=1.0,
        )
        raw_llm = """{
            "stage": "act",
            "observation": "Form is ready to submit",
            "last_action_result": "None",
            "plan": ["Click confirm"],
            "action": "click",
            "target_id": 5,
            "confidence": 0.9
        }"""
        with pytest.raises(BrainValidationError) as exc:
            validate_llm_reply(raw_llm, current_snapshot=snap)
        assert "is disabled" in str(exc.value)

    def test_llm_reply_to_agent_decision_preserves_snapshot_id(self):
        """to_agent_decision automatically attaches snapshot_id into parameters."""
        reply = LLMReply(
            stage="act",
            observation="Observed button",
            last_action_result="Initial",
            plan=["Click button"],
            action="click",
            target_id=10,
            confidence=0.9,
            snapshot_id="snap_verified_123",
        )
        dec = reply.to_agent_decision()
        assert dec.parameters["element_id"] == 10
        assert dec.parameters["snapshot_id"] == "snap_verified_123"

    def test_planner_bounds_checks_click_coords(self):
        """ActionDispatcher rejects out-of-bounds coordinates."""
        dispatcher = ActionDispatcher()
        dec = AgentDecision(
            thought="Click outside screen",
            action="click_coords",
            parameters={"coords": (-10, 500)},
        )
        res = dispatcher.dispatch(dec)
        assert res.ok is False
        assert "out of screen bounds" in (res.error or "")
