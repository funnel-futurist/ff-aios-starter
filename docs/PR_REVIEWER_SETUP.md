# PR Reviewer: 2-minute setup
A client does these 3 things, then it's live:
1. Install the Claude GitHub App: https://github.com/apps/claude → install on your repo.
2. Add your API key: repo → Settings → Secrets and variables → Actions → New repository secret → name `ANTHROPIC_API_KEY`, value = a Claude API key from console.anthropic.com. (Recommended: a dedicated key in its own Workspace with a monthly spend cap, so a leak is capped.)
3. That's it. Open a PR, the reviewer comments, fixes safe issues, and approves good work.

## Optional, let it auto-merge good work
repo Settings → enable "Allow auto-merge", then add a repository variable `PR_AUTOMERGE` = `on`. Low-risk approved PRs then merge themselves. (If your repo deploys on push via Vercel/Netlify, authorize the bot author there first.)
