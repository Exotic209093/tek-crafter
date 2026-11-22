"""Add a room reference strip for a layout (e.g. a daytime one).

usage: python make_ref.py LAYOUT OUT.npy [--fresh]
  default: orient with the layout's existing refs (accepting a weak match),
           PROVE it by opening two known targets and checking an empty
           direction stays empty, then turn to yaw 0 and capture.
  --fresh: the current facing IS yaw 0 (first ever reference for a room,
           taken right after spawning on its bed)."""
import sys

import numpy as np

import ark_chem as a
import ark_probe

layout_name, out = sys.argv[1], sys.argv[2]
fresh = "--fresh" in sys.argv
cfg = a.load_config()
cfg["timing"]["orient_min_conf"] = 1.05
layout = cfg["layouts"][layout_name]
ctl = a.Control(cfg["window_title"], paused=False, hotkeys=False)
bot = a.Bot(cfg, ctl)
ark_probe.focus()


def opens(yaw, pitch):
    bot.aim(yaw, pitch)
    a.tap("f")
    ok = ctl.wait_for(lambda: bot.seen("bench_open"), 4)
    if ok:
        bot.close_bench()
    return ok


if not fresh:
    refs = [r for r in layout["refs"] if r != out and (a.TEMPLATES / r).exists()]
    bot.orient(dict(layout, refs=refs))
    t = layout["targets"]
    checks = [(t[0], True), (t[len(t) // 2], True), (t[-1], True)]
    results = [(c["name"], opens(c["yaw"], c["pitch"]) == want) for c, want in checks]
    print("proof:", results)
    if not all(ok for _, ok in results):
        sys.exit("orientation NOT proven - reference not saved")
    bot.face_home()
strip = a.capture_strip(bot)
np.save(a.TEMPLATES / out, strip)
a._ref_cache.pop(out, None)
off, conf = a.match_strip(strip, a.capture_strip(bot))
print(f"saved {out}; self-check offset {off:+d} confidence {conf:.1f}")
ctl.stopped = True
