"""
tests/test_vocal_barge_in.py — Automated Unit & Integration Tests for Voice Duplexing & Vocal Barge-In.
"""
import unittest
import numpy as np
from core.echo import EchoGuard


class TestVocalBargeIn(unittest.TestCase):
    def setUp(self):
        self.guard = EchoGuard()
        self.sr = 16000

    def test_echo_rejection_during_playback(self):
        """Verifies that laptop speaker audio leaking back into mic does NOT trigger barge-in."""
        out_pcm = (np.sin(2 * np.pi * 440 * np.linspace(0, 0.1, 1600)) * 10000).astype(np.int16)
        mic_echo = (np.sin(2 * np.pi * 440 * np.linspace(0, 0.1, 1600)) * 5000).astype(np.int16)

        # Feed playback and corresponding echo for 12 frames
        for _ in range(12):
            self.guard.note_output(out_pcm, 24000, 0.5)
            barge = self.guard.check_vocal_barge_in(mic_echo, self.sr, 0.25)
            self.assertFalse(barge, "Echo falsely triggered vocal barge-in!")

    def test_sustained_human_voice_triggers_barge_in(self):
        """Verifies that sustained external human voice formants trigger barge-in."""
        out_pcm = (np.sin(2 * np.pi * 440 * np.linspace(0, 0.1, 1600)) * 10000).astype(np.int16)
        mic_echo = (np.sin(2 * np.pi * 440 * np.linspace(0, 0.1, 1600)) * 5000).astype(np.int16)

        # 1. Warm up with echo
        for _ in range(8):
            self.guard.note_output(out_pcm, 24000, 0.5)
            self.guard.check_vocal_barge_in(mic_echo, self.sr, 0.25)

        # 2. User voice speaking over assistant (formants at 800Hz and 1500Hz)
        mic_voice = ((np.sin(2 * np.pi * 800 * np.linspace(0, 0.1, 1600)) +
                      np.sin(2 * np.pi * 1500 * np.linspace(0, 0.1, 1600))) * 6000).astype(np.int16)

        triggered = False
        trigger_block = -1
        for block_idx in range(6):
            self.guard.note_output(out_pcm, 24000, 0.5)
            res = self.guard.check_vocal_barge_in(mic_voice, self.sr, 0.3)
            if res:
                triggered = True
                trigger_block = block_idx + 1
                break

        self.assertTrue(triggered, "Sustained human speech failed to trigger vocal barge-in")
        self.assertLessEqual(trigger_block, 4, f"Barge-in took too many blocks ({trigger_block})")

    def test_single_transient_click_does_not_trigger(self):
        """Verifies that a single transient noise block (mouse click, keyboard tap) is filtered out."""
        out_pcm = (np.sin(2 * np.pi * 440 * np.linspace(0, 0.1, 1600)) * 10000).astype(np.int16)
        mic_echo = (np.sin(2 * np.pi * 440 * np.linspace(0, 0.1, 1600)) * 5000).astype(np.int16)

        for _ in range(8):
            self.guard.note_output(out_pcm, 24000, 0.5)
            self.guard.check_vocal_barge_in(mic_echo, self.sr, 0.25)

        # 1 single noisy transient frame (e.g. key click)
        click_pcm = (np.random.normal(0, 8000, 1600)).astype(np.int16)
        self.guard.note_output(out_pcm, 24000, 0.5)
        res = self.guard.check_vocal_barge_in(click_pcm, self.sr, 0.3)
        self.assertFalse(res, "Single transient noise click falsely triggered barge-in!")


if __name__ == "__main__":
    unittest.main()
