"""Sweep 360 at given pitches; print where the bench name prompt shows.
usage: python sweep_map.py STEP PITCH [PITCH...]"""
import sys
import time

import ark_chem as a
import ark_probe

step = int(sys.argv[1])
pitches = [int(p) for p in sys.argv[2:]]
cfg = a.load_config()
bot = a.Bot(cfg, None)
ark_probe.focus()
AREA = (0, 120, 1840, 1040)
t0 = time.time()
for pitch in pitches:
    bot.look_down()
    bot.turn(0, -pitch)
    row = []
    yaw = 0
    for target in range(0, a.TURN, step):
        bot.turn(target - yaw, 0)
        yaw = target
        time.sleep(0.3)
        from PIL import ImageGrab
        img = ImageGrab.grab(bbox=AREA)
        s = a.find_text_line(img, "bench_name", "green", AREA, origin=AREA[:2])
        row.append("#" if s >= 0.7 else ".")
    bot.turn(-yaw, 0)
    line = "".join(row)
    print(f"pitch {pitch}: {line}")
print(f"  (each char = {step} counts from 0; {time.time() - t0:.0f}s)")
