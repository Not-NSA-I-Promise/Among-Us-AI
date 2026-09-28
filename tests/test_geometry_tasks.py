"""Start Reactor and Empty Trash must be driven by the GAME, not by pixel guesses.

The old solvers were the last two tasks still guessing. Start Reactor laid a 3x3
grid of hardcoded pixel offsets and looked for one hardcoded RGB triple to decide
a pad was lit. Empty Trash dragged between two hardcoded points for two seconds
and assumed that was the lever. Neither checked anything afterwards.

Both are now driven by what the game publishes:

    public class SimonSaysGame : Minigame
        public SpriteRenderer[] Buttons;    // pad screen positions
        public SpriteRenderer[] LeftLights; // light colours
    public class EmptyGarbageMinigame : Minigame
        public Collider2D Handle;           // lever screen position
        public FloatRange HandleRange;      // its travel
        private bool finished;

These tests drive the real solvers against a fake game and assert they use the
published positions, and that they refuse to click at all when the game has not
said where anything is.
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
    if not cond:
        print("  FAIL", name, "<-", detail)
        fails.append(name)


class FakeGame:
    """Stands in for the files the plugin writes."""

    def __init__(self, controls, minigame_open=True):
        self.controls = controls
        self.open = minigame_open
        self.clicks = []
        self.drags = []

    def read_minigame_controls(self, retries=4):
        return dict(self.controls) if self.controls else {}

    def read_minigame(self, retries=4):
        return {"open": self.open, "task": self.controls.get("task", "") if self.controls else ""}

    def minigame_controls_ready(self, timeout=0, poll=0):
        c = self.read_minigame_controls()
        if c and c.get("type") in ("simon", "garbage"):
            return c
        return None

    def solver_interrupted(self):
        return False


class FakePyautogui(types.ModuleType):
    def __init__(self, game):
        super().__init__("pyautogui")
        self.game = game
        self.down = False

    def click(self, x=None, y=None, *a, **k):
        self.game.clicks.append((x, y))

    def moveTo(self, x=None, y=None, *a, **k):
        if self.down:
            self.game.drags.append((x, y))
            # the lever follows the mouse while the button is held
            c = dict(self.game.controls) if self.game.controls else {}
            if "handle" in c:
                c["handle"] = (x, y)
            self.game.controls = c
        return None

    def mouseDown(self, *a, **k):
        self.down = True

    def mouseUp(self, *a, **k):
        self.down = False
        self.game.released = True

    def dragTo(self, x, y, *a, **k):
        self.game.drags.append((x, y))
        return None


def run(solver_name, game):
    """Run a real solver against the fake game."""
    pg = FakePyautogui(game)
    sys.modules["pyautogui"] = pg
    import botlink
    for name in ("read_minigame_controls", "read_minigame",
                 "minigame_controls_ready", "solver_interrupted"):
        setattr(botlink, name, getattr(game, name))
    path = os.path.join(ROOT, "task-solvers", solver_name + ".py")
    src = open(path, encoding="utf-8").read()
    g = {"__name__": "__solver__", "__file__": path}
    import io
    import contextlib
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            exec(compile(src, path, "exec"), g)
            rc = g["solve"]()
    except SystemExit as exc:
        rc = exc.code
    return rc, buf.getvalue()


# ---------------------------------------------------------------- Start Reactor
print()
print("=== Start Reactor reads the sequence from the game's light colours ===")
IDLE = (60, 60, 60)
CONTROLS = {
    "type": "simon",
    "task": "StartReactor",
    "buttons": {0: (400, 400), 1: (700, 400), 2: (400, 700), 3: (700, 700)},
    "lights": {0: (100, 400), 1: (100, 400), 2: (100, 400), 3: (100, 400)},
    "lightcols": {0: IDLE, 1: IDLE, 2: IDLE, 3: IDLE},
    "buttoncols": {0: IDLE, 1: IDLE, 2: IDLE, 3: IDLE},
}

# a game that plays a 3-step sequence, then waits
SEQUENCE = [2, 0, 3]


class SimonGame(FakeGame):
    """A game that publishes the sequence, then hands the pads over."""

    def __init__(self):
        super().__init__(dict(CONTROLS))
        self.polls = 0
        self.seq = list(SEQUENCE)

    def read_minigame_controls(self, retries=4):
        c = super().read_minigame_controls(retries)
        # the queue only drains once the sequence has been played
        if self.polls > 3:
            c["seq"] = []
        else:
            c["seq"] = list(self.seq)
        self.polls += 1
        return c

    def read_minigame(self, retries=4):
        clicked = getattr(self, "_clicked", 0)
        return {"open": clicked < len(SEQUENCE), "task": "StartReactor"}


game = SimonGame()

orig_click = FakePyautogui.click


def counting_click(self, x=None, y=None, *a, **k):
    self.game.clicks.append((x, y))
    self.game._clicked = len(self.game.clicks)


FakePyautogui.click = counting_click
rc, out = run("Start Reactor", game)
FakePyautogui.click = orig_click

print(out.strip())
check("it did not fail", rc == 0, f"rc={rc}\n{out}")
check("it clicked the pads the GAME reported, in the order it read",
      game.clicks == [CONTROLS["buttons"][i] for i in SEQUENCE],
      f"{game.clicks} vs {[CONTROLS['buttons'][i] for i in SEQUENCE]}")
check("and it did not click the light positions", all(
    c not in [(100, 400)] for c in game.clicks), game.clicks)

print()
print("=== Start Reactor refuses to click when the game says nothing ===")
silent = FakeGame({})
rc, out = run("Start Reactor", silent)
print(out.strip())
check("it refuses rather than guessing pixels", rc != 0, f"rc={rc}")
check("and it clicked nothing", silent.clicks == [], silent.clicks)
check("and it says why", "never reported the pad positions" in out, out)

print()
print("=== Start Reactor must not sample the screen at all ===")
src = open(os.path.join(ROOT, "task-solvers", "Start Reactor.py"),
           encoding="utf-8").read()
check("no pixel() sampling", "pyautogui.pixel" not in src, "it samples the screen")
check("no hardcoded pixel grid",
      "x_offset" not in src and "y_offset" not in src,
      "the old 3x3 guessed grid is back")
check("no persisted click list", "reactor_list" not in src,
      "it still replays from the JSON file")
check("the sequence comes from the game's own queue",
      'c.get("seq")' in src or '.get("seq")' in src,
      "it does not use the sequence the game publishes")
check("and it waits for the game to hand the pads over",
      "handed the pads over" in src,
      "it does not wait for its turn")

# ---------------------------------------------------------------- Empty Trash
print()
print("=== Empty Trash drags the lever the GAME reported ===")
GARBAGE = {
    "type": "garbage",
    "task": "EmptyGarbage",
    "handle": (900, 500),
    "has_handle": True,
    "handlelow": -1.0,
    "handlehigh": 1.0,
    "finished": True,
    "lever": 1.0,
}


class GarbageGame(FakeGame):
    """The handle follows the mouse while the button is held, and stops at the
    end of its travel - which is the behaviour the new drag is built around."""

    def __init__(self):
        super().__init__(dict(GARBAGE))
        self.released = False

    def read_minigame(self, retries=4):
        # the panel closes once the lever has been released at the end
        return {"open": not self.released, "task": "EmptyGarbage"}


g2 = GarbageGame()
rc, out = run("Empty Garbage", g2)
print(out.strip())
check("it completed", rc == 0, f"rc={rc}\n{out}")
check("it pressed the mouse down on the handle the game published",
      g2.drags and g2.drags[0][0] == GARBAGE["handle"][0], g2.drags)
check("it dragged downward, the direction a lever is pulled",
      len(g2.drags) > 1 and g2.drags[-1][1] > GARBAGE["handle"][1], g2.drags)
check("it released the mouse", g2.released, "never released")
check("and it did NOT let go early: it kept dragging until the handle stopped",
      len(g2.drags) >= 4, f"only {len(g2.drags)} drag steps")

print()
print("=== Empty Trash waits instead of dragging when there is no lever ===")
class NoHandleGame(FakeGame):
    def __init__(self):
        c = dict(GARBAGE)
        c["has_handle"] = False
        c.pop("handle")
        super().__init__(c)
        self.waits = 0

    def read_minigame(self, retries=4):
        self.waits += 1
        # closes after a few polls, as the real Storage stage does on its own
        return {"open": self.waits < 5, "task": "EmptyGarbage"}


g3 = NoHandleGame()
rc, out = run("Empty Garbage", g3)
print(out.strip())
check("it waits for the storage stage instead of dragging", rc == 0, f"rc={rc}\n{out}")
check("and it dragged nothing", g3.drags == [], g3.drags)
check("and it says the trash falls by itself", "no lever" in out, out)

print()
print("=== Empty Trash refuses when the game says nothing ===")
silent2 = FakeGame({})
rc, out = run("Empty Garbage", silent2)
print(out.strip())
check("it refuses rather than dragging a guessed point", rc != 0, f"rc={rc}")
check("and it dragged nothing", silent2.drags == [], silent2.drags)

print()
print("=== neither solver may use hardcoded pixel offsets any more ===")
for name in ("Start Reactor", "Empty Garbage", "Empty Chute"):
    s = open(os.path.join(ROOT, "task-solvers", name + ".py"),
             encoding="utf-8").read()
    check(f"{name} has no dimensions[]-derived click points",
          "dimensions[" not in s,
          "it still computes a click point from the window size")
    check(f"{name} does not call click_use() itself",
          "click_use(" not in s,
          "the harness opens the panel; a second USE would close it")

print()
if fails:
    print("FAILURES:", ", ".join(fails))
    raise SystemExit(1)
print("all checks passed: both tasks are driven by the game, not by pixels")
