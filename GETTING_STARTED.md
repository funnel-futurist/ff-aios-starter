# Getting Started

> Your first 10 minutes with this workspace.

---

## Step 0: How Technical Are You?

Rate yourself 1-10: *"How comfortable are you opening Terminal on your computer, typing a command, and pressing Enter?"*

| Your Score | Your Path | Your VA's Job |
|---|---|---|
| **1-3** ("What's Terminal?") | Use **Claude Desktop** app only. Your VA handles everything else. | Full setup: GitHub, folder structure, security config, all integrations |
| **4-6** ("I've used it but I'm not confident") | Use **Claude Desktop** + **GitHub Desktop** (visual Git). VA handles security and advanced setup. | Security config, integrations, server setup if needed |
| **7-10** ("I live in the terminal") | Use **VS Code + Claude Extension** or terminal. Self-serve most setup. | Collaboration partner, not setup lead |

---

## For Everyone: What You Need

1. **A Claude subscription** — **Team plan** ($25/user/mo) recommended. Sign up at [claude.ai](https://claude.ai). Gives admin controls and you can add your VA later under one bill.
   - If you don't have a company email (G Suite), start with **Pro** ($20/mo) and upgrade to Team when ready.
2. **A GitHub account** — Free. Sign up at [github.com](https://github.com). Your VA needs one too.

---

## Path A: Non-Technical Founder (Score 1-5)

### Your Setup (5 minutes)

1. **Download Claude Desktop** from [claude.ai/download](https://claude.ai/download) (Mac or Windows)
2. **Sign in** with your Claude subscription
3. **Open the Code tab** in Claude Desktop
4. **Point it at this folder** (your VA will have cloned it to your computer during setup)
5. **Type:** `/context_load` — Claude reads your workspace and gives you a briefing

That's it. You're running.

### Your Daily Workflow

**Morning:**
- Open Claude Desktop → Code tab → this folder
- Ask: *"What's my status? What needs my attention?"*
- Check `02_Deliverables/_review_queue/` if Claude says there's something to review
- Approve or give feedback

**Anytime:**
- Ask Claude anything about your business — it knows your F6, your timeline, your preferences
- Draft content briefs, review copy, check metrics — just describe what you need
- Your VA handles all the technical building

### Your VA Did This For You

Your Technical VA already:
- Cloned this repo to your computer
- Configured security settings (Claude can't read your API keys)
- Set up GitHub so you and your VA stay in sync
- Created your billing account (Team plan)
- Loaded your Foundational 6 docs into `01_Foundations/`

---

## Path B: Technical Founder (Score 6-10)

### Your Setup (10 minutes)

1. **Clone this repo:**
   ```bash
   git clone https://github.com/[your-org]/[your-repo].git
   cd [your-repo]
   ```

2. **Open in VS Code** (with Claude Code extension installed) or **Claude Desktop** (Code tab)

3. **Run `/init`** — Claude reads the workspace and generates a summary

4. **Run `/context_load`** — get your session brief

5. **If you need API integrations:**
   ```bash
   cp .env.example .env
   # Fill in your keys from 1Password → save → close
   # Claude Code CANNOT read this file — that's the security feature
   ```

### Collaborating With Your VA

- Your VA works on a **branch**, you review and approve merges to **main**
- Daily handoff: `06_Communication/daily_handoff.md` — your VA posts end-of-day updates here
- Task board: `04_Customer_Journey/task_tracker.md` — single source of truth for all work
- Review queue: `02_Deliverables/_review_queue/` — finished work lands here for your approval
- Decisions: `06_Communication/decisions_log.md` — every strategic call gets logged here

---

## What Claude Can Do In This Workspace

| Ask Claude... | It Will... |
|---|---|
| "What's my status?" | Read your task tracker, handoff, and review queue |
| "Draft a content brief for [topic]" | Use your F6 to write a brief in your brand voice |
| "Review this copy" | Check it against your QC preferences and F6 positioning |
| "What decisions have we made?" | Pull from the decisions log |
| "Summarize my last call" | Process notes from `06_Communication/meeting_notes/` |
| "What's blocked?" | Check the task tracker for stuck items |

### Skills (Pre-Built Workflows)

| Command | What It Does |
|---|---|
| `/context_load` | Reads your entire workspace and gives a session brief |
| `/dashboard` | Quick status — tasks, review queue, upcoming deadlines |
| `/qc_review` | Reviews a deliverable against your brand preferences |

---

## Keeping This Workspace Updated

Your Funnel Futurist team may push updates to this template over time — new skills, improved documentation, security patches. These updates arrive as a **pull request** on your repo. You review and merge them. Nothing changes without your approval.

This is a maintenance perk of working with Funnel Futurist — your workspace stays current as our tools evolve.

---

## Need Help?

| Need | Where |
|---|---|
| Quick question | Your Slack channel (#[your-name]-funnel-futurists) |
| Scheduled technical call | Book a Technical Support Call |
| Emergency / stuck | Book an AIOS Hot Seat |
| Self-serve | Ask Claude in this workspace — it knows your F6 and engagement context |

---

## Security: How We Protect Your Keys

- **Claude Code cannot read your `.env` file.** The `.claude/settings.json` in this repo blocks it.
- **Your `.env` file is never committed to GitHub.** The `.gitignore` blocks it.
- **API keys are never sent over Slack, email, or text.** They go through your password manager (1Password recommended) only.
- **If a key is ever accidentally shared in a message**, tell your Funnel Futurist team immediately. We revoke and regenerate within the hour.

---

*Last updated: 2026-03-20*
