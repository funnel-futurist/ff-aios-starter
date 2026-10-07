# 08_Automations

Your scheduled + triggered work, the stuff that runs without you.

This is where **operations** (the supporting layer of your business) get repeatable: scheduled tasks, recurring reports, follow-up sequences, anything you've handed to an automation instead of doing by hand.

## What lives here
- Scheduled-task definitions and notes (what runs, when, why).
- Reporting/follow-up automations (e.g. a Slack intelligence layer like Viktor, if you add one).
- Runbooks for each automation: what it does, what it touches, how to pause it.

## Guardrails (same as everywhere)
- **Keep asset *creation* in Claude Code** (your judgment). Use automations for *reporting + follow-up + routine ops*, the repeatable stuff.
- **Spend limits + scoped keys.** Any automation that calls a paid API uses a named, capped key in `.env`. Contain the blast radius (airlocks).
- **Reversible.** An automation should be easy to pause and easy to read. If you can't explain what it does in a sentence, simplify it.

Start empty. Add automations only once a task is repeatable *and* worth not doing by hand. Elimination > addition.
