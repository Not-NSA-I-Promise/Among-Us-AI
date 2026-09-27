import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))),
                                "task-solvers"))
import fake_task as f

expect = [
    ("fix wires", "Fix Wiring"),
    ("wires", "Fix Wiring"),
    ("the wiring task", "Fix Wiring"),
    ("MedBay scan", "Submit Scan"),
    ("Submit Scan", "Submit Scan"),
    ("Start Reactor", "Start Reactor"),
    ("download data", "Download Data"),
    ("Upload Data", "Upload Data"),
    ("wiring", "Fix Wiring"),
    ("divert power", "Divert Power"),
    ("Fuel Engines", "Fuel Engines"),
    ("asteroids", "Clear Asteroids"),
    ("chart the course", "Chart Course"),
    ("nonsense task", None),
    ("", None),
]

bad = []
for q, want in expect:
    rec = f.lookup(q)
    # identify which key it resolved to by matching the record object identity
    got = None
    if rec is not None:
        for k, v in f.durations().items():
            if v is rec and not k.startswith("_"):
                got = k
                break
    flag = "ok " if got == want else "BAD"
    if got != want:
        bad.append((q, want, got))
    print("  {} {:20} -> {}".format(flag, q, got))

print()
print("visual tasks and their durations:")
for n in f.known_task_names():
    rec = f.durations()[n]
    if rec.get("visual"):
        print("  {:20} {}s  visual -> refuses by default".format(n, rec["seconds"]))

print()
print("sampled durations should vary, not be a constant midpoint:")
for _ in range(5):
    print("   Download Data ->", round(f.typical_seconds("Download Data"), 2), "s")
for _ in range(4):
    print("   Swipe Card    ->", round(f.typical_seconds("Swipe Card"), 2), "s")

if bad:
    print()
    print("MISMATCHES:")
    for q, want, got in bad:
        print("  {!r}: expected {!r}, got {!r}".format(q, want, got))
    raise SystemExit(1)
print()
print()
print("=== visual / fakeable rules are map- and stage-specific ===")
# These were wrong as flat per-task flags, which made the harness refuse
# legitimate fakes and allow ones that give the bot away.
EXPECTED = [
    #  task               map     stage  fakeable
    ("Chart Course",      "SHIP",  1,     True),   # was wrongly visual
    ("Start Reactor",     "SHIP",  1,     True),   # was wrongly visual
    ("Divert Power",      "SHIP",  1,     True),
    ("Submit Scan",       "SHIP",  1,     False),
    ("Clear Asteroids",   "SHIP",  1,     False),
    ("Prime Shields",     "SHIP",  1,     False),
    ("Prime Shields",     "HQ",    1,     True),   # shields show nothing here
    ("Clear Asteroids",   "HQ",    1,     True),   # no missiles on Mira HQ
    ("Submit Scan",       "HQ",    1,     False),
    ("Submit Scan",       "PB",    1,     False),
    ("Empty Garbage",     "SHIP",  1,     True),   # Cafeteria lever: nothing shows
    ("Empty Garbage",     "SHIP",  2,     False),  # Storage: visibly full
    ("Empty Chute",       "SHIP",  1,     True),
    ("Empty Chute",       "SHIP",  2,     False),
    ("Chart Course",      None,    None,  True),   # no map known -> flat flag
    ("Submit Scan",       None,    None,  False),
]
bad = []
for task, mp, st, want in EXPECTED:
    got, why = f.is_fakeable(task, mp, st)
    if got != want:
        bad.append((task, mp, st, want, got, why))
    print("  {:4} {:16} map={:5} stage={:4} -> {:5} {}".format(
        "ok" if got == want else "BAD", task, str(mp), str(st), got,
        ("- " + why[:52]) if why else ""))

print()
print("=== a refusal explains WHY, so the model can pick another task ===")
_ok, why = f.is_fakeable("Submit Scan", "SHIP", 1)
if not (not _ok and len(why) > 20):
    bad.append(("Submit Scan", "SHIP", 1, "a reason", why, ""))
if "different task" not in why:
    bad.append(("Submit Scan", "SHIP", 1, "'different task' advice", why, ""))
print("  a visual task is refused with a reason:",
      not _ok and len(why) > 20)
print("  and it is told to fake something else:",
      "different task" in why, "->", why)

if bad:
    print()
    print("MISMATCHES:")
    for row in bad:
        print("  {!r}".format(row))
    raise SystemExit(1)
print()
print("all task lookups resolved correctly, and the map/stage visual rules hold")
