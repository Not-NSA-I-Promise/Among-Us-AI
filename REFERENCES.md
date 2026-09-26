# References

External material worth keeping a pointer to. None of it is required to build or
run this, so nothing here is fetched at runtime.

## Repositories

| repo | why it is here |
|---|---|
| `Among-us-X/AmongUs-X` | https://github.com/Among-us-X/AmongUs-X — a separate Among Us agent project. Not yet read in detail, but it is the closest thing to a prior art for this specific problem: getting a model to actually play the social-deduction half of the game rather than only pathfind and solve minigames. Worth a proper look before building more here, because if it already has a prompt format, a role-legality table or a training set, those should be reused or at least compared against rather than reinvented. |
| `Not-NSA-I-Promise/Among-Us-AI` | https://github.com/Not-NSA-I-Promise/Among-Us-AI — this repository, and the `origin` remote. |

## Sources behind the dataset

The numbers and tactics in `dataset/AMONGUS_DICTIONARY.json` are not invented.
Provenance is in `DATASET_SOURCES.md`; the load-bearing one is:

**MineAmongUs** — *Can an agent lie with its body? Yes, and it decides who wins.*
1,344 matches of LLM/VLM agents playing Among Us, with a 23-behaviour taxonomy
and win-rate correlations. This is where the strategic ordering in the dataset
comes from: fake-mission performance +0.72, witness-aware kill +0.434, post-kill
flee +0.414, strategic non-reporting +0.270, counter-accusation +0.164. Winners
fake tasks 6.6x more often than losers.

Its reported failure modes are reproduced in the dictionary under
`AGENT_FAILURE_MODES` and are the specific things entries 01-10 are written to
counteract: self-disclosure, hallucinated witnesses, two impostors voting for
each other, chasing only targets who are never alone, and — the big one —
talking defensively instead of faking.

## Game data

- Vent networks per map: Among Us Wiki, *Vent*, and community map guides
- Task timings: community timing threads; see `DATASET_SOURCES.md` for the
  individual citations and for how much to trust them
- Task ordering and the common/short/long classification: Among Us Wiki, *Tasks*
