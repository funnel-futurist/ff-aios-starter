# AIOS Setup Checklist

> Works two ways: **standalone** (you own and run your AIOS yourself) or **agency-managed** (an agency like Funnel Futurist set it up with you). Where this says "your agency," that means them, or you if you're solo.

> For the full setup walkthrough, see **GETTING_STARTED.md** and run the `/onboard_wizard` skill. This checklist is your quick-reference and verification gate before and after the setup call.

---

## What You'll Need

- [ ] A computer (Mac or Windows)
- [ ] An email address (personal Gmail works fine)
- [ ] A web browser (Chrome, Safari, Firefox, any)
- [ ] 30 minutes on a setup call with your agency (or set aside solo time if you're doing this yourself)

**You do NOT need:**
- Any technical knowledge
- A coding background
- Any special software installed
- Any API keys or credentials

---

## Step 1: Create a GitHub Account (Free)

GitHub is where your workspace files live in the cloud. Think of it like a secure Google Drive for your business.

1. Go to **github.com**
2. Click **Sign Up**
3. Use your email (personal Gmail works, you can change it later)
4. Pick a username (suggestion: `yourname-ops` or `yourbusiness-ops`)
5. **Free plan** is all you need
6. Check your email and verify your account

**Tip:** If "Continue with Google" doesn't work with your business email, use a personal Gmail instead. Non-Google-Workspace emails can't use Google SSO. You can migrate later.

---

## Step 2: Get Access to Your Workspace

Your AIOS workspace is a private GitHub repository created from the `ff-aios-starter` template. There are two ways you might have it:

**Option A: You created it yourself (standalone)**
1. You clicked "Use this template" on the `ff-aios-starter` repo
2. You now own a private repo under your own GitHub account
3. No invitation needed. Go straight to Step 3.

**Option B: Your agency set it up for you**
1. Check your email for a GitHub invitation
2. Click **"View invitation"**
3. Click **"Accept invitation"**
4. You now have access to the private workspace your agency created for you

**Don't see the email?** Ask your agency contact for the direct link.

---

## Step 3: Sign Up for Claude (Your AI Assistant)

Claude is the AI that powers your workspace. It reads your strategy docs and answers questions about your business.

1. Go to **claude.ai**
2. Click **Sign Up**
3. Choose **Team plan** ($25/user/month, monthly billing), which gives you admin controls and the ability to add your operator or VA later under one bill
4. Use your **company email** (G Suite / Google Workspace domain). Team plan requires a company email domain.
5. If you see a Tax ID field during checkout, skip it. It's optional.
6. Complete signup

**Don't have a company email (G Suite)?** Start with the **Pro plan** ($20/month) using any personal Gmail. You can upgrade to Team later once you set up Google Workspace for your business. Pro still gives you full access to Claude Code.

**Why not Free?** The Free plan doesn't include Claude Code, which is what connects to your workspace.

**Later:** If you need more usage, you can upgrade to **Premium** ($125/month) for higher limits.

---

## Step 4: Connect Claude to Your Workspace

This is where Claude gets access to your business files. If you have an agency, they'll guide you through this on the call. If you're solo, follow the steps below.

1. Go to **claude.ai** (make sure you're signed in)
2. In the left sidebar, click the **Code icon** (it looks like `< >` brackets)
3. Click **"Run Claude Code Web"** or **"Get Started"**
4. Click **"Continue with GitHub"**
5. **Authorize Claude** when GitHub asks
6. When asked where to install the GitHub app:
   - If you created the repo yourself: select **your personal GitHub account** and grant access to your AIOS repo
   - If your agency created the repo for you: select **your agency's organization** (e.g. Funnel Futurist) and grant access to your workspace repo
   - Grant **"All repositories"** access, or select the specific repo
   - Click **"Install"**
7. **Refresh the page** if your workspace doesn't appear immediately
8. Select your workspace from the list
9. You're connected.

**If your workspace doesn't appear:**
- Confirm you installed the app on the correct account (yours, or your agency's org)
- Try refreshing the page
- If agency-managed, ask your agency contact to verify permissions on their end

---

## Step 5: Your First Command

Type this into Claude:

> **What's my status?**

Claude reads your strategy docs, your task list, and your engagement timeline, then gives you a full briefing on where things stand.

This is the moment it clicks. Claude knows your business.

---

## What You Can Ask Anytime

| Say This | Claude Does This |
|---|---|
| "What's my status?" | Full briefing: tasks, timeline, strategy summary |
| "Who is my ideal client?" | Answers from your Avatar Analysis |
| "Summarize my offer" | Pulls from your Offer Optimization |
| "What's my brand voice?" | Reads your Complete Profile |
| "What should I work on?" | Checks your task tracker, suggests priorities |
| "What's in my review queue?" | Shows deliverables waiting for your approval |
| "Review this copy: [paste text]" | Checks it against your brand voice and QC standards |
| "I don't like the tone in this" | Logs your feedback for your agency (or yourself) to act on |
| "Help me draft a post about [topic]" | Writes using your voice, your positioning, your language |

---

## When You're Stuck

Type: **"Open the unstuck protocol"**

Or remember:
- **Need to DO something?** (click buttons, navigate a tool) Use AI Studio Live (screen share)
- **Need to KNOW something?** (plan, write, draft) Ask Claude right here
- **Need to RESEARCH something?** Use Gemini Deep Research
- **Still stuck after 15 minutes?** Message your agency team, book a support call (if your engagement includes one, or your agency's equivalent), or post in your community

---

## What Happens Next

| When | What |
|---|---|
| **This week** | Explore your workspace, review any docs loaded, get comfortable |
| **As docs finish** | New strategy docs get pushed to your workspace. You'll see them appear. |
| **When deliverables arrive** | "What's in my review queue?" then review and give feedback |
| **When your operator or VA joins** | They set up their own account, get added to your workspace, and you manage the team |

---

## Calls and Check-ins

If your engagement with your agency includes scheduled calls (e.g. a Catalyst Call, AIOS Hot Seat, QBR, or Technical Support Call), those are your touch points to ask questions, review progress, and get unblocked. If you're running this solo, build in your own review rhythms.

If your agency provides a client portal, you can track progress and access resources there. Your agency's portal address will be shared with you directly.

---

## Your Costs

| Item | Cost | Notes |
|---|---|---|
| GitHub account | Free | Always free |
| Claude Team | $25/user/month | Default: admin controls, add operator or VA later under one bill |
| Claude Pro (fallback) | $20/month | If you don't have a company email (G Suite) yet |
| Premium upgrade (future) | $125/month | When you need more usage |

---

## Support

- **Quick question:** Ask Claude in your workspace
- **Technical issue:** Message your agency contact (or check GETTING_STARTED.md if you're solo)
- **Stuck:** Use the unstuck protocol (type "Open the unstuck protocol")

---

*This workspace is yours. Refer back to this checklist anytime. Your workspace gets smarter over time: every document, every decision, every piece of feedback makes it more useful.*
