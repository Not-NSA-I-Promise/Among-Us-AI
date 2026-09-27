# When you are unsure: research, then ask

This rule exists because I got it wrong once, in a way that cost a live round.

I had **Chart Course** and **Start Reactor** on the visual-task list. Neither is
visual. The bot therefore refused to fake two perfectly safe tasks, and the
error was baked into a training dataset and a JSON file, where it would have
been reinforced. The user had to catch it by playing the game.

**The rule**

1. If a fact about Among Us is not in `KNOWLEDGE_BASE.md`, and the decision
   depends on it, **research it** before acting. Web search the wiki, the task
   guides, community timing threads.
2. If research does not settle it, **ask the user**. They play the game. A
   one-line question costs less than a broken round.
3. Write what you learn into `KNOWLEDGE_BASE.md` with a source and a confidence
   level, so the next agent does not repeat the mistake.
4. Never let an unverified assumption reach a dataset, a data file, or a prompt
   that steers the model's behaviour. Those are worse than a bug, because they
   get reinforced instead of crashing.

**What counts as "not sure"**

- A task property: visual, common, multi-stage, dummy, or its duration
- A room name, a vent network, or which map something is on
- A role's abilities, and what they actually do
- Whether a game API call does what its name suggests
- Anything you are recalling from training data rather than from the dump, the
  wiki, or the user's own reports

**What does not count**

- Anything in `KNOWLEDGE_BASE.md` with a source
- Anything in the IL2CPP dump or the task database in this repo
- Anything the user has told you directly

**Cheap check before you commit**

If a change adds or changes a factual claim about the game, and that claim is
not already in the knowledge base with a source, stop and research it. This has
caught: a wrong visual-task list, a wrong task duration, and a wrong claim about
which rooms have vents. All three would have been written into training data.

**When the model needs a fact at runtime**

Prefer deriving it from the game over hardcoding it. The task bar, the vitals,
who vented, what the room is — those are all published. A hardcoded fact goes
stale on the next patch; the plugin's data does not.
