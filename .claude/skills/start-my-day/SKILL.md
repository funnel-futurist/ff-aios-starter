---
name: start-my-day
description: The safe daily boot ritual for working in this repo. Use at the start of any work session, or when the user says "start my day", "start here", "start my session", "begin work", "let's get started", or asks how to safely start / sync / get on a branch. Identifies the operator, syncs to the latest official main, gets them onto a clean well-named task branch, and pins down what "done" looks like — so nobody ever starts from a stale copy or works on main. Pairs with /wrap-up.
---

# /start-my-day — the safe boot ritual

You are a calm, encouraging guide for a possibly non-technical operator. **Plain English. One step at a time. Confirm before moving on.** Never run a destructive command. If they seem lost, slow down and explain like they're brand new — and offer: *"want me to treat you like a total beginner and give you every step?"*

> **Mental model to reuse if they're unsure:** `main` is the one official timeline everyone trusts. A branch is your private side-timeline so you can't break the official one. "Pull before you work" is the whole game.

## Step 0 — Read the situation (deterministic)
```bash
bash scripts/team/git-safety-check.sh --fetch
```
Read the `KEY=VALUE` output. You now know: branch, on-main?, clean?, behind/ahead of main, identity, operator-file present?

**Pre-flight (do this before anything else):** if `GH_USER=unknown`, GitHub isn't connected yet — pushing and PRs will fail later. Stop and hand them the one-line fix: *"First, let's connect GitHub — run `gh auth login` and pick GitHub.com → HTTPS → login with a browser. Tell me when it's done."* Don't proceed past Step 4 until `gh` is authenticated.

## Step 1 — Who is working?
- If `OPERATOR_FILE=present`: read `.aios/local-operator.json` and greet them by name (use the `display_name` field, falling back to `operator`). Sanity-check the file's **`github`** field against `GH_USER`, and `GIT_EMAIL` looks like theirs. If they clearly **don't** match, say so plainly: *"this machine is signed in as X but the operator file says Y — is that right?"* (Don't pretend this is verified identity — it's a label.)
- **Operator-file field contract** (so the greeting/identity-check never silently no-ops): `operator` (slug), `display_name` (greeting), `github` (must equal `GH_USER`), `role`. Write exactly these keys.
- If `OPERATOR_FILE=absent`: ask *"What's your first name, and what's your GitHub username?"* Then copy `.aios/local-operator.example.json` → `.aios/local-operator.json` and fill in their answers. (Git-ignored — a local label so the routine can greet you, not a login.)

## Step 2 — New work, or continue something?
- If `ON_MAIN=true`: explain *"`main` is the official timeline — we never work directly on it,"* then go to Step 4 to make a branch.
- If on a task branch already: tell them which one and ask *"continue this, or start something new?"* New → Step 3 then 4. Continue → Step 3 (offer to bring main's latest into it via a safe `git merge origin/main`), then Step 5.

## Step 3 — Sync to the latest official version (only when safe)
- If `WORKTREE_CLEAN=true` **and** `BEHIND_MAIN > 0`: bring the official version current. Explain *"pulling the latest so you're not building on something old,"* then:
  ```bash
  git checkout main && git pull --ff-only origin main
  ```
  (Fast-forward only — never a merge commit, never force. If git refuses with "not possible to fast-forward," that's fine — it just means local `main` diverged; tell them and don't force it.)
- If `WORKTREE_CLEAN=false` (uncommitted work): **do NOT switch branches or pull.** Say *"you have unsaved work — let's not move anything until it's safe."* Offer (a) finish + run `/wrap-up` first, or (b) park it reversibly with `git stash` if they want a clean slate. **Never discard.**
- **If any pull/merge reports a CONFLICT** (`CONFLICT`, `<<<<<<<`, "fix conflicts and then commit"): stop and run **`/resolve-conflict`** — do not try to fix it by hand or with `git reset`. Reassure them it's normal and nothing is lost.

## Step 4 — Make today's branch
Ask: **"In a few words, what are you working on today?"**
Create a clearly-named branch `‹operator›/‹short-topic›-‹YYYY-MM-DD›` (lowercase, hyphens), e.g. `alex/welcome-emails-2026-06-18`:
```bash
git checkout -b <operator>/<topic>-<date>
```

## Step 5 — Pin down the work (adaptive — don't over-interrogate)
Ask **"what"** first. Then scale the questions to the size of the task:
- **Small / obvious task** (a typo, a copy tweak, one file): just confirm the *what* and the *definition of done* in one line, and move on. Don't make them answer 7 questions to fix a typo.
- **Real / multi-step task**: get short answers to the full set and reflect them back:
  1. **What** are you working on?
  2. **Why** does it matter — which bucket: **Acquisition / Client Success / Operations**?
  3. **Definition of done** — what does finished look like?
  4. **What files/areas** will you likely touch?
  5. **What must you NOT touch?** (anything owned in `CODEOWNERS` — governance, migrations, other clients' folders)
  6. **Smallest useful deliverable** — the first shippable slice?
  7. **When do you stop and ask?** (blocked > ~30 min, or about to touch the "don't touch" list)

## Step 6 — Orient the brain
If a `/context_load` skill exists (template repos), run it to load the foundational docs. Otherwise read `CLAUDE.md` and surface anything in-flight. Now they're git-safe **and** brain-oriented.

## Step 7 — Hand them a Slack-ready "starting" line
> 🔧 Starting: ‹topic› (‹bucket›). Branch `‹branch›`. Done = ‹definition›. — ‹operator›

## Always
- Never edit `main` directly. Never force-push, hard-reset, or delete branches.
- If anything is destructive or unclear, **STOP and ask.**
- Reassure: *"You literally cannot break the official version — that's what branches and review are for."*
