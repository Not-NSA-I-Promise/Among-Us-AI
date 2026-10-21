r"""Reroll a Skeld practice round until the wanted tasks turn up.

Practice mode gives four random tasks and offers no way to choose them, so
getting a specific panel on screen means rerolling. This drives the menus and
reports the task list it got, so the loop is one command instead of a dozen
screenshots.

    .venv\Scripts\python.exe practice.py --want "Calibrate Distributor" "Start Reactor" --any

--any stops at the first round holding AT LEAST ONE wanted task. Rerolling for
several at once almost never succeeds: a Skeld round deals four tasks out of
twenty-odd.

Two things make this work and are not optional:

  * The game PAUSES when it loses focus, so the plugin stops publishing and the
    snapshot goes stale. focus_game() is called before every interaction, and a
    stale snapshot is treated as "the game was unfocused", not as "no tasks".
  * "In a round" is decided by the snapshot being FRESH, never by inGameData.txt.
    That flag says the game was in a round at some point; it does not say it
    still is, and it is left behind on the main menu.

Development aid for writing solvers. It only ever drives the menus; the bot's
own files are not involved.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, "task-solvers")
import poke  # noqa: E402
import pyautogui  # noqa: E402
import utility  # noqa: E402

pyautogui.FAILSAFE = False

# Read off the menu screenshots, in CLIENT pixels. Every one of these was
# confirmed against a real screenshot rather than guessed.
MENU_PLAY = (350, 390)
MENU_PRACTICE = (1576, 908)
MENU_SKELD = (1115, 508)
IN_GAME_GEAR = (1651, 87)
GEAR_LEAVE = (959, 869)

SNAPSHOT = utility.SEND_DATA_PATH
FRESH = 2.0


def click(dim, pt, pause=1.2):
    x, y = (dim[0] + int(pt[0]), dim[1] + int(pt[1]))
    pyautogui.click(x, y)
    time.sleep(pause)


def snapshot_age():
    try:
        return time.time() - os.path.getmtime(SNAPSHOT)
    except OSError:
        return 999.0


def read_tasks():
    """The local player's task list, or None if the game is not publishing one.

    None covers two distinct situations the caller must not confuse: no panel
    is open yet, and the game is paused or unfocused.
    """
    age = snapshot_age()
    if age > 5.0:
        return None, f"the game is not publishing (snapshot is {age:.0f}s old)"
    try:
        data = utility.getGameData()
    except Exception as exc:
        return None, f"no snapshot yet ({exc})"
    if not data or not data.get("tasks"):
        return None, "the plugin has not published a task list yet"
    steps = data.get("task_steps") or []
    out = []
    for i, name in enumerate(data["tasks"]):
        step = steps[i] if i < len(steps) else "?"
        loc = (data.get("task_locations") or ["?"] * (i + 1))[i]
        out.append((name, step, loc))
    return out, None


def wait_for_tasks(timeout=30.0):
    """Wait for a fresh snapshot, refocusing the game whenever it goes stale."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        poke.focus_game()
        tasks, err = read_tasks()
        if tasks:
            return tasks
        time.sleep(0.8)
    return None


def in_round():
    return snapshot_age() < FRESH


def leave_round(dim):
    """Back to the main menu, from wherever we are.

    The game has to actually be back at the menu before the next round is
    started, or the clicks land on a round that is still running and the game
    ends up in a state where nothing responds.
    """
    if not in_round():
        return
    poke.focus_game()
    click(dim, IN_GAME_GEAR, pause=1.5)
    click(dim, GEAR_LEAVE, pause=4.0)
    time.sleep(1.0)
    try:
        pyautogui.press("enter")
    except Exception:
        pass
    time.sleep(4.0)
    # The main menu does not publish a snapshot, so a stale snapshot is how a
    # successful return looks. Waiting for it is how we know we are back.
    for _ in range(20):
        poke.focus_game()
        if snapshot_age() > 5.0:
            return
        time.sleep(0.5)


def start_round(dim):
    """Main menu -> Practice -> The Skeld."""
    poke.focus_game()
    click(dim, MENU_PLAY, pause=3.0)
    click(dim, MENU_PRACTICE, pause=2.5)
    click(dim, MENU_SKELD, pause=6.0)


def current_tasks():
    """The tasks in the round that is running right now."""
    tasks, err = read_tasks()
    return tasks or []


def get_round(want, rounds=10, any_of=True):
    """Reroll until a round holds at least one of the wanted tasks.

    Returns 0 when a suitable round is reached, 1 otherwise. The round is left
    running, so the caller can walk to the panels.
    """
    dim = poke.task_utility.get_dimensions()
    if not dim:
        print("   game window not found")
        return 1
    for attempt in range(1, rounds + 1):
        if attempt > 1 or in_round():
            leave_round(dim)
        start_round(dim)
        poke.focus_game()
        tasks = wait_for_tasks()
        if tasks is None:
            print(f"   round {attempt}: no fresh task list (is the game focused?)")
            continue
        names = [t[0] for t in tasks]
        print(f"   round {attempt}: " + ", ".join(f"{n} {s}" for n, s, _ in tasks))
        if not want:
            # no filter: any round will do
            return 0
        hit = [w for w in want if w in names]
        if hit:
            print(f"   -> have: {', '.join(hit)}")
            return 0
    print(f"   gave up after {rounds} round(s)")
    return 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--want", nargs="*", default=[])
    ap.add_argument("--rounds", type=int, default=1)
    ap.add_argument("--any", action="store_true",
                    help="stop at the first round holding AT LEAST ONE wanted task")
    args = ap.parse_args()

    poke.focus_game()
    dim = poke.task_utility.get_dimensions()
    if not dim:
        print("game window not found")
        return 2

    for attempt in range(1, args.rounds + 1):
        if attempt > 1 or in_round():
            leave_round(dim)
        start_round(dim)
        poke.focus_game()
        tasks = wait_for_tasks()
        if tasks is None:
            print(f"round {attempt}: no fresh task list (is the game focused?)")
            continue
        names = [t[0] for t in tasks]
        print(f"round {attempt}: " + ", ".join(f"{n} {s}" for n, s, _ in tasks))
        if args.want:
            hit = [w for w in args.want if w in names]
            missing = [w for w in args.want if w not in names]
            if (args.any and hit) or (not args.any and not missing):
                print("  -> have " + ("some of" if args.any else "everything")
                      + " what was wanted: " + ", ".join(hit))
                return 0
            print(f"  -> still missing: {', '.join(missing)}")
    if args.want:
        print(f"gave up after {args.rounds} round(s)")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
