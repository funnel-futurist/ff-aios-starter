# Your AIOS: an AI operating system for your business

This template gives you a working **AI operating system**: one repo that becomes your business's second brain, run by Claude Code. Click **"Use this template,"** and in a few minutes you (and your team) are operating with AI: an always-on PR reviewer watching your back, a guided setup wizard, and a safety net for when you get stuck.

**AIOS is the *mechanism*, not the tool.** The agent (Claude Code today) is interchangeable; the system (your brain, your folders, your skills) is what compounds.

---

## Start in 3 steps

1. **Use this template** → click the green **"Use this template"** button → you get your own private repo. That repo *is* your AIOS.
2. **Open it in Claude Code** and run **`/onboard_wizard`**: it walks you through the whole setup (pick your tool, clone the repo, add your keys, invite your team) and captures your vision / mission / values.
3. **Go.** Open a PR and the reviewer has your back; get stuck and the unstuck protocol gets you moving.

Full written walkthrough (caveman mode, no skipped steps): **[GETTING_STARTED.md](GETTING_STARTED.md)**.

---

## What's inside

| Piece | What it is |
|---|---|
| **Your workspace** (`01_Foundations/` → `09_Archive/`) | Where your strategy, deliverables, brain, and history live. `01_Foundations/` holds your Foundational 6 (market, avatar, offer, economics, pitch, profile). |
| **Skills** (type `/`) | Pre-built workflows: `onboard_wizard`, `context_load`, `dashboard`, `qc_review`, `workspace_health`, `pr_review` (your guardian), and more. Add your own. |
| **The PR reviewer** ([docs/PR_REVIEWER_SETUP.md](docs/PR_REVIEWER_SETUP.md)) | Reviews every PR, auto-fixes safe issues, approves good work, flags real risk. **Never blocks you.** ~2-min setup. |
| **The unstuck protocol** ([docs/UNSTUCK_PROTOCOL.md](docs/UNSTUCK_PROTOCOL.md)) | Your safety net: caveman mode → screenshot + AI → YouTube (last 1–2 months) → NotebookLM → escalate. You'll solve ~99% yourself. |
| **CLAUDE.md** | Your constitution; loads into every message. It's yours to shape (just follow the best practices in it). |

---

## The best practices (your guardrails)

- **Secrets stay out of the repo.** Keys live in `.env` (gitignored); set a spend limit on each; turn on 2FA. (Airlocks: scope access, contain the blast radius.)
- **Reversible by default.** Commit early and often; don't force-push or delete important work.
- **Lean beats bloated.** Add the high-impact core; look the specifics up as you go.
- **Never run skills from sources you don't trust.**

---

## It's yours

This is *your* AIOS: own it, shape it, grow it. We give you a clean, secure, best-practice starting point; what you build on top is up to you. As the tooling evolves, improvements arrive as **pull requests** you review and merge, so nothing changes without your approval.
