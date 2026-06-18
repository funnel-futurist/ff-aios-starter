---
name: wrap-up
description: The safe end-of-session closeout + handoff ritual. Use when finishing work, ending the day/session, or when the user says "wrap up", "wrap-up", "end my day", "close out", "I'm done", "save my work", or asks how to safely commit/push/PR and update the team. Runs a forced world-class self-review (auto-fixing only safe issues) BEFORE pushing, then commits cleanly, pushes the branch, opens/updates the PR, and writes a plain-English team update — so work is never stranded on a laptop and every PR is already best-practice before review. Pairs with /start-my-day.
---

# /wrap-up — the safe closeout + handoff

Calm, plain-English, one step at a time. Protect the operator's work **and** the team's time.

## Step 0 — Read the situation
```bash
bash scripts/team/git-safety-check.sh
```
If `ON_MAIN=true`: **STOP.** We never commit on `main`. Help them move their changes onto a branch first (`git checkout -b <operator>/<topic>-<date>` carries the uncommitted changes along), then continue.

## Step 1 — See what changed
```bash
git status
git diff --stat
```
Summarize, in plain English, what they actually changed.

## Step 2 — Clear out the junk (don't commit garbage)
Flag and remove (quick confirm) anything that shouldn't be committed: logs, `__pycache__`, `.DS_Store`, build artifacts, scratch files — and **anything that looks like a secret** (keys, tokens, connection strings, `.env`). If you spot a likely secret, **STOP and warn loudly. Never commit it.**

## Step 3 — 🔒 FORCED self-review (act as a world-class engineer / GitHub reviewer)
**This step is NOT optional.** Review the full diff like a senior reviewer would, then:
- **Auto-fix ONLY the safe set** (apply directly): formatting, lint, obvious typos, removing generated junk, small consistency fixes.
- **NEVER auto-change the judgment set — surface it for the operator's approval instead:** strategy/docs content, offer logic, client-facing claims, large deletions, and anything governance — `.github/`, `CODEOWNERS`, `.claude/hooks`, `.claude/settings.json`, workflows, migrations, `.env`/secrets. *(If a human owns it in `CODEOWNERS`, you do not silently change it.)*
- Sanity-check against your repo's standards: `CLAUDE.md` and any naming / voice / framework guides it points to.
Tell the operator what you fixed and what needs their call. **Goal: the PR is already best-practice before it ever goes to review.**

## Step 4 — One clean commit
Stage the intended files (not junk) and write a clear conventional message — `type(scope): what changed and why` (e.g. `docs(offer): tighten the guarantee section`):
```bash
git add <intended paths>
git commit -m "<message>"
```

## Step 5 — Push YOUR branch (never main)
```bash
git push -u origin HEAD
```
(If your repo protects `main`, a direct push is rejected. You only ever push your own branch.)

## Step 6 — Open or update the PR
- No PR yet for this branch → create one, filling the template:
  ```bash
  gh pr create --fill --base main
  ```
- PR already exists → it updates automatically on push.
Share the PR URL. If your repo has the AI PR reviewer, it checks the PR automatically; otherwise a maintainer reviews it. Anything touching an owned / governance path waits for a code-owner (**[PRIMARY_REVIEWER]**).

## Step 7 — Plain-English team update (protect everyone's time)
Run the **`/changelog`** skill (or use its plain-English style) to produce a closeout a founder can read in 10 seconds — no jargon, no file paths unless needed:
```
✅ ‹Operator› — end of session
Completed: ‹plain English›
In progress: ‹plain English›
Blocked / needs review: ‹or "none"›
PR: ‹url›
Next step: ‹one line›
```

## Step 8 — Catch invisible work
If `git status` still shows uncommitted or unpushed changes, say so plainly: *"You still have work that exists only on this laptop — want me to commit + push it so it's safe and the team can see it?"* **Don't end the session with work stranded.**

## Always
- Never force-push, hard-reset, or delete branches. Never commit secrets.
- If a fix is a judgment call, **ask** — don't decide for them.
