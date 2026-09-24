# Your skills (what they are, what they do)

Skills are pre-built moves your AIOS can run by name. Type `/` in Claude Code to see them live. Here's the full list with a one-line description and how to trigger each.

## The core set (20 ship in this repo, plus Anthropic's four document skills)

| Skill | What it does | Trigger |
|---|---|---|
| **start** | The role-based way in: who you are, what your role may do, which release is installed and whether it still matches, and which files are the founder's. | `/start` |
| **start-my-day** | Begin a session safely: syncs you to the latest, puts you on your own branch, loads your brain. | `/start-my-day` |
| **wrap-up** | End a session safely: self-review, save, push, open the review request, write a plain-English handover. | `/wrap-up` |
| **review-queue** | The reviewer's live queue: every open change, sorted into ready, waiting on you, stuck and stale. | `/review-queue` |
| **resolve-conflict** | A calm, plain-English path through a merge conflict, when two people changed the same lines. | `/resolve-conflict` |
| **onboard_wizard** | First-run setup walk: tool → repo → keys → invite team; captures your vision / mission / values; proves the brain works. Run it first, and again when a teammate joins. | `/onboard_wizard` |
| **context_load** | Reads your whole workspace and gives you a session brief (what's here, what's active). | `/context_load` |
| **dashboard** | Quick status: open tasks, what's in the review queue, what's coming up. | `/dashboard` |
| **grill_me** | Pressure-tests your thinking before you act. DECIDE mode runs the Define-Before-You-Build gate so you never build the wrong thing; CAPTURE mode interviews you and writes a process/offer/decision into a clean doc so nothing tacit gets lost. Sparring partner, not answer machine. | `/grill_me` |
| **project_management** | Break-glass clarity when your plate is overwhelming. Dump everything on it; it triages the whole plate on a value x energy 2x2, tags each by acquisition/fulfillment/operations, flags what you're avoiding, names the one lever, and hands back own/delegate/automate/eliminate + a single "do this next." Pairs with grill_me (grill_me = one decision; this = the whole plate). | `/project_management` |
| **upskill** | Researches what Claude Code + the ecosystem now offer for YOUR workflows, grills you on skill-bloat (you can have 500 skills and use 10), and proposes what to add, update, or retire. Stay current and lean. | `/upskill` |
| **pr_review** | Your guardian. Reviews every pull request, auto-fixes safe issues, flags real risk, approves good work. Never blocks you. | runs on PRs |
| **qc_review** | Reviews a deliverable against your brand voice and quality standards. | `/qc_review` |
| **workspace_health** | Checks your workspace is structured right (folders, files, no rot). | `/workspace_health` |
| **f6_completeness_check** | Checks your Foundational 6 (market, avatar, offer, economics, pitch, profile) are complete enough for the brain to work well. | `/f6_completeness_check` |
| **security_check** | Scans for leaked secrets and obvious security issues before you push. | `/security_check` |
| **file_audit** | Audits filenames + structure against your naming rules. | `/file_audit` |
| **changelog** | Generates a clean changelog entry from your recent changes. | `/changelog` |
| **humanize** | Strips AI-tells from copy (em-dashes, filler, robotic phrasing) so it reads like you. | `/humanize` |
| **financial_teardown** | Runs a full subscription/software teardown: AI reads your bank statements to inventory every recurring charge, sorts each tool by "would anything break?", cancels dead weight, claws back refunds with proven templates, and sets up prevention (dedicated card + limits). Cuts monthly burn, recovers cash, frees bandwidth. | `/financial_teardown` |
| **docx** · **pdf** · **xlsx** · **pptx** | Your document factory: create and edit Word docs, PDFs, Excel sheets, and PowerPoint decks. **Made by Anthropic, installed from Anthropic** as the `document-skills` plugin, not copied into this repo (see `THIRD_PARTY_NOTICES.md`). `/onboard_wizard` installs it; after that Claude reaches for these automatically when you ask for a document. | automatic, once installed |

## How to add your own
When you catch yourself explaining the same task twice, make it a skill: a folder under `.claude/skills/<name>/` with a `SKILL.md` (a name, a description of when to use it, and the steps). Ask Claude Code to scaffold one for you. **Never run a skill from a source you don't trust**, it runs with your access; read it first.

## This brain evolves (staying current + updated)
- **We'll add skills over time, but only what's actually useful to you.** If a skill isn't solving something specific in your business, it doesn't go in. We won't overwhelm you with capability you don't need.
- **Install packs:** periodically we ship curated bundles of new, tested skills you can opt into, so you stay current without chasing every update yourself. You + your operator doing light research consistently = you stay ahead of the curve.
- **Stay current yourself:** run `/upskill` now and then. The tools change monthly, this keeps you on today's best setup without bloat.
- **Pull template updates:** run `/start` to see which release you are on and whether your workspace still matches it, then run `upgrade` from an up-to-date copy of the Starter to move to a newer approved release. Upgrades replace the system layer and never touch your work, and `rollback` puts you back. Full walkthrough: **[docs/INSTALL_AND_UPGRADE.md](../../docs/INSTALL_AND_UPGRADE.md)**.
- **The template brain (copy it / share it):** github.com/funnel-futurist/ff-aios-starter → green **"Use this template."**

## Useful source docs (always current, never stale)
- Claude + Claude Code: https://docs.claude.com
- GitHub: https://docs.github.com
- Anthropic's skills repo, where the document skills come from: github.com/anthropics/skills. The document skills there are Anthropic's, under Anthropic's terms (source-available, not open source), which is why this AIOS installs them from Anthropic instead of copying them.
- When a setup looks out of date, go to the source above or use your unstuck protocol (`docs/UNSTUCK_PROTOCOL.md`).
