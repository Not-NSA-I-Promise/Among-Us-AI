"""Calibrate Distributor: the solver plays the dials the game says are right.

The task used to be a pixel solver that built a 2px strip at
window_x + width/1.56 and read the colour off it. That column is the black
middle of each row's bar, so the colour test could never pass and the solver
sat there forever; the rewrite before that cropped the panel and hunted for
blobs, found the game's own HUD, and printed "3/3 done".

It is now driven by the game. SweepMinigame.FixedUpdate works out the live
dial's angle as (int)(SpinRate * timer) degrees and compares it with the
target: the dial is in range when min(rem, 360 - rem) is under 13 degrees.
The plugin publishes that distance, and SweepMinigame.HitButton(i) accepts
the press for the live dial when the same test passes.

So the solver's job is narrow and checkable:

  * press the LIVE dial, and only that one - HitButton ignores any other
  * press it while it is in range, with enough margin for the command to
    reach the game
  * tell a rejected press from an accepted one - an accepted press moves the
    dial on, a rejected one resets the whole task
  * report success only when the game confirms it
"""
import importlib.util as il
import os
import sys
import types

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
PATH = os.path.join(ROOT, "task-solvers", "Calibrate Distributor.py")

fails = []


def check(name, cond, detail=""):
    print(("  PASS " if cond else "  FAIL ") + name + ("" if cond else f" <- {detail}"))
    if not cond:
        fails.append(name)


class CommandFailed(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class FakeBotlink:
    """A fake game that answers the way the real one does.

    `dials` is the list of distances the game reports, in order, one per
    poll. `accept` says whether the game accepts the presses.
    """

    def __init__(self, dials, accept=True, done_after=None, open_panel=True):
        self.dials = list(dials)
        self.accept = accept
        self.done_after = done_after
        self.open_panel = open_panel
        self.reads = 0
        self.calls = []

    def read_minigame_hot(self):
        self.reads += 1
        if not self.open_panel:
            return {}
        if self.dials:
            dist = self.dials.pop(0) if len(self.dials) > 1 else self.dials[0]
        else:
            dist = 999
        return {"task": "CalibrateDistributor", "spinner": 0, "dist": dist,
                "spinrate": 60.0, "step": 0, "maxstep": 1}

    def read_minigame(self):
        return {"open": self.open_panel, "task": "CalibrateDistributor"}

    def solver_interrupted(self):
        return False

    def minigame_call(self, method, *args, **k):
        self.calls.append((method, list(args)))
        if not self.accept:
            raise CommandFailed("fail the game refused")
        return True


def run(dials, accept=True, done_after=None, open_panel=True, task_utility=None):
    fake = FakeBotlink(dials, accept=accept, done_after=done_after,
                       open_panel=open_panel)
    bl = types.ModuleType("botlink")
    bl.read_minigame_hot = fake.read_minigame_hot
    bl.read_minigame = fake.read_minigame
    bl.solver_interrupted = fake.solver_interrupted
    bl.minigame_call = fake.minigame_call
    bl.CommandFailed = CommandFailed
    sys.modules["botlink"] = bl

    tu = types.ModuleType("task_utility")
    tu.get_dimensions = lambda: [0, 0, 1920, 1080]
    # the solver opens the panel itself, and the game says whether it is open
    tu.open_task_panel = lambda *a, **k: open_panel
    state = {"reads": 0}

    def _done(task=None, *a, **k):
        state["reads"] += 1
        if done_after is None:
            return False
        return state["reads"] > done_after
    tu.is_task_done = _done
    tu.is_urgent_task = lambda *a, **k: False
    if task_utility:
        for k, v in task_utility.items():
            setattr(tu, k, v)
    sys.modules["task_utility"] = tu

    spec = il.spec_from_file_location("cd_test", PATH)
    cd = il.module_from_spec(spec)
    spec.loader.exec_module(cd)

    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            rc = cd.solve()
        except SystemExit as exc:
            rc = exc.code
    return rc, fake, buf.getvalue()


print()
print("=== it presses the live dial while it is in range ===")
# The dial comes into range, then leaves. The solver should press once, on
# the way in, and not press again once it is out of range.
rc, fake, out = run([30, 30, 4, 4, 900, 900, 900], done_after=3)
check("it pressed exactly once", len(fake.calls) == 1, fake.calls)
if fake.calls:
    check("and it pressed the live dial", fake.calls[0] == ("HitButton", [0]),
          fake.calls[0])
check("it succeeded once the game confirmed it", rc == 0, f"rc={rc}\n{out}")
check("it says the game confirmed it", "confirms it done" in out, out)

print()
print("=== it does not press while the dial is out of range ===")
rc, fake, out = run([40, 40, 40, 40], done_after=2)
check("it pressed nothing", fake.calls == [], fake.calls)

print()
print("=== it leaves margin for the command to reach the game ===")
# At 60 degrees a second, a dial that is 12.9 degrees out has 0.0017s of
# window left, which is less than the round trip. A solver that pressed the
# instant the dial came into range would miss every time.
rc, fake, out = run([12, 12, 12, 12], done_after=2)
check("it did not press a dial that is nearly out of the window",
      fake.calls == [], fake.calls)

print()
print("=== it refuses when there is no panel ===")
rc, fake, out = run([0], open_panel=False)
check("it refuses", rc != 0, f"rc={rc}")
check("and presses nothing", fake.calls == [], fake.calls)
check("and says why", "no panel is open" in out, out)

print()
print("=== it does not claim success the game has not confirmed ===")
rc, fake, out = run([0, 0, 0, 0], done_after=None)
check("it returns failure when the task is never done", rc == 1, f"rc={rc}")
check("and it never claims the task is done", "confirms it done" not in out, out)

print()
print("=== a rejected press is reported, not hidden ===")
# The game refuses the press: the dial does not move on and the task resets.
rc, fake, out = run([0, 0, 0, 0, 0, 0, 0, 0, 0, 0], accept=False)
check("it says the press was refused", "refused" in out, out)
check("and it does not claim the task is done", "confirms it done" not in out, out)

print()
if fails:
    print("FAILURES:", ", ".join(fails))
    raise SystemExit(1)
print("all checks passed: the solver plays the dials the game says are ready")
