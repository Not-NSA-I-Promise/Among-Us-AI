"""A crewmate must be able to do tasks, and only tasks in the room it is in.

The live log showed a Crewmate being refused with "you are an impostor" and then
idling for the whole round. The condition and the message in do_task were
inverted: `not isImpostor()` is true for a CREWMATE.
"""
import _path  # noqa: F401
import os
import sys

import agent
import agent_loop
import botlink
import utility

failures = []


def check(label, cond, detail=""):
    print("  {} {}{}".format("PASS" if cond else "FAIL", label,
                             ("  <- " + str(detail)[:150]) if (detail and not cond) else ""))
    if not cond:
        failures.append(label)


TASKS = ["Fix Wiring", "Empty Garbage", "Divert Power", "Prime Shields"]
LOCS = ["Electrical", "Cafeteria", "Upper Engine", "Shields"]


def set_state(imp=False, room="Cafeteria", dead=False, meeting=False,
              steps=None):
    """steps: dict of task -> (done, total); the fake solver advances it."""
    STEPS.clear()
    STEPS.update(steps if steps is not None
                 else {t: (0, 1) for t in TASKS})
    def snapshot():
        return {
            "map_id": "Ship", "room": room, "color": "RED", "inMeeting": meeting,
            "playersDead": {"RED": dead}, "tasks": list(TASKS),
            "task_locations": list(LOCS),
            "task_steps": [f"{STEPS.get(t, (0, 1))[0]}/{STEPS.get(t, (0, 1))[1]}"
                           for t in TASKS],
            "position": (0, 0), "lights": "0",
            "nearbyPlayers": []}
    utility.getGameData = snapshot
    utility.isImpostor = lambda: imp
    utility.isDead = lambda: dead
    utility.in_meeting = lambda: meeting
    utility.get_fellow_imposters = lambda: []
    utility.get_killCD = lambda: 0.0
    utility.is_urgent_task = lambda *a, **k: None
    utility.get_chat_messages = lambda: []
    botlink.get_role = lambda: "Impostor" if imp else "Crewmate"
    botlink.read_ability = lambda: {
        "invent": "0", "isdead": "1" if dead else "0",
        "isimpostor": "1" if imp else "0", "cankill": "1",
        "canvent": "1" if imp else "0", "abilitycount": "0"}


# stand in for the solver so no game interaction happens
solver_calls = []
# the simulated step counter the fake solver advances
STEPS = {}


class FakeSolver:
    @staticmethod
    def solve_task(task_name=None, **kw):
        solver_calls.append(task_name)
        # A real solver completes a panel, so the counter must move. Without
        # this the harness correctly reports "no stage completed", which is the
        # behaviour the live log showed when Fix Wiring did nothing.
        if task_name in STEPS:
            cur, total = STEPS[task_name]
            if cur < total:
                STEPS[task_name] = (cur + 1, total)
        return 0


sys.modules["solver"] = FakeSolver

# and for movement, so no real walking is attempted
walk_calls = []


def fake_walk(G, x, y):
    walk_calls.append((round(x, 1), round(y, 1)))
    return True


import roleplay  # noqa: E402
roleplay.walk_to = fake_walk
roleplay.press_use = lambda *a, **k: True
# no taskRoutes.txt while the game is closed, so fall back to the database
roleplay.task_route = lambda name: []

print("=== 1. a CREWMATE is not told it is an impostor ===")
set_state(imp=False, room="Cafeteria")
try:
    out = agent.do_task("Empty Garbage")
    check("crew do_task succeeds", True, out)
except agent.ActionError as exc:
    check("crew do_task succeeds", False, exc)
except Exception as exc:
    check("crew do_task succeeds", False, f"{type(exc).__name__}: {exc}")
check("the impostor message is NOT what a crewmate gets",
      "impostor" not in str(solver_calls), solver_calls)

print()
print("=== 2. an IMPOSTOR is told not to do real tasks ===")
set_state(imp=True, room="Cafeteria")
before = len(solver_calls)
try:
    agent.do_task("Empty Garbage")
    check("imp do_task is refused", False, "it was allowed")
except agent.ActionError as exc:
    check("imp do_task is refused", "impostor" in str(exc).lower(), exc)
check("and the solver was never called for the impostor",
      len(solver_calls) == before, solver_calls)

print()
print("=== 3. a dead ghost is refused, for a different reason ===")
set_state(imp=False, dead=True, room="Cafeteria")
try:
    agent.do_task("Empty Garbage")
    check("dead ghost do_task is refused", False, "it was allowed")
except agent.ActionError as exc:
    check("dead ghost do_task is refused", "dead" in str(exc).lower(), exc)

print()
print("=== 4. a task in ANOTHER room is refused, with the room named ===")
set_state(imp=False, room="Weapons")   # no task here at all
try:
    agent.do_task("Empty Garbage")
    check("out-of-room task is refused", False, "it was allowed")
except agent.ActionError as exc:
    check("out-of-room task is refused", "go_to" in str(exc), exc)
    check("and it says which room the task is in", "Cafeteria" in str(exc), exc)

print()
print("=== 5. a task in this room works, and the solver gets the real name ===")
set_state(imp=False, room="Cafeteria")
del solver_calls[:]
out = agent.do_task("empty garbage")       # loose phrasing
check("in-room task succeeds", "Empty Garbage" in out, out)
check("the solver received the canonical name", solver_calls == ["Empty Garbage"],
      solver_calls)

print()
print("=== 6. a task the bot does not have is refused, listing what it has ===")
set_state(imp=False, room="Cafeteria")
try:
    agent.do_task("Start Reactor")
    check("a task it does not have is refused", False, "it was allowed")
except agent.ActionError as exc:
    check("a task it does not have is refused", "Start Reactor" in str(exc), exc)
    check("and the refusal lists the real list", "Fix Wiring" in str(exc), exc)

print()
print("=== 7. the prompt offers in-room tasks ONLY ===")
set_state(imp=False, room="Cafeteria")
st = agent._brief_state()
check("the in-room task is offered", "Empty Garbage" in st, st)
check("the in-room offer is explicitly 'in THIS room'",
      "tasks you can do in THIS room" in st, st)
# out-of-room tasks ARE mentioned, but as progress only - never as doable here
offer = st.split("tasks you can do in THIS room")[1].split(";")[0]
check("no out-of-room task appears in the in-room offer",
      "Fix Wiring" not in offer and "Divert Power" not in offer, offer)
check("out-of-room tasks are still shown as progress",
      "Fix Wiring 0/1 not started, in Electrical" in st, st)
check("no route is suggested when a task is already underfoot",
      "use go_to" not in st, st)

set_state(imp=False, room="Weapons")
st = agent._brief_state()
check("a room with no task says so", "no task in this room" in st, st)
check("and points at the remaining ones with their rooms",
      "Empty Garbage (Cafeteria)" in st, st)
check("and says to use go_to", "use go_to" in st, st)

print()
print("=== 8. an impostor is offered fakes, not real tasks, for this room ===")
set_state(imp=True, room="Cafeteria")
st = agent._brief_state()
check("imp sees FAKE wording", "FAKE" in st, st)
check("imp is not told it can do a real task here",
      "can do in THIS room" not in st, st)

print()
print("=== 9. the wait nudge only offers an in-room task ===")
botlink.read_ability = lambda: {"invent": "0", "isdead": "0", "isimpostor": "0",
                                "cankill": "0", "canvent": "0", "abilitycount": "0"}
a = agent_loop.Agent()
a._consecutive_waits = agent_loop.WAIT_STREAK_LIMIT
sit = a.situation()
check("nudge offers the in-room task", "do_task Empty Garbage" in sit, sit[-220:])

set_state(imp=False, room="Weapons")
a = agent_loop.Agent()
a._consecutive_waits = agent_loop.WAIT_STREAK_LIMIT
sit = a.situation()
check("with no task here, no do_task is offered", "do_task" not in sit, sit[-220:])
check("and it suggests going somewhere instead", "go_to" in sit, sit[-220:])

if failures:
    print()
    print("FAILURES:", ", ".join(failures))
    sys.exit(1)
print()
print("all checks passed: a crewmate can do tasks, and only the ones underfoot")
