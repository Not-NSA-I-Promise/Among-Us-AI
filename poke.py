r"""Click and drag in CLIENT coordinates, so a position read off peek.py works.

    .venv\Scripts\python.exe poke.py click 350 390
    .venv\Scripts\python.exe poke.py drag 100 100 400 400 0.8
    .venv\Scripts\python.exe poke.py use          # the on-screen USE button
    .venv\Scripts\python.exe poke.py escape

A development aid for driving the game by hand while writing a solver. It
translates client pixels to screen pixels using the game's own window rect,
which is the same mapping every solver uses.
"""
import sys
import time

sys.path.insert(0, "task-solvers")
import task_utility  # noqa: E402
import pyautogui  # noqa: E402
import win32con  # noqa: E402
import win32gui  # noqa: E402

pyautogui.FAILSAFE = False


def focus_game(topmost=True):
    """Put the game window on top and give it keyboard focus.

    SetForegroundWindow alone is refused whenever the calling process does not
    own the foreground, and this one usually does not - so a click intended for
    the game lands on whatever window happens to be in front instead, and the
    round silently never starts. Raising the window with SetWindowPos works
    regardless of who owns the foreground.

    TOPMOST is the part that actually matters here. Without it, anything that
    opens - a cleaner, a settings window, a notification - covers the game,
    the game pauses, and the plugin stops publishing. With it, the game stays
    the window the clicks go to. Clear it with --notopmost when you are done.
    """
    hwnd = win32gui.FindWindow(None, "Among Us")
    if not hwnd:
        return None
    try:
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    except Exception:
        pass
    z = win32con.HWND_TOPMOST if topmost else win32con.HWND_NOTOPMOST
    for attempt in range(3):
        try:
            win32gui.SetWindowPos(hwnd, z, 0, 0, 0, 0,
                                  win32con.SWP_NOMOVE | win32con.SWP_NOSIZE |
                                  win32con.SWP_SHOWWINDOW)
        except Exception:
            pass
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass
        try:
            if win32gui.GetForegroundWindow() == hwnd:
                return hwnd
        except Exception:
            pass
        time.sleep(0.4)
    return hwnd


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    what = sys.argv[1]
    focus_game()
    dim = task_utility.get_dimensions()
    if not dim:
        print("game window not found")
        return 2

    def to_screen(x, y):
        return (dim[0] + int(x), dim[1] + int(y))

    if what == "click":
        x, y = to_screen(sys.argv[2], sys.argv[3])
        pyautogui.click(x, y)
        print(f"clicked ({x},{y})")
    elif what == "drag":
        x0, y0 = to_screen(sys.argv[2], sys.argv[3])
        x1, y1 = to_screen(sys.argv[4], sys.argv[5])
        dur = float(sys.argv[6]) if len(sys.argv) > 6 else 0.8
        pyautogui.moveTo(x0, y0)
        time.sleep(0.15)
        pyautogui.mouseDown()
        time.sleep(0.15)
        # move in steps: a single jump is treated as a flick, not a drag
        steps = 30
        for i in range(1, steps + 1):
            pyautogui.moveTo(x0 + (x1 - x0) * i // steps,
                             y0 + (y1 - y0) * i // steps)
            time.sleep(dur / steps)
        time.sleep(0.15)
        pyautogui.mouseUp()
        print(f"dragged ({x0},{y0}) -> ({x1},{y1})")
    elif what == "use":
        # the same position task_utility.click_use() uses
        x = dim[0] + dim[2] - round(dim[2] / 13)
        y = dim[1] + dim[3] - round(dim[3] / 7)
        pyautogui.click(x, y)
        print(f"clicked USE at ({x},{y})")
    elif what == "escape":
        pyautogui.press("escape")
        print("escape")
    elif what == "notopmost":
        poke = sys.modules[__name__]
        poke.focus_game(topmost=False)
        print("game window is no longer topmost")
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
