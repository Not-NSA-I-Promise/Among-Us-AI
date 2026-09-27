"""The decision loop. The model picks, this executes. Nothing decides on its own.

Read ARCHITECTURE.md first. The short version: this module is allowed to ask the
model what to do and then do exactly that one thing. It is not allowed to kill
because the cooldown looked ready, or vent because the role can, or sabotage
because lights were off. If the model says "wait", this waits.
"""
import time

import agent
import botlink
import llm
import utility

# How many `wait`s in a row before the model is told that idling looks like
# faking. Four is roughly long enough that "nothing is safe right now" is a real
# possibility, and short enough to catch the pattern in one round.
WAIT_STREAK_LIMIT = 4


class Agent:
    """Holds the short memory of what the model has already decided."""

    def __init__(self, history=8):
        self.history = []
        self.max_history = history
        self.last_action = None
        self.last_outcome = None
        self.model = None
        self._meeting_turns = 0
        self._consecutive_waits = 0

    # ------------------------------------------------------------------ prompt
    def system_prompt(self):
        try:
            role = __import__("botlink").get_role()
        except Exception:
            role = None
        return agent.tool_reference(role)

    def state_line(self):
        """One compact line describing the present."""
        try:
            return agent._brief_state()
        except Exception as exc:
            return f"state unavailable: {exc}"

    def situation(self):
        parts = [self.state_line()]
        if self.last_action:
            parts.append(f"last turn you chose: {self.last_action} -> {self.last_outcome}")
        if self.history:
            recent = "; ".join(h for h in self.history[-3:])
            parts.append(f"recent decisions: {recent}")
        if self._meeting_turns:
            parts.append(f"{self._meeting_turns} turns left in this meeting: "
                         "you still need to speak and vote")

        # Anti-idle. A run of `wait` is not neutral: to the rest of the lobby the
        # bot is standing in a room doing nothing, which is precisely what an
        # impostor faking a task looks like. The model is told this, and is given
        # the options it actually has, rather than being left to default to wait.
        if self._consecutive_waits >= WAIT_STREAK_LIMIT:
            useful = self._useful_actions()
            parts.append(
                f"You have chosen 'wait' {self._consecutive_waits} times in a row. "
                f"From outside this looks like you are faking a task, which is how "
                f"impostors give themselves away. Do something instead. "
                f"Right now you could: {', '.join(useful) if useful else 'go_to a room'}"
            )
        return " | ".join(parts)

    def _useful_actions(self):
        """What is actually available this turn, in words.

        Computed from live state, not guessed, so the nudge cannot suggest
        something illegal like venting as a Tracker.
        """
        out = []
        try:
            ab = botlink.read_ability()
            is_imp = ab.get("isimpostor") == "1"
        except Exception:
            return out

        if not agent._in_meeting():
            try:
                here = agent._tasks_here()
            except Exception:
                here = []
            if here and not is_imp:
                out.append(f"do_task {here[0]}")
            if is_imp:
                out.append("fake_task <something on your list>")
                if ab.get("cankill") == "1":
                    out.append("kill (if a kill is safe)")
            try:
                outstanding = __import__("roleplay").outstanding_tasks()
            except Exception:
                outstanding = []
            if outstanding and not here:
                out.append(f"go_to the room with {outstanding[0]}")
            if ab.get("canvent") == "1" and not ab.get("invent") == "1":
                out.append("vent (for movement)")
        return out

    # A meeting has a time limit. The model gets told how many turns are left so
    # it can budget speaking against voting, but it is still the model that
    # decides to speak and to vote - nothing here chooses for it.
    def _meeting_budget(self):
        """How many turns are left in the meeting, for budgeting speech vs vote.

        This read a 'meetingtime' key from read_ui_coords(), which only ever
        contains screen coordinates, so it always fell through to a guessed 20
        seconds. It now asks the plugin, which reads MeetingHud.discussionTimer.
        """
        try:
            if not agent._in_meeting():
                self._meeting_turns = 0
                return
            remaining = botlink.meeting_time_left()
            if remaining is None or remaining < 0:
                remaining = 20.0
            # one decision per ~2 seconds
            self._meeting_turns = max(0, int(remaining // 2) - 1)
        except Exception:
            self._meeting_turns = 0

    # -------------------------------------------------------------------- think
    def decide(self):
        """Ask the model for one action. Returns (name, args) or (None, raw)."""
        self._meeting_budget()
        messages = [
            {"role": "system", "content": self.system_prompt()},
            {"role": "user", "content":
                "Current situation: " + self.situation() +
                "\nWhat is your single next action? Reply with one line only."},
        ]
        try:
            reply = llm.ask(messages, num_predict=32, temperature=0.4)
        except Exception as exc:
            return None, f"<model error: {exc}>"
        if not reply:
            return None, "<model returned nothing>"
        return agent.parse_action(reply)

    # --------------------------------------------------------------------- act
    def step(self):
        """One full turn: ask, then do exactly one thing.

        Returns a short description of what happened, for the caller to log.
        """
        name, raw = self.decide()
        if name is None:
            # An unusable reply is NOT permission to improvise. Doing nothing is
            # the honest response to a confused model.
            self.last_action = None
            self.last_outcome = f"no valid action (said: {raw})"
            # A reply the parser could not read is not a decision, so it must not
            # count as a deliberate wait - but it also must not reset the streak,
            # because repeatedly saying something unparseable is the same problem.
            return self.last_outcome

        args = raw if isinstance(raw, list) else []
        try:
            outcome = agent.run_action(name, args)
        except agent.ActionError as exc:
            outcome = f"refused: {exc}"
        except botlink.CommandFailed as exc:
            outcome = f"game refused: {exc}"
        except Exception as exc:
            outcome = f"error: {type(exc).__name__}: {exc}"

        self.last_action = f"{name} {' '.join(args)}".strip()
        self.last_outcome = outcome
        if name == "wait":
            self._consecutive_waits += 1
        else:
            self._consecutive_waits = 0
        self.history.append(self.last_action)
        if len(self.history) > self.max_history:
            self.history.pop(0)
        return f"{self.last_action}  ->  {outcome}"


def botlink_error():
    """botlink.CommandFailed, resolved lazily so importing is safe."""
    try:
        import botlink
        return botlink.CommandFailed
    except Exception:
        return RuntimeError


def run_forever(interval=2.0, steps=None, on_step=None):
    """Drive the game by asking the model each turn.

    `interval` is the gap between decisions. It is not a frame rate: a local
    model round trip is the bottleneck, so this is one decision per interval,
    not per frame.
    """
    a = Agent()
    n = 0
    while steps is None or n < steps:
        line = a.step()
        if on_step:
            on_step(line)
        else:
            print(f"  {line}")
        n += 1
        if steps is None or n < steps:
            time.sleep(interval)
    return a
