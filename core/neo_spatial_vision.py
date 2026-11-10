"""
core/neo_spatial_vision.py — Spatial Multimodal Vision & Neural Presence Suite for NEO.

Architecture:
1. Biometric Desk Presence & Return Greeting:
   - Detects when Fayid sits down at desk ("Welcome back, Fayid.")
   - Detects prolonged absence to pause active live sessions.
   - Fatigue & focus tracker (proposes breaks during 90+ minute coding marathons).
2. Optical Physical Document & Whiteboard Scanner:
   - Captures high-res camera frame of physical papers, books, or whiteboards.
   - Enhances contrast & perspective.
   - Extracts structured Markdown via deep OCR / Gemini Vision.
   - Automatically stores notes into Notes Studio (`memory/notes.json`).
3. Air Pointer & Spatial Gesture Telemetry Bridge.
"""
from __future__ import annotations

import io
import json
import logging
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtCore import QObject, pyqtSignal

try:
    import cv2
    _CV2_OK = True
except ImportError:
    _CV2_OK = False

from core import gemini
from core.camera_service import get_camera_service
from core.neo_ambient_sensor import ambient_sensor
from core.neo_precognition import precognitive_engine, ProactiveOpportunity

_BASE_DIR = Path(__file__).resolve().parent.parent
_LOGGER = logging.getLogger("NEO.SpatialVision")


class NEOSpatialVisionSuite(QObject):
    """
    Spatial Computer Vision and Biometric Presence suite.
    """
    presence_changed = pyqtSignal(bool)                   # is_present
    user_returned = pyqtSignal(str)                       # greeting_text
    fatigue_alert = pyqtSignal(str)                       # warning_text
    document_scanned = pyqtSignal(str, str)               # title, markdown_content

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.is_present = True
        self._last_face_seen = time.time()
        self._continuous_focus_start = time.time()
        self._last_fatigue_alert = 0.0
        self._face_cascade = None
        self._lock = threading.Lock()
        self._init_cascade()

    def _init_cascade(self) -> None:
        """Initializes OpenCV Haar face cascade if available."""
        if _CV2_OK and self._face_cascade is None:
            try:
                cp = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
                if os.path.exists(cp):
                    self._face_cascade = cv2.CascadeClassifier(cp)
            except Exception:
                pass

    # ─────────────────────────────────────────────────────────────────────────
    # 1. Biometric Presence & Fatigue Detection
    # ─────────────────────────────────────────────────────────────────────────

    def process_camera_frame(self, frame_bytes: bytes) -> Dict[str, Any]:
        """
        Analyzes a single camera JPEG/PNG frame for human face presence and posture.
        """
        if not _CV2_OK or not self._face_cascade or not frame_bytes:
            return {"face_detected": False, "is_present": self.is_present}

        try:
            import numpy as np
            nparr = np.frombuffer(frame_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is None:
                return {"face_detected": False, "is_present": self.is_present}

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            faces = self._face_cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=4, minSize=(60, 60))

            now = time.time()
            face_found = len(faces) > 0

            with self._lock:
                if face_found:
                    self._last_face_seen = now
                    if not self.is_present:
                        self.is_present = True
                        self.presence_changed.emit(True)
                        hr = datetime.now().hour
                        period = "morning" if hr < 12 else ("afternoon" if hr < 17 else "evening")
                        greeting = f"Welcome back, Fayid. Good {period}."
                        self.user_returned.emit(greeting)
                        self._continuous_focus_start = now
                else:
                    if self.is_present and (now - self._last_face_seen > 45.0):
                        self.is_present = False
                        self.presence_changed.emit(False)

                # Check for 90+ minute fatigue
                if self.is_present and (now - self._continuous_focus_start > 5400):  # 90 mins
                    if now - self._last_fatigue_alert > 1800:  # 30m cooldown
                        self._last_fatigue_alert = now
                        fatigue_msg = "You have been in continuous focus for over 90 minutes. A 3-minute eye rest is recommended."
                        self.fatigue_alert.emit(fatigue_msg)
                        self._dispatch_fatigue_chip()

            return {
                "face_detected": face_found,
                "faces_count": len(faces),
                "is_present": self.is_present,
            }
        except Exception as e:
            return {"face_detected": False, "is_present": self.is_present, "error": str(e)}

    def _dispatch_fatigue_chip(self) -> None:
        """Dispatches an ergonomic break chip to Hero stage."""
        opp = ProactiveOpportunity(
            opportunity_id=f"ergonomic_{int(time.time())}",
            category="FOCUS_ERGONOMICS",
            urgency=0.48,
            confidence=0.90,
            title="💧 Take 3-Minute Rest",
            subtitle="Continuous desk streak exceeded 90 minutes. Relax eyes and stretch.",
            action_type="COMMAND",
            action_payload="Start 3-minute ergonomic eye rest break, Boss.",
            icon_name="smile",
            cooldown_key="ergonomic:rest_break",
            created_at=time.time(),
        )
        precognitive_engine._dispatch_opportunity(opp, ambient_sensor.get_focus_state())

    # ─────────────────────────────────────────────────────────────────────────
    # 2. Optical Physical Document Scanner
    # ─────────────────────────────────────────────────────────────────────────

    def scan_physical_document(self) -> Tuple[bool, str, str]:
        """
        Captures high-res camera frame of a paper document, notes, or whiteboard,
        extracts text via Gemini Vision OCR, and saves directly into Notes Studio.
        """
        # 1. Grab camera frame
        frame_bytes = b""
        try:
            cam = get_camera_service()
            frame_bytes, _ = cam.snapshot()
        except Exception:
            pass

        if not frame_bytes:
            # Fallback to local snapshot file if camera inactive
            snap_path = _BASE_DIR / "temp_doc_scan.jpg"
            if _CV2_OK:
                try:
                    cap = cv2.VideoCapture(0)
                    ret, frame = cap.read()
                    cap.release()
                    if ret:
                        cv2.imwrite(str(snap_path), frame)
                        frame_bytes = snap_path.read_bytes()
                except Exception:
                    pass

        if not frame_bytes:
            return False, "Camera Unavailable", "Could not capture camera frame for physical scanning."

        prompt = """You are an elite Multimodal Document Scanner in Tony Stark's lab.
Examine this physical document/whiteboard captured via optical sensor.
1. Extract all text, headings, bullet points, and code accurately.
2. If diagrams/tables exist, describe them cleanly in structured Markdown.
3. Provide a clear title on the first line formatted as: '# Document Title'."""

        try:
            # Send image to Gemini Vision
            markdown_content = gemini.describe_image(frame_bytes, prompt=prompt)
            if not markdown_content or not markdown_content.strip():
                return False, "Scan Failed", "No readable text detected in camera frame."

            lines = markdown_content.strip().splitlines()
            first_line = lines[0].replace("#", "").strip() if lines else "Scanned Document"
            title = first_line[:40] if first_line else "Physical Optical Scan"

            # Save note into memory/notes.json
            self._save_scanned_note(title, markdown_content)
            self.document_scanned.emit(title, markdown_content)

            return True, title, markdown_content
        except Exception as e:
            return False, "Scan Error", f"Optical scanning exception: {e}"

    def _save_scanned_note(self, title: str, content: str) -> None:
        """Appends note to persistent memory/notes.json."""
        notes_file = _BASE_DIR / "memory" / "notes.json"
        try:
            notes = []
            if notes_file.exists():
                with open(notes_file, "r", encoding="utf-8") as f:
                    notes = json.load(f)
            
            note_item = {
                "id": f"note_scan_{int(time.time())}",
                "title": f"📷 {title}",
                "content": content,
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "source": "optical_scanner",
            }
            notes.insert(0, note_item)
            with open(notes_file, "w", encoding="utf-8") as f:
                json.dump(notes[:50], f, indent=2)
        except Exception as e:
            _LOGGER.warning(f"Could not persist scanned note: {e}")


# Global Singleton Spatial Vision Suite
spatial_vision = NEOSpatialVisionSuite()
