# Release brief: AIOS Starter 2.7.0

**Written for:** Phoenix, before being asked to approve anything. About four minutes.

> **Approved 2026-10-06 at `c5dce56`**, not `d3f360d`: `c5dce56` is `d3f360d` plus the version label (`.template_version.json` says 2.7.0). Phoenix's words and the line he answered are in `releases/starter-2.7.0.json`.

## The decision in one line

Approve AIOS Starter 2.7.0 at `d3f360d`. It is 2.6.1's fixes plus three things:
- the Obsidian Workspace Kit;
- setup guides that finally match the installer;
- a way to prove a release tag really is the approved release.

It replaces 2.6.1, which was never approved.

## Where this stands (2026-09-29)

| Step | Status |
|---|---|
| 1. Build and test the changes (PR #21, which carries P01's #20) | **DONE.** 156 of 156 tests; every PR check passes |
| 2. Cut 2.7.0 and run it the way a learner does | **DONE.** Nine rehearsals, below |
| 3. Approve | **WAITING FOR YOU.** Not recorded. The release is `draft` |
| 4. Merge PR #21 with a merge commit, then tag | After step 3. A person merges; the repository's own gate is "manual merge only" |

- **Exact candidate:** `d3f360de286146da7bfde0817114fd85723eafe1` on branch `exec/p22-v4-clean-vault-20260928`.
- **In the release:** 110 files. The release owns 74, and 36 become the client's the moment they land. There are 20 skills.
- **Upgrades:** from 2.6.0 onward.
- **Release scan:** 0 findings on the exact file set. The noisier pass had 50 hits, and every one was an ordinary word ("template", "weekly").

## What changes for whoever installs next

1. **2.6.1's fixes, which nobody has yet.**
   - Founder-only files are enforced, in Claude's session and at the pull request.
   - Anthropic's document skills come from Anthropic instead of being copied.
   - The upgrade-lock bug is fixed.
   - 2.6.0, the only approved release today, has none of these.
2. **The Obsidian Workspace Kit.**
   - One vault over the company's own repositories. A repository still mixing a private method or another company's material can't be downloaded into it.
   - A copy left behind is moved out on request, never deleted.
3. **Guides that match the product.**
   - Install with the installer, not "Use this template".
   - Git, Python 3, Node.js and the GitHub CLI are named up front.
   - Setup happens on the desktop app, not the web.
   - The API key is optional.
   - A new "learning sandbox" page comes before any certification.
4. **Exact releases by tag.** `release check-tag` proves a tag carries the approval and installs the pinned files byte for byte.
   - 2.6.0's tag fails it: the tag was placed before its approval was recorded, so it carries an older draft.
   - Published tags are never moved. From 2.7.0 the approval commit is the one tagged.

## How it was tested (the learner's path, not just unit tests)

A fresh GitHub clone of the candidate, installed into empty repositories. The full script and its output are in `evidence/dispatch/p22-starter/rehearsal-2.7.0/`.

| # | What was tried | Result |
|---|---|---|
| R2 | Install the real draft record | Refused: draft, no approval. Nothing is inferred |
| R3 | Install the candidate, push, `start`, `verify --repo` | Founder role shown; "matches the installed release"; no `releases/`, `tests/` or `evidence/` shipped |
| R4 | Claude editing a founder-only file | Founder allowed; operator refused; ordinary work allowed; unidentified (no `gh`) refused, with the desktop route named |
| R5 | Operator pull request touching founder-only files | Check fails; passes only after a founder approves that exact commit |
| R6 | Safety hooks with and without Node.js | With Node, force-push and `reset --hard` stop and **ask** (not block). Without Node the hook can't start, and Claude Code carries on. `start` warns |
| R7 | Upgrade approved 2.6.0 to this candidate | Upgrade succeeds, `verify` matches, the learner's own files and edits survive. About 215 changed files remain for the learner to commit, most of them 2.6.0's copied Anthropic skills leaving |
| R8 | Tag on the approval commit vs on the pin | Approval-commit tag passes `check-tag`; pin tag refused |
| R9 | Workspace Kit over this sandbox | A not-split Design repo is refused as active. The vault holds 124 files, 0 other-client folders, 0 Design method files. A later phase switched on appears on START-HERE and the maps. Switched off, its copy is reported, then moved (not deleted) |

## What protects a learner, and when it doesn't

Claude Code treats a hook that can't start as a non-blocking error, and it has no setting to change that.

- **Python 3 missing:** the founder-file hook is skipped, and nothing in the session can warn.
- **Node.js missing:** the git guard is skipped. `start` warns, and a warning is not protection.
- **Pull-request check:** runs on GitHub either way. On a personal free private repository it can't *block* a merge: GitHub answers "Upgrade to GitHub Pro or make this repository public". Nothing was bought (D8).

## Not in this release

- **FF's Design capability.** It isn't callable by a client yet (P04, extraction step 3). The Design side of the pilot is marked "not available", not faked with Anthropic's skills.
- **A real Obsidian-app test.** Only a person can click "Open folder as vault". That's Febi's test T7.

## What happens when you approve

1. I record your approval in `releases/starter-2.7.0.json` with the time and your words. In the same change I mark 2.6.0 `superseded`, so nobody installs the version with the upgrade bug and no founder-only enforcement, and I mark the never-approved 2.6.1 `superseded` too.
2. You, or John, merge PR #21 **with a merge commit**. A squash would drop the pinned commit from `main`, and I would re-cut and ask again.
3. I tag the commit that recorded your approval `starter-2.7.0` and run `check-tag`, and I push the tag only when it passes.

**If something is wrong after approving:** set 2.7.0 to `withdrawn`, and the tool refuses to install or upgrade to it. Nobody is on it yet.

## Recommendation

**Approve it.** It's the first release a learner can install that has the founder-only protection, the guides that match it, and the Obsidian kit. Febi's pilot needs all three: Milestone 3 tests the protection, and Milestone 4 needs the kit.

## The exact words

One message, in this chat, from you directly:

*"Approve starter 2.7.0 at d3f360d."*

**How to verify afterwards:**
- `releases/starter-2.7.0.json` on `main` shows `"status": "approved"` with your handle.
- `python3 scripts/aios/aios.py release check-tag starter-2.7.0 --release-id starter-2.7.0` prints "the tag carries the approval and installs the pinned files byte for byte".
