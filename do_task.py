r"""Do one task, the way the 2023 original did it.

Why this exists
---------------
The 2023 originals opened their own panels: the state machine walked to the
panel and then the solver called `click_use()` - a MOUSE CLICK on the on-screen
USE button, bottom right.

When the model took over from the state machine, that convention was inverted:
the harness now opens the panel by pressing the gamepad's A button
(`roleplay.press_use`) and the solvers no longer click. A live run showed that
inversion failing at the door:

    Calibrate Distributor: the game says no panel is open, so nothing was clicked
    Start Reactor: the game says no panel is open, so nothing was clicked

Gamepad-A proximity opening is evidently not reliable here; the mouse click on
the on-screen button is what demonstrably worked.

This script restores the original behaviour WITHOUT changing any solver file. It
walks to the panel, opens it the original way, confirms from the game's own state
that it is actually open, runs the task's existing solver untouched, and then
confirms from the task bar whether the task actually completed.

Nothing else in the harness is modified by running it.

Usage - use the VENV, not the bare `python`:

    .venv\Scripts\python.exe do_task.py "Inspect Sample" --verbose
    .venv\Scripts\python.exe do_task.py "Start Reactor"
    .venv\Scripts\python.exe do_task.py "Inspect Sample" --no-solver

On this machine `python` is Python 2.7 (C:\Python27\python.exe), which cannot
parse this file at all. The project uses the venv everywhere else too -
start_bot.bat calls .venv\Scripts\python.exe - so use that.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, os.path.join(os.getcwd(), "task-solvers"))

import botlink        # noqa: E402
import roleplay       # noqa: E402
import task_utility   # noqa: E402
import utility        # noqa: E402

VERBOSE = False


def say(*a):
    print(*a, flush=True)


def minigame():
    try:
        return botlink.read_minigame() or {}
    except Exception as exc:
        return {"error": str(exc)}


def progress_of(task):
    try:
        for n, done, total, room in roleplay.task_progress():
            if n == task:
                return done, total
    except Exception:
        pass
    return None, None


def walk_to_panel(task, budget=45.0):
    """Walk to the task's live panel position. Bounded, never spins."""
    data = utility.getGameData()
    room = data.get("room")
    target_room = ""
    names = data.get("tasks") or []
    locs = data.get("task_locations") or []
    for i, n in enumerate(names):
        if n == task and i < len(locs):
            target_room = locs[i].split("|")[0].strip()
    say(f"  you are in {room}; {task} is at {target_room or 'an unknown room'}")

    route = roleplay.task_route(task, refresh=True)
    pos = route[0] if route else None
    if not pos:
        import agent
        pos = agent._panel_position(task)
    if not pos:
        say("  no position is known for this panel")
        return False
    if VERBOSE:
        say(f"  walking to {pos}")

    G = utility.load_G(data["map_id"])
    # Bounded: a walk that cannot arrive must give up rather than burn CPU
    # forever, which is what happened when this was tried ad hoc.
    t0 = time.time()
    if not roleplay.walk_to(G, pos[0], pos[1]):
        say("  walk_to reported failure")
    roleplay.creep_to(G, pos[0], pos[1], tolerance=0.45, timeout=3.0)
    took = time.time() - t0
    now = (utility.getGameData() or {}).get("room")
    say(f"  walked for {took:.1f}s; now in {now}")
    return True


def open_panel_original_way(budget=8.0):
    """Open with click_use(), the original's method: a mouse click on the
    on-screen USE button. Verified against Minigame.Instance, not assumed."""
    if minigame().get("open"):
        say("  a panel is already open")
        return True
    deadline = time.time() + budget
    attempts = 0
    while time.time() < deadline:
        attempts += 1
        if VERBOSE:
            say(f"  click_use() attempt {attempts}")
        task_utility.click_use()
        time.sleep(0.8)
        st = minigame()
        if st.get("open"):
            say(f"  panel open after {attempts} click(s): {st.get('task')}")
            return True
    say(f"  the panel never opened after {attempts} click(s); "
        f"the game still reports no minigame")
    return False


def run_solver(task, budget=180.0):
    import solver
    say(f"  running the untouched {task}.py")
    t0 = time.time()
    try:
        rc = solver.solve_task(task_name=task)
    except Exception as exc:
        say(f"  the solver raised {type(exc).__name__}: {exc}")
        return 99
    say(f"  solver returned {rc} after {time.time() - t0:.1f}s")
    return rc


def main():
    global VERBOSE
    ap = argparse.ArgumentParser()
    ap.add_argument("task")
    ap.add_argument("--verbose", "-v", action="store_true")
    ap.add_argument("--no-solver", action="store_true",
                    help="just open the panel and stop")
    args = ap.parse_args()
    VERBOSE = args.verbose
    task = args.task.strip()

    say(f"=== {task} ===")
    say(f"  task bar: {progress_of(task)[0]}/{progress_of(task)[1]}")
    say(f"  minigame before: {minigame()}")

    if not walk_to_panel(task):
        return 2
    if not open_panel_original_way():
        return 3

    if args.no_solver:
        return 0

    before = progress_of(task)[0]
    run_solver(task)
    after = progress_of(task)[0]

    say("")
    say(f"  task bar before: {before}   after: {after}")
    say(f"  minigame after: {minigame()}")
    total = progress_of(task)[1]
    if total and after is not None and after >= total:
        say(f"  VERIFIED: the game reports {task} complete ({after}/{total})")
        return 0
    say(f"  NOT complete. The game reports {after}/{total}.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
