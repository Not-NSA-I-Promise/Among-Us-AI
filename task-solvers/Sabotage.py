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
    """Trigger one sabotage from the Admin table.

    Which sabotage is decided by the caller (the model, via
    roleplay.decide_sabotage) or by the queued sabotageRequest.txt. There is no
    random choice of our own unless nothing was requested.
    """
    dimensions = get_dimensions()
    if not dimensions:
        return False
    map_id = _map_id()
    table = load_coords().get(map_id, {})
    if not table:
        print(f"Sabotage: no coordinates for map {map_id}")
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

    if forced:
        if forced not in table:
            print(f"Sabotage: {forced} is not available on {map_id} "
                  f"(have: {', '.join(table)})")
            return False
        chosen = forced
    else:
        chosen = random.choice(list(table))

    dx, dy = table[chosen]

    # Must be a truthiness check: task_utility.is_urgent_task() returns False
    # (not None) when nothing is urgent, so `is not None` skipped every time.
    if chosen in ("reactor", "oxygen") and is_urgent_task():
        print("Sabotage: a critical sabotage is already active, skipping")
        return False

    wake()
    # Impostors open the map with their own sabotage button from anywhere; there
    # is no need to stand at the Admin table.
    opened = False
    try:
        import sys
        root = os.path.dirname(HERE)
        if root not in sys.path:
            sys.path.insert(0, root)
        import botlink
        opened = botlink.open_sabotage_map()
    except Exception:
        opened = False

    if not opened:
        # fall back to clicking the Admin table in the world
        pyautogui.click(dimensions[0] + round(dimensions[2] / 1.42),
                        dimensions[1] + round(dimensions[3] / 1.207),
                        duration=0.2)
    time.sleep(0.9)

    pyautogui.click(dimensions[0] + round(dimensions[2] / dx),
                    dimensions[1] + round(dimensions[3] / dy), duration=0.2)
    time.sleep(1 / 30)
    print(f"Sabotage: triggered {chosen} ({describe(chosen)}) on {map_id}")

    try:
        cx, cy = load_coords().get("_close", {}).get(map_id, (12.8, 7.66))
        pyautogui.click(dimensions[0] + round(dimensions[2] / cx),
                        dimensions[1] + round(dimensions[3] / cy), duration=0.2)
    except Exception:
        pass
    return True


if __name__ == "__main__":
    print("available:", options_for())
    sabotage()
