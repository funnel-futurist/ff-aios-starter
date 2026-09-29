# Your learning sandbox

**What it is.** A private AIOS of your own, holding only invented content, where you practise while you learn. It's the space the AIOS Operator certification calls your sandbox. You don't need any certificate to make one: it comes first, and the learning happens inside it.

**What it is not.** It isn't Funnel Futurist's own AIOS, and it isn't a client's. It never holds client names, client files, real business data or real API keys. If your GitHub account can open other company repositories, leave them alone while you practise here.

## Make it (about 30 minutes, most of it installing tools)

1. **Tools.** Install git, Python 3 and the GitHub CLI, then run `gh auth login`. See [GETTING_STARTED.md](../GETTING_STARTED.md) step 3.
2. **Where.** Use the Claude Code desktop app or VS Code for this. Claude Code on the web can't run `gh`, so it can't tell who you are (step 4).
3. **Repository.** Create an empty private repository on your own GitHub account. If you're taking the AIOS Operator certification, name it the way the certification says: `AIOS_CERT_C0_<FirstName>_Sandbox`.
4. **Install.** Install the newest approved release into it with the installer, with yourself as `founder` in the organization file (GETTING_STARTED step 6). Put an invented company name in `org_id`.
5. **Check.** In the sandbox, run `python3 scripts/aios/aios.py start`, then `python3 scripts/aios/aios.py verify --target .`

**It worked when** `start` prints your GitHub name, the role `founder` and the release, and `verify` says `matches the installed release`. The sandbox then has the `01`-`09` folders, `CLAUDE.md` and the skills. It has no `releases/`, `tests/` or `evidence/` folders: those belong to the Starter's own repository, not to yours.

## What's in it, and what isn't yet

| Part | In your sandbox | Not in it |
|---|---|---|
| AIOS | The approved Starter release, owned by you | Funnel Futurist's own AIOS |
| Design | Your brand guide and assets in `05_Assets/`, and Anthropic's document skills if you install them during onboarding. Those skills are Anthropic's, not Funnel Futurist's | FF's protected Design method. FF's document production is planned as a service you can request; it isn't callable yet |
| Obsidian map (optional) | A vault over your own repositories, made with the Workspace Kit once your release includes it ([WORKSPACE_KIT.md](WORKSPACE_KIT.md)) | Any Funnel Futurist repository |
| Branch protection | On a personal free GitHub account, a private repository can't have branch protection. GitHub answers "Upgrade to GitHub Pro or make this repository public". The founder-only pull-request check still runs and shows red, but it can't block a merge | Hard blocking, unless the account is on a paid plan or the repository belongs to an organization on a paid plan |

## When something doesn't match

If the certification or this page tells you to do something the sandbox can't do, write down where it said so, what you did and what happened. That's a finding about the product or the training. It isn't your mistake.
