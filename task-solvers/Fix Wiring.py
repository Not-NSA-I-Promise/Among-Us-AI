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


def endpoint_still_present(color):
    """Is this wire's loose end still on screen?

    Uses the SAME confidence ladder as finding the endpoint in the first place,
    and that is not a detail: the wire templates in this repo do not match above
    about 0.74 - the original code even discarded a 0.738 match as a failure. A
    stricter ladder here therefore finds NOTHING, ever, so "not present" is always
    true, every wire is instantly declared already-connected, no drag ever runs,
    and the panel just opens and closes. That is exactly what a live run did after
    this was briefly set to 0.9/0.85/0.8.

    The worry that motivated a stricter check - a connected wire is still drawn,
    so a loose match would treat a finished wire as pending and drag it onto a
    neighbour - is not what happens: the template is the loose END, and the end is
    what disappears on connection.
    """
    return endpoint_pos(color) is not None


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

# Which colours are actually on THIS panel, decided once while everything is
# still loose. It has to be a snapshot, because the test for "is this wire still
# loose?" is the same test that returns nothing for a colour that is not on the
# panel at all - so asking per wire would quietly report absent colours as
# connected and claim 4 of 4 on a two-wire panel.
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

connected = []
failed = []

for color in panel_colors:
    # Order within the panel: the game's own numbers run red 1, blue 2, yellow 3,
    # pink 4, and connecting them visibly out of order is wrong to anyone who
    # knows the pattern, so they are done in that order.
    done = False
    for attempt in range(3):
        if not endpoint_still_present(color):
            # the loose end is gone, so this wire is connected
            done = True
            break
        ends = endpoint_pos(color)
        if not ends:
            break
        left, right = ends
        pyautogui.moveTo(left[0] + round(dimensions[2] / 32), left[1])
        pyautogui.dragTo(right[0] - round(dimensions[2] / 19.2), right[1],
                          duration=0.25, tween=pyautogui.easeOutQuad)
        # The wire needs a moment to snap into place. Closing the panel after 0.2s
        # was cancelling the connection before the game registered it, which is
        # the other half of why the stage never completed.
        time.sleep(0.7)
    if done:
        connected.append(color)
        print(f"Fix Wiring: connected the {color} wire")
    else:
        failed.append(color)
        print(f"Fix Wiring: the {color} wire did not stay connected after 3 tries")

# Honest summary. A panel is only finished when every wire on it is connected, so
# this line is what lets the harness tell the difference between "did the panel"
# and "moved one wire and gave up" - which is what it used to report.
print(f"Fix Wiring: {len(connected)} of {len(panel_colors)} wires connected"
      + (f" (unconnected: {', '.join(failed)})" if failed else ""))

if failed:
    # Leave the panel open. Closing it would throw away the wires that DID
    # connect, and the retry would start the whole panel from scratch.
    print("Fix Wiring: leaving the panel open because some wires are unconnected")
else:
    try:
        how = click_close()
        print(f"Fix Wiring: {how}")
    except TypeError:
        pass
