"""Calibration helper: px-per-count measurement and wall screenshots."""
import time

import numpy as np
from PIL import ImageGrab, Image

import ark_chem as a
import ark_probe

cfg = a.load_config()
bot = a.Bot(cfg, None)
ark_probe.focus()


def grab():
    return ImageGrab.grab()


def shift_px(img1, img2, max_shift=400):
    """Horizontal shift (px) of img2 relative to img1 via row-profile correlation."""
    g1 = np.asarray(img1.convert("L").crop((0, 300, 1920, 700)), dtype=np.float32).mean(axis=0)
    g2 = np.asarray(img2.convert("L").crop((0, 300, 1920, 700)), dtype=np.float32).mean(axis=0)
    g1 -= g1.mean(); g2 -= g2.mean()
    best, arg = -1e18, 0
    for s in range(-max_shift, max_shift + 1):
        a1 = g1[max(0, s):1920 + min(0, s)]
        a2 = g2[max(0, -s):1920 - max(0, s)]
        v = float((a1 * a2).sum()) / len(a1)
        if v > best:
            best, arg = v, s
    return arg


# px per count around the right wall
bot.look_down(); bot.turn(1500, -1300); time.sleep(0.5)
i1 = grab()
bot.turn(100, 0); time.sleep(0.5)
i2 = grab()
bot.turn(-100, 0); time.sleep(0.3)
s = shift_px(i1, i2)
print(f"100 counts -> {s} px  ({abs(s) / 100:.2f} px/count)")

# wall shots at a pitch that shows both levels
for name, yaw in (("right", 1500), ("back", 2750), ("left", -1000)):
    bot.look_down(); bot.turn(yaw, -1330); time.sleep(0.5)
    grab().save(f"shots/wall_{name}.png")
    bot.turn(-yaw, 0)
print("saved")
