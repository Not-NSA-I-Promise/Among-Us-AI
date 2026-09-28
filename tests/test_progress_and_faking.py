"""Multi-stage progress, faking rules, and having a reason to act.

The live log: Divert Power executed perfectly, and the harness reported
"attempted ... still outstanding, so it was NOT completed", so the model walked to
Communications and then had nothing to do there. The cause was that completion
was checked by asking whether the task NAME was still in the list, and the list
keeps a two-stage task until its LAST stage.
"""
import _path  # noqa: F401
import os
import sys

import agent
import agent_loop
import botlink
import roleplay
import utility

failures = []


def check(label, cond, detail=""):
    print("  {} {}{}".format("PASS" if cond else "FAIL", label,
                             ("  <- " + str(detail)[:160]) if (detail and not cond) else ""))
    if not cond:
        failures.append(label)


# Divert Power 0/2 in Electrical is the live shape; Electrical and Communications
TASKS = ["Fix Wiring", "Divert Power", "Upload Data"]
LOCS = ["Storage", "Electrical", "Communications"]
STEPS = ["0/3", "0/2", "0/2"]


def set_state(imp=False, room="Electrical", steps=None, dead=False):
    steps = steps or list(STEPS)
    utility.getGameData = lambda: {
        "map_id": "Ship", "room": room, "color": "RED", "inMeeting": False,
        "playersDead": {"RED": dead, "BLUE": False}, "tasks": list(TASKS),
        "task_locations": list(LOCS), "task_steps": list(steps),
        "position": (0, 0), "lights": "0", "nearbyPlayers": []}
    utility.isImpostor = lambda: imp
    utility.isDead = lambda: dead
    utility.in_meeting = lambda: False
    utility.get_fellow_imposters = lambda: []
    utility.get_killCD = lambda: 0.0
    utility.is_urgent_task = lambda *a, **k: None
    utility.get_chat_messages = lambda: []
    utility.MAP = "SHIP"
    roleplay.TASK_ROUTES = None
    botlink.get_role = lambda: "Impostor" if imp else "Crewmate"
    botlink.read_ability = lambda: {
        "invent": "0", "isdead": "1" if dead else "0",
        "isimpostor": "1" if imp else "0", "cankill": "1",
        "canvent": "1" if imp else "0", "abilitycount": "0"}


print("=== 1. stage progress is read, not list membership ===")
set_state()
prog = roleplay.task_progress()
by_name = {n: (d, t) for n, d, t, _r in prog}
check("Divert Power is 0/2", by_name.get("Divert Power") == (0, 2), by_name)
check("Fix Wiring is 0/3", by_name.get("Fix Wiring") == (0, 3), by_name)
check("a 0/2 task is NOT complete", roleplay.task_is_complete("Divert Power") is False)
set_state(steps=["0/3", "2/2", "0/2"])
check("a 2/2 task IS complete even though the name may still be listed",
      roleplay.task_is_complete("Divert Power") is True,
      roleplay.task_progress())
set_state(steps=["0/3", "1/2", "0/2"])
check("a 1/2 task is not complete", roleplay.task_is_complete("Divert Power") is False)

print()
print("=== 2. the model is told the progress and the task bar ===")
set_state(steps=["0/3", "1/2", "0/2"])
st = agent._brief_state()
check("per-stage progress is shown", "Divert Power 1/2" in st, st)
check("not-started tasks show their room", "Upload Data 0/2 not started" in st, st)
check("the overall bar is shown", "task bar" in st, st)
check("a partly done task does NOT name a guessed next room",
      "MedBay" not in st, st)
check("and says the next part is elsewhere", "another panel" in st, st)

print()
print("=== 3. an impostor is told what it has already faked ===")
set_state(imp=True, room="Electrical")
agent._FAKED_ONCE.clear()
agent._FAKED_ONCE.add("Divert Power")
st = agent._brief_state()
check("already-faked tasks are listed", "already faked" in st, st)
check("and named", "Divert Power" in st, st)

print()
print("=== 4. faking a task twice is refused ===")
agent._FAKED_ONCE.clear()
seen = []
import importlib.util as _il
spec = _il.spec_from_file_location(
    "fk", os.path.join(os.getcwd(), "task-solvers", "fake_task.py"))
fk = _il.module_from_spec(spec)
spec.loader.exec_module(fk)
calls = []
# Substitute the module agent.fake_task actually uses. It used to build its own
# private copy of fake_task.py on every call, so stubbing the copy loaded here
# did nothing and the test ran the REAL solver - which passed only because the
# game happened to be running, and failed with 'no game window dimensions' when
# it was not. The module is now cached and injectable.
fake_mod = type("FakeMod", (), {})()
fake_mod.fake_task = lambda name, allow_visual=False, map_name=None, stage=None: (
    calls.append(name) or {"ok": True, "task": name, "seconds": 6.0})
agent._FAKE_MODULE = fake_mod
set_state(imp=True, room="Electrical")
first = agent.fake_task("Divert Power")
check("the first fake is allowed", "faked Divert Power" in first, first)
try:
    agent.fake_task("Divert Power")
    check("the second fake is refused", False, "it was allowed")
except agent.ActionError as exc:
    check("the second fake is refused", "already faked" in str(exc), exc)
# the refusal happens before the solver is reached, which is what matters; the
# count cannot be observed because agent.fake_task re-imports the module each call
check("only one task is recorded as faked", len(agent._FAKED_ONCE) == 1,
      agent._FAKED_ONCE)

print()
print("=== 5. faking walks the bot TO the task, and refuses if it cannot ===")
agent._FAKED_ONCE.clear()
# stand in for movement, which would otherwise need a real game
import roleplay as _rp
_rp.walk_to = lambda G, x, y: True
_rp.press_use = lambda *a, **k: True
agent._walk_near = lambda G=None, target=None, task="": True
agent._tasks_here_real = True

# model the walk: _tasks_here reports "not there" until _walk_near is called,
# then reports the panel, exactly as arriving at a room would
_real_tasks_here = agent._tasks_here
_arrived = {"at": False}


def _fake_tasks_here():
    return ["Divert Power"] if _arrived["at"] else []


def _fake_walk(G=None, target=None, task=""):
    _arrived["at"] = True
    return True


agent._tasks_here = _fake_tasks_here
agent._walk_near = _fake_walk
# The harness now opens the panel and confirms it from the GAME's own state
# (Minigame.Instance), not from a screenshot. Report it open for this scenario.
botlink.read_minigame = lambda *a, **k: {"open": True, "task": "DivertPower"}
botlink.minigame_is = lambda name=None, timeout=0, poll=0: (
    {"open": True, "task": "DivertPower"})
import roleplay as _rp0  # noqa: E402
_rp0.press_use = lambda *a, **k: None
calls = []
import importlib.util as _il
spec = _il.spec_from_file_location(
    "fk2", os.path.join(os.getcwd(), "task-solvers", "fake_task.py"))
fk2 = _il.module_from_spec(spec)
spec.loader.exec_module(fk2)
fk2.fake_task = lambda name, allow_visual=False: (
    calls.append(name) or {"ok": True, "task": name, "seconds": 6.0})
out = agent.fake_task("Divert Power")
check("faking walks there and then fakes", "faked Divert Power" in out, out)
check("and reports that it walked", "walked to the panel" in out, out)

print()
print("=== faking walks using the LIVE route, not the static task database ===")
# This was a real bug found in a live game. The bot was in Admin, the static
# database has an Admin entry for Upload Data, so the old code walked to
# (2.69, -6.87) - a panel it was already standing at - and never moved at all,
# while reporting that it had walked. The live route the plugin publishes puts
# the real panel in Navigation at (17.0, -2.45).
import roleplay as _rp2  # noqa: E402

_walked_to = []
_saved = {
    "walk": _rp2.walk_to,
    "route": _rp2.task_route,
    "tasks_here": agent._tasks_here,
    "walk_near": agent._walk_near,
    "match": agent._match_outstanding_task,
    "locs": agent.roleplay_locations,
}
_arrived = {"at": False}


def _record_walk(G, x, y):
    _walked_to.append((x, y))
    _arrived["at"] = True
    return True


# empty before the walk, the panel after it - so the post-walk check passes
agent._tasks_here = lambda: ["Upload Data"] if _arrived["at"] else []
agent._walk_near = lambda G=None, target=None, task="": (
    _record_walk(G, target[0], target[1]) if target else False)
_rp2.walk_to = lambda G, x, y: _record_walk(G, x, y)
_rp2.task_route = lambda n, refresh=False: [(17.0, -2.45)]
agent._match_outstanding_task = lambda t: "Upload Data"
agent.roleplay_locations = lambda: {"Upload Data": "Navigation"}

agent._FAKED_ONCE.clear()
try:
    _out = agent.fake_task("Upload Data")
    check("faking reaches the panel", "walked to the panel" in _out, _out)
    check("and it walked to the LIVE route, not the static database",
          _walked_to and abs(_walked_to[0][0] - 17.0) < 0.01, _walked_to)
    check("and never to the Admin position the database offered",
          all(abs(w[0] - 2.68849) > 0.01 for w in _walked_to), _walked_to)
except Exception as exc:
    check("faking reaches the panel", False, f"{type(exc).__name__}: {exc}")
finally:
    _rp2.walk_to = _saved["walk"]
    _rp2.task_route = _saved["route"]
    agent._tasks_here = _saved["tasks_here"]
    agent._walk_near = _saved["walk_near"]
    agent._match_outstanding_task = _saved["match"]
    agent.roleplay_locations = _saved["locs"]
    agent._FAKED_ONCE.clear()

print()
print("=== 5b. it refuses when the GAME says the panel did not open ===")
# The harness confirms the panel from Minigame.Instance rather than from a
# screenshot. If the game says no minigame, the solver must not be run against a
# closed panel - that is what made "opens and closes, nothing connected" happen.
import botlink  # noqa: E402

agent._FAKED_ONCE.clear()
agent._tasks_here = lambda: []
agent._walk_near = lambda G=None, target=None, task="": True
_real_match2 = agent._match_outstanding_task
_real_locs2 = agent.roleplay_locations
_real_route2 = _rp2.task_route
agent._match_outstanding_task = lambda t: "Divert Power"
agent.roleplay_locations = lambda: {"Divert Power": "Electrical"}
_rp2.task_route = lambda n, refresh=False: [(5.0, -5.0)]
botlink.read_minigame = lambda *a, **k: {"open": False, "task": ""}
botlink.minigame_is = lambda name=None, timeout=0, poll=0: None
agent.utility.in_meeting = lambda: False
try:
    agent.fake_task("Divert Power")
    check("faking is refused when the panel never opened", False, "it was allowed")
except agent.ActionError as exc:
    check("faking is refused when the panel never opened", True)
    check("and it says the game reported no minigame",
          "no minigame" in str(exc), exc)
finally:
    agent._match_outstanding_task = _real_match2
    agent.roleplay_locations = _real_locs2
    _rp2.task_route = _real_route2

print()
print("=== 5c. a panel the game says is already open is not clicked again ===")
# USE toggles a minigame, so a second click closes the panel.
_clicked = []
_real_press = _rp2.press_use
_rp2.press_use = lambda *a, **k: _clicked.append(1)
botlink.read_minigame = lambda *a, **k: {"open": True, "task": "DivertPower"}
botlink.minigame_is = lambda name=None, timeout=0, poll=0: (
    {"open": True, "task": "DivertPower"})
try:
    agent._stand_at_panel("Divert Power")
    check("an already-open panel is not pressed USE again",
          not _clicked, f"{len(_clicked)} presses")
finally:
    _rp2.press_use = _real_press

print()
print("=== 5d. it refuses when it cannot walk there at all ===")
agent._FAKED_ONCE.clear()
agent._tasks_here = lambda: []
agent._walk_near = lambda G=None, target=None, task="": False
try:
    agent.fake_task("Divert Power")
    check("faking away from the task is refused when it cannot walk", False,
          "it was allowed")
except agent.ActionError as exc:
    check("faking away from the task is refused when it cannot walk",
          "could not walk" in str(exc) or "could not get to" in str(exc), exc)
agent._walk_near = lambda G=None, target=None, task="": True

print()
print("=== 6. faking a task you do not have is refused ===")
agent._FAKED_ONCE.clear()
set_state(imp=True, room="Electrical")
try:
    agent.fake_task("Start Reactor")
    check("faking a task it does not have is refused", False, "it was allowed")
except agent.ActionError as exc:
    check("faking a task it does not have is refused",
          "not on your fake task list" in str(exc), exc)

print()
print("=== 7. the model is given a reason to act ===")
set_state(imp=True, room="Cafeteria")
imp_st = agent._brief_state()
check("an impostor is told how it wins", "YOUR OBJECTIVE" in imp_st, imp_st[-200:])
check("and is told a kill is available or not", "kill is available" in imp_st,
      imp_st[-200:])
check("and is told idling loses", "Standing still is the one thing that loses" in imp_st,
      imp_st[-200:])
set_state(imp=False, room="Electrical")
crew_st = agent._brief_state()
check("a crewmate is told how it wins",
      "finish the task bar" in crew_st, crew_st[-200:])
check("and is given the progress", "Progress:" in crew_st or "task bar" in crew_st,
      crew_st[-200:])
check("and is told to use what it saw", "actually saw" in crew_st, crew_st[-200:])

print()
print("=== 8. no room is ever guessed for a later stage ===")
set_state(steps=["0/3", "1/2", "0/2"])
st = agent._brief_state()
check("no MedBay appears for an Electrical task", "MedBay" not in st, st)
check("the wording admits the room is unknown", "another panel" in st, st)
check("next_stage_room returns None rather than a guess",
      roleplay.next_stage_room("Divert Power", 1) is None)

if failures:
    print()
    print("FAILURES:", ", ".join(failures))
    sys.exit(1)
print()
print("all checks passed")
