"""Does stepping in small increments lose mouse counts?
Do N steps of S right, one big move back, measure net drift by strip match."""
import sys
import time

import ark_chem as a
import ark_probe

cfg = a.load_config()
bot = a.Bot(cfg, None)
ark_probe.focus()
ref = a.capture_strip(bot)
for spec in sys.argv[1:]:
    s, n, delay = spec.split("/")
    s, n, delay = int(s), int(n), float(delay)
    before, _ = a.match_strip(ref, a.capture_strip(bot))
    bot.look_down()
    bot.turn(0, -1000)
    for _ in range(n):
        bot.turn(s, 0)
        time.sleep(delay)
    bot.turn(-s * n, 0)
    time.sleep(0.5)
    after, conf = a.match_strip(ref, a.capture_strip(bot))
    print(f"{n} steps of {s} (pause {delay}s), one move back: drift {after - before:+d} "
          f"({(after - before) / (s * n) * 100:+.1f}%) conf {conf:.1f}")
