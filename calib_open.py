"""Open each candidate aim, grab the bench's storage area, report duplicates.
usage: python calib_open.py yaw:pitch:label ..."""
import sys
import time

import numpy as np
from PIL import Image, ImageDraw, ImageGrab

import ark_chem as a
import ark_probe

aims = []
for s in sys.argv[1:]:
    p = s.split(":")
    aims.append((int(p[0]), int(p[1]), p[2]))
cfg = a.load_config()
ctl = a.Control(cfg["window_title"], paused=False, hotkeys=False)
bot = a.Bot(cfg, ctl)
ark_probe.focus()
crops, labels = [], []
for yaw, pitch, label in aims:
    bot.look_down()
    bot.turn(yaw, -pitch)
    time.sleep(0.7)
    a.tap("f")
    ok = ctl.wait_for(lambda: a.on_screen(cfg, "bench_open"), 5)
    if ok:
        ctl.wait_for(lambda: a.on_screen(cfg, "grid_ready"), 4)
        time.sleep(0.4)
        im = ImageGrab.grab(bbox=(1243, 420, 1800, 700)).convert("RGB")
        a.tap("esc")
        ctl.wait_for(lambda: not a.on_screen(cfg, "bench_open"), 4)
    else:
        im = Image.new("RGB", (557, 280), (90, 0, 0))
    bot.turn(-yaw, 0)
    print(f"{label}: {'opened' if ok else 'DID NOT OPEN'}")
    d = ImageDraw.Draw(im)
    d.text((5, 5), label, fill="yellow", font_size=30)
    crops.append(im)
    labels.append(label)

# duplicates: compare item-count regions
arrs = [np.asarray(c.convert("L").resize((140, 70)), dtype=np.float32) for c in crops]
for i in range(len(arrs)):
    for j in range(i + 1, len(arrs)):
        diff = np.abs(arrs[i] - arrs[j]).mean()
        if diff < 4:
            print(f"  possible SAME bench: {labels[i]} ~ {labels[j]} (diff {diff:.1f})")
cols = 3
g = Image.new("RGB", (557 * cols, 280 * ((len(crops) + cols - 1) // cols)))
for i, c in enumerate(crops):
    g.paste(c, ((i % cols) * 557, (i // cols) * 280))
g.save("shots/opened.png")
ctl.stopped = True

