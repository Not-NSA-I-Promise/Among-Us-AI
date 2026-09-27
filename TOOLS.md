# The model's tools

The complete set of actions the model can take. This is `agent.ACTIONS`, and it
is the whole API — nothing outside this table is reachable, no matter what the
model says. If a behaviour is not in here, the bot cannot do it.

Source of truth: `agent.py`. If this document and the code disagree, the code is
right and this file is a bug.

## The table

| Action | Argument | What it does |
|---|---|---|
| `go_to` | room | Walk to a named room |
| `stop` | — | Stop walking |
| `vent` | — | Enter a vent, or travel to a connected one if already inside |
| `do_task` | task | Walk to a task and actually complete it |
| `fake_task` | task | Pretend to do a task, standing there for the real duration |
| `kill` | — | Kill the nearest player in range |
| `report` | — | Report the body you are standing at |
| `sabotage` | name | Trigger lights, comms, o2, reactor, or a named door |
| `queue_sabotage` | name | Note a sabotage to consider later |
| `ability` | — | Role's first ability |
| `ability2` | — | Role's second ability, if it has one |
| `protect` | color | Guardian Angel: shield a player |
| `mimic` | color | Shapeshifter: appear as a player |
| `interrogate` | — | Detective: inspect the player or body next to you |
| `notes` | — | Detective: read the notebook |
| `overrule` | player_id | Judge: spend the extra vote |
| `say` | message | Speak in chat or at a meeting |
| `vote` | color or `skip` | Vote at a meeting |
| `observe` | what | Read state, map, vitals, tracker, notes, memory or witnesses |
| `wait` | — | Deliberately do nothing this turn. **On a 3 minute cooldown**: after using it, the action is removed from the model's tool list and replying with the word is refused |

19 or 20 actions are offered at any moment — `wait` is the only one that can be
withheld, and it is withheld whenever its cooldown is running. That is deliberate:
`wait` is the one action that always looks available and always looks harmless, so
it wins whenever the model is unsure. Prompting the model not to spam it did not
work, because it was reaching for `wait` long before any limit fired.

## Restrictions the harness enforces

These are refusals, not preferences. The model is told and then the game or the
harness says no.

| Action | Refused when |
|---|---|
| `kill` | you are dead, or you are not an impostor, or the kill misses |
| `do_task` | **you are an impostor** — real task progress is proof of innocence |
| `fake_task` | the task is visual on this map at this stage (Submit Scan, Clear Asteroids, Prime Shields, Skeld Empty Garbage/Chute at the Storage stage) and `allow_visual` was not set |
| `vent` | `canvent` is not set, or you are dead, or no travel options exist |
| `ability` | no ability button on screen, or you are dead |
| `ability2` | your role has fewer than 2 abilities |
| `protect` / `mimic` | no player of that colour exists |
| `overrule` | no overrule available, already used, or task-blocked |
| `sabotage` | the game has no such map entry, or declines |
| `go_to` | no room by that name — and the refusal lists the real rooms |

`do_task` refusing for impostors is deliberate and was added because the model
was being asked to solve Start Reactor while trying to kill people. An
impostor's task list is a cover story.

## What the model is told before it chooses

- its role, and exactly how many abilities it has (1, or 2 for Detective and
  Phantom; 0 for Crewmate and Impostor)
- "No role in this game has more than 2 abilities"
- the room names for the current map
- its outstanding tasks — or, for an impostor, that they are a cover story and
  `fake_task` is the tool for them
- its position, room, who is alive, who is near it
- for an impostor: the kill cooldown and whether a kill is available right now
- during a meeting: roughly how many turns are left, so it can budget speaking
  against voting
- its last few decisions and their outcomes

## The model does not get

- pixel coordinates of anything
- direct input access — it cannot click, it can only name an action
- the ability to act twice in one turn
- any way to bypass a refusal

## How a reply becomes an action

1. `agent.parse_action` takes the first line, strips `action:` / `` ` `` / quotes.
2. If it is a literal action name with enough arguments, that is used.
3. Otherwise `agent.PHRASES` tries to read it as English — "head to the Reactor",
   "use my secondary ability", "shield the red", "eject BLUE", "go do the Swipe
   Card task". This maps onto the existing actions; it does not add any.
4. If neither works, **no action is taken** and the reply is reported as
   unparseable. A confused model does not get to improvise.

Verified by `tests/test_agent_parse.py`: 33 phrasings parse to the correct action
*and argument*, 7 invented verbs are rejected.

## Adding a tool

Add an entry to `agent.ACTIONS` with `(args, handler, description)`. The
description is what the model reads, so write it for the model. Then:

- add the phrase patterns to `PHRASES` if a person would say it differently
- add cases to `tests/test_agent_parse.py`, including a wrong-argument case
- update the table above

Do not add an action the harness would take on its own initiative. The whole
point is that nothing happens unless the model asked for it.
