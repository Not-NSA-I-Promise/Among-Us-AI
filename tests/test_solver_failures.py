"""A solver must never look like a success when it actually crashed.

pyautogui.locateCenterOnScreen RAISES ImageNotFoundException. Solvers written
as `pos = pyautogui.locateCenterOnScreen(...)` therefore die on that line, and
solve_task used to return 0 for a dead subprocess - so the model was told a task
was completed when nothing had happened. The live log proved it: a 0.738 match
was discarded because the confidence ladder had no exception handling, and the
resulting crash was reported as a completed Fix Wiring.
"""
import _path  # noqa: F401
import ast
import os
import sys
import glob

failures = []


def check(label, cond, detail=""):
    print("  {} {}{}".format("PASS" if cond else "FAIL", label,
                             ("  <- " + str(detail)[:150]) if (detail and not cond) else ""))
    if not cond:
        failures.append(label)


SOLVERS = sorted(glob.glob(os.path.join("task-solvers", "*.py")))

print("=== 1. no solver calls locateCenterOnScreen without guarding it ===")
for path in SOLVERS:
    name = os.path.basename(path)
    with open(path, encoding="utf-8", errors="replace") as f:
        src = f.read()
    if "locateCenterOnScreen" not in src:
        continue
    uses_helper = "find_template" in src
    # the only remaining direct calls should be inside task_utility's own helper
    check("{} routes through find_template".format(name), uses_helper, src[:200])

print()
print("=== 2. every solver that uses find_template imports it ===")
for path in SOLVERS:
    name = os.path.basename(path)
    if name == "task_utility.py":
        continue          # this IS the module that defines it
    with open(path, encoding="utf-8", errors="replace") as f:
        src = f.read()
    if "find_template" not in src:
        continue
    has_star = "from task_utility import *" in src
    check("{} imports task_utility's helpers".format(name), has_star, src[:160])

print()
print("=== 3. no unbounded retry loop on a template remains ===")
for path in SOLVERS:
    name = os.path.basename(path)
    with open(path, encoding="utf-8", errors="replace") as f:
        src = f.read()
    # strip comments so a comment describing the old bug is not a false positive
    code = "\n".join(l.split("#")[0] for l in src.splitlines())
    check("{} has no unbounded template retry".format(name),
          "while pos is None" not in code, "unbounded while-loop still present")

print()
print("=== 4. find_template exists, is importable, and returns None not raise ===")
sys.path.insert(0, os.path.join(os.getcwd(), "task-solvers"))
import task_utility  # noqa: E402

check("find_template is defined", callable(getattr(task_utility, "find_template", None)))
check("has a default confidence ladder",
      getattr(getattr(task_utility, "find_template", None), "__defaults__", None) is not None)

# nothing on screen will match this, so it must return None rather than raise
missing = os.path.join("task-solvers", "cv2-templates", "definitely_not_here.png")
try:
    got = task_utility.find_template(missing, region=(0, 0, 100, 100),
                                     confidences=(0.9, 0.8), verbose=False)
    check("a template that cannot exist returns None", got is None, repr(got))
except Exception as exc:
    check("a template that cannot exist returns None", False,
          f"it raised {type(exc).__name__}: {exc}")

print()
print("=== 5. find_template tries the lower rungs (the bug that ate 0.738) ===")
src = __import__("inspect").getsource(task_utility.find_template)
check("catches ImageNotFoundException", "ImageNotFoundException" in src)
check("loops over the confidence ladder", "for c in confidences" in src)
check("continues down the ladder on a miss", "continue" in src)
# the old code was: `for confidence in (...): pos = pyautogui.locateCenterOnScreen(...)`
# with no try/except, so the first rung raised and the rest were unreachable
fix_wiring = os.path.join("task-solvers", "Fix Wiring.py")
with open(fix_wiring, encoding="utf-8") as f:
    fw = f.read()
check("Fix Wiring no longer calls pyautogui.locateCenterOnScreen directly",
      "pyautogui.locateCenterOnScreen" not in fw)
check("Fix Wiring uses find_template", "find_template" in fw)
check("Fix Wiring has no bare confidence loop",
      "for confidence in (" not in fw)

print()
print("=== 6. solve_task reports a crashed solver instead of success ===")
solver_src = open("solver.py", encoding="utf-8").read()
check("checks the subprocess return code", "p.returncode" in solver_src)
check("returns a distinct failure code", "return 3" in solver_src)
check("no longer returns 0 unconditionally after the wait loop",
      solver_src.count("        if task_name == \"Inspect Sample\" or task_name == \"Reboot Wifi\":\n            return 2\n        else:\n            return 0") <= 1)

print()
print("=== 7. agent.do_task distinguishes a crashed solver from a completed one ===")
import agent  # noqa: E402
src = agent.__file__
with open(src, encoding="utf-8") as f:
    a = f.read()
check("handles rc == 3 as a crash", "rc == 3" in a)
check("says the task was not attempted successfully",
      "was not attempted successfully" in a)
check("still verifies the task actually went away",
      "still showing as" in a)

if failures:
    print()
    print("FAILURES:", ", ".join(failures))
    sys.exit(1)
print()
print("all checks passed: a failed template search is a reported failure, not a fake success")
