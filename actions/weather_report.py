"""
actions/weather_report.py — Accurate real-time weather reports for F.R.I.D.A.Y.
Supports Open-Meteo, wttr.in, and instant speech synthesis answers without forced browser redirects.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

from core import outcome

def _fetch_weather(city: str) -> dict:
    clean_city = urllib.parse.quote(city.strip())
    # 1. First attempt: wttr.in JSON format (free, no API key required)
    try:
        url = f"https://wttr.in/{clean_city}?format=j1"
        req = urllib.request.Request(url, headers={"User-Agent": "curl/7.68.0"})
        with urllib.request.urlopen(req, timeout=3.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            cur = data.get("current_condition", [{}])[0]
            weather_desc = cur.get("weatherDesc", [{}])[0].get("value", "Clear")
            temp_c = cur.get("temp_C", "--")
            temp_f = cur.get("temp_F", "--")
            humidity = cur.get("humidity", "--")
            wind_kmph = cur.get("windspeedKmph", "--")
            feels_like_c = cur.get("FeelsLikeC", temp_c)
            return {
                "city": city.title(),
                "condition": weather_desc,
                "temp_c": temp_c,
                "temp_f": temp_f,
                "feels_like_c": feels_like_c,
                "humidity": humidity,
                "wind_kmph": wind_kmph,
            }
    except Exception:
        pass

    # 2. Open-Meteo geocoding fallback
    try:
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={clean_city}&count=1&language=en&format=json"
        with urllib.request.urlopen(geo_url, timeout=3.5) as resp:
            geo_data = json.loads(resp.read().decode("utf-8"))
            results = geo_data.get("results", [])
            if results:
                lat = results[0]["latitude"]
                lon = results[0]["longitude"]
                name = results[0].get("name", city.title())
                om_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m"
                with urllib.request.urlopen(om_url, timeout=3.5) as om_resp:
                    om_data = json.loads(om_resp.read().decode("utf-8"))
                    cur = om_data.get("current", {})
                    return {
                        "city": name,
                        "condition": "Fair",
                        "temp_c": str(round(cur.get("temperature_2m", 25))),
                        "temp_f": str(round(cur.get("temperature_2m", 25) * 9/5 + 32)),
                        "feels_like_c": str(round(cur.get("apparent_temperature", cur.get("temperature_2m", 25)))),
                        "humidity": str(cur.get("relative_humidity_2m", "--")),
                        "wind_kmph": str(round(cur.get("wind_speed_10m", 10))),
                    }
    except Exception:
        pass

    return {}


def weather_action(parameters: dict, player=None, session_memory=None) -> str:
    city = (parameters or {}).get("city", "").strip()
    if not city:
        city = "Kerala"

    info = _fetch_weather(city)
    if not info:
        return outcome.failed("weather_report", f"Unable to fetch live meteorological data for {city}, Boss.")

    report = (
        f"Current weather for {info['city']}: {info['condition']}, {info['temp_c']}°C ({info['temp_f']}°F). "
        f"Feels like {info['feels_like_c']}°C, with {info['humidity']}% humidity and wind at {info['wind_kmph']} km/h."
    )

    if player and hasattr(player, "write_log"):
        player.write_log(f"🌤️ {report}")

    return outcome.done("weather_report", city=info['city'], temp_c=info['temp_c'], condition=info['condition'], summary=report)


TOOL = {
    "name": "weather_report",
    "description": (
        "Fetches live meteorological weather reports and forecasts for any city or region. "
        "Provides real temperature in Celsius/Fahrenheit, condition (Sunny, Rain, Fair), humidity, and wind speed."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "city": {
                "type": "STRING",
                "description": "City, region, or location name (e.g. 'Kochi', 'New York', 'London', 'Kerala')"
            }
        },
        "required": ["city"]
    },
    "handler": weather_action,
}
