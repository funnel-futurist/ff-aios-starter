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
If `GH_USER=unknown`: GitHub isn't connected — the push/PR steps will fail. Do Steps 1–4 (so their work is at least committed locally and safe), then hand the fix before Step 5: *"run `gh auth login` (GitHub.com → HTTPS → browser), then we'll push."*

## Step 1 — See what changed
```bash
git status
git diff --stat
```
Summarize, in plain English, what they actually changed.

## Step 2 — Clear out the junk (don't commit garbage)
Flag and remove (quick confirm) anything that shouldn't be committed: logs, `__pycache__`, `.DS_Store`, build artifacts, scratch files — and **anything that looks like a secret** (keys, tokens, connection strings, `.env`).
**If you spot a likely secret, STOP and walk them through removing it — don't just warn:**
1. Take it out of the file (replace with a placeholder or move it to `.env`, which is git-ignored).
2. If the secret's file should never be tracked, add it to `.gitignore`.
3. If it was already **committed earlier** on this branch, tell them plainly the key must be **rotated/regenerated** (treat it as exposed), and ask a senior person for help — don't attempt history rewrites yourself.
4. Re-run `/wrap-up` once it's clean. Do not commit until the secret is gone.

## Step 3 — 🔒 Self-review (always run it — act as a world-class engineer / GitHub reviewer)
Run this every time — it's how you ship clean work. (Honest about what it is: a strong built-in habit, not a hard technical gate — if your repo has an AI PR reviewer or a maintainer, that's the real gate. Review against the same bar they'll use so nothing you pass here gets bounced there.) Review the full diff like a senior reviewer would, then:
- **Auto-fix ONLY the safe set** (apply directly): formatting, lint, obvious typos, removing generated junk, small consistency fixes.
- **NEVER auto-change the judgment set — surface it for the operator's approval instead:** strategy/docs content, offer logic, client-facing claims, large deletions, and anything governance — `.github/`, `CODEOWNERS`, `.claude/hooks`, `.claude/settings.json`, workflows, migrations, `.env`/secrets. *(If a human owns it in `CODEOWNERS`, you do not silently change it.)*
- Sanity-check against your repo's standards: `CLAUDE.md` and any naming / voice / framework guides it points to.
- **Documentation check:** if this change adds or edits a skill, hook, or process step, confirm it's documented where people will actually find it — the skill's own description, `README`/`CONTRIBUTING`, and (if it changes how the team works) the onboarding wizard. If it isn't, add it before opening the PR. *A new step nobody knows about doesn't exist.*
Tell the operator what you fixed and what needs their call. **Goal: the PR is already best-practice before it ever goes to review.**

## Step 4 — One clean commit (you write the message, not them)
**Don't make a non-technical operator format a commit message.** Ask in plain English what they did, then YOU write the conventional message — `type(scope): what changed and why` (e.g. `docs(offer): tighten the guarantee section`). Show it, get a nod.
```bash
git add <intended paths>
git commit -m "<message you wrote>"
```

## Step 5 — Push YOUR branch (never main)
```bash
git push -u origin HEAD
```
(If your repo protects `main`, a direct push is rejected. You only ever push your own branch.)
If the push is **rejected because the branch is behind**, don't force it — bring the latest in first (`git merge origin/main`), and if that conflicts, run **`/resolve-conflict`**, then push again.

## Step 6 — Open or update the PR (fill the template, don't skip it)
- No PR yet → create one and **populate the PR template** (don't rely on `--fill`, which only copies the commit and skips the checklist / AI-disclosure). Write the body to match `.github/pull_request_template.md`, then:
  ```bash
  gh pr create --base main --title "<type(scope): summary>" --body-file <(printf '%s' "<filled template body>")
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
