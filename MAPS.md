# Map support

Verified by `tests/test_maps.py`, not assumed. The check is honest about what is
missing rather than failing somewhere deep in a movement routine.

| map | movement graph | task database | playable |
|---|---|---|---|
| Skeld | yes | yes | **yes** |
| Polus | yes | yes | **yes** |
| Airship | no | yes | partially |
| Mira HQ | no | yes | partially |
| Fungle | no | no | no |

Check at any time with `utility.available_maps()`.

## What "partially" means

Airship and Mira HQ have a task database but no `graphs/*_G.pkl`, so:

- `go_to` and `do_task` cannot work - there is no graph to pathfind on
- task solving by name still works if the bot is already standing at a panel
- everything that does not need movement works: chat, voting, abilities, faking,
  and all the UI control

The harness says this in the prompt on those maps rather than letting the model
discover it through repeated refusals:

```
WARNING: this map (AIRSHIP) is not fully supported - no movement graph
(so go_to and do_task cannot work). Fully supported maps: SHIP, PB.
Expect movement to fail.
```

## The bug that caused this

The game reports `MapType.ToString()`: `Ship`, `Polus`, `Airship`, `Fungle`,
`MIRA HQ`. The rest of the code keyed everything off the original repo's legacy
names `SHIP` / `PB` / `AIRSHIP` / `HQ`, and set the key with `map_id.upper()`.

That produced `SHIP`, `POLUS`, `AIRSHIP`, `FUNGLE`, `MIRA HQ`. Only `SHIP` and
`AIRSHIP` matched any branch, so:

- `load_dict()` returned `None` on Polus, Fungle and Mira HQ, and every caller
  then hit an `AttributeError` on `None`
- `load_G("Polus")` looked for `graphs/Polus_G.pkl` when the file is `Pb_G.pkl`
  and raised a bare `FileNotFoundError`
- Airship resolved a task database but still had no graph, so movement failed
  anyway

**The bot worked on Skeld and was broken everywhere else.** It was never
noticed because Skeld is the default practice map.

`utility.normalize_map()` is now the single place that translation happens, and
`load_G()` raises an error naming the map, what is missing, and which maps do
work.

## Adding a map

1. Generate the graph and save it as `graphs/<NAME>_G.pkl`
2. Add the task database as `tasks-json/<NAME>_TASK_TYPES.json`
3. Add the entry to `_MAP_ALIASES` (game name -> internal key) and
   `_GRAPH_FILES` (internal key -> graph file)
4. `python tests/test_maps.py` will tell you whether it is complete

The graph can be produced from a recorded walk with `main.py`'s graph tooling,
but nothing in this repo currently does that automatically.
