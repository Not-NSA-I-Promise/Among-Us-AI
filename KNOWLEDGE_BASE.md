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

### UNSOLVED: the task also needs the rings ROTATED

The original only reads a colour and clicks a bar. On the current game that is
not the whole task. Measured live:

- each of the three rings has a **draggable handle** on its rim;
- each row's bar is **green while that handle sits in the correct arc** and
  **silver otherwise** - the green-dominant pixel count at the bar's centre is a
  reliable signal (green ~60, silver 0);
- clicking the right-hand panel **rotated ring 1's handle**, and its bar went from
  green to silver;
- ring geometry at 1920x1080: centres `(700, 258) (700, 535) (700, 812)`,
  radius ~100. Bars centred at `(1232, 310) (1232, 585) (1232, 840)`.

A full 360-degree drag of a handle did **not** bring any bar green, so the
mechanic is not simply "rotate until the bar turns green", and this task is
**not solved**. Whatever the interaction is, it has to be found by experiment in a
live panel rather than reasoned about.

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
