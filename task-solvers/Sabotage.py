import json
import os
import random
import time

import pyautogui

from task_utility import *

HERE = os.path.dirname(os.path.realpath(__file__))
COORDS_FILE = os.path.join(os.path.dirname(HERE), "sabotage_coords.json")

ONLY = None  # sabotage name to force; None = use whatever the model requested

# The Admin table can sabotage far more than the four critical systems. Skeld
# also has door hijacks in Cafeteria, Upper Engine, MedBay, Security, Lower
# Engine and Storage, and the lights are two separate buttons (Electrical and
# Navigation). Coordinates live in sabotage_coords.json and can be recalibrated
# with 'cal' in test_commands.py.
DESCRIPTIONS = {
    "reactor": "hijacks the reactor, forcing a Reset Reactor",
    "oxygen": "hijacks oxygen, forcing Restore Oxygen",
    "comms": "breaks communications",
    "lights": "hijacks the lights in Electrical",
    "lights_navigation": "hijacks the lights in Navigation",
    "doors_cafeteria": "hijacks the Cafeteria doors",
    "doors_upper": "hijacks the Upper Engine doors",
    "doors_medbay": "hijacks the MedBay doors",
    "doors_security": "hijacks the Security doors",
    "doors_electrical": "hijacks the Electrical doors",
    "doors_lower": "hijacks the Lower Engine doors",
    "doors_storage": "hijacks the Storage doors",
    "mushroom_mixup": "mushroom mixup (Fungle)",
    "heli": "heli sabotage (Airship)",
}


def load_coords():
    try:
        with open(COORDS_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_coords(data):
    with open(COORDS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _map_id():
    return getGameData()["map_id"].upper()


def options_for(map_id=None):
    """Sabotage names this map supports."""
    map_id = map_id or _map_id()
    return list(load_coords().get(map_id, {}).keys())


def describe(name):
    return DESCRIPTIONS.get(name, name)


def sabotage(G=None):
    """Trigger one sabotage on the in-game map.

    The plugin drives the map's own MapRoom object, so this works from anywhere
    and at any resolution. Which sabotage is decided by the caller (the model, via
    roleplay.decide_sabotage) or by the queued sabotageRequest.txt. There is no
    random choice of our own.
    """
    dimensions = get_dimensions()
    if not dimensions:
        return False

    forced = ONLY
    if forced is None:
        try:
            import sys
            root = os.path.dirname(HERE)
            if root not in sys.path:
                sys.path.insert(0, root)
            import roleplay
            forced = roleplay.consume_sabotage_request()
        except Exception:
            forced = None

    if not forced:
        # No model decision available: do nothing rather than fire something
        # arbitrary. A wrong sabotage kills a crewmate and looks human.
        print("Sabotage: no sabotage queued (use `sb` in the harness to request one)")
        return False

    # Validate against what the game itself reports, not a hardcoded table.
    try:
        import sys
        root = os.path.dirname(HERE)
        if root not in sys.path:
            sys.path.insert(0, root)
        import botlink
        available = botlink.sabotage_options()
    except Exception:
        available = []
    if available:
        # accept either the raw MapRoom name or a friendly alias
        aliases = {"oxygen": "LifeSupp", "o2": "LifeSupp", "comms": "Comms",
                   "lights": "Shields", "heli": "HeliSabotage",
                   "upper": "UpperEngine", "lower": "LowerEngine",
                   "medbay": "MedBay", "medica": "MedBay", "sec": "Security"}
        target = aliases.get(forced.lower(), forced)
        if target not in available:
            print(f"Sabotage: {forced!r} is not on this map right now "
                  f"(have: {', '.join(available)})")
            return False
    else:
        print(f"Sabotage: {forced!r} (could not confirm against the game)")

    chosen = forced

    # Must be a truthiness check: task_utility.is_urgent_task() returns False
    # (not None) when nothing is urgent, so `is not None` skipped every time.
    if chosen in ("reactor", "oxygen") and is_urgent_task():
        print("Sabotage: a critical sabotage is already active, skipping")
        return False

    wake()

    # Ask the plugin to drive the map's own MapRoom object. The plugin resolves
    # the name to a room and calls SabotageDoors()/SabotageLights()/etc, which is
    # exactly what pressing the entry on the map does. Nothing here uses pixels,
    # so the resolution genuinely cannot break it.
    # The plugin replies in cmdResult.txt; treat that as the only evidence. A
    # successful file write is not a successful sabotage.
    try:
        import sys
        root = os.path.dirname(HERE)
        if root not in sys.path:
            sys.path.insert(0, root)
        import botlink
        if not botlink.open_sabotage_map():
            print(f"Sabotage: could not open the map "
                  f"(plugin said: {botlink.last_result() or 'no reply'})")
            return False
        time.sleep(0.9)
        if botlink.click_sabotage(chosen):
            time.sleep(1 / 30)
            print(f"Sabotage: CONFIRMED {chosen} ({describe(chosen)}) - "
                  f"game replied '{botlink.last_result()}'")
            return True
        print(f"Sabotage: the game did NOT do it: {botlink.last_result()}")
    except botlink.CommandFailed as exc:
        print(f"Sabotage: refused: {exc.reason}")
    except Exception as e:
        print(f"Sabotage: plugin path failed ({e})")
    return False


if __name__ == "__main__":
    print("available:", options_for())
    sabotage()
