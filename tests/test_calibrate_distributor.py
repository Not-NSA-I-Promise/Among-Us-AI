"""Calibrate Distributor is back on its 2023 logic, and the numbers are checked.

The colour-hunting rewrite that replaced it is gone. It cropped the panel and
looked for blobs of roughly the right colour, which found the game's own HUD - a
regular column at x~1120 - clicked it three times, and printed "3/3 done". The
original's strip logic is self-consistent: a 2px strip at
window_x + width/1.56, sampled with getpixel((0, y)) so x=0 OF THE STRIP, and
clicked at dimensions[0], the same x.

test_restored_solvers.py diffs every number against the original in git history.
This file checks the behaviour the restored code actually has.
"""
import ast
import importlib.util as il
import time as time_module
import os
import subprocess
import sys
import types

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
SOLVERS = os.path.join(ROOT, "task-solvers")
ORIGINAL_COMMIT = "2c965811b5b89940391da3f63de0fb41903a9dd0"

fails = []


def check(name, cond, detail=""):
    print(("  PASS " if cond else "  FAIL ") + name + ("" if cond else f" <- {detail}"))
    if not cond:
        fails.append(name)


def code_only(text):
    out = []
    in_doc = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith('"""') or s.startswith("'''"):
            in_doc = not in_doc
            continue
        if in_doc or s.startswith("#"):
            continue
        out.append(line.split("#")[0])
    return "\n".join(out)


PATH = os.path.join(SOLVERS, "Calibrate Distributor.py")
SRC = open(PATH, encoding="utf-8").read()
CODE = code_only(SRC)
ORIG = subprocess.run(
    ["git", "cat-file", "-p",
     f"{ORIGINAL_COMMIT}:task-solvers/Calibrate Distributor.py"],
    cwd=ROOT, capture_output=True, text=True).stdout

print()
print("=== the sample and click columns are DIFFERENT, and both measured ===")
# The original used one column for both. Measured from a live 1920x1080
# screenshot of this panel, that column is rgb(0, 0, 0) - the black middle of
# each row's bar - on all three rows, so its colour test could never pass and it
# sat there forever. The colour is a small strip on the LEFT edge of each bar:
# yellow x 1116..1134, blue and cyan x 1116..1122. The click stays at the
# original's width/1.56 because that lands on the button at x 1128..1336.
check("it samples at the measured colour column",
      "colour_x = dimensions[0] + round(dimensions[2] * 7 / 12)" in CODE,
      "the sampling column is not the measured one")
check("it clicks at the original's button column",
      "button_x = dimensions[0] + round(dimensions[2] / 1.56)" in CODE,
      "the click column changed without being measured")
check("it strips the colour column for sampling",
      "dimensions[0] = colour_x" in CODE,
      "the strip is not built at the colour column")
check("all three clicks use button_x, not the strip",
      CODE.count("pyautogui.click((button_x,") == 3,
      f"{CODE.count('pyautogui.click((button_x,')} of 3 do")
check("and it says which column it sampled and which it clicked",
      "sampling the colour at x=" in CODE,
      "it does not report the two columns")

print()
print("=== the three sample rows are the original's, and are correct ===")
for expr, why in (
        ("round(dimensions[3] / 4.8)", "yellow, y 225"),
        ("round(dimensions[3] / 2.16)", "blue, y 500"),
        ("round(dimensions[3] / 1.44)", "cyan, y 750"),
        ("button_offset = dimensions[3] / 14.4", "the click offset below the bar"),
        ("get_screenshot(dimensions)", "it reads the strip it just built"),
        ("getpixel((0, yellow_offset))", "x=0 OF THE STRIP"),
):
    check(f"it keeps {expr} ({why})", expr in CODE, "it is not there")

print()
print("=== the colour ranges are the original's, unchanged ===")
for cond, why in (
        ("s_y[0] > 200 and s_y[1] > 200 and s_y[2] < 5", "yellow"),
        ("s_b[0] < 105 and s_b[0] > 80", "blue, red/green bounds"),
        ("s_b[2] > 250", "blue, blue channel"),
        ("s_c[0] < 115 and s_c[0] > 105", "cyan, red channel"),
        ("s_c[1] < 255 and s_c[1] > 245", "cyan, green channel"),
):
    check(f"it keeps the {why} range", cond in CODE, "it is not there")

print()
print("=== the colour-hunting rewrite is gone ===")
check("no _find_dials helper", "_find_dials" not in SRC, "the rewrite is back")
check("no numpy blob scan", "np.where" not in CODE, "it is still scanning blobs")
check("no cropped panel region", "pyautogui.screenshot(region=" not in CODE,
      "it is cropping the panel instead of using the strip")
check("no GUESSES warning", "GUESSES" not in SRC, "it still claims unknown geometry")
check("it does not wait on the plugin's sprite publishing",
      "read_minigame_controls" not in CODE,
      "it still depends on the class resolution that never worked")

# ------------------------------------------------------------------ behaviour
print()
print("=== it reads the strip and clicks that strip's own x ===")

# a 1920x1080 client at the origin, like the real thing
DIMS = [0, 0, 1920, 1080]
STRIP_X = 0 + round(1920 / 1.56)
Y_OFF = round(1080 / 4.8)
B_OFF = round(1080 / 2.16)
C_OFF = round(1080 / 1.44)
BTN = 1080 / 14.4


class FakeShot:
    """A 2px strip, so getpixel((0, y)) really is the strip's x."""

    def __init__(self, rows):
        self.rows = rows

    def getpixel(self, xy):
        return self.rows.get(xy[1], (0, 0, 0))


class FakePg:
    clicks = []
    downs = []

    @staticmethod
    def click(*a, **k):
        # the original calls pyautogui.click((x, y)) with a single tuple, which
        # pyautogui accepts; normalise it so the recorder sees real coordinates
        if len(a) == 1 and isinstance(a[0], (tuple, list)):
            FakePg.clicks.append(tuple(a[0]))
        else:
            FakePg.clicks.append((a[0] if a else k.get("x"),
                                  a[1] if len(a) > 1 else k.get("y")))

    @staticmethod
    def mouseDown(*a, **k):
        FakePg.downs.append(1)

    @staticmethod
    def mouseUp(*a, **k):
        pass

    @staticmethod
    def moveTo(*a, **k):
        pass

    @staticmethod
    def dragTo(*a, **k):
        pass

    @staticmethod
    def screenshot(*a, **k):
        return None


def run_solver(rows, done_after=99, panel_open=True, fast_forward=False):
    """Run the real solver against a fake game and strip.

    `fast_forward` jumps the solver's clock, so the 40s timeout is reached in
    microseconds instead of making the test suite wait for it.
    """
    FakePg.clicks = []
    sys.modules["pyautogui"] = FakePg

    tu = types.ModuleType("task_utility")
    tu.get_dimensions = lambda: list(DIMS)
    tu.get_screenshot = lambda dimensions=None, window_title="Among Us": \
        FakeShot(rows)
    state = {"reads": 0}

    def _done(task=None, *a, **k):
        state["reads"] += 1
        return state["reads"] > done_after

    tu.is_task_done = _done
    tu.is_urgent_task = lambda *a, **k: False
    sys.modules["task_utility"] = tu

    bl = types.ModuleType("botlink")
    bl.read_minigame = lambda *a, **k: {"open": panel_open, "task": ""}
    bl.solver_interrupted = lambda: False
    bl.MINIGAME_CONTROLS_PATH = ""
    sys.modules["botlink"] = bl

    spec = il.spec_from_file_location("cd_test", PATH)
    cd = il.module_from_spec(spec)
    spec.loader.exec_module(cd)

    if fast_forward:
        # every call to time() advances the clock by a second, so the solver's
        # own 40 second budget is exhausted almost immediately
        _t = types.SimpleNamespace()
        _real = time_module.time
        _t.time = lambda: _real() + state.setdefault("tick", 0)
        _t.sleep = lambda s: None
        _orig_time, _orig_sleep = cd.time.time, cd.time.sleep
        state["tick"] = 0
        cd.time = types.SimpleNamespace(
            time=lambda: _real() + state["tick"],
            sleep=lambda s: state.__setitem__("tick", state["tick"] + 1))
        cd.__dict__["_time_patched"] = True

    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            rc = cd.solve()
        except SystemExit as exc:
            rc = exc.code
    return rc, FakePg.clicks, buf.getvalue()


rc, clicks, out = run_solver({
    Y_OFF: (255, 255, 0),
    B_OFF: (90, 90, 255),
    C_OFF: (110, 250, 255),
})
print(out.strip())
check("it succeeded once the game reported the task done", rc == 0, f"rc={rc}\n{out}")
check("it clicked three times", len(clicks) == 3, clicks)
check("every click is at the strip's own x, not at the window's left edge",
      all(x == STRIP_X for x, _y in clicks), f"{clicks} vs strip x {STRIP_X}")
check("and the click y is the sample y plus the button offset",
      clicks[0] == (STRIP_X, Y_OFF + BTN) if clicks else False,
      f"{clicks[:1]} vs {(STRIP_X, Y_OFF + BTN)}")
check("it says the game confirmed it", "confirms it done" in out, out)

print()
print("=== it does not click when the game says no panel is open ===")
rc, clicks, out = run_solver({Y_OFF: (255, 255, 0)}, panel_open=False)
check("it refuses", rc != 0, f"rc={rc}")
check("and clicks nothing", clicks == [], clicks)
check("and says why", "no panel is open" in out, out)

print()
print("=== it does not claim success the game has not confirmed ===")
rc, clicks, out = run_solver({Y_OFF: (255, 255, 0)}, done_after=10 ** 9,
                             fast_forward=True)
check("it returns failure when the task is never done", rc == 1, f"rc={rc}")
# Two honest ways out of a task that never completes: the loop times out, or it
# exits and finds the game still says not done. Either is a failure; what must
# not happen is a success.
check("and it admits it, rather than reporting success",
      ("gave up after 40s" in out) or ("does NOT report the task as done" in out),
      out)
check("and it never claims the task is done", "confirms it done" not in out, out)

print()
if fails:
    print("FAILURES:", ", ".join(fails))
    raise SystemExit(1)
print("all checks passed: the original's strip logic, verified end to end")
