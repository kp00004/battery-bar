"""battery-bar plugin: EvoFox / Amkette Ghost X mouse over its 2.4 GHz dongle or USB cable.

Uses the open-source evofox-ctl protocol library (read-only status query):
https://github.com/Sharwesh05/Evofox_ctl

Config:
[[plugin]]
name = "Ghost X"
icon = "mouse"
command = ["python", "C:/path/to/battery-bar/examples/evofox_ghostx.py", "C:/path/to/Evofox_ctl"]
interval = 120
fallback_for = "Ghost X1"   # the mouse's Bluetooth name: skip the dongle while Bluetooth is in use
"""
import json
import sys

if len(sys.argv) > 1:
    sys.path.insert(0, sys.argv[1])

try:
    from ghostx.device import GhostX
    from ghostx.devices import RealSource
except ImportError:
    print(json.dumps({"connected": False}))
    sys.exit()

result = {"connected": False}
for entry in RealSource().scan():
    try:
        with GhostX(entry.open()) as g:
            st = g.status()
    except Exception:
        continue  # mouse asleep / another app using it
    if st.connected or entry.kind == "wired":
        result = {"connected": True, "level": st.battery, "charging": st.charging}
        break
print(json.dumps(result))
