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
    if ok:
        return ok
    raise ActionError("the kill did not happen - the game did not report a new "
                      "body, so nothing was killed")


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
_FAKED_ONCE = set()


def fake_task(name, visual=False):
    """Pretend to do a task, for as long as a real one takes.

    The point is the WAIT. An impostor who leaves a panel in one second is
    caught; one who stands there for the real duration is not, even though the
    task bar never moves.

    Two rules that make it actually convincing, and that were missing:

    - You have to BE at the task, and the bot WALKS there for you, because the
      panel coordinates are known. Faking Swipe Card from across Admin, or from
      the wrong end of Electrical, does not look like swiping a card - it looks
      like someone loitering. So it walks to the right panel and opens it.
    - Only fake a given task once. Standing at the same panel twice doing nothing
      is far more suspicious than doing nothing once, because the impostor task
      list is short and known.

    Visual tasks (Submit Scan, Clear Asteroids, Prime Shields, and Skeld Empty
    Garbage/Chute at the Storage stage) are refused by default, because other
    players can see them and standing still does not imitate them. Which tasks
    are visual depends on the map and the stage, so that is checked against the
    live map rather than a flat list. Pass visual=True to override.
    """
    import importlib.util
    ts = os.path.join(os.path.dirname(os.path.realpath(__file__)), "task-solvers")
    spec = importlib.util.spec_from_file_location(
        "fakemod", os.path.join(ts, "fake_task.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    wanted = str(name).strip()
    if wanted in _FAKED_ONCE:
        done = sorted(_FAKED_ONCE)
        raise ActionError(
            f"you already faked {wanted}. Faking the same task twice is very "
            f"suspicious - the impostor task list is short and other players "
            f"notice. Already faked: {', '.join(done)}. Fake something else, or "
            f"do something useful instead.")

    real = _match_outstanding_task(wanted)
    if real is None:
        raise ActionError(
            f"{wanted!r} is not on your fake task list, so faking it would give "
            f"you away. Outstanding: {', '.join(roleplay_outstanding()) or 'none'}")

    # Walk to the panel. This reuses _stand_at_panel, the same routine that
    # makes real tasks work, rather than a second copy of it: the copy here only
    # consulted the static task database, ignored the live route the plugin
    # publishes for multi-stage panels, and silently did nothing when the
    # database had no entry for the room we were standing in.
    walked = ""
    here = _tasks_here()
    if real not in here:
        room = roleplay_locations().get(real, "")
        note = f"{real} is in {room}" if room else f"{real} is elsewhere"
        refusal = _stand_at_panel(real)
        if refusal:
            raise ActionError(f"could not get to the {real} panel to fake it: "
                              f"{refusal}")
        walked = " (walked to the panel)"
        if real not in _tasks_here():
            raise ActionError(f"walked to {note} but the {real} panel is not here - "
                              f"ask go_to for {room} and try again")
    else:
        walked = ""

    # The visual/fakeable rules are map- and stage-specific, so the live map and
    # the stage we are actually standing at have to be passed in. A flat
    # per-task flag was wrong: Prime Shields is visual on Skeld but not Mira HQ,
    # and Skeld Empty Garbage is only visual at the Storage stage.
    _map, _stage = _here_context(real)
    result = mod.fake_task(real, allow_visual=bool(visual),
                           map_name=_map, stage=_stage)
    if not result.get("ok"):
        raise ActionError(result.get("reason", "could not fake that"))
    _FAKED_ONCE.add(real)
    # Report the honest caveat rather than claiming the task got done, and say
    # whether the bot had to walk there first.
    return (f"faked {result['task']}{walked} for {result['seconds']}s "
            f"(timing only - the task bar did not move)")


def faked_tasks():
    return sorted(_FAKED_ONCE)


def reset_for_new_round():
    """Clear per-round state. Called when a game ends, not every turn.

    Without this, the "faked once" list survived the whole process, so after one
    game the bot refused to fake ANY task ever again - the set only lived in
    memory and nothing ever emptied it. Same for the `wait` cooldown, which
    should not carry into a fresh game.
    """
    global _wait_used_at
    _FAKED_ONCE.clear()
    _wait_used_at = None


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
        # already in a vent: travel to one of the connected ones. The plugin only
        # writes ventOptions.txt while we are inside a vent, and only on its own
        # tick, so reading it the instant we get in races that write and comes
        # back empty - which is why travelling looked broken while entering
        # worked. Poll briefly for it instead of giving up on the first miss.
        options = []
        for _ in range(10):
            options = botlink.read_vent_options()
            if options:
                break
            time.sleep(0.25)
        if not options:
            raise ActionError(
                "you are in a vent but the game never reported any travel "
                "options after waiting. You may be in a vent with nothing "
                "connected to it - leave it with `go_to` to somewhere else.")
        # travel to a DIFFERENT vent, not back to the one we are in
        here = options[0][0]
        target = None
        for vid, _x, _y in options:
            if vid != here:
                target = vid
                break
        if target is None:
            raise ActionError(
                f"vent {here} has nothing connected to it, so there is nowhere "
                f"to travel to. Leave it with `go_to`.")
        if botlink.vent_travel(target):
            return f"travelled to vent {target} (from vent {here})"
        raise ActionError(f"the game refused to travel to vent {target}: "
                          f"{botlink.last_result()}")

    ok = roleplay.vent_turn(G, force=True)
    if not ok:
        raise ActionError("could not reach a vent or get into one")
    return "entered a vent"


# ------------------------------------------------------------------ tasks
def do_task(name=None):
    """Work through a task to completion, one stage at a time.

    Three things were wrong here, in order of how badly they hurt:

    1. It did not walk to the panel. solver.solve_task just spawns a script that
       drives the mouse; it assumes you are standing at the panel. The old state
       machine walked first and that step was lost when the model took over.
    2. It did only ONE stage. Fix Wiring is three panels and Divert Power is two,
       so a single pass can never complete either - the log showed the wire being
       "connected" and the counter still reading 0/3. PlayerTask.Locations holds
       only the CURRENT panel (the game re-points it between stages, which is why
       taskRoutes.txt has one position per task), so the way through is to
       re-read where the game says the task is now and walk there again.
    3. It reported completion on the solver's exit code, which is 0 whenever the
       subprocess exits. It now compares stage counts before and after.

    Returns a description of what actually happened, including honest partial
    progress, so the model is never told a task finished when it did not.
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
        room = _current_task_room(task_name)
        if here:
            raise ActionError(
                f"{task_name} is not in this room. "
                f"Tasks in this room: {', '.join(here)}. "
                f"{task_name} is in {room} - use go_to {room} first")
        raise ActionError(
            f"there is no task in this room. {task_name} is in {room} - "
            f"use go_to {room} first")

    total = _stage_total(task_name) or 1
    done = 0
    notes = []
    last_room = None
    stalled = 0

    # One pass per remaining stage. The game re-points the task between stages,
    # so each iteration re-reads where it is now.
    for attempt in range(int(total) + 1):
        if roleplay.task_is_complete(task_name):
            break
        if utility.isDead():
            notes.append("died partway")
            break
        try:
            if utility.in_meeting():
                notes.append("a meeting started")
                break
        except Exception:
            pass

        room = _current_task_room(task_name)
        if room and room.lower() == (utility.getGameData().get("room", "") or "").lower():
            here_now = _tasks_here()
            if task_name not in here_now:
                # the room name matches but the panel is not here, so the game
                # has re-pointed the task somewhere else in this room
                stalled += 1
                if stalled >= 2:
                    notes.append(f"the game kept re-pointing {task_name} and no "
                                 f"stage completed")
                    break
        if room and room != last_room:
            last_room = room
        done = _stage_count(task_name) or 0

        walked = _stand_at_panel(task_name)
        if walked.startswith("could not"):
            notes.append(walked)
            break

        before = _stage_count(task_name) or 0
        try:
            rc = solver.solve_task(task_name=task_name)
        except Exception as exc:
            raise ActionError(f"solving {task_name} failed: {exc}")
        if rc == 1:
            notes.append("a meeting interrupted it")
            break
        if rc == 2:
            return f"started {task_name}{walked} - it finishes later (it is timed)"

        time.sleep(0.4)
        after = _stage_count(task_name) or 0
        if after > before:
            done = after
            if rc == 3:
                notes.append("the solver crashed afterwards but the stage landed")
            continue
        if rc == 3:
            notes.append("the solver crashed and no stage completed")
            break
        # no progress on a stage that should have advanced
        stalled += 1
        if stalled >= 2:
            notes.append(f"two attempts at {task_name} made no progress - the "
                         f"solver is not completing the panel")
            break

    final = _stage_count(task_name) or 0
    total = _stage_total(task_name) or total
    if roleplay.task_is_complete(task_name) or (total and final >= total):
        msg = f"completed {task_name} ({final}/{total} stages)"
        if notes:
            msg += " - " + "; ".join(notes)
        return msg
    if final > 0:
        nxt = _next_room_for(task_name)
        tail = f"; next part is at {nxt}" if nxt else ""
        why = ("; ".join(notes) if notes else
               "ask for it again once you are at the next panel")
        return (f"did {final}/{total} stages of {task_name} - it is NOT "
                f"finished{tail} ({why})")
    raise ActionError(f"attempted {task_name} but no stage completed, so it was "
                      f"NOT completed"
                      + (f" ({'; '.join(notes)})" if notes else ""))


def _current_task_room(task_name):
    """Where the game currently says this task is.

    task_locations publishes StartAt, and the game moves that between stages for
    tasks like Fix Wiring, so this is re-read every iteration rather than cached.
    """
    try:
        data = utility.getGameData()
    except Exception:
        return ""
    names = data.get("tasks") or []
    locs = data.get("task_locations") or []
    for i, n in enumerate(names):
        if n == task_name and i < len(locs):
            return locs[i].split("|")[0].strip()
    return ""


def _stand_at_panel(task_name):
    """Walk to the current panel. Returns a note, or a refusal.

    It deliberately does NOT open the panel. Pressing USE here opened the
    minigame, and then the solver's own click_use() clicked the on-screen USE
    button again - and with a minigame already open, that click CLOSES it. So
    the solver then dragged wires on a closed panel, which is exactly what was
    seen in a live game: the cursor crossed the screen while the Fix Wiring
    panel was gone.

    Almost every solver already calls click_use() itself, which is the
    convention. So this walks, confirms arrival, and leaves the opening to them.
    """
    try:
        import roleplay
    except Exception as exc:
        return f"could not import movement ({exc})"
    try:
        if utility.in_meeting():
            return "could not reach the panel, a meeting is running"
    except Exception:
        pass

    # refresh=True: the plugin publishes only the CURRENT panel, and it moves
    # between stages, so a cached route points at the panel we already finished.
    route = roleplay.task_route(task_name, refresh=True)
    if route:
        target = route[0]
    else:
        pos = _panel_position(task_name)
        if not pos:
            return (f"no position is known for the {task_name} panel, so the "
                    f"solver would run in the wrong place")
        target = pos
    if not _walk_near(G=None, target=target, task=task_name):
        return f"could not walk to the {task_name} panel"

    # Open the panel HARNESS-side, and confirm it from the game's own state rather
    # than from a screenshot. Minigame.Instance is the authority; every pixel-based
    # "is it open" check that came before was a guess and each one was wrong in a
    # different way.
    #
    # The solver still has its own single click as a fallback, because it may be
    # run on its own, but when the panel is already up the solver must not click
    # again - USE is a toggle and that closes the panel.
    if botlink.read_minigame().get("open"):
        return ""                       # already open: do not touch it
    if utility.in_meeting():
        return "a meeting started before the panel could be opened"
    try:
        import roleplay
        roleplay.press_use()
    except Exception as exc:
        return f"could not press USE to open the {task_name} panel ({exc})"

    state = botlink.minigame_is(task_name, timeout=4.0)
    if not state:
        return (f"the {task_name} panel did not open - the game still reports no "
                f"minigame, so the solver was not run against a closed panel")
    return ""


def _stage_info(name):
    import roleplay
    for n, done, total, room in roleplay.task_progress():
        if n == name:
            return done, total, room
    return None, None, ""


def _stage_count(name):
    return _stage_info(name)[0]


def _stage_total(name):
    return _stage_info(name)[1]


def _next_room_for(name):
    """Where the unfinished part of a task is. Never guesses - see the docstring
    on roleplay.next_stage_room about the MedBay/Electrical mix-up."""
    import roleplay
    done, _total, room = _stage_info(name)
    if done is None:
        return "its remaining room"
    nxt = roleplay.next_stage_room(name, done)
    if nxt:
        return nxt
    if done == 0 and room:
        return room
    return "another panel of it - the game only publishes the first stage"


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


def _here_context(task_name=""):
    """The live map key and the stage number of `task_name`.

    Returns (map_key, stage). Both are needed for the fake-task rules, because
    "is this visual" is not a property of the task alone: Prime Shields lights up
    on Skeld but shows nothing on Mira HQ, and Skeld Empty Garbage is only
    visual at the Storage stage, so its Cafeteria stage can be faked.

    The map is the repo's internal key (SHIP/PB/AIRSHIP/HQ/FUNGLE) because that
    is the vocabulary task_durations.json uses, and the stage comes from the
    same _stage_info the do_task progress check uses, so those two can never
    disagree.
    """
    map_key = ""
    stage = None
    try:
        data = utility.getGameData() or {}
        map_key = utility.normalize_map(data.get("map_id")) or ""
    except Exception:
        pass
    if task_name:
        try:
            done, _total, _room = _stage_info(task_name)
            if done is not None:
                # completed stages, so the one being stood at is the next index
                stage = (int(done) or 0) + 1
        except Exception:
            pass
    return map_key, stage


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
        return ("YOUR ABILITY: appear as another player with `mimic <colour>`. "
                "Do NOT shapeshift while a crewmate is near you - they will see "
                "the transformation and you are dead. Only do it when nobody is "
                "near, and mimic someone who has not been accused yet. If you "
                "have not used it this round, you are wasting the one thing "
                "that makes you hard to pin down.")
    if role == "Viper":
        return ("YOUR ABILITY: vent, and kill THROUGH the vent at longer range. "
                "A ground-level USE press is not a Viper kill - you must be "
                "inside a vent. So: use `vent`, then `kill`. If you are playing "
                "as a crewmate Viper, your vent is for movement and you cannot "
                "kill at all.")
    if role == "Phantom":
        return ("YOUR TWO ABILITIES: `ability` makes you invisible and `ability2` "
                "leaves a decoy of you somewhere you have already left. Ability 1 "
                "works even as a crewmate, so using it is never suspicious and is "
                "a free alibi. As an impostor, kill behind a closed door and then "
                "vanish to cover the window before the doors open. If you are "
                "still visible, do not use it - the animation is seen by anyone "
                "in vision.")
    if role == "Engineer":
        return ("YOUR ABILITY: `vent` for movement anywhere on the ship. You "
                "cannot kill. Venting is not a giveaway for an Engineer, and "
                "saying so unprompted is a good alibi - so use it to get where "
                "you need to be rather than walking.")
    if role == "Scientist":
        return ("YOUR ABILITY: `ability` opens Admin vitals, which tell you who "
                "is dead and who is disconnected. Read them, then say what you "
                "saw - it is checkable, so it carries weight in a meeting. If "
                "bodies have been found but nobody is dead on vitals, a vent "
                "happened, and that is the strongest thing you can tell the room.")
    if role == "Tracker":
        return ("YOUR ABILITY: `ability` tracks one player on the map. Pick "
                "someone you have actually seen, and turn where they went into "
                "one specific thing to say in the meeting. You CANNOT vent. If "
                "you have not tracked anyone this round, you are contributing "
                "nothing - use it.")
    if role == "Noisemaker":
        return ("YOUR ABILITY: `ability` places a decoy arrow that pulls players "
                "toward wherever you put it. Place it somewhere you have already "
                "left, ideally near a body, so the group walks away from where "
                "you actually are.")
    if role == "Detective":
        return ("YOUR TWO ABILITIES: `interrogate` inspects the player or body "
                "you are standing next to, and `notes` reads your notebook. Do "
                "NOT interrogate a random player - spend it on a body, or on "
                "someone near one, or someone nobody can account for. Then read "
                "the notes and report ONLY what they say, without adding a "
                "theory. Interrogating a stranger wastes the ability and teaches "
                "you nothing.")
    if role == "Judge":
        return ("YOUR ABILITY: `overrule <player_id>` spends your one extra vote "
                "to eject. Do NOT use it on a hunch. Wait until you have real "
                "information - you witnessed them near a kill, they vented, a "
                "body was found where they were, or nobody can say where they "
                "were. A vent-kill is enough. One bad overrule costs the game.")
    if role == "Guardian Angel":
        return ("YOUR ABILITY: `protect <colour>` shields a player for the "
                "round. Shield the player the evidence actually points at, not a "
                "random one. You are a ghost, so you have seen things the living "
                "have not - use that.")
    if role == "Crewmate":
        return ("You have no ability. Your job is tasks and information: do your "
                "tasks to look innocent and to make progress, and use what you "
                "actually saw - bodies, cameras, vitals, who was where. Ask "
                "'who followed you'; that question catches more impostors than "
                "asking who was near the body. If you did not see something, do "
                "not claim you did. Skip the vote if you have no information.")

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


def _objective(role, is_imp, data, ab):
    """Why this player should be doing anything at all.

    The model had no goal. It was told what it could do but never what it was
    trying to achieve, so "do the most useful thing" was a meaningless prompt and
    it defaulted to wait. An impostor wins by reaching parity; a crewmate wins by
    finishing the bar and ejecting the impostor.
    """
    if is_imp:
        try:
            alive = len(_living_players()) + 1
        except Exception:
            alive = None
        goal = ("You win when the number of living impostors equals or beats the "
                "living crewmates")
        if alive is not None:
            goal += f". Right now {alive} are alive and you are one of them"
        cds = ab.get("cankill") == "1"
        return (f"YOUR OBJECTIVE: {goal}. Counting you, that is "
                f"{'a kill is available - take it if it is safe' if cds else 'no kill available right now'}. "
                f"Sabotages stall the crew and give you a reason to be away from "
                f"where you killed. Standing still is the one thing that loses "
                f"you the game.")
    prog = ""
    try:
        import roleplay as _rp
        prog = _rp.progress_summary()
    except Exception:
        pass
    # the per-task progress and the bar total are already in the state line, so
    # the objective only restates what to DO, not how far along things are
    return ("YOUR OBJECTIVE: finish the task bar and get every impostor ejected. "
            "Do your tasks to look innocent and to make progress, and use the "
            "things you actually saw - bodies, cameras, vitals, who was where "
            "- to find the impostor. Sitting still achieves neither.")


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

    # A kill that just happened. The bot used to have no idea one had occurred: it
    # only ever saw a name appear in playersDead, with no killer, no location and
    # no sense of whether it was anywhere near it. That is the single most
    # important piece of information a player gets when they hear a kill, and
    # without it the model cannot reason about who to suspect or whether it is
    # safe to be standing where it is.
    try:
        alert = botlink.kill_alert()
    except Exception:
        alert = ""
    if alert:
        bits.append(alert + " - anyone who claims to have been elsewhere then is lying")

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
    # Per-task stage progress, and which task to work on next. A two-stage task
    # stays in the list until the last stage, so without this the model could not
    # tell "not started" from "half done", and would keep asking for a part it had
    # already done.
    try:
        import roleplay as _rp
        prog = _rp.task_progress()
        parts = []
        for n, d, t, room in prog:
            if t and d is not None:
                if d >= t:
                    parts.append(f"{n} DONE")
                elif d == 0:
                    parts.append(f"{n} 0/{t} not started, in {room}")
                else:
                    nxt = _rp.next_stage_room(n, d)
                    where = nxt if nxt else ("another panel - the game only "
                                              f"publishes the first stage's room")
                    parts.append(f"{n} {d}/{t} done, next part is in {where}")
        if parts:
            bits.append("task progress: " + "; ".join(parts))
        summary = _rp.progress_summary()
        if summary:
            bits.append(summary)
    except Exception:
        pass

    if is_imp and _FAKED_ONCE:
        bits.append("tasks you have already faked (do NOT fake these again): "
                    + ", ".join(sorted(_FAKED_ONCE)))

    if here:
        if is_imp:
            bits.append("tasks you could FAKE in THIS room (once each): " + ", ".join(here))
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
    try:
        obj = _objective(role, is_imp, data, ab)
        if obj:
            bits.append(obj)
    except Exception:
        pass
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


def action_names(available_only=False):
    """The action names, optionally excluding the ones on cooldown.

    `wait` is genuinely removed from this list while it is cooling down, so the
    model is never shown it as an option. Telling a model "don't spam wait" in
    the prompt does not work - it is the one action that always looks available
    and always looks harmless, so it wins whenever the model is unsure. Hiding
    it is the only thing that actually stops it.
    """
    if available_only and _wait_cooldown_left() > 0:
        return sorted(n for n in ACTIONS if n != "wait")
    return sorted(ACTIONS)


# How long `wait` is unavailable after the model uses it. Long enough that
# waiting twice in a row is not an option, because the point of waiting is to
# let a situation change - and a second wait only burns a turn.
WAIT_COOLDOWN_SECONDS = 180.0
_wait_used_at = None


def _wait_cooldown_left():
    """Seconds until `wait` becomes available again, or 0."""
    global _wait_used_at
    if _wait_used_at is None:
        return 0.0
    left = WAIT_COOLDOWN_SECONDS - (time.time() - _wait_used_at)
    return left if left > 0 else 0.0


def _wait_used():
    """Start the cooldown. Called only when the model actually waits."""
    global _wait_used_at
    _wait_used_at = time.time()


def _wait_cooldown_note(suggestions=None):
    """A line for the situation block, so the model knows why `wait` is gone.

    `suggestions` are the options that are actually legal right now, computed
    from live state. Saying "do something real" without saying what is legal
    just makes the model pick again at random - it cannot vent as a Tracker, and
    offering that would be worse than offering nothing.
    """
    left = _wait_cooldown_left()
    if left <= 0:
        return ""
    out = (f"you just decided to wait, so you are committed to it for another "
           f"{int(round(left))}s. `wait` is not an option right now - the next "
           f"action must be a real one.")
    if suggestions:
        out += f" Right now you could: {', '.join(suggestions)}"
    return out


def reset_wait_cooldown():
    """Clear the cooldown. Called when a round starts, not every turn."""
    global _wait_used_at
    _wait_used_at = None


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
    _cooling = _wait_cooldown_left() > 0
    lines += [
        "You may call exactly one of these per turn. Nothing else is possible:",
        "",
    ]
    for name in action_names(available_only=True):
        _args, _fn, desc = ACTIONS[name]
        lines.append(f"  {desc}")
    if _cooling:
        # No need to list it or even name it as a choice - it is simply not
        # there, which is the point.
        lines.append("")
        lines.append(f"({_wait_cooldown_note()})")
    lines += [
        "",
        "Reply with one line: the action name and its argument, nothing else.",
        'Examples: "go_to Electrical", "kill", "sabotage lights".',
    ]
    if _cooling:
        # Do not suggest `wait` in the closing line while it is disabled -
        # offering it in the closing line is what made the model keep reaching
        # for it.
        lines.append("Choose one of the actions listed above.")
    else:
        lines.append(
            "If nothing is safe or useful to do right now, reply \"wait\" - but "
            "that is a real decision, not a fallback: after you wait, waiting is "
            "closed to you for three minutes and you will have to act.")
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
    if name == "wait":
        # Even though `wait` is hidden from the tool list while it is cooling
        # down, the model can still reply with the word, and some models will.
        # That is a refusal, not a free action - otherwise "wait" would still
        # be the path of least resistance and the cooldown would mean nothing.
        left = _wait_cooldown_left()
        if left > 0:
            raise ActionError(
                f"you already waited, so you are committed to that for another "
                f"{int(round(left))}s. Waiting twice in a row just burns a turn - "
                f"commit to something: move somewhere, do or fake a task, use "
                f"your ability, or say something useful.")
    _required, handler, _desc = ACTIONS[name]
    out = handler(*args)
    if name == "wait":
        _wait_used()
    return out
