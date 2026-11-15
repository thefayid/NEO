"""
tests/test_neo_daemon_ipc.py — Unit tests for NeoCore Daemon Service & IPC Communication.
"""
import unittest
from unittest.mock import MagicMock, patch

from core.neo_daemon import NeoDaemonService, daemon_service
from core.neo_ipc_client import NeoIPCClient


class TestNeoDaemonIPC(unittest.TestCase):
    def test_daemon_status_and_lifecycle(self):
        status = daemon_service.get_status()
        self.assertIsNotNone(status)
        self.assertGreaterEqual(status.uptime_seconds, 0)
        self.assertEqual(status.audio_state, "idle")

    def test_command_registration(self):
        received = []

        def sample_handler(payload):
            received.append(payload)

        daemon_service.register_command_handler("test_cmd", sample_handler)
        self.assertIn("test_cmd", daemon_service._callbacks)
        self.assertIn(sample_handler, daemon_service._callbacks["test_cmd"])

    def test_event_broadcasting_mock(self):
        mock_client = MagicMock()
        with patch.object(daemon_service, "_connected_clients", {mock_client}):
            daemon_service._is_running = True
            daemon_service._loop = MagicMock()

            # Broadcast transcript
            daemon_service.emit_transcript("user", "Hello Neo")
            daemon_service.emit_audio_state("speaking")
            daemon_service.emit_tool_call("open_app", "done", "Opened Chrome")

            # Validate audio state update
            self.assertEqual(daemon_service.audio_state, "speaking")

    def test_ipc_client_signals(self):
        client = NeoIPCClient()
        received_transcripts = []
        client.transcript_received.connect(lambda role, text, final: received_transcripts.append((role, text)))

        # Trigger message handling
        client._handle_daemon_event({
            "type": "event",
            "event": "transcript",
            "payload": {"role": "assistant", "text": "At your service.", "is_final": True}
        })

        self.assertEqual(len(received_transcripts), 1)
        self.assertEqual(received_transcripts[0], ("assistant", "At your service."))


if __name__ == "__main__":
    unittest.main()
