import numpy as np
import cv2
from task_utility import *
import time
import copy
import os
import pyautogui

# Inspect Sample is a two-step task, and the old version did neither step
# reliably:
#
#   1. It opened the panel with click_use(), but the harness had ALREADY opened
#      it with a USE press, so that second click closed it again. Every click
#      after that landed on the game world, not the panel - which is why it
#      looked like the bot was clicking and nothing happened, and why it looped
#      reopening and closing the same panel.
#   2. The code that found the anomaly tube was commented out, and the live
#      click was at a fixed offset (width/1.52, height/1.16) that is not the
#      green START button. So it pressed once somewhere, never waited for the
#      sample animation, and never clicked a tube.
#   3. It clicked without any check that the panel was open, so a closed panel
#      looked exactly like a successful one.
#
# The real sequence is: open the panel, click START, wait for the tubes to stop
# moving, click the odd one, and confirm the panel is gone. Anomaly.png is the
# only template available, so the START button is located by the fixed position
# the original used, but the TUBE is found by template, which is what matters.

dimensions = get_dimensions()


def _tube_pos():
    """Where an anomaly tube is, or None."""
    return find_template(
        f"{get_dir()}\\task-solvers\\cv2-templates\\Inspect Sample\\anomaly.png",
        confidences=(0.5, 0.4, 0.3), verbose=False)


# The middle of the screen, where the open panel is drawn. Used only to place the
# START click and to save a debug image on failure - never to decide whether the
# panel is open, which a blind brightness threshold gets wrong.
PANEL_REGION = [
    dimensions[0] + round(dimensions[2] * 0.25),
    dimensions[1] + round(dimensions[3] * 0.15),
    round(dimensions[2] * 0.50),
    round(dimensions[3] * 0.70),
]


def panel_is_open():
    """True if the Inspect Sample panel is up.

    Only the tube template is trusted. A brightness check was added here as a
    fallback and had to be removed: the panel region of a normally lit room is
    often brighter than any threshold that can be picked blind, so it reported
    "open" on a closed panel and the solver never clicked anything.
    """
    return _tube_pos() is not None


def open_panel():
    """Open the panel with AT MOST ONE click, then wait for it to appear.

    Clicking more than once is what made this task loop: the second click closed
    the panel the first one had opened, so the panel opened and shut repeatedly
    and nothing was ever submitted. So: check, click once, wait. Never click
    again - if it does not appear, report that and let the harness retry.
    """
    if panel_is_open():
        return True
    click_use()
    for _ in range(16):          # up to ~4s
        time.sleep(0.25)
        if panel_is_open():
            return True
    return False


def _save_debug(why):
    """Save what the panel looked like, so a failure is diagnosable.

    Every attempt to get this task right so far has been a guess about where the
    START button and the tubes are, and each guess was wrong in a different way.
    Writing the actual screen out turns the next attempt into a measurement.
    """
    try:
        path = os.path.join(get_dir(), f"inspect_sample_debug_{why}.png")
        pyautogui.screenshot(region=PANEL_REGION).save(path)
        print(f"Inspect Sample: saved the panel to {path} to show why ({why})")
    except Exception as exc:
        print(f"Inspect Sample: could not save a debug image ({exc})")


if not open_panel():
    print("Inspect Sample: could not open the panel - no anomaly tube was ever "
          "visible, so nothing was clicked")
    raise SystemExit(0)

# START button. The original used width/1.52, height/1.16; the user reports the
# panel opening and START never being pressed, so the click is placed from the
# panel's own geometry instead: horizontally centred, and near the bottom of the
# panel where the button is. Guessing a fraction of the whole window is what put
# the click in the wrong place to begin with.
start_x = PANEL_REGION[0] + round(PANEL_REGION[2] / 2)
start_y = PANEL_REGION[1] + round(PANEL_REGION[3] * 0.85)
pyautogui.click((start_x, start_y))
print(f"Inspect Sample: clicked START at ({start_x},{start_y})")

# The sample animates for about five seconds. Clicking during the animation
# either does nothing or closes the panel, so wait for the tubes to settle
# before looking for the odd one. Poll rather than trusting a fixed sleep.
tube = None
for _ in range(30):
    time.sleep(0.25)
    tube = _tube_pos()
    if tube:
        break

if not tube:
    print("Inspect Sample: START was clicked but the anomaly tube never "
          "appeared, so nothing was clicked")
    _save_debug("no-tube-after-start")
    try:
        print(f"Inspect Sample: {click_close()}")
    except TypeError:
        pass
    raise SystemExit(0)

# NO position filter here. A filter was added that rejected any match outside the
# middle 60% of the window height, on the theory that it would catch a match on
# the START button instead of a tube. It did the opposite: it rejected genuine
# tube matches every time, so the panel was never advanced and the task looped
# forever. The template is a picture of an anomaly tube, so a match is a tube.
pyautogui.click((tube[0], tube[1]))
print(f"Inspect Sample: clicked the anomaly tube at ({tube[0]},{tube[1]})")

# A correct pick closes the panel by itself. If it is still open, the click did
# not register on a tube.
time.sleep(0.8)
if panel_is_open():
    print("Inspect Sample: the panel is still open after clicking a tube, so the "
          "sample was NOT submitted")
    try:
        print(f"Inspect Sample: {click_close()}")
    except TypeError:
        pass
    raise SystemExit(0)

print("Inspect Sample: the panel closed, so the sample was submitted")
