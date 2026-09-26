# Sources for the task durations in task_durations.json

These are community-measured figures, not values read out of the game. The game
does not publish them; players who "bust" fakes time them, and that is where
these come from.

Used here so the bot's fake takes roughly as long as a real task, because
returning from a panel faster than a crewmate can is the single most common way
an impostor gets caught doing nothing.

## Figures used

**Download Data / Upload Data — 8-10s**
> "Click Download/Upload and wait for about 8.5 seconds."
> — gameplay.tips, *Among Us – Tasks and Sabotages Guide*
> "Download/ upload tasks take exactly 8 seconds, so if someone is there for less
> than that, they're faking."
> — Indie Game Culture, *Among Us Tasks Guide*
> "Each download will take just under 10 seconds."
> — TheGamer, *The Skeld Task Guide*
> Anecdotal spread reported in r/AmongUs: "I got accused of being imp when I
> wasn't because ... it took me 15sec to download data instead of 9" — so a real
> player can overrun the timer, which is why this is a range.

**Submit Scan (MedBay) — 10s, visual**
> "Step on the scanner in MedBay and wait for a holographic indicator to pass
> over your character's body. This process takes about 10 seconds. As this is a
> visual task, it's a good way to confirm whether players are Crewmates."
> — TheGamer, *The Skeld Task Guide*
> "Submit Scan – Visual, 1 Part Task, Medbay. Let it scan yourself for 10 seconds."
> — gameplay.tips

**Start Reactor — 15s+, visual**
> "Start Reactor takes a minimum of 15 seconds."
> — Indie Game Culture, *Among Us Tasks Guide*
> Listed as a long task, one of the easiest to fake precisely because real times
> vary greatly — which is also why a fixed-length fake is unreliable.
> — ScreenRant, *How Long Tasks Take to Complete (For The Sneaky Imposter)*

**Inspect Sample — ~60s**
> "Step away for a full minute. After the minute is over, interact with the
> machine and press the green button beneath the red anomaly sample."
> — TheGamer. "You can exit out and the timer will still count down."
> — gameplay.tips

**Fuel Engines — 6s per stage**
> "Fuel Engines takes 6 seconds."
> — Indie Game Culture
> Four separate stages, each in a different room, so the total is much longer
> than 6s but no single wait is.

**Swipe Card — 4-7s, very variable**
> "This can take about three to five seconds to complete." — ScreenRant
> "admin swipe: 4 to 7 seconds" — r/AmongUs task timing thread
> "I got accused of being imp when I wasn't because I couldn't get the card to
> swipe" — same thread. Wide variance is the point: a 3s swipe reads as fake.

**Common / short tasks — 3-5s**
> "Essentially, common tasks will take three to five seconds to complete.
> Remember: if a crewmate is watching, wait until the task bar increases before
> leaving the spot."
> — ScreenRant

**Fix Wiring — ~3s per panel**
> "Standing at the panel and doing the task probably takes about three seconds
> per panel. If faking this task, ensure that the task meter goes up before
> leaving the panel."
> — ScreenRant

**Task-type classification (common / short / long)**
> Among Us Wiki, *Tasks*: short tasks "require only a single stage and take very
> little time"; long tasks "have multiple stages, or force the player to spend a
> long time, such as Start Reactor". Common tasks go to every player, so faking
> one you do not have is a guaranteed tell.
> — among-us.fandom.com/wiki/Tasks

## Uncertainties

- The figures were measured on **mobile** (the r/AmongUs cheatsheet says so
  explicitly) and on Skeld-era builds. PC and console players are typically
  faster, and later tasks have been rebalanced.
- Nothing here is verified against the 2026.8.18 build. The ranges are
  deliberately wide for that reason.
- A bot that hits the *midpoint* every single time is itself a tell, so
  `fake_task` samples within the range rather than picking one value.

## How to improve this

The honest way to get exact numbers for the current build is to measure them:
stand at each panel as a crewmate with a stopwatch, or instrument the game's own
minigame. Until then these are community estimates and `fake_task` treats them
as such.
