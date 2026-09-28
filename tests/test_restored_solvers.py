"""The three restored solvers must match the 2023 originals' geometry exactly.

Two of them were rewritten into something worse and the user had to point it out.
The originals are in git history and their coordinates were MEASURED against these
panels, so "improving" them by inventing new ones is how the bot ended up clicking
the game's own HUD.

This compares the restored files against the originals in git, extracting every
coordinate expression and every colour threshold, so a typo or a "harmless"
adjustment fails here rather than in a live game.
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
SOLVERS = os.path.join(ROOT, "task-solvers")

fails = []


def check(name, cond, detail=""):
    print(("  PASS " if cond else "  FAIL ") + name + ("" if cond else f" <- {detail}"))
    if not cond:
        fails.append(name)


def original(path, first_non_empty):
    out = subprocess.run(["git", "cat-file", "-p", f"{first_non_empty}:{path}"],
                         cwd=ROOT, capture_output=True, text=True)
    return out.stdout


ORIGINALS = {
    "Inspect Sample": ("task-solvers/Inspect Sample.py",
                       "1aee06fce223983c6c7fd0980e89c0af86b4c0b1"),
    "Start Reactor": ("task-solvers/Start Reactor.py",
                      "2d3b70bf55333234209172b1a18a593bdb5c5f46"),
    "Calibrate Distributor": ("task-solvers/Calibrate Distributor.py",
                               "2c965811b5b89940391da3f63de0fb41903a9dd0"),
}


def numbers(text):
    """Every numeric literal in a body of code, normalised.

    Comments and docstrings are stripped first: the restored files explain WHY
    they use these numbers, and those explanations quote the originals.
    """
    out = []
    in_doc = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith('"""') or s.startswith("'''"):
            in_doc = not in_doc
            continue
        if in_doc or s.startswith("#"):
            continue
        code = re.sub(r"#.*$", "", line)
        for m in re.finditer(r"\d+\.?\d*", code):
            out.append(m.group(0))
    return out


def code_only(text):
    """Strip comments and docstrings.

    Necessary, not pedantic: these files explain WHY they use the numbers they do,
    and those explanations quote the originals and name click_use(). A text search
    that cannot tell an explanation from a call is not a check.
    """
    out = []
    in_doc = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith('"""') or s.startswith("'''"):
            in_doc = not in_doc
            continue
        if in_doc or s.startswith("#"):
            continue
        out.append(re.sub(r"#.*$", "", line))
    return "\n".join(out)


# Numbers the originals used that are deliberately NOT reproduced, with the reason.
# Anything not listed here must still be present, so a typo fails the test.
INTENTIONALLY_CHANGED = {
    "Inspect Sample": {
        # the original's `time.sleep(61)` was a blind wait; it is now a poll with
        # a 65s ceiling, so the click lands when the tube appears rather than
        # 61s later whatever happened
        "61": "replaced by a 65s polling ceiling, which is strictly better",
        # note: 0.8 IS still present, as the settle after clicking START. The
        # original's 0.8 was the settle after click_use(), which is gone; the
        # one here earns its place.
    },
    "Start Reactor": {
        "0.8": "was the post-click_use settle; the harness opens the panel now",
        # the original's time.sleep(1/5) written out as 0.2
        "5": "1/5 written as 0.2, identical",
    },
    "Calibrate Distributor": {
        "0.8": "was the post-click_use settle; the harness opens the panel now",
    },
}

print()
print("=== the restored files exist and are not the broken rewrites ===")
for name in ORIGINALS:
    p = os.path.join(SOLVERS, name + ".py")
    check(f"{name}.py exists", os.path.exists(p), p)
    src = open(p, encoding="utf-8").read() if os.path.exists(p) else ""
    check(f"{name} does not hunt for coloured blobs in a cropped panel",
          "_find_dials" not in src, "the colour-hunting rewrite is back")
    check(f"{name} does not claim geometry it does not have",
          "GUESSES" not in src, "it still warns about guessed positions")

print()
print("=== every coordinate expression matches the original ===")
for name, (path, commit) in ORIGINALS.items():
    orig = original(path, commit)
    cur = open(os.path.join(SOLVERS, name + ".py"), encoding="utf-8").read()
    allowed = INTENTIONALLY_CHANGED.get(name, {})
    on, cn = numbers(orig), numbers(cur)
    missing = [n for n in on if n not in cn and n not in allowed]
    check(f"{name} keeps every number the original used",
          not missing,
          f"missing and not declared intentional: {sorted(set(missing))}")
    for n, why in allowed.items():
        check(f"{name}: '{n}' is intentionally not reproduced", n not in cn,
              f"'{n}' is present, so the reason recorded for it is stale")
    print(f"     {name}: original {len(on)} literals, restored {len(cn)}")

print()
print("=== the specific values that were lost ===")
cases = [
    ("Inspect Sample", "dimensions[2] / 1.52", "the START click x"),
    ("Inspect Sample", "dimensions[3] / 1.16", "the START click y"),
    ("Inspect Sample", "dimensions[2] / 2.81", "the tube search region x"),
    ("Inspect Sample", "dimensions[3] / 3.2", "the tube search region y"),
    ("Inspect Sample", "y_offset / 2.87", "the click offset below the match"),
    ("Start Reactor", "dimensions[2] / 3.7", "the pad grid origin x"),
    ("Start Reactor", "dimensions[3] / 2.3", "the pad grid origin y"),
    ("Start Reactor", "dimensions[2] / 16", "the pad grid x step"),
    ("Start Reactor", "dimensions[3] / 9", "the pad grid y step"),
    ("Start Reactor", "dimensions[2] / 3.11", "the offset from pad to button"),
    ("Calibrate Distributor", "dimensions[2] / 1.56", "the strip x"),
    ("Calibrate Distributor", "dimensions[3] / 4.8", "the yellow sample y"),
    ("Calibrate Distributor", "dimensions[3] / 2.16", "the blue sample y"),
    ("Calibrate Distributor", "dimensions[3] / 1.44", "the cyan sample y"),
    ("Calibrate Distributor", "dimensions[3] / 14.4", "the button offset"),
]
for name, expr, why in cases:
    src = open(os.path.join(SOLVERS, name + ".py"), encoding="utf-8").read()
    check(f"{name} keeps {expr} ({why})", expr in src, "it is not there")

print()
print("=== the lit-pad colour is the original's ===")
src = open(os.path.join(SOLVERS, "Start Reactor.py"), encoding="utf-8").read()
check("the lit colour is (68, 168, 255)", "68" in src and "168" in src and "255" in src,
      "the measured colour is gone")
check("it still tolerates +/-2 per channel", "abs(pixel[0] - LIT[0]) < 2" in src,
      "the tolerance is gone")

print()
print("=== the long animation wait is back ===")
src = open(os.path.join(SOLVERS, "Inspect Sample.py"), encoding="utf-8").read()
check("Inspect Sample waits about a minute for the sample",
      "TUBE_TIMEOUT = 65.0" in src,
      "the wait was shortened to 7.5s, which is shorter than the animation")
m = re.search(r"TUBE_TIMEOUT = ([0-9.]+)", src)
if m:
    check("and the wait is genuinely long", float(m.group(1)) >= 45.0, m.group(1))

print()
print("=== the stale JSON cache is not reintroduced ===")
src = open(os.path.join(SOLVERS, "Start Reactor.py"), encoding="utf-8").read()
check("Start Reactor does not open reactor_list.json",
      "reactor_list" not in code_only(src),
      "a stale file makes the next run replay pads that were never lit")
check("the reactor_list directory is gone",
      not os.path.exists(os.path.join(SOLVERS, "reactor_list")),
      "it is still on disk")

print()
print("=== honesty: success only when the game confirms it ===")
for name in ORIGINALS:
    src = open(os.path.join(SOLVERS, name + ".py"), encoding="utf-8").read()
    code = code_only(src)
    check(f"{name} refuses to click a closed panel",
          "no panel is open" in code, "no panel check")
    check(f"{name} only reports success when the game confirms it",
          ("confirms it" in code)
          or ("the panel closed" in code and "_panel_open" in code),
          "success is not gated on the game")
    check(f"{name} does not call click_use() itself",
          "click_use(" not in code,
          "the harness opens the panel; a second USE would close it")
    check(f"{name} has a timeout",
          "gave up after" in code or "TUBE_TIMEOUT" in code,
          "it can loop forever")

print()
if fails:
    print("FAILURES:", ", ".join(fails))
    raise SystemExit(1)
print("all checks passed: the three solvers are back to the measured originals")
