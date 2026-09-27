"""Two bugs that made the bot lie or die, and which must never come back.

1. `kill` reported success from a button press. As a Viper, whose kill goes
   THROUGH a vent, pressing USE on the ground does nothing at all - and the
   harness still logged "killed". A press is an attempt; only a new body is a
   kill.

2. `focus()` let a pywintypes.error escape. "SetForegroundWindow failed" happens
   whenever the window already has focus, so the bot crashed at startup and
   exited with code 1 while the game was sitting right there.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(os.getcwd(), "task-solvers"))

import agent           # noqa: E402
import roleplay        # noqa: E402
import utility         # noqa: E402

fails = []


def check(name, cond, detail=""):
    if cond:
        print("  PASS", name)
    else:
        print("  FAIL", name, "<-", detail)
        fails.append(name)


def _raises(fn):
    """Return the exception fn raised, or None."""
    try:
        fn()
    except Exception as exc:
        return exc
    return None


# ---------------------------------------------------------------- kill
STATE = {
    "imp": True,
    "dead": False,
    "bodies": 0,
    "role": "Impostor",
    "in_vent": "0",
    "data": {},
}

utility.isImpostor = lambda: STATE["imp"]
utility.isDead = lambda: STATE["dead"]
utility.get_real_dist = lambda G, p: (
    0.0 if p == (12.0, 10.0) else 99.0)


def _make_data():
    """A fresh snapshot: PINK alive, only BLUE already dead."""
    return {
        "color": "RED",
        "position": (10.0, 10.0),
        "map_id": "SHIP",
        "playersDead": {"RED": False, "PINK": False, "BLUE": True},
        "nearbyPlayers": {"PINK": (12.0, 10.0)},
    }


def _reset():
    """A new scenario: PINK alive again, nobody dead but BLUE.

    This must be separate from the getGameData stub. When the getter rebuilt the
    data on every call, every body count reset the death it was meant to detect,
    so a real kill could never be confirmed - which is exactly the bug this test
    exists to catch, reintroduced by the stub.
    """
    STATE["data"] = _make_data()
    STATE["bodies"] = 0


_reset()

# the getter returns the CURRENT state, like the real file does
utility.getGameData = lambda: STATE["data"]
utility.load_G = lambda name: object()
roleplay.walk_to = lambda G, x, y: True
roleplay.creep_to = lambda *a, **k: True


def _fake_press_use(*a, **k):
    """Simulate the game. It only kills when STATE says the press connected -
    which is the whole point: a press is not a kill."""
    STATE["pressed"] = True
    if STATE.get("use_kills"):
        # the game marks the victim dead, which is the ONLY evidence of a kill
        STATE["data"]["playersDead"]["PINK"] = True
        STATE["bodies"] += 1


roleplay.press_use = _fake_press_use
roleplay.time = type("t", (), {"sleep": staticmethod(lambda s: None)})()

import botlink           # noqa: E402
botlink.get_role = lambda *a, **k: STATE["role"]
botlink.read_ability = lambda *a, **k: {"invent": STATE["in_vent"]}
botlink.read_kill_presence = lambda *a, **k: {
    f"body{i}": True for i in range(STATE["bodies"])}

print()
print("=== a kill is only reported when a new body actually appears ===")
# the press misses: the game does nothing
_reset()
STATE.update(imp=True, dead=False, role="Impostor", in_vent="0", use_kills=False)
STATE.pop("pressed", None)
out = roleplay.kill_nearest(None)
check("USE was actually pressed", STATE.get("pressed") is True)
check("but no kill is claimed when no body appeared", out is None, out)

# the press connects: the game creates a body
STATE["use_kills"] = True
out = roleplay.kill_nearest(None)
check("a real kill is reported", out == "killed PINK", out)

print()
print("=== a Viper must be inside a vent, or the harness refuses instead ===")
_reset()
STATE.update(imp=True, dead=False, role="Viper", in_vent="0", use_kills=True)
STATE.pop("pressed", None)
out = roleplay.kill_nearest(None)
check("a Viper on the ground does not 'kill'", out is None, out)
check("no USE was pressed on the ground", STATE.get("pressed") is None)

STATE["in_vent"] = "1"
STATE["bodies"] = 2
out = roleplay.kill_nearest(None)
check("a Viper inside a vent kills", out == "killed PINK", out)

print()
print("=== the model is told the kill failed, not that it succeeded ===")
STATE.update(imp=True, dead=False, bodies=1, role="Impostor", in_vent="0",
             use_kills=False)
try:
    agent.kill()
    check("agent.kill raises when nothing died", False, "it reported success")
except agent.ActionError as exc:
    check("agent.kill raises when nothing died", True)
    check("and says nothing was killed", "nothing was killed" in str(exc), exc)

print()
print("=== a dead or crew player cannot kill at all ===")
STATE.update(dead=True, imp=True)
check("a dead player does not kill", roleplay.kill_nearest(None) is None)
STATE.update(dead=False, imp=False)
check("a crewmate does not kill", roleplay.kill_nearest(None) is None)

print()
print("=== nobody in range is a refusal, not a cross-map hike ===")
_reset()
STATE.update(imp=True, dead=False, use_kills=True)
# PINK is alive and present, but far away
STATE["data"]["nearbyPlayers"]["PINK"] = (900.0, 900.0)
check("a player too far away is not killed", roleplay.kill_nearest(None) is None)
STATE["data"]["nearbyPlayers"] = {}
check("with nobody in range there is no kill", roleplay.kill_nearest(None) is None)


# ---------------------------------------------------------------- focus
print()
print("=== focus() must never kill the bot ===")
import win32gui          # noqa: E402
import pywintypes        # noqa: E402


def _boom(*a, **k):
    raise pywintypes.error(0, "SetForegroundWindow",
                           "No error message is available")


real_find, real_fore, real_iconic = (
    win32gui.FindWindow, win32gui.SetForegroundWindow, win32gui.IsIconic)
try:
    win32gui.FindWindow = lambda cls, title: 0x1234
    win32gui.SetForegroundWindow = _boom
    win32gui.IsIconic = lambda h: False

    try:
        ok = utility.focus()
        check("a SetForegroundWindow failure is caught, not raised", True)
        check("and it reports it did not focus, without dying", ok is False)
    except Exception as exc:
        check("a SetForegroundWindow failure is caught, not raised", False,
              f"{type(exc).__name__}: {exc}")

    win32gui.SetForegroundWindow = lambda h: None      # a normal, working focus
    check("a normal focus still works", utility.focus() is True)

    win32gui.SetForegroundWindow = _boom
    win32gui.FindWindow = lambda cls, title: 0
    check("a missing window is handled too", utility.focus() is False)
finally:
    win32gui.FindWindow, win32gui.SetForegroundWindow, win32gui.IsIconic = (
        real_find, real_fore, real_iconic)

print()
print("=== reading the snapshot survives the game writing it ===")
# The plugin rewrites sendData.txt on every tick with File.WriteAllText, which
# truncates first. On Windows, opening a file another process is in the middle of
# writing raises PermissionError, and a half-written file is short. Both killed a
# solver outright - "Clear Asteroids" died with PermissionError on sendData.txt
# and the whole task was abandoned mid-run.
import importlib.util as _ilu
import tempfile

sys.path.insert(0, os.path.join(ROOT, "task-solvers"))
_tu_spec = _ilu.spec_from_file_location(
    "tu_test", os.path.join(ROOT, "task-solvers", "task_utility.py"))

GOOD = "".join(f"line {i}\n" for i in range(15))
SHORT = "line 0\nline 1\n"

_tmpdir = tempfile.mkdtemp()
_good = os.path.join(_tmpdir, "good.txt")
_short = os.path.join(_tmpdir, "short.txt")
open(_good, "w", encoding="utf-8").write(GOOD)
open(_short, "w", encoding="utf-8").write(SHORT)


def _load():
    mod = _ilu.module_from_spec(_tu_spec)
    _tu_spec.loader.exec_module(mod)
    return mod


tu = _load()
check("a complete snapshot is read straight through",
      len(tu.read_snapshot_lines(_good)) == 15)
check("a truncated snapshot raises a clear error, not a bare OSError",
      _raises(lambda: tu.read_snapshot_lines(_short, tries=2, pause=0.01)) is not None
      and "too short" in str(_raises(lambda: tu.read_snapshot_lines(
          _short, tries=2, pause=0.01)) or ""),
      _raises(lambda: tu.read_snapshot_lines(_short, tries=2, pause=0.01)))


def _permission_error(path, tries=8, pause=0.15):
    import builtins
    real_open = builtins.open
    state = {"n": 0}

    def flaky(*a, **k):
        if str(path).endswith("good.txt"):
            state["n"] += 1
            if state["n"] <= 3:
                raise PermissionError(13, "used by another process")
        return real_open(*a, **k)

    builtins.open = flaky
    try:
        return tu.read_snapshot_lines(path, tries=tries, pause=0.01)
    finally:
        builtins.open = real_open


lines = _permission_error(_good)
check("a PermissionError from the game's write is retried, not fatal",
      lines is not None and len(lines) == 15, lines)

print()
if fails:
    print("FAILURES:", ", ".join(fails))
    raise SystemExit(1)
print("all checks passed: a kill needs a body, focus cannot crash the bot, "
      "and the snapshot read survives the game writing it")
