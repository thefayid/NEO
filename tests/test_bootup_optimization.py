"""
tests/test_bootup_optimization.py — Unit Tests & Benchmarks for Rapid Cold Bootup & Autostart Optimization.
"""
import sys
import time
import unittest

from core.lazyimport import LazyModule


class TestBootupOptimization(unittest.TestCase):
    def test_01_lazy_cloud_and_audio_proxies(self):
        """Heavy dependencies (genai, sounddevice) must be lazy proxies on the launch path."""
        import main
        self.assertIsInstance(main.sd, LazyModule, "sounddevice must be wrapped in LazyModule")
        self.assertIsInstance(main.genai, LazyModule, "google.genai must be wrapped in LazyModule")
        self.assertIsInstance(main.types, LazyModule, "google.genai.types must be wrapped in LazyModule")

    def test_02_theme_mode_idempotent_no_retheme(self):
        """Setting the current theme mode must be a no-op that skips widget tree traversal."""
        from ui import set_ui_theme_mode, _CURRENT_THEME_MODE
        t0 = time.perf_counter()
        set_ui_theme_mode(_CURRENT_THEME_MODE)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        self.assertLess(elapsed_ms, 5.0, f"Redundant theme set took too long: {elapsed_ms:.2f}ms")

    def test_03_autostart_registry_canonical_and_deduped(self):
        """Autostart in Windows registry must be single canonical 'NEO' using pythonw.exe."""
        if sys.platform.startswith("win"):
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_READ,
            )
            # Legacy duplicates must be absent
            with self.assertRaises(FileNotFoundError):
                winreg.QueryValueEx(key, "NEO_AI")
            with self.assertRaises(FileNotFoundError):
                winreg.QueryValueEx(key, "JARVIS_AI")

            val, _ = winreg.QueryValueEx(key, "NEO")
            winreg.CloseKey(key)
            self.assertIn("pythonw.exe", val.lower(), "Startup must use windowless pythonw.exe")
            self.assertIn("main.py", val)


if __name__ == "__main__":
    unittest.main()
