"""Prove the model is actually told what is happening.

The reported bug was that the harness gives the model nothing: it cannot tell it
a meeting is running, it never shows the chat, and `say` did not exist. All three
are invisible from a code read, so they are asserted here against a faked game.
"""
import _path  # noqa: F401
import os
import sys

import agent
import agent_loop
import botlink
import utility

failures = []


def check(label, cond, detail=""):
    print("  {} {}{}".format("PASS" if cond else "FAIL", label,
                             ("  <- " + str(detail)) if (detail and not cond) else ""))
    if not cond:
        failures.append(label)


def fake_game(in_meeting, chat, in_vent=False, dead=False, imp=False, cooldown=None):
    def getGameData():
        return {"map_id": "Skeld", "room": "Cafeteria", "color": "RED",
                "inMeeting": in_meeting, "playersDead": {"RED": dead, "BLUE": False},
                "tasks": [], "task_locations": [], "position": (0, 0),
                "lights": "0", "nearbyPlayers": []}
    utility.getGameData = getGameData
    utility.is_urgent_task = lambda *a, **k: None
    utility.get_chat_messages = lambda: list(chat)
    utility.in_meeting = lambda: in_meeting
    botlink.get_role = lambda: "Impostor" if imp else "Crewmate"
    botlink.read_ability = lambda: {"invent": "1" if in_vent else "0",
                                    "isdead": "1" if dead else "0",
                                    "isimpostor": "1" if imp else "0",
                                    "cankill": "1", "abilitycount": "0"}
    botlink.get_chat_messages = lambda: list(chat)


print("=== 1. a meeting is reported, whether inMeeting is a bool or the string '1' ===")
for value, label in ((True, "python bool True"), ("1", "the string '1'")):
    fake_game(value, [])
    check(f"meeting detected when inMeeting is {label}", agent._in_meeting() is True)
fake_game(False, [])
check("no meeting reported when inMeeting is False", agent._in_meeting() is False)

print()
print("=== 2. the chat transcript reaches the state line ===")
fake_game(True, ["BLUE: red is sus", "GREEN: i was in elec the whole time",
                 "PINK: who was near the body"])
state = agent._brief_state()
check("state mentions the meeting", "MEETING IS RUNNING" in state, state)
check("state contains BLUE's message", "red is sus" in state, state)
check("state contains GREEN's message", "elec" in state, state)
check("state contains PINK's message", "who was near" in state, state)

print()
print("=== 3. no chat means no empty noise, and no crash ===")
fake_game(True, [])
state = agent._brief_state()
check("empty chat does not add junk", "what everyone has said" not in state, state)
fake_game(True, None)
check("chat=None does not crash", isinstance(agent._brief_state(), str))

print()
print("=== 4. the model is restricted during a meeting, and told so ===")
legal = agent._valid_actions_now() if hasattr(agent, "_valid_actions_now") else None
if legal is None:
    # the table itself has no notion of a meeting, so assert the prompt instead
    fake_game(True, [])
    state = agent._brief_state()
    check("prompt says only say/observe/vote are possible",
          "you can only say, observe and vote" in state, state)
else:
    check("kill is not offered in a meeting", "kill" not in legal, legal)

print()
print("=== 5. venting and death are reported ===")
fake_game(False, [], in_vent=True)
check("in-vent is reported", "inside a vent" in agent._brief_state())
fake_game(False, [], dead=True)
check("death is reported", "you are dead" in agent._brief_state())

print()
print("=== 6. say() no longer calls the function that never existed ===")
import inspect
import ast


def code_only(fn):
    """Source with docstrings and comments removed.

    The fixes are all *described* in docstrings, so a naive substring check finds
    the old name in the explanation of why it went. Only executable code counts.
    """
    src = inspect.getsource(fn)
    tree = ast.parse(src.lstrip() if not src.startswith((" ", "\t")) else
                     "def _f():\n" + "\n".join(" " + l for l in src.splitlines()))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
                             ast.Module)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and \
                    isinstance(body[0].value, ast.Constant) and \
                    isinstance(body[0].value.value, str):
                node.body = body[1:] or [ast.Pass()]
    return ast.unparse(ast.fix_missing_locations(tree))


say_code = code_only(agent.ACTIONS["say"][1])
check("say() does not call chatGPT", "chatGPT" not in say_code, say_code)
check("say() goes through botlink", "botlink.say" in say_code, say_code)
check("botlink.say sends the 'say' command",
      "send_cmd('say '" in code_only(botlink.say)
      or 'send_cmd("say "' in code_only(botlink.say),
      code_only(botlink.say))

print()
print("=== 7. the meeting clock is read from the plugin, not from ui coords ===")
budget_code = code_only(agent_loop.Agent._meeting_budget)
check("uses botlink.meeting_time_left",
      "meeting_time_left" in budget_code, budget_code)
check("no longer reads a ui coords meetingtime",
      "read_ui_coords" not in budget_code, budget_code)

print()
print("=== 8. a real decision prompt contains the chat ===")
captured = {}


def fake_ask(messages, **kw):
    captured["messages"] = messages
    return "vote BLUE"


llm = sys.modules.get("llm")
llm.ask = fake_ask
fake_game(True, ["BLUE: red vented in elec", "GREEN: thats sus"])
a = agent_loop.Agent()
name, arg = a.decide()
user_text = captured["messages"][-1]["content"]
check("the situation line the model receives contains the chat",
      "red vented in elec" in user_text, user_text)
check("the situation line states the meeting", "MEETING IS RUNNING" in user_text,
      user_text)
print()
print("  --- what the model actually receives ---")
for line in user_text.splitlines():
    print("   ", line[:150])

if failures:
    print()
    print("FAILURES:", ", ".join(failures))
    sys.exit(1)
print()
print("all checks passed: the model is told the meeting state, the chat, and can speak")
