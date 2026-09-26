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


def a_vent_options(pre=None):
    banner("vent travel  (be inside a vent first)")
    raw = botlink.read_vent_options_raw().strip()
    if not raw:
        print("  no ventOptions.txt yet - the plugin writes it every snapshot.")
        print("  get inside a vent, then retry.")
        return

    diag = [ln for ln in raw.splitlines() if ln.startswith("#")]
    if diag:
        print("  " + diag[0].strip())
    else:
        print("  (no diagnostic line in ventOptions.txt)")

    ab = botlink.read_ability()
    print(f"  inVent={ab.get('invent')}  canVent={ab.get('canvent')}")
    if ab.get("invent") != "1":
        print("  you are NOT in a vent, so the game will not offer any travel options.")
        print("  press '9' to run the vent routine, then come back here.")

    opts = botlink.read_vent_options()
    if not opts:
        print("\n  no options reported. Check the #found / #field numbers above:")
        print("    #field=False  -> the private currentTarget lookup failed")
        print("    #found=0      -> no VentButton objects exist right now")
        print("    #found>0      -> buttons exist but none were usable")
        return

    here = None
    try:
        here = int(botlink.getGameData()["task_rooms"].split("|")[0]) if False else None
    except Exception:
        pass
    print(f"\n  {len(opts)} travel option(s):")
    for vid, x, y in opts:
        print(f"    vent {vid:2} at ({x:7.2f},{y:7.2f})")
    if len(opts) == 1:
        vid = opts[0][0]
        print(f"\n  only one option -> travelling to vent {vid}")
        time.sleep(0.4)
        print(f"  sent: {botlink.vent_travel(vid)}")
        return

    pick = pre
    if not pick:
        pick = input("  which vent id? > ").strip()
    if not pick:
        print("  cancelled")
        return
    try:
        vid = int(pick)
    except ValueError:
        print(f"  {pick!r} is not a vent id")
        return
    if vid not in [o[0] for o in opts]:
        print(f"  vent {vid} is not one of the options above")
        return
    time.sleep(0.4)
    print(f"  sent: {botlink.vent_travel(vid)}")


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


def _sabotage_choices():
    """Every sabotage the game currently reports, doors included."""
    opts = botlink.sabotage_options()
    aliases = {
        "Reactor": "reactor",
        "LifeSupp": "oxygen",
        "Comms": "comms",
        "Shields": "lights",
        "HeliSabotage": "heli",
        "MushroomMixupSabotage": "mushroom",
    }
    out = []
    for o in opts:
        out.append((aliases.get(o, o), o))
    return out


def _pick_sabotage(prompt="  > "):
    """Numbered list built from the live game state, or a typed name."""
    choices = _sabotage_choices()
    if not choices:
        print("  the game reported no sabotage entries - start a game as impostor.")
        return None
    print(f"  {botlink.sabotage_button_stats()}")
    for i, (friendly, real) in enumerate(choices, 1):
        kind = "doors" if real not in ("Reactor", "LifeSupp", "Comms", "Shields",
                                       "HeliSabotage", "MushroomMixupSabotage") else "other"
        print(f"  {i:>2}) {friendly:24} ({real}, {kind})")
    print("\n  type a number, or a name directly (e.g. Electrical, lights, o2)")
    raw = input(prompt).strip()
    if not raw:
        return None
    if raw.isdigit():
        n = int(raw)
        if 1 <= n <= len(choices):
            return choices[n - 1][0]
        print(f"  no entry #{n}")
        return None
    low = raw.lower()
    for friendly, _real in choices:
        if friendly == low:
            return friendly
    print(f"  {raw!r} is not one of the entries listed above")
    return None


def a_sabotage_choose(pre=None):
    banner("sabotage  (choose which one)")
    if not wait_for_game():
        return
    forced = pre or _pick_sabotage()
    if not forced:
        print("  cancelled")
        return
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "sab", os.path.join(os.path.dirname(os.path.realpath(__file__)),
                             "task-solvers", "Sabotage.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
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


def a_sab_request(pre=None):
    banner("queue a sabotage  (fires on the next 'b')")
    if not wait_for_game():
        return
    name = pre or _pick_sabotage()
    if not name:
        print("  cancelled")
        return
    print(f"  request_sabotage -> {roleplay.request_sabotage(name)}")
    print("  now press 'b' to fire it")


def a_detective():
    banner("detective  (two abilities: interrogate, and read notes)")
    role = botlink.get_role()
    ab = botlink.read_ability()
    print(f"  role={role}  ability buttons showing={ab.get('abilitycount', '?')}")
    for i, a in enumerate(roleplay.my_abilities(role, ab.get("abilitycount")), 1):
        print(f"    ability {i}: {a}")

    print("\n  -- interrogate (primary) --")
    print("  Stand next to a body or a player, then press ENTER to interrogate.")
    input()
    print(f"  result: {roleplay.detective_interrogate()}")
    time.sleep(0.8)

    print("\n  -- read notes (secondary) --")
    text = roleplay.detective_notes()
    pages = botlink.read_detective_notes()
    if not pages:
        print("  no detectiveData.txt yet - interrogate a body first.")
        return
    print(f"\n  the game has {len(pages)} page(s):\n")
    for p in pages:
        print(f"    body {p['index']}: {p.get('victim', '?')}")
        print(f"       location    {p.get('location', 'unknown')}")
        print(f"       preposition {p.get('preposition', 'none')}")
        print(f"       impostor    {p.get('impostor', 'unknown')}")
        for s in p["suspects"]:
            print(f"       near        {s}")
        print()
    print("  as the model would say it:")
    print("   ", text)


def a_detective_interrogate():
    banner("detective: interrogate  (primary ability)")
    if not wait_for_game():
        return
    print("  Stand next to a body or a player first.")
    print(f"  result: {roleplay.detective_interrogate()}")


def a_detective_notes():
    banner("detective: read notes  (secondary ability)")
    if not wait_for_game():
        return
    text = roleplay.detective_notes()
    if not text:
        return
    print("\n  notes:\n   ", text)


def a_scientist():
    banner("scientist vitals  (VitalsPanel data)")
    vitals = botlink.read_scientist_vitals()
    if not vitals:
        print("  no scientistData.txt - open Admin (vitals) first, then retry.")
        return
    for name, color, state in vitals:
        mark = "  <<<" if state != "ALIVE" else ""
        print(f"    {name:14} {color:8} {state}{mark}")


def a_judge(pre=None):
    banner("judge  (extra vote)")
    state = botlink.read_judge_state()
    if not state:
        print("  no judgeData.txt - you are probably not the Judge.")
        return
    print(f"  has an overrule use : {state.get('hasuse')}")
    print(f"  already used it     : {state.get('used')}")
    print(f"  blocked by tasks    : {state.get('blocked')}")
    if state.get("hasuse") != "1":
        print("  no overrule available")
        return
    if state.get("used") == "1":
        print("  already overruled this meeting")
        return
    if state.get("blocked") == "1":
        print("  blocked until your tasks are done")
        return
    target = pre or input("  playerId to overrule > ").strip()
    if not target:
        print("  cancelled")
        return
    print(f"  sent: {botlink.overrule(target)}")


def a_role_memory():
    banner("role facts the bot has learned")
    facts = roleplay.role_memory()
    if not facts:
        print("  nothing recorded yet.")
        return
    for f in facts:
        print(f"  - {f}")


def a_calibrate():
    banner("sabotage targets reported by the game")
    if not wait_for_game():
        return
    print("  " + botlink.sabotage_button_stats())
    btns = botlink.read_sabotage_buttons()
    if not btns:
        print("  no MapRoom objects found yet - start a game as impostor and retry.")
        return
    print(f"\n  the game exposes {len(btns)} sabotage entries. Names are read straight")
    print("  off the map objects, so there is nothing to calibrate:\n")
    for idx, name, val, active in btns:
        print(f"    {name:24} system={val:<3} active={active}")
    print("\n  door sabotages: " + ", ".join(
        n for n in botlink.sabotage_options()
        if n not in ("Reactor", "LifeSupp", "Comms", "Shields",
                     "HeliSabotage", "MushroomMixupSabotage")))
    print("  other sabotages: " + ", ".join(
        n for n in botlink.sabotage_options()
        if n in ("Reactor", "LifeSupp", "Comms", "Shields",
                 "HeliSabotage", "MushroomMixupSabotage")))
    print("\n  fire one with:  sb <name>   then   b")
    print("  e.g. sb Electrical  /  sb lights  /  sb comms")


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
    ("sb", "queue sabotage  e.g. 'sb Electrical' or bare 'sb' to pick", a_sab_request),
    ("b", "sabotage      - fire it  e.g. 'b lights'", a_sabotage_choose),
    ("cal", "sabotage list - entries the game reports (nothing to calibrate)", a_calibrate),
    ("dt", "detective   - both abilities: interrogate, then read notes", a_detective),
    ("di", "interrogate - detective primary ability (stand next to target)", a_detective_interrogate),
    ("dn", "notes       - detective secondary ability (open notebook)", a_detective_notes),
    ("sv", "scientist   - vitals: who is dead / disconnected", a_scientist),
    ("j", "judge       - overrule a player  e.g. 'j 3'", a_judge),
    ("rm", "role memory - facts the roles have learned", a_role_memory),
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
            raw = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not raw:
            continue
        if raw.lower() in ("q", "quit", "exit"):
            break
        # allow "sb Electrical" as well as a bare "sb"
        parts = raw.split(None, 1)
        choice = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else None
        for key, _label, fn in MENU:
            if choice == key:
                try:
                    show_state()
                    # handlers that take a target accept it as an argument
                    if arg and fn.__code__.co_argcount:
                        fn(arg)
                    else:
                        fn()
                except Exception as exc:
                    print(f"{RED}  action failed: {exc}{RESET}")
                break
        else:
            if choice:
                print(f"{RED}  unknown choice{RESET}")


if __name__ == "__main__":
    main()
