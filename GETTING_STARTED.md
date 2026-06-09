# Getting Started — your AIOS, step by step (caveman mode: no skipped steps)

> Fastest path: open this repo in Claude Code and run **`/onboard_wizard`** — it walks you through all of this interactively. This doc is the written reference. If any step is fuzzy, use the unstuck protocol (`docs/UNSTUCK_PROTOCOL.md`) or search YouTube for it (a video from the last 1–2 months).

## The setup, in order
1. **Get a Claude subscription** (Pro or Max — Max if you'll use it heavily).
2. **Get this template** — click **"Use this template"** on the GitHub repo → you get your own private copy. That repo is your AIOS.
3. **Pick how you run Claude Code:** **Web** (easiest, no install) · **Desktop** · **VS Code** (recommended — you see your files, full control).
4. **If local (Desktop/VS Code):** install **git** once, then **clone your repo into a folder on your computer** — that folder *is* your AIOS.
5. **Open Claude Code** in that folder and run **`/onboard_wizard`** (or `/context_load` for a quick brief).
6. **Invite your team** — your GitHub repo → Settings → Collaborators → add each teammate's GitHub username. Now everyone shares the **same brain**.
7. **Sync:** when you change things, commit + push (Claude does it for you); your team pulls. GitHub keeps everyone in sync.
8. **Secure it (airlocks):** turn on **2FA**, keep keys in `.env` (gitignored), set a **spend limit** on each API key.

**Done = subscription · repo · running (web or local) · team invited · secure.**

## Connect your Google Drive (so your brain stays current)
So your AIOS always works from the latest version of your docs:
- In **Google Cloud Console** (one project), enable the **document-suite APIs** you'll actually use: **Drive** (your files), **Docs** (create/edit docs + reports), **Sheets** (trackers/data/reporting), **Slides** (decks). Add others (Gmail, Calendar) **later, one at a time**, when you have a specific reason — don't switch everything on up front (least privilege).
- Create credentials, keep the key in `.env`, then point your `01_Foundations/` (your F6) at your Drive docs so they sync to the latest versions. Stuck? `docs/UNSTUCK_PROTOCOL.md` → search "Google Drive API key Cloud Console."

## Your guardrail + safety net
- **PR reviewer** — every PR is reviewed, safe issues auto-fixed, good work approved, risk flagged. It never blocks you. Setup: `docs/PR_REVIEWER_SETUP.md` (2 minutes).
- **Unstuck protocol** — your safety net the whole way: `docs/UNSTUCK_PROTOCOL.md`.

*This is your AIOS — `CLAUDE.md` is yours to shape as you grow. Just follow the best practices in it.*
