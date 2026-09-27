"""`wait` needs a real cooldown, not a request.

The model was spamming `wait` with no reason, and the fix at the time was to
count the waits and tell it off in the prompt once it had already done it four
times. That cannot work: `wait` is the one action that always looks available
and always looks harmless, so it wins whenever the model is unsure - and it was
reaching for it long before any limit fired.

So `wait` is now on a timer, and while the timer runs the action is removed from
the model's tool list entirely. If the model replies with the word anyway, it is
refused, because a refusal costs it the turn just as much as the wait would have.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

import agent   # noqa: E402

fails = []


def check(name, cond, detail=""):
    if cond:
        print("  PASS", name)
    else:
        print("  FAIL", name, "<-", detail)
        fails.append(name)


NEEDLE = "wait - deliberately"

print()
print("=== `wait` starts available ===")
agent.reset_for_new_round()
check("wait is in the tool list", "wait" in agent.action_names(available_only=True))
check("and appears in the prompt", NEEDLE in agent.tool_reference("Impostor"))
check("there is no cooldown running", agent._wait_cooldown_left() == 0)

print()
print("=== using it removes it from the tool list ===")
agent.run_action("wait", [])
check("wait is gone from the offered actions",
      "wait" not in agent.action_names(available_only=True))
ref = agent.tool_reference("Impostor")
check("and gone from the model prompt", NEEDLE not in ref)
check("the cooldown is running", agent._wait_cooldown_left() > 170,
      agent._wait_cooldown_left())
check("it is a three minute cooldown", agent.WAIT_COOLDOWN_SECONDS == 180.0)

print()
print("=== every OTHER action is untouched ===")
offered = set(agent.action_names(available_only=True))
expected = set(agent.ACTIONS) - {"wait"}
check("only wait is removed", offered == expected,
      sorted(expected.symmetric_difference(offered)))
check("19 of 20 actions are still offered", len(offered) == 19, len(offered))

print()
print("=== the prompt does not advertise a disabled action ===")
lines = [ln for ln in ref.splitlines() if "wait" in ln.lower()]
print("     the only lines mentioning it:")
for ln in lines:
    print("      >", ln[:150])
check("the closing line does not offer wait as a fallback",
      not any(ln.strip().startswith('If nothing is safe') and '"wait"' in ln
              for ln in lines), lines)
check("but it is told wait is closed, with a time",
      any("not an option" in ln for ln in lines), lines)
check("and a real time is given", any("180s" in ln for ln in lines), lines)

print()
print("=== replying with the word anyway is refused, not obeyed ===")
try:
    agent.run_action("wait", [])
    check("a second wait is refused", False, "it was allowed")
except agent.ActionError as exc:
    check("a second wait is refused", True)
    check("and it says why", "already waited" in str(exc), exc)
    check("and it pushes for a real action",
          "move somewhere" in str(exc) or "fake a task" in str(exc), exc)

print()
print("=== every other action still works during the cooldown ===")
called = []
agent.ACTIONS["observe"] = (("what",),
                            lambda *a: called.append(a) or "observed", "obs")
try:
    agent.run_action("observe", ["state"])
    check("another action is unaffected", called == [("state",)], called)
    check("and it did not clear the cooldown", agent._wait_cooldown_left() > 170)
finally:
    _args, _fn, _desc = agent.ACTIONS["observe"]
    del agent.ACTIONS["observe"]
agent.ACTIONS["observe"] = (
    ("what",), agent.observe, "observe <what> - gather information")

print()
print("=== a new round clears it ===")
agent._FAKED_ONCE.add("Download Data")
agent.reset_for_new_round()
check("wait is available again", "wait" in agent.action_names(available_only=True))
check("and the cooldown is gone", agent._wait_cooldown_left() == 0)
check("and the faked-once list is cleared, which it never was before",
      agent.faked_tasks() == [], agent.faked_tasks())

print()
if fails:
    print("FAILURES:", ", ".join(fails))
    raise SystemExit(1)
print("all checks passed: wait is a real cooldown, and a hidden option")
