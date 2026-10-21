"""Inspect Sample, driven by the game's own answer.

What the task actually is
-------------------------
A rack of five sample tubes. The panel processes the sample and then one of
them is the odd one out; you pick it.

The old solver found the odd tube by matching a picture of it on the screen
and clicking at a fixed distance below the match, and it was flaky: the first
click after START was often swallowed, and the whole thing depended on where
the template happened to be.

The game knows the answer. It is not a matter of looking:

  * The task keeps a byte array, `NormalPlayerTask.Data`. For this task
    `Data[0]` is a STATE CODE, not a count: 64 means a tube may be picked,
    32 means the processing has finished, 128 means the lower buttons are up.
  * When the processing finishes, SampleMinigame.FixedUpdate picks a random
    tube at random and writes its index into `Data[1]`, and highlights it.
  * SampleMinigame.SelectTube(i) does nothing unless `Data[0]` is 64, and
    then compares `i` with `Data[1]`. So the tube to pick is `Data[1]`, and
    the game refuses a pick made before it is ready.

So the solver does not look for anything. It waits for the game to say the
panel is ready, reads the tube the game picked, and asks the game to select
it - the same public method the tube's own button calls.

The one thing still done with the mouse is the START press, because the
START button is ordinary panel furniture and the game does not expose it as
a method. Its position is the one the 2023 original used, which was verified
in a live game; the click is retried, because the old solver's one known
flaw was that the first click after the panel opens can be swallowed.
"""
import os
import sys
import time

import pyautogui

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(os.getcwd(), "task-solvers"))

import botlink  # noqa: E402
from task_utility import get_dimensions, is_task_done, open_task_panel  # noqa: E402

# The panel's state code that means "a tube may be selected".
READY = 64

# How long to wait for the panel to be ready. The processing animation is
# about a minute in the current build, so this is generous on purpose.
READY_TIMEOUT = 75.0


def _interrupted():
    try:
        return botlink.solver_interrupted()
    except Exception:
        return False


def _start_position(dimensions):
    """Where the START button is, in screen pixels.

    The 2023 original's position, width/1.52 and height/1.16 from the top
    left of the client area. It was confirmed in a live game, so it is the
    one position in this file that is not derived from the game itself -
    which is why the click is retried rather than trusted.
    """
    return (dimensions[0] + round(dimensions[2] / 1.52),
            dimensions[1] + round(dimensions[3] / 1.16))


def solve():
    dimensions = get_dimensions()
    if not dimensions:
        print("Inspect Sample: no game window dimensions")
        return 1

    if not open_task_panel():
        print("Inspect Sample: no panel is open - it would not open, so nothing was pressed")
        return 1

    hot = botlink.read_minigame_hot()
    if not hot:
        print("Inspect Sample: no panel is open, so nothing was pressed")
        return 1
    print(f"Inspect Sample: the panel says {hot.get('task')!r}")

    x, y = _start_position(dimensions)
    deadline = time.time() + READY_TIMEOUT
    start_clicked = False
    next_click = 0.0

    while time.time() < deadline:
        if _interrupted():
            print("Inspect Sample: interrupted")
            return 2
        if is_task_done("Inspect Sample"):
            print("Inspect Sample: the game confirms it done")
            return 0

        hot = botlink.read_minigame_hot()
        if not hot:
            if is_task_done("Inspect Sample"):
                print("Inspect Sample: the game confirms it done")
                return 0
            print("Inspect Sample: the panel closed and the task is not done")
            return 1

        data = hot.get("data") or {}
        state = data.get(0, 0)

        if state == READY:
            anomaly = data.get(1)
            if anomaly is None:
                time.sleep(0.05)
                continue
            print(f"Inspect Sample: the game says tube {anomaly} is the odd one")
            try:
                botlink.minigame_call("SelectTube", anomaly, timeout=3.0)
            except botlink.CommandFailed as exc:
                # The game can refuse the pick, and it does not always refuse
                # for the same reason. So the refusal is retried a couple of
                # times, and the task bar is checked in between: a pick that
                # the game actually carried out and then complained about is
                # still a completed task.
                print(f"Inspect Sample: the game refused the pick "
                      f"({exc.reason}) - trying again")
                for _ in range(3):
                    if is_task_done("Inspect Sample"):
                        print("Inspect Sample: the game confirms it done")
                        return 0
                    time.sleep(1.0)
                    try:
                        botlink.minigame_call("SelectTube", anomaly, timeout=3.0)
                        break
                    except botlink.CommandFailed as exc2:
                        print(f"Inspect Sample: refused again ({exc2.reason})")
                        exc = exc2
                else:
                    if is_task_done("Inspect Sample"):
                        print("Inspect Sample: the game confirms it done")
                        return 0
                    print(f"Inspect Sample: the pick was refused and the task is "
                          f"not done ({exc.reason})")
                    return 1
            # The task completes itself from here; the game closes the panel.
            for _ in range(40):
                if is_task_done("Inspect Sample"):
                    print("Inspect Sample: the game confirms it done")
                    return 0
                time.sleep(0.25)
            print("Inspect Sample: the pick was made but the task is not done")
            return 1

        # Not ready yet. Press START if we have not, and keep pressing it
        # occasionally: the old solver's one known flaw was that the first
        # click after the panel opens is often swallowed.
        now = time.time()
        if not start_clicked or now >= next_click:
            pyautogui.click(x, y)
            if not start_clicked:
                print(f"Inspect Sample: pressed START at ({x},{y})")
                start_clicked = True
                next_click = now + 3.0
            else:
                next_click = now + 5.0
        time.sleep(0.25)

    print(f"Inspect Sample: the panel was still not ready after {READY_TIMEOUT:.0f}s")
    return 1


solve = solve


if __name__ == "__main__":
    sys.exit(solve())
