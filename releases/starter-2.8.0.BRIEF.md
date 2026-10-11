# Release brief: AIOS Starter 2.8.0

> **Approved 2026-10-11 at `ffafd5f`**, the exact commit this brief names. Phoenix's words and where they are recorded are in `releases/starter-2.8.0.json`.

**Written for:** the founder, before approving. About three minutes.

> **Candidate, not approved.** `releases/starter-2.8.0.json` is a draft pinned to `ffafd5f3844646240e60fa29032ce3d9bc9ee41a`. Nothing is tagged and nothing installs it until a founder approves that exact commit in their own words (ruling D3).

## The decision in one line
**Approve AIOS Starter 2.8.0 at `ffafd5f`.** It is 2.7.2 plus two things a client can see and two safeguards they can't.

| Card | |
|---|---|
| **Wanted outcome** | A client can customise Claude Code's permissions and still upgrade. The public template can no longer be shipped with FF's protected method text by accident. We say plainly which files only work with Claude Code. |
| **The problem and its evidence** | 1. **A customised workspace cannot upgrade.** The upgrade rehearsal on 2.7.2 appended one deny rule to the managed `.claude/settings.json` and was refused: the only options were "revert" or "never upgrade". 2. **Nothing checked the public tree for protected text.** The 7 method files that are public on purpose were a judgment call per pull request, not a check. 3. **"Works with Claude Code only" was unwritten.** The Starter has no file for any other tool, and nothing said so or noticed a new tool-specific file. |
| **If we do nothing** | Clients who tighten permissions are stuck on the version they installed, which is how a client ends up without a safety fix. |
| **What changes for a client** | 1. **A file of their own: `.claude/settings.local.json`.** Claude Code merges it over the managed settings. No install, upgrade, rollback or `verify` ever writes, replaces or removes it. The upgrade docs have a new "Your own settings" section, and the refusal for an edited `settings.json` now points to it. 2. **Six managed files change, two are added** (the installer's new commands and the docs). 3. **Nothing of theirs changes.** No seed line this time. |
| **The chosen fix, and why** | An override file the tools already support, rather than teaching the installer to tolerate edits to managed files. Tolerating edits would make `verify` mean nothing. Claude Code's settings documentation lists project-local settings above shared-project settings and says list settings such as `permissions.allow` merge. |
| **The simpler alternative** | Tell clients never to edit `settings.json`. That is what 2.7.2 did, and the rehearsal shows what it costs. |
| **The upgrade test** | **Passed,** with the real installer: a 2.7.2 workspace with its own skill, data, `CLAUDE.md` rule and a settings override, upgraded to 2.8.0 and rolled back. The override was byte-identical after upgrade and after rollback, ignored by git and committed on purpose; the whole workspace was byte-identical after rollback; `verify --repo` matched. An edited managed `settings.json` is refused with the pointer, and moving the change to the override lets the upgrade through. Also: 247 unit tests (184 before), 60 integration checks (55 before), 40 skill-validator tests, 17 PR-floor tests, 49 hook tests. |
| **Downside and recovery** | The override cannot remove a permission rule or change what the release's hooks do: lists merge, so ours stay, and a request to change them is a request for a release. It is untracked by default, so the pull-request `boundary` check never sees it; the guide says so. Recovery is the usual one: set 2.8.0 to `withdrawn` and the installer refuses it; `rollback` is tested. |
| **Why you** | Approval is a human act (ruling D3). Protection also requires a code owner's review on release files. |
| **Exact place, steps and success** | 1. **Say:** "Approve starter 2.8.0 at ffafd5f". 2. Lane 0.1 records the approval, tags `starter-2.8.0` once `check-tag` passes, and marks 2.7.2 `superseded`. 3. A founder reviews and approves the pull request; it is merged with a merge commit. **Success:** `main` equals the `starter-2.8.0` tag and shows `protected: true`. |
| **State** | **A new decision.** Next owner: lane 0.1 (approval commit and tag), then Chat Zero (the merge). |
| **Evidence** | `releases/starter-2.8.0.json` (a draft until approved) and the pull request description. |

## Two decisions that are separate from this release
- **Which of the 7 public method files stay public.** `release/public_methods.json` lists them one by one with a reason and pins their exact bytes. Nothing here removes or flags any of them. The scan exempts exactly that list, so a founder who pulls one deletes the entry and the file.
- **Whether to rewrite git history.** This change deletes 7 files under `evidence/` that named staff and private repositories. Git history still holds them. A rewrite is a founder decision and is not done here.

## What is not claimed
- The protected-text scan is a tripwire for copy and paste, not a proof that no protected idea is present. It needs a private fingerprint list; the public CI proves the mechanism with an invented paragraph and says `NOT RUN` where the list is not configured.
- Claude Code is the only tool marked `verified`, by named tests of the file layout and hook contract. No other tool is supported or verified, and no adapter was added.
