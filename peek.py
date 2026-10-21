r"""Screenshot the Among Us client (or the whole desktop) for looking at.

    .venv\Scripts\python.exe peek.py shot.png            # the game window
    .venv\Scripts\python.exe peek.py --desktop shot.png # everything
    .venv\Scripts\python.exe peek.py --wait 20          # just wait N seconds

Purely a development aid: it exists so a human (or the agent) can see what the
game is showing while a solver is being written. It sends nothing anywhere and
is not part of the bot.
"""
import argparse
import sys
import time

sys.path.insert(0, "task-solvers")
import task_utility  # noqa: E402
import poke  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out", nargs="?", default="peek.png")
    ap.add_argument("--desktop", action="store_true",
                    help="whole desktop rather than the game client area")
    ap.add_argument("--wait", type=float, default=0.0)
    ap.add_argument("--region", default=None,
                    help="x,y,w,h in CLIENT pixels, e.g. 0,0,1920,1080")
    args = ap.parse_args()

    if args.wait:
        time.sleep(args.wait)

    if not args.desktop:
        poke.focus_game()
    if args.desktop:
        import pyautogui
        img = pyautogui.screenshot()
    else:
        dim = task_utility.get_dimensions()
        if not dim:
            print("game window not found")
            return 2
        if args.region:
            x, y, w, h = [int(v) for v in args.region.split(",")]
            region = (dim[0] + x, dim[1] + y, w, h)
        else:
            region = (dim[0], dim[1], dim[2], dim[3])
        import pyautogui
        img = pyautogui.screenshot(region=region)
        print(f"client origin ({dim[0]},{dim[1]}) size {dim[2]}x{dim[3]}")

    img.save(args.out)
    print(f"wrote {args.out} ({img.width}x{img.height})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
