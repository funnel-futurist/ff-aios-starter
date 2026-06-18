# CONTRIBUTING — how you work in your AIOS

Plain-English operating rhythm for you and anyone you add (operators / VAs). Never used git? Fine — the two skills do the work. Start with **[START_HERE.md](START_HERE.md)**, then use this for the details. For the full first-time walkthrough, run **`/onboard_wizard`**.

## First-time setup (once per computer)
> You'll type the commands below in a **terminal** — in Claude Code that's the built-in terminal (in VS Code: Terminal → New Terminal). Never used one? Paste the step to Claude and say *"walk me through this, I've never used a terminal."*
1. Install **git** (search "install git for [your OS]" if needed).
2. Clone your repo: `git clone <your-repo-url>` — get the URL from the green **Code** button on your repo's GitHub page.
3. Sign in to GitHub from the command line with **your own** account: `gh auth login` (pick GitHub.com → HTTPS → login with a browser).
4. Open the folder in **Claude Code** (VS Code extension or desktop app).
5. Run **`/start-my-day`**. The first time it asks your name + GitHub username and saves a small local file (`.aios/local-operator.json`) so it can greet you. That file stays on your machine.

## Already set up but maybe behind? Sync up so you're not missing skills
*(For people who set this up a while ago — first-timers get everything on clone.)* New skills and fixes land on `main` over time, and you won't have them locally until you sync. **Tell:** if you type `/` and don't see `/start-my-day` and `/wrap-up`, you're behind. To catch up:
- **Easiest:** open the repo in Claude Code and say *"sync me to the latest main."* Claude does it safely.
- **Or do it yourself:**
  1. If you have unsaved work, run `/wrap-up` first (or `git stash`) so nothing is lost.
  2. `git checkout main && git pull --ff-only origin main`
  3. On a long-running branch? Bring main's updates into it: `git merge origin/main`
  4. If a sync ever shows a **conflict** (`<<<<<<<` markers), don't panic and don't `git reset` — run **`/resolve-conflict`** and it'll walk you through it.

Now the latest skills are available — use `/start-my-day` and `/wrap-up` as normal. Re-running this anytime you feel out of date is safe.

## The daily rhythm
1. Open the repo in Claude Code → you'll see a status nudge.
2. **`/start-my-day`** → sync, get on a branch, decide what "done" looks like, load your brain.
3. Do your work. Commit small, reviewable chunks (or let `/wrap-up` handle it).
4. **`/wrap-up`** → self-review, commit, push, open/update your PR, post the team update.

## Branch names
`yourname/short-topic-YYYY-MM-DD` — e.g. `alex/welcome-emails-2026-06-18`. `/start-my-day` makes these for you.

## What waits for a human
Set a `CODEOWNERS` file so the catastrophic / irreversible paths (e.g. `.github/`, your `CLAUDE.md`, the skills/hooks engine, any database migrations) require a **code-owner ([PRIMARY_REVIEWER])** to approve before merge. Everything else can move freely. (See `.github/CODEOWNERS` — fill in the placeholders for your repo.)

## If you're the one who reviews / merges (the repo owner)
Run **`/review-queue`** anytime to see what needs you right now — what's **ready to merge**, what's **waiting on your review**, what's **blocked**, and what's **going stale**. It reads live from GitHub (never a stale list), names who acts next, and lets you merge with one confirmation. This is your "what's on my plate" view so nothing sits unseen.

The "you can't break main" promise depends on branch protection being **on**. After you enable it, confirm it's real:
```bash
bash scripts/team/verify-branch-protection.sh
```
It checks protection + required checks + CODEOWNERS, so the promise can't silently be false. (A weekly CI job in `.github/workflows/verify-protection.yml` can do this too — it needs an admin token secret to read protection.)

## What to do when…
- **"I'm behind / stale"** → run `/start-my-day`; it syncs you safely.
- **"I synced and got a conflict / weird `<<<<<<<` symbols"** → run **`/resolve-conflict`**; it walks you through it calmly. Don't `git reset`.
- **"I'm confused / scared I'll break something"** → you won't. Nothing on your branch touches the official version until it's reviewed. Ask Claude to explain like you're new.
- **"I want to start completely fresh"** → run `/start-my-day`; if you have unsaved work it parks it safely first (never deletes it).
- **"I have work I forgot to push"** → run `/wrap-up`; it finds uncommitted/unpushed work and gets it safe.
- **"I'm blocked for more than ~30 minutes"** → stop, `/wrap-up` what you have, and put the blocker in your team update.

## The hard rules
- Never work on `main`. (The nudge + `/start-my-day` keep you off it.)
- Never force-push or hard-reset. (Blocked by your repo's safety settings.)
- Never commit secrets/keys. (`/wrap-up`'s review flags them; `.env` is git-ignored.)
- Send changes to `main` through a reviewed PR (turn on branch protection — see below).

## Want to understand the automatic stuff (hooks)?
A tiny program runs automatically when you open the repo: a **staleness nudge** that tells you if you're on `main` or behind the latest. It only *reads* — it never changes your files. Your `.claude/settings.json` also **denies** the most dangerous commands outright (`rm -rf`, `git push --force`, `git reset --hard`, …). You never configure these; they exist to protect you. (Covered in the AIOS training + certification.)

## Recommended GitHub settings (one-time, by the repo owner)
- Protect `main`: require a PR before merge, block force-pushes and deletions.
- Require **code-owner review** so the `CODEOWNERS` paths can't merge without a human.
- (Optional) add the AI PR reviewer for automatic first-pass review.
