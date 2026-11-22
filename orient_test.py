"""Test strip-based orientation: capture a reference, turn a known amount,
capture again, and check the matcher recovers the turn."""
import sys
import time

import numpy as np

import ark_chem as a
import ark_probe

cfg = a.load_config()
bot = a.Bot(cfg, None)
ark_probe.focus()

t0 = time.time()
ref = a.capture_strip(bot)
print(f"reference strip {ref.shape} in {time.time() - t0:.1f}s")
np.save("templates/room_ref_test.npy", ref)

for turn in [int(x) for x in sys.argv[1:]] or [1700]:
    bot.turn(turn, 0)          # pretend we spawned facing `turn` further right
    cur = a.capture_strip(bot)
    off, score = a.match_strip(ref, cur)
    print(f"turned {turn:+5d}: matcher says offset {off:+5d} (score {score:.3f})")
    bot.turn(-turn, 0)
