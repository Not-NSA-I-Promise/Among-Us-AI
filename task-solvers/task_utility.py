from PIL import ImageGrab
import ctypes
import win32gui
import pyautogui
import numpy as np
import cv2
import os
import pydirectinput
import time
from wake_keyboard import wake
from PIL import Image


ctypes.windll.user32.SetProcessDPIAware()

with open("sendDataDir.txt") as f:
    line = f.readline().rstrip()
    SEND_DATA_PATH = line + "\\sendData.txt"

SABOTAGE_TASKS = ["Reset Reactor", "Fix Lights", "Fix Communications", "Restore Oxygen"]

# A complete snapshot needs at least this many lines; the reader below uses
# lines[10] for the room, so 10 was not enough and the old check let a truncated
# file spin in `while True` forever.
DATA_MIN_LINES = 11


def read_snapshot_lines(path, tries=8, pause=0.15):
    """Read sendData.txt, tolerating the game writing it at the same moment.

    The plugin rewrites this file on every tick with File.WriteAllText, which
    truncates it first. On Windows, opening a file another process is writing is
    not guaranteed to succeed - it raises PermissionError - and a half-written
    file can be short. Both killed a solver outright: "Clear Asteroids" died with
    PermissionError: 'C:\\Games\\Among Us\\sendData.txt' and the whole task was
    abandoned mid-run.

    So: retry a few times, sharing the file so the writer is not locked out, and
    raise a clear error at the end rather than looping forever or crashing with a
    bare OSError.
    """
    last = None
    for _ in range(tries):
        try:
            with open(path, "r", buffering=1) as file:
                lines = file.readlines()
            if len(lines) >= DATA_MIN_LINES:
                return lines
            last = (f"the file is too short - only {len(lines)} line(s) where "
                    f"{DATA_MIN_LINES} are needed, so the game was caught "
                    f"mid-write")
        except PermissionError as exc:
            last = f"the game is writing it ({exc})"
        except OSError as exc:
            last = str(exc)
        time.sleep(pause)
    raise IOError(
        f"could not read a complete game snapshot from {path!r}: {last}. "
        f"The game may be loading, or the match may have ended.")


def getGameData():
    dataLen: int = DATA_MIN_LINES
    x,y,status,tasks, task_locations, task_steps, map_id, dead = None, None, None, None, None, None, None, None
    lines = read_snapshot_lines(SEND_DATA_PATH)
    if len(lines) < dataLen:
        raise IOError(f"game snapshot is too short: {len(lines)} lines")

    x = float(lines[0].split()[0])
    y = float(lines[0].split()[1])
    status = lines[1].strip()

    tasks = lines[2].rstrip().strip('][').split(", ")

    task_locations = lines[3].rstrip().strip('][').split(", ")

    task_steps = lines[4].rstrip().strip('][').split(", ")

    map_id = lines[5].rstrip()

    dead = bool(int(lines[6].rstrip()))

    room = lines[10].rstrip()

    if None in [x,y,status,tasks, task_locations, task_steps, map_id, dead, room]:
        raise IOError("game snapshot had missing fields")

    if dead or status == "impostor":
        if tasks[0] == "Submit Scan" and task_locations[0] == "Hallway":
            tasks.pop(0)
            task_locations.pop(0)
    return {"position" : (x,y), "status" : status, "tasks" : tasks, "task_locations" : task_locations, "task_steps" : task_steps, "map_id" : map_id, "dead": dead, "room" : room}

def get_screenshot(dimensions=None, window_title="Among Us"):
    if window_title:
        hwnd = win32gui.FindWindow(None, window_title)
        if hwnd and not dimensions:
            try:
                win32gui.SetForegroundWindow(hwnd)
            except Exception:
                pass
            x, y, x1, y1 = win32gui.GetClientRect(hwnd)
            x, y = win32gui.ClientToScreen(hwnd, (x, y))
            x1, y1 = win32gui.ClientToScreen(hwnd, (x1 - x, y1 - y))
            im = pyautogui.screenshot(region=(x, y, x1, y1))
            return im
        elif dimensions:
            im = pyautogui.screenshot(region=dimensions)
            return im
        else:
            print('Window not found!')
    else:
        im = pyautogui.screenshot()
        return im

def get_dimensions():
    window_title="Among Us"
    hwnd = win32gui.FindWindow(None, window_title)
    if hwnd:
        # Focusing is best-effort. SetForegroundWindow raises
        # pywintypes.error when the process does not own focus, and since every
        # coordinate helper goes through here, an unguarded call takes the whole
        # bot down. Getting the rect does not require focus.
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass
        x, y, x1, y1 = win32gui.GetClientRect(hwnd)
        x, y = win32gui.ClientToScreen(hwnd, (x, y))
        x1, y1 = win32gui.ClientToScreen(hwnd, (x1 - x, y1 - y))
        return [x, y, x1, y1]
    else:
        print('Window not found!')
        return None

def click_use():
    wake()
    dim = get_dimensions()
    pydirectinput.moveTo(dim[0] + dim[2] - round(dim[2] / 13), dim[1] + dim[3] - round(dim[3] / 7))
    pydirectinput.click()
    return

def find_template(template, region=None, confidences=(0.8, 0.7, 0.6, 0.5, 0.4),
                  grayscale=False, verbose=True):
    """Locate a template on screen, returning None instead of raising.

    pyautogui.locateCenterOnScreen RAISES ImageNotFoundException when it cannot
    find something. Solvers written as `pos = pyautogui.locateCenterOnScreen(...)`
    therefore die at that line whenever the template is not on screen, and a dead
    solver looks like a successful one to solve_task.

    This walks a confidence ladder and catches the exception at each rung, so a
    lower-confidence match is actually reachable. Use this instead of calling
    pyautogui directly.
    """
    for c in confidences:
        try:
            pos = pyautogui.locateCenterOnScreen(
                template, confidence=c, region=region, grayscale=grayscale)
            if pos:
                if verbose and c < confidences[0]:
                    print(f"  matched {os.path.basename(template)} "
                          f"at confidence {c}")
                return pos
        except pyautogui.ImageNotFoundException:
            continue
        except Exception as exc:
            # a bad region or a corrupt template should not kill the solver
            if verbose:
                print(f"  template search failed for "
                      f"{os.path.basename(template)}: {type(exc).__name__}")
            return None
    if verbose:
        print(f"  could not find {os.path.basename(template)} anywhere in the "
              f"region (tried confidence down to {confidences[-1]})")
    return None


def resize_images(dimensions, task_name):
    if task_name == "Unlock Manifolds":
        for i in range(1,11):
            loaded_img = Image.open(f"{get_dir()}\\task-solvers\\cv2-templates\\{task_name}\\{i}.png")
            new_img = loaded_img.resize((round(loaded_img.width * (dimensions[2] / 1920)), round(loaded_img.height*(dimensions[3] / 1080))))
            new_img.save(f"{get_dir()}\\task-solvers\\cv2-templates\\{task_name} resized\\{i}.png")
            
    elif task_name == "Fix Wiring":
        wire_colors = ["red", "blue", "yellow", "pink"]
        for color in wire_colors:
            loaded_img = Image.open(f"{get_dir()}\\task-solvers\\cv2-templates\\{task_name}\\{color}Wire.png")
            new_img = loaded_img.resize((round(loaded_img.width * (dimensions[2] / 1920)), round(loaded_img.height*(dimensions[3] / 1080))))
            new_img.save(f"{get_dir()}\\task-solvers\\cv2-templates\\{task_name} resized\\{color}Wire.png")

    elif task_name == "Stabilize Steering":
        loaded_img = Image.open(f"{get_dir()}\\task-solvers\\cv2-templates\\{task_name}\\crosshair.png")
        new_img = loaded_img.resize((round(loaded_img.width * (dimensions[2] / 1920)), round(loaded_img.height*(dimensions[3] / 1080))))
        new_img.save(f"{get_dir()}\\task-solvers\\cv2-templates\\{task_name} resized\\crosshair.png")

    elif task_name == "Inspect Sample":
        loaded_img = Image.open(f"{get_dir()}\\task-solvers\\cv2-templates\\{task_name}\\anomaly.png")
        new_img = loaded_img.resize((round(loaded_img.width * (dimensions[2] / 1920)), round(loaded_img.height*(dimensions[3] / 1080))))
        new_img.save(f"{get_dir()}\\task-solvers\\cv2-templates\\{task_name} resized\\anomaly.png")

    elif task_name == "close":
        loaded_img = Image.open(f"{get_dir()}\\task-solvers\\cv2-templates\\{task_name}\\closeX.png")
        new_img = loaded_img.resize((round(loaded_img.width * (dimensions[2] / 1920)), round(loaded_img.height*(dimensions[3] / 1080))))
        new_img.save(f"{get_dir()}\\task-solvers\\cv2-templates\\{task_name} resized\\closeX.png")


def get_dir():
    return os.getcwd()

def click_close():
    """Close the open task panel.

    This must never raise. It is called at the end of nearly every solver, often
    straight after the task succeeded - so if the close button cannot be found,
    killing the solver with an exception turned a completed task into a reported
    failure. The task panel closes on Escape anyway, so that is the fallback.
    """
    try:
        wake()
    except Exception:
        pass
    try:
        dim = get_dimensions()
    except Exception:
        dim = None
    if dim:
        try:
            resize_images(dim, "close")
        except Exception:
            pass
    center = find_template(
        f"{get_dir()}\\task-solvers\\cv2-templates\\close resized\\closeX.png",
        confidences=(0.7, 0.6, 0.5, 0.4), grayscale=True, verbose=False)
    if center:
        try:
            pydirectinput.moveTo(center[0], center[1])
            pydirectinput.click()
            return "closed with the X button"
        except Exception as exc:
            print(f"  close: click failed ({exc}); using escape")
    # The panel closes on Escape whether or not the X was found. Trying this
    # costs nothing and is far better than raising.
    try:
        pyautogui.press("escape")
        return "closed with escape"
    except Exception as exc:
        print(f"  close: could not close the panel ({exc})")
        return "could not close the panel"

def get_screen_coords():
    while True:
        print(pyautogui.position(), end='\r')

def get_screen_ratio(dim):
    while True:
        print(round(abs(dim[2] / (pyautogui.position().x - dim[0])), 2), round(abs(dim[3] / (pyautogui.position().y - dim[1])), 2), end='\r')

def is_task_done(task):
    data = getGameData()

    try:
        if task in SABOTAGE_TASKS:
            if task in data["tasks"]:
                return False
            return True

        index = data["tasks"].index(task)
        steps = data["task_steps"][index].split('/')
        return steps[0] == steps[1]
    
    # Index error on new ver
    except (IndexError, ValueError) as e:
        if task == "Reset Reactor" or task == "Reset Seismic Stabilizers":
            return not ("Reset Reactor" in data["tasks"] or "Reset Seismic Stabilizers" in data["tasks"])
        print("Index / Value error")
        print(task)
        print(data["tasks"])
        print(data["task_steps"])
        print(e)
        return False

def is_urgent_task() -> bool:
    data = getGameData()
    if data["dead"]:
        return False

    urgent_tasks = ["Reset Reactor", "Restore Oxygen", "Reset Seismic Stabilizers"]
    for task in urgent_tasks:
        if task in data['tasks']:
            return True
    return False