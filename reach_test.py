"""Travel to BED (exact name), then check which of a layout's 18 default aims
show the structure name prompt, and optionally open each one.
usage: python reach_test.py BED LAYOUT [--here] [--open]"""
import sys

from PIL import ImageGrab

import ark_chem as a
import ark_probe

bed, layout_name = sys.argv[1], sys.argv[2]
cfg = a.load_config()
layout = cfg["layouts"][layout_name]
ctl = a.Control(cfg["window_title"], paused=False, hotkeys=False)
bot = a.Bot(cfg, ctl)
ark_probe.focus()
bot.recover()
if "--here" not in sys.argv:
    bot.travel_to(bed)
bot.yaw, bot.pitch = 0, None
AREA = (0, 120, 1840, 1040)
ok_n = 0
for t in layout["targets"]:
    bot.aim(t["yaw"], t["pitch"])
    img = ImageGrab.grab(bbox=AREA)
    pr = layout["prompt"]
    ok = a.find_text_line(img, pr["template"], pr["kind"], AREA, origin=AREA[:2]) >= pr["min"]
    if ok and "--open" in sys.argv:
        a.tap(cfg["keys"]["access"])
        ok = ctl.wait_for(lambda: bot.seen("bench_open"), 5)
        if ok:
            bot.close_bench()
    ok_n += ok
    print(f"  {t['name']}: {'OK' if ok else 'NO'}")
bot.face_home()
print(f"{bed}: {ok_n}/{len(layout['targets'])}")
ctl.stopped = True
