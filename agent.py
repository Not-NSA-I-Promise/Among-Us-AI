"""The agent loop: the model plays, this file only executes.

The rule (see ARCHITECTURE.md): the model decides WHAT happens, the harness
decides only HOW. This module is the tool surface. Every legal game action is a
named function in ACTIONS. Nothing outside that table can be done, and a
function here may not perform a second action the model did not ask for.

Concretely that means no `if cooldown_ready(): kill()`. The model has to say so.
"""
import os
import time

import botlink
import utility

# --------------------------------------------------------------------------
# The action table. This is the whole API the model has.
#
# Each entry is: name -> (required args, handler, one-line description)
# The descriptions are what get sent to the model, so they are written to be
# read by the model rather than by a human maintainer.
# --------------------------------------------------------------------------


class ActionError(Exception):
    """The requested action is not legal right now."""


def _living_players():
    try:
        data = utility.getGameData()
    except Exception:
        return []
    me = data.get("color")
    return [c for c, dead in data.get("playersDead", {}).items()
            if not dead and c != me]


def _nearby_players():
    try:
        G = utility.load_G(utility.getGameData()["map_id"])
        data = utility.getGameData()
        return [c for c in utility.get_imposter_nearby_players(G) if c != data["color"]]
    except Exception:
        return []


# ---------------------------------------------------------------- movement
def go_to_room(room):
    """Walk to a named room on this map."""
    import roleplay
    key = str(room).strip().lower()
    try:
        G = utility.load_G(utility.getGameData()["map_id"])
    except Exception as exc:
        raise ActionError(f"no map graph: {exc}")
    pos = roleplay.room_position(G, key)
    if pos is None:
        raise ActionError(f"no room called {key!r} on this map")
    ok = roleplay.walk_to(G, pos[0], pos[1])
    return f"walking to {key}" if ok else f"could not walk to {key}"


def stop_moving():
    """Stop walking where you are."""
    try:
        import roleplay
        roleplay.utility.gamepad.leftStick.axis(0).value = 0
        return "stopped"
    except Exception as exc:
        raise ActionError(str(exc))


# ----------------------------------------------------------------- combat
def kill():
    """Kill the nearest player in range."""
    if not utility.should_I_kill():
        raise ActionError("no kill is available: cooldown, nobody in range, or not an impostor")
    try:
        G = utility.load_G(utility.getGameData()["map_id"])
    except Exception as exc:
        raise ActionError(f"no map graph: {exc}")
    ok = roleplay_kill_nearest(G)
    return "killed" if ok else "kill did not land"


def report_body():
    """Report the body you are standing at."""
    try:
        import roleplay
        roleplay.press_button(roleplay.REPORT_BUTTON, duration=0.15)
        return "reported"
    except Exception as exc:
        raise ActionError(str(exc))


# -------------------------------------------------------------- sabotage
def sabotage(name):
    """Trigger a named sabotage, e.g. lights, comms, o2, Electrical, reactor."""
    import importlib.util
    ts = os.path.join(os.path.dirname(os.path.realpath(__file__)), "task-solvers")
    spec = importlib.util.spec_from_file_location(
        "sabmod", os.path.join(ts, "Sabotage.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.ONLY = str(name).strip()
    if mod.sabotage():
        return f"sabotaged {name}"
    raise ActionError(f"the game did not perform the {name} sabotage")


def queue_sabotage(name):
    """Ask the model to consider a sabotage later (records the preference)."""
    import roleplay
    roleplay.request_sabotage(str(name).strip())
    return f"queued {name}"


# ------------------------------------------------------------- abilities
def use_ability():
    """Use your role's first ability."""
    if botlink.use_ability():
        return "used ability 1"
    raise ActionError(f"ability 1 was refused: {botlink.last_result()}")


def use_ability_2():
    """Use your role's second ability, if your role has one."""
    abilities = _abilities()
    if len(abilities) < 2:
        raise ActionError(f"your role has {len(abilities)} ability, not 2")
    if botlink.use_secondary_ability():
        return "used ability 2"
    raise ActionError(f"ability 2 was refused: {botlink.last_result()}")


def _abilities():
    import roleplay
    return roleplay.my_abilities()


def protect(color):
    """Guardian Angel: shield a player by colour."""
    idx = _color_index(color)
    if botlink.protect(idx):
        return f"protecting {color}"
    raise ActionError(f"protect refused: {botlink.last_result()}")


def mimic(color):
    """Shapeshifter: appear as a player by colour."""
    idx = _color_index(color)
    if botlink.mimic(idx):
        return f"mimicking {color}"
    raise ActionError(f"mimic refused: {botlink.last_result()}")


def interrogate():
    """Detective: interrogate a player or inspect the body you are next to."""
    import roleplay
    if roleplay.detective_interrogate():
        return "interrogated"
    raise ActionError("interrogate refused: stand next to a player or a body")


def read_notes():
    """Detective: open your notebook and read what you have collected."""
    import roleplay
    text = roleplay.detective_notes()
    if not text:
        raise ActionError("no notes collected yet")
    return text


def overrule(player_id):
    """Judge: spend your extra vote to eject a player by player id."""
    if botlink.overrule(int(player_id)):
        return f"overruled player {player_id}"
    raise ActionError(f"overrule refused: {botlink.last_result()}")


# ------------------------------------------------------------------ tasks
def do_task():
    """Do the task you are currently standing at."""
    try:
        return utility.do_tasks() or "did the task here"
    except Exception as exc:
        raise ActionError(str(exc))


# ---------------------------------------------------------------- social
def say(message):
    """Say something in the meeting or in-game chat."""
    try:
        import chatGPT
        chatGPT.say(str(message))
        return "said it"
    except Exception as exc:
        raise ActionError(str(exc))


def vote(color):
    """Vote to eject a player by colour. Use 'skip' to skip."""
    if str(color).strip().lower() in ("skip", "none", "-1"):
        if botlink.cast_vote(-1):
            return "skipped the vote"
        raise ActionError(f"skip refused: {botlink.last_result()}")
    idx = _color_index(color)
    if botlink.cast_vote(idx):
        return f"voted for {color}"
    raise ActionError(f"vote refused: {botlink.last_result()}")


# --------------------------------------------------------------- observe
def observe(what):
    """Read information. One of: state, map, vitals, tracker, notes, memory, witnesses."""
    what = str(what).strip().lower()
    if what == "state":
        return _brief_state()
    if what == "vitals":
        v = botlink.read_scientist_vitals()
        return "; ".join(f"{n} {c} {s}" for n, c, s in v) or "no vitals"
    if what == "notes":
        import roleplay
        return roleplay.detective_report() or "no notes"
    if what == "memory":
        import roleplay
        return "; ".join(roleplay.role_memory()) or "nothing learned yet"
    if what == "witnesses":
        return str(botlink.read_kill_presence())
    if what == "map":
        g = botlink.vent_graph()
        return "; ".join(f"vent {k}->{v}" for k, v in g.items()) or "no vent data"
    if what == "tracker":
        return _tracker_report()
    raise ActionError(f"cannot observe {what!r}; try state, map, vitals, tracker, notes, memory, witnesses")


def _tracker_report():
    try:
        G = utility.load_G(utility.getGameData()["map_id"])
    except Exception as exc:
        raise ActionError(f"no map graph: {exc}")
    graph = botlink.vent_graph()
    if not graph:
        return "no tracker data"
    return "; ".join(f"vent {k} connects to {v}" for k, v in graph.items())


def do_nothing():
    """Take no action this turn. Use this when nothing is safe to do."""
    return "did nothing, deliberately"


def _color_index(color):
    name = str(color).strip().lower()
    try:
        return botlink.COLOR_NAMES.index(name)
    except ValueError:
        raise ActionError(f"{color!r} is not a player colour; "
                          f"valid: {', '.join(botlink.COLOR_NAMES)}")


def _brief_state():
    data = utility.getGameData()
    role = botlink.get_role()
    ab = botlink.read_ability()
    living = _living_players()
    near = _nearby_players()
    bits = [
        f"you are {role} ({'impostor' if ab.get('isimpostor') == '1' else 'crew'})",
        f"in {data['room']}",
        f"alive: {', '.join(living) if living else 'you are alone'}",
    ]
    if near:
        bits.append(f"near you: {', '.join(near)}")
    if data.get("inMeeting") == "1":
        bits.append("a meeting is running")
    if ab.get("invent") == "1":
        bits.append("you are inside a vent")
    return "; ".join(bits)


def roleplay_kill_nearest(G):
    import roleplay
    return roleplay.kill_nearest(G)


# The table. (required args, handler, description-for-the-model)
ACTIONS = {
    "go_to": (("room",), go_to_room, "go to <room> - walk to a named room"),
    "stop": ((), stop_moving, "stop - stop walking where you are"),
    "kill": ((), kill, "kill - kill the nearest player in range"),
    "report": ((), report_body, "report - report the body you are at"),
    "sabotage": (("name",), sabotage, "sabotage <name> - trigger lights, comms, o2, reactor or a door"),
    "queue_sabotage": (("name",), queue_sabotage, "queue_sabotage <name> - note a sabotage to consider later"),
    "ability": ((), use_ability, "ability - use your role's first ability"),
    "ability2": ((), use_ability_2, "ability2 - use your role's second ability (only if you have one)"),
    "protect": (("color",), protect, "protect <color> - Guardian Angel: shield a player"),
    "mimic": (("color",), mimic, "mimic <color> - Shapeshifter: appear as a player"),
    "interrogate": ((), interrogate, "interrogate - Detective: inspect the player or body next to you"),
    "notes": ((), read_notes, "notes - Detective: read your notebook"),
    "overrule": (("player_id",), overrule, "overrule <player_id> - Judge: extra vote to eject"),
    "do_task": ((), do_task, "do_task - do the task you are standing at"),
    "say": (("message",), say, "say <message> - speak in chat or at a meeting"),
    "vote": (("color",), vote, "vote <color|skip> - vote at a meeting"),
    "observe": (("what",), observe, "observe <state|map|vitals|tracker|notes|memory|witnesses> - gather information"),
    "wait": ((), do_nothing, "wait - deliberately do nothing this turn"),
}


def action_names():
    return sorted(ACTIONS)


def tool_reference(role=None):
    """The action table rendered for the model's system prompt."""
    import roleplay
    if role is None:
        head = roleplay.ability_brief()
    else:
        abilities = roleplay.my_abilities(role)
        if not abilities:
            head = f"You are {role}. You have no special ability."
        else:
            numbered = "; ".join(f"{i + 1}) {a}" for i, a in enumerate(abilities))
            plural = "ability" if len(abilities) == 1 else "abilities"
            head = (f"You are {role}. You have {len(abilities)} {plural}: "
                    f"{numbered}.")
    lines = [
        head,
        # Stated unconditionally. A model told "you are Detective" with no
        # ability list will happily invent a third ability.
        "No role in this game has more than 2 abilities.",
        "",
        "You may call exactly one of these per turn. Nothing else is possible:",
        "",
    ]
    for name in action_names():
        _args, _fn, desc = ACTIONS[name]
        lines.append(f"  {desc}")
    lines += [
        "",
        "Reply with one line: the action name and its argument, nothing else.",
        'Examples: "go_to Electrical", "kill", "sabotage lights", "wait".',
        "If nothing is safe or useful to do right now, reply \"wait\".",
    ]
    return "\n".join(lines)


def parse_action(reply):
    """Turn one line of model output into (name, [args]). None if unusable."""
    if not reply:
        return None, None
    line = reply.strip().splitlines()[0].strip()
    line = line.strip("`").strip()
    for prefix in ("action:", "action =", "call:", "tool:"):
        if line.lower().startswith(prefix):
            line = line[len(prefix):].strip()
    if not line:
        return None, None
    parts = line.replace("=", " ").split()
    name = parts[0].lower().strip(",.:;")
    if name not in ACTIONS:
        return None, line
    args = [p.strip(",.;:\"'") for p in parts[1:]]
    required, _fn, _desc = ACTIONS[name]
    if len(args) < len(required):
        return None, line
    return name, args[:len(required)]


def run_action(name, args):
    """Execute one action. Raises ActionError if it is not legal right now."""
    _required, handler, _desc = ACTIONS[name]
    return handler(*args)
