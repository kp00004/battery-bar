"""Command plugins: run a program that prints JSON battery info (for devices Windows can't read)."""
import json
import subprocess

CREATE_NO_WINDOW = 0x08000000


def run(plugin: dict) -> list[dict]:
    """Returns a list of {"name", "icon", "connected", "level", "charging"}. Never raises."""
    try:
        out = subprocess.run(plugin["command"], capture_output=True, text=True, timeout=20,
                             creationflags=CREATE_NO_WINDOW).stdout
        data = json.loads(out.strip().splitlines()[-1])
    except Exception:
        return []
    items = data if isinstance(data, list) else [data]
    res = []
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            continue
        res.append({
            "name": it.get("name") or (plugin.get("name", "plugin") + (f" {i + 1}" if len(items) > 1 else "")),
            "icon": it.get("icon") or plugin.get("icon", "bluetooth"),
            "connected": bool(it.get("connected", it.get("level") is not None)),
            "level": it.get("level"),
            "charging": bool(it.get("charging", False)),
        })
    return res
