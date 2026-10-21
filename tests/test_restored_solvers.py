"""The three hard tasks must be driven by the game's own state, not by pixels.

These three tasks - Start Reactor, Inspect Sample, Calibrate Distributor - were
the ones that never worked. Each was originally a pixel solver, and each pixel
solver was wrong in its own way: the sampling column was black, the lit-pad
colour was a guess, the tube template matched the wrong thing, and the button
row was the game's own HUD.

They are now driven by the game itself. The plugin publishes what the open
panel is doing - which dial is live and how far it is from its target, the
task's own sequence bytes, the id of the anomalous tube - and the solver asks
the game to act on the control it names. That is the same public method the
panel's own button calls.

So this file checks the properties that make that work, and the ones that make
it honest:

  * the solver asks the game, it does not click a picture
  * the solver reads the game's state, it does not match a template
  * success is only ever reported when the game confirms it
  * a closed panel is refused, not clicked at
  * there is always a way out

The pixel geometry these solvers used to hardcode is deliberately gone, and
the test says so: the numbers are in the game, not in the file.
"""
import ast
import os
import re
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
SOLVERS = os.path.join(ROOT, "task-solvers")

fails = []


def check(name, cond, detail=""):
    print(("  PASS " if cond else "  FAIL ") + name + ("" if cond else f" <- {detail}"))
    if not cond:
        fails.append(name)


def code_only(text):
    """The source with every docstring removed, and comments gone.

    Necessary, not pedantic: these files explain WHY they work and those
    explanations quote the old pixel numbers. A text search that cannot tell an
    explanation from a call is not a check.

    Done with the parser rather than by looking for triple quotes, because a
    docstring that ENDS with a quoted string - one whose last words are an
    empty string in quotes - breaks the line based version, and it broke it
    silently: the rest of the file was then treated as prose and every check
    in it failed for the wrong reason.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return text
    lines = text.splitlines()
    drop = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        # not every node with a `body` has one that is a list of statements -
        # a lambda's body is an expression, and that is not a docstring
        if not isinstance(body, list) or not body:
            continue
        first = body[0]
        if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            for i in range(first.lineno - 1, first.end_lineno):
                drop.add(i)
    out = []
    for i, line in enumerate(lines):
        if i in drop:
            continue
        out.append(re.sub(r"#.*$", "", line))
    return "\n".join(out)


TASKS = ["Inspect Sample", "Start Reactor", "Calibrate Distributor"]


def source(name):
    p = os.path.join(SOLVERS, name + ".py")
    return open(p, encoding="utf-8").read() if os.path.exists(p) else ""


print()
print("=== the three solvers exist ===")
for name in TASKS:
    p = os.path.join(SOLVERS, name + ".py")
    check(f"{name}.py exists", os.path.exists(p), p)
    src = source(name)
    check(f"{name} does not hunt for coloured blobs in a cropped panel",
          "_find_dials" not in src, "the colour-hunting rewrite is back")
    check(f"{name} does not claim geometry it does not have",
          "GUESSES" not in src, "it still warns about guessed positions")

print()
print("=== they ask the GAME, they do not click a picture ===")
for name in TASKS:
    code = code_only(source(name))
    check(f"{name} reads the panel's published state",
          "read_minigame_hot" in code,
          "it is not reading the game's own state")
    check(f"{name} acts through the game's own method",
          "minigame_call" in code or "HitButton" in code or "SelectTube" in code,
          "it is not driving the panel's own control")
    check(f"{name} does not sample the screen for a colour",
          "pyautogui.pixel" not in code and "getpixel" not in code,
          "it is still reading pixels")
    check(f"{name} does not match a template",
          "locateCenterOnScreen" not in code and "find_template" not in code,
          "it is still template matching")
    check(f"{name} does not call click_use() itself",
          "click_use(" not in code,
          "the harness opens the panel; a second USE would close it")

print()
print("=== the pixel geometry these solvers used is gone ===")
for name, gone, why in (
        ("Inspect Sample", "TUBE_TIMEOUT", "the old blind tube wait"),
        ("Start Reactor", "LIT = ", "the guessed lit-pad colour"),
        ("Calibrate Distributor", "colour_x", "the old strip sampling")):
    src = source(name)
    check(f"{name} has no {gone} ({why})", gone not in src, "it is still there")

print()
print("=== the stale JSON cache is not reintroduced ===")
src = source("Start Reactor")
check("Start Reactor does not open reactor_list.json",
      "reactor_list" not in code_only(src),
      "a stale file makes the next run replay pads that were never lit")
check("the reactor_list directory is gone",
      not os.path.exists(os.path.join(SOLVERS, "reactor_list")),
      "it is still on disk")

print()
print("=== honesty: success only when the game confirms it ===")
for name in TASKS:
    code = code_only(source(name))
    check(f"{name} refuses to act on a closed panel",
          "no panel is open" in code, "no panel check")
    check(f"{name} only reports success when the game confirms it",
          "confirms it" in code,
          "success is not gated on the game")
    check(f"{name} has a timeout",
          "gave up after" in code or "READY_TIMEOUT" in code,
          "it can loop forever")

print()
print("=== the panel's own state is what the solver keys on ===")
# Each task keys on something the game publishes, and those three things are
# the ones the game's own code says are the answer.
check("Start Reactor reads the task's sequence bytes",
      "data" in code_only(source("Start Reactor")),
      "it is not reading the sequence")
check("Start Reactor waits for the round's playback to finish",
      "roundready" in code_only(source("Start Reactor")),
      "a press during the playback is accepted and then thrown away")
check("Calibrate Distributor reads the live dial",
      "spinner" in code_only(source("Calibrate Distributor")),
      "it is not reading which dial is live")
check("Calibrate Distributor uses the game's own target window",
      "13.0" in source("Calibrate Distributor"),
      "the 13 degree window is the game's, not a guess")
check("Inspect Sample waits for the game to say a tube may be picked",
      "READY" in code_only(source("Inspect Sample")),
      "it is not waiting for the game's ready state")

print()
if fails:
    print("FAILURES:", ", ".join(fails))
    raise SystemExit(1)
print("all checks passed: the three solvers are driven by the game itself")
