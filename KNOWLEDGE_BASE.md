# Among Us knowledge base

Researched facts about the game, with sources and confidence. This exists because
I got a core fact wrong: I had **Chart Course** and **Start Reactor** on the
visual-task list, and neither is visual. Everything here was checked against
the wiki rather than assumed.

**When something here is not listed, or you are unsure: research it, and if
research does not settle it, ask the user. Do not guess.** See
`WHEN_UNSURE.md` — this mistake was made once already and cost a round.

Confidence key: **[high]** confirmed by the wiki or two independent sources,
**[med]** one source or community consensus, **[low]** inferred.

---

## Visual tasks

A visual task is one where other players **see** it being done, so seeing it done
proves the player is not the impostor. Hosts can switch the effects off in
game options, which is why a crewmate faking one can still get away with it.
**[high]** — [Among Us Wiki, Visual tasks](https://among-us.fandom.com/wiki/Visual_tasks)

| Task | Visual on | Not visual on |
|---|---|---|
| Submit Scan | Skeld, MIRA HQ, Polus | — |
| Clear Asteroids | Skeld, Polus | **MIRA HQ** (same task, no effect there) |
| Prime Shields | Skeld | **MIRA HQ** |
| Empty Garbage | **Skeld, Storage stage only** | MIRA HQ, Polus, Airship, Fungle |
| Empty Chute | **Skeld, Storage stage only** | — |

**The Fungle and The Airship have no visual tasks at all.** **[high]**

Explicitly **not** visual, which I had wrong: **Chart Course**, **Start
Reactor**, Unlock Manifolds, Divert Power, Fix Wiring, Swipe Card, Insert Keys,
and every other task not in the table above. **[high]** — both the wiki's visual
task page and the Uncyclopedia task table agree.

### The subtlety that matters for faking

**Empty Garbage is only visual on its SECOND stage.** You pull the Cafeteria
lever (no effect anyone can see), then the Storage lever — and *that* one vents
garbage into space where anyone in Storage can watch. So a fake is convincing
only if the impostor is **in Storage** for the second lever. **[high]**

A ghost completing a visual task still triggers the effect, except on MIRA HQ.
Impostors can occasionally use this deliberately, though ghosts are invisible to
the living so it is rarely usable. **[med]**

### The correct faking rule

- Never fake a visual task **while its effect would be visible to others**
- It *is* safe to fake a visual task's **non-visual stage** — Empty Garbage in
  Cafeteria looks exactly like a crewmate doing it
- If the host has disabled effects, visual tasks are safe to fake, but the bot
  cannot detect that setting, so it should still refuse

---

## Common tasks

Common tasks go to **every** player if the host enables them. So if you see
someone doing a common task, they have it — and **if you do not have that task,
you are the impostor**. Faking a common task you were not given is a certain
loss, not a risk. **[high]**

Polus has the most common tasks: Swipe Card, Fix Wiring, Insert Keys, Scan
Boarding Pass. **[med]**

The bot should therefore never fake a task that is not on its own fake list. The
harness enforces this in `agent.fake_task`.

---

## Inspect Sample — verified working

Measured live on Skeld MedBay, 1920x1080 game on a 2560x1600 desktop:

- `do_task.py` walks to the panel, opens it with `task_utility.click_use()` (a
  mouse click on the on-screen USE button), and it opens **on the first click**.
  Opening the panel with gamepad A via `roleplay.press_use()` is *not* reliable —
  tasks that way log "the game says no panel is open" and refuse at the door. The
  2023 convention of the solver clicking its own panel open is correct.
- The tube is matched at y=497 and the submit click is at **y=873**, i.e.
  `tube_y + height/2.87`, exactly as the 2023 original computes it. This is
  correct. An earlier reading of the panel screenshot suggested the click landed
  below the buttons; that was a misread of a scaled image, and a rewrite to
  locate the buttons by colour was reverted rather than shipped.
- For the record, the green confirm buttons sit at y 825..868 in the *game crop*
  (`task_utility.get_screenshot()` is 1920x1080), and the green "SELECT ANOMALY"
  text below them is at y 923..957. `pyautogui.screenshot()` returns the whole
  2560x1600 desktop instead. Do not mix the two up when reasoning about panel
  coordinates — but the 2023 arithmetic already lands on a working click, so the
  mapping is not needed.
- **It is flaky on a cold panel.** Two consecutive identical runs: the first
  clicked (733, 873) and the panel stayed open; the second clicked the identical
  point and submitted, task bar 0/1 → 1/1. The first click after START can be
  swallowed while the panel settles. A retry on "panel still open" is the obvious
  hardening; it is not implemented yet.
- Verified result: `VERIFIED: the game reports Inspect Sample complete (1/1)`.

### It is now driven by the game, and the flakiness is gone

The pixel version above still works, but the game knows the answer, so the
solver no longer has to find it. `SampleMinigame` keeps the id of the
anomalous tube in **the task's own bytes**, and refuses a pick made before it
is ready — read out of the game's own code:

| what | where | meaning |
|---|---|---|
| the state code | `NormalPlayerTask.Data[0]` | 32 = processing finished, 64 = a tube may be picked, 128 = the lower buttons are up |
| the odd tube | `NormalPlayerTask.Data[1]` | written when the processing finishes, and only valid once the state is 64 |
| the pick | `SampleMinigame.SelectTube(int)` | does nothing unless the state is 64, and compares its argument with `Data[1]` |

So the solver waits for the state to be 64, reads `Data[1]`, and calls
`SelectTube` — the same public method the tube's own button calls. The START
press is still a mouse click, because the START button is ordinary panel
furniture and the game exposes no method for it; that click is retried,
because the old solver's one known flaw was the first click after the panel
opens being swallowed.

**Verified live:** the game named tube 4, the pick was made, and the task bar
went 0/1 → 1/1.

---

## Start Reactor — verified working

The panel is a memory game. On the left, a 3x3 grid of squares; on the right,
a 3x3 grid of pads. The game plays a sequence back and you press the matching
pads in the same order. There are five rounds, and each round replays the whole
sequence with one more element added — so the rounds are 1, 2, 3, 4 and 5
presses long, and the task needs 15 presses in total.

**The sequence is not in the minigame, and it is not on the screen.** It is in
the task's own bytes, `NormalPlayerTask.Data`, a `byte[6]` allocated for a
Start Reactor task — room for a count and five indices:

| what | meaning |
|---|---|
| `Data[0]` | how long the current sequence is |
| `Data[1..count]` | the pad indices, in order |
| `taskStep` | how many of them have been pressed **this round** |

`SimonSaysGame.HitButton(i)` compares `i` with `Data[taskStep + 1]` and does
nothing at all if they differ, so **the pad to press is `Data[taskStep + 1]`**.
`taskStep` is reset to 0 at the end of every round's playback, which is why
every round starts again at `Data[1]`. A press on the WRONG pad sets
`Data[0] = 0`, which throws the sequence away and restarts with a fresh random
pad — a wrong press loses the task, it is not a lost point.

### The trap: a press during the playback is accepted and then thrown away

`HitButton` does not check whether the round's playback is still running. A
press issued mid-playback passes the `Data[taskStep + 1]` check, bumps
`taskStep`, and is then silently discarded when the playback resets the
counter. The bot is now one press out of step, and its next press is the wrong
one, which loses the task.

The game's own end-of-playback signal is its colour: the playback turns every
pad **grey** as it starts and **white** as it ends, and nothing else makes a
pad white while a playback is running. The press echo is a brief blue flash on
one pad, so "at least one pad is white" is true whenever the player is allowed
to press. The plugin publishes that as `roundready`.

**Verified live:** five rounds, 15 presses, task bar 0/5 → 5/5, in 14.6s.

---

## Calibrate Distributor — verified working

Three dials, each with a handle on its rim. The handle sweeps round, and the
dial is only correct while it is within **13 degrees** of the top. The game
accepts a press only on the live dial and only inside that window; a press at
the wrong time is not ignored, it throws the whole task away — the dials are
re-randomised and you start again.

All of that is the game's own arithmetic, read out of its code:

```
SweepMinigame.CalcXPerc():
    int rem  = (int)(SpinRate * timer) % 360;
    int dist = min(rem, 360 - rem);
    // accepted when 13.0f > dist
```

`SweepMinigame.FixedUpdate` advances `timer` and writes the same distance into
`Gauges[spinnerIdx].Value` — 0.9 when the dial is in range, 0.1 when it is
not, with a small Perlin wobble on top. `SweepMinigame.HitButton(i)` does
nothing unless `i == spinnerIdx`, and on a good press it moves on to the next
dial; on a bad one it calls `ResetGauges()`, which sets `spinnerIdx` back to 0
and re-randomises the timers.

The plugin publishes the live dial's `spinner`, `dist` and `spinrate`, computed
with the game's own arithmetic, so the solver cannot get the rounding wrong.

**Verified live:** three dials, three presses, task bar 0/1 → 1/1, in 5.8s.

### A note on the Fix Wiring section below

The "rings ROTATED" passage that used to sit under Fix Wiring was describing
**Calibrate Distributor**, not Fix Wiring. The three dials with a handle on
their rim and a bar beside each one are Calibrate Distributor's panel. Fix
Wiring's panel is a pair of wire columns and nothing else. That misreading is
why the old Calibrate Distributor solver went looking for coloured blobs in a
cropped picture of the panel: it was reading the wrong task's shape.

---

## Dummy tasks

Some "tasks" shown to an impostor **cannot be completed at all**. **[med]**

- Reactor on Skeld has a dummy Divert Power panel
- Polus Office has a dummy, and Divert Power does not exist on that map
- Airship has three unfixable Fix Wiring panels: Armory, Communications, Vault
- Fungle has an unusable Empty Garbage bin in Lounge

So an impostor standing at one of these doing nothing is correct behaviour, not
suspicion. **[med]** — single source, worth verifying in game.

---

## Task timing

Community-measured; see `DATASET_SOURCES.md` for individual citations. The
numbers in `task_durations.json` come from here. **[med]** overall, because the
main timing study was done on mobile.

| Task | Time |
|---|---|
| Download / Upload Data | 8-10s (a hard timer) |
| Submit Scan | 10s |
| Start Reactor | 15s+, and highly variable with skill |
| Inspect Sample | ~60s, keeps counting if you walk away |
| Fuel Engines | ~6s per stage, four stages |
| Prime Shields | 8-12s |
| Clear Asteroids | 8-12s |
| Swipe Card | 4-7s, wildly variable |
| Common tasks | 3-5s |
| Fix Wiring | ~3-4s per panel |
| Chart Course | 6-10s |
| Calibrate Distributor | 6-9s |

A fake that returns faster than the real thing is the single most common tell.

---

## Fix Wiring

Wires are ordered by a **hidden number 1-7**, and you connect lowest to lowest.
The **panel order is fixed**: Electrical, Storage, Admin, Navigation, Cafeteria,
Security. You are assigned **3 of those 6** panels, and they always appear in
that relative order. **[high]** — the wiki documents the order, and it is
visibly wrong to connect them out of sequence.

Consequence: a bot that fakes wiring in alphabetical or arbitrary order is
visibly incorrect to anyone who knows the pattern, and a model trained on that
will repeat it every time.

### All four wires on a panel must be connected

This is the single most important fact about the task, and the harness had it
wrong. The wiki states that "at each panel, 4 wires are assigned one of the
default colors: red, blue, yellow, and magenta", and that "the background behind
the four colored wires is eleven wires for aesthetics". **[high]**

So a single Fix Wiring panel has **four real wires**, and **all four** must be
connected before the panel counts as done. Only then does the task move to the
next of its three panels.

The solver used to connect one wire and close the panel, on a mistaken belief
that a Skeld panel has only one wire. In a live game that produced: drag red,
close, and the task bar never moved — because a panel with one of four wires
connected is not finished. Confirmed in game, and the fix is in
`task-solvers/Fix Wiring.py`.

Two more facts that matter for automating it:

- **A drag can connect to the wrong wire.** "Wires can connect to the incorrect
  wire, but they must be connected to the correct wire to complete the task", and
  "multiple wires can be connected to the same wire". **[high]** So the visual
  result of a drag is not proof of a correct connection - the task's own stage
  counter is the only real evidence, which is what the harness checks.
- **Connected wires stay on screen.** They are still drawn between the two sides
  after connecting. **[med]** So a solver that checks "is this colour still
  visible?" must look for the loose *endpoint* at high confidence, not for the
  colour anywhere, or it will think a completed wire is still waiting and drag it
  again.

### The sampling column is NOT the clicking column - measured, not guessed

The 2023 original samples the colour at `window_x + width/1.56` = **x 1231** at
1920x1080. Measured on a live panel, that column is **`rgb(0, 0, 0)`** - the
black middle of each row's bar - on all three rows. A "bright yellow" test cannot
pass on black, so the solver could never have worked there.

The colour is a small strip on the **left edge** of each bar:

| | measured |
|---|---|
| yellow | x 1116..1134 |
| blue | x 1116..1122 |
| cyan | x 1116..1122 |
| the button | x 1128..1336 |

So sampling is at `width * 7/12` and clicking stays at `width / 1.56`. The two
columns are **deliberately different**; the original assumed they were the same,
and that is the whole bug. The three sample **rows** (height/4.8, /2.16, /1.44 =
225, 500, 750) are the original's and are correct.

**The original's colour thresholds are correct** and were never the problem. With
the column corrected they read, live: yellow `rgb(255,227,0)`, blue
`rgb(83,98,255)`, cyan `rgb(111,249,255)` - all three pass the 2023 tests
exactly as written.

> **Those measurements are Calibrate Distributor's, not Fix Wiring's.** The three
> rows of coloured bars and the button under each are that task's panel. They
> were filed here, and the mismatch is why the Calibrate Distributor solver
> ended up hunting for coloured blobs in a cropped picture: it was reading the
> wrong task's shape. The numbers above are therefore **not** a description of
> Fix Wiring and should not be copied into anything.

### The rings are not part of Fix Wiring

An earlier version of this file claimed that Fix Wiring's panel has rotating
rings with draggable handles, and that a full 360-degree drag never turned any
bar green. **That was Calibrate Distributor's panel**, described by mistake. The
rings are the three dials, the bars are the gauges beside them, and the reason
a drag did nothing is now known exactly: the dials are not dragged at all, they
are pressed, and the press is only accepted inside a 13-degree window. See
**Calibrate Distributor** above.

Fix Wiring's panel is a pair of wire columns with a header, and nothing else.
What is true of it, and was measured, is below.

### The wires themselves

Fix Wiring's solver locates each wire by its **colour**. There are four
templates — red, blue, yellow and pink — and a wire is dragged from the left
column's end of that colour to the right column's end of the same colour. The
wiki's description of the panel agrees: "at each panel, 4 wires are assigned one
of the default colors: red, blue, yellow, and magenta". **[high]**

### UNSOLVED: the Polus 8-wire panel

That is the only part of this task left open. It is described below.

### Polus 8-wire panel is not supported

On Polus the final panel, in Electrical, has **eight** wires: the four standard
colours plus light green, white, cyan and gray. **[high]** There are no templates
for those four extra colours in this repo, so that panel cannot be completed
here. The solver connects what it can and says how many wires it managed, rather
than claiming the panel is done. Templates for the four extra colours would be
needed to close this gap.

---

## Venting

| Map | Vents | Notes |
|---|---|---|
| Skeld | 14, four networks | Upper/Reactor/Lower, MedBay/Security/Electrical, Admin/Cafeteria/Shields, Weapons/Nav/Shields |
| Polus | 12, four systems | Vents are holes in the floor — **no open/close animation**, so hiding is much harder to spot |
| Airship | 12, four networks | **no visual tasks**, so timing is the only tell |
| MIRA HQ | all interconnected | vent, get seen, then cut the witness off before Cafeteria |
| Fungle | — | rooms move between rounds |

**Communications has no vent on any map.** **[high]**

Only Impostor, Engineer, Shapeshifter, Phantom and Viper can vent. Hiding in a
vent **pauses the impostor kill cooldown**, but not other ability cooldowns.
**[high]** — [Wiki, Vent](https://among-us.fandom.com/wiki/Vent)

On Skeld, MIRA HQ, Airship and Fungle the vent **animation is visible outside
your vision**, so venting away after a kill is a visible act. On Polus it is not.

---

## Roles

Two abilities is the maximum. Only **Detective** and **Phantom** have a second.
Only **Impostor, Shapeshifter, Phantom, Viper, Engineer** can vent. Only
impostor-side roles can kill. **[high]** — verified by listing every class in the
IL2CPP dump that overrides `UseSecondaryAbility` and by the `CanVent` flag.

| Role | Side | Abilities | Notes |
|---|---|---|---|
| Crewmate | crew | 0 | |
| Impostor | imp | 0 abilities, kill + sabotage + vent | |
| Scientist | crew | vitals | sees who is dead/disconnected |
| Engineer | crew | vent | movement only, cannot kill |
| Guardian Angel | crew | protect one player | ghost only |
| Shapeshifter | imp | mimic | |
| Noisemaker | crew | decoy arrow | |
| Phantom | either | vanish, decoy | ability 1 works even as crew |
| Tracker | crew | track a player | **cannot vent** |
| Detective | crew | interrogate, read notes | |
| Viper | imp | vent, and **kill from inside a vent** | |
| Judge | crew | one extra vote | blocked until tasks done |

### Viper specifically — the source of the "killed" bug

Viper's kill comes **through the vent**, at longer range than a normal kill.
Pressing USE on the ground near a vent with a Viper does not behave like a normal
impostor kill, so a harness that says "killed" after a single `press_use()` with
nothing verified is reporting a guess, not a fact. **[med]** — the vent-kill
mechanism is documented, the exact range is not. Verify in game.

---

## Meeting behaviour

- Tie votes **void** the meeting. A tie is a guaranteed impostor win. **[high]**
- Emergency meetings can be limited by the host; an impostor calling one is
  deeply unexpected and buys a whole discussion to plant a name. **[med]**
- "I saw him vent" is believed almost without question — and if it is wrong, the
  person who claimed it is now the most suspicious player alive. Save it for
  when one eject ends the game. **[med]**
- Skipping is usually right when you have no information. Ejecting an innocent
  loses the round. **[med]**

---

## How to get the truth about a minigame

There is a way to read what a minigame actually does, and it is not by
guessing at pixels: **the game's own code is in the IL2CPP binary, and it can
be decompiled.**

`tools/dump/dump.cs` is an Il2CppDumper dump. It has every class, field and
method SIGNATURE, and the RVA of every method — but not the bodies. So it
tells you that `SweepMinigame` has a `HitButton(int)` and a `float SpinRate`,
and nothing about what `HitButton` accepts.

Cpp2IL recovers the bodies. `Cpp2IL.Core.dll` and `LibCpp2IL.dll` are in
`C:\Games\Among Us\BepInEx\core`, the metadata is in
`Among Us_Data\il2cpp_data\Metadata\global-metadata.dat`, and the code is in
`GameAssembly.dll`. A small driver that loads all three and asks
`MethodAnalysisContext.Analyze()` gives the bodies as IL.

**Use the raw x86, not Cpp2IL's ISIL.** The ISIL is a normalised form and it
loses the detail that matters: it renders `Data[taskStep + 1]` as a comparison
against a pointer, because it cannot tell an array read from a field read. The
raw disassembly is exact, and the difference between the two is the difference
between "the solver presses the wrong pad" and "the solver presses the right
one".

The driver lives at `tools/cpp2ildrv` and runs as:

```
cd tools/cpp2ildrv
dotnet run -c Release --no-build -- out.txt "SimonSaysGame" --raw
```

`--raw` gives exact x86-64 for every method of the named types; without it you
get the ISIL. Types are matched by name, and a nested coroutine's name is
given as `Outer+<Coroutine>d__NN`.

### The rules that came out of it

- **A minigame's answer is usually on the TASK, not the panel.** The panel
  class holds the controls; the sequence, the anomaly id and the state code
  live in `NormalPlayerTask.Data`, and the panel reads them. Walking the
  panel's class hierarchy will never find them.
- **A minigame that has a pressable control exposes it as a public method**,
  and that method is the one the panel's own button calls. `HitButton(int)`,
  `SelectTube(int)` and friends are the game's UI, not a way around it. The
  plugin calls them through `minigamecall`.
- **Read the constants out of the binary, do not recall them.** The 13-degree
  window in Calibrate Distributor, the 1.0-3.0 second random timer, the
  `byte[6]` task data, the 64 state code: each is a float or a byte in
  `GameAssembly.dll`, and `pefloat.py` in this repo reads them by address.

---

## Known uncertainties

These are open. Do not build on them without checking:

1. **Exact dummy-task locations** — [med], one source
2. **Viper vent-kill range** — [med], undocumented precisely
3. **Whether `PlayerTask.Locations` ever holds more than the current panel** —
   the harness has only ever observed one position per task, so multi-stage
   routing re-reads the game's reported location each pass instead
4. **Task timings for the 2026.8.18 build** — all figures predate it
5. **Fungle vent network** — not documented anywhere reliable

If any of these matter to what you are building, research them or ask.
