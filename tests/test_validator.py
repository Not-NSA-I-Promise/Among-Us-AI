"""Prove validate.py rejects the defective entries it is meant to reject.

The user named these specific failure modes, so each one gets a deliberately
broken entry and an assertion that the validator catches it. A gate that has
never been shown to fail is not a gate.
"""
import _path  # noqa: F401
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))),
                                "dataset"))
import validate as V  # noqa: E402


def entry(role, side, turns, **mt):
    base = {
        "id": "test", "metatags": {"role": role, "side": side, "map": "Skeld",
                                   "result": "crew"},
        "turns": turns, "notes": "test",
    }
    base["metatags"].update(mt)
    return base


def t(n, action, args=None, **kw):
    d = {"n": n, "action": action, "args": args or [], "rationale": "test",
         "user": "you are a test; in Cafeteria"}
    d.update(kw)
    return d


def pad(turns, n=14):
    """The validator requires a whole match, so allowed-cases need real length."""
    out = list(turns)
    filler = ["go_to", "observe", "wait", "go_to"]
    rooms = ["Reactor", "Cafeteria", "state", "Electrical", "map", "Storage",
             "witnesses", "Weapons", "memory", "Oxygen", "notes", "Admin",
             "state", "Navigation"]
    i = 0
    while len(out) < n:
        a = filler[i % len(filler)]
        args = {"go_to": [rooms[i % len(rooms)]], "observe": [rooms[i % len(rooms)]],
                "wait": []}.get(a, [])
        out.append(t(len(out) + 1, a, args))
        i += 1
    for j, tt in enumerate(out, 1):
        tt["n"] = j
    return out


CASES = [
    ("Tracker vents (the classic mistake)",
     entry("Tracker", "crew", [t(1, "vent")]),
     "cannot vent"),

    ("Crewmate vents",
     entry("Crewmate", "crew", [t(1, "vent")]),
     "cannot vent"),

    ("Engineer vents (must be ALLOWED)",
     entry("Engineer", "crew", pad([t(1, "vent")])),
     None),

    ("Impostor completes a real task",
     entry("Impostor", "impostor", [t(1, "do_task", ["Swipe Card"])]),
     "must never complete a real task"),

    ("Crewmate tries to kill",
     entry("Scientist", "crew", [t(1, "kill")]),
     "cannot kill"),

    ("ability2 on a one-ability role",
     entry("Scientist", "crew", [t(1, "ability2")]),
     "ability2 is impossible"),

    ("ability2 on the Detective (must be ALLOWED)",
     entry("Detective", "crew", pad([t(1, "ability2")])),
     None),

    ("faking a visual task without opting in",
     entry("Impostor", "impostor", [t(1, "fake_task", ["Submit Scan"], seconds=10)]),
     "VISUAL"),

    ("faking wires for the wrong duration",
     entry("Impostor", "impostor",
           [t(1, "fake_task", ["Fix Wiring"], seconds=0.5)]),
     "wrong duration"),

    ("faking wires for the right duration (must be ALLOWED)",
     entry("Impostor", "impostor",
           pad([t(1, "fake_task", ["Fix Wiring"], seconds=3.5)])),
     None),

    ("faking a download for 8.5s (must be ALLOWED)",
     entry("Impostor", "impostor",
           pad([t(1, "fake_task", ["Download Data"], seconds=8.5)])),
     None),

    ("killing during a meeting",
     entry("Impostor", "impostor", pad([
         # the meeting state is derived from the situation text, so it has to say so
         t(1, "say", ["red sus"], user="a meeting is running; 3 turns left"),
         t(2, "kill", user="a meeting is running; 2 turns left"),
     ])),
     "impossible during a meeting"),

    ("two kills on consecutive turns",
     entry("Impostor", "impostor", pad([
         t(1, "kill"), t(2, "kill"),
     ])),
     "consecutive"),

    ("protect used by the wrong role",
     entry("Scientist", "crew", [t(1, "protect", ["RED"])]),
     "Guardian Angel's ability"),

    ("mimic used by the wrong role",
     entry("Engineer", "crew", [t(1, "mimic", ["RED"])]),
     "Shapeshifter's ability"),

    ("overrule used by the wrong role",
     entry("Detective", "crew", [t(1, "overrule", ["3"])]),
     "Judge's ability"),

    ("can_vent metatag contradicts the dictionary",
     entry("Tracker", "crew", [t(1, "wait")], can_vent=True),
     "can_vent"),

    ("abilities metatag contradicts the dictionary",
     entry("Scientist", "crew", [t(1, "wait")], abilities=2),
     "abilities"),

    ("side contradicts the role",
     entry("Impostor", "crew", [t(1, "wait")]),
     "impostor role but side"),

    ("unknown role",
     entry("Wizard", "crew", [t(1, "wait")]),
     "unknown role"),

    ("an impostor entry that never fakes a task (warning)",
     entry("Impostor", "impostor", pad([t(1, "kill"), t(2, "go_to", ["Reactor"])])),
     "never fakes a task"),
]

fails = []
print("{:<52} {}".format("CASE", "RESULT"))
print("-" * 78)
for label, e, expect_err in CASES:
    rep = V.validate(e, label)
    if expect_err is None:
        if rep.errors:
            fails.append(f"{label}: expected to PASS but got {rep.errors}")
            print("{:<52} FAIL  (unexpected: {})".format(label, rep.errors[0][:44]))
        else:
            print("{:<52} pass  (allowed, as expected)".format(label))
    else:
        if expect_err in " ".join(rep.warnings + rep.errors):
            print("{:<52} caught".format(label))
        else:
            fails.append(f"{label}: expected {expect_err!r}, got {rep.errors + rep.warnings}")
            print("{:<52} MISSED".format(label))

print()
if fails:
    print("VALIDATOR GAPS:")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("validator caught every case it was supposed to")
