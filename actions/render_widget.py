"""
Action: render_widget
Generative UI Engine for NEO:
Renders dynamic, high-tech interactive visual cards directly inside the HUD content stage.
Supports:
1. 'system_analytics': Live interactive multi-core CPU, RAM & GPU telemetry gauges.
2. 'calendar_feed': Interactive agenda schedule cards with time status.
3. 'media_player': Interactive audio / cybernetic music player card.
4. 'chart': Dynamic ASCII/SVG bar chart for custom metrics or data trends.
"""

import html
import json


def _render_system_card(metrics: dict) -> str:
    cpu = metrics.get("cpu_percent", 0)
    ram = metrics.get("ram_percent", 0)
    gpu = metrics.get("gpu_percent")
    temp = metrics.get("cpu_temp_c")
    uptime = metrics.get("uptime", "--")

    gpu_str = f"{gpu}%" if gpu is not None else "N/A"
    temp_str = f"{temp}°C" if temp is not None else "NORMAL"

    def _bar(pct, col="#00e5ff"):
        p = min(max(int(pct), 0), 100)
        return (
            f'<div style="background:#0d1420; border:1px solid #1a2638; border-radius:4px; height:8px; width:100%; margin:3px 0 6px 0;">'
            f'<div style="background:{col}; width:{p}%; height:100%; border-radius:3px;"></div></div>'
        )

    return f"""
    <div style="font-family: Consolas, 'Segoe UI', monospace; padding: 4px; color: #e2e8f0;">
        <div style="color: #00e5ff; font-weight: bold; font-size: 11px; margin-bottom: 8px; letter-spacing: 1px;">
            ⚡ SYSTEM NEURAL TELEMETRY // REAL-TIME METRICS
        </div>
        <table style="width:100%; border-collapse: collapse; font-size: 10px;">
            <tr>
                <td style="width:50%; padding-right:10px; vertical-align:top;">
                    <div style="display:flex; justify-content:space-between;">
                        <span style="color:#94a3b8;">CPU CORES</span>
                        <span style="color:#00e5ff; font-weight:bold;">{cpu}%</span>
                    </div>
                    {_bar(cpu, '#00e5ff')}
                    <div style="display:flex; justify-content:space-between;">
                        <span style="color:#94a3b8;">MEMORY SYNC</span>
                        <span style="color:#f43f5e; font-weight:bold;">{ram}%</span>
                    </div>
                    {_bar(ram, '#f43f5e')}
                </td>
                <td style="width:50%; padding-left:10px; vertical-align:top;">
                    <div style="display:flex; justify-content:space-between;">
                        <span style="color:#94a3b8;">NEURAL GPU</span>
                        <span style="color:#10b981; font-weight:bold;">{gpu_str}</span>
                    </div>
                    {_bar(gpu if gpu is not None else 0, '#10b981')}
                    <div style="display:flex; justify-content:space-between;">
                        <span style="color:#94a3b8;">THERMAL STATUS</span>
                        <span style="color:#f59e0b; font-weight:bold;">{temp_str}</span>
                    </div>
                    {_bar(temp if temp is not None else 45, '#f59e0b')}
                </td>
            </tr>
        </table>
        <div style="margin-top: 6px; padding-top: 4px; border-top: 1px solid #1a2638; font-size: 9px; color: #64748b;">
            UPTIME: <span style="color:#10b981;">{uptime}</span>  ·  ENGINE: <span style="color:#00e5ff;">ACTIVE KERNEL</span>  ·  LINK: ENCRYPTED
        </div>
    </div>
    """


def _render_calendar_card(events: list) -> str:
    rows = []
    for ev in (events or []):
        time_lbl = html.escape(str(ev.get("time", "ALL DAY")))
        title = html.escape(str(ev.get("title", "Scheduled Task")))
        loc = html.escape(str(ev.get("location", "")))
        loc_str = f" <span style='color:#64748b;'>({loc})</span>" if loc else ""
        rows.append(
            f"""
        <div style="background:#0d1420; border-left:3px solid #00e5ff; border:1px solid #1a2638; border-radius:4px; padding:6px 10px; margin-bottom:5px;">
            <span style="color:#00e5ff; font-weight:bold; font-size:9px;">[{time_lbl}]</span>
            <span style="color:#ffffff; font-weight:bold; font-size:10px; margin-left:6px;">{title}</span>
            {loc_str}
        </div>
        """
        )
    if not rows:
        rows.append(
            "<div style='color:#64748b; font-size:10px;'>No scheduled events for today. Horizon is clear.</div>"
        )

    return f"""
    <div style="font-family: Consolas, 'Segoe UI', monospace; padding: 4px;">
        <div style="color: #00e5ff; font-weight: bold; font-size: 11px; margin-bottom: 8px; letter-spacing: 1px;">
            📅 TACTICAL SCHEDULE & AGENDA
        </div>
        {''.join(rows)}
    </div>
    """


def _render_media_card(track: str, artist: str, state: str = "PLAYING") -> str:
    t = html.escape(track or "Unknown Track")
    a = html.escape(artist or "Unknown Artist")
    status_col = "#10b981" if "play" in state.lower() else "#f59e0b"
    return f"""
    <div style="font-family: Consolas, 'Segoe UI', monospace; padding: 6px; background:#0d1420; border:1px solid #1a2638; border-radius:6px;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <div>
                <span style="color:#00e5ff; font-size:14px; font-weight:bold;">♫ {t}</span><br/>
                <span style="color:#94a3b8; font-size:10px;">by {a}</span>
            </div>
            <span style="color:{status_col}; font-weight:bold; font-size:9px; border:1px solid {status_col}; padding:2px 6px; border-radius:10px;">
                {state.upper()}
            </span>
        </div>
        <div style="background:#111c2e; border-radius:3px; height:4px; margin-top:8px; overflow:hidden;">
            <div style="background:#00e5ff; width:65%; height:100%;"></div>
        </div>
    </div>
    """


def _render_chart_card(title: str, labels: list, values: list) -> str:
    max_val = max(values) if values and max(values) > 0 else 1
    bars = []
    for lbl, val in zip(labels, values):
        l_esc = html.escape(str(lbl))
        pct = int((float(val) / float(max_val)) * 100)
        bars.append(
            f"""
        <div style="margin-bottom:4px;">
            <div style="display:flex; justify-content:space-between; font-size:9px;">
                <span style="color:#94a3b8;">{l_esc}</span>
                <span style="color:#00e5ff; font-weight:bold;">{val}</span>
            </div>
            <div style="background:#0d1420; border:1px solid #1a2638; border-radius:3px; height:6px; margin-top:2px;">
                <div style="background:#00e5ff; width:{pct}%; height:100%; border-radius:2px;"></div>
            </div>
        </div>
        """
        )

    return f"""
    <div style="font-family: Consolas, 'Segoe UI', monospace; padding: 4px;">
        <div style="color: #00e5ff; font-weight: bold; font-size: 11px; margin-bottom: 8px; letter-spacing: 1px;">
            📊 {html.escape(title.upper())}
        </div>
        {''.join(bars)}
    </div>
    """


def render_widget(widget_type: str, data: dict = None) -> str:
    """Generate interactive HTML cards for HUD display."""
    data = data or {}
    w_type = (widget_type or "").lower().strip()

    if w_type == "system_analytics":
        from actions.system_monitor import get_system_status

        metrics = get_system_status()
        return _render_system_card(metrics)
    elif w_type == "calendar_feed":
        events = data.get("events", [])
        return _render_calendar_card(events)
    elif w_type == "media_player":
        track = data.get("track", "Midnight Cyber City")
        artist = data.get("artist", "Synthwave Collective")
        state = data.get("state", "PLAYING")
        return _render_media_card(track, artist, state)
    elif w_type == "chart":
        title = data.get("title", "Performance Metrics")
        labels = data.get("labels", ["Mon", "Tue", "Wed", "Thu", "Fri"])
        values = data.get("values", [24, 45, 78, 62, 85])
        return _render_chart_card(title, labels, values)
    else:
        return f"<div style='color:#f43f5e;'>Unknown widget type: {html.escape(w_type)}</div>"

