"""Stepped-turn drift with Windows pointer precision ON vs OFF.
Shift is measured by correlating before/after screenshots (px -> counts).
The original mouse setting is always restored."""
import ctypes
import time

import numpy as np
from PIL import ImageGrab

import ark_chem as a
import ark_probe

SPI_GETMOUSE, SPI_SETMOUSE = 0x0003, 0x0004
u = ctypes.windll.user32
orig = (ctypes.c_int * 3)()
u.SystemParametersInfoW(SPI_GETMOUSE, 0, orig, 0)
cfg = a.load_config()
bot = a.Bot(cfg, None)
ark_probe.focus()


def prof():
    g = np.asarray(ImageGrab.grab(bbox=(0, 250, 1920, 830)).convert("L"), dtype=np.float32)
    p = g.mean(axis=0)
    return p - p.mean()


def shift(p1, p2, m=500):
    best, arg = -1e18, 0
    for s in range(-m, m + 1):
        a1 = p1[max(0, s):1920 + min(0, s)]
        a2 = p2[max(0, -s):1920 - max(0, s)]
        v = float((a1 * a2).sum()) / len(a1)
        if v > best:
            best, arg = v, s
    return arg


def run(label):
    bot.look_down(); bot.turn(0, -1000); time.sleep(0.6)
    p1 = prof()
    for _ in range(40):
        bot.turn(50, 0)
        time.sleep(0.22)
    bot.turn(-2000, 0)
    time.sleep(0.6)
    p2 = prof()
    s = shift(p1, p2)
    print(f"{label}: 40 steps of 50 then one move back -> view shifted {s:+d}px "
          f"(~{s / 0.87:+.0f} counts, {s / 0.87 / 2000 * 100:+.1f}%)")
    # undo the drift so the next test starts from the same facing
    bot.turn(int(round(s / 0.87)), 0)


try:
    run("pointer precision ON ")
    u.SystemParametersInfoW(SPI_SETMOUSE, 0, (ctypes.c_int * 3)(0, 0, 0), 0)
    run("pointer precision OFF")
finally:
    u.SystemParametersInfoW(SPI_SETMOUSE, 0, orig, 0)
    back = (ctypes.c_int * 3)()
    u.SystemParametersInfoW(SPI_GETMOUSE, 0, back, 0)
    print("restored", list(back))
