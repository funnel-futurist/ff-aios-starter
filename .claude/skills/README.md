# Your skills (what they are, what they do)

Skills are pre-built moves your AIOS can run by name. Type `/` in Claude Code to see them live. Here's the full list with a one-line description and how to trigger each.

## The core set (shipped with your AIOS)

| Skill | What it does | Trigger |
|---|---|---|
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
| **docx** · **pdf** · **xlsx** · **pptx** | Your document factory: create and edit Word docs, PDFs, Excel sheets, and PowerPoint decks. Claude reaches for these automatically when you ask for a document. | automatic |

## How to add your own
When you catch yourself explaining the same task twice, make it a skill: a folder under `.claude/skills/<name>/` with a `SKILL.md` (a name, a description of when to use it, and the steps). Ask Claude Code to scaffold one for you. **Never run a skill from a source you don't trust**, it runs with your access; read it first.

## This brain evolves (staying current + updated)
- **We'll add skills over time, but only what's actually useful to you.** If a skill isn't solving something specific in your business, it doesn't go in. We won't overwhelm you with capability you don't need.
- **Install packs:** periodically we ship curated bundles of new, tested skills you can opt into, so you stay current without chasing every update yourself. You + your operator doing light research consistently = you stay ahead of the curve.
- **Stay current yourself:** run `/upskill` now and then. The tools change monthly, this keeps you on today's best setup without bloat.
- **Pull template updates:** you can re-pull improvements from the template brain on demand, or set up a **routine** (`/schedule`) to check for updates automatically. No database, no server, just a scheduled check you own.
- **The template brain (copy it / share it):** github.com/funnel-futurist/ff-aios-starter → green **"Use this template."**

## Useful source docs (always current, never stale)
- Claude + Claude Code: https://docs.claude.com
- GitHub: https://docs.github.com
- The open skills library (where the document skills come from): github.com/anthropics/skills
- When a setup looks out of date, go to the source above or use your unstuck protocol (`docs/UNSTUCK_PROTOCOL.md`).
