import _path  # noqa: F401  (puts the repo root on sys.path)
import agent

print("ACTIONS:", len(agent.ACTIONS))
for n in agent.action_names():
    print("  ", n)

print()
print("=== parse tests ===")
cases = [
    "go_to Electrical",
    "kill",
    "sabotage lights",
    "wait",
    "ability2",
    "vote skip",
    "action: go_to Reactor",
    "`mimic RED`",
    "go_to",                  # missing required arg -> must be rejected
    "teleport to hell",       # not in the table -> must be rejected
    "wait\nkill",             # only the first line counts
    "",                       # empty -> no action
    "ability2",               # legal name, but the role check is at run time
]
for c in cases:
    print("  {!r:34} -> {}".format(c, agent.parse_action(c)))
