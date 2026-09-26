import _path  # noqa: F401
import agent

# The exact replies the real model produced in the failing session, plus the
# phrasings a small local model is likely to reach for.
cases = [
    # --- these three are the real observed failures ---
    "go to Cafeteria",
    "go to room",
    "go to Room1",
    # --- other natural phrasings ---
    "go_to Electrical",
    "head to the Reactor",
    "walk towards MedBay",
    "move to Storage",
    "kill",
    "kill the nearest player",
    "murder RED",
    "report the body",
    "sabotage lights",
    "sabotage the lights",
    "queue_sabotage comms",
    "use my ability",
    "use ability 1",
    "use my ability 2",
    "use my secondary ability",
    "protect BLUE",
    "shield the red",
    "mimic GREEN",
    "shapeshift into PINK",
    "interrogate",
    "read my notes",
    "open notes",
    "overrule 3",
    "do a task",
    "complete the task",
    "say \"hello everyone\"",
    "vote for RED",
    "eject BLUE",
    "skip",
    "skip the vote",
    "observe state",
    "check the map",
    "wait",
    "do nothing",
    "stand still",
    "stop",
    "action: go_to Reactor",
    "`mimic RED`",
        # --- must still be rejected: no such action, or missing an argument ---
    "teleport to hell",
    "sudo destroy the reactor",
    "go to",
    "sabotage",
    "rm -rf",
    "",
]

# (reply, expected action, expected argument or None) - argument checked too,
# because a correct verb with a wrong argument is still broken.
expected = [
    ("go to Cafeteria", "go_to", "Cafeteria"),
    ("go_to Electrical", "go_to", "Electrical"),
    ("head to the Reactor", "go_to", "Reactor"),
    ("walk towards MedBay", "go_to", "MedBay"),
    ("move to Storage", "go_to", "Storage"),
    ("go to Room1", "go_to", "Room1"),
    ("sabotage lights", "sabotage", "lights"),
    ("sabotage the lights", "sabotage", "lights"),
    ("queue_sabotage comms", "queue_sabotage", "comms"),
    ("protect BLUE", "protect", "BLUE"),
    ("shield the red", "protect", "red"),
    ("mimic GREEN", "mimic", "GREEN"),
    ("shapeshift into PINK", "mimic", "PINK"),
    ("overrule 3", "overrule", "3"),
    ("vote for RED", "vote", "RED"),
    ("eject BLUE", "vote", "BLUE"),
    ("skip", "vote", "skip"),
    ("skip the vote", "vote", "skip"),
    ("observe state", "observe", "state"),
    ("check the map", "observe", "map"),
    ("kill", "kill", None),
    ("report the body", "report", None),
    ("use my ability", "ability", None),
    ("use my ability 2", "ability2", None),
    ("wait", "wait", None),
    ("do nothing", "wait", None),
    ("stop", "stop", None),
    ("interrogate", "interrogate", None),
    ("read my notes", "notes", None),
    ("do a task", "do_task", "here"),
    ("do_task Calibrate Distributor", "do_task", "Calibrate"),
    ("do the wiring task", "do_task", "wiring"),
    ("go do the Swipe Card task", "do_task", "Swipe Card"),
]

reject = [
    "teleport to hell", "sudo destroy the reactor", "go to", "sabotage",
    "rm -rf", "", "dance like a penguin",
]

print("{!r:34} -> {}".format("REPLY", "PARSED"))
print("-" * 62)
problems = []
for c in cases:
    name, arg = agent.parse_action(c)
    print("{!r:34} -> {}".format(c, (name, arg) if name else "REJECTED"))

print()
for reply, want_name, want_arg in expected:
    name, arg = agent.parse_action(reply)
    got_arg = arg[0] if isinstance(arg, list) and arg else None
    if name != want_name or got_arg != want_arg:
        problems.append("{!r}: expected ({!r}, {!r}) got ({!r}, {!r})".format(
            reply, want_name, want_arg, name, got_arg))

for reply in reject:
    name, _ = agent.parse_action(reply)
    if name is not None:
        problems.append("{!r}: should have been rejected, got {!r}".format(reply, name))

print()
if problems:
    print("PROBLEMS:")
    for p in problems:
        print("  -", p)
    raise SystemExit(1)
print("all {} phrasings parsed with the right argument; all {} invented verbs rejected".format(
    len(expected), len(reject)))
