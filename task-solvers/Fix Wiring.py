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

wire_colors = ["red", "blue", "yellow", "pink"]

for color in wire_colors:
    template = f"{get_dir()}\\task-solvers\\cv2-templates\\Fix Wiring resized\\{color}Wire.png"

    # Widen the confidence window before giving up on a wire.
    left = None
    for confidence in (0.8, 0.7, 0.6, 0.5):
        left = pyautogui.locateCenterOnScreen(template, confidence=confidence, region=left_dimensions)
        if left:
            break
    if not left:
        print(f"Fix Wiring: could not find {color} wire on the left")
        break

    pyautogui.moveTo(left[0] + round(dimensions[2] / 32), left[1])

    right = None
    for confidence in (0.8, 0.7, 0.6, 0.5):
        right = pyautogui.locateCenterOnScreen(template, confidence=confidence, region=right_dimensions)
        if right:
            break
    if not right:
        print(f"Fix Wiring: could not find {color} wire on the right")
        break

    pyautogui.dragTo(right[0] - round(dimensions[2] / 19.2), right[1], duration=0.2, tween=pyautogui.easeOutQuad)
    time.sleep(0.2)

try:
    click_close()
except TypeError:
    # panel already closed, nothing to click
    pass
