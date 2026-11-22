"""Find the first crafting recipe (blueprint) in a structure's item grid.

Grid slots are 93px apart starting at (1290, 278) on a 1920x1080 screen.
A recipe slot has an icon and NO quantity text; a stored stack shows a cyan
"x123" in its top-left corner; an empty slot is flat dark.
"""
import numpy as np

GRID0 = (1290, 278)
STEP_X, STEP_Y = 93, 94
COLS, ROWS = 6, 3


def slot_centers():
    return [(GRID0[0] + STEP_X * c, GRID0[1] + STEP_Y * r) for r in range(ROWS) for c in range(COLS)]


def _cyan(rgb):
    r, g, b = (rgb[..., i].astype(np.int16) for i in range(3))
    return (b > 190) & (g > 170) & (r < 140)


def slot_kind(rgb, x, y, ox=0, oy=0):
    """'empty' | 'stack' | 'recipe' for the slot centred at screen (x, y).
    rgb is a screenshot array whose top-left is at screen (ox, oy)."""
    cx, cy = x - ox, y - oy
    icon = rgb[cy - 28:cy + 22, cx - 28:cx + 28].astype(np.float32)
    if icon.size == 0:
        return "empty"
    if icon.mean(axis=2).std() < 14:
        return "empty"
    qty = rgb[cy - 48:cy - 30, cx - 46:cx + 10]
    if int(_cyan(qty).sum()) > 6:
        return "stack"
    return "recipe"


def first_recipe(rgb, ox=0, oy=0):
    for x, y in slot_centers():
        if y - oy + 30 > rgb.shape[0] or x - ox + 30 > rgb.shape[1]:
            break
        k = slot_kind(rgb, x, y, ox, oy)
        if k == "recipe":
            return x, y
    return None


if __name__ == "__main__":
    import sys
    from PIL import Image
    f = sys.argv[1]
    ox, oy = (int(sys.argv[2]), int(sys.argv[3])) if len(sys.argv) > 3 else (0, 0)
    rgb = np.asarray(Image.open(f).convert("RGB"))
    for x, y in slot_centers():
        if y - oy + 30 <= rgb.shape[0] and x - ox + 30 <= rgb.shape[1]:
            print((x, y), slot_kind(rgb, x, y, ox, oy))
    print("first recipe:", first_recipe(rgb, ox, oy))
