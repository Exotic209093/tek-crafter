"""Chem Bench Bot - desktop app for the ARK crafting loop.

Double-click to open (pythonw, no console). Settings are saved to
ark_chem_config.json next to this file. Global hotkeys work while ARK is
focused: Start/Pause (default F9) and Stop (default F10), both rebindable.
An optional click-through overlay in the top-left corner of the screen shows
progress (e.g. "CB1 - 12/18 crafted").
"""

import copy
import ctypes
import ctypes.wintypes
import json
import queue
import subprocess
import sys
import threading
import time
import traceback
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ark_chem as eng  # noqa: E402

APP_TITLE = "Chem Bench Bot"
user32 = ctypes.windll.user32

# ------------------------------------------------------------------ key names

KEY_NAMES = {0x04: "Mouse Middle", 0x05: "Mouse Back", 0x06: "Mouse Forward",
             0x08: "Backspace", 0x09: "Tab", 0x0D: "Enter", 0x13: "Pause",
             0x14: "Caps Lock", 0x1B: "Esc", 0x20: "Space", 0x21: "Page Up",
             0x22: "Page Down", 0x23: "End", 0x24: "Home", 0x25: "Left",
             0x26: "Up", 0x27: "Right", 0x28: "Down", 0x2D: "Insert",
             0x2E: "Delete", 0x91: "Scroll Lock", 0x6A: "Num *", 0x6B: "Num +",
             0x6D: "Num -", 0x6E: "Num .", 0x6F: "Num /", 0xC0: "`"}
KEY_NAMES.update({0x70 + i: f"F{i + 1}" for i in range(24)})
KEY_NAMES.update({0x60 + i: f"Num {i}" for i in range(10)})
KEY_NAMES.update({0x30 + i: str(i) for i in range(10)})
KEY_NAMES.update({0x41 + i: chr(0x41 + i) for i in range(26)})

# Keys ARK needs for this bot or for normal play; binding them would fight it.
GAME_KEYS = {0x1B, 0x09, 0x20} | {ord(c) for c in "WASDEFCQ"}


def key_name(vk):
    return KEY_NAMES.get(vk, f"Key 0x{vk:02X}")


def is_down(vk):
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


class QueueWriter:
    """Stands in for stdout/stderr so the bot's print() lands in the app."""

    def __init__(self, q):
        self.q = q

    def write(self, s):
        if s:
            self.q.put(s)

    def flush(self):
        pass


# ------------------------------------------------------------------ overlay

class Overlay:
    """Small always-on-top, click-through progress panel. Lives in the top-left
    corner (y < 118) so it never covers anything the bot reads on screen."""
    KEY = "#010203"   # transparent colour

    def __init__(self, root):
        self.win = tk.Toplevel(root)
        w = self.win
        w.title("Chem Bench Bot overlay")
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.configure(bg=self.KEY)
        w.attributes("-transparentcolor", self.KEY)
        w.geometry("+10+34")
        self.top = tk.Label(w, text="", font=("Segoe UI Semibold", 15), fg="#5ef0a0",
                            bg=self.KEY)
        self.top.pack(anchor="w")
        self.sub = tk.Label(w, text="", font=("Segoe UI", 10), fg="#e8eef4", bg=self.KEY)
        self.sub.pack(anchor="w")
        w.update_idletasks()
        self._click_through()

    def _click_through(self):
        GWL_EXSTYLE = -20
        WS_EX_LAYERED, WS_EX_TRANSPARENT = 0x80000, 0x20
        WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW = 0x08000000, 0x80
        hwnd = user32.GetParent(self.win.winfo_id()) or self.win.winfo_id()
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT
                              | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)

    def show(self, top, sub, color):
        self.top.configure(text=top, fg=color)
        self.sub.configure(text=sub)
        self.win.deiconify()

    def hide(self):
        self.win.withdraw()


# ------------------------------------------------------------------ the app

class App:
    BG, PANEL, FG, DIM, ACCENT, OK, WARN, BAD = (
        "#12161c", "#1b2129", "#dfe6ee", "#8a96a3", "#33c3f0", "#3fcf7f", "#f0b33c", "#ef5a5a")

    def __init__(self, root):
        self.root = root
        self.cfg = eng.load_config()
        self.app = self.cfg.setdefault("app", {})
        self.app.setdefault("start_key", 0x78)   # F9
        self.app.setdefault("stop_key", 0x79)    # F10
        self.app.setdefault("on_top", False)
        self.app.setdefault("overlay", True)

        self.ctl = None
        self.worker = None
        self.calib = None        # running calibration subprocess
        self.capturing = None    # "start" | "stop" while waiting for a key
        self.log_q = queue.Queue()
        sys.stdout = sys.stderr = QueueWriter(self.log_q)

        self._style()
        self._build()
        self.overlay = Overlay(root)
        self.overlay.hide()
        self._load_into_form()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.attributes("-topmost", self.app["on_top"])

        threading.Thread(target=self._hotkey_loop, daemon=True).start()
        self._tick()
        print(f"{APP_TITLE} ready. {key_name(self.app['start_key'])} = start/pause, "
              f"{key_name(self.app['stop_key'])} = stop.")

    # ---------------------------------------------------------------- layout

    def _style(self):
        r = self.root
        r.title(APP_TITLE)
        r.configure(bg=self.BG)
        r.minsize(620, 640)
        r.geometry("720x1010+40+0")
        s = ttk.Style(r)
        s.theme_use("clam")
        s.configure(".", background=self.BG, foreground=self.FG, fieldbackground=self.PANEL,
                    bordercolor="#2a323d", lightcolor=self.PANEL, darkcolor=self.PANEL,
                    font=("Segoe UI", 10))
        s.configure("TFrame", background=self.BG)
        s.configure("Card.TFrame", background=self.PANEL)
        s.configure("TLabel", background=self.BG, foreground=self.FG)
        s.configure("Card.TLabel", background=self.PANEL)
        s.configure("Dim.TLabel", background=self.PANEL, foreground=self.DIM, font=("Segoe UI", 9))
        s.configure("Head.TLabel", background=self.PANEL, foreground=self.ACCENT,
                    font=("Segoe UI Semibold", 10))
        s.configure("Big.TLabel", background=self.PANEL, font=("Segoe UI Semibold", 15))
        for w in ("TCheckbutton", "TRadiobutton"):
            s.configure(w, background=self.PANEL, foreground=self.FG)
            s.map(w, background=[("active", self.PANEL)])
        s.configure("TButton", background="#26303b", foreground=self.FG, padding=(10, 5),
                    bordercolor="#2f3a46")
        s.map("TButton", background=[("active", "#303c49")])
        s.configure("Go.TButton", background="#1f6f4a", font=("Segoe UI Semibold", 11), padding=(14, 8))
        s.map("Go.TButton", background=[("active", "#26875a")])
        s.configure("Stop.TButton", background="#7a2a2a", font=("Segoe UI Semibold", 11), padding=(14, 8))
        s.map("Stop.TButton", background=[("active", "#933333")])
        s.configure("TEntry", foreground=self.FG, insertcolor=self.FG, padding=4)
        s.configure("TCombobox", foreground=self.FG, arrowcolor=self.FG)
        s.map("TCombobox", fieldbackground=[("readonly", "#26303b")],
              foreground=[("readonly", self.FG)], selectbackground=[("readonly", "#26303b")],
              selectforeground=[("readonly", self.FG)])
        r.option_add("*TCombobox*Listbox.background", "#26303b")
        r.option_add("*TCombobox*Listbox.foreground", self.FG)

    def _card(self, parent, title):
        f = ttk.Frame(parent, style="Card.TFrame", padding=(12, 7))
        f.pack(fill="x", pady=(0, 6))
        ttk.Label(f, text=title, style="Head.TLabel").pack(anchor="w", pady=(0, 3))
        body = ttk.Frame(f, style="Card.TFrame")
        body.pack(fill="x")
        return body

    def _field(self, grid, row, label, var, hint, width=10):
        ttk.Label(grid, text=label, style="Card.TLabel").grid(row=row, column=0, sticky="w", pady=3)
        ttk.Entry(grid, textvariable=var, width=width).grid(row=row, column=1, sticky="w", padx=8)
        ttk.Label(grid, text=hint, style="Dim.TLabel").grid(row=row, column=2, sticky="w")

    def _build(self):
        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill="both", expand=True)

        # status + controls
        st = ttk.Frame(outer, style="Card.TFrame", padding=(12, 10))
        st.pack(fill="x", pady=(0, 8))
        top = ttk.Frame(st, style="Card.TFrame")
        top.pack(fill="x")
        self.dot = tk.Canvas(top, width=16, height=16, bg=self.PANEL, highlightthickness=0)
        self.dot.pack(side="left", padx=(0, 8))
        self.dot_id = self.dot.create_oval(2, 2, 14, 14, fill=self.DIM, outline="")
        self.state_lbl = ttk.Label(top, text="Idle", style="Big.TLabel")
        self.state_lbl.pack(side="left")
        self.detail_lbl = ttk.Label(st, text="", style="Dim.TLabel")
        self.detail_lbl.pack(anchor="w", pady=(4, 8))
        btns = ttk.Frame(st, style="Card.TFrame")
        btns.pack(fill="x")
        self.go_btn = ttk.Button(btns, text="Start", style="Go.TButton", command=self.toggle)
        self.go_btn.pack(side="left")
        ttk.Button(btns, text="Stop", style="Stop.TButton", command=self.stop).pack(side="left", padx=8)
        self.keys_lbl = ttk.Label(btns, text="", style="Dim.TLabel")
        self.keys_lbl.pack(side="left", padx=8)

        # stations
        sc = self._card(outer, "Stations (visited in order, forever)")
        self.station_vars, self.station_lbls = [], []
        for st_cfg in self.cfg["stations"]:
            row = ttk.Frame(sc, style="Card.TFrame")
            row.pack(fill="x", pady=1)
            v = tk.BooleanVar()
            self.station_vars.append(v)
            label = self.cfg["layouts"][st_cfg["layout"]].get("label", st_cfg["layout"])
            ttk.Checkbutton(row, text=f"{st_cfg['name']}  ({label})", variable=v,
                            width=24).pack(side="left")
            lbl = ttk.Label(row, text="", style="Dim.TLabel")
            lbl.pack(side="left")
            self.station_lbls.append(lbl)
        ttk.Label(sc, text="Main bed first; the others are spares used if it's on cooldown. "
                           "Number = calibrated targets on that bed.",
                  style="Dim.TLabel").pack(anchor="w", pady=(4, 0))

        # crafting settings
        cc = self._card(outer, "Crafting")
        g = ttk.Frame(cc, style="Card.TFrame")
        g.pack(fill="x")
        self.chem_pull, self.chem_presses = tk.StringVar(), tk.StringVar()
        self.fab_search, self.fab_pull, self.fab_presses = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.wait_var = tk.StringVar()
        ttk.Label(g, text="Chem benches → Gunpowder", style="Head.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w")
        self._field(g, 1, "Pull amount", self.chem_pull, "typed in the amount box, then pull (blank = no pull)")
        self._field(g, 2, "A presses", self.chem_presses, "each press queues 100")
        ttk.Label(g, text="Fabricators", style="Head.TLabel").grid(
            row=3, column=0, columnspan=3, sticky="w", pady=(8, 0))
        self._field(g, 4, "Search", self.fab_search, "typed in the fabricator's search box", width=18)
        self._field(g, 5, "Pull amount", self.fab_pull, "")
        self._field(g, 6, "A presses", self.fab_presses, "")
        self._field(g, 7, "Wait between cycles (min)", self.wait_var, "after every station is done")

        # start + calibrate
        sm = self._card(outer, "Start & calibration")
        self.mode_var = tk.StringVar(value="travel")
        ttk.Radiobutton(sm, text="Travel to the first station before starting (recommended)",
                        variable=self.mode_var, value="travel").pack(anchor="w")
        hr = ttk.Frame(sm, style="Card.TFrame")
        hr.pack(anchor="w")
        ttk.Radiobutton(hr, text="I just spawned on bed", variable=self.mode_var,
                        value="here").pack(side="left")
        self.here_var = tk.StringVar()
        self.here_box = ttk.Combobox(hr, textvariable=self.here_var, width=8, state="readonly")
        self.here_box.pack(side="left", padx=6)
        cr = ttk.Frame(sm, style="Card.TFrame")
        cr.pack(anchor="w", pady=(8, 0))
        ttk.Label(cr, text="Calibrate bed", style="Card.TLabel").pack(side="left")
        self.cal_var = tk.StringVar()
        self.cal_box = ttk.Combobox(cr, textvariable=self.cal_var, width=8, state="readonly")
        self.cal_box.pack(side="left", padx=6)
        ttk.Button(cr, text="Calibrate", command=self.calibrate).pack(side="left")
        ttk.Label(sm, text="Travels to the bed and finds every bench it can open (~5 min). "
                           "Hands off the mouse meanwhile.",
                  style="Dim.TLabel").pack(anchor="w", pady=(4, 0))

        # hotkeys + options
        hk = self._card(outer, "Hotkeys & options")
        hrow = ttk.Frame(hk, style="Card.TFrame")
        hrow.pack(fill="x")
        ttk.Label(hrow, text="Start / pause", style="Card.TLabel").grid(row=0, column=0, sticky="w")
        self.start_key_btn = ttk.Button(hrow, width=14, command=lambda: self.capture("start"))
        self.start_key_btn.grid(row=0, column=1, padx=8, pady=2)
        ttk.Label(hrow, text="Stop", style="Card.TLabel").grid(row=0, column=2, sticky="w", padx=(10, 0))
        self.stop_key_btn = ttk.Button(hrow, width=14, command=lambda: self.capture("stop"))
        self.stop_key_btn.grid(row=0, column=3, padx=8, pady=2)
        ttk.Label(hk, text="Click a box, then press the key you want (mouse side buttons work). "
                           "Esc cancels.", style="Dim.TLabel").pack(anchor="w", pady=(4, 4))
        self.top_var = tk.BooleanVar()
        ttk.Checkbutton(hk, text="Keep this window on top", variable=self.top_var,
                        command=lambda: self.root.attributes("-topmost", self.top_var.get())).pack(anchor="w")
        self.ov_var = tk.BooleanVar()
        ttk.Checkbutton(hk, text="Show progress overlay in game (top-left)",
                        variable=self.ov_var).pack(anchor="w")

        # log
        lg = ttk.Frame(outer, style="Card.TFrame", padding=(12, 10))
        lg.pack(fill="both", expand=True)
        ttk.Label(lg, text="Log", style="Head.TLabel").pack(anchor="w", pady=(0, 6))
        self.log = tk.Text(lg, height=6, bg="#0d1116", fg="#c8d2dc", insertbackground=self.FG,
                           relief="flat", font=("Consolas", 9), wrap="word", state="disabled")
        self.log.pack(fill="both", expand=True)
        self.log.tag_configure("bad", foreground=self.BAD)
        self.log.tag_configure("ok", foreground=self.OK)

    # ---------------------------------------------------------------- settings

    def _all_beds(self):
        return [b for st in self.cfg["stations"] for b in st["beds"]]

    def _refresh_stations(self):
        bt = self.cfg.get("bed_targets", {})
        for st_cfg, lbl in zip(self.cfg["stations"], self.station_lbls):
            parts = []
            for b in st_cfg["beds"]:
                n = len(bt.get(b, {}).get("targets", []))
                parts.append(f"{b} {n if n else '–'}")
            lbl.configure(text="   ".join(parts))
        beds = self._all_beds()
        self.here_box.configure(values=beds)
        self.cal_box.configure(values=beds)
        if not self.cal_var.get() and beds:
            self.cal_var.set(beds[0])
        if not self.here_var.get() and beds:
            self.here_var.set(beds[0])

    def _load_into_form(self):
        c = self.cfg
        for v, st_cfg in zip(self.station_vars, c["stations"]):
            v.set(st_cfg.get("enabled", True))
        ch, fb = c["layouts"]["chem"], c["layouts"]["fab"]
        self.chem_pull.set(ch.get("pull_amount", ""))
        self.chem_presses.set(str(ch["craft_presses"]))
        self.fab_search.set(fb.get("search", ""))
        self.fab_pull.set(fb.get("pull_amount", ""))
        self.fab_presses.set(str(fb["craft_presses"]))
        self.wait_var.set(f"{c['cycle_wait_minutes']:g}")
        self.top_var.set(self.app["on_top"])
        self.ov_var.set(self.app["overlay"])
        self._refresh_keys()
        self._refresh_stations()

    def _refresh_keys(self):
        self.start_key_btn.configure(text=key_name(self.app["start_key"]))
        self.stop_key_btn.configure(text=key_name(self.app["stop_key"]))
        self.keys_lbl.configure(text=f"{key_name(self.app['start_key'])} start/pause  ·  "
                                     f"{key_name(self.app['stop_key'])} stop")

    def _form_to_cfg(self):
        """Validate the form into self.cfg. Returns an error string or None."""
        try:
            chem_presses = int(self.chem_presses.get())
            fab_presses = int(self.fab_presses.get())
            wait = float(self.wait_var.get())
        except ValueError:
            return "A presses and wait must be numbers."
        if not (1 <= chem_presses <= 50 and 1 <= fab_presses <= 50):
            return "A presses should be between 1 and 50."
        if wait < 0:
            return "Wait can't be negative."
        for pull in (self.chem_pull.get().strip(), self.fab_pull.get().strip()):
            if pull and not pull.isdigit():
                return "Pull amounts must be whole numbers (or blank)."
        if not any(v.get() for v in self.station_vars):
            return "Tick at least one station."
        c = self.cfg
        for v, st_cfg in zip(self.station_vars, c["stations"]):
            st_cfg["enabled"] = bool(v.get())
        ch, fb = c["layouts"]["chem"], c["layouts"]["fab"]
        ch["pull_amount"] = self.chem_pull.get().strip()
        ch["craft_presses"] = chem_presses
        fb["search"] = self.fab_search.get().strip()
        fb["pull_amount"] = self.fab_pull.get().strip()
        fb["craft_presses"] = fab_presses
        c["cycle_wait_minutes"] = wait
        self.app["on_top"] = bool(self.top_var.get())
        self.app["overlay"] = bool(self.ov_var.get())
        return None

    def save(self):
        err = self._form_to_cfg()
        if err:
            return err
        # keep calibration results written by calibrate_bed.py meanwhile
        if eng.CONFIG_PATH.exists():
            disk = json.loads(eng.CONFIG_PATH.read_text())
            self.cfg["bed_targets"] = disk.get("bed_targets", self.cfg.get("bed_targets", {}))
        eng.CONFIG_PATH.write_text(json.dumps(self.cfg, indent=2))
        return None

    # ---------------------------------------------------------------- run control

    def running(self):
        return self.worker is not None and self.worker.is_alive()

    def toggle(self):
        if not self.running():
            self.start()
        elif self.ctl.paused:
            self.ctl.paused = False
            print("[resumed]")
        else:
            self.ctl.paused = True
            print("[paused]")

    def start(self):
        if self.calib and self.calib.poll() is None:
            messagebox.showinfo(APP_TITLE, "A calibration is running; wait for it to finish.")
            return
        err = self.save()
        if err:
            messagebox.showerror(APP_TITLE, err)
            return
        cfg = copy.deepcopy(self.cfg)
        stations = eng.stations_from(cfg)
        if not stations:
            messagebox.showerror(APP_TITLE, "None of the ticked stations has a calibrated bed yet. "
                                            "Use Calibrate first.")
            return
        here = self.here_var.get() if self.mode_var.get() == "here" else None
        if here and not any(here in st["beds"] for st in stations[:1]):
            messagebox.showerror(APP_TITLE, f"{here} isn't a bed of the first station "
                                            f"({stations[0]['name']}).")
            return
        self.ctl = eng.Control(cfg["window_title"], paused=False, hotkeys=False)
        ctl = self.ctl

        def work():
            try:
                eng.run_loop(cfg, stations, here, ctl)
            except Exception:
                print("CRASHED:\n" + traceback.format_exc())
        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()
        print(f"[started {time.strftime('%H:%M:%S')}] switch to ARK - the bot waits until ARK is focused")

    def stop(self):
        if self.running():
            self.ctl.stopped = True
            print("[stopping...]")
        if self.calib and self.calib.poll() is None:
            self.calib.terminate()
            print("[calibration stopped]")

    def calibrate(self):
        if self.running():
            messagebox.showinfo(APP_TITLE, "Stop the bot first.")
            return
        if self.calib and self.calib.poll() is None:
            return
        bed = self.cal_var.get()
        st = next(s for s in self.cfg["stations"] if bed in s["beds"])
        err = self.save()
        if err:
            messagebox.showerror(APP_TITLE, err)
            return
        pitches = ",".join(str(p) for p in self.cfg["layouts"][st["layout"]]["sweep_pitches"])
        cmd = [sys.executable.replace("pythonw.exe", "python.exe"), "-u", "calibrate_bed.py",
               bed, st["layout"], "--step", "75", "--pitches", pitches]
        print(f"calibrating {bed} - switch to ARK and don't touch the mouse")
        self.calib = subprocess.Popen(cmd, cwd=HERE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                      text=True, creationflags=0x08000000)

        def pump(proc):
            for line in proc.stdout:
                self.log_q.put(line)
            proc.wait()
            self.root.after(0, self._calib_done)
        threading.Thread(target=pump, args=(self.calib,), daemon=True).start()

    def _calib_done(self):
        disk = json.loads(eng.CONFIG_PATH.read_text())
        self.cfg["bed_targets"] = disk.get("bed_targets", {})
        self._refresh_stations()
        print("calibration finished")

    # ---------------------------------------------------------------- hotkeys

    def _hotkey_loop(self):
        was = {}
        while True:
            if self.capturing:
                time.sleep(0.03)
                continue
            for which in ("start_key", "stop_key"):
                vk = self.app[which]
                down = is_down(vk)
                if down and not was.get(vk):
                    self.root.after(0, self.toggle if which == "start_key" else self.stop)
                was[vk] = down
            time.sleep(0.02)

    def capture(self, which):
        if self.running():
            messagebox.showinfo(APP_TITLE, "Stop the bot before changing hotkeys.")
            return
        self.capturing = which
        btn = self.start_key_btn if which == "start" else self.stop_key_btn
        btn.configure(text="press a key…")
        threading.Thread(target=self._capture_key, args=(which,), daemon=True).start()

    def _capture_key(self, which):
        time.sleep(0.3)  # let go of the mouse click
        # skip left/right click and bare modifiers
        skip = {0x01, 0x02, 0x10, 0x11, 0x12, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5}
        while True:
            for vk in range(0x04, 0xFF):
                if vk in skip or not is_down(vk):
                    continue
                while is_down(vk):
                    time.sleep(0.02)
                self.root.after(0, self._set_key, which, vk)
                return
            time.sleep(0.02)

    def _set_key(self, which, vk):
        self.capturing = None
        if vk == 0x1B:
            self._refresh_keys()
            return
        other = self.app["stop_key" if which == "start" else "start_key"]
        if vk == other:
            messagebox.showwarning(APP_TITLE, "That key is already used for the other action.")
        elif vk in GAME_KEYS:
            messagebox.showwarning(APP_TITLE, f"{key_name(vk)} is used by ARK/the bot. Pick another "
                                              "key (F-keys, numpad or mouse side buttons work well).")
        else:
            self.app[f"{which}_key"] = vk
            self.save()
            print(f"{which} hotkey set to {key_name(vk)}")
        self._refresh_keys()

    # ---------------------------------------------------------------- UI loop

    def _tick(self):
        chunks = []
        while not self.log_q.empty():
            chunks.append(self.log_q.get_nowait())
        if chunks:
            self.log.configure(state="normal")
            for line in "".join(chunks).splitlines(keepends=True):
                tag = "bad" if ("!" in line[:6] or "FAILED" in line or "CRASH" in line
                                or "PAUSED" in line or "did not open" in line) else (
                    "ok" if ("queued" in line or "OK" in line) else "")
                self.log.insert("end", line, tag)
            lines = int(self.log.index("end-1c").split(".")[0])
            if lines > 800:
                self.log.delete("1.0", f"{lines - 800}.0")
            self.log.see("end")
            self.log.configure(state="disabled")

        ov_top = ov_sub = None
        ov_color = self.OK
        if self.running():
            c = self.ctl
            p = c.progress or {}
            focused = c.title.lower() in eng.window_title().lower()
            prog = ""
            if p:
                prog = (f"{p['station']} ({p['bed']}) · {p['done']}/{p['total']} crafted"
                        + (f", {p['failed']} missed" if p["failed"] else ""))
            if c.stopped:
                state, color, detail = "Stopping…", self.WARN, ""
            elif c.paused:
                state, color, detail = "Paused", self.WARN, f"press {key_name(self.app['start_key'])} to resume"
            elif not focused:
                state, color, detail = "Waiting for ARK", self.WARN, "switch to the ARK window"
            elif c.next_run:
                left = max(0, int(c.next_run - time.time()))
                state, color = "Waiting", self.ACCENT
                detail = (f"cycle {p.get('cycle', 0)} done · next run "
                          f"{time.strftime('%H:%M', time.localtime(c.next_run))} "
                          f"(in {left // 60}:{left % 60:02d})")
            else:
                state, color, detail = "Running", self.OK, c.status
            self.go_btn.configure(text="Resume" if c.paused else "Pause")
            ov_top = prog or state
            ov_sub = f"{state} · {detail}" if detail else state
            if p and not c.next_run and not c.paused:
                ov_sub = f"cycle {p['cycle']} · {p['visited']}/{p['total']} visited · {c.status}"
            ov_color = color
        elif self.calib and self.calib.poll() is None:
            state, color, detail = "Calibrating", self.ACCENT, f"{self.cal_var.get()} - don't touch the mouse"
            self.go_btn.configure(text="Start")
        else:
            state, color, detail = "Idle", self.DIM, "settings are saved when you press Start"
            self.go_btn.configure(text="Start")
        self.state_lbl.configure(text=state)
        self.detail_lbl.configure(text=detail)
        self.dot.itemconfigure(self.dot_id, fill=color)
        if ov_top and self.ov_var.get():
            self.overlay.show(ov_top, ov_sub, ov_color)
        else:
            self.overlay.hide()
        self.root.after(250, self._tick)

    def on_close(self):
        if self.running() or (self.calib and self.calib.poll() is None):
            if not messagebox.askyesno(APP_TITLE, "The bot is running. Stop it and close?"):
                return
            self.stop()
        self.save()
        self.root.destroy()


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
