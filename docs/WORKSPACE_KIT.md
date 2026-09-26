# The Workspace Kit: see the whole system in Obsidian

**What it is.** One folder you open in Obsidian that shows every part of your company's system: AIOS, Creation, Team Ops and, once they're switched on, Command OS, RevOps and Attention. Each part stays in its own GitHub repository with its own history. The folder is a map over them. It doesn't combine them.

**What you need.** The free Obsidian app, Git, and a GitHub sign-in that can read your repositories. You don't need an Obsidian account, an API key, Obsidian Publish or Obsidian Sync, and there are no community plugins to install.

**What it never does.** It never deletes, resets, stashes or force-pushes anything. If a folder has unsaved work or has drifted from GitHub, it leaves the folder alone and tells you the next step.

## Set it up (about 10 minutes)

Run these from a copy of the Starter, the same way you run upgrades.

1. **Write the manifest.** Copy `templates/workspace-kit/workspace.example.json` somewhere outside any repository, and put your own repository addresses in it. Set each one to `active`, `inactive` (not part of your plan yet) or `reference` (shown as an interface, not downloaded). Never put a password or token in this file. A web address with a token in it is refused.
2. **See the plan.** Nothing changes during this step.
   ```sh
   python3 scripts/aios/aios.py workspace plan --manifest ~/my-workspace.json --parent ~/Documents/MyCompany-Operating-System
   ```
   You get one line per repository. Each line says whether it will be downloaded, shown as inactive, or reported as "not connected" because this computer can't read it.
3. **Create it.**
   ```sh
   python3 scripts/aios/aios.py workspace init --manifest ~/my-workspace.json --parent ~/Documents/MyCompany-Operating-System
   ```
   The folder must be new or empty, and it must not be inside another repository. For a very large repository, add `--filter blob:none`. It downloads file contents only when they're opened.
4. **Open it in Obsidian.** *This is a click only you can make.* Open Obsidian, choose **Open folder as vault**, and pick the folder from step 3.
   **What you should see:** a file list with one folder per repository, plus `00-MAPS` and `START-HERE.md`.
5. **Trust the vault.** *This is also a click only you can make.* If Obsidian asks whether you trust the author, choose **Browse vault in restricted mode** or **Trust**. The kit uses only Obsidian's built-in features, so restricted mode loses nothing.
6. **Open `START-HERE.md`.** From there, the **Operating System** canvas shows how the parts fit together.

## What is in the folder

| Item | What it is | Can I edit it? |
|---|---|---|
| `aios/`, `creation/`, ... | Your repositories, each with its own Git history | Yes. This is where your work goes |
| `START-HERE.md` | The entry page | Yes. If you edit it, a refresh writes the new version beside it instead |
| `00-MAPS/` | Generated maps: Repository Map, System Relationships, Knowledge Health, the Operating System canvas | You can, but they're rebuilt. Put notes in a repository instead |
| `WORKSPACE.json` | The manifest | Yes. It's how you switch a phase on |
| `.obsidian/` | Obsidian's settings: built-in plugins only, links left alone when you rename, and Publish and Sync off | Yes. Your changes are kept |

A folder shown as **inactive** or **reference** isn't missing or broken. It's a part of the system this company hasn't set up yet. A box marked **Interface only** on the canvas is a job Funnel Futurist does for you: you ask for it and get the result in your own systems. The method behind it isn't in this folder.

## Day to day

- **See what state each repository is in, without downloading anything:** `aios workspace status --parent <folder>`
- **Refresh:** `aios workspace sync --parent <folder>`. It downloads new repositories, brings clean ones up to date, and rebuilds the maps.
- **Switch on a new phase:** change its `state` to `active` in `WORKSPACE.json`, then run `sync`. Only repositories you can already read are downloaded. It never creates empty placeholder repositories.

## When something is wrong

| You see | What it means | What to do |
|---|---|---|
| `dirty` | That repository has changes you haven't committed | Commit them, or move them to a branch, then sync again. Nothing was changed |
| `diverged` | Your copy and GitHub both have new commits | Run `git pull` in that folder and resolve it, or ask for help. Nothing was changed |
| `other-branch` | You're working on another branch | Switch back when you're ready. Nothing was changed |
| `not connected` | This computer can't read that repository | Run `gh auth login` as someone with access, or ask an owner for access. Everything else still works |
| `Repository Map.new.md` appears | You edited a generated map, so your version was kept | Read the new one, then delete whichever you don't want |
| A warning about a nested vault | A repository has its own `.obsidian` folder | Open the parent folder in Obsidian, not the repository |

## What this is not

- **It isn't access control.** Hiding a file in Obsidian doesn't protect it. The kit keeps private material out by never downloading it.
- **It isn't a scheduler.** The cloud Architecture Health check reads GitHub directly and runs with this computer off and Obsidian closed. The Knowledge Health page here is a local check of the files on this computer, labelled with the exact version it looked at.
- **It isn't a source of truth.** Business facts live in the repositories. The maps can be deleted and rebuilt at any time.
