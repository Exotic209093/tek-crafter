"""Turn raw sweep hits into one aim per structure.

A hit is (yaw, ax, ay, pitch, x, y): the crosshair at (yaw, pitch) showed the
structure name line with its left edge at screen (x, y). Name prompts are
drawn at the structure, so:
  * the line's height on screen tells which ROW (low/high) it belongs to:
    anchor pitch = pitch - (y - 540) / PY_PROMPT is ~constant per row;
  * within one sweep, the line drifts smoothly while the crosshair stays on
    one structure and jumps when it moves to the next.
For each row we use the sweep pitch that saw the row most, split its hits at
the jumps, and aim at the middle of each run.
"""
TURN = 5000
PX_PROMPT = 0.74   # prompt x drift per yaw count (measured, near structures)
PY_PROMPT = 0.68   # prompt y drift per pitch count (measured)


def find_aims(hits, min_run=2, step=50):
    near = int(step * 1.5)
    rows = []  # list of lists of (anchor_pitch, hit)
    for h in sorted(hits, key=lambda h: h[3] - (h[5] - 540) / PY_PROMPT):
        ap = h[3] - (h[5] - 540) / PY_PROMPT
        if rows and ap - rows[-1][-1][0] < 200:
            rows[-1].append((ap, h))
        else:
            rows.append([(ap, h)])
    aims = []
    for row in rows:
        by_pitch = {}
        for _, h in row:
            by_pitch.setdefault(h[3], []).append(h)
        # among sweeps that saw most of this row, use the one where the prompt
        # sat nearest mid-screen: there it tracks the structure cleanly (near
        # the screen edge it gets clamped/distorted)
        most = max(len(v) for v in by_pitch.values())
        good = [p for p in by_pitch if len(by_pitch[p]) >= 0.7 * most]
        pitch = min(good, key=lambda p: abs(sorted(h[5] for h in by_pitch[p])[len(by_pitch[p]) // 2] - 600))
        hs = sorted(by_pitch[pitch], key=lambda h: h[0])
        runs = []
        for h in hs:
            ax = h[0] + (h[4] - 960) / PX_PROMPT
            if runs:
                py, pax = runs[-1][-1]
                if h[0] - py <= near and abs(ax - pax) < 100:
                    runs[-1].append((h[0], ax))
                    continue
            runs.append([(h[0], ax)])
        # a run cut by the +-2500 seam: join last and first
        if len(runs) > 1:
            first, last = runs[0], runs[-1]
            if (first[0][0] + TURN) - last[-1][0] <= near and \
                    abs((first[0][1] + TURN) - last[-1][1]) < 100:
                runs[-1] = last + [(y + TURN, a + TURN) for y, a in first]
                runs.pop(0)
        for r in runs:
            if len(r) < min_run:
                continue
            mid = (r[0][0] + r[-1][0]) / 2
            mid = ((mid + TURN // 2) % TURN) - TURN // 2
            aims.append({"yaw": int(round(mid)), "pitch": pitch, "steps": len(r)})
    return aims


if __name__ == "__main__":
    import json
    import sys
    for f in sys.argv[1:]:
        aims = find_aims(json.load(open(f)))
        print(f, len(aims), "aims")
        for a in aims:
            print("  ", a)

