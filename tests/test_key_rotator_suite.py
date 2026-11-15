"""
tests/test_key_rotator_suite.py — Unit test suite for NEO Multi-Key Pool & Quota Rotator.
"""
import unittest
from unittest.mock import patch
from core.neo_key_rotator import GeminiKeyPool
from memory.config_manager import save_api_keys, get_gemini_key, get_all_gemini_keys
from core.gemini import is_quota_error, note_live_failure


class TestGeminiKeyPool(unittest.TestCase):
    def setUp(self):
        self.pool = GeminiKeyPool()
        # Reset internal state for test isolation
        self.pool._cooldowns.clear()
        self.pool._active_index = 0

    def test_parse_keys_single_and_multiple(self):
        data_single = {"gemini_api_key": "AIzaSyFakeKey11111111111111"}
        keys = self.pool._parse_keys_from_config(data_single)
        self.assertEqual(len(keys), 1)
        self.assertEqual(keys[0], "AIzaSyFakeKey11111111111111")

        data_csv = {"gemini_api_key": "AIzaSyFakeKey11111111111111, AIzaSyFakeKey22222222222222"}
        keys_csv = self.pool._parse_keys_from_config(data_csv)
        self.assertEqual(len(keys_csv), 2)

        data_list = {
            "gemini_api_keys": [
                "AIzaSyFakeKey11111111111111",
                "AIzaSyFakeKey22222222222222",
                "AIzaSyFakeKey33333333333333",
            ]
        }
        keys_list = self.pool._parse_keys_from_config(data_list)
        self.assertEqual(len(keys_list), 3)

    def test_key_masking(self):
        masked = self.pool.mask_key("AIzaSyB1234567890XYZW")
        self.assertTrue(masked.startswith("AIzaSy..."))
        self.assertTrue(masked.endswith("XYZW"))
        self.assertEqual(self.pool.mask_key(""), "NONE")

    def test_rotation_flow(self):
        self.pool._keys = [
            "AIzaSyKeyOne111111111111111",
            "AIzaSyKeyTwo222222222222222",
            "AIzaSyKeyThree3333333333333",
        ]
        self.pool._active_index = 0

        # Initial active key
        self.assertEqual(self.pool.get_active_key(), "AIzaSyKeyOne111111111111111")

        # Simulate quota exhaustion on Key 1
        with patch.object(self.pool, "_save_primary_key"):
            ok, new_k, msg = self.pool.rotate_key("429 RESOURCE_EXHAUSTED")
            self.assertTrue(ok)
            self.assertEqual(new_k, "AIzaSyKeyTwo222222222222222")
            self.assertEqual(self.pool.get_active_key(), "AIzaSyKeyTwo222222222222222")
            self.assertIn("Rotated key from #1", msg)

            # Key 1 should be cooling
            self.assertTrue(self.pool.is_cooling("AIzaSyKeyOne111111111111111"))

            # Simulate quota exhaustion on Key 2
            ok2, new_k2, _ = self.pool.rotate_key("429 RESOURCE_EXHAUSTED")
            self.assertTrue(ok2)
            self.assertEqual(new_k2, "AIzaSyKeyThree3333333333333")

    def test_single_key_graceful_handling(self):
        self.pool._keys = ["AIzaSyOnlyOneKey1111111111"]
        self.pool._active_index = 0

        ok, key, msg = self.pool.rotate_key("quota")
        self.assertFalse(ok)
        self.assertEqual(key, "AIzaSyOnlyOneKey1111111111")
        self.assertIn("Only 1 API key", msg)

    def test_note_live_failure_triggers_rotation(self):
        self.pool._keys = [
            "AIzaSyKeyOne111111111111111",
            "AIzaSyKeyTwo222222222222222",
        ]
        self.pool._active_index = 0

        with patch("core.neo_key_rotator.key_rotator", self.pool), \
             patch.object(self.pool, "_save_primary_key"):
            self.assertTrue(is_quota_error("429 RESOURCE_EXHAUSTED: quota exceeded"))
            res = note_live_failure("models/gemini-2.0-flash-exp", "429 RESOURCE_EXHAUSTED")
            self.assertTrue(res)
            # Active index should have moved to 1
            self.assertEqual(self.pool._active_index, 1)


    def test_config_manager_multi_key_helpers(self):
        with patch("memory.config_manager._write_config") as mock_write, \
             patch("memory.config_manager.load_api_keys", return_value={}):
            save_api_keys(["AIzaSyKeyA1111111111111", "AIzaSyKeyB2222222222222"])
            self.assertTrue(mock_write.called)
            saved_data = mock_write.call_args[0][0]
            self.assertEqual(saved_data["gemini_api_key"], "AIzaSyKeyA1111111111111")
            self.assertEqual(len(saved_data["gemini_api_keys"]), 2)

        with patch("core.neo_key_rotator.key_rotator.get_active_key", return_value="AIzaSyActiveKey11111"), \
             patch("core.neo_key_rotator.key_rotator.get_keys", return_value=["AIzaSyActiveKey11111", "AIzaSyNext22222"]):
            self.assertEqual(get_gemini_key(), "AIzaSyActiveKey11111")
            self.assertEqual(len(get_all_gemini_keys()), 2)

    def test_on_setup_done_preserves_multiple_keys(self):
        from unittest.mock import MagicMock
        fake_self = MagicMock()
        import ui
        with patch("ui._read_full_config", return_value={}), \
             patch.object(ui, "API_FILE", MagicMock()), \
             patch("memory.config_manager.save_api_keys") as mock_save:
            payload = {
                "gemini_api_key": "AIzaSyKey1111111111111",
                "gemini_api_keys": ["AIzaSyKey1111111111111", "AIzaSyKey2222222222222"],
                "os_system": "windows",
                "user_name": "Boss",
            }
            ui.MainWindow._on_setup_done(fake_self, payload)
            self.assertTrue(mock_save.called)
            saved_keys = mock_save.call_args[0][0]
            self.assertEqual(saved_keys, ["AIzaSyKey1111111111111", "AIzaSyKey2222222222222"])


if __name__ == "__main__":
    unittest.main()
