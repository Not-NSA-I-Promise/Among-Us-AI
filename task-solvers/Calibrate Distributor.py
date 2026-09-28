"""Calibrate Distributor, restored to the logic that was known to work.

This file was rewritten twice and both rewrites were worse than what they
replaced. The original is in git history (2c96581, 2023-01-26) and it is
self-consistent:

  - it builds a 2px-wide strip starting at window_x + width/1.56;
  - it hands that strip to get_screenshot(), which DOES honour a region, and
    reads getpixel((0, y)) - i.e. x=0 OF THE STRIP, which is the strip's real x;
  - it clicks at dimensions[0], the same x.

So the sample point and the click point are the same place. The colour ranges in
the original were measured against this panel, not guessed.

An intermediate rewrite replaced all of that with "crop the panel and hunt for
blobs of roughly the right colour". That was strictly worse: it found the game's
own HUD - a regular column at x~1120 - clicked it three times, and printed
"3/3 done". It also carried a claim in its own docstring that get_screenshot()
ignored the region, which was false; that came from reading a truncated context
window. The claim is recorded here because it is the sort of thing that gets
re-derived and re-trusted.

Kept from the rewrite, because both are improvements and neither touches the
coordinates:

  - the harness opens the panel and confirms it from Minigame.Instance, so this
    does not call click_use(). The original did, which toggled the panel shut.
  - the result is reported honestly. The original set done[i] = True the instant
    it clicked, so "done" was a claim about clicks issued, not about the task.
    Success is now only printed when the game itself reports the task complete.
"""
import os
import sys
import time

from task_utility import get_dimensions, get_screenshot, is_task_done  # noqa: E402
from task_utility import is_urgent_task  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, ROOT)
import botlink  # noqa: E402


def _interrupted():
    return botlink.solver_interrupted()


def _panel_open():
    try:
        return (botlink.read_minigame() or {}).get("open")
    except Exception:
        return None


def _solve():
    dimensions = get_dimensions()
    if not dimensions:
        print("Calibrate Distributor: no game window dimensions")
        return 1

    if _panel_open() is False:
        print("Calibrate Distributor: the game says no panel is open, so nothing "
              "was clicked")
        return 1

    # Measured from a live 1920x1080 screenshot of this panel, not guessed.
    #
    # The original sampled the colour at window_x + width/1.56 = 1231. Measured,
    # that column is rgb(0, 0, 0) - the black middle of each row's bar - on all
    # three rows, so a "bright yellow" test could never pass and the solver sat
    # there forever. The colour is in a small strip on the LEFT edge of each bar:
    #
    #   yellow  x 1116..1134
    #   blue    x 1116..1122
    #   cyan    x 1116..1122
    #
    # 1120/1920 is 7/12, which is the fraction used for sampling. The CLICK stays
    # at the original's width/1.56, because that lands on the button, which spans
    # roughly x 1140..1330. So the sample column and the click column are
    # deliberately different, which the original got wrong by assuming they were
    # the same.
    #
    # The three sample ROWS are the original's and are correct: 225, 500 and 750
    # all sit on their bars in the screenshot.
    colour_x = dimensions[0] + round(dimensions[2] * 7 / 12)
    button_x = dimensions[0] + round(dimensions[2] / 1.56)
    dimensions[0] = colour_x
    dimensions[2] = 2
    dimensions[2] = round(dimensions[2])

    yellow_offset = round(dimensions[3] / 4.8)
    blue_offset = round(dimensions[3] / 2.16)
    cyan_offset = round(dimensions[3] / 1.44)
    button_offset = dimensions[3] / 14.4

    # The original's three checks, verbatim.
    done = [False, False, False]
    start = time.time()
    clicks = 0
    print(f"Calibrate Distributor: sampling the colour at x={colour_x}, "
          f"clicking the button at x={button_x}")

    while not is_task_done(task="Calibrate Distributor"):
        if _interrupted():
            print("Calibrate Distributor: interrupted")
            return 2
        if is_urgent_task():
            print("Calibrate Distributor: an urgent task needs doing")
            return 2
        if time.time() - start > 40:
            missing = [n for n, d in zip(("yellow", "blue", "cyan"), done) if not d]
            print(f"Calibrate Distributor: gave up after 40s, {clicks} click(s); "
                  f"never done: {', '.join(missing) or 'nothing'}")
            return 1

        screenshot = get_screenshot(dimensions)
        if screenshot is None:
            # the grab failed (UAC, locked session, display change). Skipping a
            # pass is correct: it is not a reason to abandon the task, and it is
            # certainly not a reason to claim the task was done.
            time.sleep(0.2)
            continue
        s_y = screenshot.getpixel((0, yellow_offset))
        s_b = screenshot.getpixel((0, blue_offset))
        s_c = screenshot.getpixel((0, cyan_offset))

        clicked = False

        if not done[0]:
            if s_y[0] > 200 and s_y[1] > 200 and s_y[2] < 5:
                pyautogui = __import__("pyautogui")
                pyautogui.click((button_x,
                                 dimensions[1] + yellow_offset + button_offset))
                done[0] = True
                clicks += 1
                clicked = True
                print(f"Calibrate Distributor: clicked yellow at {s_y}")
            else:
                time.sleep(0.05)
                continue

        if not done[1]:
            if s_b[0] < 105 and s_b[0] > 80 and s_b[1] < 105 and s_b[1] > 80 \
                    and s_b[2] > 250:
                pyautogui = __import__("pyautogui")
                pyautogui.click((button_x,
                                 dimensions[1] + blue_offset + button_offset))
                done[1] = True
                clicks += 1
                clicked = True
                print(f"Calibrate Distributor: clicked blue at {s_b}")
            else:
                time.sleep(0.05)
                continue

        if not done[2]:
            if s_c[0] < 115 and s_c[0] > 105 and s_c[1] < 255 and s_c[1] > 245 \
                    and s_c[2] > 250:
                pyautogui = __import__("pyautogui")
                pyautogui.click((button_x,
                                 dimensions[1] + cyan_offset + button_offset))
                done[2] = True
                clicks += 1
                clicked = True
                print(f"Calibrate Distributor: clicked cyan at {s_c}")
            else:
                time.sleep(0.05)
                continue

        if clicked:
            # let the dial settle, so the next read is not mid-animation
            time.sleep(0.7)

    if is_task_done(task="Calibrate Distributor"):
        print(f"Calibrate Distributor: the game confirms it done - {clicks} "
              f"click(s), {sum(done)}/3 dials")
        return 0
    print("Calibrate Distributor: the game does NOT report the task as done")
    return 1


solve = _solve


if __name__ == "__main__":
    sys.exit(solve())
