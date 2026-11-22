"""For each bed name, filter the map and report whether a bed icon shows.
usage: python check_names.py NAME [NAME...]"""
import sys
import time

import numpy as np
from PIL import ImageGrab

import ark_chem as a
import ark_probe

cfg = a.load_config()
ui = cfg["ui"]
ctl = a.Control(cfg["window_title"], paused=False, hotkeys=False)
bot = a.Bot(cfg, ctl)
ark_probe.focus()
bot.recover()
bot.open_map()
for name in sys.argv[1:]:
    a.click(*ui["bed_filter"])
    for _ in range(8):
        a.tap("backspace", hold=0.01)
    a.type_text(name)
    time.sleep(0.8)
    a.move_to(1000, 800)
    time.sleep(0.3)
    a.click(*ui["bed_icon"])
    time.sleep(0.8)
    a.move_to(1000, 800)
    time.sleep(0.3)
    img = np.asarray(ImageGrab.grab().convert("L")).astype(int)
    x0, y0 = ui["bed_list_first"]
    rows = []
    for i in range(4):
        yy = y0 + i * ui["bed_list_step"]
        rows.append(int((img[yy - 10:yy + 10, x0 - 110:x0 + 130] > 100).sum()))
    n = sum(1 for r in rows if r > 60)
    ImageGrab.grab().crop((560, 940, 960, 1010)).save(f"shots/chkbtn_{name}.png")
    print(f"{name}: {n} bed(s) listed {rows}")
    a.click(*ui["bed_icon"])
    time.sleep(0.4)
bot.recover()
ctl.stopped = True
