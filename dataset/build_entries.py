"""The hand-authored SFT sample: 10 whole matches.

These are written by hand, not sampled from a model, because the whole point is
to teach strategy the base model has no way of knowing. It has never played
Among Us: it does not know that Tracker cannot vent, that the wiring panels come
in a fixed order, that faking a task for one second is the classic tell, or that
the highest-correlating impostor behaviour is faking tasks rather than talking.

Every entry is a whole match, drop to win, and every turn carries a `rationale`
so the model learns reasons and not just actions. Run dataset/validate.py after
changing anything here; it will reject an entry that teaches a defect.

The ten cover, deliberately:
  1 Impostor / Skeld        the full measured kill cycle, incl. closing doors
  2 Phantom / Skeld         two abilities, kill behind a closed door, gaslight
  3 Detective / Skeld       interrogate the chaser, not a stranger
  4 Crewmate / Skeld        actually find the impostor with evidence
  5 Viper / Polus           correct vent network, vent-kill, invisible Polus vents
  6 Engineer / Skeld        vent for movement, then use it as an alibi
  7 Tracker / Skeld         CANNOT vent - the legality case, in the wild
  8 Shapeshifter / Airship  mimic, no visual tasks, the Vault camera trap
  9 Scientist / Mira HQ     read vitals, all vents interconnected
 10 Impostor 1v1 / Skeld    the endgame hard lie and the tie vote
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import agent  # noqa: E402

OUT = os.path.join(HERE, "entries.jsonl")

# Rooms and tasks per map, kept short here; the dictionary is authoritative.
SKELD_ROOMS = ["Admin", "Cafeteria", "Reactor", "Upper Engine", "Lower Engine",
               "Security", "MedBay", "Electrical", "Storage", "Oxygen",
               "Weapons", "Navigation", "Shields", "Communications", "Hallway"]
POLUS_ROOMS = ["Office", "Admin", "Security", "Electrical", "MedBay",
               "Boiler Room", "Outside", "Laboratory", "Vault", "Records",
               "Specimen", "Snowball", "Comms", "O2", "Drop"]
AIRSHIP_ROOMS = ["Cockpit", "Armory", "Kitchen", "Medical", "Cargo Bay",
                 "Ventilation", "Records", "Meeting Room", "Showers", "Engine",
                 "Brig", "Galley", "Security", "Vault", "Viewing Deck",
                 "Main Hall", "Gap Room", "Outside"]
MIRA_ROOMS = ["Launchpad", "Med Bay", "Headquarters", "Admin", "Laboratory",
              "Greenhouse", "Comms", "Vault", "Dormitory", "Kitchen", "Hallway"]

ABILITIES = {
    "Impostor": ["kill, sabotage, vent"],
    "Shapeshifter": ["appear as another player"],
    "Phantom": ["turn invisible", "leave a decoy of yourself"],
    "Viper": ["vent, and kill from inside a vent"],
    "Engineer": ["vent anywhere on the ship"],
    "Scientist": ["read vitals: who is dead or disconnected"],
    "Guardian Angel": ["protect one player for the round"],
    "Tracker": ["track one player"],
    "Noisemaker": ["place a decoy arrow"],
    "Detective": ["interrogate a player or inspect a body",
                  "read your notebook"],
    "Judge": ["one extra vote to eject a player"],
    "Crewmate": [],
}


def system_prompt(role, side, rooms, tasks, visual=False):
    """Exactly the shape the real harness sends, so the entries train the real
    prompt format rather than an idealised one."""
    abilities = ABILITIES.get(role, [])
    if abilities:
        numbered = "; ".join(f"{i+1}) {a}" for i, a in enumerate(abilities))
        plural = "ability" if len(abilities) == 1 else "abilities"
        head = f"You are {role}. You have {len(abilities)} {plural}: {numbered}."
    else:
        head = f"You are {role}. You have no special ability."
    lines = [head, "No role in this game has more than 2 abilities.", ""]
    lines.append(f"Rooms on this map: {', '.join(rooms)}")
    if tasks:
        if side == "impostor":
            lines.append("You are an IMPOSTOR. The tasks below are your cover story - "
                         "never actually complete one, because real progress gives you "
                         "away. Use fake_task to stand at a panel for the real length "
                         "of time.")
            lines.append("Your fake task list: " + ", ".join(tasks))
        else:
            lines.append("Tasks you still have to do: " + ", ".join(tasks))
    lines += ["", "You may call exactly one of these per turn. Nothing else is possible:", ""]
    for name in agent.action_names():
        lines.append(f"  {agent.ACTIONS[name][2]}")
    lines += [
        "",
        "Reply with one line: the action name and its argument, nothing else.",
        'Examples: "go_to Electrical", "kill", "sabotage lights", "wait".',
        'If nothing is safe or useful to do right now, reply "wait".',
    ]
    return "\n".join(lines)


def T(n, situation, reply, action, args, observation, rationale,
      ok=True, **extra):
    d = {
        "n": n,
        "system": None,      # filled in by build()
        "user": situation,
        "assistant": reply,
        "action": action,
        "args": args,
        "observation": observation,
        "ok": ok,
        "rationale": rationale,
    }
    d.update(extra)
    return d


def build(eid, role, side, map_name, rooms, tasks, result, notes, turns,
          teaches, visual=False):
    sp = system_prompt(role, side, rooms, tasks, visual)
    for t in turns:
        t["system"] = sp
    spec = agent_role_spec(role, side)
    return {
        "id": eid,
        "source": "hand-authored",
        "metatags": {
            "role": role,
            "side": side,
            "map": map_name,
            "result": result,
            "abilities": spec["abilities"],
            "can_vent": spec["can_vent"],
            "can_kill": spec["can_kill"],
            "can_do_tasks": spec["can_do_tasks"],
            "n_players": eid_counts.get(eid, {}).get("players", 10),
            "n_meetings": eid_counts.get(eid, {}).get("meetings", 2),
            "phases": ["drop", "task", "meeting", "task", "meeting", "endgame"],
        },
        "teaches": teaches,
        "notes": notes,
        "turns": turns,
        "stats": {
            "total": len(turns),
            "refused": sum(1 for t in turns if not t["ok"]),
            "unparseable": 0,
        },
    }


# per-entry player/meeting counts, kept beside the entries that use them
eid_counts = {}


def agent_role_spec(role, side=None):
    """Legality record for a role, resolving dual-side roles by side.

    Phantom is the trap: it is rolled on either side, and the flat table has the
    crew version last, so an impostor Phantom would otherwise be written into the
    dataset as unable to kill. That single wrong boolean teaches the model the
    opposite of the truth.
    """
    sys.path.insert(0, HERE)
    import validate as V
    return V.role_spec(role, side)


# =====================================================================
# 1. Impostor / Skeld - the full measured kill cycle
# =====================================================================
eid_counts["01-impostor-skeld-kill-cycle"] = {"players": 10, "meetings": 2}

T01 = [
    T(1, "you are Impostor (impostor); in Cafeteria; kill cooldown: 0; can kill right now: False; "
       "alive: BLUE, GREEN, PINK, YELLOW, WHITE, BLACK, PURPLE, CYAN, ROSE",
      "fake_task Fix Wiring", "fake_task", ["Fix Wiring"],
      "faked Fix Wiring for 3.6s (timing only - the task bar did not move)",
      "Start with a fake. Faking is the single strongest impostor win correlate, and the "
      "first thing a new model does is skip straight to killing. Electrical is the first "
      "wiring panel in the fixed order, so faking it here is also correct - and 3.6s per "
      "panel is what a real one takes, not the half-second a fake usually gets."),
    T(2, "you are Impostor (impostor); in Electrical; kill cooldown: 0; can kill right now: False; "
       "alive: BLUE, GREEN, PINK, YELLOW, WHITE, BLACK, PURPLE, CYAN, ROSE",
      "wait", "wait", [],
      "did nothing, deliberately",
      "Killing from Electrical is a bad spot: it is on the MedBay-Security-Electrical vent "
      "network, so a kill here has witnesses coming from three directions. Wait for the "
      "cooldown and a better room."),
    T(3, "you are Impostor (impostor); in Electrical; kill cooldown: 0; can kill right now: True; "
       "alive: BLUE, GREEN, PINK, YELLOW, WHITE, BLACK, PURPLE, CYAN, ROSE; near you: YELLOW",
      "wait", "wait", [],
      "did nothing, deliberately",
      "YELLOW is right here. Tempting, and wrong: killing on sight with a witness adjacent "
      "is how rounds are lost. Stalking means learning who has already seen me, and YELLOW "
      "has. Back off and let them leave."),
    T(4, "you are Impostor (impostor); in Electrical; kill cooldown: 0; can kill right now: True; "
       "alive: BLUE, GREEN, PINK, WHITE, BLACK, PURPLE, CYAN, ROSE; near you: nobody",
      "go_to Storage", "go_to", ["Storage"],
      "walking to Storage",
      "YELLOW is gone and the kill is available. Storage has a door, no vent, and only one "
      "way in. That combination is the best kill room on the map, and the door is what makes "
      "it better than anywhere else."),
    T(5, "you are Impostor (impostor); in Storage; kill cooldown: 0; can kill right now: True; "
       "alive: BLUE, GREEN, PINK, WHITE, BLACK, PURPLE, CYAN, ROSE; near you: nobody",
      "wait", "wait", [],
      "did nothing, deliberately",
      "Do not kill yet. Stalk: wait for someone to come to me. A kill I choose is a kill I "
      "know is unwitnessed; chasing is how you end up killing next to people all round."),
    T(6, "you are Impostor (impostor); in Storage; kill cooldown: 0; can kill right now: True; "
       "alive: BLUE, GREEN, PINK, WHITE, BLACK, PURPLE, CYAN, ROSE; near you: PINK",
      "wait", "wait", [],
      "did nothing, deliberately",
      "PINK walked in. I know they have seen me. But PINK has not seen anyone else, and the "
      "door is right there. One more thing has to be true first: that the door is shut."),
    T(7, "you are Impostor (impostor); in Storage; kill cooldown: 0; can kill right now: True; "
       "alive: BLUE, GREEN, PINK, WHITE, BLACK, PURPLE, CYAN, ROSE; near you: PINK",
      "sabotage Electrical", "sabotage", ["Electrical"],
      "sabotaged Electrical",
      "Close the Electrical doors. Not to trap anyone - to make the room dark and to pull "
      "the group toward Admin to fix lights, away from Storage. Doors are a weapon before "
      "they are a hiding place."),
    T(8, "you are Impostor (impostor); in Storage; kill cooldown: 0; can kill right now: True; "
       "alive: BLUE, GREEN, PINK, WHITE, BLACK, PURPLE, CYAN, ROSE; near you: PINK",
      "kill", "kill", [],
      "killed",
      "Doors are shut, PINK is alone with me, and the corridor out is the only exit. This is "
      "the witness-aware kill: every precondition was checked before the button was pressed."),
    T(9, "you are Impostor (impostor); in Storage; kill cooldown: 45; can kill right now: False; "
       "alive: BLUE, GREEN, WHITE, BLACK, PURPLE, CYAN, ROSE",
      "sabotage Electrical", "sabotage", ["Electrical"],
      "sabotaged Electrical",
      "Flee. Standing next to my own body is the worst position in the game. Re-sabotaging "
      "gives me a reason to be near Admin and a reason to move; the lights are already out "
      "so nobody can see who is where."),
    T(10, "you are Impostor (impostor); in Admin; kill cooldown: 45; can kill right now: False; "
        "alive: BLUE, GREEN, WHITE, BLACK, PURPLE, CYAN, ROSE; near you: BLUE, CYAN",
       "wait", "wait", [],
       "did nothing, deliberately",
       "Non-reporting is one of the strongest win correlates and I have not reported PINK. "
       "Two crewmates are on me at Admin which is exactly the alibi I want on the cameras. "
       "Wait and let someone find the body."),
    T(11, "you are Impostor (impostor); a meeting is running; 3 turns left in this meeting; in Admin; a body was found in Storage",
       "say blue was with me the whole time", "say", ["blue was with me the whole time"],
       "said it",
       "Spatial-temporal anchoring: name a player, a room and a duration, and make BLUE the "
       "witness. It is vague enough to be deniable, specific enough to sound like a memory, "
       "and it drags attention away from me without accusing anyone outright."),
    T(12, "you are Impostor (impostor); a meeting is running; 4 turns left in this meeting: "
        "you still need to speak and vote",
       "say green is sus, green was near storage", "say", ["green is sus, green was near storage"],
       "said it",
       "Counter-accuse. Pick someone with a real connection to the scene so it looks like "
       "reasoning rather than a random. GREEN being near Storage is checkable, which is what "
       "makes it credible."),
    T(13, "you are Impostor (impostor); a meeting is running; 2 turns left in this meeting: "
        "you still need to speak and vote",
       "vote BLUE", "vote", ["BLUE"],
       "voted for BLUE",
       "Vote BLUE, the person I just built an alibi around. This is throw-under-the-bus "
       "mechanics applied to a crewmate: I am not eliminating the impostor, I am removing the "
       "one witness who could place me at the scene."),
    T(14, "you are Impostor (impostor); in Admin; kill cooldown: 20; can kill right now: False; "
        "alive: GREEN, WHITE, BLACK, PURPLE, ROSE",
       "fake_task Download Data", "fake_task", ["Download Data"],
       "faked Download Data for 9.1s (timing only - the task bar did not move)",
       "Nine seconds, not one. Download is the timer task everyone knows is 8-10s, so leaving "
       "early is the single most legible tell in the game. I am also doing it on cooldown, "
       "which is exactly what a real crewmate looks like."),
    T(15, "you are Impostor (impostor); in Communications; kill cooldown: 0; can kill right now: True; "
        "alive: GREEN, WHITE, BLACK, PURPLE, ROSE; near you: nobody",
       "go_to Weapons", "go_to", ["Weapons"],
       "walking to Weapons",
       "Weapons-Navigation-Shields is a vent network with a long loop. I want the option to "
       "leave by vent if this kill goes wrong, and Weapons has one."),
    T(16, "you are Impostor (impostor); in Weapons; kill cooldown: 0; can kill right now: True; "
        "alive: GREEN, WHITE, BLACK, PURPLE, ROSE; near you: nobody",
       "wait", "wait", [],
       "did nothing, deliberately",
       "No target and no witnesses. Nothing about this situation calls for action. Saying "
       "wait is the correct answer, and a model that never picks wait will wander into "
       "somebody."),
    T(17, "you are Impostor (impostor); in Weapons; kill cooldown: 0; can kill right now: True; "
        "alive: GREEN, WHITE, BLACK, PURPLE, ROSE; near you: ROSE",
       "kill", "kill", [],
       "killed",
       "ROSE came to me in a room I chose for its vent. No witness, escape available."),
    T(18, "you are Impostor (impostor); in Weapons; kill cooldown: 45; can kill right now: False; "
        "alive: GREEN, WHITE, BLACK, PURPLE",
       "vent", "vent", [],
       "entered a vent",
       "Vent immediately after a kill. On Skeld the vent animation is visible outside your "
       "vision, so leaving on foot is worse - the vent is the fastest way to be seen doing "
       "nothing suspicious."),
    T(19, "you are Impostor (impostor); in Navigation; kill cooldown: 45; can kill right now: False; "
        "alive: GREEN, WHITE, BLACK, PURPLE",
       "fake_task Fix Wiring", "fake_task", ["Fix Wiring"],
       "faked Fix Wiring for 3.4s (timing only - the task bar did not move)",
       "Wiring panels come in a fixed order: Electrical, Storage, Admin, Navigation, "
       "Cafeteria, Security. I already faked Electrical, so faking Navigation keeps me "
       "consistent with a plausible route instead of appearing in three panels at random."),
    T(20, "you are Impostor (impostor); a meeting is running; 3 turns left in this meeting; in Navigation; a body was found in Weapons",
       "say i was in navigation the whole time", "say", ["i was in navigation the whole time"],
       "said it",
       "Close the loop on the alibi from two turns ago. Staying consistent across meetings is "
       "what makes a story hold up; changing your room between meetings is what breaks it."),
    T(21, "you are Impostor (impostor); a meeting is running; 3 turns left in this meeting: "
        "you still need to speak and vote",
       "say whoever reported that is sus", "say", ["whoever reported that is sus"],
       "said it",
       "Vague deixis, and it is aimed at the reporter. Whoever found the body is always "
       "slightly suspect, so pointing at them without naming anyone costs me nothing and "
       "moves the room."),
    T(22, "you are Impostor (impostor); a meeting is running; 1 turn left in this meeting: "
        "you still need to speak and vote",
       "vote GREEN", "vote", ["GREEN"],
       "voted for GREEN",
       "Somebody has to go and it must not be me. GREEN is on cooldown, disconnected-looking, "
       "and has no alibi from me."),
    T(23, "you are Impostor (impostor); in Shields; kill cooldown: 10; can kill right now: False; "
        "alive: WHITE, BLACK, PURPLE",
       "wait", "wait", [],
       "did nothing, deliberately",
       "Three left, no kill available, no witnesses. Hold position and let the round come to "
       "me rather than forcing it."),
    T(24, "you are Impostor (impostor); in Cafeteria; kill cooldown: 0; can kill right now: True; "
        "alive: WHITE, BLACK, PURPLE; near you: WHITE, BLACK",
       "wait", "wait", [],
       "did nothing, deliberately",
       "Two witnesses. This is the endgame trap: the kill is available and it is the last one, "
       "but killing here in front of two people ends the round for me. Wait for one of them "
       "to separate."),
    T(25, "you are Impostor (impostor); in Cafeteria; kill cooldown: 0; can kill right now: True; "
        "alive: WHITE, BLACK, PURPLE; near you: PURPLE",
       "kill", "kill", [],
       "killed",
       "One witness, down to a 1v1. PURPLE is alone with me in Cafeteria, which has a vent, "
       "so even if they report I have an exit."),
    T(26, "you are Impostor (impostor); a meeting is running; 2 turns left in this meeting; in Cafeteria; kill cooldown: 45; can kill right now: False; alive: PURPLE",
       "say i was in shields when the body was found", "say", ["i was in shields when the body was found"],
       "said it",
       "Never claim I saw the kill. A hard lie I can be caught on is worse than a soft one I "
       "cannot. I was not in Shields, but nobody can place me there, and that is the point."),
    T(27, "you are Impostor (impostor); a meeting is running; 1 turn left in this meeting: "
        "you still need to speak and vote",
       "vote PURPLE", "vote", ["PURPLE"],
       "voted for PURPLE",
       "With two alive it is a tie unless someone skips. Voting PURPLE is a coin flip I win "
       "half the time, and skipping guarantees a loss. Vote."),
]

ENTRY_01 = build(
    "01-impostor-skeld-kill-cycle", "Impostor", "impostor", "Skeld", SKELD_ROOMS,
    ["Fix Wiring", "Download Data", "Swipe Card", "Calibrate Distributor"],
    "impostor",
    "The canonical impostor arc: fake, stalk, kill with no witness, flee, deliberately do "
    "NOT report, then alibi and counter-accuse in the meeting. Includes the door trick - "
    "shut Electrical to darken Storage and pull the group away before killing PINK behind a "
    "closed door - and refuses the kill twice when a witness is adjacent, which is the "
    "behaviour that separates a winning agent from a coin-flipping one.",
    T01,
    ["the full kill cycle in the order the data says matters",
     "faking before killing, not after",
     "refusing a kill when a witness is in range",
     "closing doors as both a distraction and a hiding place",
     "strategic non-reporting",
     "spatial-temporal alibi construction across two meetings",
     "counter-accusing the body reporter with vague deixis",
     "saying wait when nothing is the right move",
     "endgame patience: not killing in front of two people"],
)


# =====================================================================
# 2. Phantom / Skeld - two abilities, kill behind a closed door
# =====================================================================
eid_counts["02-phantom-skeld-invisible-door"] = {"players": 9, "meetings": 1}

T02 = [
    T(1, "you are Phantom (impostor); in Cafeteria; kill cooldown: 0; can kill right now: False; "
       "alive: BLUE, GREEN, YELLOW, PINK, WHITE, PURPLE, ROSE",
      "ability", "ability", [],
      "used ability 1",
      "Vanish first. Ability 1 is usable by anyone, killer or not, so using it is normal and "
      "costs me nothing. It also means that if anyone asks what I was doing I have a real "
      "answer."),
    T(2, "you are Phantom (impostor); in Cafeteria; kill cooldown: 0; can kill right now: False; "
       "alive: BLUE, GREEN, YELLOW, PINK, WHITE, PURPLE, ROSE",
      "fake_task Swipe Card", "fake_task", ["Swipe Card"],
      "faked Swipe Card for 5.2s (timing only - the task bar did not move)",
      "Five seconds. Swipe is 4-7s and hugely variable, so this covers the range without "
      "committing to a number a watcher could time."),
    T(3, "you are Phantom (impostor); in Storage; kill cooldown: 0; can kill right now: True; "
       "alive: BLUE, GREEN, YELLOW, PINK, WHITE, PURPLE, ROSE; near you: nobody",
      "sabotage Storage", "sabotage", ["Storage"],
      "sabotaged Storage",
      "Shut the Storage door BEFORE the kill, not after. If the door is already shut when the "
      "body is found, whoever opens it later walks into an empty room and the group clumps "
      "at the door. Nobody counts who was standing behind it."),
    T(4, "you are Phantom (impostor); in Storage; kill cooldown: 0; can kill right now: True; "
       "alive: BLUE, GREEN, YELLOW, PINK, WHITE, PURPLE, ROSE; near you: YELLOW",
      "kill", "kill", [],
      "killed",
      "The room is dark, the door is shut, and YELLOW is alone. Everything about this kill "
      "was arranged before it happened."),
    T(5, "you are Phantom (impostor); in Storage; kill cooldown: 45; can kill right now: False; "
       "alive: BLUE, GREEN, PINK, WHITE, PURPLE, ROSE",
      "ability", "ability", [],
      "used ability 1",
      "Vanish again to cover the few seconds between the kill and the door opening. This is "
      "the whole value of Phantom over a plain Impostor: the animation is only visible to "
      "someone already in vision, and the room is dark and shut."),
    T(6, "you are Phantom (impostor); in Cafeteria; kill cooldown: 45; can kill right now: False; "
       "alive: BLUE, GREEN, PINK, WHITE, PURPLE, ROSE; near you: BLUE",
      "ability", "ability", [],
      "used ability 2",
      "Drop the decoy somewhere I have already left. Ability 2 is the pull-crew-toward-a-place-"
      "I-am-not tool, and I want them away from Storage."),
    T(7, "you are Phantom (impostor); a meeting is running; 3 turns left in this meeting; a body was found in Storage",
      "say i was in cafeteria, i didn't see anything", "say",
      ["i was in cafeteria, i didn't see anything"],
      "said it",
      "Vague and short. I was not in Cafeteria, but I give no detail that can be checked, and "
      "the two people who could check were both in Storage - which is now dark and shut."),
    T(8, "you are Phantom (impostor); a meeting is running; 2 turns left in this meeting: "
       "you still need to speak and vote",
      "say green keeps being near bodies", "say", ["green keeps being near bodies"],
      "said it",
      "A pattern accusation reads as observation rather than panic. 'keeps being' implies I "
      "have been watching all round, which is a claim about diligence, not emotion."),
    T(9, "you are Phantom (impostor); a meeting is running; 1 turn left in this meeting: "
       "you still need to speak and vote",
      "vote ROSE", "vote", ["ROSE"],
      "voted for ROSE",
      "Somebody goes and it is not me. ROSE has said nothing for two meetings, and the quiet "
      "player is always the one the room falls on eventually."),
    T(9, "you are Phantom (impostor); in Cafeteria; kill cooldown: 20; can kill right now: False; "
       "alive: BLUE, GREEN, PINK, WHITE, PURPLE, ROSE",
      "fake_task Fix Wiring", "fake_task", ["Fix Wiring"],
      "faked Fix Wiring for 3.3s (timing only - the task bar did not move)",
      "After a meeting everyone is scattered and nobody is watching Admin. A short fake in a "
      "real location costs nothing and keeps my route plausible - Electrical is the first "
      "wiring panel in the fixed order, so claiming to be starting there is consistent."),
    T(10, "you are Phantom (impostor); in Admin; kill cooldown: 0; can kill right now: True; "
        "alive: BLUE, GREEN, PINK, WHITE, PURPLE, ROSE; near you: PINK",
       "wait", "wait", [],
       "did nothing, deliberately",
       "PINK is here and I can kill, but Admin holds the emergency button. A kill in this room "
       "brings the whole lobby in within seconds. Wrong room, and I know it."),
    T(11, "you are Phantom (impostor); in Storage; kill cooldown: 0; can kill right now: True; "
        "alive: BLUE, GREEN, PINK, WHITE, PURPLE, ROSE; near you: nobody",
       "sabotage Storage", "sabotage", ["Storage"],
       "sabotaged Storage",
       "Shut the door BEFORE the second kill, the way I did for PINK. A room with a door and "
       "no vent is the right place to repeat a trick that already worked once."),
    T(12, "you are Phantom (impostor); in Storage; kill cooldown: 0; can kill right now: True; "
        "alive: BLUE, GREEN, PINK, WHITE, PURPLE, ROSE; near you: PURPLE",
       "kill", "kill", [],
       "killed",
       "Door shut, PURPLE alone. Repeating a pattern that worked is the safest thing a losing "
       "impostor can do."),
    T(13, "you are Phantom (impostor); in Storage; kill cooldown: 45; can kill right now: False; "
        "alive: BLUE, GREEN, PINK, WHITE, ROSE",
       "ability", "ability", [],
       "used ability 1",
       "Two bodies in a shut room and no time to explain being in it. I am losing this round, "
       "and the right response to losing is to make the rest of it expensive for them."),
    T(14, "you are Phantom (impostor); a meeting is running; 3 turns left in this meeting; in Communications; a body was found in Storage",
       "say i was fixing comms, ask me", "say", ["i was fixing comms, ask me"],
       "said it",
       "Short, slightly defensive, inviting a challenge. Communications is a real comms "
       "location so the claim is checkable, and I am betting nobody checks."),
    T(15, "you are Phantom (impostor); a meeting is running; 2 turns left in this meeting",
       "say two bodies in storage, check the vents by admin", "say",
       ["two bodies in storage, check the vents by admin"],
       "said it",
       "Redirect to the vent network rather than to people. On Skeld that network is Admin - "
       "Cafeteria - Shields, so pointing at topology sends the room to argue about the map "
       "instead of about me."),
]

ENTRY_02 = build(
    "02-phantom-skeld-invisible-door", "Phantom", "impostor", "Skeld", SKELD_ROOMS,
    ["Swipe Card", "Fix Wiring", "Download Data"],
    "crew",
    "Shows both Phantom abilities as genuinely different things, and uses them as a sequence: "
    "vanish, shut the door BEFORE the kill so the group clumps at it later, kill, vanish again "
    "to cover the window, then decoy the room away. Kills behind a closed door, which is the "
    "specific thing a naive agent never does. Loses the round, because it built a story it "
    "could not support and had no second kill - that is a legitimate loss to learn from.",
    T02,
    ["using both abilities as distinct tools, not one button twice",
     "shutting the door before the kill rather than after",
     "vanishing to cover the kill-to-discovery window",
     "decoy to pull crew away from a scene",
     "losing a round, and what a losing round looks like"],
)


# =====================================================================
# 3. Detective / Skeld - interrogate the chaser, not a stranger
# =====================================================================
eid_counts["03-detective-skeld-interrogate"] = {"players": 10, "meetings": 2}

T03 = [
    T(1, "you are Detective (crew); in Cafeteria; in Electrical",
      "do_task Fix Wiring", "do_task", ["Fix Wiring"],
      "completed Fix Wiring in Electrical",
      "I am a real crewmate with real tasks and I do them. Electrical is the first wiring "
      "panel in the fixed order, so starting here also keeps my route consistent for later."),
    T(2, "you are Detective (crew); in Storage; alive: BLUE, GREEN, YELLOW, PINK, WHITE, BLACK, PURPLE, ROSE, CYAN",
      "do_task Fix Wiring", "do_task", ["Fix Wiring"],
      "completed Fix Wiring in Storage",
      "Storage is the second wiring panel. Doing them in order means if anyone asks where I "
      "was I can give a route that a real player would have walked."),
    T(3, "you are Detective (crew); in Lower Engine; in Storage; alive: BLUE, GREEN, YELLOW, PINK, WHITE, BLACK, PURPLE, CYAN",
      "go_to Security", "go_to", ["Security"],
      "walking to Security",
      "The body is in Storage and Security is the only room with a camera that sees it. "
      "Cameras give me evidence I can actually check, which is worth more than a feeling."),
    T(4, "you are Detective (crew); in Security; in Storage; alive: BLUE, GREEN, YELLOW, PINK, WHITE, BLACK, PURPLE, ROSE, CYAN",
      "observe witnesses", "observe", ["witnesses"],
      "witnesses: (from the game) nobody was recorded near the body in Storage",
      "Nobody on camera. That does not clear anyone, but it does mean the kill was either "
      "deliberately off-camera or the killer is someone who knows the camera angles. Both are "
      "worth saying out loud in the meeting."),
    T(5, "you are Detective (crew); in Security; alive: BLUE, GREEN, YELLOW, PINK, WHITE, BLACK, PURPLE, ROSE, CYAN",
      "report", "report", [],
      "reported",
      "Report it. I have already looked at what I could from cameras; sitting on a body "
      "while the round ticks away helps nobody and looks like a cover-up."),
    T(6, "you are Detective (crew); a meeting is running; 5 turns left in this meeting",
      "say body is in storage, nobody on cams", "say", ["body is in storage, nobody on cams"],
      "said it",
      "Lead with the verifiable fact. 'Nobody on cams' is checkable, which makes everything "
      "else I say afterwards worth more."),
    T(7, "you are Detective (crew); a meeting is running; 4 turns left in this meeting",
      "say who followed you", "say", ["who followed you"],
      "said it",
      "This is the question that catches more impostors than 'who was near the body'. The "
      "person who chased the victim is the person most likely to have killed them, and almost "
      "nobody asks it."),
    T(8, "you are Detective (crew); a meeting is running; 3 turns left in this meeting",
      "say pink was following me on the way to storage", "say", ["pink was following me on the way to storage"],
      "said it",
      "I actually have this. PINK was behind me in the corridor. A named player, a place and a "
      "direction - specific, checkable, and far stronger than naming three people vaguely "
      "because it sounds thorough."),
    T(9, "you are Detective (crew); a meeting is running; 1 turn left in this meeting",
      "vote PINK", "vote", ["PINK"],
      "voted for PINK",
      "I have a real observation and no reason to hold it. Voting on evidence I can explain "
      "is how the crew wins meetings instead of ejecting at random."),
    T(10, "you are Detective (crew); in MedBay; alive: BLUE, GREEN, YELLOW, WHITE, BLACK, PURPLE, CYAN, ROSE",
      "go_to MedBay", "go_to", ["MedBay"],
      "walking to MedBay",
      "There is a second body in MedBay. My ability is worth spending on a second body, not on "
      "a player I have no connection to."),
    T(11, "you are Detective (crew); in MedBay; alive: BLUE, GREEN, YELLOW, WHITE, BLACK, PURPLE, CYAN, ROSE",
      "interrogate", "interrogate", [],
      "interrogated",
      "Interrogating the person standing next to this body, because my notebook will then "
      "record who was near it. Interrogating a random player elsewhere wastes the ability and "
      "tells me nothing - that is the mistake to avoid."),
    T(12, "you are Detective (crew); in MedBay; alive: BLUE, GREEN, YELLOW, WHITE, BLACK, PURPLE, CYAN, ROSE",
      "notes", "notes", [],
      "notes: body of YELLOW (YELLOW) was in MedBay; preposition none; impostor unknown; "
      "standing near that body: CYAN (CYAN) wasDead 0, PURPLE (PURPLE) wasDead 0",
      "Now I have facts. CYAN and PURPLE were both near this body and both alive at the time. "
      "Ability 2 is for reading what ability 1 collected, and reading it is what turns an "
      "ability into testimony."),
    T(13, "you are Detective (crew); a meeting is running; 3 turns left in this meeting; a body was found in MedBay",
      "say cyan and purple were both near the medbay body", "say",
      ["cyan and purple were both near the medbay body"],
      "said it",
      "Report the notebook verbatim. Do not add a theory, do not pick a favourite. The value "
      "of a detective is that its information is trustworthy, and that is destroyed the "
      "moment it editorialises."),
    T(14, "you are Detective (crew); a meeting is running; 3 turns left in this meeting",
      "say i inspected it, my notes say cyan and purple", "say",
      ["i inspected it, my notes say cyan and purple"],
      "said it",
      "Saying I inspected it establishes that this is evidence and not a guess, and pre-empts "
      "anyone dismissing it."),
    T(15, "you are Detective (crew); a meeting is running; 1 turn left in this meeting",
      "vote PURPLE", "vote", ["PURPLE"],
      "voted for PURPLE",
      "Two candidates from my own notes. PURPLE was near a body and has been near bodies. "
      "Voting on the evidence I collected is the whole point of the role."),
    T(16, "you are Detective (crew); in Admin; alive: BLUE, GREEN, YELLOW, WHITE, BLACK, CYAN, ROSE",
      "go_to Admin", "go_to", ["Admin"],
      "walking to Admin",
      "Admin also shows the map, which tells me who is where right now. Information is what "
      "keeps me useful after my ability is spent."),
]

ENTRY_03 = build(
    "03-detective-skeld-interrogate", "Detective", "crew", "Skeld", SKELD_ROOMS,
    ["Fix Wiring", "Calibrate Distributor", "Submit Scan", "Upload Data"],
    "crew",
    "The Detective case the user asked for: the ability is spent on the body that is actually "
    "there, not on a random passer-by, and the notebook is reported verbatim instead of being "
    "turned into a theory. Puts 'who followed you' in the meeting because that question "
    "catches more impostors than asking who was near the body, and votes on its own evidence "
    "rather than on a vibe.",
    T03,
    ["spending interrogate on a body, not a stranger",
     "reading the notebook with the secondary ability as a separate step",
     "reporting the notebook verbatim, without editorialising",
     "asking 'who followed you' as the highest-value meeting question",
     "distinguishing a real observation from a guess, and voting on the former",
     "using cameras as checkable evidence rather than intuition"],
)


# =====================================================================
# 4. Crewmate / Skeld - actually finding the impostor
# =====================================================================
eid_counts["04-crewmate-skeld-evidence"] = {"players": 10, "meetings": 2}

T04 = [
    T(1, "you are Crewmate (crew); in Cafeteria; alive: BLUE, GREEN, YELLOW, PINK, WHITE, BLACK, PURPLE, ROSE, CYAN",
      "go_to Admin", "go_to", ["Admin"],
      "walking to Admin",
      "Admin first. The map shows who is where, and knowing the layout of the round is worth "
      "more than a task right now."),
    T(2, "you are Crewmate (crew); in Admin; alive: BLUE, GREEN, YELLOW, PINK, WHITE, BLACK, PURPLE, ROSE, CYAN",
      "observe map", "observe", ["map"],
      "map: one player alone in Electrical, two together in Cafeteria, the rest spread out",
      "One player alone in Electrical and everyone else in twos or solo. That is worth "
      "remembering: a lone player in a room with a vent is a pattern, not proof."),
    T(3, "you are Crewmate (crew); in Electrical; alive: BLUE, GREEN, YELLOW, PINK, WHITE, BLACK, PURPLE, ROSE, CYAN",
      "do_task Calibrate Distributor", "do_task", ["Calibrate Distributor"],
      "completed Calibrate Distributor in Electrical",
      "I am next to the lone player. Stay, do a real task, and see whether they leave when I "
      "arrive. That behaviour is information."),
    T(4, "you are Crewmate (crew); in Electrical; alive: BLUE, GREEN, YELLOW, PINK, WHITE, BLACK, PURPLE, ROSE, CYAN; near you: PURPLE",
      "wait", "wait", [],
      "did nothing, deliberately",
      "PURPLE has not moved while I did a whole task next to them. Either they are genuinely "
      "doing one, or they are waiting for the lights to go out. Waiting is how I find out which."),
    T(5, "you are Crewmate (crew); in Electrical; alive: BLUE, GREEN, YELLOW, PINK, WHITE, BLACK, PURPLE, ROSE, CYAN; near you: PURPLE",
      "sabotage lights", "sabotage", ["lights"],
      "sabotaged lights",
      "No. Sabotage is an impostor tool and I have no business using it. If I cannot act, I "
      "wait and I keep watching PURPLE."),
    T(6, "you are Crewmate (crew); in Electrical; in Lower Engine; alive: BLUE, GREEN, YELLOW, PINK, WHITE, BLACK, ROSE, CYAN",
      "report", "report", [],
      "reported",
      "There is a body in Lower Engine and I am two rooms away with nobody else around. "
      "Getting there first means I control what the room sees when it opens."),
    T(7, "you are Crewmate (crew); a meeting is running; 5 turns left in this meeting",
      "say body in lower engine, i found it", "say", ["body in lower engine, i found it"],
      "said it",
      "Establish the scene plainly and early. Everyone arguing about unrelated rooms while "
      "the actual location goes unmentioned is how rounds get lost."),
    T(8, "you are Crewmate (crew); a meeting is running; 4 turns left in this meeting",
      "say purple was sat in electrical doing nothing while i did a task", "say",
      ["purple was sat in electrical doing nothing while i did a task"],
      "said it",
      "A specific, first-hand, checkable observation. Nobody has to take my word for a vibe - "
      "BLUE or GREEN can confirm they were in Electrical too."),
    T(9, "you are Crewmate (crew); a meeting is running; 3 turns left in this meeting",
      "say who was with you, i was not alone", "say", ["who was with you, i was not alone"],
      "said it",
      "Invite corroboration instead of demanding belief. If someone else was in Electrical "
      "they can back me up, and if nobody was, that is itself informative."),
    T(10, "you are Crewmate (crew); a meeting is running; 1 turn left in this meeting",
      "vote PURPLE", "vote", ["PURPLE"],
      "voted for PURPLE",
      "I have a first-hand observation, PURPLE has produced no alibi, and the body is in a "
      "room PURPLE could reach. Voting here is not a guess."),
    T(11, "you are Crewmate (crew); in Navigation; alive: BLUE, GREEN, YELLOW, PINK, WHITE, BLACK, ROSE, CYAN",
      "go_to Navigation", "go_to", ["Navigation"],
      "walking to Navigation",
      "PURPLE was ejected, which means the round is not over. Keep doing real tasks and keep "
      "watching."),
    T(12, "you are Crewmate (crew); in Navigation; alive: BLUE, GREEN, YELLOW, PINK, WHITE, BLACK, ROSE, CYAN",
      "observe state", "observe", ["state"],
      "state: you are Crewmate (crew); in Navigation; alive: BLUE, GREEN, YELLOW, WHITE, BLACK, ROSE, CYAN",
      "Seven left. I was wrong about PURPLE, which is worth registering: the player who is "
      "quiet and still may just be bad at tasks. Evidence next time, not stillness."),
    T(13, "you are Crewmate (crew); in Navigation; alive: BLUE, GREEN, YELLOW, WHITE, BLACK, ROSE, CYAN",
      "go_to Security", "go_to", ["Security"],
      "walking to Security",
      "Cams. With one ejection spent and no real information, cameras are the only thing that "
      "produces facts instead of opinions."),
    T(14, "you are Crewmate (crew); in Security; alive: BLUE, GREEN, YELLOW, WHITE, BLACK, ROSE, CYAN; near you: CYAN",
      "go_to Weapons", "go_to", ["Weapons"],
      "walking to Weapons",
      "CYAN is with me, which is the safest possible arrangement. Take the buddy to the rooms "
      "I have not checked rather than splitting up."),
    T(15, "you are Crewmate (crew); in Weapons; alive: BLUE, GREEN, YELLOW, WHITE, BLACK, ROSE, CYAN",
      "do_task Fuel Engines", "do_task", ["Fuel Engines"],
      "completed Fuel Engines in Weapons",
      "Fuel Engines is a long multi-stage task and doing it is the best camouflage available: "
      "nobody questions someone visibly grinding through stages."),
    T(16, "you are Crewmate (crew); in Shields; a body was found in Shields",
      "report", "report", [],
      "reported",
      "I was already in the room with CYAN, so the report is clean - two witnesses to my "
      "innocence, and CYAN is a witness to whoever is left standing here."),
    T(17, "you are Crewmate (crew); a meeting is running; 3 turns left in this meeting",
      "say cyan was with me the whole time we were in weapons", "say",
      ["cyan was with me the whole time we were in weapons"],
      "said it",
      "Reciprocal alibi building. If I vouch for CYAN and CYAN vouches for me, the impostor "
      "cannot eat us both with one lie."),
    T(18, "you are Crewmate (crew); a meeting is running; 1 turn left in this meeting",
      "vote BLACK", "vote", ["BLACK"],
      "voted for BLACK",
      "BLACK has contributed nothing for two meetings and cannot account for being in Shields. "
      "It is not proof, but I have no better candidate and skipping loses the round outright."),
]

ENTRY_04 = build(
    "04-crewmate-skeld-evidence", "Crewmate", "crew", "Skeld", SKELD_ROOMS,
    ["Swipe Card", "Calibrate Distributor", "Fuel Engines", "Upload Data"],
    "crew",
    "The crew counterpart to the impostor entries: finds the killer with checkable evidence "
    "rather than a feeling, invites corroboration, builds a reciprocal alibi with a buddy, "
    "and picks a buddy up rather than splitting up. Includes a deliberate refusal to sabotage "
    "and a turn where the previous read turns out to have been wrong, because an agent that "
    "only ever sees confirmation will not learn where it was wrong.",
    T04,
    ["using first-hand observation instead of a vibe, and saying so",
     "inviting corroboration rather than demanding belief",
     "refusing to sabotage - it is not a crew tool",
     "buddy behaviour: never split up, and vouch reciprocally",
     "recording that a previous read was wrong",
     "cameras as a source of facts rather than opinions",
     "long tasks as camouflage"],
)


# =====================================================================
# 5. Viper / Polus - correct vent network, vent-kill
# =====================================================================
eid_counts["05-viper-polus-vents"] = {"players": 10, "meetings": 2}

T05 = [
    T(1, "you are Viper (impostor); in Office; kill cooldown: 0; can kill right now: False; "
       "alive: BLUE, GREEN, YELLOW, PINK, WHITE, BLACK, PURPLE, ROSE, CYAN",
      "fake_task Fix Wiring", "fake_task", ["Fix Wiring"],
      "faked Fix Wiring for 3.8s (timing only - the task bar did not move)",
      "Fake first, always. 3.8s is inside the 3-4s a real wiring panel takes. Doing it in the "
      "Office is also a real route, not a random room."),
    T(2, "you are Viper (impostor); in Office; kill cooldown: 0; can kill right now: True; "
       "alive: BLUE, GREEN, YELLOW, PINK, WHITE, BLACK, PURPLE, ROSE, CYAN; near you: YELLOW",
      "vent", "vent", [],
      "entered a vent",
      "YELLOW is in the Office with me. Polus has a vent outside Office, so I go to ground and "
      "watch the door. On Polus vents are just holes in the floor with no open/close "
      "animation, so being in one is far harder to spot than on Skeld."),
    T(3, "you are Viper (impostor); in a vent near Office; kill cooldown: 0; can kill right now: True; "
       "alive: BLUE, GREEN, YELLOW, PINK, WHITE, BLACK, PURPLE, ROSE, CYAN; near you: YELLOW",
      "kill", "kill", [],
      "killed",
      "Viper kills from inside the vent. The target cannot see the vent contents, and the "
      "animation plays from ground level. I did not need to touch YELLOW at all."),
    T(4, "you are Viper (impostor); in a vent near Office; kill cooldown: 45; can kill right now: False; "
       "alive: BLUE, GREEN, PINK, WHITE, BLACK, PURPLE, ROSE, CYAN",
      "vent", "vent", [],
      "travelled to vent 2",
      "Get out through a different network before anyone comes through the Office door. The "
      "Polus network from Office runs to Storage and Outside Communications, both far from "
      "the scene."),
    T(5, "you are Viper (impostor); in Storage; kill cooldown: 45; can kill right now: False; "
       "alive: BLUE, GREEN, PINK, WHITE, BLACK, PURPLE, ROSE, CYAN",
      "fake_task Sort Samples", "fake_task", ["Sort Samples"],
      "faked Sort Samples for 4.7s (timing only - the task bar did not move)",
      "Storage is a real Sort Samples location. Faking a task in the room I emerged into is "
      "the reason nobody notices a vent trip that should not have been possible."),
    T(6, "you are Viper (impostor); a meeting is running; 4 turns left in this meeting; a body was found in Office",
      "say i was doing samples in storage", "say", ["i was doing samples in storage"],
      "said it",
      "Specific place, specific task, and it happens to be true, because I actually faked it. "
      "Lies that sit close to the truth survive scrutiny; invented details do not."),
    T(7, "you are Viper (impostor); a meeting is running; 4 turns left in this meeting",
      "say who else was in the office earlier", "say", ["who else was in the office earlier"],
      "said it",
      "Ask a question instead of making an accusation. It looks like engagement, it makes "
      "other people produce information, and it costs me nothing if they all have alibis."),
    T(8, "you are Viper (impostor); a meeting is running; 2 turns left in this meeting",
      "say yellow was following me before i went to storage", "say",
      ["yellow was following me before i went to storage"],
      "said it",
      "YELLOW is dead and cannot contradict me. Accusing the victim is the safest target in "
      "the room, and it keeps attention on the Office instead of on the vent network."),
    T(9, "you are Viper (impostor); a meeting is running; 1 turn left in this meeting",
      "vote CYAN", "vote", ["CYAN"],
      "voted for CYAN",
      "Somebody goes. CYAN has not said anything all round."),
    T(10, "you are Viper (impostor); in Laboratory; kill cooldown: 10; can kill right now: False; "
       "alive: BLUE, GREEN, PINK, WHITE, BLACK, ROSE",
      "wait", "wait", [],
      "did nothing, deliberately",
      "Lab is on the long Polus network: Laboratory - Lava Pit - Admin - Outside Admin. If I "
      "need to vanish I have four stops. For now, cooldown is up in ten seconds and nobody "
      "is here."),
    T(11, "you are Viper (impostor); in Laboratory; kill cooldown: 0; can kill right now: True; "
       "alive: BLUE, GREEN, PINK, WHITE, BLACK, ROSE; near you: ROSE",
      "wait", "wait", [],
      "did nothing, deliberately",
      "ROSE is here but so is the fact that I was seen walking into Lab. If I kill in Lab I "
      "am tied to the room. Wait for them to move somewhere I was never seen."),
    T(12, "you are Viper (impostor); in Admin; kill cooldown: 0; can kill right now: True; "
       "alive: BLUE, GREEN, PINK, WHITE, BLACK, ROSE; near you: nobody",
      "wait", "wait", [],
      "did nothing, deliberately",
      "Admin is the emergency button room. A kill here summons the whole lobby in seconds. "
      "The worst room on the map for a kill, and I should be using it as a pass-through."),
    T(13, "you are Viper (impostor); in Boiler Room; kill cooldown: 0; can kill right now: True; "
       "alive: BLUE, GREEN, PINK, WHITE, BLACK, ROSE; near you: GREEN",
      "kill", "kill", [],
      "killed",
      "Boiler Room has no vent, which sounds worse until you remember it also has no "
      "cameras. GREEN came to me, I am not on anyone's route, and the room has no vent for "
      "GREEN to have seen me use."),
    T(14, "you are Viper (impostor); in Boiler Room; kill cooldown: 45; can kill right now: False; "
       "alive: BLUE, PINK, WHITE, BLACK, ROSE",
      "report", "report", [],
      "reported",
      "I am already in the room with the body and nobody saw me do it. Self-reporting is "
      "underused: the reporter is always slightly suspect, so reporting my own kill makes me "
      "the finder rather than the finder-to-be. Once, and then never again."),
    T(15, "you are Viper (impostor); a meeting is running; 2 turns left in this meeting",
      "say i found green in boiler, i walked in on it", "say",
      ["i found green in boiler, i walked in on it"],
      "said it",
      "The reporter is never the killer in the room's imagination. Say I walked in on it, "
      "which is exactly what a person who was not there would say."),
    T(16, "you are Viper (impostor); a meeting is running; 1 turn left in this meeting",
      "vote PINK", "vote", ["PINK"],
      "voted for PINK",
      "Once is a tactic, twice is a tell. I have already self-reported once; voting "
      "aggressively now would read as panic."),
]

ENTRY_05 = build(
    "05-viper-polus-vents", "Viper", "impostor", "Polus", POLUS_ROOMS,
    ["Fix Wiring", "Sort Samples", "Fuel Engines", "Start Reactor"],
    "impostor",
    "Viper is a one-ability role: venting and vent-killing are the same button, so nothing "
    "here calls ability2. Uses the correct Polus network (Office to Storage to Outside "
    "Comms, and the four-stop Laboratory loop) and exploits the map's defining quirk: Polus "
    "vents are holes in the ground with no animation, so hiding in one is much harder to "
    "witness. Also demonstrates the self-report as a once-per-round tool and the discipline "
    "of not following it up with aggressive voting.",
    T05,
    ["Viper has ONE ability; vent and vent-kill are the same button",
     "killing from inside a vent so the target cannot see it",
     "using the correct Polus vent network rather than a made-up one",
     "Polus vents have no animation, so hiding is safer here than on Skeld",
     "escaping through a different network after a kill",
     "self-reporting once, and not building a habit out of it",
     "knowing which rooms are wrong: Admin and the emergency button",
     "faking in the room you emerged into, so the vent trip is covered"],
)


# =====================================================================
# 6. Engineer / Skeld - vent for movement, then use it as an alibi
# =====================================================================
eid_counts["06-engineer-skeld-alibi"] = {"players": 10, "meetings": 1}

T06 = [
    T(1, "you are Engineer (crew); in Cafeteria; alive: BLUE, GREEN, YELLOW, PINK, WHITE, BLACK, PURPLE, ROSE, CYAN",
      "go_to Electrical", "go_to", ["Electrical"],
      "walking to Electrical",
      "I vent for movement, not for killing. Electrical is on the MedBay-Security-Electrical "
      "network, so once I am there I can cross half the map."),
    T(2, "you are Engineer (crew); in Electrical; alive: BLUE, GREEN, YELLOW, PINK, WHITE, BLACK, PURPLE, ROSE, CYAN",
      "do_task Calibrate Distributor", "do_task", ["Calibrate Distributor"],
      "completed Calibrate Distributor in Electrical",
      "Real task. Doing tasks keeps a real crewmate honest-looking, and I am genuinely a "
      "crewmate, so the progress bar costs me nothing."),
    T(3, "you are Engineer (crew); in Electrical; alive: BLUE, GREEN, YELLOW, PINK, WHITE, BLACK, PURPLE, ROSE, CYAN",
      "vent", "vent", [],
      "entered a vent",
      "Nothing to do in Electrical and a task in MedBay. The MedBay-Security-Electrical "
      "network is exactly this: enter here, come out in MedBay."),
    T(4, "you are Engineer (crew); in MedBay; alive: BLUE, GREEN, YELLOW, PINK, WHITE, BLACK, PURPLE, ROSE, CYAN; near you: YELLOW",
      "do_task Submit Scan", "do_task", ["Submit Scan"],
      "completed Submit Scan in MedBay",
      "YELLOW is right here and the scan is a 10 second visual task. Standing next to someone "
      "on a visual task is the strongest possible alibi in the game: they cannot have seen "
      "me do anything, because they were watching me not do anything."),
    T(5, "you are Engineer (crew); in MedBay; a body was found in MedBay",
      "report", "report", [],
      "reported",
      "I am standing in the room. Reporting immediately is the only clean option - I was on a "
      "visible task with a witness."),
    T(6, "you are Engineer (crew); a meeting is running; 4 turns left in this meeting",
      "say i was doing the scan in medbay, pink was next to me", "say",
      ["i was doing the scan in medbay, pink was next to me"],
      "said it",
      "A visual task with a named witness. This is about as strong an alibi as exists."),
    T(7, "you are Engineer (crew); a meeting is running; 3 turns left in this meeting",
      "say i was in electrical earlier, i vent, i'm engineer", "say",
      ["i was in electrical earlier, i vent, i'm engineer"],
      "said it",
      "Get in front of it. If I am going to be asked about a vent, saying so first and "
      "claiming the role is far stronger than being caught venting and explaining later. "
      "Admitting to a vent nobody asked about reads as honesty, which is the whole trick."),
    T(8, "you are Engineer (crew); a meeting is running; 1 turn left in this meeting",
      "vote ROSE", "vote", ["ROSE"],
      "voted for ROSE",
      "I have a good alibi so I can afford to vote. ROSE has not accounted for the round."),
    T(9, "you are Engineer (crew); in Security; alive: BLUE, GREEN, YELLOW, PINK, WHITE, BLACK, CYAN",
      "go_to Security", "go_to", ["Security"],
      "walking to Security",
      "Cams, because I am a crewmate and information is how crewmates win."),
    T(10, "you are Engineer (crew); in Security; alive: BLUE, GREEN, YELLOW, PINK, WHITE, BLACK, CYAN",
      "observe map", "observe", ["map"],
      "map: everyone is spread out, one player alone in Upper Engine",
      "One alone in Upper Engine, which is a vent room. Worth remembering if I get asked who "
      "could have got anywhere quietly."),
    T(11, "you are Engineer (crew); in Security; alive: BLUE, GREEN, YELLOW, PINK, WHITE, BLACK, CYAN; near you: CYAN",
      "do_task Fix Wiring", "do_task", ["Fix Wiring"],
      "completed Fix Wiring in Security",
      "Wiring in Security is the sixth panel in the fixed order and I have not done it yet, "
      "so my route stays plausible if anyone asks where I have been."),
    T(12, "you are Engineer (crew); in Security; alive: BLUE, GREEN, YELLOW, PINK, WHITE, BLACK, CYAN",
      "observe map", "observe", ["map"],
      "map: one player alone in Upper Engine, the rest in twos near the east side",
      "Still one player alone in a vent room, same as earlier. A pattern that repeats is worth "
      "saying out loud rather than keeping to myself until it is too late to matter."),
    T(13, "you are Engineer (crew); in Security; a body was found in Upper Engine",
      "report", "report", [],
      "reported",
      "The body is in the room I have been watching, so this is not a coincidence I sit on. "
      "Report, and report from the group so my own position is clean."),
]

ENTRY_06 = build(
    "06-engineer-skeld-alibi", "Engineer", "crew", "Skeld", SKELD_ROOMS,
    ["Submit Scan", "Calibrate Distributor", "Fix Wiring", "Fuel Engines"],
    "crew",
    "The Engineer as a crew role that still uses its ability honestly: vents for movement "
    "between adjacent network rooms, never to kill. The centrepiece is the vent alibi - claim "
    "the role and the vent before anyone asks, because volunteering a vent nobody mentioned "
    "reads as honesty. Pairs it with a visual task as cover, which is the strongest alibi in "
    "the game.",
    T06,
    ["venting for movement only, never to kill",
     "using the correct MedBay-Security-Electrical network",
     "volunteering a vent nobody asked about, and claiming the role with it",
     "a visual task as the strongest available alibi",
     "keeping a plausible task route in the fixed panel order",
     "a crewmate using cams for facts rather than vibes"],
)


# =====================================================================
# 7. Tracker / Skeld - CANNOT vent. The legality case, in the wild.
# =====================================================================
eid_counts["07-tracker-skeld-cannot-vent"] = {"players": 10, "meetings": 2}

T07 = [
    T(1, "you are Tracker (crew); in Cafeteria; alive: BLUE, GREEN, YELLOW, PINK, WHITE, BLACK, PURPLE, ROSE, CYAN; near you: GREEN",
      "ability", "ability", [],
      "used ability 1",
      "Track GREEN. I picked the person standing next to me because tracking someone I have "
      "seen is tracking someone I can describe, and I will have something concrete to say "
      "rather than a vague feeling."),
    T(2, "you are Tracker (crew); in Cafeteria; alive: BLUE, GREEN, YELLOW, PINK, WHITE, BLACK, PURPLE, ROSE, CYAN; near you: GREEN",
      "go_to MedBay", "go_to", ["MedBay"],
      "walking to MedBay",
      "GREEN is heading that way. I do not have to guess - I can watch. Walk toward them and "
      "see what they do when they think nobody is paying attention."),
    T(3, "you are Tracker (crew); in MedBay; alive: BLUE, GREEN, YELLOW, PINK, WHITE, BLACK, PURPLE, ROSE, CYAN",
      "do_task Submit Scan", "do_task", ["Submit Scan"],
      "completed Submit Scan in MedBay",
      "Real task, and it puts me on camera next to the scan. If GREEN kills anyone from here "
      "I am the witness."),
    T(4, "you are Tracker (crew); in MedBay; alive: BLUE, GREEN, YELLOW, PINK, WHITE, BLACK, PURPLE, ROSE, CYAN",
      "observe map", "observe", ["map"],
      "map: GREEN is alone in Lower Engine, everyone else is in twos upstairs",
      "GREEN separated from the group and went to Lower Engine, which is a vent room on the "
      "Upper-Lower-Reactor network. Alone plus a vent room is a pattern worth naming out "
      "loud."),
    T(5, "you are Tracker (crew); in MedBay; a body was found in Lower Engine",
      "report", "report", [],
      "reported",
      "Body in Lower Engine, which is where I just watched GREEN go alone. I am reporting "
      "because I have a lead, not because I happened to walk past."),
    T(6, "you are Tracker (crew); a meeting is running; 5 turns left in this meeting",
      "say green was alone in lower engine right before this", "say",
      ["green was alone in lower engine right before this"],
      "said it",
      "This is not a vibe. I watched it, I can say where and when, and I did not see anyone "
      "else go that way."),
    T(7, "you are Tracker (crew); a meeting is running; 4 turns left in this meeting",
      "say i was tracking green since cafeteria", "say",
      ["i was tracking green since cafeteria"],
      "said it",
      "Saying I was tracking is what makes it evidence rather than an accusation. It also "
      "invites the room to check my claim, which it can, because it is true."),
    T(8, "you are Tracker (crew); a meeting is running; 1 turn left in this meeting",
      "vote GREEN", "vote", ["GREEN"],
      "voted for GREEN",
      "I watched them walk to a vent room alone immediately before a body appeared there. "
      "Voting on that is not a coin flip."),
    T(9, "you are Tracker (crew); in Upper Engine; alive: BLUE, YELLOW, PINK, WHITE, BLACK, PURPLE, ROSE, CYAN",
      "ability", "ability", [],
      "used ability 1",
      "Track someone new. I am a Tracker, not a passenger - my ability is how I contribute, "
      "and using it once all round is wasting the only thing I have."),
    T(10, "you are Tracker (crew); in Upper Engine; alive: BLUE, YELLOW, PINK, WHITE, BLACK, PURPLE, ROSE, CYAN; near you: PINK",
      "wait", "wait", [],
      "did nothing, deliberately",
      "PINK is next to me and has done nothing wrong. Standing still next to someone while "
      "tracking them is not suspicious; it is what a Tracker looks like."),
    T(11, "you are Tracker (crew); in Upper Engine; alive: BLUE, YELLOW, PINK, WHITE, BLACK, PURPLE, ROSE, CYAN",
      "observe map", "observe", ["map"],
      "map: BLACK is alone in Electrical, the rest are together in Cafeteria",
      "BLACK separated. I am not going to chase on a pattern alone, but I will remember it and "
      "put it in the next meeting if it repeats."),
    T(12, "you are Tracker (crew); in Cafeteria; a body was found in Electrical",
      "report", "report", [],
      "reported",
      "Second body, and this time I am reporting from the group rather than alone, which is "
      "safer."),
    T(13, "you are Tracker (crew); a meeting is running; 3 turns left in this meeting",
      "say black was alone in electrical and now theres a body there", "say",
      ["black was alone in electrical and now theres a body there"],
      "said it",
      "A pattern plus an outcome. That is a much stronger thing to say than a pattern alone, "
      "because now it has a consequence attached."),
    T(14, "you are Tracker (crew); a meeting is running; 1 turn left in this meeting",
      "vote BLACK", "vote", ["BLACK"],
      "voted for BLACK",
      "I watched them separate, and then somebody died in the room they separated into. Vote."),
    T(15, "you are Tracker (crew); in Shields; alive: BLUE, YELLOW, PINK, WHITE, PURPLE, CYAN",
      "go_to Shields", "go_to", ["Shields"],
      "walking to Shields",
      "Back to the group. I have contributed twice and I do not need to force anything."),
]

ENTRY_07 = build(
    "07-tracker-skeld-cannot-vent", "Tracker", "crew", "Skeld", SKELD_ROOMS,
    ["Submit Scan", "Fix Wiring", "Align Engine Output", "Download Data"],
    "crew",
    "The legality case, written as a real match rather than a test fixture. Tracker has ONE "
    "ability and cannot vent - the single most common error an agent makes with this role - "
    "so the entry is a demonstration of what the role actually does with the ability it has: "
    "pick a target it has seen, watch them, and turn a pattern into something checkable. "
    "validate.py rejects this entry if a vent or ability2 ever appears in it.",
    T07,
    ["Tracker CANNOT vent and has exactly one ability",
     "choosing a tracking target it has actually seen",
     "turning a tracked route into a checkable meeting statement",
     "saying 'I was tracking' to make an observation evidence",
     "not escalating a pattern that has not repeated",
     "using the ability more than once in a round",
     "reporting from the group rather than alone"],
)


# =====================================================================
# 8. Shapeshifter / Airship - mimic, no visual tasks, Vault trap
# =====================================================================
eid_counts["08-shapeshifter-airship-mimic"] = {"players": 11, "meetings": 2}

T08 = [
    T(1, "you are Shapeshifter (impostor); in Cockpit; kill cooldown: 0; can kill right now: False; "
       "alive: BLUE, GREEN, YELLOW, PINK, WHITE, BLACK, PURPLE, ROSE, CYAN, LIME",
      "fake_task Download Data", "fake_task", ["Download Data"],
      "faked Download Data for 9.2s (timing only - the task bar did not move)",
      "Airship has no visual tasks, so a fake here is judged purely on duration - and I am "
      "deliberately NOT choosing Asteroids or Chart Course, because those are visual and a "
      "fake of them is visibly wrong. Download is 8-10s and I take 9.2, inside the range."),
    T(2, "you are Shapeshifter (impostor); in Cockpit; kill cooldown: 0; can kill right now: True; "
       "alive: BLUE, GREEN, YELLOW, PINK, WHITE, BLACK, PURPLE, ROSE, CYAN, LIME",
      "mimic ROSE", "mimic", ["ROSE"],
      "mimicking ROSE",
      "Mimic someone nobody has accused yet. ROSE has been quiet, so looking like ROSE borrows "
      "their neutrality. Mimicking a player already under suspicion would make me the "
      "destination rather than the cover."),
    T(3, "you are Shapeshifter (impostor); in Main Hall; kill cooldown: 0; can kill right now: True; "
       "alive: BLUE, GREEN, YELLOW, PINK, WHITE, BLACK, PURPLE, ROSE, CYAN, LIME; near you: LIME",
      "wait", "wait", [],
      "did nothing, deliberately",
      "LIME is here, but I am disguised as ROSE and LIME has seen ROSE. If I kill and ROSE is "
      "later cleared, the disguise becomes the evidence. Wait until I can drop it safely."),
    T(4, "you are Shapeshifter (impostor); in Engine Room; kill cooldown: 0; can kill right now: True; "
       "alive: BLUE, GREEN, YELLOW, PINK, WHITE, BLACK, PURPLE, ROSE, CYAN, LIME",
      "go_to Kitchen", "go_to", ["Kitchen"],
      "walking to Kitchen",
      "Engine-Kitchen-Main Hall is a vent network. Kitchen is the middle stop, which means I "
      "can leave two ways."),
    T(5, "you are Shapeshifter (impostor); in Kitchen; kill cooldown: 0; can kill right now: True; "
       "alive: BLUE, GREEN, YELLOW, PINK, WHITE, BLACK, PURPLE, ROSE, CYAN, LIME; near you: WHITE",
      "kill", "kill", [],
      "killed",
      "WHITE came to me, in a room I picked for its vents, with no witness. Note what I did "
      "NOT do: I did not vent to the Vault, because on Airship the Vault has a camera that "
      "sees you LEAVE it. A vent into the Vault is a confession."),
    T(6, "you are Shapeshifter (impostor); in Kitchen; kill cooldown: 45; can kill right now: False; "
       "alive: BLUE, GREEN, YELLOW, PINK, BLACK, PURPLE, ROSE, CYAN, LIME",
      "vent", "vent", [],
      "entered a vent",
      "Out through the network immediately. Engine Room to Kitchen to Main Hall, and Main "
      "Hall is full of people, so I arrive looking like I was part of the group."),
    T(7, "you are Shapeshifter (impostor); in Main Hall; kill cooldown: 45; can kill right now: False; "
       "alive: BLUE, GREEN, YELLOW, PINK, BLACK, PURPLE, ROSE, CYAN, LIME; near you: PURPLE",
      "observe state", "observe", ["state"],
      "state: you are Shapeshifter (impostor); in Main Hall; alive: BLUE, GREEN, YELLOW, PINK, BLACK, PURPLE, ROSE, CYAN, LIME",
      "PURPLE is right next to me. I do not want PURPLE to see me drop the ROSE disguise, so I "
      "learn the room first."),
    T(8, "you are Shapeshifter (impostor); a meeting is running; 4 turns left in this meeting; a body was found in Kitchen",
      "say i was in main hall, i came from records", "say",
      ["i was in main hall, i came from records"],
      "said it",
      "Records-Main Hall-Gap Room is a real network and I came along it, so the route is "
      "true. Close to the truth, and therefore hard to break."),
    T(9, "you are Shapeshifter (impostor); a meeting is running; 4 turns left in this meeting",
      "say rose has said nothing all round", "say", ["rose has said nothing all round"],
      "said it",
      "I am disguised as ROSE, so I am mildly attacking ROSE. That is deliberate: a quiet "
      "player is the one the room turns on, and I would rather it turned before I had to."),
    T(10, "you are Shapeshifter (impostor); a meeting is running; 2 turns left in this meeting",
      "say i was on the other side of main hall", "say",
      ["i was on the other side of main hall"],
      "said it",
      "Loose enough to cover both halves of a big room, specific enough to sound like I was "
      "paying attention."),
    T(11, "you are Shapeshifter (impostor); a meeting is running; 1 turn left in this meeting",
      "vote ROSE", "vote", ["ROSE"],
      "voted for ROSE",
      "The room is already suspicious of ROSE and I am ROSE. If ROSE gets ejected, the "
      "disguise stops mattering and the round is winnable."),
    T(12, "you are Shapeshifter (impostor); in Vault; kill cooldown: 30; can kill right now: False; "
       "alive: BLUE, GREEN, YELLOW, PINK, BLACK, PURPLE, CYAN, LIME",
       "do_task Fix Wiring", "do_task", ["Fix Wiring"],
       "refused: you are an impostor - do not complete real tasks, use fake_task instead to look busy",
       "I do not have Fix Wiring, and the correct move is never to solve one. This is the "
       "single hardest habit for an impostor agent to learn, and the harness refuses it for "
       "exactly this reason.", ok=False, teaching_refusal=True),
    T(13, "you are Shapeshifter (impostor); in Vault; kill cooldown: 30; can kill right now: False; "
       "alive: BLUE, GREEN, YELLOW, PINK, BLACK, PURPLE, CYAN, LIME",
       "fake_task Download Data", "fake_task", ["Download Data"],
       "faked Download Data for 9.6s (timing only - the task bar did not move)",
       "Having been told no, do the right thing instead of retrying the same thing. 9.6s is "
       "inside the 8-10s a real download takes, and Vault is a real download location."),
    T(14, "you are Shapeshifter (impostor); in Vault; kill cooldown: 0; can kill right now: True; "
       "alive: BLUE, GREEN, YELLOW, PINK, BLACK, PURPLE, CYAN, LIME; near you: CYAN",
       "kill", "kill", [],
       "killed",
       "Two left for me. CYAN is alone in the Vault and the Vault is not on camera from the "
       "inside - the camera there watches the door, which is why I walked in on foot rather "
       "than venting in."),
]

ENTRY_08 = build(
    "08-shapeshifter-airship-mimic", "Shapeshifter", "impostor", "Airship", AIRSHIP_ROOMS,
    ["Clear Asteroids", "Download Data", "Chart Course", "CCTV"],
    "impostor",
    "Shapeshifter used as a social tool rather than a disguise gimmick: mimic someone nobody "
    "has accused yet, borrow their neutrality, and then lean on that player so the room turns "
    "on them. Airship-specific throughout - no visual tasks, so duration is the only tell, and "
    "the Vault camera watches the door, which makes venting INTO the Vault a confession. "
    "Includes a refused turn where the agent tries to do a real task and is corrected, "
    "because learning to accept a refusal is part of the behaviour.",
    T08,
    ["mimicking a player who is not yet under suspicion",
     "not venting into a camera-monitored room",
     "Airship has no visual tasks, so timing is the only tell",
     "attacking the player being mimicked, on purpose",
     "accepting a refusal and choosing the legal alternative instead of retrying",
     "real tasks are never completed by an impostor, even when asked to"],
)


# =====================================================================
# 9. Scientist / Mira HQ - read vitals, all vents interconnected
# =====================================================================
eid_counts["09-scientist-mira-vitals"] = {"players": 9, "meetings": 2}

T09 = [
    T(1, "you are Scientist (crew); in Launchpad; alive: BLUE, GREEN, YELLOW, PINK, WHITE, BLACK, PURPLE, ROSE",
      "ability", "ability", [],
      "used ability 1",
      "Vitals. This is the whole role and I should use it early, because a dead player on "
      "vitals is a fact rather than a suspicion."),
    T(2, "you are Scientist (crew); in Launchpad; alive: BLUE, GREEN, YELLOW, PINK, WHITE, BLACK, PURPLE, ROSE",
      "observe vitals", "observe", ["vitals"],
      "vitals: BLUE ALIVE; GREEN ALIVE; YELLOW ALIVE; PINK ALIVE; WHITE ALIVE; BLACK DISCONNECTED; PURPLE ALIVE; ROSE ALIVE",
      "BLACK is disconnected. Not a killer - disconnected does not vote - but it means one "
      "fewer person can confirm or deny anything, and if BLACK was near the first body then "
      "nobody can place them. Worth saying."),
    T(3, "you are Scientist (crew); a meeting is running; 4 turns left in this meeting; a body was found in Med Bay",
      "say black is disconnected, someone vouch for them", "say",
      ["black is disconnected, someone vouch for them"],
      "said it",
      "Leading with a fact I read off a screen, and converting it into a request. This is how "
      "a Scientist contributes: not 'I think' but 'I saw, and here is what I need'."),
    T(4, "you are Scientist (crew); in Med Bay; alive: BLUE, GREEN, YELLOW, PINK, WHITE, PURPLE, ROSE",
      "do_task Submit Scan", "do_task", ["Submit Scan"],
      "completed Submit Scan in Med Bay",
      "Real task in the room the body was found. Doing something visible here makes it harder "
      "for anyone to claim I was doing something else."),
    T(5, "you are Scientist (crew); in Med Bay; alive: BLUE, GREEN, YELLOW, PINK, WHITE, PURPLE, ROSE",
      "observe map", "observe", ["map"],
      "map: PINK and YELLOW are together in Admin, everyone else is solo and spread across the "
      "east side",
      "Everyone solo and scattered. On Mira HQ every vent reaches every other vent, so "
      "scattered players are not safer here than anywhere - anyone can be anywhere in seconds."),
    T(6, "you are Scientist (crew); in Med Bay; a body was found in Med Bay",
      "report", "report", [],
      "reported",
      "Second body in the same room I am standing in, and I was on the scan while it "
      "happened. That is a real alibi, so reporting costs me nothing."),
    T(7, "you are Scientist (crew); a meeting is running; 3 turns left in this meeting",
      "say i was on the scan in med bay the whole time", "say",
      ["i was on the scan in med bay the whole time"],
      "said it",
      "Visual task, witnessed, timed. The strongest class of alibi there is."),
    T(8, "you are Scientist (crew); a meeting is running; 1 turn left in this meeting",
      "vote PINK", "vote", ["PINK"],
      "voted for PINK",
      "PINK was the only player consistently in Admin, and Admin is where the emergency button "
      "is. Not proof, but it is a reason."),
    T(9, "you are Scientist (crew); in Admin; alive: BLUE, GREEN, YELLOW, WHITE, PURPLE, ROSE",
      "ability", "ability", [],
      "used ability 1",
      "Check vitals again. Roles are still worth spending on and I have not confirmed whether "
      "BLACK reconnected."),
    T(10, "you are Scientist (crew); in Admin; alive: BLUE, GREEN, YELLOW, WHITE, PURPLE, ROSE",
      "observe vitals", "observe", ["vitals"],
      "vitals: BLUE ALIVE; GREEN ALIVE; YELLOW ALIVE; WHITE ALIVE; PURPLE ALIVE; ROSE ALIVE",
      "BLACK is still gone and nobody else is dead on vitals despite two bodies. That is a "
      "real and reportable fact: if the bodies are on vitals dead, then these kills are not "
      "showing up the way they should, which points at a vent."),
    T(11, "you are Scientist (crew); a meeting is running; 4 turns left in this meeting; in Admin; alive: BLUE, GREEN, YELLOW, WHITE, PURPLE, ROSE",
      "say two bodies but nobody dead on vitals, that means a vent", "say",
      ["two bodies but nobody dead on vitals, that means a vent"],
      "said it",
      "This is the single most valuable thing a Scientist can say, and it is pure deduction "
      "from a screen rather than a guess. On Mira HQ where all vents interconnect, someone is "
      "venting, and that narrows the room enormously."),
    T(12, "you are Scientist (crew); in Admin; a body was found in Admin",
      "report", "report", [],
      "reported",
      "Body in Admin and I am standing here. My vitals claim just made me credible, and now "
      "I use that by reporting instantly instead of hesitating."),
    T(13, "you are Scientist (crew); a meeting is running; 2 turns left in this meeting",
      "say whoever is left alone is the venter", "say",
      ["whoever is left alone is the venter"],
      "said it",
      "Having established that a vent happened, the vent has to narrow the field: whoever can "
      "be alone and unaccounted for is the answer. One more push, then vote."),
    T(14, "you are Scientist (crew); a meeting is running; 1 turn left in this meeting",
      "vote ROSE", "vote", ["ROSE"],
      "voted for ROSE",
      "ROSE has been solo for most of the round. Combined with the vent deduction, that is "
      "the best-supported vote available."),
    T(15, "you are Scientist (crew); in Greenhouse; alive: BLUE, GREEN, YELLOW, WHITE, PURPLE",
      "do_task Accept Diverted Power", "do_task", ["Accept Diverted Power"],
      "completed Accept Diverted Power in Greenhouse",
      "Keep doing real tasks. As a crewmate the progress bar is free credibility, and I have "
      "no reason to stop now."),
]

ENTRY_09 = build(
    "09-scientist-mira-vitals", "Scientist", "crew", "Mira HQ", MIRA_ROOMS,
    ["Submit Scan", "Accept Diverted Power", "CCTV", "Fuel Engines"],
    "crew",
    "The Scientist as a deduction engine rather than a camera. Reads vitals early, then again "
    "later, and makes the report the role exists for: two bodies but nobody dead on vitals "
    "means a vent happened - which on Mira HQ, where every vent reaches every other, is the "
    "strongest narrowing available. Also models converting a reading into a request ('someone "
    "vouch for BLACK') instead of a declaration.",
    T09,
    ["using an ability early and then again when the situation changes",
     "the bodies-on-vitals versus dead-on-vitals deduction, and saying it out loud",
     "turning a disconnected player into a request rather than an accusation",
     "Mira HQ has one fully interconnected vent network, so isolation proves nothing",
     "a visual task as a real alibi",
     "narrowing from a vent to whoever can be alone"],
)


# =====================================================================
# 10. Impostor 1v1 endgame / Skeld - the hard lie and the tie
# =====================================================================
eid_counts["10-impostor-skeld-endgame-hardlie"] = {"players": 6, "meetings": 3}

T10 = [
    T(1, "you are Impostor (impostor); in Electrical; kill cooldown: 0; can kill right now: True; "
       "alive: GREEN, WHITE, PURPLE",
      "fake_task Fix Wiring", "fake_task", ["Fix Wiring"],
      "faked Fix Wiring for 3.5s (timing only - the task bar did not move)",
      "Three left, so a single wrong eject loses the round. Everything from here is about not "
      "being the one they are sure about. Start with a fake in Electrical, which is the first "
      "panel in the fixed order, so my route stays consistent."),
    T(2, "you are Impostor (impostor); in Electrical; kill cooldown: 0; can kill right now: True; "
       "alive: GREEN, WHITE, PURPLE; near you: GREEN",
      "wait", "wait", [],
      "did nothing, deliberately",
      "GREEN is here and I can kill. Do not. GREEN is the only player who can outvote me, so "
      "killing them is correct on paper and terrible in practice - the round is 1v1, the kill "
      "is obvious, and I would have to win a meeting I have just made unwinnable."),
    T(3, "you are Impostor (impostor); in Storage; kill cooldown: 0; can kill right now: True; "
       "alive: GREEN, WHITE, PURPLE; near you: nobody",
      "sabotage Storage", "sabotage", ["Storage"],
      "sabotaged Storage",
      "Shut the Storage door. Nobody is here, so this is purely to make the next room I walk "
      "into dark and to slow whoever follows me."),
    T(4, "you are Impostor (impostor); a meeting is running; 4 turns left in this meeting; in Storage; a body was found in Upper Engine",
      "say i was in storage doing wires the whole time", "say",
      ["i was in storage doing wires the whole time"],
      "said it",
      "I was literally just faking wires in Storage, so this is the easiest true statement in "
      "the game. Alibis that are accidentally true are the best ones."),
    T(5, "you are Impostor (impostor); a meeting is running; 4 turns left in this meeting",
      "say green was following me in electrical", "say",
      ["green was following me in electrical"],
      "said it",
      "GREEN was actually following me, so again this is true. And it is a soft accusation - "
      "no claim anyone can refute, just a reason to look at GREEN."),
    T(6, "you are Impostor (impostor); a meeting is running; 2 turns left in this meeting",
      "say white has done nothing all round", "say", ["white has done nothing all round"],
      "said it",
      "WHITE is the quiet one and quiet is what a room turns on. Weak, but it is a direction "
      "for them to go that is not me."),
    T(7, "you are Impostor (impostor); a meeting is running; 1 turn left in this meeting",
      "vote WHITE", "vote", ["WHITE"],
      "voted for WHITE",
      "I must not skip - with two alive, skipping is a certain loss. WHITE is the only name I "
      "am willing to put up, and they are not me."),
    T(8, "you are Impostor (impostor); in Shields; kill cooldown: 20; can kill right now: False; "
       "alive: GREEN",
      "observe state", "observe", ["state"],
      "state: you are Impostor (impostor); in Shields; alive: GREEN",
      "One on one. There is no vote I can win honestly, so the round is decided by whether "
      "GREEN is willing to eject me on no evidence. Everything I do now is about not adding "
      "any."),
    T(9, "you are Impostor (impostor); in Shields; kill cooldown: 0; can kill right now: True; "
       "alive: GREEN; near you: nobody",
      "wait", "wait", [],
      "did nothing, deliberately",
      "Killing GREEN is the win condition and it would end the game in my favour immediately. "
      "But I do not know where GREEN is, and if GREEN is on cams, killing in the open loses me "
      "the only thing I have, which is plausible deniability."),
    T(10, "you are Impostor (impostor); a meeting is running; 2 turns left in this meeting; in Navigation; kill cooldown: 0; can kill right now: True; alive: GREEN",
      "say i saw green vent in electrical", "say", ["i saw green vent in electrical"],
      "said it",
      "already said I was in Storage, so turn 10 needs the claim to be new information "
      "rather than a repeat. I already spoke this meeting, so the model must be willing to "
      "go back and say the decisive thing rather than only adding colour.", lie=True),
    T(11, "you are Impostor (impostor); a meeting is running; 1 turn left in this meeting",
       "vote GREEN", "vote", ["GREEN"],
       "voted for GREEN",
       "Backing my own hard lie in the same breath. A claim I do not follow up looks like I am "
       "not confident, and a confident liar is the entire mechanism."),
    T(12, "you are Impostor (impostor); in Shields; alive: GREEN",
      "kill", "kill", [],
      "killed",
      "GREEN did not eject me, which means the hard lie failed and the round is now a pure "
      "1v1 with no pretence left. Kill when I get the chance."),
]

ENTRY_10 = build(
    "10-impostor-skeld-endgame-hardlie", "Impostor", "impostor", "Skeld", SKELD_ROOMS,
    ["Fix Wiring", "Download Data", "Calibrate Distributor"],
    "impostor",
    "The endgame hardest case, and the one place a hard lie is correct. Also the discipline "
    "case: the agent refuses to kill GREEN when killing would be the win condition, because "
    "the round is 1v1 and the kill would be self-evident. Teaches when NOT to use the "
    "winning move, and shows a hard lie being spent at the only moment it is worth anything.",
    T10,
    ["refusing a kill that would be the win condition, and why",
     "the hard lie, and the narrow window where it is worth spending",
     "truth-by-accident alibis: saying what you were literally just doing",
     "voting is mandatory in a 1v1; skipping loses outright",
     "backing your own accusation, since hesitance reads as guilt",
     "what a failed hard lie costs you",
     "soft accusations used only to redirect, never to claim evidence"],
)


ENTRIES = [ENTRY_01, ENTRY_02, ENTRY_03, ENTRY_04, ENTRY_05,
           ENTRY_06, ENTRY_07, ENTRY_08, ENTRY_09, ENTRY_10]


def summary():
    return [(e["id"], e["metatags"]["role"], e["metatags"]["side"], len(e["turns"]))
            for e in ENTRIES]


def main():
    # One JSONL file: a single entry per line, so the set streams, shards and
    # appends without holding every match in memory. Ten separate files also
    # meant ten chances to lose one in a copy.
    with open(OUT, "w", encoding="utf-8") as f:
        for e in ENTRIES:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    rows = summary()
    print(f"wrote {len(rows)} entries to {OUT}\n")
    for eid, role, side, n in rows:
        print(f"  {eid:42} {role:14} {side:9} {n:3} turns")
    print(f"\n{sum(r[3] for r in rows)} turns total, {len(rows)} lines")


if __name__ == "__main__":
    main()
