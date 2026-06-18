# START HERE — working in your AIOS (read once, ~3 minutes)

Welcome. This repo is your **AI Operating System** — your second brain. This page is everything you need to work in it safely. You **cannot** break it — that's by design.

## The one picture you need: separate timelines
- **`main`** = the *one official timeline* you trust.
- A **branch** = a *private side-timeline*. You work here so you can never break the official one.
- **pull** = copy the latest official changes into yours (so you're never working from an old copy).
- **commit** = save a checkpoint of your work.
- **push** = upload your branch so it's safe and your team can see it.
- **PR (pull request)** = *"please add my side-timeline to the official one"* — where it gets reviewed.

**The only rule that matters:** *pull before you work, push when you're done.* Two commands do this for you.

## The two commands (this is the whole routine)
| When | Command | What it does |
|---|---|---|
| Start of a work session | **`/start-my-day`** | Figures out who you are, syncs you to the latest official version, puts you on a clean branch, helps you decide what "done" looks like, and loads your brain (`/context_load`). |
| End of a work session | **`/wrap-up`** | Reviews your work like a senior engineer (and cleans it up), saves it, pushes it, opens your review request, and writes a plain-English update for your team. |

That's it. Open the repo in Claude Code → type **`/start-my-day`** when you begin → **`/wrap-up`** when you're done.

## What happens automatically (you do nothing)
- When you open the repo, you get a friendly nudge **if** you're on `main` or behind the latest — telling you to run `/start-my-day`.
- Genuinely dangerous commands (that could delete unsaved work) are blocked or paused for you.

## If you get stuck or confused
- Tell Claude: *"treat me like a caveman, explain like I'm 5, give me every click."*
- **Saw scary `<<<<<<<` symbols after syncing?** That's a merge conflict — normal, nothing's lost. Run **`/resolve-conflict`**.
- Read **[CONTRIBUTING.md](CONTRIBUTING.md)** for the "what do I do when…" answers.
- New here? Run **`/onboard_wizard`** for the full guided first-time setup.
- When in doubt, run `/wrap-up` and ask. Nothing on your own branch can hurt the official version.
