import numpy as np
import cv2
from task_utility import *
import time
import pyautogui
import keyboard

click_use()
time.sleep(0.8)

dimensions = get_dimensions()
resize_images(dimensions, "Unlock Manifolds")
dimensions[0] += round(dimensions[2] / 3.4)
dimensions[1] += round(dimensions[3] / 2.9)
dimensions[2] = round(dimensions[2] / 2.4)
dimensions[3] = round(dimensions[3] / 3.1)

pos = None
for i in range(1, 11):
    # The old version polled in an unbounded while-loop whose only exit was the
    # ` key, and the pyautogui call RAISES on the first miss rather than
    # returning None, so the loop never even ran - it just crashed. Bounded
    # retries here, and a clean failure instead of a crash or a hang.
    pos = None
    for _attempt in range(5):
        pos = find_template(
            f"{get_dir()}\\task-solvers\\cv2-templates\\Unlock Manifolds resized\\{i}.png",
            region=dimensions, confidences=(0.8, 0.7, 0.6), grayscale=True,
            verbose=False)
        if pos:
            break
        if keyboard.is_pressed('`'):
            raise SystemExit(0)
        time.sleep(0.4)
    if not pos:
        print(f"Unlock Manifolds: gave up looking for step {i}")
        break
    pyautogui.click(pos)
