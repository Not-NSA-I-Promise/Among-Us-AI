r"""One process that owns the virtual gamepad, the game, and the test runs.

Why this exists
---------------
Among Us enumerates its input devices at startup and does not hot-plug them,
and ViGEmBus leaves a zombie "Xbox 360 Controller for Windows" behind every
time a process that held a virtual pad dies. Both facts are in bootstrap.py
and both bite hard:

  * A pad created after the game is running is invisible to the game, so the
    player never moves and every walk silently does nothing.
  * Several pads at once make the game bind to a dead one, and again nothing
    moves - with no error anywhere, which is what makes it so confusing.

So the only reliable order is: purge the zombies, create the pad, THEN launch
the game, and keep everything in one process so the same pad is held by the
process that drives the bot. Running a task from a fresh python process while
the game is already up is exactly the broken configuration.

Usage
-----
    .venv\Scripts\python.exe lab.py --want "Start Reactor" "Calibrate Distributor"
    .venv\Scripts\python.exe lab.py --want "Inspect Sample" --keep-game

`--keep-game` leaves the game running instead of restarting it, which is only
safe if this process is the one that launched it - otherwise the pad is not
the one the game knows about.
"""
import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "task-solvers"))

GAMEDIR = r"C:\Games\Among Us"


def purge_zombie_pads(verbose=True):
    """Remove every leftover virtual pad. See bootstrap.py for why."""
    import subprocess
    ps = ("Get-PnpDevice -ErrorAction SilentlyContinue | "
          "Where-Object { $_.InstanceId -like '*VID_045E&PID_028E*' } | "
          "ForEach-Object { $_.InstanceId }")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                             capture_output=True, text=True, timeout=90)
    except Exception:
        return
    ids = [ln.strip() for ln in (out.stdout or "").splitlines() if ln.strip()]
    if verbose:
        print(f"  {len(ids)} leftover virtual pad device(s)")
    for dev in ids:
        try:
            subprocess.run(["pnputil", "/remove-device", dev],
                           capture_output=True, text=True, timeout=30)
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--want", nargs="*", default=[])
    ap.add_argument("--rounds", type=int, default=10)
    ap.add_argument("--keep-game", action="store_true")
    ap.add_argument("--no-solve", action="store_true",
                    help="open the panel but do not run the solver")
    ap.add_argument("--watch", type=float, default=0.0,
                    help="open the panel and dump the hot state for N seconds")
    ap.add_argument("--all", action="store_true",
                    help="solve EVERY task the round holds, not just the wanted ones")
    ap.add_argument("--wait", type=float, default=0.0,
                    help="seconds to WAIT in the round before solving, so the "
                         "task list can be set up by hand")
    args = ap.parse_args()

    print("=== lab ===")

    # 0. The game has to be down before the plugin can be replaced - BepInEx
    # holds the DLL open for the life of the process - and the plugin has to be
    # the current build, or the lab is testing yesterday's code. The game loads
    # it at startup, so it has to be in place before the game is launched.
    import shutil
    import subprocess
    plugin = os.path.join(GAMEDIR, "BepInEx", "plugins", "AmongUsAI.dll")
    src = os.path.join(HERE, "plugin", "bin", "Release", "AmongUsAI.dll")
    project = os.path.join(HERE, "plugin", "AmongUsAI.csproj")
    if not os.path.exists(src) and os.path.exists(project):
        print("0. building the plugin")
        import subprocess
        subprocess.run(["dotnet", "build", "-c", "Release", "-v", "quiet",
                        "--nologo", project], cwd=HERE)
    if not args.keep_game:
        print("0. stopping the game so the plugin can be replaced")
        subprocess.run(["taskkill", "/F", "/IM", "Among Us.exe"],
                       capture_output=True)
        time.sleep(4.0)
    if os.path.exists(src) and os.path.exists(plugin):
        if os.path.getmtime(src) > os.path.getmtime(plugin):
            print("0. deploying the freshly built plugin")
            shutil.copyfile(src, plugin)
        else:
            print("0. plugin is up to date")
    else:
        print("0. NOTE: could not compare the plugin build")

    # 1. Pads first. A pad created after the game starts is invisible to it.
    print("1. purging zombie virtual gamepads")
    purge_zombie_pads()

    print("2. creating THE virtual gamepad (this process holds it)")
    import utility  # noqa: F401  - import side effect creates and holds the pad
    try:
        import vgamepad as vg
        vg.VX360Gamepad().update()
    except Exception:
        pass
    time.sleep(1.0)

    # 3. Then the game, so it enumerates OUR pad.
    if args.keep_game:
        print("3. keeping the running game")
    else:
        print("3. launching the game so it enumerates our pad")
        subprocess.Popen([os.path.join(GAMEDIR, "Among Us.exe")], cwd=GAMEDIR)
        # The game needs a while to come up and enumerate devices.
        time.sleep(28.0)

    import poke
    for _ in range(60):
        if poke.focus_game(topmost=True):
            break
        time.sleep(1.0)

    import practice

    # 4/5. Reroll until every wanted task has been seen and attempted. A
    # Skeld practice round deals four tasks out of twenty-odd, so the three
    # wanted ones rarely turn up together.
    import do_task
    import roleplay
    import solver

    wanted = list(args.want)
    if args.all:
        wanted = []
    done = set()
    failures = 0
    for attempt in range(1, args.rounds + 1):
        remaining = [t for t in wanted if t not in done]
        if args.all:
            remaining = []
        if not args.all and not remaining:
            break
        print(f"\n--- round {attempt}: still need {', '.join(remaining)}"
              if remaining else f"\n--- round {attempt}: every task")
        if args.all:
            # Do NOT reroll: the round that is already running is the one the
            # user set up, with the tasks they enabled. Only start one if
            # there is not a round yet.
            if not practice.in_round():
                practice.start_round(poke.task_utility.get_dimensions())
                practice.wait_for_tasks()
            if args.wait:
                # The task list is set up by hand in the lobby, and changing it
                # re-deals the round. So the bot waits, and says what the list
                # is doing, rather than rerolling under the user's hands.
                print(f"   waiting {args.wait:.0f}s for the task list to be set "
                      f"up...")
                until = time.time() + args.wait
                shown = None
                while time.time() < until:
                    poke.focus_game()
                    try:
                        names = [n for n, _, _ in practice.current_tasks()]
                    except Exception:
                        names = []
                    if names and names != shown:
                        shown = names
                        print(f"   {len(names)} task(s): {', '.join(names)}")
                    time.sleep(2.0)
        elif practice.get_round(remaining, rounds=1, any_of=True) != 0:
            continue
        try:
            names = [n for n, _, _ in practice.current_tasks()]
        except Exception:
            names = []
        targets = names if args.all else [t for t in remaining if t in names]
        for task in targets:
            print(f"\n=== {task} ===")
            if not do_task.walk_to_panel(task):
                print(f"  {task}: could not get to the panel")
                failures += 1
                continue
            # The panel is NOT opened here: the solver opens it, exactly as the
            # real bot does. Opening it here as well would close it again -
            # USE is a toggle - and the solver would work on a closed panel.
            if args.no_solve:
                do_task.open_panel_original_way()
                print(f"  {task}: panel open, not solving")
                done.add(task)
                continue
            if args.watch:
                import botlink
                t_end = time.time() + args.watch
                prev = None
                while time.time() < t_end:
                    hot = botlink.read_minigame_hot()
                    if hot and hot != prev:
                        print(f"  {time.time() - t_end:7.2f}s  {hot}")
                        prev = hot
                    time.sleep(0.1)
                done.add(task)
                continue
            t0 = time.time()
            rc = solver.solve_task(task_name=task)
            print(f"  {task}: solver returned {rc} after {time.time() - t0:.1f}s")
            try:
                prog = dict((n, (d, m)) for n, d, m in roleplay.task_progress())
                print(f"  {task}: task bar now {prog.get(task)}")
            except Exception:
                pass
            done.add(task)
            if rc != 0:
                failures += 1
        if args.all:
            break

    missing = [t for t in wanted if t not in done]
    if missing:
        print(f"\nnever appeared: {', '.join(missing)}")
    print(f"\n=== lab done ({failures} failure(s)) ===")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
