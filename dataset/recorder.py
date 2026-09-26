"""Record real matches in the multi-turn dataset format.

This is the honest data source: it plays with the real model against a real
game and writes down every turn, including the ones that failed. The failures
are the useful part - a dataset of only successes teaches the model nothing about
the parse errors and refusals we are trying to eliminate.

Usage:
    .venv\Scripts\python.exe dataset\recorder.py            # play and record
    .venv\Scripts\python.exe dataset\recorder.py --dry-run  # log, do not execute

Output: dataset/matches/<id>.json  (one file per match, see README.md)
"""
import argparse
import json
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import agent_loop  # noqa: E402
import botlink  # noqa: E402
import utility  # noqa: E402

OUT_DIR = os.path.join(HERE, "matches")


def _map_name():
    try:
        return utility.getGameData().get("map_id", "unknown")
    except Exception:
        return "unknown"


def new_id(map_name):
    stamp = time.strftime("%Y-%m-%d-%H%M%S")
    safe = "".join(c for c in str(map_name) if c.isalnum() or c in "-_")
    return f"{safe}-{stamp}"


class Recorder(agent_loop.Agent):
    """An Agent that writes down what it did, turn by turn.

    Subclasses Agent rather than wrapping it, so it sees the real system prompt
    and the real raw reply. A wrapper could only see the parsed result, which
    would throw away the most valuable column in the dataset.
    """

    def __init__(self, dry_run=False, **kw):
        super().__init__(**kw)
        self.dry_run = dry_run
        self.turns = []
        self.match_id = new_id(_map_name())
        self._seen_replies = set()

    def step(self):
        system = self.system_prompt()
        situation = self.situation()
        name, raw = self.decide()
        raw_text = raw if isinstance(raw, str) else " ".join(raw or [])

        observation = None
        ok = True
        if self.dry_run:
            observation = "(dry run: not executed)"
        elif name is None:
            observation = f"no valid action (said: {raw_text})"
            ok = False
        else:
            args = raw if isinstance(raw, list) else []
            try:
                observation = agent_loop.agent.run_action(name, args)
            except agent_loop.agent.ActionError as exc:
                observation = f"refused: {exc}"
                ok = False
            except Exception as exc:
                observation = f"error: {type(exc).__name__}: {exc}"
                ok = False

        self.last_action = f"{name} {' '.join(args)}".strip() if name else None
        self.last_outcome = observation
        if self.last_action:
            self.history.append(self.last_action)
            if len(self.history) > self.max_history:
                self.history.pop(0)

        self.turns.append({
            "n": len(self.turns) + 1,
            "system": system,
            "user": situation,
            "assistant": raw_text,
            "action": name,
            "args": list(args) if name and isinstance(raw, list) else ([] if name else None),
            "observation": observation,
            "ok": ok,
        })
        return f"{self.last_action or raw_text}  ->  {observation}"

    # ------------------------------------------------------------------ output
    def write(self, result="unknown", notes=""):
        os.makedirs(OUT_DIR, exist_ok=True)
        try:
            role = botlink.get_role()
            imp = botlink.read_ability().get("isimpostor") == "1"
            map_name = _map_name()
        except Exception:
            role, imp, map_name = "unknown", False, "unknown"

        refused = sum(1 for t in self.turns if not t["ok"])
        record = {
            "id": self.match_id,
            "source": "recorded",
            "map": map_name,
            "role": role,
            "is_impostor": imp,
            "result": result,
            "turns": self.turns,
            "stats": {
                "total": len(self.turns),
                "refused": refused,
                "unparseable": sum(1 for t in self.turns if t["action"] is None),
            },
            "notes": notes,
        }
        path = os.path.join(OUT_DIR, f"{self.match_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2)
        return path, record["stats"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="log the model's decisions without executing them")
    ap.add_argument("--interval", type=float, default=2.0)
    ap.add_argument("--result", default="unknown")
    args = ap.parse_args()

    rec = Recorder(dry_run=args.dry_run)
    print(f"recording match {rec.match_id}  (dry_run={args.dry_run})")
    print(f"  model: {rec.system_prompt().splitlines()[0]}")
    print("  Ctrl+C to stop and write the file.\n")

    try:
        while True:
            try:
                print("  " + rec.step())
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                # a broken turn must not lose the whole match
                print(f"  turn failed: {type(exc).__name__}: {exc}")
                rec.turns.append({
                    "n": len(rec.turns) + 1,
                    "system": "", "user": "", "assistant": "",
                    "action": None, "args": None,
                    "observation": f"harness error: {type(exc).__name__}: {exc}",
                    "ok": False,
                })
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        if rec.turns:
            path, stats = rec.write(result=args.result, notes="recorded by recorder.py")
            print(f"\nwrote {path}")
            print(f"  {stats}")
        else:
            print("\nno turns recorded, nothing written")


if __name__ == "__main__":
    main()
