"""Bridge to the BepInEx plugin's control channel.

The bot used to blind-click hardcoded screen ratios for every UI element, which
only ever worked at one exact resolution. The plugin now exposes the game's own
UI through two files:

    botCmd.txt   bot -> game   one command per write, consumed by the plugin
    uiCoords.txt game -> bot   live screen positions of UI elements

Commanding the real game API (InGamePlayerList.SetActive for chat,
MeetingHud.Select/Confirm for voting) is resolution independent.
"""
import os
import time

with open("sendDataDir.txt") as f:
    _GAME_DIR = f.readline().rstrip()

CMD_PATH = os.path.join(_GAME_DIR, "botCmd.txt")
UI_PATH = os.path.join(_GAME_DIR, "uiCoords.txt")
ROLE_PATH = os.path.join(_GAME_DIR, "roleData.txt")
PRESENCE_PATH = os.path.join(_GAME_DIR, "killPresence.txt")

COLOR_NAMES = [
    "RED", "BLUE", "GREEN", "PINK", "ORANGE", "YELLOW", "BLACK", "WHITE",
    "PURPLE", "BROWN", "CYAN", "LIME", "MAROON", "ROSE", "BANANA", "GRAY",
    "TAN", "CORAL",
]

# RoleTypes enum from the game (dump.cs). 0/1 are the plain crewmate/impostor.
ROLES = {
    0: "Crewmate", 1: "Impostor", 2: "Scientist", 3: "Engineer",
    4: "Guardian Angel", 5: "Shapeshifter", 6: "Crewmate Ghost",
    7: "Impostor Ghost", 8: "Noisemaker", 9: "Phantom", 10: "Tracker",
    12: "Detective", 18: "Viper", 19: "Judge",
}

# Roles whose abilities this bot knows how to reason about at all.
KNOWN_ABILITIES = {
    "Engineer": "can vent and vent-kill",
    "Scientist": "has motion sensors",
    "Tracker": "sees everyone's name on the tracker",
    "Detective": "sees who inspected him / how long bodies have been there",
    "Guardian Angel": "can protect a player",
    "Shapeshifter": "can mimic another player",
    "Viper": "can vent-kill from farther away",
    "Judge": "can vote multiple times",
    "Noisemaker": "can place a noise decoy",
    "Phantom": "can go invisible",
}


RESULT_PATH = os.path.join(_GAME_DIR, "cmdResult.txt")


class CommandFailed(RuntimeError):
    """The game did not perform the command. Carries the plugin's reason."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def last_result() -> str:
    try:
        with open(RESULT_PATH) as f:
            return f.read().strip()
    except OSError:
        return ""


def send_cmd(cmd: str, timeout: float = 2.0) -> bool:
    """Send a command and WAIT for the game to confirm it.

    This used to return True as soon as the command file was written, which is
    not evidence the game did anything - a sabotage on a map with no matching
    entry still reported success. The plugin now answers every command in
    cmdResult.txt, so the return value reflects the game, not the write.

    Raises CommandFailed when the game declined, so a caller cannot quietly
    report an action that never happened.
    """
    try:
        with open(RESULT_PATH, "w") as f:
            f.write("")
    except OSError:
        pass
    for _ in range(3):
        try:
            with open(CMD_PATH, "w") as f:
                f.write(cmd)
            break
        except OSError:
            time.sleep(0.2)
    else:
        return False

    deadline = time.time() + timeout
    while time.time() < deadline:
        result = last_result()
        if result:
            if result.startswith("ok"):
                return True
            raise CommandFailed(result)
        time.sleep(0.03)
    return False


def try_cmd(cmd: str, timeout: float = 2.0):
    """Like send_cmd but returns (ok, detail) instead of raising."""
    try:
        return True, send_cmd(cmd, timeout)
    except CommandFailed as exc:
        return False, exc.reason


def open_chat() -> bool:
    return send_cmd("openchat")


def say(message: str) -> bool:
    """Send a chat message through the game's own RPC.

    This did not exist: agent.say() called chatGPT.say(), which was never
    implemented, so every `say` action raised AttributeError and the model could
    not speak at all - it could only vote silently.
    """
    text = str(message).strip()
    if not text:
        return False
    return send_cmd("say " + text)


def meeting_time_left() -> float:
    """Seconds left in the meeting's discussion phase, or -1 if none.

    Needed so the model can budget speaking against voting instead of either
    talking until the timer expires or never speaking at all.
    """
    try:
        ok, detail = try_cmd("meetingtime")
    except Exception:
        return -1.0
    if not ok or not str(detail).startswith("ok"):
        return -1.0
    try:
        return float(str(detail).split(" ", 1)[1])
    except (IndexError, ValueError):
        return -1.0


def close_chat() -> bool:
    return send_cmd("closechat")


def cast_vote(color_index: int) -> bool:
    """color_index is the Among Us color id, or -1 to skip."""
    return send_cmd(f"castvote {color_index}")


def read_ui_coords() -> dict:
    """Parse uiCoords.txt into {'chat': (x, y), 'vote:3': (x, y), ...}."""
    coords = {}
    try:
        with open(UI_PATH) as f:
            for line in f:
                parts = line.split()
                if len(parts) == 3:
                    coords[parts[0] + (":" + parts[1] if parts[0] == "vote" else "")] = (
                        int(parts[-2]), int(parts[-1]))
    except (OSError, ValueError):
        pass
    return coords


def get_role(retries=4) -> str:
    """Role name from roleData.txt.

    Retries like read_ability(): a single empty read used to report
    "Unknown" for a split second even though the role was known, which showed up
    as role=Crewmate then role=Unknown in the same menu press.
    """
    for _ in range(retries):
        try:
            with open(ROLE_PATH) as f:
                raw = f.readline().strip()
            if raw:
                return ROLES.get(int(raw), "Unknown")
        except (OSError, ValueError):
            pass
        time.sleep(0.05)
    return "Unknown"


def get_role_ability(role: str = None) -> str:
    role = role or get_role()
    return KNOWN_ABILITIES.get(role, "no special ability")


def read_kill_presence() -> dict:
    """Who was within earshot of the victim when they died: {COLOR: distance}."""
    try:
        with open(PRESENCE_PATH) as f:
            raw = f.readline().strip().strip("][")
        out = {}
        if not raw:
            return out
        for item in raw.split(", "):
            if "/" not in item:
                continue
            color, dist = item.split("/")
            out[color] = float(dist)
        return out
    except (OSError, ValueError):
        return {}


ABILITY_PATH = os.path.join(_GAME_DIR, "abilityData.txt")
VENT_PATH = os.path.join(_GAME_DIR, "ventData.txt")
MINIGAME_PATH = os.path.join(_GAME_DIR, "minigameState.txt")


def read_minigame(retries=4):
    """What the GAME says about the task panel: is it open, and which one.

    This is read from Minigame.Instance in the game itself, not inferred from a
    screenshot. The screenshot heuristics were the source of a long run of
    defects - claiming a panel was open when it was closed, closed when it was
    open, and unable to tell a wiring panel from a lights panel - because they
    were guesses about pixels standing in for a fact the game already knows.

    Returns {"open": bool, "task": str} where `task` is the game's own name for
    the panel, e.g. "FixWiring". Returns open=False when no panel is up, or when
    the plugin is not running.
    """
    out = {"open": False, "task": ""}
    for _ in range(retries):
        try:
            with open(MINIGAME_PATH) as f:
                text = f.read()
        except OSError:
            time.sleep(0.05)
            continue
        out = {"open": False, "task": ""}
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("open "):
                out["open"] = line[5:].strip() == "1"
            elif line.startswith("task "):
                out["task"] = line[5:].strip()
        return out
    return out


def minigame_is(task_name=None, timeout=3.0, poll=0.1):
    """Wait for a panel to be open. Optionally require a specific task.

    `task_name` is matched leniently: the game calls it "FixWiring" and the
    harness calls it "Fix Wiring", so compare with the spaces and case removed.

    Returns the state dict, or None on timeout. Callers must not treat None as
    "closed" without saying so - that is what turned a slow panel into a panel
    that was believed shut.
    """
    deadline = time.time() + max(0.0, timeout)
    want = _norm_task(task_name) if task_name else None
    state = {"open": False, "task": ""}
    while True:
        state = read_minigame()
        if state["open"] and (want is None or _norm_task(state["task"]) == want):
            return state
        if time.time() >= deadline:
            return None
        time.sleep(poll)


def _norm_task(name):
    """'Fix Wiring', 'FixWiring' and 'fix_wiring' all become 'fixwiring'."""
    return "".join(ch for ch in str(name).lower() if ch.isalnum())


def read_ability(retries=4):
    """Live role state written by the plugin each snapshot.

    Retries on a partial read: the plugin swaps the file in atomically, but a
    read can still land in the instant the old file is gone, which used to look
    exactly like canvent=0 and silently stopped vent roles from venting.
    """
    out = {}
    for attempt in range(retries):
        try:
            with open(ABILITY_PATH) as f:
                data = f.read()
        except OSError:
            time.sleep(0.05)
            continue
        out = {}
        for line in data.splitlines():
            parts = line.split()
            if len(parts) == 2:
                out[parts[0]] = parts[1]
        if "canvent" in out:
            return out
        time.sleep(0.05)
    return out


VENT_OPTIONS_PATH = os.path.join(_GAME_DIR, "ventOptions.txt")


def read_vent_options() -> list:
    """Vents reachable from the vent we are currently in, as [(id, x, y)].

    The plugin enumerates the game's own VentButton objects, so this is the real
    menu rather than a guess: a vent only appears here if the game offers it.
    """
    out = []
    try:
        with open(VENT_OPTIONS_PATH) as f:
            for line in f:
                p = line.split()
                if len(p) == 3:
                    out.append((int(p[0]), int(p[1]), int(p[2])))
    except (OSError, ValueError):
        pass
    return out


def vent_travel(vent_id: int) -> bool:
    """Travel to a connected vent. The plugin clicks the real VentButton."""
    return send_cmd(f"venttravel {vent_id}")


SABOTAGE_BUTTONS_PATH = os.path.join(_GAME_DIR, "sabotageButtons.txt")
SABOTAGE_NAMES_PATH = os.path.join(_GAME_DIR, "sabotage_names.txt")


def read_sabotage_buttons() -> list:
    """Sabotage map entries as [(index, name, system_value, active)].

    These come from the game's own MapRoom objects, which carry their SystemTypes,
    so the names are real. Lines are "<index> <Name> <value> <active>"; a leading
    "#" line carries the counts.
    """
    out = []
    try:
        with open(SABOTAGE_BUTTONS_PATH) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                p = line.split()
                if len(p) >= 3 and p[0].isdigit():
                    active = len(p) > 3 and p[3] in ("True", "true", "1")
                    out.append((int(p[0]), p[1], int(p[2]), active))
    except (OSError, ValueError):
        pass
    return out


def sabotage_options() -> list:
    """Names the game itself reports, e.g. Cafeteria, Electrical, Reactor."""
    return [name for _, name, _, _ in read_sabotage_buttons()]


def sabotage_button_stats() -> str:
    try:
        with open(SABOTAGE_BUTTONS_PATH) as f:
            for line in f:
                if line.startswith("#"):
                    return line.strip()
    except OSError:
        pass
    return "#no sabotageButtons.txt"


def read_sabotage_names() -> dict:
    """Calibrated name -> button index. This is element identity, not pixels."""
    out = {}
    try:
        with open(SABOTAGE_NAMES_PATH) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                p = line.split(" ", 1)
                if len(p) == 2 and p[0].isdigit():
                    out[p[1].strip()] = int(p[0])
    except OSError:
        pass
    return out


def write_sabotage_names(names: dict) -> None:
    with open(SABOTAGE_NAMES_PATH, "w") as f:
        f.write("# sabotage name -> button index (element identity, resolution independent)\n")
        for name, idx in sorted(names.items(), key=lambda kv: kv[1]):
            f.write(f"{idx} {name}\n")


def open_sabotage_map() -> bool:
    """Impostors open the sabotage map with their own button, from anywhere."""
    return send_cmd("opensabotage")


def click_sabotage(name: str) -> bool:
    """Ask the plugin to activate a sabotage by name; it finds the live button."""
    return send_cmd(f"clicksabotage {name}")


def read_vent_options_raw() -> str:
    try:
        with open(VENT_OPTIONS_PATH) as f:
            return f.read()
    except OSError:
        return ""


def read_vents() -> list:
    vents = []
    for vid, x, y, *_ in _vent_rows():
        vents.append((vid, x, y))
    return vents


def _vent_rows() -> list:
    """[(id, x, y, left, right, center), ...] including the real vent graph."""
    rows = []
    try:
        with open(VENT_PATH) as f:
            raw = f.readline().strip().strip("][")
        for item in raw.split(", "):
            if item.count("/") < 2:
                continue
            parts = item.split("/")
            vid, x, y = int(parts[0]), float(parts[1]), float(parts[2])
            if len(parts) >= 4 and parts[3]:
                links = [int(v) for v in parts[3].split(",") if v != "" and v != "-1"]
            else:
                links = []
            rows.append((vid, x, y, links))
    except (OSError, ValueError):
        pass
    return rows


def vent_graph() -> dict:
    """{vent_id: [neighbour_vent_ids]} straight from the game's Vent.Left/Right/Center."""
    return {vid: links for vid, _x, _y, links in _vent_rows()}


def reachable_vents(from_vent_id: int) -> set:
    """Every real vent reachable by vent-travel starting at from_vent_id.

    The game only lets you travel between vents that share a link, so the bot
    must never path from, say, MedBay straight to Admin.
    """
    graph = vent_graph()
    known = set(graph.keys())
    if not known:
        return set()
    start = from_vent_id if from_vent_id in known else None
    if start is None:
        return set(known)
    seen = {start}
    stack = [start]
    while stack:
        cur = stack.pop()
        for nb in graph.get(cur, []):
            if nb in known and nb not in seen:
                seen.add(nb)
                stack.append(nb)
    return seen


def use_ability() -> bool:
    """Trigger the role's primary ability through RoleBehaviour.UseAbility()."""
    return send_cmd("useability")


def use_secondary_ability() -> bool:
    return send_cmd("useability2")


def protect(color_index: int) -> bool:
    """Guardian Angel: shield a player."""
    return send_cmd(f"protect {color_index}")


def mimic(color_index: int) -> bool:
    """Shapeshifter: appear as another player."""
    return send_cmd(f"mimic {color_index}")


def overrule(player_id: int) -> bool:
    """Judge: cast the extra vote against a player id."""
    return send_cmd(f"overrule {player_id}")


DETECTIVE_PATH = os.path.join(_GAME_DIR, "detectiveData.txt")
SCIENTIST_PATH = os.path.join(_GAME_DIR, "scientistData.txt")
JUDGE_PATH = os.path.join(_GAME_DIR, "judgeData.txt")


def read_detective_notes() -> list:
    """The detective's own pages: one dict per inspected body.

    Straight from DetectiveRole.notesPageInfos, so victim / room / nearby players
    are what the game recorded, not an inference. The plugin writes one field per
    line because names and room names contain spaces.
    """
    pages = []
    cur = None
    try:
        with open(DETECTIVE_PATH) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("page "):
                    cur = {"index": line.split()[1], "suspects": []}
                    pages.append(cur)
                elif cur is not None:
                    key, _, val = line.partition(" ")
                    if key == "suspect":
                        cur["suspects"].append(val)
                    else:
                        cur[key] = val
    except OSError:
        pass
    return pages


def read_scientist_vitals() -> list:
    """Scientist sensor read: [(name, color, state)] from the game's VitalsPanels."""
    out = []
    try:
        with open(SCIENTIST_PATH) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                p = line.rsplit(" ", 2)
                if len(p) == 3:
                    name = p[0].strip()
                    color = p[1].strip().strip("()")
                    out.append((name, color, p[2].strip()))
    except OSError:
        pass
    return out


def read_judge_state() -> dict:
    out = {}
    try:
        with open(JUDGE_PATH) as f:
            for line in f:
                p = line.split()
                if len(p) == 2:
                    out[p[0]] = p[1]
    except OSError:
        pass
    return out


if __name__ == "__main__":
    # quick self-test of the channel
    print("role      :", get_role())
    print("ability   :", get_role_ability())
    print("uiCoords  :", read_ui_coords())
    print("presence  :", read_kill_presence())
    print("abilitySt :", read_ability())
    print("vents     :", read_vents())
