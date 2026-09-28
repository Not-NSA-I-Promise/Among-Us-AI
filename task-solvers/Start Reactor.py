"""Start Reactor, driven entirely by the game's own state.

The old solver guessed. It laid a 3x3 grid of hardcoded pixel offsets over the
panel, sampled each point, and looked for one specific RGB value, (68, 168, 255),
to decide a pad was lit. Then it replayed the clicks from a JSON file. Every one
of those numbers was an assumption about where the game would put things, and
none of it survived contact with a real panel.

None of it is needed. The game class is:

    public class SimonSaysGame : Minigame
        private Queue<int> operations;      // the sequence
        public SpriteRenderer[] Buttons;    // the four pads
        public SpriteRenderer[] LeftLights; // the four lights
        private Color gray, blue, red, green;

and the plugin runs inside the game, so it publishes each pad's screen position
AND each light's current colour on every tick. So this script never has to look
at the screen at all:

  - which pad is lit  -> the game's own light colour, exactly
  - where to click it -> the game's own pad position, exactly
  - when the sequence is over -> every light is back to its idle colour

The only verification is the truth: did the panel close, and did the task bar
move. Both are read from the game.
"""
import os
import sys
import time

import pyautogui

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "task-solvers"))

import botlink  # noqa: E402


def _idle(colours):
    """The idle colour of a light: the one most of them share when unlit.

    Derived from the panel itself rather than hardcoded, because the old hardcoded
    RGB triple was an assumption too. At rest every unlit light is the same grey,
    so the most common colour in a settled panel IS the idle colour.
    """
    if not colours:
        return None
    tally = {}
    for _i, c in colours.items():
        tally[c] = tally.get(c, 0) + 1
    return max(tally, key=lambda c: tally[c])


def _lit_now(colours, idle):
    """Which lights differ from idle, if any."""
    if idle is None:
        return []
    return [i for i, c in colours.items() if c != idle]


def solve():
    controls = botlink.minigame_controls_ready(timeout=5.0)
    if not controls:
        print("Start Reactor: the game never reported the pad positions, so "
              "nothing was clicked. Guessing pixel offsets is what this task used "
              "to do and it did not work.")
        return 1
    if controls.get("type") != "simon":
        print(f"Start Reactor: the open panel is "
              f"{controls.get('type')!r}, not a Simon Says panel")
        return 1

    buttons = controls.get("buttons") or {}
    lightcols = controls.get("lightcols") or {}
    if not buttons:
        print("Start Reactor: the game reported no button positions")
        return 1
    if not lightcols:
        print("Start Reactor: the game reported no light colours")
        return 1

    print(f"Start Reactor: the game reports {len(buttons)} pads at "
          f"{sorted(buttons.values())}")

    # The sequence comes from the game's own `operations` queue, published by the
    # plugin. There is no other way to know how many pads to press, or when they
    # have all been played: between two flashes every light is dark, so reading
    # the light colours alone cannot tell one step from a whole round. The first
    # non-empty snapshot is the full sequence, because the queue is only consumed
    # as the game plays it.
    sequence = None
    deadline = time.time() + 8.0
    while time.time() < deadline:
        c = botlink.read_minigame_controls() or {}
        seq = c.get("seq")
        if seq:
            sequence = list(seq)
            break
        if botlink.solver_interrupted():
            print("Start Reactor: interrupted before the sequence was published")
            return 2
        time.sleep(0.05)

    if not sequence:
        print("Start Reactor: the game never published the sequence, so nothing "
              "was clicked")
        return 1
    print(f"Start Reactor: the game says to press {len(sequence)} pad(s): "
          f"{sequence}")

    # Wait for the game to stop playing the sequence and hand over the pads. The
    # queue empties as it is consumed, so an empty sequence means "your turn".
    deadline = time.time() + 20.0
    while time.time() < deadline:
        c = botlink.read_minigame_controls() or {}
        if not c.get("seq"):
            break
        if not botlink.read_minigame().get("open"):
            print("Start Reactor: the panel closed before the pads were pressed")
            return 2
        if botlink.solver_interrupted():
            return 2
        time.sleep(0.05)
    else:
        print("Start Reactor: the game never handed the pads over in 20s")
        return 1

    # Replay it.
    controls = botlink.read_minigame_controls() or controls
    buttons = controls.get("buttons") or buttons
    for step, idx in enumerate(sequence, 1):
        pos = buttons.get(idx)
        if pos is None:
            print(f"Start Reactor: step {step} needs pad {idx}, which the game "
                  f"did not report a position for")
            return 1
        pyautogui.click(pos[0], pos[1])
        print(f"Start Reactor: step {step}/{len(sequence)} clicked pad {idx} "
              f"at {pos}")
        time.sleep(0.28)
        if _urgent():
            return 2

    # The truth: the panel should close of its own accord.
    deadline = time.time() + 4.0
    while time.time() < deadline:
        if not botlink.read_minigame().get("open"):
            print(f"Start Reactor: the panel closed after all {len(sequence)} "
                  f"steps")
            return 0
        time.sleep(0.1)
    print("Start Reactor: the panel is still open after replaying the sequence, "
          "so it was NOT completed")
    return 1


def _urgent():
    # Cheap file reads only. The old version called meeting_time_left(), a
    # command round trip through the plugin, inside a 30ms poll loop.
    return botlink.solver_interrupted()




if __name__ == "__main__":
    sys.exit(solve())
