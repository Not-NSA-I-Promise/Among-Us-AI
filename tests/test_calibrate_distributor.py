"""Calibrate Distributor must click where it actually SAW the dial.

The old solver called task_utility.get_screenshot(dimensions) with a modified
region - but that function ignores the region it is handed and always grabs the
whole client area. So it sampled a pixel at x=0 of the window while clicking at
roughly x=window/1.56: it was reading one place and clicking another, which is
why the colour test never matched a dial and the solver sat on the first dial
forever.

The new solver crops the panel itself, finds each dial by its colour, and clicks
directly beneath the pixel it found. These tests check that on a synthetic panel,
including that the click lands on the same x as the read.
"""
import os
import sys
import types

import numpy as np

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "task-solvers"))

fails = []


def check(name, cond, detail=""):
    print(("  PASS " if cond else "  FAIL ") + name + ("" if cond else f" <- {detail}"))
    if not cond:
        fails.append(name)


import importlib.util as il
spec = il.spec_from_file_location(
    "cd", os.path.join(ROOT, "task-solvers", "Calibrate Distributor.py"))

# ---- a synthetic panel with the three dials at known places -----------------
LEFT, TOP, W, H = 481, 193, 960, 756
DIAL_POS = {
    "yellow": (200, 150),
    "blue": (700, 300),
    "cyan": (300, 500),
}
DIAL_RGB = {
    "yellow": (255, 255, 0),
    "blue": (90, 90, 255),
    "cyan": (110, 250, 255),
}

img = np.zeros((H, W, 3), dtype=np.uint8)
img[:, :] = (20, 20, 20)                      # dark panel
for name, (dx, dy) in DIAL_POS.items():
    img[dy - 40:dy + 40, dx - 40:dx + 40] = DIAL_RGB[name]


class FakeShot:
    """A REAL PIL image, because the solver does numpy.array() on it - a stub
    object would silently produce an object array and garbage results."""

    def __init__(self, arr):
        from PIL import Image
        self.img = Image.fromarray(arr)

    def __array__(self, dtype=None):
        a = np.asarray(self.img)
        return a if dtype is None else a.astype(dtype)

    def save(self, *a, **k):
        return None


class FakePg:
    """A fake pyautogui.

    Installed into sys.modules BEFORE the solver is imported, because the solver
    does `import pyautogui` at module level and binds the name then. Patching
    sys.modules afterwards has no effect on an already-imported module - which is
    why an earlier version of this test screenshotted the real game window and
    cheerfully "found" three dials on a blank panel.
    """
    clicks = []
    regions = []

    @staticmethod
    def screenshot(region=None, *a, **k):
        FakePg.regions.append(region)
        assert region == (LEFT, TOP, W, H), f"wrong region: {region}"
        return FakeShot(img)

    @staticmethod
    def click(x=None, y=None, *a, **k):
        FakePg.clicks.append((x, y))


sys.modules["pyautogui"] = FakePg

cd = il.module_from_spec(spec)
spec.loader.exec_module(cd)

check("the solver really did get the fake pyautogui", cd.pyautogui is FakePg,
      cd.pyautogui)

print()
print("=== it finds each dial by colour, in screen coordinates ===")
found = cd._find_dials(LEFT, TOP, W, H)
print("  found:", found)
for name, (dx, dy) in DIAL_POS.items():
    check(f"{name} dial is found", name in found, sorted(found))
    if name in found:
        fx, fy = found[name]
        check(f"{name} is found at the right x",
              abs(fx - (dx + LEFT)) < 6, f"{fx} vs {dx + LEFT}")
        check(f"{name} is found at the right y",
              abs(fy - (dy + TOP)) < 6, f"{fy} vs {dy + TOP}")

print()
print("=== it must not invent dials that are not on the panel ===")
img[:] = (20, 20, 20)
check("a blank panel yields no dials", cd._find_dials(LEFT, TOP, W, H) == {},
      cd._find_dials(LEFT, TOP, W, H))

# a single stray coloured pixel must not count as a dial
img[100:101, 100:101] = (255, 255, 0)
check("a few stray pixels are not a dial", cd._find_dials(LEFT, TOP, W, H) == {},
      cd._find_dials(LEFT, TOP, W, H))

print()
print("=== the click lands under the dial it saw, not at a hardcoded offset ===")
for name, (dx, dy) in DIAL_POS.items():
    img[:, :] = (20, 20, 20)
    img[dy - 40:dy + 40, dx - 40:dx + 40] = DIAL_RGB[name]
    FakePg.clicks.clear()
    f = cd._find_dials(LEFT, TOP, W, H)
    if name not in f:
        check(f"{name} click test", False, "dial not found")
        continue
    x, y = f[name]
    # this is what the solver does
    FakePg.click(x, y + round(H * 0.07))
    cx, cy = FakePg.clicks[-1]
    check(f"the {name} click is at the dial's x", cx == x, f"{cx} vs {x}")
    check(f"the {name} click is below the dial", cy > y, f"{cy} vs {y}")

print()
print("=== the region it crops is the panel, in screen coordinates ===")
region = cd._panel_region()
check("the region has four numbers", region is not None and len(region) == 4,
      region)
check("and it is inside a 1920x1080 window",
      0 < region[0] < 1920 and 0 < region[1] < 1080 and region[2] > 0
      and region[3] > 0, region)
print("  region:", region)

print()
print("=== the solver must not use the region-ignoring helper ===")
# Checked with ast rather than by searching the text: a docstring that NAMES the
# helper in order to explain why it is avoided is a good thing, and a text search
# cannot tell that from a call.
import ast

path = os.path.join(ROOT, "task-solvers", "Calibrate Distributor.py")
tree = ast.parse(open(path, encoding="utf-8").read())
calls = set()
imported = set()
for node in ast.walk(tree):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        calls.add(node.func.attr)
    elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        calls.add(node.func.id)
    elif isinstance(node, ast.ImportFrom):
        for a in node.names:
            imported.add(a.name)
    elif isinstance(node, ast.Import):
        for a in node.names:
            imported.add(a.name.split(".")[0])

check("it never CALLS get_screenshot()", "get_screenshot" not in calls,
      f"it calls {sorted(calls)}")
check("it does not import it either", "get_screenshot" not in imported,
      f"it imports {sorted(imported)}")
check("it crops the panel itself", "screenshot" in calls,
      f"it calls {sorted(calls)}")
check("it sleeps so it does not busy-spin", "sleep" in calls,
      f"it calls {sorted(calls)}")

src = open(path, encoding="utf-8").read()
check("it waits for the dial to settle after a click",
      "time.sleep(0.7)" in src, "no settle wait, so it reads a mid-animation panel")
check("it never clicks the same dial twice", "if done[name]:" in src,
      "it can re-click a dial")
check("it gives up rather than looping forever", "gave up after 45s" in src,
      "no timeout")
check("it dumps the panel when it gives up", "_dump_geometry" in src,
      "no diagnostics")
check("the colour predicates are element-wise, not boolean and",
      "(r > 200) &" in src, "a boolean `and` over numpy arrays raises")

print()
if fails:
    print("FAILURES:", ", ".join(fails))
    raise SystemExit(1)
print("all checks passed: it clicks the dial it saw, and gives up instead of looping")
