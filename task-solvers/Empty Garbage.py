"""Empty Trash (Skeld: Empty Chute and Empty Garbage), driven by the game.

The old solver opened the panel and then dragged the mouse from one hardcoded
point to another, lower down, over two seconds, and assumed that was the lever.
There was no check that anything happened, which is why it failed silently and
the task retried forever.

The game class is:

    public class EmptyGarbageMinigame : Minigame
        public FloatRange HandleRange;    // the lever's full travel
        public Collider2D Handle;         // the lever itself
        private bool finished;
        private float leverInput;
        private TouchpadBehavior touchpad;

so the plugin publishes the handle's real screen position, the travel range, and
the live `finished` and `leverInput` values. This script therefore:

  - only drags if there IS a handle. The second stage, in Storage, has nothing to
    drag - the trash simply falls - so it waits for the panel to close instead of
    dragging at empty space;
  - drags from the handle's actual position through the actual travel, not through
    a guessed fraction of the window;
  - checks `finished` afterwards, so "it dragged" is never reported as "it worked";
  - waits for the panel to actually close, which is the real completion.
"""
import os
import sys
import time

import pyautogui

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "task-solvers"))

import botlink  # noqa: E402


def _urgent():
    # Cheap file reads only. The old version called meeting_time_left(), a
    # command round trip through the plugin, inside a 30ms poll loop.
    return botlink.solver_interrupted()




def _wait_for_close(timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not botlink.read_minigame().get("open"):
            return True
        if _urgent():
            return False
        time.sleep(0.1)
    return not botlink.read_minigame().get("open")


def solve():
    controls = botlink.minigame_controls_ready(timeout=5.0)
    if not controls:
        print("Empty Trash: the game never reported the lever position, so "
              "nothing was dragged. Guessing pixel offsets is what this used to "
              "do and it did not work.")
        return 1
    if controls.get("type") != "garbage":
        print(f"Empty Trash: the open panel is {controls.get('type')!r}, not an "
              f"Empty Garbage panel")
        return 1

    has_handle = controls.get("has_handle", "handle" in controls)
    if not has_handle or "handle" not in controls:
        # Storage stage: the chute is up and the trash falls on its own. There is
        # nothing to click, so waiting is the correct behaviour, and the previous
        # version's blind 2-second drag here was pure noise.
        print("Empty Trash: this stage has no lever - the trash falls by itself, "
              "so waiting for it")
        return 0 if _wait_for_close(20.0) else (
            print("Empty Trash: the panel did not close in 20s") or 1)

    pos = controls["handle"]
    low = controls.get("handlelow")
    high = controls.get("handlehigh")
    print(f"Empty Trash: the lever is at {pos}, travel {low} to {high}")

    # Drag the full length of the travel, in a direction chosen from the range.
    # Pulling it up and letting it down are the same gesture, so the exact
    # direction does not matter - only that the mouse travels the whole range,
    # which the old hardcoded third-of-a-window offset frequently did not.
    span = abs((high or 0) - (low or 0))
    # The handle is a Collider2D in world space; a stage stage of travel is a few
    # units, and at this camera scale a full pull is comfortably ~2/3 of the
    # panel's height. Clamped so it is a drag and not a flick.
    pixels = max(60, min(400, int(span * 60) or 220))
    dest = (pos[0], pos[1] + pixels)

    print(f"Empty Trash: dragging the lever from {pos} to {dest}")
    pyautogui.moveTo(pos[0], pos[1])
    time.sleep(0.2)
    pyautogui.dragTo(dest[0], dest[1], duration=1.5, button="left")
    time.sleep(0.8)

    controls = botlink.read_minigame_controls() or controls
    if controls.get("finished"):
        print("Empty Trash: the game reports the lever is finished")
    else:
        print("Empty Trash: the game does NOT report it finished yet "
              f"(lever={controls.get('lever')}), so the drag may not have taken")

    if _wait_for_close(6.0):
        print("Empty Trash: the panel closed, so the stage completed")
        return 0
    print("Empty Trash: the panel is still open, so the stage did NOT complete")
    return 1


if __name__ == "__main__":
    sys.exit(solve())
