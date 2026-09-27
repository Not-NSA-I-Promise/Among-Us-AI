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

click_use()
time.sleep(0.8)

# Wires in numeric order, which is the order the game's hidden numbers run in
# (red 1, blue 2, yellow 3, pink 4). Connecting them out of order is visibly
# wrong to anyone who knows the pattern, so this order matters.
wire_colors = ["red", "blue", "yellow", "pink"]

connected = 0
for color in wire_colors:
    template = f"{get_dir()}\\task-solvers\\cv2-templates\\Fix Wiring resized\\{color}Wire.png"

    # find_template catches ImageNotFoundException at each rung. The previous
    # loop here called pyautogui directly, which RAISES rather than returning
    # None, so the very first attempt at confidence=0.8 killed the script and
    # the lower rungs were never reached - a 0.738 match was discarded.
    #
    # A colour that is not on this panel must be SKIPPED, not treated as the end.
    # The old `break` stopped the whole loop on the first miss, so a panel whose
    # wire was not red did nothing at all.
    left = find_template(template, region=left_dimensions, verbose=False)
    if not left:
        continue

    right = find_template(template, region=right_dimensions, verbose=False)
    if not right:
        continue

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

