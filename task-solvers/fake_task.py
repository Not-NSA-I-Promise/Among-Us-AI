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


def best_match(query, candidates):
    """Fuzzy-match a free-text task name against a list of real task names.

    Returns the best candidate, or None. Handles the inflections and dropped
    words the model actually produces: "wires" for "Fix Wiring", "swipe card" for
    "Swipe Card", "do the download" for "Download Data".

    Shared with roleplay.find_task, which has to resolve the same phrasings -
    if only this one could match them, the model could parse a task it could
    never execute.
    """
    import difflib
    q = str(query).strip().strip("\"'`.,;:!?").lower()
    if not q or len(q) < 3:
        return None
    candidates = [c for c in candidates if c]
    if not candidates:
        return None
    lowered = {c: c.lower() for c in candidates}
    words = [w for w in q.replace("(", " ").replace(")", " ").split()
             if w not in ("the", "a", "an", "task", "do", "my", "fake", "please")]

    for c, low in lowered.items():
        if low == q or low in q:
            return c

    best, best_ratio = None, 0.0
    for name in candidates:
        ratio = difflib.SequenceMatcher(None, q, lowered[name]).ratio()
        if ratio > best_ratio:
            best, best_ratio = name, ratio
    if best and best_ratio >= 0.62:
        return best

    # A long phrase gets no loose word-level pass. "wires" should find "Fix
    # Wiring", but "fix the flux capacitor" shares only the word "fix" and must
    # not be allowed to resolve to it - a false match here sends the bot to the
    # wrong panel.
    if len(words) > 2:
        return None

    # word-level, on stems, scored by how much of the query is covered
    best_name, best_key = None, None
    for name in candidates:
        stems = {_stem(w) for w in lowered[name].split()}
        hits = 0
        for w in words:
            sw = _stem(w)
            if not sw:
                continue
            if sw in stems:
                hits += 1
            elif any(difflib.SequenceMatcher(None, sw, ns).ratio() >= 0.75
                     for ns in stems):
                hits += 0.5
        if hits <= 0:
            continue
        key = (hits, -len(stems))
        if best_key is None or key > best_key:
            best_name, best_key = name, key
    if best_name and best_key[0] >= 1:
        return best_name
    return None


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

def is_visual(name, map_name=None, stage=None):
    """Is this task visible to other players HERE, at THIS stage?

    A flat per-task "visual" flag was wrong and the harness had to be corrected
    for it, because the same task is not visual on every map and not visual at
    every stage:

      - Prime Shields lights up on Skeld but shows nothing on Mira HQ.
      - Clear Asteroids fires missiles outside the ship, so it is visible on
        Skeld and Polus but not Mira HQ.
      - Skeld Empty Garbage / Empty Chute is only visual at the STORAGE stage
        (stage 2). The Cafeteria lever stage shows nothing, so faking stage 1 is
        perfectly safe.

    Returns (is_visual, reason) so the caller can explain the refusal instead of
    just failing.
    """
    rec = lookup(name)
    if not rec:
        return False, ""

    maps = rec.get("visual_maps")
    if maps and map_name:
        # task_durations.json uses the repo's internal map keys (SHIP, PB, HQ),
        # but accept the in-game names too rather than silently matching nothing.
        _MAP_WORDS = {
            "SHIP": ("SHIP", "SKELD"), "PB": ("PB", "POLUS"),
            "AIRSHIP": ("AIRSHIP",), "HQ": ("HQ", "MIRA", "MIRAHQ"),
            "FUNGLE": ("FUNGLE",),
        }
        want = set()
        for m in maps:
            key = str(m).upper().replace("_", " ").strip()
            want.add(key)
            want.update(_MAP_WORDS.get(key, ()))
        have = str(map_name).upper().replace("_", " ").strip()
        if have not in want and not any(w in have for w in want):
            return False, (f"{name} is only visual on {'/'.join(maps)}, and you "
                           f"are on {map_name}")

    vis_stage = rec.get("visual_stage")
    if vis_stage is not None and stage is not None:
        if int(vis_stage) != int(stage):
            return False, (f"{name} is only visual at stage {vis_stage}, and you "
                           f"are on stage {stage} - this part is safe to fake")

    if rec.get("visual") and not maps and not vis_stage:
        return True, (f"{name} is a visual task - other players can see it "
                      f"happening, so standing still does not look like doing it")

    return bool(rec.get("visual")), ""


def is_fakeable(name, map_name=None, stage=None):
    """Can this task be faked HERE, at THIS stage?

    The map- and stage-aware `is_visual` wins over the flat `fakeable` flag,
    because the flag is only a summary. A task whose record says
    `fakeable: false` because it is visual on one map is still fine to fake on
    a map where it shows nothing - Prime Shields on Mira HQ, or Skeld Empty
    Garbage at its Cafeteria stage. The flat flag is only consulted when we
    genuinely do not know the map or stage.
    """
    rec = lookup(name)
    if not rec:
        return False, ""

    if map_name or stage is not None:
        vis, why = is_visual(name, map_name, stage)
        if vis:
            return False, ((why or f"{name} is visual here") +
                           " - so standing still does not imitate it. Fake a "
                           "different task instead.")
        return True, ""

    rule = rec.get("fakeable", rec.get("visual") is False)
    if rule is True:
        return True, ""
    if rule == "stage1" and stage is not None and int(stage) == 1:
        return True, ""
    return False, (f"{name} is visual here, so standing still does not look like "
                   f"doing it - fake a different task instead")


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


def fake_task(name, allow_visual=False, factor=1.0, map_name=None, stage=None):
    """Stand at a task panel for as long a real one takes.

    Returns a dict describing what happened, so the caller can report honestly
    rather than claiming success.

    `map_name` and `stage` are what make the visual check correct: Prime Shields
    is visual on Skeld but not on Mira HQ, and Skeld Empty Garbage is only visual
    at the Storage stage, so stage 1 can be faked.
    """
    rec = lookup(name)
    if rec is None:
        return {"ok": False, "reason": f"no timing data for {name!r}",
                "known": known_task_names()}

    if not allow_visual:
        ok, why = is_fakeable(name, map_name, stage)
        if not ok:
            return {
                "ok": False,
                "reason": (why or f"{name} is visual here") +
                          ". Fake a different task instead.",
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
