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
print("all task lookups resolved correctly")
