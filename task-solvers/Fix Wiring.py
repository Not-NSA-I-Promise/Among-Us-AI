import numpy as np
import cv2
from task_utility import *
import time
import copy
import pyautogui

dimensions = get_dimensions()
resize_images(dimensions, "Fix Wiring")

# The original searched two very narrow vertical bands (x 505-612 and 1305-1412
# on a 1920 client), which only worked if the wiring panel happened to sit exactly
# there. Search the outer half of the panel on each side instead.
SEARCH_TOP = dimensions[1] + round(dimensions[3] / 8)
SEARCH_HEIGHT = round(dimensions[3] * 0.75)
SEARCH_WIDTH = round(dimensions[2] * 0.42)

left_dimensions = [
    dimensions[0] + round(dimensions[2] / 16),
    SEARCH_TOP,
    SEARCH_WIDTH,
    SEARCH_HEIGHT,
]

right_dimensions = [
    dimensions[0] + round(dimensions[2] * 0.55),
    SEARCH_TOP,
    SEARCH_WIDTH,
    SEARCH_HEIGHT,
]

wire_colors = ["red", "blue", "yellow", "pink"]


def endpoint_pos(color):
    """Where a wire's endpoints are, or None if that colour is not on the panel.

    Finding an endpoint is also how we know the panel is actually OPEN. Dragging
    at coordinates on a closed panel just moves the mouse over the game, which
    is what made a live run report a drag that could not possibly have worked.
    """
    template = (f"{get_dir()}\\task-solvers\\cv2-templates\\"
                f"Fix Wiring resized\\{color}Wire.png")
    left = find_template(template, region=left_dimensions, verbose=False)
    if not left:
        return None
    right = find_template(template, region=right_dimensions, verbose=False)
    if not right:
        return None
    return left, right


# Open the panel. The harness does NOT open it for us: it used to press USE here
# and then this click_use() clicked the on-screen USE button a second time, and
# with a minigame already open that second click CLOSES it.
def open_panel():
    """Open the panel and confirm it is really open. Returns True if it is."""
    for attempt in range(3):
        click_use()
        time.sleep(0.8)
        for color in wire_colors:
            if endpoint_pos(color):
                return True
        # No endpoint on any wire. Either the panel did not open, or we are
        # looking at the wrong panel - try opening again rather than dragging
        # blind.
        print(f"Fix Wiring: panel not open after opening it "
              f"(attempt {attempt + 1})")
    return False


if not open_panel():
    print("Fix Wiring: could not open the panel - the wire endpoints were never "
          "visible, so no wire was dragged")
    raise SystemExit(0)

# Wires in numeric order, which is the order the game's hidden numbers run in
# (red 1, blue 2, yellow 3, pink 4). Connecting them out of order is visibly
# wrong to anyone who knows the pattern, so this order matters.
connected = 0
for color in wire_colors:
    # find_template catches ImageNotFoundException at each rung. The previous
    # loop here called pyautogui directly, which RAISES rather than returning
    # None, so the very first attempt at confidence=0.8 killed the script and
    # the lower rungs were never reached - a 0.738 match was discarded.
    #
    # A colour that is not on this panel must be SKIPPED, not treated as the end.
    # The old `break` stopped the whole loop on the first miss, so a panel whose
    # wire was not red did nothing at all.
    ends = endpoint_pos(color)
    if not ends:
        continue
    left, right = ends

    pyautogui.moveTo(left[0] + round(dimensions[2] / 32), left[1])
    pyautogui.dragTo(right[0] - round(dimensions[2] / 19.2), right[1],
                      duration=0.2, tween=pyautogui.easeOutQuad)
    time.sleep(0.2)
    # Deliberately not "connected". A drag that misses still completes the code
    # path, and this line is what the harness reads as the solver having worked.
    # The stage counter is the only real evidence, and the harness checks that.
    print(f"Fix Wiring: dragged the {color} wire across - unverified")
    connected += 1
    break   # one wire per panel on Skeld; a second would be a wrong click

if connected == 0:
    print("Fix Wiring: no wire endpoint found on either side of this panel")
else:
    try:
        how = click_close()
        print(f"Fix Wiring: {how}")
    except TypeError:
        pass
