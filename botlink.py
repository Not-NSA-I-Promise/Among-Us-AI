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


def send_cmd(cmd: str) -> bool:
    """Write a command for the plugin. Returns False if the plugin can't be reached."""
    for _ in range(3):
        try:
            with open(CMD_PATH, "w") as f:
                f.write(cmd)
            return True
        except OSError:
            time.sleep(0.2)
    return False


def open_chat() -> bool:
    return send_cmd("openchat")


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


if __name__ == "__main__":
    # quick self-test of the channel
    print("role      :", get_role())
    print("ability   :", get_role_ability())
    print("uiCoords  :", read_ui_coords())
    print("presence  :", read_kill_presence())
    print("abilitySt :", read_ability())
    print("vents     :", read_vents())
