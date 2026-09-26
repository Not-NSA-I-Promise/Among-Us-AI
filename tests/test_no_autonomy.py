import _path  # noqa: F401  (puts the repo root on sys.path)
"""Prove the harness cannot act on its own.

Fakes the model and the game. The point is that every game action must be
traceable to a model reply: if the loop acts without being asked, this fails.
"""
import sys
import types

import agent
import agent_loop

executed = []


def install_fake_model(reply):
    import llm
    calls = []

    def ask(messages, **kw):
        calls.append(messages)
        return reply

    llm.ask = ask
    return calls


def install_fake_game():
    """Replace every action with a recorder, so we can see what was called."""
    for name, (args, fn, desc) in agent.ACTIONS.items():
        def make(n, a):
            def stub(*vals):
                executed.append((n, list(vals)))
                return f"{n} done"
            return stub
        agent.ACTIONS[name] = (args, make(name, args), desc)


# keep a handle on the real ability2 so test 7 exercises its guard
real_ability2 = agent.ACTIONS["ability2"][1]


failures = []


def check(label, cond):
    print("  {} {}".format("PASS" if cond else "FAIL", label))
    if not cond:
        failures.append(label)


print("=== 1. model says 'go_to Electrical' -> only go_to runs ===")
executed.clear()
install_fake_game()
install_fake_model("go_to Electrical")
a = agent_loop.Agent()
a.step()
check("exactly one action ran", len(executed) == 1)
check("it was go_to with Electrical", executed == [("go_to", ["Electrical"])])

print()
print("=== 2. model says 'kill' -> only kill runs, no follow-on sabotage ===")
executed.clear()
install_fake_model("kill")
a = agent_loop.Agent()
a.step()
check("exactly one action ran", len(executed) == 1)
check("it was kill", executed == [("kill", [])])

print()
print("=== 3. model says 'wait' -> no GAME action runs ===")
executed.clear()
real_wait = agent.ACTIONS["wait"][1]
agent.ACTIONS["wait"] = ((), lambda: "did nothing, deliberately", "wait")
install_fake_model("wait")
a = agent_loop.Agent()
out = a.step()
check("no real game action ran", executed == [])
check("reported doing nothing", "deliberately" in out or "wait" in out)

print()
print("=== 4. model invents a verb -> NOTHING runs ===")
executed.clear()
install_fake_model("sudo destroy the reactor")
a = agent_loop.Agent()
out = a.step()
check("no game action ran", executed == [])
check("reported the bad reply", "no valid action" in out)

print()
print("=== 5. model is silent -> NOTHING runs ===")
executed.clear()
install_fake_model("")
a = agent_loop.Agent()
out = a.step()
check("no game action ran", executed == [])
check("reported empty reply", "nothing" in out)

print()
print("=== 6. model errors out -> NOTHING runs, no crash ===")
executed.clear()
import llm


def boom(messages, **kw):
    raise RuntimeError("ollama down")


llm.ask = boom
a = agent_loop.Agent()
out = a.step()
check("no game action ran", executed == [])
check("reported the error", "model error" in out)

print()
print("=== 7. illegal action is refused, not forced ===")
executed.clear()
install_fake_model("ability2")
# restore the REAL ability2 so its guard is what runs, not a stub
agent.ACTIONS["ability2"] = ((), real_ability2, "ability2")
# give a role with no second ability
import roleplay
roleplay.my_abilities = lambda role=None, live_count=None: ["only one ability"]
a = agent_loop.Agent()
out = a.step()
check("refused rather than used", "refused" in out)
check("said why", "not 2" in out or "ability" in out)

print()
print("=== 8. the model is asked, with the tool table in the system prompt ===")
calls = install_fake_model("wait")
a = agent_loop.Agent()
a.step()
sysmsg = calls[0][0]["content"] if calls else ""
check("system prompt lists the actions", "go_to" in sysmsg and "sabotage" in sysmsg)
check("system prompt states ability count rules", "No role in this game has more than 2" in sysmsg)
check("system prompt offers wait", "wait" in sysmsg)

print()
if failures:
    print("FAILURES:")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("all checks passed")
