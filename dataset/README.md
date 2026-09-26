# Dataset

Training data for the model that drives the harness. The goal is to reduce the
failure rate measured in `tests/test_no_autonomy.py` and the parse failures in
`tests/test_agent_parse.py` — a model that reliably emits one parseable action
per turn, in context of a whole match, rather than a single isolated turn.

## Format

JSON Lines. One JSON object per line, one line per match. Multi-turn inside,
because the thing being learned is a *policy over a match*, not a mapping from
one prompt to one reply. A single-turn dataset teaches a model to answer the
question; it does not teach it to remember what it did six turns ago, to not
kill the same person twice, or to stop saying "wait" forever.

```json
{
  "id": "skeld-2026-09-26-0001",
  "map": "Skeld",
  "role": "Shapeshifter",
  "is_impostor": true,
  "result": "crew",
  "turns": [
    {
      "n": 1,
      "system": "You are Shapeshifter. You have 1 ability: ...",
      "user": "Current situation: you are Shapeshifter (impostor); in Cafeteria; ...",
      "assistant": "go_to Electrical",
      "action": "go_to",
      "args": ["Electrical"],
      "observation": "walking to Electrical",
      "ok": true
    }
  ],
  "notes": "..."
}
```

### Fields

| field | meaning |
|---|---|
| `turns[].system` | the exact system prompt the model was given |
| `turns[].user` | the exact situation line it was given |
| `turns[].assistant` | its raw reply, **before** parsing |
| `turns[].action` / `args` | what the parser made of it, or `null` if unparseable |
| `turns[].observation` | what the harness reported back |
| `turns[].ok` | false when the action was refused or produced no valid action |

Keeping the raw reply next to the parsed action is the point. A dataset of only
successful parses teaches nothing about the failures, and the failures are what
we are trying to remove.

`ok: false` turns are the valuable ones. Do not filter them out.

## Why whole matches

A round of Among Us is 5-15 minutes and contains phases with different rules:
the drop, free roaming, the first meeting, mid-game, the final meeting. The
correct behaviour in each is different, and a model that has only seen
mid-game snippets will kill on cooldown and fake a MedBay scan.

So a recording should aim to span the whole round, including the meetings and
the endgame, rather than stopping after the first kill. `recorder.py` writes one
file per match for exactly this reason.

## Generating data

Two sources, both writing the same format.

**Record real matches** — the honest source:

```
.venv\Scripts\python.exe dataset\recorder.py
```

Plays with the real model and logs every turn, including the refusals. Point it
at a real game and let it play a few full rounds. This is the data that will
actually move the failure rate.

**Synthesise matches** — for bootstrapping, and for covering situations that are
rare in one sitting (a 1v1 endgame, a meeting where the body was found by
someone else, a round where the model correctly chose to do nothing for thirty
seconds):

```
.venv\Scripts\python.exe dataset\generate.py --matches 200 --out dataset\matches
```

Synthesised data is only as good as the script that made it. It is generated
from the same `agent.ACTIONS` table and the same prompt builder, so at least it
cannot teach the model a format the parser does not accept — but it teaches no
game knowledge, and should be labelled as synthetic. Every file records which
produced it in the `source` field.

## Splits

Do not train and validate on the same file. Split by `id`, not by turn, or the
same match leaks across the split and the validation number is meaningless.

## What a good sample looks like

The interesting cases, in rough order of value:

- the model replying with something unparseable, and the correct recovery
- the model choosing `wait` repeatedly and it being *right*
- a meeting where it speaks and then votes, in that order, inside the timer
- an impostor faking a task for the correct duration
- the model choosing not to kill when the kill was available
- the endgame with two players left, where the right answer is usually not to
  kill immediately
