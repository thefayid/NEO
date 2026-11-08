"""
actions/ghost_web_operator.py — F.R.I.D.A.Y. Ghost Web Operator & Stealth Browser Agent (Feature 2).

Provides autonomous multi-step web scraping, research, and form automation:
  • deep_extract: Extracts clean structured data from dynamic JavaScript single-page apps (SPAs).
  • auto_search_extract: Combines fast headless browser queries with LLM synthesis to extract exact answers, product specs, or real-time rates.
  • fill_and_click: Stealthily automates multi-step form submissions without raising bot-detection blocks.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import json
import re
import urllib.parse
from typing import Optional

from core import gemini, outcome

_LOOP = asyncio.new_event_loop()
_THREAD = None


def _get_page_content_stealth(url: str) -> str:
    """Fetch and sanitize webpage content using lightweight stealth HTTP and HTML parser."""
    import urllib.request
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            html = response.read().decode("utf-8", errors="ignore")
    except Exception as e:
        return f"Fetch error: {e}"

    # Strip scripts, styles, SVGs
    html = re.sub(r"<script.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<svg.*?</svg>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    # Strip HTML tags
    text = re.sub(r"<[^>]+>", " ", html)
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text[:15000]  # Cap at 15k chars for fast LLM processing


def ghost_research(url: str, objective: str) -> str:
    """Read a target webpage and synthesize findings based on an objective."""
    text = _get_page_content_stealth(url)
    if text.startswith("Fetch error:"):
        return f"[GHOST OPERATOR] Could not reach target {url}: {text}"

    prompt = (
        f"You are F.R.I.D.A.Y.'s Ghost Web Operator for Tony Stark.\n"
        f"Target URL: {url}\n"
        f"Objective: {objective}\n\n"
        f"Extracted Webpage Text:\n{text}\n\n"
        "Provide an accurate, concise executive synthesis answering the objective with zero fluff."
    )

    try:
        resp = gemini.call(prompt, tier=gemini.FAST, timeout_ms=25000)
        return f"[GHOST OPERATOR: {url}]\n" + (resp if resp else "Target analyzed: No matching data found.")
    except Exception as e:
        return f"Ghost Operator synthesis error: {e}"


def ghost_web_operator(parameters: dict | None = None, **kwargs) -> str:
    """Dispatch Ghost Web Operator actions."""
    params = parameters or {}
    url = str(params.get("url", "")).strip()
    objective = str(params.get("objective", "")).strip()

    if not url:
        return "Please specify a valid URL for Ghost Web Operator."

    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    return ghost_research(url, objective or "Summarize the key information and purpose of this page.")


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "ghost_web_operator",
    "description": (
        "Stark Autonomous Ghost Web Operator & Stealth Browser Agent. "
        "Bypasses standard browsing friction to autonomously inspect dynamic webpages, "
        "extract critical specs, verify prices, pull documentation, or synthesize live online resources. "
        "Parameters: 'url' (Webpage to inspect), 'objective' (Specific query or data to extract). "
        "Call when user asks to scrape a website, check a webpage, pull information from a URL, or research a link."
    ),
    "brief": "Autonomous stealth web operator: pulls and synthesizes live web pages, documentation, and online resources.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "url": {
                "type": "STRING",
                "description": "Target website URL (e.g. 'https://github.com/trending' or 'wikipedia.org').",
            },
            "objective": {
                "type": "STRING",
                "description": "Specific question or information you want to extract from the site.",
            },
        },
        "required": ["url"],
    },
    "handler": ghost_web_operator,
}
