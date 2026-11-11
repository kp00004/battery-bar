"""battery-bar: Bluetooth battery levels inside the Windows taskbar, left of the tray.

- Every paired Bluetooth device that is connected and reports a battery shows up (mouse, keyboard,
  headphones, earbuds, controller, ...). Disconnected devices disappear.
- Nothing / CMF earbuds get left / case / right, dimmed while a bud rests in the case.
- Plugins (any command printing JSON) cover devices Windows can't read, e.g. 2.4 GHz dongles.
- Double-click the strip to refresh. Right-click > Quit. Hover for names.
"""
import asyncio
import ctypes
import ctypes.wintypes as wt
import sys
import threading
import time
import tkinter as tk
import winreg

# Must match Explorer's DPI mode, or Windows refuses to put our window inside the taskbar.
ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))

from . import config as config_mod  # noqa: E402
from . import devices, nothing, plugins  # noqa: E402

DEBUG = "--debug" in sys.argv
user32 = ctypes.windll.user32


def log(*a):
    if DEBUG:
        print(time.strftime("%H:%M:%S"), *a, flush=True)


# =============================== engine (background thread) ===============================
class Engine:
    def __init__(self, cfg):
        self.cfg = cfg
        g = cfg["general"]
        self.poll = g["poll_seconds"]
        self.reask = max(60, int(g["nothing_reask_seconds"]))
        self.devices: dict[int, devices.Device] = {}
        self.battery: dict[int, int | None] = {}
        self.last_read: dict[int, float] = {}
        self.buds: dict[int, nothing.BudsState] = {}
        self.buds_tasks: dict[int, asyncio.Task] = {}
        self.no_buds_service: set[int] = set()
        self.plugin_items: dict[int, list[dict]] = {}
        self.plugin_last: dict[int, float] = {}
        self.refresh = threading.Event()

    def start(self):
        threading.Thread(target=lambda: asyncio.run(self.main()), daemon=True).start()

    async def main(self):
        await asyncio.gather(self.bt_loop(), self.plugin_loop(), self.refresh_clear())

    async def refresh_clear(self):
        while True:
            if self.refresh.is_set():
                await asyncio.sleep(3)
                self.refresh.clear()
            await asyncio.sleep(0.2)

    async def bt_loop(self):
        while True:
            try:
                found = await devices.paired()
            except Exception as e:
                log("discovery error", e)
                found = []
            self.devices = {d.address: d for d in found}
            now = time.monotonic()
            for d in found:
                if not d.connected:
                    self.last_read.pop(d.address, None)
                    continue
                if nothing.is_nothing(d.name) and d.address not in self.no_buds_service:
                    t = self.buds_tasks.get(d.address)
                    if t is None or t.done():
                        st = self.buds.setdefault(d.address, nothing.BudsState())
                        self.buds_tasks[d.address] = asyncio.ensure_future(self._buds(d.address, st))
                due = now - self.last_read.get(d.address, -1e9) > self.poll
                if due or self.refresh.is_set():
                    self.battery[d.address] = await asyncio.to_thread(devices.windows_battery, d.addr_hex)
                    self.last_read[d.address] = now
                    log("battery", d.name, self.battery[d.address])
            await asyncio.sleep(5)

    async def _buds(self, address, st):
        ok = await nothing.session(address, st, self.reask, self.refresh.is_set, log)
        if not ok:
            self.no_buds_service.add(address)
        await asyncio.sleep(3)

    async def plugin_loop(self):
        while True:
            for i, p in enumerate(self.cfg.get("plugin", [])):
                fb = p.get("fallback_for")
                if fb and any(d.connected and d.name == fb for d in self.devices.values()):
                    self.plugin_items[i] = []
                    continue
                every = max(60, int(p.get("interval", 120)))
                if self.refresh.is_set() or time.monotonic() - self.plugin_last.get(i, -1e9) > every:
                    self.plugin_last[i] = time.monotonic()
                    self.plugin_items[i] = await asyncio.to_thread(plugins.run, p)
                    log("plugin", p.get("name"), self.plugin_items[i])
            await asyncio.sleep(5)

    # ---- what to show (called from the UI thread) ----
    def items(self) -> list[dict]:
        cfg = self.cfg
        hide, aliases, icons = set(cfg["hide"]), cfg["aliases"], cfg["icons"]
        groups = []  # (sort name, [items])
        for d in list(self.devices.values()):
            if not d.connected or d.name in hide:
                continue
            label = aliases.get(d.name, d.name)
            st = self.buds.get(d.address)
            if st and st.link and st.bat:
                its = []
                for part in ("L", "case", "R"):
                    if part not in st.bat:
                        continue
                    lvl, chg = st.bat[part]
                    if part == "case":
                        its.append(dict(key=f"{d.address}:case", icon="case", tag="", level=lvl, charging=chg,
                                        mode="stale" if st.case_stale else "on", tip=f"{label} case"))
                    else:
                        in_case = st.pos.get(part) == "case"
                        its.append(dict(key=f"{d.address}:{part}", icon="bud", tag=part, level=lvl,
                                        charging=chg and in_case, mode="case" if in_case else "on",
                                        tip=f"{label} {'left' if part == 'L' else 'right'}"
                                            + (" (in case)" if in_case else "")))
                groups.append((d.name, its))
                continue
            lvl = self.battery.get(d.address)
            if lvl is None:
                continue
            groups.append((d.name, [dict(key=str(d.address), icon=icons.get(d.name, d.icon), tag="", level=lvl,
                                         charging=False, mode="on", tip=label)]))
        for i, its in self.plugin_items.items():
            for it in its:
                if it["connected"] and it["level"] is not None and it["name"] not in hide:
                    label = aliases.get(it["name"], it["name"])
                    groups.append((it["name"], [dict(key=f"plugin{i}:{it['name']}", icon=icons.get(it["name"], it["icon"]),
                                                     tag="", level=int(it["level"]), charging=it["charging"],
                                                     mode="on", tip=label)]))
        order = cfg["order"]
        groups.sort(key=lambda g: (order.index(g[0]) if g[0] in order else len(order), g[0].lower()))
        return [it for _, its in groups for it in its]


# =============================== UI ===============================
GLYPH = {"mouse": "", "keyboard": "", "headphones": "", "earbuds": "",
         "bud": "", "case": "", "gamepad": "", "speaker": "", "phone": "",
         "watch": "", "pen": "", "bluetooth": ""}
BOLT = ""
ICON_FONT, TEXT_FONT, SMALL_FONT = "Segoe Fluent Icons", "Segoe UI Semibold", "Segoe UI"


def dark_theme() -> bool:
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        return winreg.QueryValueEx(k, "SystemUsesLightTheme")[0] == 0
    except OSError:
        return True


def mix(a, b, t):
    a = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def close(a, b):
    return all(abs(int(a[i:i + 2], 16) - int(b[i:i + 2], 16)) < 6 for i in (1, 3, 5))


class Bar:
    def __init__(self, engine: Engine, cfg):
        self.e, self.cfg = engine, cfg
        g = cfg["general"]
        self.low, self.gap, self.show_names = int(g["low_battery"]), int(g["gap"]), bool(g["show_names"])
        dark = dark_theme()
        self.KEY = "#1b1b1b" if dark else "#eeeeee"
        self.FG = "#ffffff" if dark else "#1a1a1a"
        self.DIM = "#7d7d7d" if dark else "#8c8c8c"
        self.RED, self.GREEN, self.ACCENT = "#ff6b6b", "#4cd082", "#7cc4ff"

        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.configure(bg=self.KEY)
        self.root.attributes("-transparentcolor", self.KEY)
        self.row = tk.Frame(self.root, bg=self.KEY)
        self.row.pack()
        self.root.geometry("1x1+-100+-100")
        self.root.update()  # Tk creates the outer window only once mapped
        self.hwnd = user32.GetParent(self.root.winfo_id())
        user32.SetWindowLongW(self.hwnd, -20, user32.GetWindowLongW(self.hwnd, -20) | 0x80 | 0x08000000)
        user32.ShowWindow(self.hwnd, 0)

        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Quit battery-bar", command=self.root.destroy)
        self.root.bind_all("<Button-3>", lambda ev: menu.tk_popup(ev.x_root, ev.y_root))
        self.root.bind_all("<Double-Button-1>", lambda ev: self.do_refresh())

        self.tip = None
        self.cells: dict[str, dict] = {}
        self.order = None
        self.parent = 0

    # ---- interactions ----
    def do_refresh(self):
        self.e.refresh.set()
        for c in self.cells.values():
            c["color"] = self.ACCENT

    def show_tip(self, text):
        self.hide_tip()
        t = tk.Toplevel(self.root)
        t.overrideredirect(True)
        t.attributes("-topmost", True)
        tk.Label(t, text=text, font=(SMALL_FONT, 9), fg=self.FG, bg="#2b2b2b" if self.FG == "#ffffff" else "#f9f9f9",
                 padx=8, pady=4, relief="solid", bd=1).pack()
        t.update_idletasks()
        x, y = self.root.winfo_pointerx(), self.root.winfo_pointery()
        t.geometry(f"+{x - t.winfo_reqwidth() // 2}+{y - t.winfo_reqheight() - 24}")
        self.tip = t

    def hide_tip(self):
        if self.tip is not None:
            self.tip.destroy()
            self.tip = None

    # ---- cells ----
    def cell(self, key):
        if key in self.cells:
            return self.cells[key]
        f = tk.Frame(self.row, bg=self.KEY)
        c = dict(f=f,
                 g=tk.Label(f, font=(ICON_FONT, 12), bg=self.KEY),
                 t=tk.Label(f, font=(SMALL_FONT, 7), bg=self.KEY),
                 v=tk.Label(f, font=(TEXT_FONT, 10), bg=self.KEY),
                 n=tk.Label(f, font=(SMALL_FONT, 8), bg=self.KEY),
                 b=tk.Label(f, text=BOLT, font=(ICON_FONT, 8), fg=self.GREEN, bg=self.KEY),
                 d=tk.Label(f, text="●", font=(SMALL_FONT, 5), fg=self.DIM, bg=self.KEY),
                 color=self.DIM, target=self.FG, sig=None, tiptext="")
        for w in (f, c["g"], c["t"], c["v"], c["n"]):
            w.bind("<Enter>", lambda ev, c=c: self.show_tip(c["tiptext"]))
            w.bind("<Leave>", lambda ev: self.hide_tip())
        self.cells[key] = c
        return c

    def update_cell(self, c, it):
        sig = (it["icon"], it["tag"], it["level"], it["charging"], it["mode"], it["tip"])
        c["tiptext"] = f'{it["tip"]}: {it["level"]}%' + (" (charging)" if it["charging"] else "")
        if sig == c["sig"]:
            return
        was = c["sig"][4] if c["sig"] else None
        c["sig"] = sig
        c["g"].config(text=GLYPH.get(it["icon"], GLYPH["bluetooth"]))
        c["t"].config(text=it["tag"])
        c["v"].config(text=f'{it["level"]}%')
        c["n"].config(text=it["tip"] if self.show_names and not it["tag"] else "")
        for k in "gtvnbd":
            c[k].pack_forget()
        c["g"].pack(side="left")
        if it["tag"]:
            c["t"].pack(side="left", anchor="s", pady=(0, 3))
        c["v"].pack(side="left", padx=(3, 0))
        if c["n"]["text"]:
            c["n"].pack(side="left", padx=(3, 0))
        if it["charging"]:
            c["b"].pack(side="left")
        if it["mode"] == "case":
            c["d"].pack(side="left", padx=(2, 0), anchor="n", pady=(2, 0))
        low = it["level"] <= self.low and not it["charging"]
        c["target"] = self.RED if low else (self.FG if it["mode"] == "on" else self.DIM)
        if it["mode"] == "on" and was == "case":
            c["color"] = self.ACCENT  # picked up: glow, then settle

    def step(self, c):
        if c["color"] != c["target"]:
            c["color"] = c["target"] if close(c["color"], c["target"]) else mix(c["color"], c["target"], 0.25)
        for k in "gtvn":
            c[k].config(fg=c["color"])

    # ---- taskbar ----
    def attach(self, tb):
        st = user32.GetWindowLongW(self.hwnd, -16) & 0xFFFFFFFF
        new = ((st & ~0x80000000) | 0x40000000) & 0xFFFFFFFF  # -WS_POPUP +WS_CHILD
        user32.SetWindowLongW(self.hwnd, -16, ctypes.c_long(new - (1 << 32) if new >= 1 << 31 else new))
        user32.SetParent(self.hwnd, tb)
        self.parent = tb

    @staticmethod
    def rect(h):
        r = wt.RECT()
        user32.GetWindowRect(h, ctypes.byref(r))
        return r

    def tick(self):
        items = self.e.items()
        order = [it["key"] for it in items]
        if order != self.order:
            for c in self.cells.values():
                c["f"].pack_forget()
            for k in order:
                self.cell(k)["f"].pack(side="left", padx=self.gap)
            self.order = order
        for it in items:
            c = self.cell(it["key"])
            self.update_cell(c, it)
            self.step(c)

        tb = user32.FindWindowW("Shell_TrayWnd", None)
        tray = user32.FindWindowExW(tb, None, "TrayNotifyWnd", None) if tb else 0
        if tb and tray and items:
            if tb != self.parent:  # first run, or Explorer restarted
                self.attach(tb)
            self.root.update_idletasks()
            w, h = self.row.winfo_reqwidth(), self.row.winfo_reqheight()
            t, n = self.rect(tb), self.rect(tray)
            user32.SetWindowPos(self.hwnd, 0, n.left - t.left - w - 6, (t.bottom - t.top - h) // 2, w, h,
                                0x0010 | 0x0040)  # NOACTIVATE | SHOWWINDOW
            user32.BringWindowToTop(self.hwnd)
        else:
            user32.ShowWindow(self.hwnd, 0)
            self.hide_tip()
        self.root.after(60, self.tick)

    def run(self):
        self.root.after(300, self.tick)
        self.root.mainloop()


def single_instance() -> bool:
    ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\battery-bar-singleton")
    return ctypes.windll.kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


def main():
    if not single_instance():
        return
    cfg = config_mod.load()
    engine = Engine(cfg)
    engine.start()
    Bar(engine, cfg).run()
