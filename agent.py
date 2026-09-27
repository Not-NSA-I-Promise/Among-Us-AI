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


# ------------------------------------------------------------------- faking
def fake_task(name, visual=False):
    """Pretend to do a task, for as long as a real one takes.

    The point is the WAIT. An impostor who leaves a panel in one second is
    caught; one who stands there for the real duration is not, even though the
    task bar never moves.

    Visual tasks (MedBay scan, Start Reactor, Asteroids, Chart Course) are
    refused by default, because other players can see the task happening and
    standing still does not imitate it. Pass visual=True to override.
    """
    import importlib.util
    ts = os.path.join(os.path.dirname(os.path.realpath(__file__)), "task-solvers")
    spec = importlib.util.spec_from_file_location(
        "fakemod", os.path.join(ts, "fake_task.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    result = mod.fake_task(str(name), allow_visual=bool(visual))
    if not result.get("ok"):
        raise ActionError(result.get("reason", "could not fake that"))
    # Report the honest caveat rather than claiming the task got done.
    return (f"faked {result['task']} for {result['seconds']}s "
            f"(timing only - the task bar did not move)")


# ------------------------------------------------------------------- venting
def vent():
    """Go into a vent, or travel to a connected one if already inside.

    Requires canvent. The game refuses otherwise, and the refusal is reported
    back rather than swallowed.
    """
    import roleplay
    ability = botlink.read_ability()
    if ability.get("canvent") != "1":
        raise ActionError("your role cannot vent")
    if ability.get("isdead") == "1":
        raise ActionError("you are dead")
    try:
        G = utility.load_G(utility.getGameData()["map_id"])
    except Exception as exc:
        raise ActionError(f"no map graph: {exc}")

    if ability.get("invent") == "1":
        # already in a vent: travel to one of the connected ones
        options = botlink.read_vent_options()
        if not options:
            raise ActionError(
                "you are in a vent but the game reported no travel options. "
                "Nothing is in range to travel to.")
        target = options[0][0]
        for vid, _x, _y in options:
            if vid != options[0][0]:
                target = vid
                break
        if botlink.vent_travel(target):
            return f"travelled to vent {target}"
        raise ActionError(f"the game refused to travel to vent {target}: "
                          f"{botlink.last_result()}")

    ok = roleplay.vent_turn(G, force=True)
    if not ok:
        raise ActionError("could not reach a vent or get into one")
    return "entered a vent"


# ------------------------------------------------------------------ tasks
def do_task(name=None):
    """Walk to a task panel, then run its solver.

    Two things were wrong here. The bot did not WALK to the panel first, so the
    solver - which drives the mouse - ran at whatever spot it happened to be
    standing in; and it reported "completed" purely on the solver's exit code,
    which is 0 even when the solver did nothing useful.

    So: resolve the task, walk to its panel, press USE to open it, run the
    solver, and then CHECK whether the task actually went away. The result
    reported to the model distinguishes done from attempted.
    """
    import roleplay
    import solver

    # This was inverted. `not isImpostor()` is true for a CREWMATE, so a
    # crewmate got refused with a message about being an impostor, and then
    # idled for the whole round. The condition and the message have to agree.
    if utility.isImpostor() and not utility.isDead():
        raise ActionError("you are an impostor - do not complete real tasks, "
                          "use fake_task instead to look busy")
    if utility.isDead():
        raise ActionError("you are dead - ghosts cannot do tasks")

    if not name:
        here = _tasks_here()
        if not here:
            raise ActionError("there is no task in this room to do")
        name = here[0]

    wanted = str(name).strip()
    match = roleplay.find_task(wanted)
    if match is None:
        available = roleplay_outstanding()
        raise ActionError(
            f"you do not have a task called {wanted!r}. "
            f"You still have: {', '.join(available) if available else 'nothing'}")
    task_name = match[0]

    here = _tasks_here()
    if task_name not in here:
        route = roleplay.task_route(task_name)
        loc = roleplay_locations().get(task_name, "another room")
        if here:
            raise ActionError(
                f"{task_name} is not in this room. "
                f"Tasks in this room: {', '.join(here)}. "
                f"{task_name} is in {loc} - use go_to {loc} first")
        raise ActionError(
            f"there is no task in this room. {task_name} is in {loc} - "
            f"use go_to {loc} first")

    # Stand at the actual panel. The room name is not enough: the panel is a
    # specific spot in the room, and a solver that clicks pixels needs to be
    # standing at it.
    route = roleplay.task_route(task_name)
    walked = ""
    if route:
        stage = route[0]
        if not _walk_near(G=None, target=stage, task=task_name):
            raise ActionError(f"could not walk to the {task_name} panel")
        walked = f" at {stage[0]:.1f},{stage[1]:.1f}"
        time.sleep(0.3)
        # USE opens the panel; without it the solver has nothing to work on
        try:
            import roleplay as _rp
            _rp.press_use()
            time.sleep(0.6)
        except Exception:
            pass
    else:
        # No route published. Fall back to the task database's position for the
        # room we are in, which is what the old state machine used.
        pos = _panel_position(task_name)
        if pos:
            if not _walk_near(G=None, target=pos, task=task_name):
                raise ActionError(f"could not walk to the {task_name} panel")
            walked = f" at {pos[0]:.1f},{pos[1]:.1f}"
            time.sleep(0.3)
            try:
                import roleplay as _rp
                _rp.press_use()
                time.sleep(0.6)
            except Exception:
                pass
        else:
            raise ActionError(
                f"no position is known for the {task_name} panel, so the solver "
                f"would run in the wrong place. Try again, or use observe state "
                f"to check where you are")

    before = len(roleplay_outstanding())
    try:
        rc = solver.solve_task(task_name=task_name)
    except Exception as exc:
        raise ActionError(f"solving {task_name} failed: {exc}")
    if rc == 1:
        raise ActionError(f"a meeting interrupted {task_name}")
    if rc == 2:
        return f"started {task_name}{walked} - it finishes later (it is timed)"

    # Verify. solve_task returns 0 when the subprocess exited, which says nothing
    # about whether anything was solved.
    time.sleep(0.4)
    after = roleplay_outstanding()
    if task_name not in after:
        return f"completed {task_name}{walked}"
    if len(after) < before:
        return f"partly did {task_name}{walked} - still outstanding"
    return (f"attempted {task_name}{walked} but the task is still showing as "
            f"outstanding, so it was NOT completed")


def _walk_near(G=None, target=None, task=""):
    """Walk to a world position. Thin wrapper so do_task stays readable."""
    try:
        import roleplay
        if G is None:
            G = utility.load_G(utility.getGameData()["map_id"])
        return roleplay.walk_to(G, target[0], target[1])
    except Exception as exc:
        print(f"  walk to {task} failed: {exc}")
        return False


def _panel_position(task_name):
    """A task's panel position, from the repo's task database."""
    try:
        import roleplay
        d = utility.load_dict()
    except Exception:
        return None
    entry = d.get(task_name)
    if not entry:
        return None
    room = str(_current_room()).lower()
    for loc, pos in entry.items():
        if loc.lower() == room:
            try:
                return tuple(pos)
            except Exception:
                return None
    for _loc, pos in entry.items():
        try:
            return tuple(pos)
        except Exception:
            continue
    return None


def _current_room():
    try:
        return utility.getGameData().get("room", "")
    except Exception:
        return ""


# ---------------------------------------------------------------- social
def say(message):
    """Say something in the meeting or in-game chat.

    Goes through the game's own chat RPC via the plugin, so the message is
    indistinguishable from a typed one. This used to call a chatGPT.say() that
    never existed, so speaking was impossible and the model could only vote.
    """
    text = str(message).strip()
    if not text:
        raise ActionError("say needs something to say")
    if botlink.say(text):
        return f"said: {text}"
    raise ActionError(f"the game would not send it: {botlink.last_result()}")


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


def roleplay_outstanding():
    import roleplay
    return roleplay.outstanding_tasks()


def roleplay_locations():
    """Task name -> the room it is in, so a refusal can say where to go."""
    import roleplay
    out = {}
    try:
        data = utility.getGameData()
    except Exception:
        return out
    names = data.get("tasks") or []
    locs = data.get("task_locations") or []
    for i, n in enumerate(names):
        if i < len(locs):
            out[n] = locs[i].split("|")[0].strip()
    return out


def _role_guidance(role, is_imp, ab):
    """Role-specific judgement, as advice in the prompt.

    Not enforced by the harness - it is the model's decision, which is the point.
    But the model has no way to know these rules unless it is told them, and a
    base model will happily shapeshift next to a witness or interrogate a
    random player.

    Every role in the game has an entry. A missing one is a role playing blind,
    so an unknown role gets the generic fallback rather than nothing.
    """
    # Specific role advice is checked BEFORE the generic impostor advice, or an
    # impostor Shapeshifter and a Viper would only ever be told the generic
    # version and their own rules would be unreachable.
    if role == "Shapeshifter":
        return ("Do NOT shapeshift while a crewmate is near you - they will see the "
                "transformation and you are dead. Only do it when nobody is near, "
                "and mimic someone who has not been accused yet.")
    if role == "Viper":
        return ("You can kill from inside a vent. Vent when nobody can see you, and "
                "kill from there rather than on foot.")
    if role == "Phantom":
        return ("Ability 1 makes you invisible and is usable even as a crewmate, so "
                "using it is never suspicious. Ability 2 leaves a decoy - place it "
                "somewhere you have already left. If you are an impostor, kill "
                "behind a closed door and then vanish to cover the discovery.")

    if is_imp:
        return ("As an impostor: fake a task before you do anything else, because "
                "standing still doing nothing is what an impostor looks like. If "
                "your fellow impostor has just killed and a crewmate is nearby, "
                "kill that crewmate too - a double kill ends the round. Do not "
                "shapeshift or stand in the open next to a witness.")
    if role == "Detective":
        return ("Do NOT interrogate a random player. Your ability is worth spending "
                "on a body, or on someone who was near a body, or on someone who "
                "was following or chasing a player. A player nobody can account "
                "for is the right target; a player with a solid alibi is not. Read "
                "your notes before you report and say only what they say.")
    if role == "Judge":
        return ("Do NOT spend your overrule on a hunch. Wait until you have real "
                "information: you witnessed them near a kill, they vented, a body "
                "was found where they were, or nobody can say where they were. A "
                "vent-kill is enough. One bad overrule costs you the whole game.")
    if role == "Engineer":
        return ("You can vent for movement, and saying so is a good alibi rather "
                "than a giveaway. Venting proves nothing on its own.")
    if role == "Noisemaker":
        return ("Your decoy arrow pulls players toward wherever you place it. Put "
                "it somewhere you have already left, ideally near a body, so the "
                "group walks away from where you actually are.")
    if role == "Scientist":
        return ("Vitals tell you who is dead and who is disconnected. If bodies have "
                "been found but nobody is dead on vitals, a vent happened - that is "
                "the strongest thing you can tell the room.")
    if role == "Tracker":
        return ("You CANNOT vent. Track someone you have actually seen, and turn "
                "where they went into a specific thing to say in the meeting.")
    if role == "Guardian Angel":
        return ("Shield the player the evidence actually points at, not a random "
                "one. Remember bodies and who was near them.")
    if role == "Crewmate":
        return ("Ask 'who followed you' - that question catches more impostors than "
                "asking who was near the body. If you did not see something, do "
                "not claim you did. Skip the vote if you have no information.")
    if role == "Impostor":
        return ("As an impostor: fake a task before you do anything else, because "
                "standing still doing nothing is what an impostor looks like. If "
                "your fellow impostor has just killed and a crewmate is nearby, "
                "kill that crewmate too - a double kill ends the round.")
    # An unknown or newly added role still gets the general impostor advice if it
    # is on that side, rather than nothing at all.
    if is_imp:
        return ("As an impostor: fake a task before you do anything else, because "
                "standing still doing nothing is what an impostor looks like. Never "
                "kill or vote your fellow impostor.")
    return ("Stay with a group if you can - two players together is very hard to "
            "kill cleanly. Do not claim you saw something you did not see.")


def _map_support_warning():
    """Say plainly when the current map cannot be played.

    Only Skeld and Polus ship with a movement graph. On the other three the bot
    cannot walk anywhere, so every movement action would fail, and the model
    would burn the round on refusals. Better to say so once, up front, than to
    have it discover it a hundred times.
    """
    try:
        data = utility.getGameData()
        if not data:
            return ""
        key = utility.normalize_map(data.get("map_id"))
        graph, db = False, False
        for k, g, d in utility.available_maps():
            if k == key:
                graph, db = g, d
        if graph and db:
            return ""
        missing = []
        if not graph:
            missing.append("no movement graph (so go_to and do_task cannot work)")
        if not db:
            missing.append("no task database (so task positions are unknown)")
        usable = [k for k, g, d in utility.available_maps() if g and d]
        return (f"WARNING: this map ({key}) is not fully supported - "
                f"{'; '.join(missing)}. Fully supported maps: "
                f"{', '.join(usable) or 'none'}. Expect movement to fail.")
    except Exception:
        return ""


def _brief_state():
    data = utility.getGameData()
    if not data:
        # getGameData() returns None when the plugin has not written a complete
        # snapshot yet - which is exactly the "get INTO a match first" state.
        # Indexing into it raised TypeError and killed the loop.
        return ("no game data yet - you are not in a match, or the plugin has not "
                "published a snapshot. Do nothing until this changes.")
    role = botlink.get_role()
    ab = botlink.read_ability()
    living = _living_players()
    near = _nearby_players()
    is_imp = ab.get("isimpostor") == "1"
    bits = [
        f"you are {role} ({'impostor' if is_imp else 'crew'})",
        f"in {data['room']}",
        f"alive: {', '.join(living) if living else 'you are alone'}",
    ]
    if near:
        bits.append(f"near you RIGHT NOW: {', '.join(near)}")
    else:
        bits.append("nobody near you right now")

    # Fellow impostors. An impostor needs to know who not to kill and who not to
    # vote, and it needs to know before it acts, not after.
    if is_imp:
        try:
            mates = [m for m in utility.get_fellow_imposters() if m]
            if mates:
                bits.append(f"your fellow IMPOSTOR: {', '.join(mates)} - never kill or vote them")
        except Exception:
            pass

    # Tasks in this room. Without this the model has no idea it is standing at a
    # panel, which is most of why it walked the map doing nothing. Only the tasks
    # underfoot are offered, because a task in another room is a `go_to`, not a
    # `do_task` - asking for it wastes the turn and looks like guessing.
    try:
        here = _tasks_here(data)
    except Exception:
        here = []
    if here:
        if is_imp:
            bits.append("tasks you could FAKE in THIS room: " + ", ".join(here))
        else:
            bits.append("tasks you can do in THIS room right now: " + ", ".join(here))
    else:
        bits.append("no task in this room")
        try:
            outstanding = roleplay_outstanding()
        except Exception:
            outstanding = []
        if outstanding:
            where = roleplay_locations()
            hints = ", ".join(f"{t} ({where.get(t, '?')})" for t in outstanding[:3])
            bits.append(f"your remaining tasks are elsewhere: {hints} - use go_to")

    # The cooldown is the model's business, not the harness's, so give it the
    # number rather than deciding on its behalf that the kill is unavailable.
    if is_imp:
        try:
            cd = utility.get_killCD()
            bits.append(f"kill cooldown: {cd}")
        except Exception:
            pass
        bits.append(f"can kill right now: {ab.get('cankill') == '1'}")
        bits.append("if your fellow impostor has just killed near a crewmate, "
                    "killing that crewmate too is a double kill and wins you the round")

    if _in_meeting():
        bits.append("a MEETING IS RUNNING - you can only say, observe and vote")
    if _in_vent(ab):
        bits.append("you are inside a vent")
    if ab.get("isdead") == "1":
        bits.append("you are dead")

    chat = _chat_transcript()
    if chat:
        bits.append("what everyone has said so far: " + chat)
    try:
        urgent = utility.is_urgent_task()
        if urgent:
            bits.append(f"an urgent task is up: {urgent}")
    except Exception:
        pass

    guidance = _role_guidance(role, is_imp, ab)
    if guidance:
        bits.append(guidance)
    warn = _map_support_warning()
    if warn:
        bits.append(warn)
    return "; ".join(bits)


def _tasks_here(data=None):
    """Outstanding tasks located in the room the bot is standing in.

    This is the piece that was missing: the model was told its whole task list
    and the whole room list, but never which tasks were underfoot, so it had to
    guess whether doing anything was even possible where it stood.
    """
    try:
        data = data or utility.getGameData()
    except Exception:
        return []
    if not data:
        return []
    room = str(data.get("room", "") or "").strip().lower()
    if not room:
        return []
    names = data.get("tasks") or []
    locs = data.get("task_locations") or []
    here = []
    for i, name in enumerate(names):
        if i >= len(locs):
            continue
        raw = locs[i]
        if not isinstance(raw, str):
            continue
        parts = [p.strip() for p in raw.lower().split("|")]
        if room in parts:
            here.append(name)
    return here


def _in_meeting():
    """True if a meeting is running. Tolerates bool or the string '1'."""
    try:
        v = utility.getGameData().get("inMeeting")
    except Exception:
        return False
    if isinstance(v, str):
        return v.strip() in ("1", "True", "true")
    return bool(v)


def _in_vent(ab=None):
    ab = ab if ab is not None else botlink.read_ability()
    return ab.get("invent") == "1"


def _chat_transcript(limit=8):
    """What the other players have actually said.

    This is the single most important input in a social deduction game and it
    was being thrown away. The plugin already captures every chat message into
    chatData.txt; nothing was reading it into the prompt, so the model had no
    idea what the room was arguing about when it was asked to vote.
    """
    try:
        msgs = utility.get_chat_messages()
    except Exception:
        return ""
    msgs = [m.strip() for m in msgs if m and m.strip()]
    if not msgs:
        return ""
    if len(msgs) > limit:
        msgs = msgs[-limit:]
    return " | ".join(msgs)


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
    "fake_task": (("task",), fake_task, "fake_task <task> - pretend to do a task, taking the real time"),
    "vent": ((), vent, "vent - go into a vent, or travel to a connected one if inside"),
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
        is_imp = False
        try:
            is_imp = botlink.read_ability().get("isimpostor") == "1"
        except Exception:
            pass
        tasks = _rp.outstanding_tasks()
        if tasks and is_imp:
            # An impostor's task list is a cover story, never real work. Telling
            # an imp to "do" a task is nonsense - it made the model try to
            # solve Start Reactor while trying to kill people.
            lines.append("You are an IMPOSTOR. The tasks below are your cover "
                         "story - never actually complete one, because real "
                         "progress gives you away. Use fake_task to stand at a "
                         "panel for the right length of time.")
            lines.append("Your fake task list: " + ", ".join(tasks))
        elif tasks:
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
    (r"^(?:go\s+)?vent$", "vent", None),
    (r"^vent\s+(?:to\s+(?:a\s+|the\s+)?)?(\w+)$", "vent", None),
    (r"^(?:hide|enter|get)\s+(?:in|into)\s+(?:a\s+|the\s+)?vent$", "vent", None),
    (r"^(?:fake|pretend)\s+(?:i'?m\s+|im\s+|to\s+be\s+)?(?:doing\s+)?(?:a\s+|the\s+)?(?:task\s+)?(.+)$", "fake_task", 1),
    (r"^(?:look\s+like)\s+(?:i(?:'m| am)\s+)?doing\s+(?:a\s+|the\s+)?(.+)$", "fake_task", 1),
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
            if required:
                # Task names are multi-word. "do_task Fix Wiring" must keep
                # "Fix Wiring", not collapse to "Fix", or find_task gets half a
                # name and the solver has nothing to work with.
                if name in ("do_task", "fake_task"):
                    return name, [" ".join(parts[1:]).strip(",.;:\"'")]
                return name, args[:len(required)]
            return name, []
        return None, line

    # A bare task name, with no verb at all: "fix wiring", "swipe card", "wires".
    # The model asked for the wires exactly like this and the parser had no way to
    # read it, so it stood there doing nothing - which to the rest of the lobby is
    # indistinguishable from an impostor faking a task. Matching against the real
    # outstanding list means the model's own wording is enough.
    matched = _match_outstanding_task(line)
    if matched:
        try:
            is_imp = botlink.read_ability().get("isimpostor") == "1"
        except Exception:
            is_imp = False
        verb = "fake_task" if is_imp else "do_task"
        # only when a task really was named, so this cannot swallow typos
        return verb, [matched]

    # A bare sentence during a meeting is speech. The model was told to prefix
    # with `say`, and often does, but a chatty reply like "i think red is sus"
    # otherwise parsed as nothing - which is the same failure as not being able
    # to speak at all. Restricted to meetings, to a plausible chat length, and
    # only when it reads like a sentence rather than a typo.
    if _looks_like_speech(line):
        return "say", [line]

    return None, line


def _looks_like_speech(line):
    """Is this a chat message rather than a typo or an invented verb?"""
    s = str(line).strip()
    if not s or len(s) > 120 or len(s) < 3:
        return False
    if not _in_meeting():
        return False
    # a wall of no-spaces, camelCase or symbols is code or a typo, not speech
    if any(ch in s for ch in "{}[]<>|\\`~*#@$%^&_="):
        return False
    if "_" in s and " " not in s:
        return False
    words = s.split()
    if len(words) > 20:
        return False
    # must start like a sentence a player would type
    if not (words[0].lower().endswith("i") or words[0].lower() in (
            "i", "im", "no", "yes", "red", "blue", "green", "yellow", "pink",
            "white", "black", "purple", "cyan", "brown", "orange", "lime",
            "rose", "banana", "skip", "vote", "who", "what", "where", "why",
            "stop", "wait", "its", "thats", "there", "he", "she", "they", "it",
            "not", "can", "dont", "do", "we", "you", "ur", "ok", "wait")):
        return False
    return True


def _match_outstanding_task(text):
    """If `text` names one of the bot's outstanding tasks, return the real name."""
    t = str(text).strip().strip("\"'`.,;:!?")
    if not t or len(t) < 3:
        return None
    try:
        import roleplay
        found = roleplay.find_task(t)
    except Exception:
        return None
    return found[0] if found else None


def run_action(name, args):
    """Execute one action. Raises ActionError if it is not legal right now."""
    _required, handler, _desc = ACTIONS[name]
    return handler(*args)
