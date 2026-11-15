"""
tests/test_audio_diagnostic.py — Unit tests for Audio Diagnostic Tool.
"""
import unittest
from unittest.mock import patch, MagicMock
import numpy as np

from actions.audio_diagnostic import run_audio_diagnostics, manage_audio_diagnostic


class TestAudioDiagnostic(unittest.TestCase):
    @patch("actions.audio_diagnostic.sd")
    @patch("actions.audio_diagnostic.get_input_device")
    @patch("actions.audio_diagnostic.get_turn_tuning")
    @patch("actions.audio_diagnostic.get_proactive_audio_enabled")
    def test_run_audio_diagnostics(self, mock_proactive, mock_tuning, mock_device, mock_sd):
        mock_device.return_value = ""
        mock_tuning.return_value = {"enabled": False, "silence_ms": 750}
        mock_proactive.return_value = False

        mock_sd.default.device = [1, 2]
        mock_sd.query_devices.return_value = [
            {"name": "Mic 1", "max_input_channels": 1, "hostapi": 0},
            {"name": "Speaker 1", "max_input_channels": 0, "hostapi": 0},
        ]
        mock_sd.query_hostapis.return_value = [{"name": "MME"}]

        # Fake 16kHz sine wave audio
        fake_rec = (np.sin(2 * np.pi * 440 * np.linspace(0, 0.1, 1600)) * 5000).astype(np.int16)
        mock_sd.rec.return_value = fake_rec

        res = run_audio_diagnostics(duration_s=0.1)
        self.assertEqual(res["status"], "success")
        self.assertEqual(len(res["devices"]), 1)
        self.assertEqual(res["devices"][0]["health"], "OPTIMAL")

    def test_manage_audio_diagnostic_set_device(self):
        with patch("actions.audio_diagnostic.save_input_device") as mock_save:
            res = manage_audio_diagnostic({"operation": "set_device", "device_name": "Test Mic"})
            mock_save.assert_called_once_with("Test Mic")
            self.assertIn("Test Mic", res)

    def test_manage_audio_diagnostic_optimize(self):
        with patch("actions.audio_diagnostic.save_proactive_audio_enabled") as mock_proactive, \
             patch("actions.audio_diagnostic.save_turn_tuning") as mock_tuning:
            res = manage_audio_diagnostic({"operation": "optimize_settings"})
            mock_proactive.assert_called_once_with(False)
            mock_tuning.assert_called_once()
            self.assertIn("status=success", res)


if __name__ == "__main__":
    unittest.main()
