---
name: dashboard
description: Quick status brief, what's active, what's blocked, what needs attention. No input needed.
---

# Dashboard

A quick-glance status of your workspace. Run anytime you want to know where things stand.

## Steps

1. Read `04_Customer_Journey/task_tracker.md`, count active, blocked, in-review, up-next tasks.
2. Read `02_Deliverables/_review_queue/`, list any files waiting for review with their names and a 1-line description of what they are.
3. Read latest entry in `06_Communication/daily_handoff.md`, summarize in 1 line.
4. Read `04_Customer_Journey/success_metrics.md`, pull current KPI values if populated.
5. Read `04_Customer_Journey/engagement_timeline.md`, check for upcoming deadlines within 7 days.

## Output

```
DASHBOARD, [date]

TASKS: [X active] / [X blocked] / [X in review] / [X up next]
[List blocked tasks with reason if available]

REVIEW QUEUE: [X files]
[List each file with 1-line description]

UPCOMING (next 7 days):
[Any deadlines from engagement_timeline]

LAST HANDOFF ([date]):
[1-line summary]
```

## Rules

- No input required, run it and get the brief.
- If sections are empty, say "Nothing here yet", don't pad with filler.
- Highlight anything that looks overdue or stale (tasks unchanged for 3+ days).
