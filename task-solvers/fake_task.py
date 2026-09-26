"""Fake a task convincingly.

An impostor standing at a panel and leaving after one second is the single most
common way to get caught. This stands there for as long a real crewmate would
take, so the timing matches.

Durations come from task_durations.json (see DATASET_SOURCES.md for provenance).
They are ranges, and this samples inside the range rather than always taking the
midpoint - a bot that takes exactly 8.5s on every download is its own tell.

What it deliberately does NOT do:
  - solve anything. The task bar will not move, and that is unavoidable.
  - fake a visual task by default. If the task is visible to other players
    (MedBay scan, Start Reactor, Asteroids, Chart Course) then no amount of
    standing still reproduces it, so the default is to refuse. The option exists
    via `allow_visual=True` because sometimes a brief fake is still the lesser
    evil, and the model gets to make that call.
"""
import json
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)

DURATIONS_PATH = os.path.join(ROOT, "task_durations.json")

_cache = None


def durations():
    global _cache
    if _cache is None:
        try:
            with open(DURATIONS_PATH, encoding="utf-8") as f:
                _cache = json.load(f)
        except (OSError, ValueError):
            _cache = {}
    return _cache


def _key(name):
    return str(name).strip().lower()


def _stem(word):
    """Crude but sufficient stem, so 'wires' and 'wiring' agree.

    Not linguistics - just enough to make task names match the loose ways the
    model refers to them.
    """
    w = str(word).strip().lower()
    if not w:
        return ""
    if w.endswith("ies") and len(w) > 4:
        w = w[:-3] + "y"
    if w.endswith("s") and not w.endswith("ss") and len(w) > 3:
        w = w[:-1]
    for suf in ("ing", "ed"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            w = w[:-len(suf)]
            break
    if w.endswith("e") and len(w) > 3:
        w = w[:-1]
    return w[:4] if len(w) >= 4 else w


def lookup(name):
    """Return the timing record for a task, matching loosely."""
    table = durations()
    want = _key(name)
    if want in table:
        return table[want]
    for k, v in table.items():
        if k.startswith("_"):
            continue
        if want == _key(k):
            return v
    if not want or len(want) < 3:
        return None
    # "Start Reactor 2" / "Upload Data (Admin)" style suffixes
    for k, v in table.items():
        if k.startswith("_"):
            continue
        if want.startswith(_key(k)) or _key(k).startswith(want):
            return v

    # Strip the words the model adds around a task name before fuzzy matching.
    words = [w for w in want.replace("(", " ").replace(")", " ").split()
             if w not in ("the", "a", "task", "do", "my", "fake")]

    # Fuzzy match, e.g. "wires" -> "Fix Wiring". difflib handles the inflection
    # that a word-overlap test cannot: "wires" and "wiring" share no exact token
    # but are obviously the same task. Tried against the whole name and against
    # each word, because the model usually drops the modifier ("asteroids") and
    # keeps only the distinctive part.
    import difflib
    candidates = [k for k in table if not k.startswith("_")]
    query = " ".join(words) if words else want
    if query:
        close = difflib.get_close_matches(query, candidates, n=1, cutoff=0.6)
        if close:
            return table[close[0]]

    # Word-level matching. The model usually drops the modifier and keeps the
    # distinctive part: "medbay scan" is "Submit Scan", "asteroids" is "Clear
    # Asteroids", "wires" is "Fix Wiring". None match on the whole string, so
    # match on stems instead - "wires" and "wiring" share no exact token but
    # both stem to "wir".
    #
    # Scored by how many of the query's words are covered, not "first match
    # wins": otherwise "fix wires" returns "Fix Weather Node" purely because
    # "fix" happens to appear there first.
    best_name, best_key = None, None
    for name in candidates:
        name_stems = {_stem(w) for w in _key(name).split()}
        hits = 0
        for w in words:
            sw = _stem(w)
            if not sw:
                continue
            if sw in name_stems:
                hits += 1
            elif any(difflib.SequenceMatcher(None, sw, ns).ratio() >= 0.75
                     for ns in name_stems):
                hits += 0.5
        if hits <= 0:
            continue
        # more coverage wins; then the shorter name, which is the more specific
        key = (hits, -len(name_stems))
        if best_key is None or key > best_key:
            best_name, best_key = name, key
    if best_name and best_key[0] >= 1:
        return table[best_name]
    return None

def is_visual(name):
    rec = lookup(name)
    return bool(rec and rec.get("visual"))


def typical_seconds(name):
    """A plausible real duration, sampled inside the task's range."""
    rec = lookup(name)
    if not rec:
        return None
    lo, hi = rec.get("seconds", [3, 5])
    if hi <= lo:
        return float(lo)
    # triangular-ish: centre-weighted but not a constant midpoint
    return random.uniform(lo, hi)


def known_task_names():
    return sorted(k for k in durations() if not k.startswith("_"))


def fake_task(name, allow_visual=False, factor=1.0):
    """Stand at a task panel for as long a real one takes.

    Returns a dict describing what happened, so the caller can report honestly
    rather than claiming success.
    """
    rec = lookup(name)
    if rec is None:
        return {"ok": False, "reason": f"no timing data for {name!r}",
                "known": known_task_names()}

    if rec.get("visual") and not allow_visual:
        return {
            "ok": False,
            "reason": (f"{name} is a visual task - other players can see it happening, "
                       f"so standing still does not look like doing it. "
                       f"Pass allow_visual=True if you still want to."),
            "visual": True,
        }

    seconds = typical_seconds(name) * factor

    sys.path.insert(0, os.path.join(ROOT, "task-solvers"))
    import pyautogui
    from task_utility import get_dimensions, wake

    wake()
    dims = get_dimensions()
    if not dims:
        return {"ok": False, "reason": "no game window dimensions"}

    # Open the panel at the player's own feet rather than a hardcoded pixel: the
    # task bar is the only thing that has to be showing, and pressing USE where
    # we are standing is what opens it.
    import roleplay
    roleplay.press_use()
    time.sleep(0.5)

    # Stand there. This is the whole point: the wait has to be the real duration.
    time.sleep(seconds)

    # Close the panel again so the bot is not left standing in a task window.
    try:
        pyautogui.press("escape")
    except Exception:
        pass
    time.sleep(0.2)

    return {
        "ok": True,
        "task": name,
        "seconds": round(seconds, 1),
        "visual": bool(rec.get("visual")),
        "note": rec.get("note", ""),
        "bar_moved": False,
        "caveat": "the task bar did not move - only the timing matches",
    }


if __name__ == "__main__":
    print("task timings loaded:")
    for n in known_task_names():
        rec = durations()[n]
        vis = "  VISUAL" if rec.get("visual") else ""
        fake = "" if rec.get("fakeable", True) else "  (bad to fake)"
        print(f"  {n:22} {rec['seconds'][0]:>3}-{rec['seconds'][1]:<3}s{vis}{fake}")
    print()
    for q in ("Download Data", "MedBay scan", "fix wires", "Start Reactor", "nonsense"):
        r = lookup(q)
        print(f"  {q:16} -> {r.get('seconds') if r else None}"
              f"{'  visual' if r and r.get('visual') else ''}")
