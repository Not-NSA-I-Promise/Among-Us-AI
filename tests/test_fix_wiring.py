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
    def __init__(self, colors, left_rows, right_rows, best_confidence=0.738,
                 bright_when_open=True, open_on_first_click=True):
        self.loose = {c: (left_rows[i], right_rows[i]) for i, c in enumerate(colors)}
        self.drags = []
        self.clicks = 0
        self.closed = False
        self.opens = 0
        self.open_state = False
        # the best match the templates in this repo can actually achieve
        self.best_confidence = best_confidence
        self.bright_when_open = bright_when_open
        # a panel that is already up before the solver runs, and one that
        # toggles on each click, like the real USE button does
        self.open_on_first_click = open_on_first_click

    def click_use(self):
        """The game's USE button TOGGLES the minigame once a panel is up."""
        self.clicks += 1
        if self.open_state:
            self.open_state = False
            self.loose = dict(self._all_colors())
        else:
            self.open_state = True
            self.opens += 1

    def _all_colors(self):
        return self._original_loose.items()

    def panel_open(self):
        if not self.open_state:
            return False
        if self.bright_when_open:
            return True
        # brightness is useless here: fall back to the wires themselves
        return any(endpoint for _, endpoint in self.loose.values())

    def endpoint(self, color, side):
        if not self.open_state:
            return None
        if color not in self.loose:
            return None
        return self.loose[color][0 if side == "l" else 1]


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
        if pos is None:
            return None
        # REALITY: the wire templates in this repo do not match above about 0.74.
        # The original code even discarded a 0.738 match. So a template only
        # matches if the ladder actually reaches that low - and if some code
        # raises the floor above it, every lookup returns None and the solver
        # does nothing at all.
        if SCREEN.best_confidence is not None:
            if not any(c <= SCREEN.best_confidence for c in confidences):
                return None
        return (pos, pos)
    tu.find_template = find_template

    def click_use():
        SCREEN.click_use()
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


# The solver asks for a screenshot of the panel region to decide open vs closed.
def install_screenshot():
    class FakeShot(list):
        def __init__(self, bright):
            super().__init__([bright] * 4)

    pg = sys.modules.get("pyautogui")

    def screenshot(region=None, *a, **k):
        # a closed panel is a dark room, an open one a pale box
        bright = 200 if SCREEN.panel_open() else 10
        return FakeShot(bright)

    pg.screenshot = screenshot


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


def run_solver(colors, left_rows, right_rows, best_confidence=0.738,
               bright_when_open=True, start_open=False):
    """Run the real Fix Wiring solver against a fake screen."""
    global SCREEN
    SCREEN = Screen(colors, left_rows, right_rows, best_confidence,
                    bright_when_open)
    SCREEN._original_loose = dict(SCREEN.loose)
    if start_open:
        SCREEN.open_state = True
    install_fake_toolkit()

    pg = FakePyautogui()
    pg.dragTo = make_drag()
    sys.modules["pyautogui"] = pg
    for m in ("numpy", "cv2"):
        sys.modules.setdefault(m, types.ModuleType(m))
    install_screenshot()

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
print("=== USE is a TOGGLE: the panel must only ever be clicked while closed ===")
# This is what a live run did, and it was confirmed by hand. A duplicated
# open_panel() call meant the first opened the panel and the second clicked it
# shut, and every drag after that was into empty space. The panel appeared to
# open and close while nothing was connected.
screen = run_solver(["red", "blue", "yellow", "pink"],
                    [100, 200, 300, 400], [1500, 1400, 1300, 1200])
check("USE is clicked exactly once, not once to open and once to close",
      screen.clicks == 1, f"{screen.clicks} clicks")
check("and the panel is left open for the drags",
      screen.open_state, "the panel was closed again")
check("so the wires really were connected", not screen.loose, screen.loose)
check("all four were dragged", len(screen.drags) == 4, screen.drags)

print()
print("=== a panel that is ALREADY open is never clicked ===")
# Even a stray second call to open_panel() must be a no-op, not a click that
# closes the panel.
screen = run_solver(["red", "blue", "yellow", "pink"],
                    [100, 200, 300, 400], [1500, 1400, 1300, 1200],
                    start_open=True)
check("an already-open panel is not clicked at all",
      screen.clicks == 0, f"{screen.clicks} clicks")
check("and is still wired", len(screen.drags) == 4, screen.drags)

print()
print("=== open_panel() must be called exactly once in the source ===")
src = open(os.path.join(ROOT, "task-solvers", "Fix Wiring.py"),
           encoding="utf-8").read()
check("there is a single call to open_panel()",
      src.count("if not open_panel():") == 1,
      f"{src.count('if not open_panel():')} calls")
check("and it checks the panel before it clicks USE",
      "if wires_visible():" in src and
      src.index("if wires_visible():") < src.index("click_use()", src.index("def open_panel")),
      "the click is not guarded by a state check")

print()
print("=== a solver may click USE AT MOST ONCE ===")
# USE toggles a minigame, so a second click closes the panel. This has broken
# Fix Wiring three ways: a duplicated open_panel() call, a click-then-check loop,
# and a brightness check that reported a closed panel as open so the solver never
# clicked at all. The rule is now "at most one click, then wait".
for solver in ("Fix Wiring", "Inspect Sample", "Fix Communications"):
    text = open(os.path.join(ROOT, "task-solvers", solver + ".py"),
                encoding="utf-8").read()
    start = text.find("def open_panel")
    body = text[start:]
    nxt = body.find("\ndef ", 5)
    if nxt != -1:
        body = body[:nxt]
    clicks = body.count("click_use()")
    check(f"{solver} clicks USE at most once", clicks <= 1, f"{clicks} clicks")
    check(f"{solver} does not use a blind brightness threshold to decide",
          "mean()" not in body,
          "brightness as an open/closed signal is not reliable here")
    check(f"{solver} opens its panel exactly once",
          text.count("if not open_panel():") == 1,
          f"{text.count('if not open_panel():')} calls")

print()
print("=== templates only match at ~0.74, so the ladder must reach that low ===")
# This is the regression that broke a live run. The "is this wire still loose?"
# check was briefly raised to a 0.9/0.85/0.8 floor, which is above what these
# templates can ever reach. Every lookup then returned None, so every wire was
# declared already-connected, no drag ever happened, and the panel opened and
# closed having done nothing.
screen = run_solver(["red", "blue", "yellow", "pink"],
                    [100, 200, 300, 400], [1500, 1400, 1300, 1200],
                    best_confidence=0.738)
check("a 0.738-matching template is still found",
      len(screen.drags) == 4, f"{len(screen.drags)} drags: {screen.drags}")
check("so the panel is actually wired, not just opened and closed",
      not screen.loose, screen.loose)

# and a stricter floor would silently disable the whole task
check("a 0.9 floor finds nothing, which is why it must not be used",
      not any(c <= 0.738 for c in (0.9, 0.85, 0.8)), "ladder is reachable")

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
