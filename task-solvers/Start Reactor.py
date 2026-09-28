"""Start Reactor, restored to the logic that was known to work.

Original in git history: 2d3b70b, 2023-01-31.

The rewrite replaced this with "ask the plugin for the pads and the sequence".
That was a good idea in principle - the game really does expose
SimonSaysGame.Buttons and the `operations` queue - but it depends on the plugin
successfully resolving the concrete minigame class, and that has never worked: it
reported `class TaskAdderGame` for a panel that was neither, and it cached that
one wrong answer in a single static, so it was wrong for every panel afterwards.
With no pads published, the rewrite had no way to work and simply did not click.

So the pixel grid is restored. It is measured against this panel, not guessed: a
3x3 arrangement of possible pad positions, each sampled for the one colour the
game uses to indicate a lit pad, and a fixed horizontal offset to the pad itself.

Kept from the rewrite, because none of it touches the coordinates:

  - the harness opens the panel and confirms it from Minigame.Instance, so this
    does not call click_use(). The original did, which toggled the panel shut.
  - no JSON file. The original persisted the sequence to
    task-solvers/reactor_list/reactor_list.json so an interrupted run could pick
    up where it left off, and cleared it at the end. A stale file from a killed
    run made the next one replay clicks for pads that were never lit. The
    sequence is per-panel state and belongs in memory.
  - the result is only reported as success when the game says the task is done,
    rather than when the last pad happened to be clicked.
"""
import os
import sys
import time

import pyautogui

from task_utility import get_dimensions, is_task_done  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, ROOT)
import botlink  # noqa: E402

# The one colour the game lights a pad with, from the original solver.
LIT = (68, 168, 255)


def _interrupted():
    return botlink.solver_interrupted()


def _panel_open():
    try:
        return (botlink.read_minigame() or {}).get("open")
    except Exception:
        return None


def _solve():
    if _panel_open() is False:
        print("Start Reactor: the game says no panel is open, so nothing was "
              "clicked")
        return 1

    dimensions = get_dimensions()
    if not dimensions:
        print("Start Reactor: no game window dimensions")
        return 1

    # Original geometry, unchanged.
    x_start = dimensions[0] + round(dimensions[2] / 3.7)
    y_start = dimensions[1] + round(dimensions[3] / 2.3)
    x_offset = round(dimensions[2] / 16)
    y_offset = round(dimensions[3] / 9)
    button_x_offset = round(dimensions[2] / 3.11)

    click_list = []
    seen_pos = []
    start = time.time()

    while not is_task_done("Start Reactor"):
        if _interrupted():
            print("Start Reactor: interrupted")
            return 2
        if time.time() - start > 45:
            print(f"Start Reactor: gave up after 45s having read "
                  f"{len(click_list)} pad(s)")
            return 1

        found = False
        for i in range(3):
            if found:
                break
            for j in range(3):
                pos = (x_start + x_offset * i, y_start + y_offset * j)
                try:
                    pixel = pyautogui.pixel(pos[0], pos[1])
                except Exception:
                    continue
                if (abs(pixel[0] - LIT[0]) < 2 and abs(pixel[1] - LIT[1]) < 2
                        and abs(pixel[2] - LIT[2]) < 2):
                    found = True
                    if pos in seen_pos:
                        # this is the start of the player's turn: the pads we
                        # recorded are lit again, in order, waiting to be pressed
                        seen_pos.remove(pos)
                        time.sleep(0.2)
                        break
                    time.sleep(1.0)     # let the pad finish lighting
                    click_list.append(pos)
                    for cpos in click_list:
                        pyautogui.click(cpos[0] + button_x_offset, cpos[1])
                        seen_pos.append(cpos)
                        time.sleep(1 / 60)
                    print(f"Start Reactor: read {len(click_list)} pad(s) and "
                          f"pressed them in order")
                    break
        if not found:
            time.sleep(0.05)

    if is_task_done("Start Reactor"):
        print(f"Start Reactor: the game confirms it done - "
              f"{len(click_list)} pad(s) pressed")
        return 0
    print("Start Reactor: the game does NOT report the task as done")
    return 1


solve = _solve


if __name__ == "__main__":
    sys.exit(solve())
