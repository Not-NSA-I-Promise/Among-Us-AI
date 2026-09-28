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

    # Drag the lever by WATCHING IT, not by guessing how far "down" is.
    #
    # The first attempt computed a distance from the world-space travel range -
    # span 1.3 * 60 = 78px - released the mouse after 78px, and the lever sprang
    # straight back. A live run showed the handle at y=423 before and y=422 after,
    # i.e. it had not moved at all. The game wants the lever held all the way to
    # the end of its travel, and only the game knows where the end is.
    #
    # So: press on the handle, step down, and after each step re-read where the
    # game says the handle now is. When it stops moving, it has reached the end
    # of its travel, and that is the moment to release. If it never stops, the
    # drag is still going when the step budget runs out.
    pyautogui.moveTo(pos[0], pos[1])
    time.sleep(0.25)
    pyautogui.mouseDown()
    time.sleep(0.2)

    last = pos
    still = 0
    moved = 0
    steps = 0
    for i in range(1, 41):
        if botlink.solver_interrupted():
            pyautogui.mouseUp()
            print("Empty Trash: interrupted mid-drag")
            return 2
        pyautogui.moveTo(pos[0], pos[1] + i * 12)
        time.sleep(0.12)
        steps = i
        c = botlink.read_minigame_controls() or {}
        now = c.get("handle")
        if now:
            if abs(now[1] - last[1]) >= 1:
                moved = abs(now[1] - last[1])
                still = 0
            else:
                still += 1
            last = now
        # three consecutive reads with the handle in the same place means the
        # lever is against the end of its travel
        if still >= 3:
            print(f"Empty Trash: the handle has stopped moving at {last} after "
                  f"{i} step(s), so the lever is fully pulled")
            break
    pyautogui.mouseUp()
    time.sleep(0.6)

    controls = botlink.read_minigame_controls() or controls
    now = controls.get("handle")
    print(f"Empty Trash: dragged {steps} step(s); the handle is now {now} "
          f"(it started at {pos}, it moved {moved}px)")
    if controls.get("finished"):
        print("Empty Trash: the game reports finished 1")
    else:
        print("Empty Trash: the game does not report finished yet, so the stage "
              "may not have completed")

    if _wait_for_close(6.0):
        print("Empty Trash: the panel closed, so the stage completed")
        return 0
    print("Empty Trash: the panel is still open, so the stage did NOT complete")
    return 1


if __name__ == "__main__":
    sys.exit(solve())
