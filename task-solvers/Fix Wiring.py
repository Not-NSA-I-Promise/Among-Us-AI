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

# The middle of the screen, which is where the open panel is drawn. Used to tell
# "the panel is open" from "the panel is closed" by brightness, so a click is
# never spent on a panel that is already up.
PANEL_REGION = [
    dimensions[0] + round(dimensions[2] * 0.25),
    dimensions[1] + round(dimensions[3] * 0.15),
    round(dimensions[2] * 0.50),
    round(dimensions[3] * 0.70),
]
# The panel is a pale box on a darker room. A closed panel leaves the room's
# average well below this; a generous threshold, because a false "closed" only
# costs one more click while a false "open" would mean dragging at nothing.
PANEL_BRIGHTNESS = 60.0

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
def panel_is_open():
    """Is the Fix Wiring panel on screen?

    Two independent signals, because getting this wrong is expensive in both
    directions. A false "closed" costs another click, which is fine. A false
    "open" is not: we would go on to drag wires that are not there.
    """
    for color in wire_colors:
        if endpoint_pos(color):
            return True
    # Second signal: the open panel is a bright box; closed, you see the room
    # behind it. This is what lets the loop below tell "the click did nothing"
    # apart from "the panel is open but the wires are not legible yet", which is
    # the difference between clicking again and clicking on an open panel, which
    # CLOSES it.
    try:
        shot = pyautogui.screenshot(region=PANEL_REGION)
        return float(np.array(shot).mean()) > PANEL_BRIGHTNESS
    except Exception:
        return False


def open_panel():
    """Open the panel and confirm it is really open. Returns True if it is.

    Never clicks a panel that is already open. The USE button is a TOGGLE while a
    minigame is up, so an extra click does not fail to do anything - it closes
    the panel. That is not hypothetical: a duplicated call to this function in the
    source meant the first call opened the panel, the second clicked it shut, and
    the solver then dragged wires into empty space while reporting that it could
    not find the panel.

    So the state is checked BEFORE every click, and the click is only issued when
    the panel is known to be closed.
    """
    for attempt in range(3):
        if panel_is_open():
            return True
        click_use()          # only ever issued while the panel is closed
        time.sleep(0.9)
        if panel_is_open():
            return True
        print(f"Fix Wiring: the panel did not open on attempt {attempt + 1}")
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
