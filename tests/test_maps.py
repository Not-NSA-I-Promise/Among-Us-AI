"""Which maps does this bot actually work on?

Found while chasing a walking bug: the game reports MapType names, the repo keys
everything off legacy names, and only Skeld lined up. The bot was non-functional
on Polus, Fungle and Mira HQ, and Airship had a task database but no graph.
"""
import _path  # noqa: F401
import os
import sys

import utility

failures = []


def check(label, cond, detail=""):
    print("  {} {}{}".format("PASS" if cond else "FAIL", label,
                             ("  <- " + str(detail)[:130]) if (detail and not cond) else ""))
    if not cond:
        failures.append(label)


print("=== 1. every MapType name normalises to a known key ===")
# these are the strings the game actually reports
GAME_NAMES = ["Ship", "Polus", "Airship", "Fungle", "MIRA HQ"]
for name in GAME_NAMES:
    key = utility.normalize_map(name)
    check("{!r} -> {!r}".format(name, key),
          key in ("SHIP", "PB", "AIRSHIP", "FUNGLE", "HQ"), key)

print()
print("=== 2. the old .upper() behaviour is what broke it ===")
for name, broken in (("Polus", "POLUS"), ("Fungle", "FUNGLE"),
                     ("MIRA HQ", "MIRA HQ")):
    check("{!r}.upper() = {!r} matched nothing".format(name, broken),
          broken not in ("SHIP", "PB", "AIRSHIP", "HQ"))

print()
print("=== 3. load_dict resolves a task database for each map ===")
for name in GAME_NAMES:
    key = utility.normalize_map(name)
    utility.MAP = key
    try:
        d = utility.load_dict()
        if key == "FUNGLE":
            # no database is bundled for Fungle; it must degrade to {} rather
            # than None, and available_maps() must say so
            check("{!r} (FUNGLE) degrades to an empty dict, not None".format(name),
                  d == {}, repr(d))
        else:
            check("{!r} ({}) has a task database".format(name, key),
                  isinstance(d, dict) and len(d) > 0,
                  f"{type(d).__name__} len={len(d) if d else 0}")
    except Exception as exc:
        check("{!r} ({}) has a task database".format(name, key), False,
              f"{type(exc).__name__}: {exc}")

print()
print("=== 4. load_G loads a graph, or says clearly that it cannot ===")
for name in GAME_NAMES:
    key = utility.normalize_map(name)
    utility.MAP = key
    try:
        g = utility.load_G(name)
        check("{!r} ({}) loads a graph with {} nodes".format(name, key, len(g.nodes)),
              len(g.nodes) > 0)
    except FileNotFoundError as exc:
        # an honest, named failure is acceptable; a bare one is not
        msg = str(exc)
        check("{!r} ({}) fails with a NAMED, actionable message".format(name, key),
              key in msg and "go_to" in msg, msg)
    except Exception as exc:
        check("{!r} ({}) loads a graph".format(name, key), False,
              f"{type(exc).__name__}: {exc}")

print()
print("=== 5. the message names the maps that DO work ===")
try:
    utility.load_G("Fungle")
except FileNotFoundError as exc:
    check("lists the maps that have graphs", "SHIP" in str(exc), str(exc))

print()
print("=== 6. available_maps reports the truth ===")
rows = utility.available_maps()
for key, graph, db in rows:
    real_graph = os.path.exists(os.path.join(
        "graphs", utility._GRAPH_FILES.get(key, "__none__")))
    real_db = os.path.exists(os.path.join(
        "tasks-json", {"SHIP": "SHIP_TASK_TYPES.json", "PB": "PB_TASK_TYPES.json",
                       "AIRSHIP": "AIRSHIP_TASK_TYPES.json",
                       "HQ": "HQ_TASK_TYPES.json",
                       "FUNGLE": "FUNGLE_TASK_TYPES.json"}[key]))
    check("{} graph reported correctly".format(key), graph == real_graph,
          "reported {} actual {}".format(graph, real_graph))
    check("{} task db reported correctly".format(key), db == real_db,
          "reported {} actual {}".format(db, real_db))

print()
usable = [k for k, g, d in rows if g and d]
partial = [k for k, g, d in rows if g != d]
print("  fully usable maps : {}".format(usable or "none"))
print("  partially usable  : {}".format(partial or "none"))
print("  unusable          : {}".format([k for k, g, d in rows if not g and not d] or "none"))

if failures:
    print()
    print("FAILURES:", ", ".join(failures))
    sys.exit(1)
print()
print("all checks passed")
