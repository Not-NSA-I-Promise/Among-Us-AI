# Dataset — SFT for the Among Us agent

Hand-authored training data. **Not** self-distillation.

Self-distillation from the current model was the wrong idea and was removed: the
base model has never played Among Us and does not know what the game is. Training
on its own output teaches it to keep doing whatever it already does, which is
failing at exactly the things that matter — faking a download for half a second,
interrogating a stranger, walking into a room with the door open after a kill.

So these entries are written by hand to teach things the model cannot derive:

- the wiring panels come in a fixed order and have a numbered colour pattern
- a fake task must last as long as a real one or it is a giveaway
- a Detective should interrogate the player who *chased* the victim, not a stranger
- a Phantom should kill behind a closed door, then vanish
- only Detective and Phantom have two abilities; only five roles can vent
- meetings are won by specific, checkable claims, not by confident-sounding noise

## Files

| file | what it is |
|---|---|
| `AMONGUS_DICTIONARY.json` | the game knowledge a generating agent needs: roles, vent networks, task timings and orders, deception tactics, measured win correlates, slang, tropes, and a list of the specific failure modes to counteract |
| `build_entries.py` | the authored entries, as code, and the script that writes them to `entries/` |
| `validate.py` | the gate. Rejects entries that teach a defect |
| `entries/*.json` | the 10 sample entries, whole matches, 162 turns |

## Why whole matches

One turn is a mapping from a prompt to a reply. A match is a policy: when to
attack, when to shut up, what to do with the twenty seconds after a kill, how to
spend an ability once. The 10 entries run drop to win, 12-27 turns each, with
meetings, refused actions, and losses included.

Turn counts are deliberately uneven. An entry that is 12 turns long because the
round was short is fine; padding all of them to the same length teaches nothing
about pacing.

## The metatag gate

Every entry carries metatags, and `validate.py` checks them against the
dictionary rather than trusting the author:

```
python dataset/validate.py            # check everything
python dataset/validate.py --strict   # warnings fail too
```

It rejects:

- **role illegality** — Tracker or Crewmate venting, a crewmate killing,
  `ability2` on a role that has one ability, `protect` outside Guardian Angel
- **impostors completing real tasks** — the hardest habit to break, and the one
  that gives the game away
- **faking a visual task** without an explicit, justified `allow_visual`
- **wrong fake durations** — checked against `task_durations.json`, so a 0.5s
  "Fix Wiring" is rejected and a 3.5s one passes
- **impossible sequencing** — killing or walking during a meeting, two kills on
  consecutive turns, voting without speaking first
- **metatags that contradict the dictionary** — `can_vent: true` on a Tracker
- **dialogue that does not sound played** — 90-character speeches, stage
  directions, odd capitalisation

`tests/test_validator.py` asserts the validator actually catches each of these,
including the cases that must be *allowed*. A gate never shown to fail is not a
gate.

Two subtleties it handles:

- **Phantom is on both sides.** A flat role table says crew Phantom cannot kill,
  which would wrongly reject an impostor Phantom. The validator resolves
  dual-side roles by the entry's own `side` metatag.
- **Deliberate refusals are allowed.** An entry may contain an illegal action if
  it is marked `teaching_refusal: true` and `ok: false` — that is how the model
  learns to accept a correction instead of retrying. Entry 08 has one, where the
  agent tries to solve a task as Shapeshifter, is refused, and switches to
  faking. That is a warning, not an error, and it is intentional.

## The 10 entries

| # | role / side | map | what it teaches |
|---|---|---|---|
| 01 | Impostor | Skeld | the full kill cycle in the measured order, incl. the door trick, and refusing the kill twice on a witness |
| 02 | Phantom | Skeld | both abilities as distinct tools, kill behind a door shut *before* the kill, and losing a round |
| 03 | Detective | Skeld | interrogate the body not a stranger, report the notebook verbatim, ask "who followed you" |
| 04 | Crewmate | Skeld | find the killer with checkable evidence, buddy behaviour, and being wrong once |
| 05 | Viper | Polus | one ability, vent-kill, the correct Polus network and its invisible vents, one self-report |
| 06 | Engineer | Skeld | venting for movement only, and volunteering a vent nobody asked about |
| 07 | Tracker | Skeld | **cannot vent** — the legality case, as a real match |
| 08 | Shapeshifter | Airship | mimic the unaccused, avoid the Vault camera trap, accept a refusal |
| 09 | Scientist | Mira HQ | read vitals, then the bodies-vs-vitals deduction that proves a vent |
| 10 | Impostor 1v1 | Skeld | refusing the winning kill, and spending the hard lie at the only moment it works |

## Writing more

Read `AMONGUS_DICTIONARY.json` first. Add the entry to `build_entries.py`, run
it, then run `validate.py`. The gate is the point — an entry that teaches a
defect is worse than no entry, because it makes the defect *stronger*.

Give every turn a `rationale`. The model needs the reason, or it learns the
action without the judgement and will do the same thing in a situation where it
is wrong.

Keep the failures. Entries 02 and 04 lose, and 08 contains a refusal, because an
agent trained only on perfect rounds will not know what to do when a plan fails.

## Not here

No recorder. Logging the model's own games teaches it nothing, and it costs time
and server capacity every run.
