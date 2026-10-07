---
name: context_load
description: Session startup, reads F6, engagement timeline, daily handoff, and task tracker. Run this first every session.
---

# Context Load

Run this at the start of every Claude Code session to orient yourself.

## Steps

1. Read `CLAUDE.md` for workspace rules and operating context.
2. Read all documents in `01_Foundations/`, scan each subfolder for completed F6 docs (ignore empty `_workspace.md` templates).
3. Read `04_Customer_Journey/engagement_timeline.md`, current phase, schedule, standing meetings.
4. Read `04_Customer_Journey/task_tracker.md`, what's active, blocked, and up next.
5. Read the most recent entry in `06_Communication/daily_handoff.md`, last VA update.
6. Check `02_Deliverables/_review_queue/` for any files awaiting review.
7. Read `06_Communication/decisions_log.md`, last 5 entries for recent context.

## Output

Produce a **Session Brief** in this format:

```
SESSION LOADED, [Client Name] workspace

Current phase: [phase from engagement_timeline]
F6 status: [X/6 complete, list which are done]

Active tasks: [count from task tracker]
Blocked: [count + brief description of what's blocked]
Review queue: [count of files in _review_queue]

Last VA handoff: [date + 1-line summary]
Last decision: [most recent from decisions_log]

Suggested starting point: [your recommendation based on what's most urgent]
```

## Rules

- If F6 docs are empty templates, say "Not yet completed", don't guess.
- If handoff or task tracker is empty, note it, "No handoff entries yet."
- Keep the brief under 15 lines. Signal over noise.
