"""The model must be told enough to act, and must be able to ask.

Every failure here came from a real log. The bot walked the map doing nothing
and one reply was "no valid action (said: fix wiring)" - it wanted the wires and
had no way to say so, because a bare task name did not parse. To the rest of the
lobby a bot standing in a room doing nothing is an impostor faking a task.
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
                             ("  <- " + str(detail)[:120]) if (detail and not cond) else ""))
    if not cond:
        failures.append(label)


TASKS = ["Fix Wiring", "Empty Garbage", "Divert Power", "Prime Shields"]


def fake_state(in_meeting=False, imp=False, room="Electrical", near=("BLUE",),
               vent=False, dead=False):
    utility.getGameData = lambda: {
        "map_id": "Skeld", "room": room, "color": "RED", "inMeeting": in_meeting,
        "playersDead": {"RED": dead, "BLUE": False}, "tasks": list(TASKS),
        "task_locations": ["Electrical", "Cafeteria", "Upper Engine", "Shields"],
        "position": (0, 0), "lights": "0", "nearbyPlayers": []}
    utility.get_fellow_imposters = lambda: ["GREEN"]
    utility.get_killCD = lambda: 0.0
    utility.is_urgent_task = lambda *a, **k: None
    utility.get_chat_messages = lambda: []
    botlink.get_role = lambda: "Impostor" if imp else "Crewmate"
    botlink.read_ability = lambda: {
        "invent": "1" if vent else "0", "isdead": "1" if dead else "0",
        "isimpostor": "1" if imp else "0", "cankill": "1",
        "canvent": "1", "abilitycount": "1"}
    botlink.last_result = lambda: ""


print("=== 1. a bare task name parses, which is what the log showed failing ===")
fake_state()
for phrase in ("fix wiring", "fix wires", "wires", "the wiring", "do the wires",
               "empty garbage", "divert power", "prime shields", "prime"):
    n, a = agent.parse_action(phrase)
    check("crew: {!r} resolves to do_task".format(phrase),
          n == "do_task" and a, (n, a))

print()
print("=== 2. multi-word task names survive the parser ===")
for phrase, want in (("do_task Fix Wiring", "Fix Wiring"),
                     ("fake_task Download Data", "Download Data"),
                     ("do_task Calibrate Distributor", "Calibrate Distributor")):
    n, a = agent.parse_action(phrase)
    check("{!r} keeps the whole name".format(phrase), a and a[0] == want, (n, a))

print()
print("=== 3. a bare task name as an impostor becomes fake_task, not do_task ===")
fake_state(imp=True)
n, a = agent.parse_action("fix wiring")
check("imp says 'fix wiring' -> fake_task", n == "fake_task", (n, a))
fake_state()
n, a = agent.parse_action("fix wiring")
check("crew says 'fix wiring' -> do_task", n == "do_task", (n, a))

print()
print("=== 4. what the parser accepts is what the solver can run ===")
fake_state()
for phrase in ("fix wiring", "wires", "divert power", "empty garbage"):
    n, a = agent.parse_action(phrase)
    found = roleplay.find_task(a[0]) if (n and a) else None
    check("{!r} parses AND resolves to a real task".format(phrase),
          bool(found), (n, a, found))

print()
print("=== 5. non-tasks are still rejected ===")
fake_state()
for junk in ("teleport to hell", "rm -rf", "sudo kill all", "dance like a penguin",
             "go to", "fix the flux capacitor"):
    n, _ = agent.parse_action(junk)
    check("{!r} rejected".format(junk), n is None, n)

print()
print("=== 6. a bare sentence is speech, but only in a meeting ===")
fake_state(in_meeting=True)
for speech in ("i think red is sus", "red vented in elec", "who followed you",
               "no i was in elec", "its sus"):
    n, a = agent.parse_action(speech)
    check("{!r} -> say".format(speech), n == "say" and a and a[0] == speech, (n, a))
for junk in ("teleport to hell", "rm -rf", "do_something_weird", "{}[]"):
    n, _ = agent.parse_action(junk)
    check("meeting: {!r} still rejected".format(junk), n is None, n)
fake_state(in_meeting=False)
for speech in ("i think red is sus", "red vented in elec"):
    n, _ = agent.parse_action(speech)
    check("outside a meeting, {!r} is not assumed speech".format(speech),
          n is None, n)

print()
print("=== 7. the model is told which tasks are underfoot ===")
fake_state(room="Electrical")
check("tasks in Electrical are found", agent._tasks_here() == ["Fix Wiring"],
      agent._tasks_here())
fake_state(room="Cafeteria")
check("tasks in Cafeteria are found", agent._tasks_here() == ["Empty Garbage"],
      agent._tasks_here())
fake_state(room="Weapons")
check("a room with no task reports none", agent._tasks_here() == [],
      agent._tasks_here())
state = agent._brief_state() if False else None
fake_state(room="Electrical")
state = agent._brief_state()
check("the state line names the tasks in this room",
      "in THIS room" in state, state)

print()
print("=== 8. the model is told about fellow impostors ===")
fake_state(imp=True)
state = agent._brief_state()
check("fellow impostor is named", "fellow IMPOSTOR" in state, state)
check("and told not to kill them", "never kill or vote them" in state, state)

print()
print("=== 9. the role-specific judgement is in the prompt ===")
for role, imp, needle in (
        ("Shapeshifter", True, "Do NOT shapeshift while a crewmate is near"),
        ("Detective", False, "Do NOT interrogate a random player"),
        ("Judge", False, "Do NOT use it on a hunch"),
        ("Viper", True, "kill THROUGH the vent"),
        ("Tracker", False, "CANNOT vent"),
        ("Scientist", False, "nobody is dead on vitals"),
        ("Noisemaker", False, "decoy arrow"),
        ("Engineer", False, "for movement"),
        ("Guardian Angel", False, "protect <colour>"),
        ("Phantom", True, "leaves a decoy"),
        ("Crewmate", False, "who followed you"),
        ("Impostor", True, "double kill")):
    botlink.get_role = lambda r=role: r
    botlink.read_ability = lambda i=imp: {
        "invent": "0", "isdead": "0", "isimpostor": "1" if i else "0",
        "cankill": "1", "canvent": "1", "abilitycount": "1"}
    st = agent._brief_state()
    check("{} is told: {!r}".format(role, needle[:40]), needle in st, st[-160:])

print()
print("=== 10. `wait` is a real cooldown, not a prompt telling-off ===")
botlink.get_role = lambda: "Crewmate"
fake_state()
agent.reset_for_new_round()
a = agent_loop.Agent()
check("with no cooldown the model is not nagged",
      "not an option" not in a.situation(), a.situation()[-140:])

# actually wait, which starts the timer
agent.run_action("wait", [])
sit = a.situation()
check("after waiting, the model is told wait is closed",
      "not an option" in sit, sit[-200:])
check("and it is given a real time", "180s" in sit or "179s" in sit, sit[-200:])
check("and the action is gone from the tool list",
      "wait" not in agent.action_names(available_only=True))
check("not merely mentioned in a list of options",
      "wait - deliberately" not in agent.tool_reference("Crewmate"))
agent.reset_for_new_round()
check("a new round clears it", "not an option" not in a.situation())

print()
print("=== 11. a real action is always available while wait is cooling ===")
fake_state(imp=True, room="Weapons")
agent.reset_for_new_round()
agent.run_action("wait", [])
a = agent_loop.Agent()
offered = agent.action_names(available_only=True)
check("fake_task is still offered during the cooldown", "fake_task" in offered)
check("do_task is still offered for a crewmate-like state", "do_task" in offered)
check("and observe/go_to still work", "observe" in offered and "go_to" in offered)
agent.reset_for_new_round()

print()
print("=== 12. the cooldown does not block anything else ===")
a = agent_loop.Agent()
llm = sys.modules.get("llm")
llm.ask = lambda m, **k: "do_task Fix Wiring"
name, arg = a.decide()
check("the model can still choose a real action", name == "do_task", name)
check("and doing so leaves the cooldown alone", agent._wait_cooldown_left() == 0)

if failures:
    print()
    print("FAILURES:", ", ".join(failures))
    sys.exit(1)
print()
print("all checks passed: the model can name a task, sees the room, and is "
      "pushed out of a wait loop")
