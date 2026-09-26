"""The decision loop. The model picks, this executes. Nothing decides on its own.

Read ARCHITECTURE.md first. The short version: this module is allowed to ask the
model what to do and then do exactly that one thing. It is not allowed to kill
because the cooldown looked ready, or vent because the role can, or sabotage
because lights were off. If the model says "wait", this waits.
"""
import time

import agent
import llm


class Agent:
    """Holds the short memory of what the model has already decided."""

    def __init__(self, history=8):
        self.history = []
        self.max_history = history
        self.last_action = None
        self.last_outcome = None
        self.model = None

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
        return " | ".join(parts)

    # -------------------------------------------------------------------- think
    def decide(self):
        """Ask the model for one action. Returns (name, args) or (None, raw)."""
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
            return self.last_outcome

        args = raw if isinstance(raw, list) else []
        try:
            outcome = agent.run_action(name, args)
        except agent.ActionError as exc:
            outcome = f"refused: {exc}"
        except botlink_error() as exc:
            outcome = f"game refused: {exc}"
        except Exception as exc:
            outcome = f"error: {type(exc).__name__}: {exc}"

        self.last_action = f"{name} {' '.join(args)}".strip()
        self.last_outcome = outcome
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
