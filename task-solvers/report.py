from task_utility import *
import copy
import pyautogui
import time

def get_report_button_pos() -> tuple:
    dimensions = get_dimensions()

    x = dimensions[0] + round(dimensions[2] / 1.19)
    y = dimensions[1] + round(dimensions[3] / 1.17)
    return (x,y)

def can_report() -> bool:
    # Never let this raise. It is called on every step of move(); if it throws,
    # the whole movement loop dies. SetForegroundWindow in particular can fail
    # with "No error message is available" when the process does not own focus.
    try:
        x,y = get_report_button_pos()
        col = pyautogui.pixel(x, y)
        return col[0] > 200 and col[2] < 5
    except Exception:
        return False

# DEPRECIATED
def report() -> None:
    if not can_report():
        return
    wake()
    pyautogui.click(get_report_button_pos())