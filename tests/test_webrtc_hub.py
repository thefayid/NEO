"""
tests/test_webrtc_hub.py — Unit tests for WebRTC Mobile Companion Hub & Signaling.
"""
import unittest

from core.neo_webrtc_hub import NEOWebRTCHub, webrtc_hub


class TestNEOWebRTCHub(unittest.TestCase):
    def setUp(self):
        self.hub = NEOWebRTCHub()

    def test_signaling_offer_and_answer(self):
        sess_id = "test_peer_123"
        offer_msg = {
            "type": "offer",
            "sdp": "v=0\r\no=Client\r\ns=Session\r\nt=0 0\r\na=setup:actpass\r\n",
            "device": "iPhone 15 Pro",
        }
        res = self.hub.handle_signaling_message(sess_id, offer_msg)
        self.assertEqual(res["type"], "answer")
        self.assertEqual(res["session_id"], sess_id)
        self.assertEqual(res["status"], "ready")
        self.assertIn("a=setup:active", res["sdp"])

    def test_ice_candidate_handling(self):
        sess_id = "test_peer_456"
        cand_msg = {
            "type": "ice-candidate",
            "candidate": {"candidate": "candidate:1 1 UDP 2130706431 192.168.1.50 50000 typ host", "sdpMid": "0"},
        }
        res = self.hub.handle_signaling_message(sess_id, cand_msg)
        self.assertEqual(res["type"], "ack")
        self.assertIn(sess_id, self.hub._candidates)
        self.assertEqual(len(self.hub._candidates[sess_id]), 1)

    def test_audio_and_video_relay_listeners(self):
        audio_received = []
        video_received = []

        self.hub.register_audio_listener(lambda b: audio_received.append(b))
        self.hub.register_video_listener(lambda b: video_received.append(b))

        self.hub.relay_incoming_audio_chunk("peer_1", b"SAMPLE_PCM_BYTES")
        self.hub.relay_incoming_video_frame("peer_1", b"SAMPLE_JPEG_FRAME")

        self.assertEqual(audio_received, [b"SAMPLE_PCM_BYTES"])
        self.assertEqual(video_received, [b"SAMPLE_JPEG_FRAME"])

    def test_session_lifecycle(self):
        sess_id = "peer_lifecycle"
        self.hub.handle_signaling_message(sess_id, {"type": "offer", "sdp": "v=0"})
        active = [s.session_id for s in self.hub.active_sessions]
        self.assertIn(sess_id, active)

        self.hub.terminate_session(sess_id)
        active_after = [s.session_id for s in self.hub.active_sessions]
        self.assertNotIn(sess_id, active_after)


if __name__ == "__main__":
    unittest.main()
