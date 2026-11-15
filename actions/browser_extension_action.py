"""
actions/browser_extension_action.py — Hybrid Daily Browser Companion Action for NEO.

Provides direct DOM control over active daily authenticated browser tabs
(GitHub, AWS, Jira, Docs, Email) without requiring --remote-debugging-port flags.
"""
from __future__ import annotations

from typing import Any, Dict

from core import outcome
from core.neo_extension_bridge import extension_bridge


def browser_extension_action(parameters: Dict[str, Any], **kwargs) -> str:
    """Controls daily browser tabs via the NEO Companion extension."""
    action = parameters.get("action", "status")

    if action == "status":
        connected = extension_bridge.is_connected
        active = extension_bridge.active_tab
        tabs = extension_bridge.tabs
        return outcome.done(
            "browser_extension",
            connected=connected,
            active_tab={"title": active.title, "url": active.url} if active else None,
            total_tabs=len(tabs),
        )

    if not extension_bridge.is_connected:
        return outcome.failed(
            "browser_extension",
            "NEO Browser Companion extension is not connected. Load 'browser_extension/' in chrome://extensions.",
        )

    if action == "get_active_tab":
        active = extension_bridge.active_tab
        if not active:
            return outcome.failed("browser_extension", "No active browser tab found.")
        return outcome.done(
            "browser_extension",
            tab_id=active.id,
            title=active.title,
            url=active.url,
        )

    elif action == "read_page":
        content = extension_bridge.get_page_content()
        if "error" in content:
            return outcome.failed("browser_extension", content["error"])
        return outcome.done(
            "browser_extension",
            title=content.get("title", ""),
            url=content.get("url", ""),
            text_preview=content.get("text", "")[:2000],
        )

    elif action == "click":
        selector = parameters.get("selector", "")
        text = parameters.get("text", "")
        if not selector and not text:
            return outcome.failed("browser_extension", "Must provide 'selector' or 'text' for click.")
        ok, msg = extension_bridge.click_selector(selector=selector, text=text)
        return outcome.done("browser_extension", result=msg) if ok else outcome.failed("browser_extension", msg)

    elif action == "type":
        selector = parameters.get("selector", "")
        text = parameters.get("text", "")
        if not selector:
            return outcome.failed("browser_extension", "Must provide 'selector' for type.")
        ok, msg = extension_bridge.type_selector(selector=selector, text=text)
        return outcome.done("browser_extension", result=msg) if ok else outcome.failed("browser_extension", msg)

    elif action == "eval_js":
        script = parameters.get("script") or parameters.get("text") or ""
        if not script:
            return outcome.failed("browser_extension", "Must provide 'script' to evaluate.")
        res = extension_bridge.eval_js(script)
        return outcome.done("browser_extension", result=res)

    elif action == "list_tabs":
        tabs = extension_bridge.list_tabs()
        return outcome.done("browser_extension", total_tabs=len(tabs), tabs=tabs)

    elif action == "query_dom":
        selector = parameters.get("selector", "")
        elements = extension_bridge.query_dom(selector=selector)
        return outcome.done("browser_extension", count=len(elements), elements=elements)

    return outcome.failed("browser_extension", f"Unknown action '{action}'.")


TOOL = {
    "name": "browser_extension",
    "description": (
        "Operate the user's active daily browser session (Chrome, Edge, Brave) directly via the NEO Companion extension. "
        "Allows reading authenticated pages (GitHub PRs, AWS console, Google Docs, Jira), clicking buttons by text or CSS selector, "
        "typing into search inputs, and listing tabs without closing the user's browser or using debug flags."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": ["status", "get_active_tab", "read_page", "click", "type", "eval_js", "list_tabs", "query_dom"],
                "description": "Action to perform. Default is 'status'.",
            },
            "selector": {
                "type": "STRING",
                "description": "CSS selector to target on the active tab (e.g., '#submit-btn', 'input[name=\"q\"]').",
            },
            "text": {
                "type": "STRING",
                "description": "Text to type into input, button text to click, or JS to evaluate.",
            },
            "script": {
                "type": "STRING",
                "description": "JavaScript code string to evaluate in the active page (for action='eval_js').",
            },
        },
        "required": [],
    },
    "handler": browser_extension_action,
    "tier": "extra",
    "brief": "Control daily authenticated browser tabs (GitHub, Jira, AWS) via extension bridge.",
}
