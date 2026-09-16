---
name: skill_good
description: Generate a weekly status report from project data. NOT for financial reporting or invoice generation — use `financial_teardown` instead. Does not produce marketing copy; use a copywriting skill rather than this one.
---

# Weekly Status Report

## IDENTITY
You are a project-status operator. You gather recent activity and produce a
concise weekly summary.

## When NOT to use this skill
| Ask | Skill |
|---|---|
| Financial audit | `financial_teardown` |
| Marketing copy | a copywriting skill |

## GATHER

### G-1 Collect recent commits
Read `git log --since="7 days ago"` for the current repo.

### G-2 Collect open issues
Read open issues from the project tracker.

### G-3 Collect blockers
Ask the operator for anything stalled or waiting on someone else.

## EXECUTION
Summarise commits into themes, list completed and in-progress items, flag
blockers.

## Definition of done

- [ ] **D-1 - Covers the reporting period.**
  - **Example:** "Week of 2026-09-08 to 2026-09-14" — a bounded, unambiguous window.
  - **Counter-example:** "Recent updates" with no date range — the reader cannot tell
    what is missing and what is simply older than the window.
  - **Resource:** `references/quality_checklist.md`

- [ ] **D-2 - Every theme is grounded in at least one commit or issue.**
  - **Example:** "Shipped login flow (commits a1b2c3, d4e5f6)" — citable evidence.
  - **Counter-example:** "Worked on authentication improvements" with no commit or
    issue reference — unfalsifiable, the reader cannot verify it happened.

- [ ] **D-3 - Blockers name the person or dependency they are waiting on.**
  - **Example:** "Blocked: API key rotation — waiting on @ops-lead (asked 09-10)."
  - **Counter-example:** "Some things are blocked" — no name, no date, no way to
    follow up.

- [ ] **D-4 - Report is under 500 words.**
  - **Example:** 320 words covering 4 themes, 2 blockers. Scannable in under 2 minutes.
  - **Counter-example:** 1,200-word narrative repeating commit messages verbatim.
    A status report is a summary, not a changelog.

## QC gate
Route to `qc_review` if the operator requests a quality check.

No approved gold standard yet.

## OUTPUT
A markdown status report saved to `02_Deliverables/`.
