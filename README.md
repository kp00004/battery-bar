# battery-bar

Battery levels of your Bluetooth devices, **inside the Windows 11 taskbar**, right next to the tray.

```
 🎧L 100%   ▭ 95% ⚡   🎧R 95%   🖱 36%        ^   ENG  📶 🔊 🔋79%   18:27
```

- **Any Bluetooth device:** mouse, keyboard, headphones, earbuds, controller, speaker. If Windows knows its battery (the same number you see in *Settings > Bluetooth & devices*), it shows up, with an icon picked from the device type.
- **Only what's connected.** Each device appears while it is connected and disappears when it isn't. With nothing connected, the strip is gone.
- **Nothing / CMF earbuds get the full view:** left, case and right separately. A bud resting in the case is dimmed with a dot; when you pick one up it lights up. The case shows ⚡ while charging. The buds push these changes themselves, so they show up instantly with no polling.
- **Light on your devices.** Battery levels are re-read every 2 minutes (configurable, minimum 1 minute). Nothing pokes your headset mid-game.
- **Lives in the taskbar.** It's attached to the taskbar window, so it moves with it, works with auto-hide, and comes back if Explorer restarts.
- **Plugins** for things Windows can't read (2.4 GHz dongles, vendor tools): any script that prints one line of JSON.

**Double-click** the strip to refresh. **Hover** for device names. **Right-click** to quit.
Levels at or below 15% turn red.

## Install

Needs Windows 10/11 and Python 3.11+.

```powershell
git clone https://github.com/kp00004/battery-bar
cd battery-bar
powershell -ExecutionPolicy Bypass -File install.ps1
```

`install.ps1` creates a `.venv`, installs the dependencies (only the `winrt` Bluetooth bindings), adds a
*Start with Windows* shortcut and starts it. To run by hand instead:

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\pythonw run.pyw          # or: .venv\Scripts\python -m battery_bar --debug
```

Remove autostart: delete `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\battery-bar.lnk`.

## Config

Created on first run at `%APPDATA%\BatteryBar\config.toml`. Restart battery-bar after editing.

```toml
hide  = ["Old Speaker"]                  # Bluetooth names to never show
order = ["CMF Buds 2", "MX Master 3S"]   # left-to-right; others follow A-Z

[general]
low_battery = 15
poll_seconds = 120          # min 60
nothing_reask_seconds = 300
show_names = false
gap = 6

[aliases]
"MX Master 3S" = "Mouse"

[icons]                     # override the auto-picked icon
"Some Device" = "gamepad"   # mouse keyboard headphones earbuds gamepad speaker phone watch pen bluetooth
```

## Plugins

For devices Windows can't read, add a command that prints **one line of JSON**:

```toml
[[plugin]]
name = "My dongle mouse"
icon = "mouse"
command = ["python", "C:/path/to/script.py"]
interval = 120
fallback_for = "My Mouse BT"   # optional: only run while that Bluetooth device is NOT connected
```

```json
{"connected": true, "level": 57, "charging": false}
```

See [`examples/plugin_template.py`](examples/plugin_template.py), and
[`examples/evofox_ghostx.py`](examples/evofox_ghostx.py) for a real one (EvoFox / Amkette Ghost X mouse
over its 2.4 GHz dongle, using [Evofox_ctl](https://github.com/Sharwesh05/Evofox_ctl)).

## Supported earbuds (L / R / case)

The detailed view uses the earbuds' own control protocol (the one the Nothing X app uses) over Bluetooth RFCOMM.

| Device | Status |
|---|---|
| CMF Buds 2 | tested |
| Other Nothing / CMF buds (Ear (1), Ear (2), Ear (a), Ear (stick), CMF Buds Pro 2, Buds 2a, Buds 2 Plus) | should work, untested; reports welcome |

Every other headset or earbud shows one combined level (whatever Windows reports).

## Limits

- **2.4 GHz dongle devices** (most gaming mice and keyboards) don't report battery to Windows. Use a plugin.
- **Bluetooth mice and keyboards:** Windows refreshes their stored battery value only every few minutes, so it can lag a bit.
- Some devices simply don't send battery info. If *Settings > Bluetooth & devices* shows no %, battery-bar can't either.
- Built and tested on Windows 11 with a bottom taskbar.

## How it works

- Device list and type: WinRT `BluetoothDevice` / `BluetoothLEDevice` (class of device / BLE appearance), read from Windows' cache, with no radio traffic.
- Battery: the `DEVPKEY_Bluetooth_Battery` property Windows stores for the device.
- Nothing / CMF: one RFCOMM link to the control service `aeac4a03-dff5-498f-843a-34487cf133eb`, listening for battery (`0xE001`) and in-case (`0xE002`) pushes. Frame format and battery command from [Gadgetbridge](https://gadgetbridge.org)'s Nothing support; the in-case events were worked out for this project. Details are in [`battery_bar/nothing.py`](battery_bar/nothing.py).
- Taskbar: a Tk window re-parented into `Shell_TrayWnd` (per-monitor-v2 DPI, same as Explorer), placed left of `TrayNotifyWnd`.

## License

GPL-3.0. See [LICENSE](LICENSE).
