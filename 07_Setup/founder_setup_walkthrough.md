# Founder Setup Walkthrough

> Works two ways: **standalone** (you own and run your AIOS yourself) or **agency-managed** (an agency like Funnel Futurist set it up with you). Where this says "your agency," that means them, or you if you're solo.

> For the full step-by-step setup walk, see [GETTING_STARTED.md](../GETTING_STARTED.md) and the `/onboard_wizard` skill. This file is the interactive orientation walkthrough you paste into Claude once setup is done.

---

## Before You Start

- You need a Claude subscription (Pro $20/mo or Team ~$30/user/mo).
- Download Claude Desktop from [claude.ai/download](https://claude.ai/download), or open it in the browser at claude.ai.
- Your operator or VA should have already cloned this repo to your computer. If not, see GETTING_STARTED.md for the full path. Your repo was created from the ff-aios-starter template: either you clicked "Use this template" and own it directly, or your agency created the repo and invited you to it.

---

## Setup Prompt (Copy and Paste Into Claude Code Tab)

```
You are running the Founder Setup Walkthrough for my AIOS. I'm a non-technical business owner setting up my AI workspace for the first time. Walk me through each step one at a time. Use plain language, no jargon. Do NOT move to the next step until I confirm I'm ready.

STEP 1 -- ORIENT ME
- Read CLAUDE.md and tell me what this workspace is in one paragraph.
- Tell me how many folders I have and what each one is for (keep it simple).
- Ask me: "Ready to continue?"

STEP 2 -- CHECK MY FOUNDATIONS
- Look in 01_Foundations/ and tell me which of my 6 strategy docs are loaded.
- If any are missing, tell me which ones and say: "Your operator, VA, or agency will load these. No action needed from you right now."
- If all 6 are loaded, say: "Your strategy docs are fully loaded. Claude now knows your business."

STEP 3 -- SHOW ME MY STATUS
- Run /dashboard (or read the task tracker and review queue manually).
- Tell me: what's active, what's waiting for my review, and what's coming up.
- If everything is empty, say: "Your workspace is fresh, nothing to review yet. Your operator or VA will start populating this as work begins."

STEP 4 -- TEST A QUICK WIN
- Ask me: "What's one thing you'd like to ask about your business right now?"
- Answer using my strategy docs as context.
- Show me that Claude actually knows my business, not just generic answers.

STEP 5 -- SHOW ME THE DAILY ROUTINE
- Explain the daily async workflow in 3 bullet points:
  1. Your operator or VA posts updates in daily_handoff.md.
  2. Finished work lands in _review_queue/.
  3. You review, approve, or give feedback.
- Tell me: "That's it. Open Claude Desktop each morning, ask 'What's my status?' and you're caught up."

STEP 6 -- MAKE SURE I KNOW HOW TO GET HELP
- Show me the unstuck protocol: 06_Communication/unstuck_protocol.md (or docs/UNSTUCK_PROTOCOL.md).
- Remind me of support channels: Slack (if your engagement includes it), Technical Support Call, AIOS Hot Seat, and QBR, if your engagement includes them, or your agency's equivalent.
- Ask: "Any questions before we wrap up?"

End with: "You're all set. Your workspace is live. Ask me anything about your business anytime."
```

---

## What This Does

- Verifies your workspace is properly configured.
- Shows you your strategy docs are loaded.
- Demonstrates Claude actually knows YOUR business.
- Teaches the daily workflow in under 5 minutes.
- Makes sure you know how to get help.

**This walkthrough is a living doc.** As your workspace evolves, so does this guide. When template updates are pushed to ff-aios-starter, this walkthrough stays current. If your agency manages your repo, they'll keep it in sync. If you're solo, pull updates from the template as needed.

---

*Estimated time: 5-10 minutes*
