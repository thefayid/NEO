"""
actions/spatial_vision_action.py — Spatial Multimodal Vision & Document Scanner Action for NEO.

Auto-discovered by core/action_loader.py. Exposes optical paper/whiteboard document scanning
and biometric desk presence checking to Gemini Live and the Voice Assistant.
"""
from __future__ import annotations

from typing import Dict, Any, Optional
from core.neo_central_coordinator import central_core
from core.neo_spatial_vision import spatial_vision


def spatial_document_scanner(parameters: dict, **kwargs) -> str:
    """Handler for spatial document scanning and biometric presence."""
    operation = str(parameters.get("operation", "scan_document")).strip().lower()

    if operation == "check_presence":
        is_pres, conf = spatial_vision.get_presence_status()
        state = "at the desk" if is_pres else "away from desk"
        return f"User is currently {state} (presence confidence: {conf:.0%})."

    # Default: scan_document
    ok, title, note_path = central_core.scan_physical_document()
    if ok:
        return (
            f"Physical document successfully captured and converted to Markdown note.\n"
            f"Title: {title}\n"
            f"Saved to Notes Studio database: {note_path}"
        )
    return f"Document scan result: {title}"


TOOL = {
    "name": "spatial_document_scanner",
    "description": (
        "Captures a physical document, paper notebook, or whiteboard using the webcam, "
        "extracts structured Markdown notes via multimodal OCR, and saves directly to Notes Studio. "
        "Also inspects biometric desk presence. "
        "Use when the user holds up notes, whiteboard diagrams, papers, or asks to check desk presence."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "operation": {
                "type": "STRING",
                "description": "'scan_document' to photograph and OCR a physical page/whiteboard, or 'check_presence' to check if user is at the desk.",
            },
        },
        "required": ["operation"],
    },
    "handler": spatial_document_scanner,
    "behavior": "NON_BLOCKING",
    "scheduling": "WHEN_IDLE",
}
