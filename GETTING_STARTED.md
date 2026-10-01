# Getting Started: from nothing to operating (caveman mode, no skipped steps)

> Fastest path once you're in: open this repo in Claude Code and run **`/onboard_wizard`**, it walks you through the rest interactively. This page is the full written reference. If any step is fuzzy, use the unstuck protocol ([docs/UNSTUCK_PROTOCOL.md](docs/UNSTUCK_PROTOCOL.md)) or search YouTube for the exact step (a video from the **last 1-2 months**, the tools change fast).

## Two things to know before you click anything
1. **A GitHub account is the real first step.** Your AIOS lives in a private GitHub repository, so you make that account first, before anything else.
2. **Your Claude *subscription* and an *API key* are two different things.** The subscription (at claude.ai) is what you need: it runs Claude and Claude Code. An API key (at console.anthropic.com, same login) is only for scripts or skills that call Anthropic directly, and nothing in this AIOS requires one. Two dashboards, one Anthropic login.

**Heads up (things that quietly block people):** you'll need a payment method for the Claude subscription; admin rights on your computer to install git, Python 3, Node.js and the GitHub CLI; a Google account for the Drive step; and each teammate needs their *own* GitHub account before you can add them. Use a real business email you'll keep.

---

## The critical path (do these in order)

1. **Create your GitHub account, then turn on 2FA.** Go to github.com, sign up (free is fine), verify your email, pick a professional username (it shows in your repo URL). Then immediately: Settings → Password and authentication → enable Two-factor authentication with an authenticator app (not SMS), and save your recovery codes. A compromised GitHub account means someone else owns your brain. Lock it now.

2. **Create your Anthropic account and subscribe.** Go to claude.ai, sign up, then subscribe (Pro is $20/mo; Max is $100/mo, pick Max if you'll use it heavily or run a team). This gives you the Claude interface.

3. **Install the four tools the setup needs, then sign in to GitHub.** You need **git**, **Python 3**, **Node.js** and the **GitHub CLI** (`gh`). Node.js runs two of the safety checks (one of them stops risky git commands); without it Claude Code skips them without saying so. Install it from https://nodejs.org (the LTS version). Mac: open Terminal and type `git --version` (accept the install prompt if it appears) and `python3 --version` (the same prompt installs it). Install `gh` from https://cli.github.com. Windows: install git from git-scm.com/download/win, Python 3 from python.org (tick "Add python to PATH"), and `gh` from https://cli.github.com. Then run `gh auth login` and follow it. Each of `git --version`, `python3 --version`, `node --version` and `gh --version` should print a number. The workspace uses `gh` to know who you are, so this sign-in is what makes you the founder of your own AIOS.

4. **Run the setup in the Claude Code desktop app or VS Code, not the web version.** Claude Code on the web isn't guaranteed to have a signed-in `gh`, and without it the workspace can't tell who you are, so it treats even a founder as unidentified. Do the setup, installs, upgrades and founder changes on your computer. Day-to-day operator work on the web is fine later.

5. **Create an empty private repository on GitHub.** github.com → New repository → name it something like `my-aios` → set it to **Private** → leave "Add a README" unticked → Create. It stays empty until the next step fills it. That repo *is* your AIOS. (Taking the AIOS Operator certification? Use the sandbox name the certification gives you. See [docs/LEARNING_SANDBOX.md](docs/LEARNING_SANDBOX.md).)

6. **Install the approved release into it.** The installer copies an exact, approved version and checks every file it wrote. In Terminal:
   ```sh
   git clone https://github.com/funnel-futurist/ff-aios-starter.git
   git clone https://github.com/<you>/my-aios.git
   cd ff-aios-starter
   grep -l '"status": "approved"' releases/*.json    # the approved releases; use the newest
   ```
   (On Windows, open each file in the `releases` folder and use the newest one that says `"status": "approved"`.)
   Then check the release's tag: `python3 scripts/aios/aios.py release check-tag starter-X.Y.Z --release-id starter-X.Y.Z`. If it passes, run `git checkout starter-X.Y.Z`, so the install tool you run is that release's own. If it refuses (starter-2.6.0 does, a known exception described in the install guide), stay on this copy. The installer still installs only that release's files and checks every one. Write your organization file (who you are and your role) as shown in [docs/INSTALL_AND_UPGRADE.md](docs/INSTALL_AND_UPGRADE.md), then run `python3 scripts/aios/aios.py install --release releases/starter-X.Y.Z.json --target ../my-aios --config my-org.json`. Then, in `my-aios`: `git add -A`, `git commit -m "Install AIOS"`, `git push`. (Already made a copy with "Use this template"? That copies whatever was on the main branch that day. See "Already have a workspace from Use this template?" in the install guide.)

7. **Open Claude Code in your AIOS folder and check it.** VS Code: File → Open Folder → pick `my-aios`. You should see `CLAUDE.md`, `SETUP.md`, and the domain folders `00_AIOS` to `05_Jobs` plus `99_Archive` in the sidebar. Run `python3 scripts/aios/aios.py start`. It should print your GitHub name, your role (founder) and the release you installed.

8. **(Optional) Get an Anthropic API key, only if a skill asks for one.** Claude Code runs on your subscription, and every key in this AIOS is optional: the installer lists each as "not configured (optional)". If you do add one: Go to console.anthropic.com (same login), API Keys → Create key. Name it specifically, like `my-aios-claude-code`, so you can revoke just that one later. **Copy it now, you can't see it again.** Then set a spend limit on the key (start at $20-$50/mo) so a runaway script can't surprise you.

9. **(Only if you made a key in step 8) Create your `.env` file and paste the key in.** In your AIOS folder, make a file named exactly `.env`. The repo is already set to never upload this file to GitHub. Add one line: `ANTHROPIC_API_KEY=your-key-here`. Save. This is the only place your key lives. Never put it in any other file or a chat message. Every future key (Google, etc.) goes here too.

10. **Run `/onboard_wizard`.** In Claude Code, type `/onboard_wizard` and press Enter. It asks who you are (founder / operator / VA), captures your vision, mission, and values, confirms your folder structure, and personalizes your AIOS to your real business. Answer each question; wait for it to say done.

11. **Invite your team on GitHub.** Your repo → Settings → Collaborators → Add people → type each teammate's GitHub username (they each need their own account first; send them step 1). Give operators/VAs **Write**, view-only people **Read**. Now everyone shares the same brain.

12. **Learn the sync loop: commit, push, pull.** Commit = save a labeled snapshot locally. Push = upload your commits to GitHub so the team sees them. Pull = download what teammates pushed. Claude does these for you when you ask, but the habit is simple: pull at the start of a session, commit + push at the end. That keeps everyone in sync.

13. **Turn on the PR reviewer (2 minutes).** Open [docs/PR_REVIEWER_SETUP.md](docs/PR_REVIEWER_SETUP.md) and follow it. A PR (pull request) is a proposed change before it's merged. The reviewer reads every PR, flags real risks, auto-fixes safe things, and approves good work. It never blocks you. It's your safety net.

14. **Bookmark the unstuck protocol.** Open [docs/UNSTUCK_PROTOCOL.md](docs/UNSTUCK_PROTOCOL.md) and pin it. The order: caveman-mode Claude → screenshot + AI → YouTube (last 1-2 months) → NotebookLM → escalate to a human. Between Claude Code and this, you'll solve ~99% yourself.

15. **Connect Google Drive (so your brain stays current).** This lets your AIOS read and write your real documents. In console.cloud.google.com: New Project → name it → APIs and Services → Enable APIs, and turn on **only** the document suite you'll use: **Drive**, **Docs**, **Sheets**, **Slides**. Don't enable everything (least privilege; add Gmail/Calendar later only when you have a reason). Create credentials, put the key in `.env`, then point your `00_AIOS/company/` docs at your real Drive files so they stay on the latest version. Stuck? Unstuck protocol → search "Google Drive API key Cloud Console."

---

## You're set up when all of these are true
Subscription active · git, Python 3, Node.js and `gh` installed and signed in · your private repo installed from an approved release (`start` shows it) · Claude Code running on your computer · `/onboard_wizard` run · team invited to the repo · secure (2FA on, named keys with spend limits) · unstuck protocol bookmarked.

**Prove it's actually working:** run `/context_load`, then `/f6_completeness_check`, then ask *"what do you understand about my business?"* If Claude answers with specifics from your own docs, your brain is wired right. A generic answer means Drive, your `00_AIOS/company/`, or your key isn't connected yet, fix that before you rely on it.

Caveman version: **account + subscription + tools + installed repo + running + team on it + safety net + proof it works.**

---

*This is your AIOS. `CLAUDE.md` is yours to shape as you grow. Just keep the guardrails (secrets out of the repo, reversible by default, lean over bloated, never run skills you don't trust).*
