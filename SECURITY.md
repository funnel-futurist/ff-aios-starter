# Security

Your AIOS holds the keys to your business. Treat it that way. This is the short version of how the template keeps you safe and what to do if something goes wrong.

## How the template protects you
- **Claude Code can't read your secrets.** `.claude/settings.json` denies reads on `.env*`, `*.pem`, `*.key`, and credential files, so your keys never enter a Claude session.
- **Secrets never reach GitHub.** `.gitignore` ignores `.env` (and `node_modules/`, logs, etc.), so they can't be committed by accident.
- **Destructive commands are blocked by default.** `settings.json` denies `rm -rf`, force-push, `git reset --hard`, `git clean -f`, and `sudo`. You can loosen this once you know what you're doing, but the floor is "hard to wreck."
- **The PR reviewer is a second set of eyes.** Every pull request gets scanned for leaked secrets, destructive SQL, and filename hygiene before it merges. It advises; it never blocks.

## Your part (the guardrails)
- Keys live in `.env` or a password manager. Nowhere else. Not Slack, not email, not a chat message, not a Google Doc.
- Put a **spend limit** on every API key and give each one a **specific name** so you can revoke one without touching the others.
- Turn on **2FA** on GitHub and on your Anthropic Console account.
- Keep your repo **private**.
- **Never run a skill from a source you don't trust.** A skill runs with your access. Read it first.

## If a key leaks (act in this order)
1. **Revoke it immediately** in the platform that issued it (Anthropic Console, Google Cloud, etc.).
2. **Generate a replacement**, put it in `.env`, and confirm `.env` is still gitignored (`git status` should not list it).
3. **Tell your team in the open** (don't hide it). Anyone sharing the repo needs to stop using the dead key.
4. **Scrub the history if it was committed.** If the key ever landed in a tracked file and got pushed, the value lives in git history forever (even after you delete the file), and bots scrape repos within minutes. Rotation in step 1 is what actually protects you, so treat the old value as burned. To also clean history: ask Claude Code to scrub it (`git filter-repo` or BFG), or for a brand-new repo just delete it and re-create from the template.

## Reporting a problem in the template itself
Found a flaw in this template (a weak default, a missing guardrail)? Tell whoever gave you the template, or open a private issue on the upstream repo. Don't post secrets or live keys in an issue.
