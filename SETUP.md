# Setting up this workspace

**What this is:** the list of things that have to be true for this company's workspace to run safely. Do them in order, once. Each step that needs a person to click something links its card in `docs/human_steps/`, which has the exact clicks, what success looks like, and what to send back.

**Ask for everything up front.** Grant every access listed here in one sitting, at first connect, so nobody is stopped halfway through a job waiting for a permission.

## 1. The tools on your computer
git, Python 3, Node.js and the GitHub CLI, signed in with `gh auth login`. See GETTING_STARTED step 3. Without Python 3 or Node.js some safety checks are skipped silently, and `start` warns you.
- Card: [Run a terminal command Claude gives you](docs/human_steps/run_a_terminal_command_from_claude.md)

## 2. The name and the registry row
- **Name:**
  - `<company>-os` in your own GitHub organization;
  - `client-<slug>-os` while a provider holds it for you;
  - `ff-00-instance` for Funnel Futurist's own.
  - A deployed site's Vercel project uses the repository's exact name.
- **Registry row:** fill in `estate.yaml`. If a provider runs a registry for you, send them the file. They add the row before anything new is created.

## 3. Access to grant (all at once)
| Who or what | Gets | How |
|---|---|---|
| The founder | Owner or admin of the repository, with two-factor sign-in on | Card: [Turn on GitHub 2FA](docs/human_steps/turn_on_github_2fa.md) |
| Each operator | **Write** on this repository, with 2FA on; their GitHub username in `.aios/config.json` with their role | A founder edits `.aios/config.json` (a founder-only file) |
| Your provider's agent app (if you have a provider) | Installed on **this repository only**, with the permissions it lists | GitHub: your organization's Settings, then GitHub Apps |
| Vercel (if you deploy a site) | Access to this repository | Card: [Connect Vercel to a GitHub repository](docs/human_steps/connect_vercel_to_a_repo.md) |
| Supabase (if you have a database) | A token scoped to the one project and the permissions named | Card: [Create a Supabase access token](docs/human_steps/create_a_supabase_token.md) |

When someone leaves: [Remove an org member](docs/human_steps/remove_an_org_member.md), then change any shared secret they knew.

## 4. Secrets
Secret **values** live in `.env` (Git never uploads it) or in the tool that uses them. `.aios/config.json` records only *where* each one lives, for example `env:ANTHROPIC_API_KEY`.

Every key in this Starter is optional:

| Name | For |
|---|---|
| `ANTHROPIC_API_KEY` | scripts that call Anthropic directly |
| `OPENAI_API_KEY` | scripts that call OpenAI directly |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | the Google Drive connection |

`start` and `verify` list which ones are set.

## 5. The pull-request reviewer
Follow `docs/PR_REVIEWER_SETUP.md`. It reviews every pull request and never blocks you.

## 6. A site, if you have one
It lives in `03_RevOps/site/`. Vercel's Root Directory is `03_RevOps/site`. The site deploys from `main` only.
- Card: [Connect Vercel to a GitHub repository](docs/human_steps/connect_vercel_to_a_repo.md)

## 7. Backups, if you have a database
Take one before any risky change, and on a schedule you choose. Keep the files out of every repository.
- Card: [Download a Supabase backup](docs/human_steps/download_a_supabase_backup.md)

## 8. First-run checks
Run these in the workspace. Each should pass before real work starts.
```sh
python3 scripts/aios/aios.py start                  # your name, your role, the release, the layout
python3 scripts/aios/aios.py verify --target .      # "matches the installed release"
python3 scripts/aios/aios.py governance check       # the founder-only files and their owners
bash scripts/team/verify-branch-protection.sh       # whether GitHub can block a bad merge
```

**What protects you, and when it doesn't:** see "What protects you" in `docs/INSTALL_AND_UPGRADE.md`. A private repository on a personal free GitHub account can't block merges. The founder-only check still shows red, but it can't stop the merge.

## Upgrading from Starter 2.x
`python3 scripts/aios/aios.py upgrade --release releases/starter-3.0.0.json --target .` moves every file from the old numbered folders into the domain folders, and leaves nothing behind. It lists any of your own files that still mention an old folder, and any deployed site whose Vercel Root Directory must change. Commit afterwards: git shows the change as moves. `rollback` puts everything back.
