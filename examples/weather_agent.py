#!/usr/bin/env python3
"""weather_agent.py — An aX agent that fetches weather data.

Shows that agents can call external APIs, do real work,
and return structured results — all from a simple script.

Usage:
    ax listen --agent weather_bot --exec "python examples/weather_agent.py"

Mention it:
    @weather_bot what's the weather in Seattle?
"""
import json
import os
import sys
import urllib.request

content = sys.argv[-1] if len(sys.argv) > 1 else os.environ.get("AX_MENTION_CONTENT", "")

# Simple geocoding via wttr.in (no API key needed)
city = content.strip().split("in ")[-1].split("?")[0].strip() if "in " in content else "Seattle"

try:
    url = f"https://wttr.in/{city}?format=j1"
    req = urllib.request.Request(url, headers={"User-Agent": "ax-agent"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())
    current = data["current_condition"][0]
    temp_f = current["temp_F"]
    desc = current["weatherDesc"][0]["value"]
    humidity = current["humidity"]
    print(f"Weather in {city}: {desc}, {temp_f}F, {humidity}% humidity")
except Exception as e:
    print(f"Couldn't fetch weather for '{city}': {e}")
