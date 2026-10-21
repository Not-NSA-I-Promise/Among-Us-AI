"""Calibrate Distributor, driven by the game's own dial state.

What the task actually is
-------------------------
Three dials, each with a handle on its rim. The handle sweeps round and the
dial is only correct while it is within 13 degrees of the top. The game
accepts a press on a dial only when that dial is the live one AND its handle
is inside that window; a press at the wrong time is not ignored, it throws
the whole task away - the dials are re-randomised and you start again.

That is not a guess. It is what the game does, read out of the game's own
code:

  * SweepMinigame.FixedUpdate advances `timer` and works out the dial's
    angle as (int)(SpinRate * timer) degrees, then compares it with the
    target:

        int rem  = (int)(SpinRate * timer) % 360;
        int dist = min(rem, 360 - rem);
        if (13.0f > dist) { ...the dial is in range... }

  * SweepMinigame.HitButton(i) does nothing at all unless i == spinnerIdx,
    and it plays the ACCEPT sound and moves on to the next dial only when the
    same 13-degree test passes.

  * The plugin publishes `spinner`, `dist` and `spinrate` for the live dial,
    computed with the game's own arithmetic, so the solver does not have to
    redo it and cannot get the rounding wrong.

How the solver plays it
-----------------------
Poll the hot state, and press the live dial when its distance is small enough
that the press will still land inside the window by the time the game reads
the command. The dial turns at a constant `spinrate` degrees per second, so
the time left in the window is (13 - dist) / spinrate, and that is the
margin to check against.

A press is verified by the game itself: the live dial's index goes up when
the press is accepted. If it does not, the press missed the window and the
task has been reset, so the solver says so rather than claiming success.
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(os.getcwd(), "task-solvers"))

import botlink  # noqa: E402
from task_utility import is_task_done, open_task_panel  # noqa: E402

# The game's own acceptance window, in degrees. SweepMinigame compares the
# dial's distance from its target against this.
TARGET_WINDOW = 13.0

# How long a press may take to reach the game, in seconds. The plugin reads
# the command on its next FixedUpdate, so a couple of frames is the honest
# figure; this is added to the observed latency as a safety margin.
COMMAND_LATENCY = 0.06

# A press that is rejected resets the whole task - new random dials, back to
# the first one - so there is no point trying again for a while.
GIVE_UP_AFTER = 4


def _interrupted():
    try:
        return botlink.solver_interrupted()
    except Exception:
        return False


def _panel_task():
    """The game's own name for the open panel, or ""."""
    try:
        return (botlink.read_minigame() or {}).get("task", "")
    except Exception:
        return ""


def solve():
    if not open_task_panel():
        print("Calibrate Distributor: no panel is open - it would not open, so nothing was pressed")
        return 1
    hot = botlink.read_minigame_hot()
    if not hot:
        print("Calibrate Distributor: no panel is open, so nothing was pressed")
        return 1

    print(f"Calibrate Distributor: the panel says {hot.get('task')!r}, "
          f"live dial {hot.get('spinner')}")

    deadline = time.time() + 90
    misses = 0
    last_spinner = hot.get("spinner")
    presses = 0

    while time.time() < deadline:
        if _interrupted():
            print("Calibrate Distributor: interrupted")
            return 2
        if is_task_done("Calibrate Distributor"):
            print(f"Calibrate Distributor: the game confirms it done "
                  f"({presses} press(es))")
            return 0

        hot = botlink.read_minigame_hot()
        if not hot:
            # the panel closed - either the task finished or it was reset
            if is_task_done("Calibrate Distributor"):
                print(f"Calibrate Distributor: the game confirms it done "
                      f"({presses} press(es))")
                return 0
            print("Calibrate Distributor: the panel closed and the task is "
                  "not done")
            return 1

        spinner = hot.get("spinner")
        dist = hot.get("dist")
        rate = hot.get("spinrate")
        if spinner is None or dist is None:
            time.sleep(0.02)
            continue

        if spinner != last_spinner:
            print(f"Calibrate Distributor: dial {spinner} accepted")
            last_spinner = spinner
            misses = 0

        # How long the dial stays inside the window from here.
        rate = rate or 0.0
        if rate > 0:
            seconds_left = max(0.0, (TARGET_WINDOW - dist) / rate)
        else:
            seconds_left = 0.0
        if seconds_left < COMMAND_LATENCY:
            time.sleep(0.005)
            continue

        try:
            botlink.minigame_call("HitButton", spinner, timeout=2.0)
        except botlink.CommandFailed as exc:
            print(f"Calibrate Distributor: the game refused the press ({exc.reason})")
            return 1
        presses += 1
        time.sleep(0.05)

        after = botlink.read_minigame_hot()
        new_spinner = after.get("spinner") if after else None
        if new_spinner == spinner:
            # The dial did not move on, so the press was rejected: the game
            # reset the task. Say so instead of pretending.
            misses += 1
            print(f"Calibrate Distributor: the press on dial {spinner} was "
                  f"rejected (the dial did not advance) - the task resets on "
                  f"a bad press")
            if misses >= GIVE_UP_AFTER:
                return 1
            last_spinner = None

    print("Calibrate Distributor: gave up after 90s")
    return 1


solve = solve


if __name__ == "__main__":
    sys.exit(solve())
