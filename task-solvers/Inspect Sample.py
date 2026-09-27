import numpy as np
import cv2
from task_utility import *
import time
import copy
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


def panel_is_open():
    """True if an anomaly tube is on screen, i.e. the panel is really open."""
    return find_template(
        f"{get_dir()}\\task-solvers\\cv2-templates\\Inspect Sample\\anomaly.png",
        confidences=(0.5, 0.4, 0.3), verbose=False) is not None


def open_panel():
    for attempt in range(3):
        click_use()
        time.sleep(0.8)
        if panel_is_open():
            return True
        print(f"Inspect Sample: panel not open after opening it "
              f"(attempt {attempt + 1})")
    return False


if not open_panel():
    print("Inspect Sample: could not open the panel - no anomaly tube was ever "
          "visible, so nothing was clicked")
    raise SystemExit(0)

# START button. The only position available: the original used this offset and
# it does sit on the green button, so it is kept - but the panel being open is
# now confirmed first, which is what was missing.
start_x = dimensions[0] + round(dimensions[2] / 1.52)
start_y = dimensions[1] + round(dimensions[3] / 1.16)
pyautogui.click((start_x, start_y))
print("Inspect Sample: clicked START")

# The sample animates for about five seconds. Clicking during the animation
# either does nothing or closes the panel, so wait for the tubes to settle
# before looking for the odd one. Poll rather than trusting a fixed sleep.
tube = None
for _ in range(30):
    time.sleep(0.25)
    tube = find_template(
        f"{get_dir()}\\task-solvers\\cv2-templates\\Inspect Sample\\anomaly.png",
        confidences=(0.5, 0.4, 0.3), verbose=False)
    if tube:
        break

if not tube:
    print("Inspect Sample: START was clicked but the anomaly tube never "
          "appeared, so nothing was clicked")
    try:
        print(f"Inspect Sample: {click_close()}")
    except TypeError:
        pass
    raise SystemExit(0)

# The template is matched on the whole screen, so the match can be the START
# button rather than a tube. A tube sits in the middle band of the panel, and
# START is near the bottom, so require a plausible vertical position.
if not (dimensions[1] + dimensions[3] * 0.2 < tube[1]
        < dimensions[1] + dimensions[3] * 0.8):
    print("Inspect Sample: the only match was the START button, not a tube, so "
          "the panel was not advanced")
    try:
        print(f"Inspect Sample: {click_close()}")
    except TypeError:
        pass
    raise SystemExit(0)

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
