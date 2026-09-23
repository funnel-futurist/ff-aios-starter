# Release brief: AIOS Starter 2.6.0

**Written for:** Phoenix, before being asked to approve anything. About three minutes.

## The decision in one line

Approve AIOS Starter 2.6.0, the first version of the client template that clients can install, check and upgrade safely - so that from now on you ship a known version instead of whatever happens to be on `main` the day someone clicks "Use this template".

## What this release is

Today a client gets their AIOS by clicking "Use this template". That copies the repo as it stands that day, and then nothing connects them to it ever again. Nobody can tell which version a client has, whether they have edited the system files, or what would change if they updated. Our README promised they could "re-pull improvements on demand". There was no way to do that.

2.6.0 adds the missing layer, and nothing else about how the template works changes:

- **Install** a pinned version into a clean folder, and prove it by re-checking every file that landed.
- **`/start`** tells whoever opens the workspace who they are, what their role is allowed to do, which version is installed, and whether it still matches.
- **Upgrade** to a newer version without touching the client's own work - their `CLAUDE.md`, foundations, deliverables, logs, and anything they have created.
- **Roll back** if an upgrade goes wrong, including if the computer dies halfway through.
- **Adopt**, which pins a workspace made the old way onto a version, if its files match exactly.

It also fixes four things that were quietly broken in the template itself (see "What changes for clients").

| | |
|---|---|
| Files in the release | 282 - 246 the release owns and keeps up to date, 36 starter files that become the client's the moment they land |
| Skills | 24 |
| Pinned to | one exact commit, plus a fingerprint of every file. If a single byte changes, it refuses to install |
| Status now | **DRAFT** - built, tested, waiting for you |

## What changes for clients

**Clients who already have a workspace: nothing, today.** There is no automatic update, and that is deliberate. Approving the release makes it *available*; nobody's workspace changes until someone runs the upgrade or adopt command on it.

**Clients who create a new workspace after this merges** get the new tools and these four fixes:

1. **The code-owner file was dead.** It still said `[REPO_OWNER]` where names should be, so GitHub matched nobody and the "these files need a review" rules protected nothing - while every checker in the repo reported it as fine. It now names real accounts, and a check fails loudly if the placeholders ever come back.
2. **The AI pull-request reviewer showed a red X on every PR for three months**, because no credential was ever configured, not because anything was wrong. It now says "AI review not configured" instead, which is the truth.
3. **The `pr-review` workflow named John as every client's code owner** and linked to an internal file clients cannot see. Both removed.
4. **A client-facing skill pointed at an old Google Doc** as its main training source. Per your decision, that material now lives in The Operator's Reset (SOP 2 of 5), so the skill names that instead.

One side effect you will see: a new workspace made with the old button inherits our code-owner file, which names our accounts, not theirs. A four-second check in their repo turns red and tells them the one command to put their own names in. That is intended - it is the check catching exactly the problem it was built for.

## How we know it works

- **134 automated checks - 87 unit tests and 47 end-to-end - all passing on GitHub's own Linux machine** - not just on my laptop. That distinction mattered: one real bug only appeared there. Running the tool leaves behind small cache files, my Mac hides them, Linux does not, and if they had shipped, every client's first upgrade would have refused to run. Fixed three ways, and tested on both.
- **Tested against all 282 real files**, in a stripped-down environment so a pass cannot depend on anything set up on my computer.
- **The dangerous cases were tried on purpose, and every one is refused.** Installing an unapproved version, a missing credential, someone without permission trying to upgrade, upgrading over a workspace someone has hand-edited, and killing the computer halfway through an upgrade (it recovers, and the client's files come out identical).
- **Two outside AI models reviewed it independently** and found seven real defects between them, including one where an upgrade could have written a file outside the client's workspace. All seven were reproduced, fixed and locked in with a test.
- **Scanned for leaked secrets and client names across all 282 files: zero found.**

## What it does not do

- **It does not enforce the code-owner rules.** Naming owners is necessary but not enough - GitHub only enforces them when branch protection is switched on, and it is off. That needs the admin account and is a separate choice (bottom of this page).
- **Role checks are a guardrail, not a lock.** They stop a VA wandering into the founder's lane by accident. Someone with the laptop can edit the file that says who is who. The real lock is GitHub permissions plus branch protection.
- **It is not proven on a client's machine yet.** It has been proven on two machines that are not a client's. Installing it for a real client is the next package.

## Risks, and how to undo

- **Nobody has reviewed PR #12 but AI.** It is large - about 7,200 lines - but almost all of that is the install tool and its tests, which clients do not edit. The nine existing files it changes are the ones worth your eyes:
  - `START_HERE.md`, `CONTRIBUTING.md`, `.claude/skills/README.md` - point to the new `/start` and upgrade steps
  - `.claude/skills/financial_teardown/SKILL.md` - names Operator's Reset instead of the old doc
  - `.github/CODEOWNERS` - real owners instead of placeholders
  - `.github/workflows/pr-review.yml` - the "not configured" fix, and John's name removed
  - `.gitignore` - stops cache files being committed
  - `.template_version.json` - it claimed 18 skills while the template shipped 23; it now lists all 24, including the new `/start`, and a test keeps it honest
  - `scripts/team/verify-branch-protection.sh` - now fails when protection is missing instead of passing
- **If something is wrong after approving:** set the release back to `withdrawn` and the tool refuses to install it. Nobody is on it until someone runs an install, so there is nothing to roll back in the wild.
- **If the merge itself is wrong:** revert the merge commit. `main` has no protection today, so nothing stops that, or anything else.

## The order it has to happen in

This is the one thing that is easy to get wrong, and it is why this brief exists rather than a request to "reply approved".

The release is currently pinned to a commit on the PR branch, not on `main`. This repo's recent PRs were squash-merged, and a squash merge creates a **new** commit - so the commit the release points at would not be on `main`, and would survive only as long as nobody deleted the PR branch. Approve now, delete the branch later, and the release you approved points at nothing.

So:

1. **Merge PR #12.**
2. **I re-cut 2.6.0 from the merge commit on `main`** - same content, a pin that cannot disappear. I re-run every check against it.
3. **Then it is approved**, recording your name and the time.

## Recommendation

**Approve it.** It fixes real problems, changes nothing for existing clients, and has been tested harder than anything else in the template. The review worth doing is ten minutes on the nine changed files, not the 7,000 lines of tooling.

## How to do it

**The easy way - one message.** In this chat, say: *"Merge #12 and approve starter 2.6.0."* I will merge it, re-cut the release from `main`, re-run the checks, and record the approval as yours with the time and where you said it. It has to come from you directly - a message relayed through another session cannot approve a release.

**Or do the merge yourself:**

1. Open https://github.com/funnel-futurist/ff-aios-starter/pull/12
2. Scroll to the bottom of the page, to the green merge button.
3. Click the arrow beside it and choose **"Create a merge commit"** - this keeps the tested commits on `main`. Squash also works, because I re-cut either way.
4. Click **Confirm merge**.
5. Tell me it is merged, and whether you approve 2.6.0.
6. I re-cut, re-check, and record your approval.
7. **How to verify:** the file `releases/starter-2.6.0.json` on `main` shows `"status": "approved"` with your handle, and running `python3 scripts/aios/aios.py release verify releases/starter-2.6.0.json` prints *"installable (pinned, intact, approved)"*.

## Separate from this release - neither one is needed to approve it

These make the code-owner rules actually bite. They are optional, and each has a cost.

**Turn on branch protection** (needs the admin account, which is not yours).
- *What it costs:* nobody can push straight to `main` any more, you included. Every change goes through a pull request, and a PR that touches a protected file needs a code owner to approve it. GitHub will not let you approve your own PR, so your PRs to those files wait for the other code owner, and theirs wait for you.
- *Can it be avoided:* yes. Leave it off and the code-owner file is decoration. A lighter middle option is to require a pull request but not code-owner review.
- *Where:* github.com/funnel-futurist/ff-aios-starter -> **Settings** -> **Rules** -> **Rulesets** -> **New ruleset** -> **New branch ruleset** -> target `main` -> tick **Require a pull request before merging** -> tick **Require review from Code Owners** -> tick **Block force pushes** -> **Create**. *Verify:* `bash scripts/team/verify-branch-protection.sh` stops listing failures. Menus move - I will check the current wording before you do it if you ask.

**Add Justine as a third code owner.** She is in the organization but has read-only access to this repo, and GitHub ignores a code owner who cannot write.
- *What it costs:* write access lets her push branches and, while `main` is unprotected, merge.
- *Can it be avoided:* yes. Two owners is enough to work. She is only needed as a third reviewer.
- *Where:* the same repo -> **Settings** -> **Collaborators and teams** -> **Add people** -> `justine-del` -> **Write** -> **Add**. Then tell me, and I add her to the file.
