---
name: review-queue
description: The reviewer's live merge/review queue. Use when the repo owner / lead / code-owner wants to see "what needs me right now" across all open PRs — what's ready to merge, what's waiting on their review, what's blocked or going stale. Triggers on "review queue", "what needs my review", "what can I merge", "my PR queue", "what's waiting on me", "anything to merge". Reads live from GitHub (the single source of truth — never a stale list), buckets everything in plain English, and offers to open or merge with explicit confirmation. Pairs with /wrap-up (which feeds it).
---

# /review-queue — what needs you, right now

You are triaging open PRs for the person who reviews and merges. **Read live from GitHub — never invent or save a queue.** If it's not an open PR, it's not in the queue. Present it plainly and let them act fast.

## Step 1 — Pull the live queue
```bash
gh pr list --state open --limit 100 --json number,title,author,reviewDecision,mergeable,isDraft,createdAt,labels,headRefName,statusCheckRollup
```

## Step 2 — Bucket every PR (exactly one bucket each)
- **✅ Ready to merge** — not a draft, all checks green (every `statusCheckRollup` conclusion is SUCCESS, or there are no checks), and not blocked by a pending code-owner review. These just need a click.
- **👀 Needs YOUR review** — review is requested from you, or it touches a code-owned path (per `.github/CODEOWNERS`) so it can't merge without you. Surface these first — only you can unblock them.
- **⛔ Blocked** — checks failing, marked draft, or `reviewDecision = CHANGES_REQUESTED`. Note who owns the next step.
- **🕰️ Going stale** — open more than ~5 days with no movement. Flag for a nudge or a close.

## Step 3 — Show it plainly (what only you can unblock, first)
```
REVIEW QUEUE — {N} open PRs

👀 Needs you ({n})
  #{num} {title} — {author}  (touches: {owned path})
✅ Ready to merge ({n})
  #{num} {title} — {author}
⛔ Blocked ({n})
  #{num} {title} — {why} (owner: {who})
🕰️ Stale ({n})
  #{num} {title} — {days}d idle  → who acts next: {author/reviewer}
```
**Every line names who acts next** — for Blocked/Stale say whose move it is (the author fixes / the reviewer reviews), so nothing sits in limbo because each side thinks it's the other's turn.

## Step 4 — Offer action (with explicit confirmation)
- **Ready to merge** → offer to merge. Only on an explicit "yes":
  ```bash
  gh pr merge {num} --squash --delete-branch
  ```
- **Needs you** → offer to open the PR, show the diff, or surface any reviewer verdict so you can decide, then approve.
- **Stale** → offer to post a gentle nudge to the owner (a one-line comment naming what it needs), or to close it if it's dead. Don't let it keep rotting silently.
- **Never** merge without an explicit confirmation. **Never** merge a Blocked or Needs-you PR on someone's behalf.

## Always
- Read-only until the reviewer says "merge."
- Lead with signal: the PRs only the reviewer can unblock come first.
- If `gh` isn't authenticated, say so plainly and stop — don't guess at the queue.
