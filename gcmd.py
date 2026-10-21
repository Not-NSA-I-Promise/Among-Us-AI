r"""Send one command to the game and print the game's own answer.

    .venv\Scripts\python.exe cmd.py meetingtime
    .venv\Scripts\python.exe cmd.py minigamecall HitButton 5
    .venv\Scripts\python.exe cmd.py clicksabotage reactor

This is the same control channel the bot uses, exposed as a script so the game
can be driven by hand while a solver is being worked out. The reply is the
game's, not the write's: the plugin answers every command in cmdResult.txt, so
"ok" means the game did the thing and "fail ..." says why it did not.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import botlink  # noqa: E402


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cmd = " ".join(sys.argv[1:])
    try:
        ok = botlink.send_cmd(cmd, timeout=3.0)
    except botlink.CommandFailed as exc:
        print(f"FAIL {cmd!r}: {exc.reason}")
        return 1
    except Exception as exc:
        print(f"ERROR {cmd!r}: {type(exc).__name__}: {exc}")
        return 1
    detail = botlink.last_result()
    if ok:
        print(f"OK   {cmd!r} -> {detail}")
        return 0
    print(f"NO REPLY {cmd!r} (last result {detail!r})")
    return 1


if __name__ == "__main__":
    sys.exit(main())
