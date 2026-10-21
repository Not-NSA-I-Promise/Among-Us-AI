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

## Task panel convention: the harness opens it, the solver drives it

**The harness opens the panel. The solver drives what is on it.**

This is not a style preference, it was a live bug. `do_task` walked to the
panel and pressed USE to open it, and then the solver's own `click_use()`
clicked the on-screen USE button a second time. With a minigame already open,
that second click **closes** it. So every solver was driving a closed panel:
Fix Wiring moved the cursor across the screen dragging wires that were not
there, and Inspect Sample clicked into empty space. From outside it looked
like the bot was clicking and nothing was happening, which is why both tasks
looped forever.

So:

- `do_task.walk_to_panel()` walks to the live route position and **stops there**.
- `do_task.open_panel_original_way()` opens the panel with a mouse click on the
  on-screen USE button, and **confirms it from `Minigame.Instance`** before
  handing over.
- The solver never calls `click_use()`.

Every solver that opens a panel must also **confirm it opened** before working
on it, and must say so when it did not. Dragging wires or clicking tubes on an
unopened panel is indistinguishable, from the harness's point of view, from
doing the task correctly, so the solver has to check. `Fix Wiring` looks for a
wire endpoint; `Inspect Sample` reads the panel's published state.

Note that `click_use()` is a *mouse click on the on-screen USE button*, while
`roleplay.press_use()` is the *gamepad A button*. They are not the same thing,
and that difference is what made the double-open invisible.

### USE is a toggle: never click a panel that is already open

Once a minigame is up, the USE button **closes** it. So an extra click is not
harmless — it undoes the open. Every `open_panel()` therefore checks the panel
state *before* it clicks, and only ever spends a click on a panel known to be
closed. That makes it safe to call more than once, which matters because it has
been called twice by accident and the result was a panel that opened and closed
while every drag went into empty space.

"Panel is open" is checked with two independent signals, because the two failure
directions are not symmetric:

- a false **closed** costs one more click, which is harmless;
- a false **open** means the solver goes on to drag wires that are not there.

So the signal is the panel's own artwork (a wire endpoint, an anomaly tube) *or*
the brightness of the panel region, which distinguishes an open pale box from the
darker room behind it. Brightness alone is what makes this work before the
artwork is legible.

This bit Fix Wiring twice, in two unrelated ways: a duplicated `open_panel()`
call, and a `click_use()` that ran before the state check. Both are now covered by
`tests/test_fix_wiring.py`, which models USE as a toggle and asserts the solver
clicks exactly once, and never at all when the panel is already up.

## Driving a task: ask the game, do not read the screen

The hardest tasks were the ones the bot had to *see*. Start Reactor had to find
the lit pad, Inspect Sample had to find the odd tube, Calibrate Distributor had
to find the dial in range — and each of those was a guess about pixels that was
wrong in its own way. The lit-pad colour was invented, the tube template matched
the wrong thing, and the Calibrate Distributor solver ended up clicking the
game's own HUD three times and reporting "3/3 done".

**The game already knows the answer, and it will tell you.** Every minigame
with a pressable control exposes it as a plain public method, and that method
is the one the panel's own button calls:

| task | class | the method | what the game keeps |
|---|---|---|---|
| Start Reactor | `SimonSaysGame` | `HitButton(int)` | the sequence, in the TASK's bytes |
| Calibrate Distributor | `SweepMinigame` | `HitButton(int)` | the live dial and its angle |
| Inspect Sample | `SampleMinigame` | `SelectTube(int)` | which tube is odd |

So the plugin publishes the state and the solver asks the game to act:

- **`minigameHot.txt`** — the open panel's hot state, written on **every**
  FixedUpdate, separately from the snapshot. The snapshot is throttled to 50ms,
  and that is not fast enough: Calibrate Distributor's dial is inside its
  target window for a fraction of a revolution, and a solver sampling at 20Hz
  misses it.
- **`minigamecall <method> [int args]`** — calls a public method on the open
  minigame, through the game. It is not a way around the UI, it *is* the UI,
  minus the part where a pixel has to land on the right sprite.

The plugin refuses to call a panel's lifecycle methods (`Close`, `Begin`,
anything starting with `Set` or `Co`), because closing a minigame out of band
leaves the task in a state the game does not expect.

### The answer is usually on the TASK, not the panel

This is the single most useful thing the decompiled game told us. The panel
class holds the controls; the **answer** lives in `NormalPlayerTask.Data`, a
`byte[]` on the task itself:

- **Start Reactor** — `Data[0]` is the length of the sequence and `Data[1..]`
  are the pad indices. `HitButton(i)` compares `i` with `Data[taskStep + 1]`
  and does nothing at all if they differ.
- **Inspect Sample** — `Data[0]` is a state code (64 means a tube may be
  picked) and `Data[1]` is then the anomalous tube.
- **Calibrate Distributor** — the live dial and its distance from the target
  are computed by the game every frame and published by the plugin.

Walking the panel's class hierarchy will never find any of this, because it is
a different object.

### What the solvers do with it

| task | it reads | it does |
|---|---|---|
| Start Reactor | the sequence bytes, and whether the round's playback is over | `HitButton(Data[taskStep + 1])`, fifteen times over five rounds |
| Calibrate Distributor | the live dial's distance from its target | `HitButton(spinner)`, three times, once per dial |
| Inspect Sample | the state code and the odd tube | `SelectTube(tube)`, once |

And every one of them reports success **only when the game confirms it**. A
solver that presses a pad and sees nothing happen says so; it does not claim
the task is done.

## The plugin is part of the project, and it is in the repo

`plugin/` is the BepInEx plugin that runs inside the game. It is not a
dependency to be fetched — it is the half of the bot that can see the game, and
a change to it is a change to the bot. It lives here so it is versioned with
everything else.

```
cd plugin
dotnet build -c Release
copy bin\Release\AmongUsAI.dll "C:\Games\Among Us\BepInEx\plugins\"
```

The game loads it at startup, so a new build needs the game restarted. The
plugin is the only thing that can read the game's real state, and everything
that has to know what the game is doing goes through it.

## The gamepad has to exist BEFORE the game starts

Among Us enumerates its input devices at startup and does not hot-plug them, and
ViGEmBus leaves a zombie "Xbox 360 Controller for Windows" behind every time a
process that held a virtual pad dies. Both facts are in `bootstrap.py`.

- A pad created **after** the game is running is invisible to it. The player
  never moves, and every walk silently does nothing.
- Several pads at once make the game bind to a **dead** one, and again nothing
  moves — with no error anywhere, which is what makes it so confusing.

So the only reliable order is: purge the zombies, create the pad, **then**
launch the game, and keep everything in one process so the same pad is held by
the process that drives the bot. Running a task from a fresh python process
while the game is already up is exactly the broken configuration, and it looks
like a walking bug rather than an input-device bug.

`lab.py` is the harness for that: one process that owns the pad, owns the game,
and runs the test. `bootstrap.py` does the same for the real bot.

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
   *Changed since:* the harness no longer works in pixels for the tasks whose
   answer the game already holds. It asks the game. The model is unaffected
   either way, and the solvers stopped being wrong.

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

These are all done. `main.py`'s play loop now does exactly one thing:

```python
bot = agent_loop.Agent()
while True:
    if isInGame() and not keyboard.is_pressed('`'):
        print(f"  model: {bot.step()}")
    else:
        return 0
```

## Decisions taken

**Task routing.** The model picks which task and when, with
`do_task <task>`; the harness walks there and works the minigame. The task list
is in the prompt, so it can only ask for tasks that exist, and a refused request
names the outstanding ones.

**Reactivity.** The harness never auto-kills, not even on a proximity trigger.
Real players have the same reaction latency, so the model decides with the
information it has and lives with the delay. This was the explicit call.

**Kills.** `agent.kill` is not gated on `should_I_kill()`. That gate was a
harness-side decision the model could neither see nor override. The cooldown and
`cankill` are published to the model instead, and the game itself refuses an
unavailable kill.

**Walking no longer kills.** `utility.move()` contained an autonomous kill block,
and `roleplay.walk_to()` calls `move()` - so the model's `go_to` would have
killed anyone nearby as a side effect of moving. Removed.
