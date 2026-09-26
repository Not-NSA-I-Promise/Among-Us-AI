"""Synthesise whole matches in the dataset format.

For bootstrapping, and for covering situations that are rare in a sitting: a 1v1
endgame, a meeting where someone else found the body, a round where the right
answer is to do nothing for thirty seconds.

Built from the same agent.ACTIONS table and the same prompt builder as the real
thing, so it cannot teach the model a format the parser rejects. It teaches no
game knowledge, and every file says `source: synthetic` so it is never confused
with a recorded match.

Usage:
    python dataset/generate.py --matches 200
    python dataset/generate.py --matches 50 --only impostor
"""
import argparse
import json
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import agent  # noqa: E402
import roleplay  # noqa: E402
import botlink  # noqa: E402

OUT_DIR = os.path.join(HERE, "matches")

MAPS = ["Skeld", "Polus", "Airship", "Mira HQ", "Fungle"]

ROOMS = {
    "Skeld": ["Cafeteria", "Reactor", "Upper Engine", "Lower Engine", "Security",
              "MedBay", "Electrical", "Storage", "Admin", "Oxygen", "Weapons",
              "Navigation", "Shields", "Communications", "Hallway"],
    "Polus": ["Office", "Admin", "Security", "Electrical", "MedBay", "Boiler Room",
              "Snowball", "Comms", "Oxygen", "Laboratory", "Vault", "Records",
              "Specimen", "Outside", "Gap Room", "Ventilation"],
    "Airship": ["Cockpit", "Armory", "Kitchen", "Medical", "Cargo Bay", "Ventilation",
                "Records", "Meeting Room", "Showers", "Engine", "Brig", "Galley",
                "Security", "Airship Upper", "Airship Lower"],
    "Mira HQ": ["Launchpad", "Med Bay", "Headquarters", "Admin", "Laboratory",
                "Greenhouse", "Comms", "Vault", "Dormitory", "Kitchen"],
    "Fungle": ["Kitchen", "Sprinkler System", "Specimen Room", "Mushroom Mixup",
               "Lookout", "Secure Room", "Cave", "Go Here", "Ventilation"],
}

TASKS = {
    "Skeld": ["Swipe Card", "Fix Wiring", "Calibrate Distributor", "Empty Garbage",
              "Fuel Engines", "Start Reactor", "Submit Scan", "Download Data",
              "Upload Data", "Align Engine Output", "Clear Asteroids", "Prime Shields",
              "Unblock Manifolds", "Accept Diverted Power", "Clean O2 Filter", "Chart Course"],
    "Polus": ["Boarding Pass", "Fix Wiring", "Sort Samples", "Fuel Engines",
              "Start Reactor", "Submit Scan", "Download Data", "Clean O2 Filter",
              "Fix Weather Node", "Reboot Wifi", "Record Temperature", "Empty Chute"],
    "Airship": ["Swipe Card", "Fix Wiring", "Fuel Engines", "Start Reactor", "Submit Scan",
                "Download Data", "Align Engine Output", "Clear Asteroids", "Chart Course",
                "Reboot Wifi", "Unblock Manifolds", "Ventilation"],
    "Mira HQ": ["Swipe Card", "Fix Wiring", "Fuel Engines", "Start Reactor", "Submit Scan",
                "Download Data", "Clear Asteroids", "Accept Diverted Power", "Chart Course"],
    "Fungle": ["Scan Mushroom", "Collect Samples", "Fuel Engines", "Start Reactor",
               "Submit Scan", "Mushroom Mixup", "Empty Bin", "Ventilation"],
}

CREW = ["RED", "BLUE", "GREEN", "PINK", "ORANGE", "YELLOW", "WHITE", "BLACK",
        "PURPLE", "BROWN", "CYAN", "LIME", "ROSE", "BANANA"]

CREW_ROLES = ["Crewmate", "Scientist", "Engineer", "Guardian Angel", "Tracker",
              "Noisemaker", "Detective", "Judge", "Phantom"]

IMP_ROLES = ["Impostor", "Shape Shifter", "Phantom", "Viper"]

# Phantom can be rolled on either side, so it is allowed in both lists above and
# picked from whichever side this match is.

# What a person actually says in a meeting, so the model learns that `say` takes
# a short human sentence and not a paragraph of reasoning.
MEETING_LINES = [
    "who did you see near MedBay?",
    "i was on cams the whole time",
    "the body was in Electrical when i passed",
    "i think it was green, they were near the body",
    "can someone confirm reactor?",
    "i was doing tasks in storage the whole round",
    "who followed me?",
    "i killed him in self defence",
    "vote red, they were vented near me",
    "i have admin, i was in the o2 room",
]

VOTE_LINES = {
    "impostor": ["red", "blue", "skip", "green"],
    "crew": ["red", "blue", "skip"],
}


def _system_prompt(role, is_imp, map_name, tasks):
    """Build a prompt the same way the real harness does, with fake state.

    Uses agent.tool_reference so the generated data cannot drift from the format
    the parser actually accepts.
    """
    lines = []
    abilities = roleplay.ROLE_ABILITIES.get(role, [])
    if abilities:
        numbered = "; ".join(f"{i+1}) {a}" for i, a in enumerate(abilities))
        plural = "ability" if len(abilities) == 1 else "abilities"
        lines.append(f"You are {role}. You have {len(abilities)} {plural}: {numbered}.")
    else:
        lines.append(f"You are {role}. You have no special ability.")
    lines.append("No role in this game has more than 2 abilities.")
    lines.append("")
    lines.append(f"Rooms on this map: {', '.join(ROOMS.get(map_name, []))}")
    if tasks:
        if is_imp:
            lines.append("You are an IMPOSTOR. The tasks below are your cover story - "
                         "never actually complete one, because real progress gives you "
                         "away. Use fake_task to stand at a panel for the right length "
                         "of time.")
            lines.append("Your fake task list: " + ", ".join(tasks))
        else:
            lines.append("Tasks you still have to do: " + ", ".join(tasks))
    lines.append("")
    lines.append("You may call exactly one of these per turn. Nothing else is possible:")
    lines.append("")
    for name in agent.action_names():
        lines.append(f"  {agent.ACTIONS[name][2]}")
    lines += [
        "",
        "Reply with one line: the action name and its argument, nothing else.",
        'Examples: "go_to Electrical", "kill", "sabotage lights", "wait".',
        'If nothing is safe or useful to do right now, reply "wait".',
    ]
    return "\n".join(lines)


def _situation(role, is_imp, room, alive, near, in_meeting=False,
               invent=False, cooldown=None, killed=0, meeting_turns=0):
    bits = [f"you are {role} ({'impostor' if is_imp else 'crew'})", f"in {room}",
            f"alive: {', '.join(alive) if alive else 'you are alone'}"]
    if near:
        bits.append(f"near you: {', '.join(near)}")
    if is_imp:
        if cooldown is not None:
            bits.append(f"kill cooldown: {cooldown}")
            bits.append(f"can kill right now: {cooldown <= 0}")
    if in_meeting:
        bits.append("a meeting is running")
    if invent:
        bits.append("you are inside a vent")
    if killed:
        bits.append(f"you have killed {killed} so far")
    if meeting_turns:
        bits.append(f"{meeting_turns} turns left in this meeting: "
                    "you still need to speak and vote")
    return "; ".join(bits)


def _valid_actions(role, is_imp, in_meeting, invent, can_vent):
    """The actions that are legal right now, so generated turns are not nonsense."""
    names = []
    if in_meeting:
        names = ["observe", "say", "vote", "wait"]
    else:
        names = ["go_to", "observe", "wait", "do_task" if not is_imp else "fake_task"]
        if is_imp:
            names += ["kill", "sabotage", "queue_sabotage", "fake_task"]
            if can_vent:
                names.append("vent")
        else:
            if can_vent:
                names.append("vent")
        if role in ("Guardian Angel",):
            names.append("protect")
        if role in ("Shape Shifter",):
            names.append("mimic")
        if role == "Detective":
            names += ["interrogate", "notes"]
        if role == "Judge":
            names.append("overrule")
    return [n for n in names if n in agent.ACTIONS]


def _phrase(name, args, role, is_imp, map_name, rng):
    """Render a legal action the way a person would say it."""
    if name == "go_to":
        return rng.choice([f"go_to {args[0]}", f"go to {args[0]}",
                           f"head to {args[0]}", f"walk towards {args[0]}"])
    if name == "kill":
        return rng.choice(["kill", "kill the nearest player"])
    if name == "sabotage":
        n = rng.choice(["lights", "comms", "o2", "reactor", "Electrical", "MedBay"])
        return f"sabotage {n}"
    if name == "fake_task":
        return rng.choice([f"fake_task {args[0]}", f"pretend doing {args[0]}",
                           f"fake the {args[0]} task"])
    if name == "do_task":
        return f"do_task {args[0]}"
    if name == "vent":
        return rng.choice(["vent", "hide in a vent"])
    if name == "say":
        return f"say {rng.choice(MEETING_LINES)}"
    if name == "vote":
        return f"vote {args[0]}"
    if name == "observe":
        return f"observe {args[0]}"
    if name == "mimic":
        return f"mimic {args[0]}"
    if name == "protect":
        return f"protect {args[0]}"
    if name == "interrogate":
        return "interrogate"
    if name == "notes":
        return "read my notes"
    return name


def _args_for(name, role, alive, rng, tasks, meeting=False):
    if name == "go_to":
        return [rng.choice(alive)] if alive and rng.random() < 0.2 else ["__ROOM__"]
    if name == "fake_task" or name == "do_task":
        return [rng.choice(tasks)] if tasks else ["__ROOM__"]
    if name == "vote":
        return [rng.choice(VOTE_LINES["impostor" if role in IMP_ROLES else "crew"])]
    if name in ("mimic", "protect"):
        return [rng.choice(alive)] if alive else ["RED"]
    if name == "observe":
        return [rng.choice(["state", "map", "memory", "witnesses", "notes", "vitals"])]
    if name == "overrule":
        return [str(rng.randint(0, 9))]
    if name == "queue_sabotage":
        return [rng.choice(["lights", "comms", "o2", "reactor"])]
    return []


def _observation(name, args, rng, ok=True, refused=None):
    if refused:
        return f"refused: {refused}", False
    if not ok:
        return f"no valid action (said: {args})", False
    if name == "go_to":
        return f"walking to {args[0]}", True
    if name == "kill":
        return "killed", True
    if name == "sabotage":
        return f"sabotaged {args[0] if args else rng.choice(['lights','comms'])}", True
    if name == "fake_task":
        secs = round(rng.uniform(8, 10), 1)
        return (f"faked {args[0]} for {secs}s (timing only - the task bar did not move)", True)
    if name == "do_task":
        return f"completed {args[0]} in __ROOM__", True
    if name == "vent":
        return "entered a vent", True
    if name == "say":
        return "said it", True
    if name == "vote":
        return f"voted for {args[0]}", True
    if name == "wait":
        return "did nothing, deliberately", True
    if name == "observe":
        return f"{args[0]}: (synthetic observation)", True
    if name in ("mimic", "protect", "interrogate", "notes", "overrule", "queue_sabotage"):
        return f"{name} done", True
    return f"{name} done", True


def generate_match(rng, force_impostor=None):
    map_name = rng.choice(MAPS)
    rooms = ROOMS.get(map_name, ["Cafeteria"])
    tasks = TASKS.get(map_name, ["Swipe Card"])

    is_imp = force_impostor if force_impostor is not None else rng.random() < 0.4
    role = rng.choice(IMP_ROLES) if is_imp else rng.choice(CREW_ROLES)
    # only roles that can actually vent
    can_vent = role in ("Impostor", "Engineer", "Shape Shifter", "Phantom", "Viper")

    n_players = rng.randint(5, 12)
    me = rng.choice(CREW)
    others = rng.sample([c for c in CREW if c != me], min(n_players - 1, len(CREW) - 1))
    alive = [me] + others

    system = _system_prompt(role, is_imp, map_name, tasks)
    turns = []
    history = []
    killed = 0
    room = rng.choice(rooms)
    # a whole round: 40-110 turns, which is a few minutes of play
    n_turns = rng.randint(40, 110)

    meeting_at = set()
    if n_turns > 30:
        meeting_at.add(rng.randint(8, n_turns // 2))
        if rng.random() < 0.8:
            meeting_at.add(rng.randint(n_turns // 2, n_turns - 6))

    in_meeting = False
    meeting_left = 0
    invent = False

    for n in range(1, n_turns + 1):
        if n in meeting_at:
            in_meeting = True
            meeting_left = rng.randint(3, 8)
        if in_meeting:
            meeting_left -= 1
            if meeting_left <= 0:
                in_meeting = False

        if rng.random() < 0.3:
            room = rng.choice(rooms)

        near = []
        if not in_meeting and rng.random() < 0.35:
            near = rng.sample([c for c in alive if c != me],
                              min(len(alive) - 1, rng.randint(1, 2)))

        cooldown = None
        if is_imp and not in_meeting:
            cooldown = rng.choice([0, 0, 0, 5, 12, 25, 40])

        situation = _situation(role, is_imp, room, [c for c in alive if c != me][:4],
                               near, in_meeting=in_meeting, invent=invent,
                               cooldown=cooldown, killed=killed,
                               meeting_turns=meeting_left if in_meeting else 0)
        if history:
            situation += " | last turn you chose: " + history[-1]

        legal = _valid_actions(role, is_imp, in_meeting, invent, can_vent)
        # 8% of turns are unparseable: the model drifts, and the recovery is
        # the behaviour we actually want to teach
        unparseable = rng.random() < 0.08
        if unparseable:
            assistant = rng.choice([
                "go to room", "teleport to helms", "sudo kill everyone",
                "I think we should probably do something about the lights maybe",
                "wait for it", "do the thing", ""])
            action, args = None, None
            obs, ok = f"no valid action (said: {assistant})", False
        else:
            name = rng.choice(legal)
            args = _args_for(name, role, alive, rng, tasks, meeting=in_meeting)
            assistant = _phrase(name, args, role, is_imp, map_name, rng)
            # a small share of refusals, so the model learns to cope with them
            refuse = None
            if rng.random() < 0.06:
                if name == "go_to":
                    refuse = (f"there is no room called {args[0]!r} on this map. "
                              f"The rooms are: {', '.join(rooms)}")
                elif name == "vent":
                    refuse = "your role cannot vent"
                elif name == "fake_task":
                    refuse = (f"{args[0]} is a visual task - other players can see it "
                              f"happening, so standing still does not look like doing it")
                elif name == "kill":
                    refuse = "the kill did not land - cooldown, or nobody in range"
            obs, ok = _observation(name, args, rng, refused=refuse)
            action = name
            if ok and name == "kill":
                killed += 1
            if ok and name == "vent":
                invent = not invent
            if ok and name == "vote":
                in_meeting = False
                meeting_left = 0
            # the observation templates use __ROOM__ as a stand-in; resolve it
            # whether or not the action's own args carried the placeholder
            if "__ROOM__" in (obs or "") or (args and "__ROOM__" in args):
                here = rng.choice(rooms)
                if args:
                    args = [here if a == "__ROOM__" else a for a in args]
                assistant = assistant.replace("__ROOM__", here)
                obs = (obs or "").replace("__ROOM__", here)

        turns.append({
            "n": n, "system": system, "user": situation,
            "assistant": assistant, "action": action,
            "args": args, "observation": obs, "ok": ok,
        })
        if action:
            history.append(f"{action} {' '.join(args)}".strip())

    refused = sum(1 for t in turns if not t["ok"])
    return {
        "id": f"{map_name.lower().replace(' ', '-')}-synthetic-{time.strftime('%Y%m%d')}-{rng.randint(1000,9999)}",
        "source": "synthetic",
        "map": map_name,
        "role": role,
        "is_impostor": is_imp,
        "result": rng.choice(["crew", "impostor", "crew", "impostor", "draw"]),
        "turns": turns,
        "stats": {"total": len(turns), "refused": refused,
                  "unparseable": sum(1 for t in turns if t["action"] is None)},
        "notes": "synthesised by dataset/generate.py; teaches format and phase "
                 "transitions, not game knowledge",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--matches", type=int, default=100)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--out", default=OUT_DIR)
    ap.add_argument("--only", choices=["impostor", "crew"], default=None)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    os.makedirs(args.out, exist_ok=True)

    written = 0
    for i in range(args.matches):
        force = True if args.only == "impostor" else (False if args.only == "crew" else None)
        m = generate_match(rng, force_impostor=force)
        path = os.path.join(args.out, m["id"] + ".json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(m, f, indent=2)
        written += 1
    print(f"wrote {written} synthetic matches to {args.out}")


if __name__ == "__main__":
    main()
