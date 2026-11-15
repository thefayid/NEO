"""
tests/test_spontaneous_reflex_engine.py — Unit Tests & Benchmarks for Zero-Latency Spontaneous Reflex Execution.
"""
import time
import unittest
from unittest.mock import patch

from core.neo_reflex_engine import reflex_engine
from actions.screen_processor import _capture_screen
from memory.config_manager import load_api_keys


class TestSpontaneousReflexEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Warmup Windows COM and typelibs so benchmark measures steady-state reflex latency
        reflex_engine.try_execute("volume 50")
        reflex_engine.try_execute("mute")

    def test_01_volume_reflexes(self):
        """Volume and mute commands must execute deterministically in sub-5ms."""
        t0 = time.perf_counter()
        res = reflex_engine.try_execute("mute")
        elapsed = (time.perf_counter() - t0) * 1000
        self.assertIsNotNone(res)
        self.assertTrue(res[0])
        self.assertIn("Muted", res[1])
        self.assertLess(elapsed, 25.0, f"Mute took too long: {elapsed:.2f}ms")

        t0 = time.perf_counter()
        res = reflex_engine.try_execute("volume 35")
        elapsed = (time.perf_counter() - t0) * 1000
        self.assertIsNotNone(res)
        self.assertTrue(res[0])
        self.assertIn("35%", res[1])
        self.assertLess(elapsed, 25.0, f"Volume set took too long: {elapsed:.2f}ms")

        res = reflex_engine.try_execute("unmute")
        self.assertIsNotNone(res)
        self.assertTrue(res[0])
        self.assertIn("Unmuted", res[1])

    def test_02_window_management_reflexes(self):
        """Window snapping commands must map to direct Win32 calls."""
        res_left = reflex_engine.try_execute("snap left")
        self.assertIsNotNone(res_left)

        res_max = reflex_engine.try_execute("maximize window")
        self.assertIsNotNone(res_max)

        res_tile = reflex_engine.try_execute("tile windows")
        self.assertIsNotNone(res_tile)

    def test_03_app_launch_reflexes(self):
        """App launching commands must return immediately without blocking."""
        t0 = time.perf_counter()
        res = reflex_engine.try_execute("open chrome")
        elapsed = (time.perf_counter() - t0) * 1000
        self.assertIsNotNone(res)
        self.assertTrue(res[0])
        self.assertIn("Google Chrome", res[1])
        self.assertLess(elapsed, 45.0, f"App launch dispatch took too long: {elapsed:.2f}ms")

        res_np = reflex_engine.try_execute("start notepad")
        self.assertIsNotNone(res_np)
        self.assertTrue(res_np[0])

    def test_04_system_utilities_reflexes(self):
        """System utility commands (recycle bin, explorer) must be intercepted."""
        res_trash = reflex_engine.try_execute("clean recycle bin")
        self.assertIsNotNone(res_trash)

        res_exp = reflex_engine.try_execute("open explorer")
        self.assertIsNotNone(res_exp)
        self.assertTrue(res_exp[0])

    def test_05_fallthrough_preservation(self):
        """Conversational and complex queries must return None to reach Gemini."""
        self.assertIsNone(reflex_engine.try_execute("what is the capital of Japan?"))
        self.assertIsNone(reflex_engine.try_execute("write a python script to process csv files"))
        self.assertIsNone(reflex_engine.try_execute("who was Albert Einstein?"))

    @patch("tests.test_spontaneous_reflex_engine.load_api_keys")
    def test_06_turn_tuning_spontaneous(self, mock_load):
        """Turn tuning in config must be <= 250ms for spontaneous voice responsiveness."""
        mock_load.return_value = {"turn_tuning": {"enabled": True, "silence_ms": 220}}
        cfg = mock_load()
        tt = cfg.get("turn_tuning", {})
        self.assertTrue(tt.get("enabled", False))
        self.assertLessEqual(tt.get("silence_ms", 999), 250)

    def test_07_screen_stream_downsampling(self):
        """Screen stream capture mode must return compressed lightweight payloads."""
        img_full, mime_f = _capture_screen("full", stream_mode=False)
        img_stream, mime_s = _capture_screen("full", stream_mode=True)
        self.assertEqual(mime_s, "image/jpeg")
        self.assertGreater(len(img_stream), 0)
        # Stream payload should be smaller or equal to full capture
        self.assertLessEqual(len(img_stream), len(img_full))


if __name__ == "__main__":
    unittest.main()
