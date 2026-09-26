# Architecture: the model plays, the harness executes

## The rule

The model decides **what** happens. The harness does **how**.

The harness is not allowed to choose a game action on its own. No autonomous
kill, no autonomous vent, no autonomous sabotage, no autonomous task, no
autonomous "go to Electrical because the kill cooldown is ready".

This is the same split as Claude Code: the model is not there to talk, it is
there to do work, and the harness is the tool surface it drives. If the harness
decides on its own that a kill is a good idea, the model is just a chat
decorator and nothing has been fixed.

## Why

Before this was written down, `roleplay.role_turn()` ran every tick and each
role's function acted on its own: `guardian_angel_turn` protected someone,
`shapeshifter_turn` picked a mimic target, `vent_turn` entered and left vents,
`maybe_do_sabotage` decided whether to sabotage, `kill_nearest` killed. The
model was only consulted for chat and for a single sabotage choice. That is a
state machine wearing a language model as a hat.

## Layering

```
model          decides the next action, in words
  |
harness        parses that decision into one of a fixed set of actions
  |            (agent.py: ACTIONS, one entry per legal verb)
game API       plugin executes it (botCmd.txt -> real game methods)
```

The harness may:

- enumerate what is currently possible
- validate that the requested action is legal right now
- execute exactly one action
- report the result back

The harness may **not**:

- pick an action the model did not ask for
- substitute its own preference for the model's choice
- "helpfully" chain a second action (vent, then kill) on its own

## The action set

Every action the model can request is listed in `agent.ACTIONS`. Anything not
in that table cannot be done. This is deliberate: a closed set is what makes it
possible to tell whether the model is confused.

Actions, grouped:

- **movement** - go to a named room, follow a player, stop
- **combat** - kill, report, fake/knock
- **sabotage** - sabotage a named system
- **abilities** - use ability 1, use ability 2 (only if the role has a 2nd)
- **tasks** - do a task, do tasks in a room
- **social** - say something, vote
- **observe** - read the map, read the tracker, read the vitals, read notes

## Abilities: two is the maximum

Verified against the IL2CPP dump by listing every class that overrides
`UseSecondaryAbility`. Only two do:

- **Detective** - 1) interrogate a player or inspect a body, 2) read the notebook
- **Phantom** - 1) turn invisible, 2) leave a decoy of yourself

Every other role has exactly one ability button. Crewmate and Impostor have
none. No role has more than two.

The plugin publishes the live count of visible ability buttons in
`abilityData.txt` as `abilitycount`, and that overrides the static table in
`roleplay.ROLE_ABILITIES`. The model is therefore told the truth from the game
itself, not from a table that could drift when the game updates.

If a role is told it has an ability it does not have, the model will try to use
it, fail, and either retry forever or fall back to guessing. That is the exact
confusion this table exists to prevent.

## Known conflicts

These are real and unresolved. Recorded so they are not rediscovered later.

1. **The model cannot be called every tick.** A local `gemma4:e2b` round trip
   takes hundreds of milliseconds to seconds. The game runs at 60fps. So the
   loop cannot be "ask the model 60 times a second".
   *Current resolution:* the model is asked once per decision point - a
   meaningful state change (meeting starts, kill becomes available, a role
   ability becomes usable, a task completes) - not per frame. Continuous things
   like walking are executed by the harness to a destination the model picked.
   *Unresolved:* whether a small model can hold a coherent plan across a whole
   round, or whether it needs re-asking every few seconds.

2. **A small model will drift and forget the action set.** Asked to "do
   something useful" it will invent verbs. Prompting cannot fully prevent this.
   *Current resolution:* strict parsing, unmatched replies produce no action at
   all, and the last N decisions are fed back so it can see its own history.
   *Unresolved:* whether a local e2b model is strong enough to stay in the
   action set for a full round without drift.

3. **Realtime reactions conflict with model latency.** A player walks up behind
   the bot. A human kills instantly. The model needs ~1s to decide. By the time
   it answers, the moment has passed.
   *Current resolution:* none. This is a genuine design tension, not a bug.
   *Options:* (a) accept the delay and be stealthy-but-slow, (b) let the
   harness auto-kill on a hard proximity trigger and tell the model afterwards,
   which violates the rule above and needs an explicit decision, (c) a faster
   model.

4. **Tasks are mechanical, the model is not.** Dooming a task requires pixel
   work in a minigame. A model cannot usefully direct pixel-level dragging, and
   asking it to would burn enormous context for no gain.
   *Current resolution:* the model chooses *which* task and *when*; the harness
   solves it. This is the clearest case of the division of labour working.

5. **Two abilities need two buttons, and the harness must not mix them up.**
   Detective's primary and secondary are genuinely different verbs (interrogate
   vs read), not one verb twice.
   *Current resolution:* separate entry points, `detective_interrogate()` and
   `detective_notes()`, and `abilitycount` gates the second.

6. **"Do nothing" must be expressible.** If the model can only ever be asked to
   act, a timid model that correctly judges "no action is safe right now" has
   no way to say so, and the harness will fill the silence with something.
   *Current resolution:* `no action` is a first-class answer.

## What "not a state machine" rules out, concretely

- `main.py` calling `role_turn()` on a timer and letting it act
- `utility.should_I_kill()` deciding a kill and then killing
- `roleplay.decide_sabotage()` being consulted only sometimes while
  `maybe_do_sabotage` fires whenever it feels like it

These currently still exist and are the remaining work.
