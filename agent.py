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
    key = str(room).strip()
    try:
        G = utility.load_G(utility.getGameData()["map_id"])
    except Exception as exc:
        raise ActionError(f"no map graph: {exc}")
    pos = roleplay.room_position(G, key)
    if pos is None:
        # Tell the model what the rooms are actually called, so it can correct
        # itself next turn instead of repeating an invented name.
        rooms = roleplay.known_rooms()
        raise ActionError(
            f"there is no room called {key!r} on this map. "
            f"The rooms are: {', '.join(rooms)}")
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
    """Kill the nearest player in range.

    Deliberately NOT gated on utility.should_I_kill(). That was a harness-side
    decision the model could neither see nor override, which is exactly the kind
    of autonomous choice this architecture forbids. The model is told the
    cooldown and decides for itself; if the kill is not actually available the
    game refuses it and the refusal is reported back.
    """
    if utility.isDead():
        raise ActionError("you are dead")
    if not utility.isImpostor():
        raise ActionError("you are not an impostor")
    try:
        G = utility.load_G(utility.getGameData()["map_id"])
    except Exception as exc:
        raise ActionError(f"no map graph: {exc}")
    ok = roleplay_kill_nearest(G)
    if not ok:
        raise ActionError("the kill did not land - cooldown, or nobody in range")
    return "killed"


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
def do_task(name=None):
    """Do a named task: walk to where it is, then solve it.

    The model chooses WHICH task and WHEN. The harness only does the mechanical
    part - walking there and working the minigame - because a model cannot usefully
    direct pixel-level dragging and asking it to would burn context for nothing.
    """
    import roleplay
    if not name:
        # no name given: just solve whatever is underfoot
        try:
            return utility.do_tasks() or "did the task here"
        except Exception as exc:
            raise ActionError(str(exc))

    wanted = str(name).strip()
    try:
        G = utility.load_G(utility.getGameData()["map_id"])
    except Exception as exc:
        raise ActionError(f"no map graph: {exc}")

    task = roleplay.find_task(wanted)
    if task is None:
        available = roleplay.outstanding_tasks()
        raise ActionError(
            f"no outstanding task called {wanted!r}. "
            f"Outstanding: {', '.join(available) if available else 'none'}")
    task_name, location = task
    if location:
        pos = roleplay.room_position(G, location)
        if pos is None:
            raise ActionError(f"task {task_name!r} is in {location!r}, "
                              f"which is not a room I recognise")
        if not roleplay.walk_to(G, pos[0], pos[1]):
            raise ActionError(f"could not walk to {location} for {task_name}")
        # let the walk settle before the minigame is opened
        time.sleep(0.4)
    try:
        ok = utility.do_tasks()
    except Exception as exc:
        raise ActionError(f"solving {task_name} failed: {exc}")
    if not ok:
        raise ActionError(f"the solver could not complete {task_name} at {location}")
    return f"completed {task_name} in {location}"


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
    # The cooldown is the model's business, not the harness's, so give it the
    # number rather than deciding on its behalf that the kill is unavailable.
    if ab.get("isimpostor") == "1":
        try:
            cd = utility.get_killCD()
            bits.append(f"kill cooldown: {cd}")
        except Exception:
            pass
        bits.append(f"can kill right now: {ab.get('cankill') == '1'}")
    if data.get("inMeeting") == "1":
        bits.append("a meeting is running")
    if ab.get("invent") == "1":
        bits.append("you are inside a vent")
    if ab.get("isdead") == "1":
        bits.append("you are dead")
    try:
        if utility.is_urgent_task():
            bits.append(f"an urgent task is up: {utility.is_urgent_task()}")
    except Exception:
        pass
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
    "do_task": (("task",), do_task, "do_task <task> - walk to a task and complete it"),
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
    ]
    # The model cannot ask to go somewhere whose name it does not know, so the
    # room list is part of the prompt rather than something it has to guess.
    try:
        import roleplay as _rp
        rooms = _rp.known_rooms()
        if rooms:
            lines.append("Rooms on this map: " + ", ".join(rooms))
        # likewise: it cannot do a task it has not been told about
        tasks = _rp.outstanding_tasks()
        if tasks:
            lines.append("Tasks you still have to do: " + ", ".join(tasks))
        if rooms or tasks:
            lines.append("")
    except Exception:
        pass
    lines += [
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


# The model talks like a person, not like an API. These map ordinary phrasings
# onto the action table. This does NOT widen what is possible: every entry here
# still resolves to an action that already existed, and a verb with no entry is
# still rejected outright.
PHRASES = [
    (r"^go\s+to\s+(?:the\s+)?(.+)$", "go_to", 1),
    (r"^(?:head|walk|move|run|travel|return|go)\s+(?:to|over\s+to|towards?)\s+(?:the\s+)?(.+)$", "go_to", 1),
    (r"^(?:go|walk)\s+(?!to\b|over\b|towards?\b)(\w+)$", "go_to", 1),
    (r"^stop(?:\s+walking)?$", "stop", None),
    (r"^(?:stand\s+still|hold\s+position|hold\s+still|do\s+nothing|nothing|wait|idle)$", "wait", None),
    (r"^kill(?:\s+(?:the\s+)?(?:\w+))?$", "kill", None),
    (r"^murder\s+(?:\w+)$", "kill", None),
    (r"^report(?:\s+(?:the\s+)?body)?$", "report", None),
    (r"^sabotage\s+(?:the\s+)?(.+)$", "sabotage", 1),
    (r"^queue\s+sabotage\s+(?:the\s+)?(.+)$", "queue_sabotage", 1),
    (r"^use\s+(?:my\s+)?ability\s*2$", "ability2", None),
    (r"^use\s+(?:my\s+)?secondary\s+ability$", "ability2", None),
    (r"^use\s+(?:my\s+)?ability\s*1$", "ability", None),
    (r"^use\s+(?:my\s+)?(?:primary\s+)?ability$", "ability", None),
    (r"^use\s+ability$", "ability", None),
    (r"^(?:protect|shield|guard)\s+(?:the\s+)?(\w+)$", "protect", 1),
    (r"^mimic\s+(?:the\s+)?(\w+)$", "mimic", 1),
    (r"^(?:shapeshift\s+(?:into|to)\s+)(?:the\s+)?(\w+)$", "mimic", 1),
    (r"^interrogate(?:\s+.*)?$", "interrogate", None),
    (r"^(?:read|open|check)\s+(?:my\s+)?notes$", "notes", None),
    (r"^overrule\s+(\w+)$", "overrule", 1),
    # "do the wiring task" -> the wiring. Must not swallow the article, hence the
    # lookahead: without it "do a task" backtracks to capturing "a".
    (r"^(?:do|complete|finish)\s+(?:(?:a|the|my)\s+)?(?!a\b|the\b|my\b)(.+?)\s+task$", "do_task", 1),
    (r"^(?:do|complete|finish)\s+(?:a\s+|the\s+|my\s+)?task\s+(?:in\s+|at\s+)?(?:the\s+)?(.+)$", "do_task", 1),
    (r"^(?:do|complete|finish)\s+(?:a\s+|the\s+|my\s+)?task$", "do_task", "here"),
    (r"^go\s+(?:do|complete|finish)\s+(?:the\s+)?(.+?)(?:\s+task)?$", "do_task", 1),
    (r"^say\s+(?:to\s+(?:the\s+)?chat\s+)?[\"']?(.+?)[\"']?$", "say", 1),
    (r"^(?:vote\s+for\s+|vote\s+|eject\s+)(\w+)$", "vote", 1),
    (r"^skip(?:\s+(?:the\s+)?vote)?$", "vote", None),
    (r"^(?:observe|check|look\s+at|read)\s+(?:the\s+)?(\w+)$", "observe", 1),
]

def _normalise(line):
    """Best-effort mapping of a human sentence onto (name, arg|None)."""
    import re
    low = line.strip().strip("`").strip().strip('"').strip("'")
    for pattern, name, group in PHRASES:
        m = re.match(pattern, low, re.IGNORECASE)
        if not m:
            continue
        if group is None:
            if name == "vote":
                return "vote", "skip"
            return name, None
        if isinstance(group, str):
            # a fixed argument, e.g. do_task with no name means "the one here"
            return name, group
        arg = m.group(group)
        if not arg:
            # an optional capture that did not participate
            return name, None
        arg = re.sub(r"^(the|a|an)\s+", "", arg.strip(), flags=re.IGNORECASE)
        if not arg:
            return name, None
        return name, arg
    return None, None


def parse_action(reply):
    """Turn one line of model output into (name, [args]). None if unusable."""
    if not reply:
        return None, None
    line = reply.strip().splitlines()[0].strip()
    line = line.strip("`").strip()
    for prefix in ("action:", "action =", "call:", "tool:", "I will", "i will"):
        if line.lower().startswith(prefix):
            line = line[len(prefix):].strip()

    parts = line.replace("=", " ").split()
    name = parts[0].lower().strip(",.:;")

    # The specific English patterns are tried first. Otherwise "sabotage the
    # lights" matches the literal name "sabotage" and swallows "the" as its
    # argument, and "vote for RED" swallows "for".
    got, arg = _normalise(line)
    if got is not None and got in ACTIONS:
        required, _fn, _desc = ACTIONS[got]
        if required and not arg:
            return None, line          # e.g. "go to" with nowhere to go
        return got, [arg] if required else []

    if name in ACTIONS:
        args = [p.strip(",.;:\"'") for p in parts[1:]]
        required, _fn, _desc = ACTIONS[name]
        if len(args) >= len(required):
            return name, args[:len(required)]
        return None, line

    return None, line


def run_action(name, args):
    """Execute one action. Raises ActionError if it is not legal right now."""
    _required, handler, _desc = ACTIONS[name]
    return handler(*args)
