"""Start Reactor, driven by the game's own sequence.

What the task actually is
-------------------------
A memory game. The panel flashes a sequence of squares on the left and you
press the matching pads on the right, in the same order. It is five rounds,
and each round replays the whole sequence with one more element added, so the
rounds are 1, 2, 3, 4 and 5 presses long.

None of that is a guess. It is what the game does, read out of the game's own
code:

  * NormalPlayerTask.Initialize allocates `Data` as `new byte[6]` for a Start
    Reactor task - room for a count and five indices.
  * SimonSaysGame.AddIndex appends one random pad index to `Data` at the start
    of every round and bumps `Data[0]`, the count. So `Data[0]` is how long
    the current sequence is and `Data[1..]` are the pad indices.
  * SimonSaysGame.HitButton(i) compares `i` with `Data[taskStep + 1]` and
    does nothing at all if they differ. So the pad to press is
    `Data[taskStep + 1]`, and `taskStep` counts the presses made so far in
    this round.
  * The end of the round's playback sets `taskStep` back to 0, which is why
    every round starts again at `Data[1]`.
  * A press on the WRONG pad sets `Data[0] = 0`, which throws the sequence
    away and starts the next round over with a fresh random pad. So a wrong
    press is not a lost point, it is a lost task.

The one trap
------------
HitButton does not check whether the round's playback is still running. A
press issued mid-playback is accepted and then silently discarded when the
playback resets the counter, which leaves the bot one press out of step - and
the next press is then the wrong one, which loses the task.

So the solver waits for the round to be ready before it presses. The game
itself says when that is: the playback turns every pad grey as it starts and
white as it ends, and the plugin publishes that as `roundready`.
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(os.getcwd(), "task-solvers"))

import botlink  # noqa: E402
from task_utility import is_task_done, open_task_panel  # noqa: E402


def _interrupted():
    try:
        return botlink.solver_interrupted()
    except Exception:
        return False


def solve():
    if not open_task_panel():
        print("Start Reactor: no panel is open - it would not open, so nothing was pressed")
        return 1
    hot = botlink.read_minigame_hot()
    if not hot:
        print("Start Reactor: no panel is open, so nothing was pressed")
        return 1
    print(f"Start Reactor: the panel says {hot.get('task')!r}")

    deadline = time.time() + 120
    presses = 0
    rounds = 0
    last_count = 0
    # The round the solver is on. The game resets its own counter to 0 at the
    # end of every playback, and the solver keeps its own so it can tell a
    # fresh round from a stale counter left over from the last one.
    pos = 0

    while time.time() < deadline:
        if _interrupted():
            print("Start Reactor: interrupted")
            return 2
        if is_task_done("Start Reactor"):
            print(f"Start Reactor: the game confirms it done "
                  f"({presses} press(es) over {rounds} round(s))")
            return 0

        hot = botlink.read_minigame_hot()
        if not hot:
            if is_task_done("Start Reactor"):
                print(f"Start Reactor: the game confirms it done "
                      f"({presses} press(es) over {rounds} round(s))")
                return 0
            print("Start Reactor: the panel closed and the task is not done")
            return 1

        data = hot.get("data") or {}
        count = data.get(0, 0)
        step = hot.get("step", 0)

        if count == 0:
            # No round, or the last press was wrong and the sequence was
            # thrown away. The game is about to build a fresh one.
            pos = 0
            time.sleep(0.05)
            continue

        if count != last_count:
            # A new round: one more element than last time.
            rounds += 1
            last_count = count
            pos = 0
            print(f"Start Reactor: round {rounds}, {count} pad(s) to press")

        if pos >= count:
            # This round is done; wait for the game to build the next one.
            time.sleep(0.02)
            continue

        if not hot.get("roundready"):
            # The playback is still running. Pressing now would be accepted
            # and then thrown away, which is how a task is lost.
            time.sleep(0.02)
            continue

        pad = data.get(pos + 1)
        if pad is None:
            time.sleep(0.02)
            continue

        try:
            botlink.minigame_call("HitButton", pad, timeout=2.0)
        except botlink.CommandFailed as exc:
            print(f"Start Reactor: the game refused the press ({exc.reason})")
            return 1
        presses += 1
        pos += 1
        time.sleep(0.03)

    print("Start Reactor: gave up after 120s")
    return 1


solve = solve


if __name__ == "__main__":
    sys.exit(solve())
