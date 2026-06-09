# Getting Started: from nothing to operating (caveman mode, no skipped steps)

> Fastest path once you're in: open this repo in Claude Code and run **`/onboard_wizard`**, it walks you through the rest interactively. This page is the full written reference. If any step is fuzzy, use the unstuck protocol ([docs/UNSTUCK_PROTOCOL.md](docs/UNSTUCK_PROTOCOL.md)) or search YouTube for the exact step (a video from the **last 1-2 months**, the tools change fast).

## Two things to know before you click anything
1. **A GitHub account is the real first step.** You cannot click "Use this template" without one. So you make that account first, before anything else.
2. **Your Claude *subscription* and your *API key* are two different things.** The subscription (at claude.ai) is what lets you chat with Claude. The API key (at console.anthropic.com, same login) is what lets Claude Code act on its own (run skills, edit and commit files). You'll set up both. Most people get confused here, so just know: two dashboards, one Anthropic login.

**Heads up (things that quietly block people):** you'll need a payment method for the Claude subscription; admin rights on your computer if you go the install route; a Google account for the Drive step; and each teammate needs their *own* GitHub account before you can add them. Use a real business email you'll keep.

---

## The critical path (do these in order)

1. **Create your GitHub account, then turn on 2FA.** Go to github.com, sign up (free is fine), verify your email, pick a professional username (it shows in your repo URL). Then immediately: Settings → Password and authentication → enable Two-factor authentication with an authenticator app (not SMS), and save your recovery codes. A compromised GitHub account means someone else owns your brain. Lock it now.

2. **Create your Anthropic account and subscribe.** Go to claude.ai, sign up, then subscribe (Pro is $20/mo; Max is $100/mo, pick Max if you'll use it heavily or run a team). This gives you the Claude interface.

3. **Use this template to make your own repo.** On the template's GitHub page, click the green **"Use this template"** → Create a new repository. Set it to **Private** (this is your business brain, not public). Name it something like `my-aios`. Click Create. That repo *is* your AIOS.

4. **Pick how you'll run Claude Code.** Three options: **Web** (claude.ai in the browser, easiest, no install), **Desktop** (the Claude app), or **VS Code** (recommended, you see all your files next to the chat and have full control). Choose before the next step, because the next steps differ by path.

5. **(Desktop / VS Code only) Install git.** Git keeps your repo synced between GitHub and your computer. Mac: open Terminal, type `git --version`, accept the install prompt if it appears. Windows: download from git-scm.com/download/win and run it with all defaults. Then `git --version` should print a number. (Web path: skip 5-7.)

6. **(Desktop / VS Code only) Clone your repo onto your computer.** On your repo, click the green **Code** button, copy the HTTPS URL. Open Terminal (Mac) or Command Prompt / PowerShell (Windows), type `git clone <paste-the-url>` and press Enter. The folder it creates *is* your AIOS on your machine.

7. **Open Claude Code in your AIOS folder.** VS Code: File → Open Folder → pick the cloned folder. You should see `CLAUDE.md`, `GETTING_STARTED.md`, and the `01`-`09` folders in the sidebar.

8. **Get your Anthropic API key (this is the separate one).** Go to console.anthropic.com (same login), API Keys → Create key. Name it specifically, like `my-aios-claude-code`, so you can revoke just that one later. **Copy it now, you can't see it again.** Then set a spend limit on the key (start at $20-$50/mo) so a runaway script can't surprise you.

9. **Create your `.env` file and paste the key in.** In your AIOS folder, make a file named exactly `.env`. The repo is already set to never upload this file to GitHub. Add one line: `ANTHROPIC_API_KEY=your-key-here`. Save. This is the only place your key lives. Never put it in any other file or a chat message. Every future key (Google, etc.) goes here too.

10. **Run `/onboard_wizard`.** In Claude Code, type `/onboard_wizard` and press Enter. It asks who you are (founder / operator / VA), captures your vision, mission, and values, confirms your folder structure, and personalizes your AIOS to your real business. Answer each question; wait for it to say done.

11. **Invite your team on GitHub.** Your repo → Settings → Collaborators → Add people → type each teammate's GitHub username (they each need their own account first; send them step 1). Give operators/VAs **Write**, view-only people **Read**. Now everyone shares the same brain.

12. **Learn the sync loop: commit, push, pull.** Commit = save a labeled snapshot locally. Push = upload your commits to GitHub so the team sees them. Pull = download what teammates pushed. Claude does these for you when you ask, but the habit is simple: pull at the start of a session, commit + push at the end. That keeps everyone in sync.

13. **Turn on the PR reviewer (2 minutes).** Open [docs/PR_REVIEWER_SETUP.md](docs/PR_REVIEWER_SETUP.md) and follow it. A PR (pull request) is a proposed change before it's merged. The reviewer reads every PR, flags real risks, auto-fixes safe things, and approves good work. It never blocks you. It's your safety net.

14. **Bookmark the unstuck protocol.** Open [docs/UNSTUCK_PROTOCOL.md](docs/UNSTUCK_PROTOCOL.md) and pin it. The order: caveman-mode Claude → screenshot + AI → YouTube (last 1-2 months) → NotebookLM → escalate to a human. Between Claude Code and this, you'll solve ~99% yourself.

15. **Connect Google Drive (so your brain stays current).** This lets your AIOS read and write your real documents. In console.cloud.google.com: New Project → name it → APIs and Services → Enable APIs, and turn on **only** the document suite you'll use: **Drive**, **Docs**, **Sheets**, **Slides**. Don't enable everything (least privilege; add Gmail/Calendar later only when you have a reason). Create credentials, put the key in `.env`, then point your `01_Foundations/` docs at your real Drive files so they stay on the latest version. Stuck? Unstuck protocol → search "Google Drive API key Cloud Console."

---

## You're set up when all of these are true
Subscription active · your private repo created · Claude Code running (web or local) · API key in `.env` · `/onboard_wizard` run · team invited to the repo · secure (2FA on, named keys with spend limits) · unstuck protocol bookmarked.

**Prove it's actually working:** run `/context_load`, then `/f6_completeness_check`, then ask *"what do you understand about my business?"* If Claude answers with specifics from your own docs, your brain is wired right. A generic answer means Drive, your `01_Foundations/`, or your key isn't connected yet, fix that before you rely on it.

Caveman version: **account + subscription + repo + running + key secured + team on it + safety net + proof it works.**

---

*This is your AIOS. `CLAUDE.md` is yours to shape as you grow. Just keep the guardrails (secrets out of the repo, reversible by default, lean over bloated, never run skills you don't trust).*
