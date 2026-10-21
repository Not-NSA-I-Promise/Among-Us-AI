r"""Watch the open task panel's published state change over a few seconds.

The plugin publishes every member of whatever minigame is open, so the fastest
way to learn a task's protocol is to watch what the game itself does to it: the
sequence it queues, which light changes colour, and when.

    .venv\Scripts\python.exe watch.py 8
    .venv\Scripts\python.exe watch.py 8 --grep "operations|LeftSide|LeftLights"

Prints only the fields that actually changed, with a timestamp, so a flash
sequence reads as a list of events rather than a wall of identical lines.
Development aid; the bot does not use it.
"""
import argparse
import re
import sys
import time

GAME_DIR = r"C:\Games\Among Us"
CONTROLS = GAME_DIR + r"\minigameControls.txt"
STATE = GAME_DIR + r"\minigameState.txt"


def read_controls():
    try:
        with open(CONTROLS) as f:
            lines = f.read().splitlines()
    except OSError:
        return {}
    out = {}
    for ln in lines:
        if not ln or ln.startswith("#") or ln.startswith("task "):
            continue
        out[ln] = True
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("seconds", nargs="?", type=float, default=8.0)
    ap.add_argument("--grep", default=None,
                    help="only show lines matching this regex")
    ap.add_argument("--interval", type=float, default=0.05)
    args = ap.parse_args()

    keep = re.compile(args.grep) if args.grep else None
    start = time.time()
    prev = {}
    last_change = start
    while time.time() - start < args.seconds:
        cur = read_controls()
        if keep:
            cur = {k: v for k, v in cur.items() if keep.search(k)}
        gone = [k for k in prev if k not in cur]
        for k in gone:
            print(f"{time.time() - start:6.2f}s  -  {k}")
        for k, _ in sorted(cur.items()):
            if k not in prev:
                print(f"{time.time() - start:6.2f}s  +  {k}")
                last_change = time.time()
        if cur != prev:
            last_change = time.time()
        prev = cur
        time.sleep(args.interval)
    print(f"(no change for {time.time() - last_change:.1f}s)")


if __name__ == "__main__":
    sys.exit(main())
