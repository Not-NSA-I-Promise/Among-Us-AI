import numpy as np
import cv2
from task_utility import *
import time
import cv2
import copy
import pyautogui

click_use()
time.sleep(0.8)

dimensions = get_dimensions()

x = dimensions[0] + round(dimensions[2] / 1.52)
y = dimensions[1] + round(dimensions[3] / 1.16)
pyautogui.click((x,y))

click_close()
raise SystemExit(0)

"""
y_offset = dimensions[3]
dimensions[0] += round(dimensions[2] / 2.81)
dimensions[1] += round(dimensions[3] / 3.2)
dimensions[2] = round(dimensions[2] / 3.4)
dimensions[3] = round(dimensions[3] / 3.6)

pos = find_template(
    f"{get_dir()}\\task-solvers\\cv2-templates\\Inspect Sample\\anomaly.png",
    region=dimensions, confidences=(0.5, 0.4))
if pos:
    pyautogui.click(pos[0], pos[1] + round(y_offset / 2.87))
else:
    print("Inspect Sample: could not find the anomaly tube")
"""