import numpy as np
import cv2
from task_utility import *
import time
import copy
import pyautogui

# Fix Communications used to be literally "# Do nothing lol" - it relied on the
# harness opening the panel for it, and then did no work at all, so the task
# never completed and the loop just reopened the same panel forever.
#
# There are no templates for this task in the repo, so this finds the sliders
# from the pixels instead. The panel is a dark box containing a set of vertical
# tracks, each with a light handle. Every slider must be pushed UP. For each
# track the topmost light pixel is found, and the handle is clicked just below
# it, which is where the game reads a click as "move this slider up".
#
# The whole thing is verified by re-scanning: when every track's handle is at the
# top of the panel, the task is done. If the panel never opens, or the sliders
# never reach the top, that is reported instead of claimed.

dimensions = get_dimensions()

# The panel occupies the middle of the screen; the room behind it is dark too, so
# restrict the search to where the panel is drawn.
PANEL = [
    dimensions[0] + round(dimensions[2] * 0.25),
    dimensions[1] + round(dimensions[3] * 0.20),
    round(dimensions[2] * 0.50),
    round(dimensions[3] * 0.60),
]


def grab(region=None):
    """Screen pixels for a region, as an RGB numpy array."""
    shot = pyautogui.screenshot(region=region or PANEL)
    return cv2.cvtColor(np.array(shot), cv2.COLOR_RGB2BGR)


def panel_is_open():
    """The panel is open if it is much lighter than the dark room behind it."""
    img = grab()
    return float(img.mean()) > 45.0


def open_panel():
    """Open the panel. The state is checked BEFORE every click.

    USE is a toggle while a minigame is up, so clicking a panel that is already
    open closes it rather than doing nothing. Checking first means a click is
    only ever spent on a panel known to be closed, which makes this safe to call
    more than once and impossible to turn into a close.
    """
    for attempt in range(3):
        if panel_is_open():
            return True
        click_use()
        time.sleep(0.9)
        if panel_is_open():
            return True
        print(f"Fix Communications: the panel did not open on attempt "
              f"{attempt + 1}")
    return False


if not open_panel():
    print("Fix Communications: could not open the panel, so nothing was done")
    raise SystemExit(0)

# Slider handles are the brightest thing in each column. Scan columns in bands
# and, for each, find the highest row with a bright pixel.
img = grab()
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
h, w = gray.shape
BAND = max(6, w // 28)          # roughly one slider's width


def handle_rows(band_x0, band_x1):
    """Rows in one column band that look like a slider handle."""
    band = gray[:, band_x0:band_x1]
    rows = np.where(band.max(axis=1) > 150)[0]
    return rows


sliders = []
x = 0
while x + BAND < w:
    rows = handle_rows(x, x + BAND)
    if len(rows) >= 2:
        sliders.append((x + BAND // 2, int(rows[0]), int(rows[-1])))
    x += BAND

if not sliders:
    print("Fix Communications: the panel is open but no sliders were found in it, "
          "so nothing was done")
    try:
        print(f"Fix Communications: {click_close()}")
    except TypeError:
        pass
    raise SystemExit(0)

print(f"Fix Communications: found {len(sliders)} sliders")

# Each slider is a track from `top` to `bottom`; its handle starts somewhere
# between. Push every handle up by clicking just above where it currently is.
moved = 0
for _pass in range(3):
    for cx, top, bottom in sliders:
        img = grab()
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        rows = np.where(gray[:, max(0, cx - BAND // 2):cx + BAND // 2].max(axis=1)
                        > 150)[0]
        if not len(rows):
            continue
        # The handle is the lowest bright row in this column (a slider pushed up
        # has its handle near the top of the track).
        handle = int(rows[-1])
        target = handle - max(4, BAND)
        if target <= int(rows[0]) + 1:
            continue          # already at the top
        pyautogui.click((PANEL[0] + cx, PANEL[1] + target))
        moved += 1
        time.sleep(0.12)

time.sleep(0.5)

# Verify: re-scan and see whether every handle is now at the top of its track.
img = grab()
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
still_low = 0
for cx, top, bottom in sliders:
    rows = np.where(gray[:, max(0, cx - BAND // 2):cx + BAND // 2].max(axis=1)
                    > 150)[0]
    if len(rows) and int(rows[-1]) > int(rows[0]) + max(6, BAND):
        still_low += 1

if still_low:
    print(f"Fix Communications: {still_low} of {len(sliders)} sliders are still "
          f"low after {moved} clicks - NOT completed")
else:
    print(f"Fix Communications: all {len(sliders)} sliders are up after "
          f"{moved} clicks")

try:
    print(f"Fix Communications: {click_close()}")
except TypeError:
    pass
