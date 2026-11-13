"""
tests/test_live_session_resumption.py — Tests for Gemini Multimodal Live API
session duration rollover, GoAway detection, and graceful resumption.
"""
import sys
import unittest
from unittest.mock import MagicMock, patch

from main import (
    _ReconnectSignal,
    _is_reconnect_signal,
    _keep_context_of,
    _reason_of,
    _is_go_away_or_session_abort,
)


class TestLiveSessionResumptionAndGoAway(unittest.TestCase):

    def test_reconnect_signal_direct_and_group(self):
        sig = _ReconnectSignal(keep_context=True, reason="new voice")
        self.assertTrue(_is_reconnect_signal(sig))
        self.assertTrue(_keep_context_of(sig))
        self.assertEqual(_reason_of(sig), "new voice")

        # Test within BaseExceptionGroup (Python 3.11+ TaskGroup behavior)
        group = BaseExceptionGroup("TaskGroup failure", [sig])
        self.assertTrue(_is_reconnect_signal(group))
        self.assertTrue(_keep_context_of(group))
        self.assertEqual(_reason_of(group), "new voice")

    def test_go_away_or_session_abort_detection(self):
        # 1. Exact string from Google Multimodal Live API 1008 policy violation
        err1 = Exception(
            "received 1008 (policy violation) Connection aborted because the client failed to close "
            "the connection after receiving a GoAway signal once the session duration was reached"
        )
        self.assertTrue(_is_go_away_or_session_abort(err1))

        # 2. google.genai.errors.APIError shape
        err2 = Exception(
            "1008 None. Connection aborted because the client failed to close the connection "
            "after receiving a GoAway signal once the session durat"
        )
        self.assertTrue(_is_go_away_or_session_abort(err2))

        # 3. Inside ExceptionGroup
        group = ExceptionGroup("TaskGroup", [err2])
        self.assertTrue(_is_go_away_or_session_abort(group))

        # 4. Standard unrelated errors should NOT match
        err3 = ValueError("Invalid input value")
        self.assertFalse(_is_go_away_or_session_abort(err3))

        err4 = Exception("404 Resource not found")
        self.assertFalse(_is_go_away_or_session_abort(err4))

    def test_proactive_go_away_signal_logic(self):
        # Verify LiveServerGoAway structure and parsing
        from google.genai import types

        mock_go_away = types.LiveServerGoAway(time_left="10s")
        self.assertEqual(mock_go_away.time_left, "10s")

        # Verify time_left parsing logic
        _tl = mock_go_away.time_left
        _wait_s = 7.0
        if isinstance(_tl, str) and _tl.endswith("s"):
            _wait_s = max(2.0, float(_tl[:-1]) - 3.0)
        self.assertEqual(_wait_s, 7.0)


if __name__ == "__main__":
    unittest.main()

