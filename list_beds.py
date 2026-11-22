"""Open the map, filter, click the bed icon, save the list popup.
usage: python list_beds.py FILTER [FILTER...]"""
import sys
import time

from PIL import ImageGrab

import ark_chem as a
import ark_probe

cfg = a.load_config()
ctl = a.Control(cfg["window_title"], paused=False, hotkeys=False)
bot = a.Bot(cfg, ctl)
ark_probe.focus()
bot.open_map()
for f in sys.argv[1:]:
    a.click(*cfg["ui"]["bed_filter"])
    for _ in range(8):
        a.tap("backspace", hold=0.01)
    a.type_text(f)
    time.sleep(0.8)
    a.move_to(1000, 800)
    time.sleep(0.3)
    full = ImageGrab.grab()
    full.crop((560, 360, 1100, 700)).save(f"shots/list_{f}.png")
    a.click(*cfg["ui"]["bed_icon"])
    time.sleep(0.8)
    a.move_to(1000, 800)
    time.sleep(0.3)
    ImageGrab.grab().crop((560, 360, 1100, 700)).save(f"shots/listpop_{f}.png")
    a.click(*cfg["ui"]["bed_icon"])  # close the popup again
    time.sleep(0.4)
bot.recover()
ctl.stopped = True
print("saved")
