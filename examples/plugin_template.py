"""Minimal battery-bar plugin. Print ONE line of JSON and exit.

Single device:   {"connected": true, "level": 57, "charging": false}
Several devices: [{"name": "Keyboard", "icon": "keyboard", "connected": true, "level": 80}, ...]

Icons: mouse, keyboard, headphones, earbuds, gamepad, speaker, phone, watch, pen, bluetooth
Add to %APPDATA%\\BatteryBar\\config.toml:

[[plugin]]
name = "My device"
icon = "mouse"
command = ["python", "C:/path/to/this_script.py"]
interval = 120
"""
import json


def read_level():
    # Replace with real code: talk to your device / vendor tool / log file, return (connected, %, charging)
    return True, 57, False


connected, level, charging = read_level()
print(json.dumps({"connected": connected, "level": level, "charging": charging}))
