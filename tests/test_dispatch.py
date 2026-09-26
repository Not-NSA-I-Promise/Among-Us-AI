import _path  # noqa: F401  (puts the repo root on sys.path)
"""Verify the harness command parser routes keys and arguments correctly."""
import builtins
import test_commands as t

calls = []


def stub_factory(label):
    def f(pre=None):
        calls.append((label, pre))
    return f


# stub every handler so nothing touches the game
t.MENU = [
    ("sb", "", stub_factory("sb")),
    ("b", "", stub_factory("b")),
    ("vt", "", stub_factory("vt")),
    ("s", "", lambda: calls.append(("s", None))),
    ("7", "", lambda: calls.append(("7", None))),
]

seq = iter(["sb Electrical", "b lights", "vt 4", "sb", "b", "s", "q"])
builtins.input = lambda *a, **k: next(seq)
t.show_state = lambda: None

# copy of the real dispatch loop from main()
for raw in iter(lambda: next(seq, None), None):
    parts = raw.split(None, 1)
    choice = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else None
    for key, _l, fn in t.MENU:
        if choice == key:
            if arg and fn.__code__.co_argcount:
                fn(arg)
            else:
                fn()
            break

print("routed calls:")
for label, arg in calls:
    print("  {:<3} arg={!r}".format(label, arg))
