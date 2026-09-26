"""Interactive test harness for the Among-Us-AI bot.

Lets you poke every capability the bot has from a menu, so you can confirm
what actually works instead of guessing.

    .venv\\Scripts\\python.exe test_commands.py

This script is self-sufficient about the gamepad, which is the usual reason
commands appear to do nothing:

  * ViGEmBus leaves a zombie virtual pad behind every time a vgamepad process
    dies. Several at once make Among Us bind to a dead one, so it ignores all
    controller input. They are purged on startup.
  * Among Us enumerates input devices at launch and does not hot-plug, so the
    pad must exist BEFORE the game starts. This script therefore creates the
    pad first and offers to (re)start the game.
"""
import os
import subprocess
import sys
import time

GAMEDIR = r"C:\Games\Among Us"
GAME = os.path.join(GAMEDIR, "Among Us.exe")
SEND = os.path.join(GAMEDIR, "sendData.txt")
VIRTUAL_PAD_MARKER = "VID_045E&PID_028E"  # ViGEm Xbox 360 controller


def purge_zombie_pads():
    """Remove every leftover virtual pad, not just a few hardcoded ids.

    The device ids are not predictable - after a few runs there were 46 entries
    with ids like USB\\VID_045E&PID_028E&IG_01\\2&DEE0F28&9&01 as well as the
    plain \\01..\\04 forms. A hardcoded list only caught a handful, so the
    zombies regrew until the game bound to a dead controller and ignored all
    input. Enumerate instead.
    """
    ps = ("Get-PnpDevice -ErrorAction SilentlyContinue | "
          "Where-Object { $_.InstanceId -like '*VID_045E&PID_028E*' } | "
          "ForEach-Object { $_.InstanceId }")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                             capture_output=True, text=True, timeout=60)
    except Exception as exc:
        print(f"  could not enumerate pads: {exc}")
        return
    ids = [ln.strip() for ln in (out.stdout or "").splitlines() if ln.strip()]
    if not ids:
        print("  no virtual pads present")
        return
    print(f"  removing {len(ids)} leftover virtual pad device(s)")
    for dev in ids:
        try:
            subprocess.run(["pnputil", "/remove-device", dev],
                           capture_output=True, text=True, timeout=20)
        except Exception:
            pass


def game_running():
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Among Us.exe"],
                         capture_output=True, text=True)
    return "Among Us.exe" in (out.stdout or "")


def match_live():
    try:
        return os.path.exists(SEND) and (time.time() - os.path.getmtime(SEND)) < 5
    except OSError:
        return False


def active_pad_count():
    """How many virtual controllers Windows currently reports as connected."""
    ps = ("Get-PnpDevice -ErrorAction SilentlyContinue | "
          "Where-Object { $_.InstanceId -like '*VID_045E&PID_028E*' -and "
          "$_.Status -eq 'OK' } | Measure-Object | ForEach-Object { $_.Count }")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                             capture_output=True, text=True, timeout=60)
        return int((out.stdout or "0").strip() or 0)
    except Exception:
        return -1


def preflight():
    """Attach to the already-running game, exactly like start_bot.bat does.

    Deliberately does NOT purge virtual pads and does NOT restart the game.
    Purging removes the virtual controller the running game is currently bound
    to, and the game does not re-adopt a new one, so every command then does
    nothing. start_bot.bat only creates a pad and talks to the running game, and
    that is proven to work, so this script mirrors it exactly.

    If input really is dead, press 'w': the walk test reports the tile delta,
    and the menu has an explicit 'p' to purge pads - but only do that with the
    game closed.
    """
    print("1. creating the virtual gamepad (same as start_bot.bat)")
    import utility  # noqa: F401  - import creates + holds the pad
    time.sleep(0.5)
    print("   pad is held by this process")

    # The game binds to one specific controller at startup. If several are
    # connected it may have bound to a stale one from an earlier run, and then
    # nothing this process sends will ever arrive.
    n = active_pad_count()
    if n > 1:
        print(f"{RED}   WARNING: {n} virtual controllers are connected.{RESET}")
        print(f"{RED}   The game may be bound to a stale one, so commands will do nothing.{RESET}")
        print(f"   To clear them: close this script, close Among Us, press 'p' here,")
        print(f"   then start Among Us again and rerun this script.")
    elif n == 1:
        print("   exactly 1 controller connected - good")

    if game_running():
        print("2. using the running game instance\n")
    else:
        print(f"{RED}   Among Us is not running - start it and get into a match.{RESET}\n")
    return utility


# These are imported after preflight() so the pad exists first.
utility = None
botlink = None
roleplay = None

GREEN, RED, YELLOW, DIM, RESET = "\033[92m", "\033[91m", "\033[93m", "\033[2m", "\033[0m"


def show_state():
    data = utility.getGameData()
    ability = botlink.read_ability()
    role = botlink.get_role()
    print(f"{DIM}  role={role}  impostor={data['status']}  dead={data['dead']}  "
          f"inVent={ability.get('invent', '?')}  canVent={ability.get('canvent', '?')}"
          f"  canKill={ability.get('cankill', '?')}{RESET}")
    print(f"{DIM}  pos={data['position']}  room={data['room']}  alive={data['color']}"
          f"  inMeeting={data['inMeeting']}{RESET}")
    vented = [c for c, v in data["playersVent"].items() if v]
    if vented:
        print(f"{DIM}  players in vents: {vented}{RESET}")
    return data, ability


def banner(text):
    print(f"\n{YELLOW}=== {text} ==={RESET}")


def wait_for_game():
    data = utility.getGameData()
    if not utility.isInGame():
        print(f"{RED}  not in a game - start a match first{RESET}")
        return False
    return True


# --------------------------------------------------------------- menu actions
def a_chat_open():
    banner("open chat  (plugin -> InGamePlayerList.SetActive)")
    ok = botlink.open_chat()
    time.sleep(0.6)
    print(f"  command sent: {ok}  -> now type into the chat box by hand to confirm it opened")


def a_chat_close():
    banner("close chat")
    print(f"  command sent: {botlink.close_chat()}")


def a_use_ability():
    banner("use ability  (RoleBehaviour.UseAbility)")
    before = botlink.read_ability()
    ok = botlink.use_ability()
    time.sleep(0.8)
    after = botlink.read_ability()
    print(f"  command sent: {ok}")
    print(f"  before: {before}")
    print(f"  after : {after}")


def a_use_ability2():
    banner("use secondary ability")
    ok = botlink.use_secondary_ability()
    time.sleep(0.8)
    print(f"  command sent: {ok}  -> {botlink.read_ability()}")


def a_protect():
    banner("protect (Guardian Angel)")
    idx = input("  target color index (0-17): ").strip()
    if not idx.isdigit():
        return
    ok = botlink.protect(int(idx))
    time.sleep(0.8)
    print(f"  command sent: {ok}  -> protected={botlink.read_ability().get('protected')}")


def a_mimic():
    banner("mimic (Shapeshifter)")
    idx = input("  target color index (0-17): ").strip()
    if not idx.isdigit():
        return
    ok = botlink.mimic(int(idx))
    time.sleep(0.8)
    print(f"  command sent: {ok}  -> shapeshifted={botlink.read_ability().get('shapeshifted')}")


def a_vote():
    banner("cast vote  (MeetingHud.Select + Confirm)")
    idx = input("  color index, or -1 to skip: ").strip()
    if not idx.lstrip("-").isdigit():
        return
    ok = botlink.cast_vote(int(idx))
    time.sleep(0.8)
    print(f"  command sent: {ok}")


def a_press_use():
    banner("press USE (virtual gamepad X)")
    print("  walk next to a vent/console first")
    roleplay.press_use()
    time.sleep(0.5)
    print(f"  inVent now: {botlink.read_ability().get('invent')}")


def a_vent_run():
    banner("full vent routine  (walk to a legal vent, then RT)")
    if not wait_for_game():
        return
    ab = botlink.read_ability()
    if ab.get("canvent") != "1":
        print(f"  read canvent={ab.get('canvent')!r} for {botlink.get_role()} - genuinely cannot vent.")
        print("  try an Impostor/Engineer/Phantom/Shapeshifter/Viper game.")
        return
    G = utility.load_G(utility.getGameData()["map_id"])
    ok = roleplay.vent_turn(G, force=True)
    time.sleep(0.5)
    print(f"  vent_turn returned {ok}  -> inVent={botlink.read_ability().get('invent')}")


def a_vents():
    banner("vent graph (game's own Left/Right/Center connectivity)")
    graph = botlink.vent_graph()
    for vid, x, y in botlink.read_vents():
        print(f"  vent {vid:2} at ({x:7.2f},{y:7.2f})  -> {graph.get(vid, [])}")
    if not graph:
        print(f"  {DIM}no vents reported yet{RESET}")


def a_kill_presence():
    banner("kill witnesses (who was near the body)")
    print(f"  {botlink.read_kill_presence()}")


def a_sabotage():
    banner("sabotage (Admin table click)")
    if not wait_for_game():
        return
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "sab", os.path.join(os.path.dirname(os.path.realpath(__file__)),
                             "task-solvers", "Sabotage.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    print(f"  result: {mod.sabotage()}")


def a_fake():
    banner("fake / knock")
    if not wait_for_game():
        return
    G = utility.load_G(utility.getGameData()["map_id"])
    print(f"  result: {roleplay.fake_and_knock(G)}")


def a_uicoords():
    banner("live UI coordinates (resolution independent)")
    coords = botlink.read_ui_coords()
    if not coords:
        print(f"  {DIM}none reported (needs an active match){RESET}")
    for k, v in sorted(coords.items()):
        print(f"  {k:12} {v}")


def a_walk_test():
    banner("walk test  (proves the virtual gamepad reaches the game)")
    if not wait_for_game():
        return
    # The game window must be focused or the controller input is dropped.
    # main.py calls focus() for this reason and that is why the bot works.
    try:
        utility.focus()
        time.sleep(0.6)
    except Exception as exc:
        print(f"  (focus failed: {exc})")
    p0 = utility.getGameData()["position"]
    print(f"  before: {p0}")
    g = roleplay._pad()
    g.left_joystick_float(x_value_float=1.0, y_value_float=0.0)
    g.update()
    time.sleep(2.0)
    g.reset()
    g.update()
    time.sleep(0.3)
    p1 = utility.getGameData()["position"]
    d = ((p1[0] - p0[0]) ** 2 + (p1[1] - p0[1]) ** 2) ** 0.5
    print(f"  after : {p1}")
    print(f"  moved : {d:.3f} tiles")
    print("  VERDICT:", "OK - gamepad works" if d > 0.15
          else "*** no movement - check the game window is focused ***")


def a_purge_pads():
    banner("purge leftover virtual pads")
    print(f"{RED}  Only do this with Among Us CLOSED.{RESET}")
    print("  Purging while the game runs removes the controller it is bound to.")
    if game_running():
        print(f"{RED}  Among Us IS running - aborting.{RESET}")
        return
    purge_zombie_pads()
    print("  now start Among Us, then run this script again")


def a_kill():
    banner("kill  (walk to the nearest player, then USE)")
    if not wait_for_game():
        return
    G = utility.load_G(utility.getGameData()["map_id"])
    print(f"  result: {roleplay.kill_nearest(G)}")
    time.sleep(0.5)
    print(f"  killCD now: {utility.get_killCD()}")


def a_witnesses():
    banner("witnesses")
    pres = botlink.read_kill_presence()
    print(f"  recorded at last kill: {pres if pres else 'none (no kill yet)'}")
    if not wait_for_game():
        return
    G = utility.load_G(utility.getGameData()["map_id"])
    me = utility.getGameData()["color"]
    near = [c for c in utility.get_imposter_nearby_players(G) if c != me]
    print(f"  in sensor range right now: {near if near else 'nobody'}")
    print("  (anyone in that list would be recorded as a witness if you killed there)")


def a_sabotage_choose():
    banner("sabotage  (choose which one)")
    print("  1) random  2) reactor  3) oxygen  4) comms  5) lights")
    pick = input("  > ").strip()
    forced = {"2": "reactor", "3": "oxygen", "4": "comms", "5": "lights"}.get(pick)
    if not wait_for_game():
        return
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "sab", os.path.join(os.path.dirname(os.path.realpath(__file__)),
                             "task-solvers", "Sabotage.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if forced:
        mod.ONLY = forced
    print(f"  result: {mod.sabotage()}")


def a_report():
    banner("report  (virtual gamepad B)")
    roleplay.press_button(roleplay.REPORT_BUTTON, duration=0.15)
    time.sleep(0.5)
    print("  pressed REPORT button")


def a_probe_use():
    banner("probe: which button is USE?")
    if not wait_for_game():
        return
    print("  Stand next to the ADMIN TABLE so opening it is detectable,")
    print("  then press ENTER to probe A, X, B, Y in turn.")
    input()
    found, results = roleplay.probe_use_buttons()
    for name, worked in results:
        print(f"  {name}: {'OPENED the admin table  <-- this is USE' if worked else 'no effect'}")
    print(f"\n  RESULT: USE = {found}" if found
          else "\n  RESULT: none of A/X/B/Y opened admin. Stand closer to the table.")


def a_sab_request():
    banner("request a sabotage  (the model tells the harness what to do)")
    print("  1) reactor  2) oxygen  3) comms  4) lights")
    pick = input("  > ").strip()
    name = {"1": "reactor", "2": "oxygen", "3": "comms", "4": "lights"}.get(pick)
    if not name:
        print("  cancelled")
        return
    print(f"  queued: {name} (the next sabotage will use it, then clear it)")
    print(f"  request_sabotage -> {roleplay.request_sabotage(name)}")
    print("  now press 'b' to fire it")


def a_calibrate():
    banner("calibrate sabotage click points")
    if not wait_for_game():
        return
    print("  Walk to Admin, stand at the table and open the sabotage map.")
    print("  Then click each button in turn; the exact point is recorded.")
    input("  press ENTER once the map is open... ")
    import Sabotage as _sab  # noqa
    data = _sab.load_coords()
    map_id = _sab._map_id()
    data.setdefault(map_id, {})
    print(f"\n  map = {map_id}")
    print("  Click each sabotage button. Enter the name (or blank to skip),")
    print("  then click the button on screen.\n")
    while True:
        name = input("  sabotage name (blank to finish): ").strip().lower()
        if not name:
            break
        click = input("     now click that button on screen... ").strip()
        print(f"     (enter={click})")
        raw = input("     x,y of the click in pixels (from the top-left of the screen): ").strip()
        try:
            px, py = [int(v) for v in raw.replace(",", " ").split()[:2]]
        except ValueError:
            print("     could not parse, skipping")
            continue
        dims = utility.get_dimensions()
        cx, cy = px - dims[0], py - dims[1]
        w, h = dims[2], dims[3]
        if w <= 0 or h <= 0 or cx <= 0 or cy <= 0:
            print("     point is outside the game window, skipping")
            continue
        data[map_id][name] = [round(w / cx, 4), round(h / cy, 4)]
        print(f"     saved {name} -> {[round(w/cx,4), round(h/cy,4)]}")
    _sab.save_coords(data)
    print(f"\n  saved to sabotage_coords.json  [{map_id}]")
    print(f"  {data.get(map_id, {})}")


def a_vent_options():
    banner("vent travel  (pick a destination from the real vent menu)")
    opts = botlink.read_vent_options()
    if not opts:
        print("  no vent options reported.")
        print("  You must be INSIDE a vent (press 9 first) for the game to show them.")
        return
    print("  connected vents:")
    for vid, x, y in opts:
        print(f"    vent {vid:2}  button at ({x},{y})")
    pick = input("  vent id to travel to (blank to cancel): ").strip()
    if not pick.isdigit():
        print("  cancelled")
        return
    target = int(pick)
    if target not in [o[0] for o in opts]:
        print(f"  vent {target} is not in the menu - pick one of the listed ids")
        return
    print(f"  travelling to vent {target} ...")
    ok = botlink.vent_travel(target)
    time.sleep(1.0)
    pos = utility.getGameData()["position"] if utility.getGameData() else None
    if pos:
        print(f"  command sent: {ok}   now at ({pos[0]:.1f},{pos[1]:.1f})")
    else:
        print(f"  command sent: {ok}")


def a_calibrate():
    banner("calibrate sabotage buttons")
    if not wait_for_game():
        return
    print("  1. Walk to Admin if you have to, or stay put if you are the impostor.")
    print("  2. Open the sabotage map (impostor: your sabotage button).")
    input("  press ENTER once the map is open... ")
    time.sleep(1.0)
    btns = botlink.read_sabotage_buttons()
    if not btns:
        print("  the game reported no sabotage buttons - is the map actually open?")
        return
    print(f"\n  the game reports {len(btns)} sabotage buttons:")
    for i, x, y in btns:
        print(f"    #{i} at ({x},{y})")
    print("\n  For each one: move the mouse over it and press SPACE.")
    print("  I'll read the mouse position, so you never type coordinates.")
    print("  Give it a name when asked. ENTER alone finishes.\n")

    import json
    path = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                        "sabotage_coords.json")
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    map_id = None
    try:
        map_id = utility.getGameData()["map_id"].upper()
    except Exception:
        pass
    data.setdefault(map_id, {})

    while True:
        name = input("  name for the button under the cursor (blank = done): ").strip()
        if not name:
            break
        print("     move the mouse over the button and press SPACE... ", end="", flush=True)
        press = input()
        mx, my = pyautogui.position()
        dims = utility.get_dimensions()
        cx, cy = mx - dims[0], my - dims[1]
        nearest = min(btns, key=lambda b: (b[1] - mx) ** 2 + (b[2] - my) ** 2)
        dist = ((nearest[1] - mx) ** 2 + (nearest[2] - my) ** 2) ** 0.5
        w, h = dims[2], dims[3]
        data[map_id][name] = [round(w / cx, 4), round(h / cy, 4)]
        print(f"     mouse=({mx},{my}) client=({cx},{cy}) nearest button #{nearest[0]} "
              f"at {dist:.0f}px -> saved {name} = {[round(w/cx,4), round(h/cy,4)]}")
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"\n  saved to sabotage_coords.json  [{map_id}]")
    for k, v in data.get(map_id, {}).items():
        print(f"    {k:20} w/{v[0]:<8} h/{v[1]}")


MENU = [
    ("s", "state          - show current game/role state", show_state),
    ("w", "walk test     - verify gamepad reaches the game", a_walk_test),
    ("1", "open chat", a_chat_open),
    ("2", "close chat", a_chat_close),
    ("3", "use ability", a_use_ability),
    ("4", "use secondary ability", a_use_ability2),
    ("5", "protect <idx> (Guardian Angel)", a_protect),
    ("6", "mimic <idx>   (Shapeshifter)", a_mimic),
    ("7", "vote <idx>    (-1 = skip)", a_vote),
    ("8", "press USE  (gamepad A)", a_press_use),
    ("9", "vent routine  (walk + RT)", a_vent_run),
    ("vt", "vent travel  - choose a connected vent (be inside one)", a_vent_options),
    ("k", "kill          - walk to nearest player and USE", a_kill),
    ("r", "report        (gamepad B)", a_report),
    ("e", "probe USE     - find the right button at the admin table", a_probe_use),
    ("v", "vent graph", a_vents),
    ("w2", "witnesses    - who was near the last kill / is near now", a_witnesses),
    ("p", "purge pads  (game must be CLOSED)", a_purge_pads),
    ("sb", "request sabotage - queue one for the model to pick", a_sab_request),
    ("b", "sabotage      - fire it (honours the queued request)", a_sabotage_choose),
    ("cal", "calibrate    - record exact sabotage click points", a_calibrate),
    ("f", "fake / knock", a_fake),
    ("u", "ui coords", a_uicoords),
]


def main():
    global utility, botlink, roleplay
    print(f"{YELLOW}Among-Us-AI command tester{RESET}\n")
    utility = preflight()
    import botlink as _bl
    import roleplay as _rp
    botlink, roleplay = _bl, _rp
    globals()["botlink"] = _bl
    globals()["roleplay"] = _rp

    print("Press 'q' to quit.")
    while True:
        print(f"\n{DIM}{'-'*60}{RESET}")
        for key, label, _ in MENU:
            print(f"  {key:>2}) {label}")
        try:
            choice = input("\n> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break
        if choice in ("q", "quit", "exit"):
            break
        for key, _label, fn in MENU:
            if choice == key:
                try:
                    show_state()
                    fn()
                except Exception as exc:
                    print(f"{RED}  action failed: {exc}{RESET}")
                break
        else:
            if choice:
                print(f"{RED}  unknown choice{RESET}")


if __name__ == "__main__":
    main()
