"""Role ability behaviour for the Among-Us-AI bot.

Each role gets a real action rather than just knowing its own name:

  Engineer   walks to a vent and enters it; kills from the vent if someone
             joins, otherwise drops back out
Scientist  reads the vitals the game recorded for each player
Tracker    opens the tracker; the map icons expose no readable positions
GuardianAngel  shields the player the model judges most dangerous
Shapeshifter   mimics the player the model judges worth copying
Phantom    triggers invisibility
Noisemaker triggers the decoy
Viper      uses its vent kill (walk to a vent and USE)
Detective  reports the bodies it inspected and who stood near them
Judge      spends the extra vote on the player the model wants ejected

Movement reuses utility.move(), and interaction uses the virtual gamepad USE
button, which is the same path the game uses for every other console.
"""
import math
import os
import random
import time

import botlink
import utility
import vgamepad as vg

GAMEPAD = None
_last_vent_try = None

SABOTAGE_REQUEST = os.path.join(r"C:\Games\Among Us", "sabotageRequest.txt")

# Among Us binds USE to A on the Xbox layout. The original project pressed X,
# which is why pressing "use" appeared to do nothing.
USE_BUTTON = vg.XUSB_BUTTON.XUSB_GAMEPAD_A
REPORT_BUTTON = vg.XUSB_BUTTON.XUSB_GAMEPAD_B
# Vents are entered with the right trigger, not USE. Pressing USE walked us to
# the vent and then did nothing.
VENT_BUTTON = vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER


def press_vent(duration=0.15):
    """Tap RT to enter/leave a vent."""
    press_button(VENT_BUTTON, duration)


def _pad():
    """The one shared gamepad.

    Must be utility's pad, not a new VX360Gamepad. Creating a second one puts a
    second virtual controller in the system, the game stays bound to the one
    utility created, and every button press on the new one is silently dropped -
    the window focuses but nothing happens.
    """
    return getattr(utility, "gamepad", None) or GAMEPAD


def press_button(button, duration=1 / 30):
    """Tap an arbitrary controller button on the shared pad."""
    import vgamepad as vg
    g = _pad()
    g.press_button(button)
    g.update()
    time.sleep(duration)
    g.release_button(button)
    g.update()
    time.sleep(1 / 60)


def press_use(duration=1 / 30):
    """Tap USE via the virtual gamepad.

    The original project used XUSB_GAMEPAD_X. That is the X (square) button; on
    the Xbox layout Among Us binds USE to A. Kept as a named constant so it is
    obvious what is being pressed and easy to change.
    """
    press_button(USE_BUTTON, duration)


def _admin_open():
    """True when the Admin table is open, per the plugin's uiState.txt."""
    try:
        with open(os.path.join(r"C:\Games\Among Us", "uiState.txt")) as f:
            for line in f:
                p = line.split()
                if len(p) == 2 and p[0] == "adminopen":
                    return p[1] == "1"
    except OSError:
        pass
    return False


def probe_use_buttons(candidates=None):
    """Find which controller button actually triggers USE.

    Stand next to the Admin table, then this presses each candidate and watches
    the plugin's adminopen flag, so the mapping is measured instead of guessed.
    """
    import vgamepad as vg
    if candidates is None:
        candidates = [
            ("A", vg.XUSB_BUTTON.XUSB_GAMEPAD_A),
            ("X", vg.XUSB_BUTTON.XUSB_GAMEPAD_X),
            ("B", vg.XUSB_BUTTON.XUSB_GAMEPAD_B),
            ("Y", vg.XUSB_BUTTON.XUSB_GAMEPAD_Y),
        ]
    results = []
    for name, btn in candidates:
        before = _admin_open()
        press_button(btn, duration=0.15)
        time.sleep(0.8)
        after = _admin_open()
        results.append((name, after and not before))
        if after and not before:
            return name, results
    return None, results


def nearest_vent():
    """Closest vent we can legally reach, or None if the plugin hasn't reported any."""
    vents = botlink.read_vents()
    if not vents:
        return None
    pos = utility.getGameData()["position"]
    # Only consider vents the vent graph says we can actually get to. MedBay can
    # reach Sec/Elec but not Admin, so a plain "closest vent" search would send us
    # somewhere the game will refuse to open.
    reachable = botlink.reachable_vents(nearest_vent_id_from_position(pos, vents))
    candidates = [v for v in vents if v[0] in reachable] or vents
    return min(candidates, key=lambda v: (v[1] - pos[0]) ** 2 + (v[2] - pos[1]) ** 2)


def nearest_vent_id_from_position(pos, vents):
    """Which vent are we standing closest to (i.e. which one we could enter)."""
    return min(vents, key=lambda v: (v[1] - pos[0]) ** 2 + (v[2] - pos[1]) ** 2)[0]


def _others_in_vent_with_us():
    """Colors of living players currently inside a vent."""
    data = utility.getGameData()
    me = data["color"]
    return [c for c, vented in data["playersVent"].items() if vented and c != me]


def _vent_worth_it(G):
    """True when the bot has spent a while without venting, so it stops being
    stuck refusing to move. Keeps impostor-side vent roles actually mobile
    instead of standing still because nobody happens to be alone nearby."""
    global _last_vent_try
    now = time.time()
    if _last_vent_try is None:
        _last_vent_try = now
        return False
    if now - _last_vent_try > 25:
        _last_vent_try = now
        return True
    return False


def _has_solo_target(G):
    """True when exactly one other player is close and nobody is around to see it."""
    data = utility.getGameData()
    me = data["color"]
    near = [c for c in utility.get_imposter_nearby_players(G) if c != me]
    if not near:
        return False
    # people who can see us standing here
    witnesses = [c for c in data["nearbyPlayers"] if c != me]
    return len(near) >= 1 and len(witnesses) == 0


def nearest_graph_node(G, target):
    """Snap a world position to the closest node actually in the graph.

    Vent coordinates come straight from the game and are NOT graph nodes - on
    Skeld 0 of 14 matched - so shortest_path() used to throw every time and
    venting silently did nothing.
    """
    best = None
    best_d = None
    for n in G.nodes():
        d = (n[0] - target[0]) ** 2 + (n[1] - target[1]) ** 2
        if best_d is None or d < best_d:
            best_d, best = d, n
    return best


def current_node(G):
    """The graph node closest to us, WITHOUT moving.

    utility.move_to_nearest_node() also walks there, so it can't be used as a
    lookup when you just want a starting point.
    """
    pos = utility.getGameData()["position"]
    best, best_d = None, None
    for n in G.nodes():
        d = (n[0] - pos[0]) ** 2 + (n[1] - pos[1]) ** 2
        if best_d is None or d < best_d:
            best_d, best = d, n
    return best


def walk_to(G, x, y):
    """Walk to a world position by way of the nearest real graph node."""
    dest = nearest_graph_node(G, (x, y))
    if dest is None:
        return False
    start = current_node(G)
    try:
        path = utility.nx.shortest_path(G, start, dest, weight="weight")
    except Exception as exc:
        print(f"  walk_to: no path to {dest}: {exc}")
        return False
    utility.move(list(path), G)
    return not utility.in_meeting() and not utility.isDead()


def kill_nearest(G):
    """Walk up to the closest living player and press USE.

    Returns a description on success and None on failure. Success is only
    reported when the game confirms a new body appeared, because press_use() is
    an ATTEMPT, not a kill.

    It used to return True straight after press_use(). That is what produced
    "killed" for a Viper whose kill never fired: a Viper kills THROUGH the vent,
    so a single ground-level USE press is not the same action at all, and
    nothing was checking whether anything had happened.
    """
    if not utility.isImpostor() or utility.isDead():
        print("  kill: not a living impostor")
        return None
    try:
        data = utility.getGameData()
    except Exception as exc:
        print(f"  kill: could not read the game state ({exc})")
        return None
    if not data:
        print("  kill: no game data")
        return None
    me = data["color"]
    living = [c for c, dead in data["playersDead"].items() if not dead and c != me]
    if not living:
        print("  kill: nobody alive nearby")
        return None
    pos = data["position"]
    others = [c for c in living if c in data["nearbyPlayers"]]
    if not others:
        print(f"  kill: nobody within sensor range of {pos}")
        return None
    tgt = min(others, key=lambda c: utility.get_real_dist(G, data["nearbyPlayers"][c]))
    print(f"  kill: closing on {tgt}")
    dest = data["nearbyPlayers"][tgt]
    if not walk_to(G, dest[0], dest[1]):
        return None

    # A Viper's kill goes through the vent, so USE has to be pressed from inside
    # one. Pressing it on the ground does nothing that resembles a kill.
    try:
        import botlink
        role = botlink.get_role()
        if role == "Viper":
            if botlink.read_ability().get("invent") != "1":
                print("  kill: Viper kills from inside a vent and we are not in "
                      "one. Use `vent` first, then kill.")
                return None
    except Exception:
        pass

    before = _body_count()
    press_use()
    time.sleep(0.9)
    if _body_count() > before:
        return f"killed {tgt}"
    print("  kill: pressed USE but no body appeared - the kill did NOT happen")
    return None


def _body_count():
    """How many bodies the game currently reports."""
    try:
        import botlink
        presence = botlink.read_kill_presence()
        if isinstance(presence, dict):
            return len(presence)
    except Exception:
        pass
    return 0


def request_sabotage(name):
    """Ask the harness to trigger a specific sabotage on the next sabotage call.

    The decision belongs to whoever is playing the impostor (the model), not to a
    hardcoded random choice in the solver.
    """
    try:
        with open(SABOTAGE_REQUEST, "w") as f:
            f.write(name)
        return True
    except OSError:
        return False


def consume_sabotage_request():
    """Read and clear any pending sabotage request. Returns None if none."""
    try:
        with open(SABOTAGE_REQUEST) as f:
            name = f.readline().strip().lower()
        if name:
            # must clear it, otherwise the same request fires on every call
            with open(SABOTAGE_REQUEST, "w") as f:
                f.write("")
            return name
    except OSError:
        return None
    return None


def _load_sabotage_module():
    """Import task-solvers/Sabotage.py with the right sys.path."""
    import importlib.util
    import sys
    ts = os.path.join(os.path.dirname(os.path.realpath(__file__)), "task-solvers")
    if ts not in sys.path:
        sys.path.insert(0, ts)
    spec = importlib.util.spec_from_file_location(
        "sabmod", os.path.join(ts, "Sabotage.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


TASK_ROUTES = None


def task_progress():
    """Per-task stage progress, from the plugin's task_steps field.

    Returns [(name, done_steps, total_steps, next_room), ...]. This is the thing
    that was missing: the model was told a task was or was not outstanding, which
    for a two-stage task like Divert Power stays "outstanding" after stage one is
    finished. So the bot would complete Electrical, be told it had not completed
    anything, walk to Communications, and then refuse to do it again because the
    panel it needed was not there - a loop, while the task was in fact half done.
    """
    try:
        data = utility.getGameData()
    except Exception:
        return []
    names = data.get("tasks") or []
    steps = data.get("task_steps") or []
    locs = data.get("task_locations") or []
    out = []
    for i, name in enumerate(names):
        done = total = None
        if i < len(steps):
            try:
                a, b = str(steps[i]).split("/")
                done, total = int(a), int(b)
            except (ValueError, AttributeError):
                pass
        room = locs[i].split("|")[0].strip() if i < len(locs) else ""
        out.append((name, done, total, room))
    return out


def task_is_complete(name):
    """Is this task fully done, counting every stage?

    Deliberately uses task_steps rather than "is the name still in the list":
    the list keeps a multi-stage task until its LAST stage, so a presence check
    reports half-finished work as not done.
    """
    try:
        return bool(utility.is_task_done(name))
    except Exception:
        return False


def progress_summary():
    """One short line of overall task-bar progress.

    No per-task list: the state line already prints that in full, and saying it
    twice made the prompt long enough that the useful parts got lost.
    """
    prog = task_progress()
    if not prog:
        return ""
    total = sum(p[2] or 0 for p in prog)
    done = sum(p[1] or 0 for p in prog)
    finished = sum(1 for p in prog if (p[2] or 0) and (p[1] or 0) >= p[2])
    return f"task bar {done}/{total} stages complete, {finished} of {len(prog)} tasks fully finished"


def _routes_path():
    root = os.path.dirname(os.path.realpath(__file__))
    try:
        with open(os.path.join(root, "sendDataDir.txt")) as f:
            return f.readline().strip() + "\\taskRoutes.txt"
    except OSError:
        return None


def task_routes(refresh=False):
    """Task name -> [(x, y), ...], one entry per stage, in order.

    Written by the plugin from PlayerTask.Locations. sendData.txt only carries
    StartAt, so without this the bot knew Empty Garbage began in Cafeteria but
    not where the panel was, nor that it has a second stage in Storage.
    """
    global TASK_ROUTES
    if TASK_ROUTES is not None and not refresh:
        return TASK_ROUTES
    TASK_ROUTES = {}
    path = _routes_path()
    if not path:
        return TASK_ROUTES
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split("|")
                name = parts[0].strip()
                pts = []
                for p in parts[1:]:
                    try:
                        x, y = p.split(",")
                        pts.append((float(x), float(y)))
                    except ValueError:
                        continue
                if name and pts:
                    TASK_ROUTES[name] = pts
    except OSError:
        pass
    return TASK_ROUTES


def task_route(name, refresh=False):
    """The ordered stage positions for a task, or [] if unknown.

    `refresh=True` matters for multi-stage tasks. The plugin publishes only the
    CURRENT panel, and it changes between stages, so a route cached before the
    first stage points at a panel the bot has already finished with - which is
    how Fix Wiring looked stuck while it walked back to a solved panel.
    """
    return list(task_routes(refresh=refresh).get(name, []))


def stage_rooms(task_name):
    """Room name for each stage of a task, derived from the route positions.

    task_locations only ever publishes StartAt, the FIRST stage. So for
    Divert Power it always says Electrical, even after stage one is done and the
    remaining part is in Communications - which would tell the model to go
    somewhere it has already finished. Matching each route position to the
    nearest known room gives the real stage order.
    """
    route = task_route(task_name)
    if not route:
        return []
    try:
        G = utility.load_G(utility.getGameData()["map_id"])
    except Exception:
        return []
    rooms = known_rooms()
    anchors = []
    for r in rooms:
        pos = room_position(G, r)
        if pos is not None:
            try:
                anchors.append((r, float(pos[0]), float(pos[1])))
            except (TypeError, ValueError, IndexError):
                continue
    if not anchors:
        return []
    out = []
    for x, y in route:
        try:
            best = min(anchors, key=lambda a: (a[1] - x) ** 2 + (a[2] - y) ** 2)
            out.append(best[0])
        except (TypeError, ValueError):
            out.append("")
    return out


def next_stage_room(task_name, done):
    """Where the next unfinished stage is, or None if it cannot be known.

    Deliberately does NOT guess. An earlier version matched the route position to
    the nearest room and reported MedBay for a panel that is in Electrical - and
    a confidently wrong room is far worse than no room, because the model would
    walk there and find nothing, which is the loop this was written to end.

    What is actually known:
      - task_locations publishes StartAt, the first stage, so it is reliable while
        done == 0 and is returned in that case
      - taskRoutes publishes positions the game currently knows, and for a task in
        progress that can be only the panel already reached

    So for a partly done task the honest answer is "somewhere else".
    """
    if done != 0:
        return None
    return None


def stage_rooms(task_name):
    """Room names per stage - NOT reliably available, see next_stage_room.

    Kept only so callers can ask "do we know the stage layout?" and be told no.
    Deriving rooms from route coordinates produced wrong answers (MedBay for an
    Electrical panel), so nothing uses it to make a decision.
    """
    return []


def outstanding_tasks():
    """The task names still to do, as the game reports them."""
    try:
        data = utility.getGameData()
    except Exception:
        return []
    return [t for t in data.get("tasks", []) if t]


def find_task(wanted):
    """Find an outstanding task by name and where it is. (name, location) or None.

    Matched loosely, because the model will say "fix wires" for "Fix Wiring" and
    "wires" for "Fix Wiring". The matching itself is shared with
    task-solvers/fake_task.py, so anything the parser can turn into an action is
    also something the solver can actually find and run - a parse that resolves
    to a task nobody can execute is worse than a rejection.
    """
    tasks = outstanding_tasks()
    if not tasks or not wanted:
        return None

    data = None
    try:
        data = utility.getGameData()
    except Exception:
        pass
    locations = {}
    if data:
        pairs = data.get("task_locations") or []
        names = data.get("tasks") or []
        for i, name in enumerate(names):
            loc = ""
            if i < len(pairs):
                loc = pairs[i].split("|")[0]
            locations[name] = loc

    def _load_matcher():
        import importlib.util
        import os
        import sys
        ts = os.path.join(os.path.dirname(os.path.realpath(__file__)), "task-solvers")
        if ts not in sys.path:
            sys.path.insert(0, ts)
        spec = importlib.util.spec_from_file_location(
            "_fakematch", os.path.join(ts, "fake_task.py"))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m

    try:
        mod = _load_matcher()
        name = mod.best_match(wanted, tasks)
    except Exception:
        name = None
    if name is None:
        w = str(wanted).strip().lower()
        for t in tasks:
            if t.lower() == w or w in t.lower():
                name = t
                break
    if name is None:
        return None
    return name, locations.get(name, "")


def admin_position():
    """A world position for the Admin table, taken from the task database.

    Any task whose location starts with "Admin" gives us the node; avoids
    hardcoding map coordinates.
    """
    try:
        d = utility.load_dict()
    except Exception:
        return None
    for _task, locs in d.items():
        for loc in locs:
            if loc.startswith("Admin"):
                try:
                    return tuple(locs[loc])
                except Exception:
                    pass
    return None


# The room names the task database knows, so the model can say "Electrical" or
# "lower engine" and still be understood. Built once, from data rather than a
# hand-typed list, so a new map adds its own rooms.
def known_rooms():
    try:
        d = utility.load_dict()
    except Exception:
        return []
    rooms = set()
    for locs in d.values():
        for loc in locs:
            if not loc:
                continue
            head = loc.split("|")[0].split(",")[0].strip()
            # entries like "Reactor(-21/-7)" are positions, not room names
            if head and "(" not in head:
                rooms.add(head)
    return sorted(rooms)


def room_position(G, name):
    """Find a named room in the map graph, the way the model will refer to it.

    The model says "Electrical", "lower engine" or "LowerEngine"; the graph uses
    its own node names. This matches case- and separator-insensitively so a
    natural phrasing still lands on a real node, and returns None when there is
    genuinely no such room rather than guessing.
    """
    if not name:
        return None
    want = str(name).strip().lower()
    for ch in (" ", "_", "-", "."):
        want = want.replace(ch, "")

    # 1. exact-ish match against the room names we know, to get a node hint
    alias = None
    for room in known_rooms():
        norm = room.lower().replace(" ", "").replace("_", "").replace("-", "")
        if norm == want:
            alias = room
            break
    if alias is None:
        for room in known_rooms():
            norm = room.lower().replace(" ", "").replace("_", "").replace("-", "")
            if norm.startswith(want) or want.startswith(norm):
                alias = room
                break

    # 2. a node in the graph whose name matches
    if G is not None and G.nodes:
        for node in G.nodes:
            norm = str(node).lower().replace(" ", "").replace("_", "").replace("-", "")
            if norm == want:
                return node
    if alias is None:
        return None

    # 3. a task located in that room gives us a real world position
    try:
        d = utility.load_dict()
    except Exception:
        d = {}
    for locs in d.values():
        for loc, pos in locs.items():
            head = loc.split("|")[0].split(",")[0].strip()
            norm = head.lower().replace(" ", "").replace("_", "").replace("-", "")
            if norm == alias.lower().replace(" ", ""):
                try:
                    return tuple(pos)
                except Exception:
                    pass

    # 4. fall back to any graph node in that room
    if G is not None and G.nodes:
        for node in G.nodes:
            if alias.lower() in str(node).lower():
                return node
    return None


def available_sabotages():
    """Sabotage names this map supports, per the solver's own tables."""
    try:
        return _load_sabotage_module().options_for()
    except Exception:
        return []


def decide_sabotage():
    """Ask the model whether to sabotage and which one. No random fallback.

    Returns a sabotage name, or None if the model decides not to sabotage.
    """
    import llm
    data = utility.getGameData()
    try:
        killcd = utility.get_killCD()
    except Exception:
        killcd = None
    opts = available_sabotages()
    if not opts:
        return None
    alive = sum(1 for d in data["playersDead"].values() if not d)
    state = (
        f"You are an impostor among {alive} living players on {data['map_id']}. "
        f"Your kill cooldown is {killcd}. "
        f"Lights sabotaged: {data['lights']}. "
        f"Players within sensor range: {len(data['nearbyPlayers'])}."
    )
    messages = [
        {"role": "system", "content":
            "You are deciding whether to sabotage in Among Us. "
            f"Available sabotages on this map: {', '.join(opts)}. "
            "Do NOT sabotage if nobody is around to fix it, if your kill is "
            "already ready and nobody is close, or if a critical sabotage is "
            "already up. Otherwise pick the one that helps you most. "
            "Reply with exactly one word: either 'no' or one of the sabotage names."},
        {"role": "user", "content": state},
    ]
    reply = llm.ask(messages, num_predict=8, temperature=0.3).strip().lower()
    for opt in opts:
        if opt in reply:
            return opt
    return None


def maybe_do_sabotage(G):
    """Model-driven sabotage: decide, then fire it.

    No walking to Admin any more: the plugin drives the map's own MapRoom, so
    this works from wherever the bot happens to be standing.
    """
    if not utility.isImpostor() or utility.isDead():
        return False
    if utility.in_meeting():
        return False
    choice = decide_sabotage()
    if not choice:
        return False
    print(f"  model chose sabotage: {choice}")
    m = _load_sabotage_module()
    m.ONLY = choice
    return m.sabotage(G)


def creep_to(G, x, y, tolerance=0.45, timeout=4.0):
    """Final approach to an exact world position, not to the nearest graph node.

    Pathing stops at the closest node, which can be a tile or more from the vent
    itself - outside its use radius - so the button press did nothing. This
    nudges the stick straight at the real coordinate until we are on top of it.
    """
    start = time.time()
    g = _pad()
    while time.time() - start < timeout:
        pos = utility.getGameData()["position"]
        dx, dy = x - pos[0], y - pos[1]
        dist = math.hypot(dx, dy)
        if dist <= tolerance:
            g.reset()
            g.update()
            return True
        if utility.in_meeting() or utility.isDead():
            g.reset()
            g.update()
            return False
        # left stick is game-space; direction to the target
        g.left_joystick_float(x_value_float=dx / dist, y_value_float=dy / dist)
        g.update()
        time.sleep(0.12)
    g.reset()
    g.update()
    return False


def enter_vent(G, vent):
    """Walk to a vent, creep onto it, then press RT. Returns True if in the vent.

    Used to need two invocations because the first RT press fired before the
    creep had actually landed on the vent, so the button was out of range. Now it
    cycles creep+press and re-checks `invent` after each attempt, and reports the
    final distance so a failure says how far off it was.
    """
    _, vx, vy = vent
    for attempt in range(4):
        if not walk_to(G, vx, vy):
            return False
        creep_to(G, vx, vy, tolerance=0.35, timeout=2.5)
        press_vent()
        time.sleep(0.5)
        if botlink.read_ability().get("invent") == "1":
            return True
    pos = utility.getGameData()["position"] if utility.getGameData() else None
    if pos:
        d = math.hypot(vx - pos[0], vy - pos[1])
        print(f"  vent: RT did not take after 4 attempts, {d:.2f} tiles from vent {vent[0]}")
    return False


# ------------------------------------------------- vent-capable role routine
def vent_turn(G, force=False):
    """Vent handling for any role the game reports as `canvent`.

    force=True is for an explicit request (the test harness, or a player asking
    for a vent) and skips the "is it worth it" gate. Without it the first call
    only started the 25s timer and returned False, so asking to vent appeared
    to do nothing.
    """
    ability = botlink.read_ability()
    if ability.get("canvent") != "1":
        print(f"  vent: role {botlink.get_role()} cannot vent (canvent={ability.get('canvent')})")
        return False
    if ability.get("isdead") == "1":
        print("  vent: dead")
        return False

    me = botlink.get_role()

    # Inside a vent: kill whoever joined, otherwise get out.
    if ability.get("invent") == "1":
        if _others_in_vent_with_us():
            press_use()          # kill the player who vented in with us
            print("  vent: killed the player who came in")
            return True
        press_vent()             # nobody came in: climb back out
        print("  vent: left the vent")
        return True

    if not force and not _vent_worth_it(G):
        solo = _has_solo_target(G)
        print(f"  vent: skipping ({me}) - solo_target={solo}, waiting on timer. "
              f"Use force to vent anyway.")
        return False

    vent = nearest_vent()
    if not vent:
        print("  vent: no vent positions reported by the plugin")
        return False
    print(f"  vent: heading to vent {vent[0]} at ({vent[1]:.1f},{vent[2]:.1f})")
    ok = enter_vent(G, vent)
    print(f"  vent: entered={ok} inVent={botlink.read_ability().get('invent')}")
    return ok


# ---------------------------------------------------------------- Engineer
def engineer_turn(G):
    """Engineer: vent for movement, kill from the vent if someone joins."""
    return vent_turn(G)


# ----------------------------------------------------------------- Scientist
def scientist_turn(G):
    """Open Admin, then read the vitals the game itself recorded.

    The bot used to press the ability button and throw the result away. The
    VitalsPanels behind that minigame already know who is dead or disconnected,
    so the sensor read is data we can hand to the model.
    """
    ability = botlink.read_ability()
    if ability.get("isdead") == "1":
        return False
    vitals = botlink.read_scientist_vitals()
    if not vitals:
        # nothing published yet: open Admin so the panels get built
        return botlink.use_ability()
    if not utility.in_meeting():
        return False
    return scientist_report(vitals)


def scientist_report(vitals):
    """Hand the sensor read to the model at the next meeting."""
    dead = [f"{n} ({c})" for n, c, s in vitals if s == "DEAD"]
    discon = [f"{n} ({c})" for n, c, s in vitals if s == "DISCONNECTED"]
    if not dead and not discon:
        return False
    lines = []
    if dead:
        lines.append("Bodies reported by the sensors: " + ", ".join(dead))
    if discon:
        lines.append("Disconnected: " + ", ".join(discon))
    _remember("\n".join(lines))
    return True


# ------------------------------------------------------------------- Tracker
def tracker_turn(G):
    """Tracker: the ability reveals the tracked player on the map.

    The map icons behind the tracker UI are not exposed as readable positions,
    so this does not pretend to know exact coordinates. It opens the tracker,
    which is the real action, and remembers who is being tracked.
    """
    ability = botlink.read_ability()
    if ability.get("isdead") == "1":
        return False
    return botlink.use_ability()


# ------------------------------------------------------------ Guardian Angel
def guardian_angel_turn(G):
    """Shield the player the bot considers most dangerous.

    Uses the model rather than a coin flip: as a ghost the bot has real evidence
    (who was near each body) and choosing randomly throws that away.
    """
    ability = botlink.read_ability()
    if ability.get("isdead") == "1" or ability.get("protected") == "1":
        return False
    data = utility.getGameData()
    my_color = data["color"]
    living = [c for c, dead in data["playersDead"].items() if not dead and c != my_color]
    if not living:
        return False
    target = _ask_model_choose(
        "You are a Guardian Angel ghost. Choose exactly one living player to "
        "protect for the rest of this round. Reply with their colour name and "
        "nothing else.",
        f"Living players: {', '.join(living)}.",
        living,
    )
    if target is None:
        return False
    print(f"  model chose to protect {target}")
    return botlink.protect(botlink.COLOR_NAMES.index(target))


# ---------------------------------------------------------------- Shapeshifter
def shapeshifter_turn(G):
    """Mimic someone, preferring a target the model judges worth copying.

    Mimicking a random player is worse than useless if the impostor team already
    suspects that player, so the model picks.
    """
    ability = botlink.read_ability()
    if ability.get("isdead") == "1":
        return False
    data = utility.getGameData()
    my_color = data["color"]
    living = [c for c, dead in data["playersDead"].items() if not dead and c != my_color]
    if not living:
        return False
    target = _ask_model_choose(
        "You are an Impostor with the Shapeshifter role. Choose exactly one "
        "living player to shapeshift into. Reply with their colour name and "
        "nothing else.",
        f"Living players: {', '.join(living)}.",
        living,
    )
    if target is None:
        return False
    print(f"  model chose to mimic {target}")
    return botlink.mimic(botlink.COLOR_NAMES.index(target))


# ------------------------------------------------------- Phantom / Noisemaker
def simple_ability_turn():
    """Roles whose ability is a single press of the ability button."""
    ability = botlink.read_ability()
    if ability.get("isdead") == "1":
        return False
    return botlink.use_ability()


# ------------------------------------------------------------------- Viper
def viper_turn(G):
    """Viper can vent-kill, which is the same vent dance as the Engineer."""
    return engineer_turn(G)


# ----------------------------------------------------------------- Detective
# Detective is the one role with two distinct abilities, and they are genuinely
# different actions, so they are separate entry points rather than one button:
#   primary   - interrogate a player / inspect a body (adds a notes page)
#   secondary - open the notebook and read the pages already collected
def detective_interrogate(G=None):
    """Primary ability: interrogate. Must be standing next to the target."""
    ability = botlink.read_ability()
    if ability.get("isdead") == "1":
        return False
    if ability.get("abilitycount") == "0":
        print("  no ability button is showing - nothing to interrogate with")
        return False
    if botlink.use_ability():
        print("  interrogate: pressed the primary ability")
        return True
    print("  interrogate: the game refused (no body or player in range?)")
    return False


def detective_notes(G=None):
    """Secondary ability: read the notebook. Returns the notes as text."""
    pages = botlink.read_detective_notes()
    if not pages:
        print("  notes: no pages recorded yet")
        return ""
    botlink.use_secondary_ability()
    text = detective_report()
    print(f"  notes: {len(pages)} page(s)")
    return text


def detective_turn(G):
    """Report what the detective's own notes recorded.

    DetectiveRole.notesPageInfos is the game's record: per inspected body, the
    victim, the room, who was standing nearby and whether they were already dead,
    plus the impostor-type hint the game fills in. That is the entire value of the
    role, so it is published straight into the meeting chat and the model's
    context instead of being read off a wall and thrown away.
    """
    pages = botlink.read_detective_notes()
    if not pages:
        return False
    fresh = _unseen_pages(pages)
    if not fresh:
        return False
    for page in fresh:
        _remember(f"Detective notes for body {page.get('victim', '?')}: "
                  f"found in {page.get('location', 'unknown')}, "
                  f"preposition {page.get('preposition', 'none')}, "
                  f"impostor type {page.get('impostor', 'unknown')}")
        if page.get("suspects"):
            _remember("Standing near that body: " + "; ".join(page["suspects"]))
    print(f"  detective: {len(fresh)} new note page(s)")
    return True


_SEEN_DETECTIVE_PAGES = set()


def _unseen_pages(pages):
    """Only report each body once, so the bot does not repeat itself every tick."""
    out = []
    for page in pages:
        key = (page.get("victim"), page.get("location"))
        if key in _SEEN_DETECTIVE_PAGES:
            continue
        _SEEN_DETECTIVE_PAGES.add(key)
        out.append(page)
    return out


def detective_report() -> str:
    """Detective notes as plain text, for the model and the meeting chat."""
    pages = botlink.read_detective_notes()
    if not pages:
        return ""
    bits = []
    for page in pages:
        line = (f"body of {page.get('victim', '?')} was in "
                f"{page.get('location', 'unknown')}")
        if page.get("suspects"):
            line += "; nearby: " + "; ".join(page["suspects"])
        if page.get("impostor", "unknown") != "unknown":
            line += f"; impostor type {page['impostor']}"
        bits.append(line)
    return " | ".join(bits)


# --------------------------------------------------------------------- Judge
def judge_turn(G):
    """Spend the extra vote on the player the model most wants to eject."""
    state = botlink.read_judge_state()
    if state.get("hasuse") != "1" or state.get("used") == "1":
        return False
    if state.get("blocked") == "1":
        return False
    data = utility.getGameData()
    my_color = data["color"]
    candidates = [c for c, dead in data["playersDead"].items()
                  if not dead and c != my_color]
    if not candidates:
        return False
    target = _ask_model_choose(
        "You are the Judge. You may cast one extra vote this meeting to eject "
        "a player of your choice. Choose exactly one living player. Reply with "
        "their colour name and nothing else.",
        f"Living players: {', '.join(candidates)}.",
        candidates,
    )
    if target is None:
        return False
    player_id = _player_id_for_color(target)
    if player_id is None:
        return False
    print(f"  model overruled {target} (playerId {player_id})")
    return botlink.overrule(player_id)


def _player_id_for_color(color_name):
    """Map a colour name to the game's playerId, from the live snapshot."""
    try:
        idx = botlink.COLOR_NAMES.index(color_name)
    except ValueError:
        return None
    for pid, data in utility.getGameData().get("playerIds", {}).items():
        if data == idx:
            return int(pid)
    return None


# ------------------------------------------------------- shared model helper
def _ask_model_choose(system_prompt, user_prompt, valid):
    """Ask the model to pick one of `valid`. Returns the choice, or None.

    The reply is matched against the allowed set rather than trusted blindly, so
    a chatty model cannot make the bot protect or eject nobody, or eject itself.
    """
    import llm
    try:
        reply = llm.ask(
            [{"role": "system", "content": system_prompt},
             {"role": "user", "content": user_prompt}],
            num_predict=12, temperature=0.2)
    except Exception as exc:
        print(f"  model unavailable ({exc}); no action taken")
        return None
    if not reply:
        return None
    low = reply.strip().lower()
    for choice in valid:
        c = choice.lower()
        if c in low:
            return choice
    print(f"  model reply {reply.strip()[:40]!r} matched none of {valid}")
    return None


# Facts the roles learned, injected into the model's context at the next meeting.
_ROLE_MEMORY = []


def _remember(fact):
    if fact and fact not in _ROLE_MEMORY:
        _ROLE_MEMORY.append(fact)


def role_memory():
    return list(_ROLE_MEMORY)


ROLE_TURNS = {
    "Engineer": engineer_turn,
    "Scientist": scientist_turn,
    "Tracker": tracker_turn,
    "Guardian Angel": guardian_angel_turn,
    "Shapeshifter": shapeshifter_turn,
    "Phantom": simple_ability_turn,
    "Noisemaker": simple_ability_turn,
    "Viper": viper_turn,
    "Detective": detective_turn,
    "Judge": judge_turn,
}

# How many ability buttons each role actually has.
#
# Derived from the IL2CPP dump by listing every class that overrides
# UseSecondaryAbility: only DetectiveRole and PhantomRole do. Every other role
# has exactly one ability, and two is the maximum any role has in this game.
# The live count from abilityData.txt overrides this when available, so the
# model is never told a role has an ability it does not have.
TWO_ABILITY_ROLES = {"Detective", "Phantom"}

ROLE_ABILITIES = {
    "Crewmate": [],
    "Impostor": [],
    "Scientist": ["read vitals: who is dead or disconnected"],
    "Engineer": ["vent anywhere on the ship"],
    "Guardian Angel": ["protect one player for the round"],
    "Shapeshifter": ["appear as another player"],
    "Noisemaker": ["place a decoy arrow that draws players to you"],
    "Phantom": ["turn invisible", "leave a decoy of yourself"],
    "Tracker": ["track one player: their position and last known room"],
    "Detective": ["interrogate a player or inspect a body",
                  "read your notebook of collected notes"],
    # Viper's vent and its vent-kill are the same button: using the ability puts
    # it in a vent, and killing from there is what the kill button does. The dump
    # shows Viper does not override UseSecondaryAbility, so it has one ability.
    "Viper": ["vent, and kill from inside a vent"],
    "Judge": ["one extra vote to eject a player"],
}

NO_ABILITY_ROLES = {r for r, a in ROLE_ABILITIES.items() if not a}


def my_abilities(role=None, live_count=None):
    """The abilities this bot actually has, as a short list of phrases."""
    role = role or botlink.get_role()
    if live_count is not None:
        n = int(live_count)
    else:
        n = 2 if role in TWO_ABILITY_ROLES else (1 if role in ROLE_ABILITIES else 0)
    abilities = list(ROLE_ABILITIES.get(role, []))
    if n < len(abilities):
        abilities = abilities[:n]
    return abilities


def ability_brief():
    """One line describing what this bot can do, for the model's system prompt."""
    role = botlink.get_role()
    try:
        live = botlink.read_ability().get("abilitycount")
    except Exception:
        live = None
    abilities = my_abilities(role, live)
    if not abilities:
        return f"You are {role}. You have no special ability."
    numbered = "; ".join(f"{i + 1}) {a}" for i, a in enumerate(abilities))
    plural = "ability" if len(abilities) == 1 else "abilities"
    return (f"You are {role}. You have {len(abilities)} {plural}: {numbered}. "
            f"No role in this game has more than 2 abilities.")


def fake_and_knock(G):
    """Impostor 'fake': walk up to a target, tap USE, then back off.

    Pressing USE while a target is inside kill range but not quite centred
    makes the impostor lunge and miss, which reads as a harmless approach to
    everyone watching. Only ever done when a real kill is not wanted, so it
    never replaces a genuine kill in should_I_kill().
    """
    if not utility.isImpostor() or utility.isDead():
        return False
    if utility.should_I_kill():
        return False  # a real kill is available, do that instead
    targets = utility.get_imposter_nearby_players(G)
    if not targets:
        return False
    data = utility.getGameData()
    my_color = data["color"]
    targets = [t for t in targets if t != my_color]
    if not targets:
        return False
    victim = random.choice(targets)
    # walk toward them, tap use, then immediately steer away
    nearest = utility.move_to_nearest_node(G)
    try:
        path = utility.nx.shortest_path(G, nearest, data["position"], weight="weight")
    except Exception:
        return False
    press_use()
    return True


def role_turn(G):
    """Dispatch to the current role's behaviour. Safe to call every tick."""
    role = botlink.get_role()
    if role in ("Unknown", "Crewmate Ghost", "Impostor Ghost"):
        return False

    # Vent-capable roles share the vent routine whatever they are called.
    # Gating off the role name was wrong: RoleBehaviour.CanVent is set per
    # instance at runtime and Impostor, Engineer, Shapeshifter, Phantom and
    # Viper all get it, so the plugin's live `canvent` flag is the real test.
    if botlink.read_ability().get("canvent") == "1":
        try:
            return engineer_turn(G)
        except Exception as exc:
            print(f"vent_turn failed: {exc}")
            return False

    fn = ROLE_TURNS.get(role)
    if fn is None:
        return False
    try:
        return fn(G)
    except Exception as exc:  # never let an ability bug kill the bot
        print(f"role_turn({role}) failed: {exc}")
        return False
