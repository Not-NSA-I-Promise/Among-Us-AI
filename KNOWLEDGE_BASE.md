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
