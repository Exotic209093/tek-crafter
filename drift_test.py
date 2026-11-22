"""Measure yaw drift per out-and-back turn for a chunk/delay setting,
using strip matching (precise to ~10 counts)."""
import sys
import time

import ark_chem as a
import ark_probe

cfg = a.load_config()
bot = a.Bot(cfg, None)
ark_probe.focus()
ref = a.capture_strip(bot)
for spec in sys.argv[1:]:
    chunk, delay = spec.split("/")
    cfg["look"]["chunk"], cfg["look"]["chunk_delay_s"] = int(chunk), float(delay)
    before, _ = a.match_strip(ref, a.capture_strip(bot))
    t0 = time.time()
    for _ in range(6):
        bot.look_down()
        bot.turn(1800, -1000)
        time.sleep(0.15)
        bot.turn(-1800, 0)
    took = time.time() - t0
    after, score = a.match_strip(ref, a.capture_strip(bot))
    print(f"chunk {chunk:>3} delay {delay}: drift {(after - before) / 6:+.0f} counts per round trip "
          f"(6 trips {took:.1f}s, score {score:.2f})")
