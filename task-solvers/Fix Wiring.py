import numpy as np
import cv2
from task_utility import *
import time
import copy
import os
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


def endpoint_pos(color, confidences=(0.8, 0.7, 0.6, 0.5, 0.4)):
    """Where a wire's endpoints are, or None if that colour is not on the panel.

    Finding an endpoint is also how we know the panel is actually OPEN. Dragging
    at coordinates on a closed panel just moves the mouse over the game, which
    is what made a live run report a drag that could not possibly have worked.
    """
    template = (f"{get_dir()}\\task-solvers\\cv2-templates\\"
                f"Fix Wiring resized\\{color}Wire.png")
    left = find_template(template, region=left_dimensions,
                         confidences=confidences, verbose=False)
    if not left:
        return None
    right = find_template(template, region=right_dimensions,
                          confidences=confidences, verbose=False)
    if not right:
        return None
    return left, right


# Open the panel. The harness does NOT open it for us: it used to press USE here
# and then this click_use() clicked the on-screen USE button a second time, and
# with a minigame already open that second click CLOSES it.
def wires_visible():
    """Is any wire endpoint on screen? i.e. is the panel really up.

    Only this signal is trusted. A brightness check was tried here as a second
    opinion and it made things much worse: the panel region of a normally lit
    room is often brighter than the threshold, so this returned True with the
    panel closed, the solver concluded it was already open, never clicked, and
    the wires panel never opened at all.
    """
    for color in wire_colors:
        if endpoint_pos(color):
            return True
    return False


def open_panel():
    """Open the panel with AT MOST ONE click, then wait for it to appear.

    Clicking more than once is what caused this task to fail twice, in two
    different ways: a duplicated call closed the panel it had just opened, and a
    loop that re-clicked while waiting for a slow panel did the same thing. Both
    look identical from outside - the panel opens and closes having done nothing.

    So the rule is simply: check, click once if the panel is not up, then wait.
    Never click again. If it does not appear, say so honestly and let the harness
    retry the whole panel from outside, which is a safe place to do that from.
    """
    if wires_visible():
        return True              # already up: do not touch it
    click_use()                  # the one and only click
    for _ in range(16):          # up to ~4s
        time.sleep(0.25)
        if wires_visible():
            return True
    return False


if not open_panel():
    print("Fix Wiring: could not open the panel - the wire endpoints were never "
          "visible, so no wire was dragged")
    raise SystemExit(0)

def _save_debug(why):
    """Save the panel to a PNG so a failure can be looked at.

    Every attempt to get this task right has been a guess about where the wire
    ends are, and each guess was wrong differently. The templates were measured
    rather than guessed, but the panel's layout in the live game has not been,
    and until somebody looks at a real panel the guesses keep coming.
    """
    try:
        region = [
            dimensions[0] + round(dimensions[2] * 0.15),
            dimensions[1] + round(dimensions[3] * 0.05),
            round(dimensions[2] * 0.70),
            round(dimensions[3] * 0.90),
        ]
        path = os.path.join(get_dir(), f"fix_wiring_debug_{why}.png")
        pyautogui.screenshot(region=region).save(path)
        print(f"Fix Wiring: saved the panel to {path} ({why})")
    except Exception as exc:
        print(f"Fix Wiring: could not save a debug image ({exc})")


# Which colours are actually on THIS panel, decided once while everything is
# still loose. It has to be a snapshot: the "is this wire still loose?" test
# returns nothing for a colour that is not on the panel at all, so asking per
# wire would report absent colours as connected.
panel_colors = [c for c in wire_colors if endpoint_pos(c)]

if not panel_colors:
    print("Fix Wiring: the panel is open but none of the four wires could be "
          "found on it, so no wire was dragged")
    try:
        print(f"Fix Wiring: {click_close()}")
    except TypeError:
        pass
    raise SystemExit(0)

print(f"Fix Wiring: this panel has {len(panel_colors)} wire(s): "
      f"{', '.join(panel_colors)}")

# The templates were MEASURED to be 34x39 and 37x38 pixels, fully opaque, so the
# centre of a match is the centre of the wire's end nub. That means the centre is
# the right place to grab and the right place to drop.
#
# The old code dragged from left+width/32 to right-width/19.2. On a 1920 window
# that is +60px to -100px, which is one and a half to three whole template-widths
# AWAY from a nub that is only 34px wide. It happened to work because the drag
# kept the same y and the game snaps to whatever is nearest, but it is not
# targeting the wire.
#
# And the wire is not verified visually here. A per-wire "is it gone?" check was
# added and had to be removed: a 34x39 template on a confidence ladder that
# reaches 0.4, searched over a region containing the ELEVEN decorative background
# wires, produces false matches almost every time. So a wire that had connected
# correctly still read as present, and the solver dragged it three more times
# before giving up on a wire that was already done. That check was the reason a
# live run reported wires refusing to stay connected.
#
# The harness already owns the real verdict: the task's stage counter. If the
# panel really was wired, the stage advances. If it was not, do_task says so and
# retries the panel from outside, which is a safe place to retry from.
dragged = []
for color in panel_colors:
    ends = endpoint_pos(color)
    if not ends:
        print(f"Fix Wiring: the {color} wire could not be located when it came "
              f"to connecting it")
        continue
    left, right = ends
    pyautogui.moveTo(left[0], left[1])
    pyautogui.dragTo(right[0], right[1], duration=0.25,
                     tween=pyautogui.easeOutQuad)
    # The wire needs a moment to settle into place. Closing faster than this was
    # cancelling the connection before the game registered it.
    time.sleep(0.5)
    dragged.append(color)
    print(f"Fix Wiring: dragged the {color} wire across")

print(f"Fix Wiring: dragged {len(dragged)} of {len(panel_colors)} wire(s)")

if len(dragged) < len(panel_colors):
    # Leave it open rather than throwing away the wires that did land.
    _save_debug("some-wires-not-connected")
    print("Fix Wiring: leaving the panel open because some wires were not "
          "connected")
else:
    # Still capture it: the harness only sees the task bar, so this is the only
    # record of what the drags actually looked like.
    _save_debug("dragged")
    try:
        how = click_close()
        print(f"Fix Wiring: {how}")
    except TypeError:
        pass
