"""Check the detective/vitals/judge parsers against realistic plugin output."""
import _path  # noqa: F401  (puts the repo root on sys.path)
import os
import tempfile
import botlink

tmp = tempfile.mkdtemp()

detective = """#pages 2
page 0
victim Alice (RED)
location Electrical
preposition near impostor
impostor The Impostor
suspect Bob (BLUE) wasDead 0
suspect Carol (GREEN) wasDead 1
page 1
victim Dave (YELLOW)
location Cafeteria
preposition none
impostor unknown
suspect Bob (BLUE) wasDead 1
"""
scientist = """#panels 3
Alice (RED) ALIVE
Bob (BLUE) DEAD
Carol (GREEN) DISCONNECTED
"""
judge = """hasuse 1
used 0
blocked 0
"""

# redirect the module-level paths at the temp copies
botlink.DETECTIVE_PATH = os.path.join(tmp, "detectiveData.txt")
botlink.SCIENTIST_PATH = os.path.join(tmp, "scientistData.txt")
botlink.JUDGE_PATH = os.path.join(tmp, "judgeData.txt")
for name, body in (("detectiveData.txt", detective),
                   ("scientistData.txt", scientist),
                   ("judgeData.txt", judge)):
    with open(os.path.join(tmp, name), "w") as f:
        f.write(body)

print("=== detective pages ===")
for p in botlink.read_detective_notes():
    print(" ", p)
    for s in p["suspects"]:
        print("      suspect:", s)

print()
print("=== detective_report() ===")
import roleplay
roleplay.botlink = botlink
print(" ", roleplay.detective_report())

print()
print("=== scientist vitals ===")
for v in botlink.read_scientist_vitals():
    print(" ", v)

print()
print("=== judge state ===")
print(" ", botlink.read_judge_state())

print()
print("=== model chooser refuses junk ===")
real_ask = None
import llm


class FakeLLM:
    def ask(self, msgs, **kw):
        return "I think you should protect nobody in particular"


llm.ask = FakeLLM().ask
print("  reply 'protect nobody' ->", roleplay._ask_model_choose(
    "pick", "living: RED, BLUE", ["RED", "BLUE"]))


class ChattyLLM:
    def ask(self, msgs, **kw):
        return "BLUE is the one, definitely BLUE"


llm.ask = ChattyLLM().ask
print("  reply 'BLUE is the one' ->", roleplay._ask_model_choose(
    "pick", "living: RED, BLUE", ["RED", "BLUE"]))

print()
print("=== no double-reporting of the same body ===")
roleplay._SEEN_DETECTIVE_PAGES.clear()
print("  first call pages reported:", len(roleplay._unseen_pages(botlink.read_detective_notes())))
print("  second call pages reported:", len(roleplay._unseen_pages(botlink.read_detective_notes())))
