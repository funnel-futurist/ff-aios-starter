# Release brief: AIOS Starter 2.6.1

**Written for:** Phoenix, before being asked to approve anything. About three minutes.

## The decision in one line

Approve AIOS Starter 2.6.1. It is the version you accepted in the walkthrough: Anthropic's document skills are installed from Anthropic instead of copied, "ask a founder first" is enforced, and the skill list tells the truth. It also fixes a bug that would have stopped every real client from ever upgrading.

## Where this stands (2026-09-24)

| step | status |
|---|---|
| 1. Merge the accepted changes (PR #16) | **DONE** - 15:42 UTC, merge commit `8045586` |
| 2. Cut 2.6.1 and run it for real | **DONE, and it found a bug** - see "The bug the real run found" |
| 3. Fix the bug (PR #17) | **DONE** - 15:52 UTC, merge commit `8285b5d` |
| 4. Re-cut 2.6.1 from the fixed `main`, run every check | **DONE** - all green, table below |
| 5. Approve | **WAITING FOR YOU** - not recorded. The release is `draft` |

**Final commit:** `8285b5d35900244639175177fad73a570ede16c2` on `main`.

| | |
|---|---|
| Files in the release | 98. 62 the release owns and keeps up to date, 36 starter files that become the client's the moment they land. 2.6.0 had 282, and 186 of those were Anthropic's |
| Skills | 20 in the repo, plus Anthropic's four document skills, installed from Anthropic |
| Status now | **DRAFT** - merged, cut from `main`, tested, waiting for you |

## What changes for clients

**Nobody is on 2.6.0 yet**, so no client sees a change today. For whoever installs from now on:

1. **Word, PDF, PowerPoint and Excel still work, and they come from Anthropic.** The client trusts the folder in Claude Code, then types one line during onboarding: `/plugin install document-skills@anthropic-agent-skills`. They get Anthropic's current version and its future fixes. `THIRD_PARTY_NOTICES.md` credits Anthropic.
2. **Founder-only files are actually founder-only.** These are the offer economics folder, the people and role files, Claude's safety settings, `.github`, and the install tool. Claude will not edit them for an operator. A pull request from an operator that touches them fails until a founder approves that exact version.
3. **The skill list in `CLAUDE.md` and the catalog is complete**, and a test fails if it ever drifts again.
4. **Upgrades work in a real workspace.** Before the fix, no workspace kept in git could upgrade. Details below.

## The bug the real run found

Every test passed. Then I did what a client would do: installed the real, approved 2.6.0, saved it in git, and upgraded it to 2.6.1. The upgrade refused, saying there were unsaved changes when there were none.

The cause: an upgrade first creates a small lock file, so two upgrades cannot run at once, and then checks that git has nothing unsaved. Git saw the lock file. So **every workspace kept in git - which is every real client workspace - would have refused every upgrade, forever.** No test had ever run an upgrade in a workspace under git, because the check is skipped without git.

- It has been in 2.6.0, the version you approved, since its lock fix. **No client installed 2.6.0**, so nobody was hit.
- Fixed in PR #17. The tool ignores its own lock file and nothing else, so real unsaved work still blocks an upgrade. A new test fails on the old code with the exact same refusal.
- Writing the fix turned up a second error. The guide told clients to run the upgrade from inside their workspace. That cannot work, because the releases live in the Starter repo, not the workspace. Upgrades now run from a fresh copy of the Starter pointed at the workspace. That also means the new release's tool is always the one that runs, so a 2.6.0 client gets this fix on the upgrade that installs it.

## How we know it works

| check, against `8285b5d` | result |
|---|---|
| Unit tests | 120 / 120 pass |
| End-to-end on the real files, clean environment, workspace now saved in git | 55 / 55 pass |
| PR static checks + risky-git guard | 17 / 17 and 49 / 49 pass |
| Code-owner check | passes |
| Secret and client-name scan, 98 files | 0 findings on specific names. The 11 matches for the two client names that are also ordinary words are the same 11 already read by hand, all the ordinary word |
| **The real path** | Real 2.6.0 installed and saved in git, then upgraded to 2.6.1 the documented way. The Anthropic copies are gone and the hook, check, notice and plugin line are in, with no lock left behind. The workspace verifies itself. It rolled back to 2.6.0, was saved again, and upgraded again. The installed hook refused an operator's edit to the people map |

The approval used for that real-path run is the test-only fixture string, never a person's name.

## What it does not do

- **It does not prove the plugin install works on a client's machine.** I checked the settings against Claude Code's documentation and Anthropic's published catalogue, but did not run the install in a real session, because that would change your own Claude setup. **This is the first thing Febi tests.**
- **It does not stop a direct push to `main`.** Only branch protection does that. The checker says so and fails until protection is on and the `boundary` check is required.
- **Claude's shell commands are not inspected**, only its file edits. The pull request check is the backstop.
- **It is not proven by someone who did not build it.** That is Febi's project.

## Risks, and how to undo

- **If something is wrong after approving:** set 2.6.1 to `withdrawn` and the tool refuses to install or upgrade to it. Nobody is on it yet.
- **If a client upgrades and wants out:** `rollback` returns them to 2.6.0 - tested above - including the copied document skills.
- **If a merge is wrong:** revert `8285b5d` or `8045586`.

## Recommendation

**Approve it.** It is what you accepted, it fixes an upgrade bug that 2.6.0 would have handed every client, and it was run the way a client runs it. When you approve, I mark 2.6.0 `superseded` in the same change, so nobody installs the version with the upgrade bug.

## How to do it

One message, in this chat, from you directly: *"Approve starter 2.6.1 at 8285b5d."*

I then record your approval with the time, mark 2.6.0 superseded, and merge the release to `main`.

**How to verify:** `releases/starter-2.6.1.json` on `main` shows `"status": "approved"` with your handle, and `python3 scripts/aios/aios.py release verify releases/starter-2.6.1.json` prints *"installable (pinned, intact, approved)"*.

No client install happens either way until you accept Febi's results.
