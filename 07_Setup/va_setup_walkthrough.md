# VA Setup Walkthrough

> Works two ways: **standalone** (you own and run your AIOS yourself) or **agency-managed** (an agency like Funnel Futurist set it up with you). Where this says "your agency," that means them, or you if you're solo.

> For the canonical step-by-step setup, see [GETTING_STARTED.md](../GETTING_STARTED.md) and run the `/onboard_wizard` skill. This file gives you an interactive Claude Code prompt that walks through verification gates in sequence.

---

## Before You Start

- You need: the GitHub repo URL, a Claude Team plan invite or your own subscription, and any credential vault access (e.g. 1Password)
- You should be in VS Code with the Claude Code extension, or terminal
- Your repo was created from the ff-aios-starter template. If your agency created the repo for you, they may have invited you to it instead. Either way, clone it first, then `cd` into it and run `claude`.

---

## Setup Prompt (Copy and Paste Into Claude Code)

```
You are running the AIOS Setup Walkthrough. This is an interactive, step-by-step guide to configure a new operator workspace. Walk me through each step one at a time. Do NOT proceed to the next step until I confirm the current one is complete.

CONTEXT:
- This repo was created from the ff-aios-starter template
- I am the operator / VA setting up this workspace for the business
- The founder will use Claude Desktop (non-technical) or VS Code (technical)

WALKTHROUGH STEPS:

STEP 1: VERIFY SECURITY
- Check that .claude/settings.json exists and contains deny rules for .env*
- Check that .gitignore blocks .env, .env.*, *.pem, *.key, credentials.json
- Tell me: "Security verified" or list what's missing

STEP 2: SET UP ENVIRONMENT (if needed)
- Check if .env.example exists
- Ask me: "Does this setup need API integrations (Google, OpenAI, etc.)?"
- If yes: guide me to copy .env.example to .env and fill in keys from the credential vault
- If no: skip this step
- Verify .env is NOT tracked by git (run: git status)

STEP 3: LOAD FOUNDATIONAL 6
- Check 01_Foundations/ for completed F6 docs
- Ask me: "Are the F6 docs ready to load? (Market Analysis, Avatar, Offer, Economics, Pitch, Profile)"
- If yes: guide me to place them in the correct subfolders
- If no: note which are missing and move on

STEP 4: CONFIGURE BUSINESS DETAILS
- Read 04_Customer_Journey/engagement_timeline.md
- Ask me to fill in: start date, engagement type, billing cycle, primary contact
- Read 04_Customer_Journey/success_metrics.md
- Ask me to fill in primary KPIs if known

STEP 5: VERIFY SKILLS
- Check .claude/skills/ directory
- Confirm context_load, dashboard, and qc_review skills exist
- Run /context_load and verify the session brief works
- Tell me the result

STEP 6: SET UP COLLABORATION
- Verify 06_Communication/daily_handoff.md exists
- Verify 04_Customer_Journey/task_tracker.md exists
- Verify 02_Deliverables/_review_queue/ exists
- Ask me: "Is GitHub access set up for anyone else who needs it? Can they pull from this repo?"

STEP 7: FINAL VERIFICATION
- Run /dashboard and show the output
- Confirm all 6 folders have content or placeholders
- List any remaining setup items as tasks in task_tracker.md
- Tell me: "Setup complete. Ready for onboarding." or list blockers.

After completing all steps, summarize what was done and what the founder needs to do on their end (if anything).
```

---

## Post-Setup Checklist

After running the walkthrough, verify:

- [ ] `.claude/settings.json` has deny rules
- [ ] `.gitignore` blocks sensitive files
- [ ] `.env` (if created) is NOT in git status
- [ ] F6 docs loaded (or noted as pending)
- [ ] Engagement timeline filled in
- [ ] Skills working (`/context_load` produces a session brief)
- [ ] Task tracker has any remaining setup items
- [ ] GitHub access confirmed for anyone who needs it
- [ ] Ready for the onboarding sync call (if your engagement includes one, or your agency's equivalent)

---

*This walkthrough evolves with the repo. When the template updates, this file updates too.*
