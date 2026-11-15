"""
tests/test_extension_bridge.py — Unit tests for Hybrid Daily Browser Extension Bridge.
"""
import unittest
from unittest.mock import MagicMock, patch

from core.neo_extension_bridge import (
    BrowserTabInfo,
    NEOExtensionBridge,
    extension_bridge,
)
from actions.browser_extension_action import browser_extension_action


class TestNEOExtensionBridge(unittest.TestCase):
    def test_extension_tab_info(self):
        tab = BrowserTabInfo(id=101, title="GitHub PR #42", url="https://github.com/repo/pull/42", active=True)
        self.assertEqual(tab.id, 101)
        self.assertTrue(tab.active)
        self.assertIn("GitHub", tab.title)

    def test_extension_status_action(self):
        res = browser_extension_action({"action": "status"})
        self.assertIn("browser_extension", res)
        self.assertIn("connected=", res)

    def test_command_routing_mock(self):
        # Test simulated command response
        mock_response = {
            "success": True,
            "message": "Clicked element '#submit'",
            "data": {"clicked": True}
        }
        with patch.object(extension_bridge, "_send_command", return_value=mock_response):
            with patch.object(extension_bridge, "_connected_client", MagicMock()):
                ok, msg = extension_bridge.click_selector(selector="#submit")
                self.assertTrue(ok)
                self.assertIn("Clicked element", msg)

                # Test page content extraction
                mock_page = {
                    "success": True,
                    "data": {"title": "AWS Console", "url": "https://aws.amazon.com", "text": "Dashboard summary"}
                }
                with patch.object(extension_bridge, "_send_command", return_value=mock_page):
                    content = extension_bridge.get_page_content()
                    self.assertEqual(content["title"], "AWS Console")
                    self.assertIn("Dashboard", content["text"])


if __name__ == "__main__":
    unittest.main()
