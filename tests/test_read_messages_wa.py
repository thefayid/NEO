import unittest
from unittest.mock import MagicMock, patch
import platform

from actions.read_messages import TOOL as READ_TOOL, read_messages
from actions.send_message import TOOL as SEND_TOOL, _ensure_whatsapp_focused
from core import appidentity


class TestWhatsAppAndReadMessages(unittest.TestCase):
    def test_tool_schemas(self):
        self.assertEqual(READ_TOOL["name"], "read_messages")
        self.assertIn("receiver", READ_TOOL["parameters"]["properties"])
        self.assertEqual(SEND_TOOL["name"], "send_message")

    def test_appidentity_running_and_focus(self):
        if platform.system() == "Windows":
            matches = appidentity.running("WhatsApp")
            # If WhatsApp is installed/running on the host, test focus call
            if matches:
                self.assertGreater(len(matches), 0)
                hwnds = appidentity._hwnds_for(matches[0].pid)
                self.assertTrue(isinstance(hwnds, list))
                if hwnds:
                    self.assertGreater(len(hwnds), 0)

    @patch("actions.send_message._read_whatsapp_chat")
    def test_read_messages_dispatch(self, mock_read_wa):
        mock_read_wa.return_value = "[WhatsApp Chat with Vias]\nTest message"
        res = read_messages({"receiver": "Vias", "platform": "whatsapp"})
        self.assertIn("Vias", res)
        mock_read_wa.assert_called_once()

    def test_contact_alias_vias_to_vihas(self):
        from actions.send_message import _resolve_contact
        contact = _resolve_contact("Vias")
        self.assertEqual(contact["name"], "Vihas")

    def test_visual_grounding_signal_emission(self):
        from core.neo_visual_grounding import NEOVisualGrounding, UIElement
        vg = NEOVisualGrounding()
        received = []
        vg.highlight_requested.connect(lambda bbox, label, linger: received.append((bbox, label, linger)))
        elem = UIElement(label="GitHub Logo", bbox=(100, 200, 300, 400), confidence=0.98, element_type="button")
        # When called off main GUI thread, it emits highlight_requested safely
        vg.highlight_element(elem, linger_ms=2000)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0][0], (100, 200, 300, 400))
        self.assertEqual(received[0][1], "GitHub Logo")
        self.assertEqual(received[0][2], 2000)


if __name__ == "__main__":
    unittest.main()
