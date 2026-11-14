"""
actions/browser_cdp.py — Direct Chrome DevTools Protocol (CDP) Action for NEO.

Provides 100% deterministic web browser automation:
- Programmatic DOM clicks and form fills in 2ms without screen clicks.
- JavaScript expression evaluation directly in active pages.
- Structured web table extraction.
- Browser launching with remote debugging enabled.
"""
from __future__ import annotations

from typing import Any, Dict
from core.neo_cdp_bridge import cdp_bridge
from core import outcome

TOOL = {
    "name": "browser_cdp",
    "description": (
        "Operate Chrome or Edge directly through Chrome DevTools Protocol (CDP) with 100% precision: "
        "evaluate JavaScript, click CSS selectors, fill input fields, navigate URLs, inspect DOM elements, "
        "and extract table data in 2ms without mouse movement or visual coordinate drift."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "'click_selector', 'type_selector', 'eval_js', 'navigate', 'get_dom', 'extract_table', 'launch_browser', 'status'.",
                "enum": ["click_selector", "type_selector", "eval_js", "navigate", "get_dom", "extract_table", "launch_browser", "status"]
            },
            "selector": {
                "type": "STRING",
                "description": "CSS selector for target element (e.g. '#submit-btn', 'input[name=\"q\"]', 'table.results')."
            },
            "text": {
                "type": "STRING",
                "description": "Text to type into input or JavaScript expression to evaluate."
            },
            "url": {
                "type": "STRING",
                "description": "URL for navigate or launch_browser."
            },
            "browser": {
                "type": "STRING",
                "description": "'chrome' (default) or 'edge' for launch_browser."
            }
        },
        "required": ["action"]
    }
}


def run(params: Dict[str, Any], player=None) -> str:
    action = (params.get("action") or "status").strip().lower()

    if action == "status":
        connected = cdp_bridge.is_connected()
        tabs = cdp_bridge.get_tabs() if connected else []
        active = cdp_bridge.get_active_page_tab()
        return outcome.done(
            "browser_cdp",
            connected=connected,
            port=cdp_bridge.port,
            tab_count=len(tabs),
            active_title=active.get("title") if active else None,
            active_url=active.get("url") if active else None,
            message="CDP Browser bridge is online and active." if connected else "No browser running with --remote-debugging-port=9222. Use 'launch_browser' action."
        )

    elif action == "launch_browser":
        b_type = params.get("browser") or "chrome"
        target_url = params.get("url") or "https://www.google.com"
        ok = cdp_bridge.launch_browser(browser=b_type, url=target_url)
        if ok:
            return outcome.done("browser_cdp", launched=b_type, url=target_url, message=f"Launched {b_type.title()} with CDP active on port 9222.")
        return outcome.failed("browser_cdp", f"Could not launch {b_type.title()} with CDP. Ensure {b_type} is installed.")

    elif action == "click_selector":
        sel = params.get("selector") or ""
        if not sel:
            return outcome.failed("browser_cdp", "No CSS selector specified.")
        res = cdp_bridge.click_selector(sel)
        if isinstance(res, dict) and res.get("success"):
            return outcome.done("browser_cdp", clicked=sel, tag=res.get("tag"), message=f"Clicked DOM element '{sel}'.")
        return outcome.failed("browser_cdp", str(res.get("message") if isinstance(res, dict) else res))

    elif action == "type_selector":
        sel = params.get("selector") or ""
        val = params.get("text") or ""
        if not sel:
            return outcome.failed("browser_cdp", "No CSS selector specified.")
        res = cdp_bridge.type_selector(sel, val)
        if isinstance(res, dict) and res.get("success"):
            return outcome.done("browser_cdp", selector=sel, typed=val, message=f"Typed text into '{sel}'.")
        return outcome.failed("browser_cdp", str(res.get("message") if isinstance(res, dict) else res))

    elif action == "navigate":
        target_url = params.get("url") or ""
        if not target_url:
            return outcome.failed("browser_cdp", "No URL provided.")
        cdp_bridge.navigate(target_url)
        return outcome.done("browser_cdp", url=target_url, message=f"Navigated active tab to {target_url}.")

    elif action == "eval_js":
        expr = params.get("text") or ""
        if not expr:
            return outcome.failed("browser_cdp", "No JavaScript expression provided.")
        val = cdp_bridge.eval_js(expr)
        return outcome.done("browser_cdp", result=str(val)[:500])

    elif action == "get_dom":
        items = cdp_bridge.get_dom_summary(max_items=25)
        summary = [f"<{it['tag']}> '{it['text']}' ({it['selector']})" for it in items]
        return outcome.done("browser_cdp", count=len(items), elements=summary)

    elif action == "extract_table":
        sel = params.get("selector") or "table"
        data = cdp_bridge.extract_table(sel)
        return outcome.done("browser_cdp", selector=sel, rows=len(data), data=str(data)[:600])

    return outcome.failed("browser_cdp", f"Unknown action '{action}'.")
