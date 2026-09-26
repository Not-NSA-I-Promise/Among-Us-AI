"""Bootstrap for Among-Us-AI.

Two hard-won requirements, both proven by testing on this machine:

1. ViGEmBus leaves a zombie "Xbox 360 Controller for Windows" device behind
   every time a vgamepad process dies. Several zombies present at once make
   Among Us bind to a dead pad and silently ignore all controller input, so we
   purge them before creating our own.

2. Among Us enumerates input devices at startup and does not hot-plug. A virtual
   pad created *after* the game is running is invisible to it. Since utility.py
   creates the pad at import time, the pad has to be created before the game is
   launched - and it has to be the same process that later drives the bot, or
   two pads exist and the game may pick the idle one.

So the order here is: purge zombies -> import utility (creates and holds THE
pad) -> launch the game -> run the bot in this same process.
"""
import os
import subprocess
import sys
import time

GAMEDIR = r"C:\Games\Among Us"
GAME = os.path.join(GAMEDIR, "Among Us.exe")
SEND = os.path.join(GAMEDIR, "sendData.txt")
def purge_zombie_pads(verbose=True):
    """Remove every leftover virtual pad.

    Device ids are not predictable - a run of several sessions had produced 46
    entries with ids like USB\\VID_045E&PID_028E&IG_01\\2&DEE0F28&9&01 as well
    as the plain \\01..\\04 forms, so this enumerates rather than matching a
    hardcoded list that only caught a handful.
    """
    ps = ("Get-PnpDevice -ErrorAction SilentlyContinue | "
          "Where-Object { $_.InstanceId -like '*VID_045E&PID_028E*' } | "
          "ForEach-Object { $_.InstanceId }")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                             capture_output=True, text=True, timeout=60)
    except Exception:
        return
    ids = [ln.strip() for ln in (out.stdout or "").splitlines() if ln.strip()]
    if verbose:
        print(f"  {len(ids)} leftover virtual pad device(s)")
    for dev in ids:
        try:
            subprocess.run(["pnputil", "/remove-device", dev],
                           capture_output=True, text=True, timeout=20)
        except Exception:
            pass


def game_running():
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Among Us.exe"],
                         capture_output=True, text=True)
    return "Among Us.exe" in (out.stdout or "")


def launch_game():
    subprocess.Popen([GAME], cwd=GAMEDIR)


def wait_for_match(timeout=600):
    """Wait until the plugin is writing a live snapshot, i.e. we are in a game."""
    print("  waiting for a match to start (start one in the game)...")
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if os.path.exists(SEND) and (time.time() - os.path.getmtime(SEND)) < 5:
                print("  match is live")
                return True
        except OSError:
            pass
        time.sleep(2)
    return False


def main():
    print("=== Among-Us-AI bootstrap ===\n")

    print("1. purging zombie virtual gamepads")
    purge_zombie_pads()

    # The pad must be created BEFORE the game starts, and must be the only one.
    print("\n2. creating the virtual gamepad (must happen before the game launches)")
    import utility  # noqa: F401  - import side effect creates + holds the pad
    print("   virtual pad held by this process")
    try:
        import vgamepad as vg
        vg.VX360Gamepad().update()  # touch it once so the device is definitely registered
    except Exception:
        pass
    time.sleep(1.0)

    print("\n3. game")
    if game_running():
        print("   Among Us is ALREADY running.")
        print("   It enumerated its input devices before our pad existed, so it will")
        print("   ignore the gamepad and the player will not move.")
        if input("   Kill and relaunch it now? [Y/n] ").strip().lower() != "n":
            subprocess.run(["taskkill", "/F", "/IM", "Among Us.exe"], capture_output=True)
            time.sleep(3)
            launch_game()
    else:
        launch_game()
    print("   launched" if not game_running() or True else "")

    if not wait_for_match():
        print("\nNo match started within the timeout. Start a match and rerun, or")
        print("run this script again once you are in a game.")
        return 1

    print("\n4. starting the bot (same process, so it owns the same pad)")
    import main as bot
    return 0


if __name__ == "__main__":
    sys.exit(main())
