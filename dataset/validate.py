"""Gate for the SFT dataset.

Every entry has to survive this before it is allowed into the training set. The
point is that a defective entry - one where the Tracker vents, or the impostor
completes a task, or wires are faked in the wrong order - is worse than no entry
at all, because training on it teaches the defect.

Usage:
    python dataset/validate.py                 # validate everything in entries/
    python dataset/validate.py path/to/x.json  # validate one file
    python dataset/validate.py --strict        # treat warnings as errors

Exit code 0 if everything passes, 1 otherwise.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

DICT_PATH = os.path.join(HERE, "AMONGUS_DICTIONARY.json")
ENTRIES_PATH = os.path.join(HERE, "entries.jsonl")

with open(DICT_PATH, encoding="utf-8") as _f:
    D = json.load(_f)

ROLES = {}
ROLES.update(D["ROLES"]["impostor_side"])
ROLES.update(D["ROLES"]["crew_side"])
# Phantom is the one role that can be rolled on EITHER side, so a single flat
# table is wrong for it: crew Phantom cannot kill, impostor Phantom can. Resolve
# it by the entry's own `side` metatag, and keep the crew default for when the
# side is missing.
DUAL_SIDE_ROLES = {r for r in D["ROLES"]["impostor_side"]
                   if r in D["ROLES"]["crew_side"]}

VENT_NETWORKS = D["VENT_NETWORKS"]
VISUAL_TASKS = set(D["TASK_SEQUENCE"]["visual_tasks"]["list"])
WIRING_PANEL_ORDER = D["TASK_SEQUENCE"]["fix_wiring"]["panel_order"]

# every room that appears in any vent network, for travel validation
VENT_ROOMS = set()
for _map, _data in VENT_NETWORKS.items():
    if not isinstance(_data, dict):
        continue
    for net in _data.get("networks", []):
        for room in net:
            VENT_ROOMS.add(room.lower())


class Report:
    def __init__(self, name):
        self.name = name
        self.errors = []
        self.warnings = []

    def err(self, where, msg):
        self.errors.append(f"{where}: {msg}")

    def warn(self, where, msg):
        self.warnings.append(f"{where}: {msg}")

    def ok(self):
        return not self.errors


def role_spec(role, side=None):
    """The legality record for a role, resolving dual-side roles by `side`."""
    if role in DUAL_SIDE_ROLES and side:
        table = D["ROLES"]["impostor_side"] if side == "impostor" else D["ROLES"]["crew_side"]
        if role in table:
            return table[role]
    return ROLES.get(role)


def _role_spec(entry):
    mt = entry.get("metatags", {})
    return role_spec(mt.get("role"), mt.get("side"))


def check_metatags(entry, r):
    """The metatags must be present and internally consistent."""
    mt = entry.get("metatags")
    if not isinstance(mt, dict):
        r.err("metatags", "missing or not an object")
        return False
    for key in ("role", "side", "map", "result"):
        if key not in mt:
            r.err("metatags", f"missing required key {key!r}")
    role = mt.get("role")
    if role not in ROLES:
        r.err("metatags", f"unknown role {role!r}; the dictionary defines "
                          f"{sorted(ROLES)}")
        return False
    side = mt.get("side")
    expected = "impostor" if role in D["ROLES"]["impostor_side"] else "crew"
    if side and side != expected and role not in DUAL_SIDE_ROLES:
        r.err("metatags", f"role {role!r} is a {expected} role but side is {side!r}")
    if role in DUAL_SIDE_ROLES and not side:
        r.err("metatags", f"{role} can be on either side, so `side` is required")
    spec = role_spec(role, side)
    for key in ("can_vent", "can_kill", "abilities"):
        if key in mt and mt[key] != spec.get(key):
            r.err("metatags", f"{key}={mt[key]} but {role} ({side}) has "
                              f"{key}={spec.get(key)}")
    if mt.get("can_do_tasks") is not None and mt["can_do_tasks"] != spec["can_do_tasks"]:
        r.err("metatags", f"can_do_tasks={mt['can_do_tasks']} but {role} has "
                          f"{spec['can_do_tasks']}")
    if mt.get("map") not in VENT_NETWORKS and mt.get("map") not in ("Fungle",):
        r.warn("metatags", f"map {mt.get('map')!r} is not in the vent network table")
    if spec["abilities"] > 2:
        r.err("dictionary", f"{role} has {spec['abilities']} abilities; the game max is 2")
    return not r.errors


def check_turns(entry, r):
    """Every turn must be legal for the role and consistent with the state."""
    turns = entry.get("turns")
    if not isinstance(turns, list) or not turns:
        r.err("turns", "must be a non-empty list")
        return
    spec = _role_spec(entry)
    if spec is None:
        return
    side = entry["metatags"].get("side")
    role = entry["metatags"]["role"]

    # --- whole-match shape ---
    n = len(turns)
    if n < 12:
        r.err("turns", f"only {n} turns; a whole match needs more")
    actions = [t.get("action") for t in turns]
    if "say" not in actions:
        r.warn("turns", "no `say` anywhere; a match should contain meetings")
    if not any(a in ("kill", "report", "vote") for a in actions) and side == "impostor":
        r.warn("turns", "impostor entry with no kill/report/vote at all")
    if side == "impostor" and "fake_task" not in actions:
        # measured: winners fake 6.6x more often than losers
        r.warn("turns", "impostor entry never fakes a task. Winners fake far more "
                        "than losers; this is the strongest win correlate there is")

    # --- meeting structure ---
    # The situation string is the ground truth for whether a meeting is running.
    # Latching on the first `say` and never clearing produced a false positive on
    # every turn after the first meeting, so derive it from the text instead.
    in_meeting = False
    said_this_meeting = False
    voted_this_meeting = False
    for i, t in enumerate(turns, 1):
        w = f"turn {i}"
        act = t.get("action")
        situation = t.get("user", "") or ""
        was_in_meeting = in_meeting
        in_meeting = "a meeting is running" in situation
        if in_meeting and not was_in_meeting:
            said_this_meeting = False
            voted_this_meeting = False
        if act is None:
            continue
        args = t.get("args") or []

        # An entry may deliberately contain an illegal action in order to teach
        # the recovery - "the agent tried to do a task and accepted the refusal"
        # is a behaviour worth training. That is only legitimate when the turn is
        # marked as failed AND flagged, otherwise it is just a defect.
        taught = bool(t.get("teaching_refusal"))

        if act == "say":
            if not in_meeting:
                r.warn(w, "say outside a meeting")
            said_this_meeting = True
        if act == "vote":
            if not in_meeting:
                r.warn(w, "vote outside a meeting")
            if not said_this_meeting:
                r.warn(w, "voted without having spoken in the meeting")
            voted_this_meeting = True
        if in_meeting and act in ("go_to", "do_task", "kill", "vent", "sabotage",
                                  "fake_task", "ability", "ability2", "mimic",
                                  "protect", "interrogate", "notes", "overrule"):
            r.err(w, f"{act!r} is impossible during a meeting")
        if in_meeting and voted_this_meeting and act not in ("vote", "observe", "say", "wait"):
            r.warn(w, f"{act!r} after voting in the same meeting")

        # --- role legality ---
        def role_err(msg):
            if taught and t.get("ok") is False:
                r.warn(w, f"deliberately illegal action, kept for the recovery: {msg}")
            else:
                r.err(w, msg)

        if act == "vent" and not spec["can_vent"]:
            role_err(f"{role} cannot vent (can_vent={spec['can_vent']})")
        if act == "kill" and not spec["can_kill"]:
            role_err(f"{role} cannot kill (can_kill={spec['can_kill']})")
        if act == "ability2" and spec["abilities"] < 2:
            role_err(f"{role} has {spec['abilities']} ability/abilities, so "
                     f"ability2 is impossible")
        if act == "do_task" and not spec["can_do_tasks"]:
            role_err(f"{role} is an impostor-side role and must never complete a "
                     f"real task - use fake_task")
        if act == "fake_task" and side == "crew":
            r.warn(w, "crewmate faking a task; crew have real tasks, this is odd")
        if act == "protect" and role != "Guardian Angel":
            role_err(f"protect is Guardian Angel's ability, not {role}'s")
        if act == "mimic" and role != "Shapeshifter":
            role_err(f"mimic is the Shapeshifter's ability, not {role}'s")
        if act in ("interrogate", "notes") and role != "Detective":
            role_err(f"{act} is the Detective's ability, not {role}'s")
        if act == "overrule" and role != "Judge":
            role_err(f"overrule is the Judge's ability, not {role}'s")

        # --- task legality ---
        if act == "fake_task":
            if not args:
                r.err(w, "fake_task with no task name")
            else:
                name = str(args[0])
                if name in VISUAL_TASKS and not t.get("allow_visual"):
                    r.err(w, f"{name} is a VISUAL task and cannot be faked by "
                             f"standing still. Pass allow_visual and justify it "
                             f"in the turn's rationale, or pick another task")
                dur = t.get("seconds")
                if dur is not None:
                    rec = _duration_for(name)
                    if rec:
                        lo, hi = rec
                        if not (lo - 1.5 <= float(dur) <= hi + 1.5):
                            r.err(w, f"faked {name} for {dur}s but a real one takes "
                                     f"{lo}-{hi}s. A wrong duration is exactly the "
                                     f"tell this dataset is meant to prevent")
                    else:
                        r.warn(w, f"no timing data for {name!r} in task_durations.json")
        if act == "do_task" and args and str(args[0]) in VISUAL_TASKS:
            # completing a visual task is fine, it is only faking that is the problem
            pass

    # --- kill discipline: never two kills in a row with no reason ---
    kills = [i for i, t in enumerate(turns) if t.get("action") == "kill"]
    for a, b in zip(kills, kills[1:]):
        if b - a < 2:
            r.err(f"turn {b+1}", "killed on consecutive turns; the kill cooldown "
                                "makes that impossible")
    return not r.errors


def _duration_for(name):
    import sys as _s
    p = os.path.join(ROOT, "task-solvers")
    if p not in _s.path:
        _s.path.insert(0, p)
    try:
        import fake_task
        rec = fake_task.lookup(name)
        return rec.get("seconds") if rec else None
    except Exception:
        return None


def check_reasoning(entry, r):
    """Each turn should carry why, so the model learns reasoning not just action."""
    turns = entry.get("turns") or []
    missing = [i for i, t in enumerate(turns, 1) if not t.get("rationale")]
    if missing:
        r.warn("turns", f"{len(missing)} turn(s) have no `rationale` field; the "
                        f"model will learn actions without reasons (first: {missing[:5]})")
    if not entry.get("notes"):
        r.warn("entry", "no top-level `notes` explaining what this entry teaches")


def check_social_quality(entry, r):
    """Dialogue has to sound like players, not prose."""
    turns = entry.get("turns") or []
    for i, t in enumerate(turns, 1):
        if t.get("action") != "say":
            continue
        args = t.get("args") or []
        if not args:
            r.err(f"turn {i}", "say with no message")
            continue
        msg = str(args[0])
        if len(msg) > 90:
            r.warn(f"turn {i}", f"say message is {len(msg)} chars; players type "
                                f"3-8 words: {msg[:60]!r}")
        if any(ch in msg for ch in "[]*(){}"):
            r.warn(f"turn {i}", "message contains formatting characters")
        if msg != msg.lower() and not msg.isupper():
            r.warn(f"turn {i}", f"message is oddly cased: {msg[:40]!r}")


def validate(entry, name="<entry>"):
    r = Report(name)
    if not check_metatags(entry, r):
        return r
    check_turns(entry, r)
    check_reasoning(entry, r)
    check_social_quality(entry, r)
    return r


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def iter_entries(path):
    """Yield (label, entry) from a .jsonl file, or a single .json file.

    The dataset is one JSONL file with an entry per line, which streams and never
    holds every match in memory. A plain .json path is also accepted so a single
    entry can be checked on its own while authoring.
    """
    if path.endswith(".jsonl"):
        with open(path, encoding="utf-8") as f:
            for n, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    yield f"line {n}", json.loads(line)
                except ValueError as exc:
                    yield f"line {n}", {"__parse_error__": str(exc)}
    else:
        with open(path, encoding="utf-8") as f:
            yield os.path.basename(path), json.load(f)


def main():
    args = sys.argv[1:]
    strict = "--strict" in args
    paths = [a for a in args if not a.startswith("--")] or [ENTRIES_PATH]

    total = failed = warned = 0
    for path in paths:
        if not os.path.exists(path):
            print(f"no such file: {path}")
            return 1
        print(f"== {path}\n")
        for name, entry in iter_entries(path):
            total += 1
            if "__parse_error__" in entry:
                print(f"FAIL {name}: not valid JSON - {entry['__parse_error__']}")
                failed += 1
                continue
            eid = entry.get("id", name)
            r = validate(entry, eid)
            if r.errors:
                failed += 1
                print(f"FAIL {eid}")
                for e in r.errors:
                    print(f"     ERROR   {e}")
                for w in r.warnings:
                    print(f"     warning {w}")
            else:
                warned += len(r.warnings)
                mt = entry["metatags"]
                suffix = f"  ({len(r.warnings)} warning(s))" if r.warnings else ""
                print(f"PASS {eid:44} {mt['role']:14} {mt['map']:9} "
                      f"{len(entry.get('turns', [])):3} turns{suffix}")
                for w in r.warnings:
                    print(f"     warning {w}")

    print()
    print(f"{total} entries, {failed} failed, {warned} warning(s)")
    if strict and warned:
        print("strict mode: warnings are failures")
        return 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
