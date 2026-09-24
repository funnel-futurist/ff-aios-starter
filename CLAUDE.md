# Your AIOS

This is **your AI operating system**, your business's second brain. You own it and you shape it. This file (`CLAUDE.md`) is your constitution: it loads into every message, so keep it lean and make it yours.

## Start here (first run)
Run **`/onboard_wizard`**, it walks you through setup (your tool, this repo, your keys, inviting your team), captures your vision / mission / values, and gets you operating. A new teammate joining later runs it too.

## This file is yours to shape
Edit this `CLAUDE.md` freely as your business and workflow evolve, it's your brain, not a cage. Put your identity, your priorities, and a map to where things live. Keep it **lean** (a map, not a manual, detail belongs in your folders and skills). The only thing we ask: follow the best practices below.

## Best practices (the guardrails)
- **Secrets stay out of the repo.** Keys live in `.env` (it's gitignored, so it never reaches GitHub). Set a spend limit on each key; turn on 2FA. (Airlocks: scope access, contain the blast radius.)
- **Reversible by default.** Commit early and often, git is your safety net. Don't delete important work or force-push.
- **The PR reviewer has your back.** `.claude/skills/pr_review` reviews every PR, fixes safe issues, approves good work, and flags real risk. It never blocks you.
- **When you're stuck, use the unstuck protocol** (`docs/UNSTUCK_PROTOCOL.md`): Claude in caveman mode → screenshot + AI → YouTube (last 1–2 months) → NotebookLM → escalate. You'll solve ~99% yourself.
- **Lean beats bloated.** Add the high-impact core; look the specifics up as you go.

## Your workspace
`01_Foundations/` (your Foundational 6: market, avatar, offer, economics, pitch, profile) · `02_Deliverables/` · `03_Quality_Control/` · `04_Customer_Journey/` · `05_Assets/` · `06_Communication/` · `07_Setup/` · `08_Automations/` · `09_Archive/`. Add folders as you grow. File naming: lowercase, underscores, no spaces (`taxonomy_rules.md`).

## Your skills
Type `/` to see them. What each one does: `.claude/skills/README.md`. Run `/start` any time to see the moves for your role.
- **Start and end every session:** start · start-my-day · wrap-up · context_load · dashboard
- **Setup and staying current:** onboard_wizard (run it first) · upskill
- **Think before you build:** grill_me · project_management
- **Your foundations and quality:** f6_completeness_check · qc_review · humanize
- **Keep the workspace healthy:** workspace_health · file_audit · security_check · changelog
- **Working as a team:** review-queue · resolve-conflict · pr_review (your guardian, runs on every change)
- **Money:** financial_teardown
- **Documents:** Word, PDF, PowerPoint and Excel come from Anthropic's `document-skills` plugin, which `/onboard_wizard` installs. They are Anthropic's, not copied here (`THIRD_PARTY_NOTICES.md`).

Add your own (see `docs/UNSTUCK_PROTOCOL.md` and the skills folder for how). Never run skills from sources you don't trust.
