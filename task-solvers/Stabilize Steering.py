import numpy as np
import cv2
from task_utility import *
import time
import pyautogui

click_use()
time.sleep(0.8)

dimensions = get_dimensions()
resize_images(dimensions, "Stabilize Steering")

dimensions[0] += round(dimensions[2] / 3.69)
dimensions[1] += round(dimensions[3] / 10.38)
dimensions[2] = round(dimensions[2] / 2.21)
dimensions[3] = round(dimensions[3] / 1.25)
center = (round(dimensions[2] / 2), round(dimensions[3] / 2))

pos = find_template(
    f"{get_dir()}\\task-solvers\\cv2-templates\\Stabilize Steering resized\\crosshair.png",
    region=dimensions, confidences=(0.75, 0.65, 0.55))

if pos:
    pyautogui.moveTo(pos)
    pyautogui.dragTo(center[0] + dimensions[0], center[1] + dimensions[1], duration=0.2, tween=pyautogui.easeOutQuad)
else:
    print("Stabilize Steering: could not find the crosshair")