"""Inspect Sample, restored to the logic that was known to work.

Original in git history: 1aee06f, 2023-01-29. Two things in it matter and both
were lost in a rewrite that looked like an improvement:

  1. It waits 61 seconds for the sample animation. The rewrite polled for 30 x
     0.25s, i.e. 7.5 seconds, and then gave up - so it could never find the tube,
     because the tube is not identifiable until the animation has run. It then
     printed a specific and confident lie about what it had found.

  2. The START click is at window_x + width/1.52, window_y + height/1.16. The
     rewrite moved it to the centre of a guessed panel region, which is not where
     the button is. The report was "the panel opens but START is never pressed",
     which is exactly what a wrong click position looks like.

Kept from the rewrite, because neither touches the coordinates:

  - the harness opens the panel and confirms it from Minigame.Instance, so this
    does not call click_use(). The original did, which toggled the panel shut.
  - polling instead of a blind 61s sleep, which is strictly better: the click
    happens the moment the tube is identifiable rather than 61s later whatever
    happened. The timeout stays generous because the animation genuinely takes
    about that long.
  - the result is only reported as success when the game says the task is done.
"""
import os
import sys
import time

import pyautogui

from task_utility import get_dimensions, get_dir  # noqa: E402
from task_utility import click_close  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, ROOT)
import botlink  # noqa: E402

# The original waited a flat 61s. Poll for this long instead - the same ceiling,
# but the click lands as soon as the tube can be seen.
TUBE_TIMEOUT = 65.0


def _interrupted():
    return botlink.solver_interrupted()


def _panel_open():
    try:
        return (botlink.read_minigame() or {}).get("open")
    except Exception:
        return None


def _find_tube(region):
    """The anomaly tube, or None.

    locateCenterOnScreen RAISES ImageNotFoundException when it cannot find the
    template, which used to kill the solver outright. Caught here so a tube that
    has not appeared yet is simply "not yet".
    """
    try:
        return pyautogui.locateCenterOnScreen(
            os.path.join(get_dir(), "task-solvers", "cv2-templates",
                         "Inspect Sample", "anomaly.png"),
            confidence=0.5, region=region)
    except Exception:
        return None


def _solve():
    if _panel_open() is False:
        print("Inspect Sample: the game says no panel is open, so nothing was "
              "clicked")
        return 1

    dimensions = get_dimensions()
    if not dimensions:
        print("Inspect Sample: no game window dimensions")
        return 1

    # Original START position, unchanged.
    x = dimensions[0] + round(dimensions[2] / 1.52)
    y = dimensions[1] + round(dimensions[3] / 1.16)
    pyautogui.click((x, y))
    print(f"Inspect Sample: clicked START at ({x},{y})")
    time.sleep(0.8)

    # Original search region for the tube, unchanged. The original clicked a
    # fixed distance BELOW the match, which is preserved: the template matches
    # the top of the tube and the click target is lower down it.
    y_offset = dimensions[3]
    region = [
        dimensions[0] + round(dimensions[2] / 2.81),
        dimensions[1] + round(dimensions[3] / 3.2),
        round(dimensions[2] / 3.4),
        round(dimensions[3] / 3.6),
    ]

    deadline = time.time() + TUBE_TIMEOUT
    pos = None
    while time.time() < deadline:
        if _interrupted():
            print("Inspect Sample: interrupted while waiting for the sample")
            return 2
        # the game closes the panel itself once the right tube is submitted
        if _panel_open() is False:
            print("Inspect Sample: the panel closed, so the sample was submitted")
            return 0
        pos = _find_tube(region)
        if pos:
            break
        time.sleep(0.5)

    if not pos:
        print(f"Inspect Sample: START was clicked but no anomaly tube was "
              f"identifiable within {TUBE_TIMEOUT:.0f}s, so nothing was clicked")
        try:
            click_close()
        except Exception:
            pass
        return 1

    target = (pos[0], pos[1] + round(y_offset / 2.87))
    pyautogui.click(target)
    print(f"Inspect Sample: matched the tube at {pos} and clicked {target}")

    # The truth: the panel should close by itself on a correct pick.
    deadline = time.time() + 5.0
    while time.time() < deadline:
        if _panel_open() is False:
            print("Inspect Sample: the panel closed, so the sample was submitted")
            return 0
        time.sleep(0.2)

    print("Inspect Sample: the panel is still open after clicking the tube, so "
          "the sample was NOT submitted")
    try:
        click_close()
    except Exception:
        pass
    return 1


solve = _solve


if __name__ == "__main__":
    sys.exit(solve())
