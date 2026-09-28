"""Calibrate Distributor.

The panel has a dial per colour and a button. The old solver took a screenshot,
decided what to do, and then clicked - and because the dials are ANIMATING, the
dial it had just read had already rotated by the time the click landed. So it
clicked the wrong place, the dial it had read was now somewhere else, and it sat
in a loop on the first dial forever.

The fix is about timing and not being stale:

  - one fresh screenshot per decision, used immediately;
  - the click happens in the same breath as the read that justified it, with no
    other work in between, so the dial has had as little time as possible to move;
  - after a click, WAIT for the dial to finish rotating before deciding anything
    again, instead of immediately re-reading a panel that is mid-animation;
  - a dial that has been clicked is never clicked again;
  - a short sleep when there is nothing to do, so it is not spinning a core.

This is still pixel-based, because the panel's real geometry is not available yet:
minigameControls.txt reports `type other` with no class name and no sprite
positions for this task, which means the plugin build that publishes them has not
been loaded. When it has, the class name and every sprite's screen position will
be in that file and this solver can be written against the real thing instead.
Until then this version at least stops losing the race.
"""
import os
import sys
import time

import pyautogui

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "task-solvers"))

import botlink  # noqa: E402
from task_utility import get_dimensions, is_task_done, is_urgent_task  # noqa: E402


def _interrupted():
    return botlink.solver_interrupted()


def _dump_geometry(why):
    """Copy the panel geometry and a screenshot out, so this can be written
    properly instead of guessed at again."""
    try:
        import shutil
        src = os.path.join(os.path.dirname(botlink.MINIGAME_CONTROLS_PATH),
                           "minigameControls.txt")
        dst = os.path.join(ROOT, f"calibrate_distributor_controls_{why}.txt")
        shutil.copyfile(src, dst)
        print(f"Calibrate Distributor: panel geometry copied to {dst}")
    except Exception as exc:
        print(f"Calibrate Distributor: could not copy the panel geometry ({exc})")
    try:
        pyautogui.screenshot().save(
            os.path.join(ROOT, f"calibrate_distributor_{why}.png"))
        print(f"Calibrate Distributor: screenshot saved for {why}")
    except Exception as exc:
        print(f"Calibrate Distributor: could not save a screenshot ({exc})")


def _panel_region():
    """The middle of the window, which is where a task panel is drawn.

    Returns (left, top, width, height) in SCREEN coordinates, so a pixel found in
    the screenshot and the click sent to it are the same coordinate. That matters:
    task_utility.get_screenshot(dimensions) ignores the region it is given and
    always grabs the whole client area, so the old solver sampled x=0 of the
    window while clicking at about x=window/1.56. It was reading one place and
    clicking another, which is why the colour test never matched a dial.
    """
    dims = get_dimensions()
    if not dims:
        return None
    x, y, w, h = dims[0], dims[1], dims[2], dims[3]
    left = x + round(w * 0.25)
    top = y + round(h * 0.15)
    width = round(w * 0.50)
    height = round(h * 0.70)
    return left, top, width, height


# Each dial is identified by the colour of its own light. These are the values the
# previous solver used, kept because they are the only part of it that was ever
# measured rather than invented - but they are now used to FIND the dial, rather
# than to test a pixel at a hardcoded offset that was never where the dial was.
#
# These are element-wise, not `and`: the predicates run over whole numpy arrays of
# the cropped panel, and `and` would raise "truth value of an array is ambiguous".
DIALS = [
    ("yellow", lambda r, g, b: (r > 200) & (g > 200) & (b < 5)),
    ("blue", lambda r, g, b: (r > 80) & (r < 105) & (g > 80) & (g < 105) & (b > 250)),
    ("cyan", lambda r, g, b: (r > 105) & (r < 115) & (g > 245) & (g < 255) & (b > 250)),
]


def _find_dials(left, top, width, height):
    """Find each dial by its colour, and return screen positions.

    Returns {name: (x, y)} in SCREEN coordinates, using the centre of the cluster
    of matching pixels.
    """
    import numpy as np
    shot = pyautogui.screenshot(region=(left, top, width, height))
    arr = np.array(shot)[:, :, :3].astype(int)
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]

    found = {}
    for name, test in DIALS:
        mask = test(r, g, b)
        # a dial is a blob, not speckle: ignore anything under a few pixels
        if int(mask.sum()) < 12:
            continue
        ys, xs = np.where(mask)
        if not len(xs):
            continue
        cx = int(xs.mean()) + left
        cy = int(ys.mean()) + top
        found[name] = (cx, cy)
    return found


def solve():
    region = _panel_region()
    if not region:
        print("Calibrate Distributor: no game window dimensions")
        return 1
    left, top, width, height = region

    # The button sits below its dial. This offset is the one remaining assumption
    # in the solver, and it is why a screenshot is saved on failure: the dials
    # themselves are now found by colour, so only the button's position is a
    # guess, and the picture will show whether it is right.
    button_dy = round(height * 0.07)

    done = {name: False for name, _t in DIALS}
    start = time.time()
    clicks = 0

    while not is_task_done(task="Calibrate Distributor"):
        if _interrupted():
            print("Calibrate Distributor: interrupted")
            return 2
        if is_urgent_task():
            print("Calibrate Distributor: an urgent task needs doing")
            return 2
        if time.time() - start > 45:
            missing = [n for n in done if not done[n]]
            print(f"Calibrate Distributor: gave up after 45s; still to do: "
                  f"{', '.join(missing) or 'nothing'}")
            _dump_geometry("timeout")
            return 1

        dials = _find_dials(left, top, width, height)
        if not dials:
            # The panel is animating, or the dials are all at rest and dark.
            time.sleep(0.06)
            continue

        clicked = False
        for name, _t in DIALS:
            if done[name]:
                continue
            pos = dials.get(name)
            if not pos:
                continue
            # Click the button directly beneath the dial we can SEE, and do it
            # immediately: no other screenshot, no other dial examined first, so
            # the dial has the least possible time to rotate between being seen
            # and being clicked.
            pyautogui.click((pos[0], pos[1] + button_dy))
            done[name] = True
            clicks += 1
            clicked = True
            print(f"Calibrate Distributor: clicked the {name} button, found at "
                  f"{pos} - {sum(done.values())}/{len(DIALS)} done")
            break

        if clicked:
            # Wait for the dial to finish rotating before deciding anything again.
            time.sleep(0.7)
        else:
            time.sleep(0.06)

    print(f"Calibrate Distributor: done, {clicks} click(s), "
          f"{sum(done.values())}/{len(DIALS)} dials")
    return 0


if __name__ == "__main__":
    sys.exit(solve())
