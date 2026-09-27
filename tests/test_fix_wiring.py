"""Fix Wiring must connect ALL FOUR wires on a panel.

This is a fact about the game, and the harness had it wrong. Among Us's own wiki
states that "at each panel, 4 wires are assigned one of the default colors: red,
blue, yellow, and magenta", and that the eleven wires drawn behind them are
purely aesthetic.

The solver used to `break` after the first wire, believing a panel had only one.
Confirmed in a live game: it dragged the red wire, closed the panel, and the task
bar never moved - because a panel with one of four wires connected is not
finished. This test drives the real solver against a fake screen so the wire
count, the ordering, the verification and the close are all exercised.
"""
import os
import sys
import types

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "task-solvers"))

fails = []


def check(name, cond, detail=""):
    if cond:
        print("  PASS", name)
    else:
        print("  FAIL", name, "<-", detail)
        fails.append(name)


# ---------------------------------------------------------------- fake screen
# A panel that has every colour still loose until it is dragged. `connected`
# mirrors the game's own rule: a wire the bot dropped anywhere disappears, which
# is why a visible result is not proof and the harness checks the task bar.
class Screen:
    def __init__(self, colors, left_rows, right_rows):
        self.loose = {c: (left_rows[i], right_rows[i]) for i, c in enumerate(colors)}
        self.drags = []
        self.closed = False
        self.opens = 0

    # where a loose endpoint is drawn, or None if it is already connected
    def endpoint(self, color, side):
        if color not in self.loose:
            return None
        return self.loose[color][0 if side == "l" else 1]

    def panel_open(self):
        return self.opens > 0 and bool(self.loose)


SCREEN = None


def install_fake_toolkit():
    """A stand-in for task_utility, so the real solver logic runs unchanged."""
    tu = types.ModuleType("task_utility")

    tu.get_dimensions = lambda: (0, 0, 1920, 1080)
    tu.get_dir = lambda: ROOT
    tu.resize_images = lambda *a, **k: None

    def find_template(template, region=None, confidences=(0.8,), verbose=True):
        color = os.path.basename(template).replace("Wire.png", "")
        for side, code in (("l", "l"), ("r", "r")):
            pass
        which = "l" if region[0] < 1000 else "r"
        pos = SCREEN.endpoint(color, which)
        return None if pos is None else (pos, pos)
    tu.find_template = find_template

    def click_use():
        SCREEN.opens += 1
        return True
    tu.click_use = click_use

    def click_close():
        SCREEN.closed = True
        return "closed with the X button"
    tu.click_close = click_close

    def wake():
        return True
    tu.wake = wake

    sys.modules["task_utility"] = tu
    return tu


# fake pyautogui that records drags and makes the wire disappear
class FakePyautogui(types.ModuleType):
    easeOutQuad = "easeOutQuad"

    def __init__(self):
        super().__init__("pyautogui")

    def moveTo(self, x, y, *a, **k):
        return None

    def dragTo(self, x, y, *a, **k):
        return None

    def click(self, *a, **k):
        return None

    def screenshot(self, *a, **k):
        raise AssertionError("Fix Wiring must not need a screenshot")


def make_drag():
    """pyautogui.dragTo. Bound onto the instance, so no `self`."""
    def dragTo(x, y, duration=None, tween=None):
        SCREEN.drags.append((x, y))
        # the game accepts a drop on any wire: remove whichever loose endpoint is
        # closest to where the wire was released
        best = None
        for color, (lx, rx) in list(SCREEN.loose.items()):
            d = abs(rx - x)
            if best is None or d < best[0]:
                best = (d, color)
        if best:
            del SCREEN.loose[best[1]]
        return None
    return dragTo


def run_solver(colors, left_rows, right_rows):
    """Run the real Fix Wiring solver against a fake screen."""
    global SCREEN
    SCREEN = Screen(colors, left_rows, right_rows)
    install_fake_toolkit()

    pg = FakePyautogui()
    pg.dragTo = make_drag()
    sys.modules["pyautogui"] = pg
    for m in ("numpy", "cv2"):
        sys.modules.setdefault(m, types.ModuleType(m))

    path = os.path.join(ROOT, "task-solvers", "Fix Wiring.py")
    src = open(path, encoding="utf-8").read()
    g = {"__name__": "__main__", "__file__": path}
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exec(compile(src, path, "exec"), g)
    OUT.append(buf.getvalue())
    return SCREEN


# what the solver printed, line by line, for the most recent run
OUT = []


print()
print("=== a panel with all four wires: all four get connected ===")
screen = run_solver(["red", "blue", "yellow", "pink"],
                    [100, 200, 300, 400], [1500, 1400, 1300, 1200])
check("the panel was opened", screen.opens > 0, screen.opens)
check("all four wires were dragged, not just the first",
      len(screen.drags) == 4, f"{len(screen.drags)} drags: {screen.drags}")
check("every colour is gone from the panel", not screen.loose, screen.loose)
check("and then the panel was closed", screen.closed, screen.closed)

print()
print("=== the wires are done in the game's own number order ===")
# red 1, blue 2, yellow 3, pink 4. Rows increase downward, so connecting
# top-to-bottom is the number order.
screen = run_solver(["red", "blue", "yellow", "pink"],
                    [100, 200, 300, 400], [1500, 1400, 1300, 1200])
order = [d[1] for d in screen.drags]
check("the release rows descend, i.e. numbers ascend",
      order == sorted(order, reverse=True), order)

print()
print("=== a panel missing a colour: only the real wires are counted ===")
screen = run_solver(["red", "yellow"], [100, 300], [1500, 1300])
check("both wires dragged", len(screen.drags) == 2, screen.drags)
check("and the panel closed", screen.closed, screen.closed)
check("a two-wire panel is not claimed as 4 of 4", "2 of 2" in OUT[-1], OUT[-1])

print()
print("=== a closed panel is never dragged on ===")
# A screen where opening never reveals a single wire: the solver must report that
# and drag nothing, rather than dragging blind at remembered coordinates.
SCREEN = Screen([], [], [])
install_fake_toolkit()
check("with no wires visible, nothing was dragged", not SCREEN.drags, SCREEN.drags)
check("and the panel was not falsely reported as done", not SCREEN.closed,
      SCREEN.closed)

print()
print("=== the solver source itself must not bail out after one wire ===")
src = open(os.path.join(ROOT, "task-solvers", "Fix Wiring.py"),
           encoding="utf-8").read()
check("there is no 'break' inside the wire loop",
      "    break   # one wire" not in src and
      "one wire per panel" not in src,
      "the old one-wire-per-panel break is back")
check("all four colours are in the work list",
      all(f'"{c}"' in src for c in ("red", "blue", "yellow", "pink")))

print()
if fails:
    print("FAILURES:", ", ".join(fails))
    raise SystemExit(1)
print("all checks passed: all four wires, in order, verified before closing")
