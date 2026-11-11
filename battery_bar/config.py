"""User config: %APPDATA%\\BatteryBar\\config.toml (created with defaults on first run)."""
import os
import tomllib
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home())) / "BatteryBar"
CONFIG_PATH = CONFIG_DIR / "config.toml"

TEMPLATE = """\
# battery-bar config. Edit, save, then restart battery-bar (right-click the strip > Quit, start it again).

# Hide devices by their Bluetooth name
hide = []

# Order (Bluetooth names or plugin names). Anything not listed comes after, A-Z.
order = []

[general]
low_battery = 15            # % at or below which a level turns red
poll_seconds = 120          # how often battery levels are re-read (min 60)
nothing_reask_seconds = 300 # Nothing/CMF buds push changes themselves; this is only a safety re-ask
show_names = false          # show device names next to the icons
gap = 6                     # px between items

# Rename devices in tooltips / labels:  "Bluetooth name" = "Short name"
[aliases]

# Force an icon:  "Bluetooth name" = "mouse" | "keyboard" | "headphones" | "earbuds" | "gamepad"
#                                   | "speaker" | "phone" | "watch" | "pen" | "bluetooth"
[icons]

# Plugins: any command that prints JSON, for devices Windows can't read (2.4 GHz dongles etc).
# Output: {"connected": true, "level": 57, "charging": false}  (or a list of those with "name"/"icon")
# [[plugin]]
# name = "My dongle mouse"
# icon = "mouse"
# command = ["python", "C:/path/to/script.py"]
# interval = 120
# fallback_for = "My Mouse BT"   # only run while this Bluetooth device is NOT connected
"""

DEFAULTS = {
    "general": {"low_battery": 15, "poll_seconds": 120, "nothing_reask_seconds": 300,
                "show_names": False, "gap": 6},
    "hide": [], "order": [], "aliases": {}, "icons": {}, "plugin": [],
}


def load() -> dict:
    if not CONFIG_PATH.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(TEMPLATE, encoding="utf-8")
    try:
        user = tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as e:
        print(f"config error, using defaults: {e}")
        user = {}
    cfg = {k: (dict(v) if isinstance(v, dict) else list(v)) for k, v in DEFAULTS.items()}
    for k, v in user.items():
        if isinstance(v, dict) and isinstance(cfg.get(k), dict):
            cfg[k].update(v)
        else:
            cfg[k] = v
    cfg["general"]["poll_seconds"] = max(60, int(cfg["general"]["poll_seconds"]))
    return cfg
