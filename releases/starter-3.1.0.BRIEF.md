# Release brief: AIOS Starter 3.1.0

**Written for:** the founder, before approving. About four minutes.

> **Candidate, not approved.** `releases/starter-3.1.0.json` is a draft pinned to `7ebf598959b5f97e5e36e6548ddea0db6af1b58a`. Nothing is tagged and nothing installs it until a founder approves that exact commit in their own words (ruling D3).

## Decision
**Approve AIOS Starter 3.1.0 at `7ebf598`.**
- It adds the one thing FF's own adoption needs (your G81 and G98 rulings): a way to bring the Starter into a repository that already exists, without overwriting anything. It also keeps who may approve founder-gated paths separate from who is a founder.
- For clients on 3.0.0 it's an ordinary upgrade: nothing moves. A 2.x client still gets the 3.0 folder move, as before. Review hardened three things that apply to every workspace, listed below: the committed install record is no longer trusted, a shallow clone can't upgrade, and an upgrade made before 3.1 is rolled back with its own installer. And, by the C3 choice in the delegated owner batch (#81 6234002893), a change to the list of which files are the installer's own needs a founder's approval.

## Principle
- **Only ever create.** Adopting into an existing repository never overwrites, merges or deletes a file of that repository's.
- **Nothing is inferred.** The repository's own committed plan names every path the release ships as adopted, kept as its own, or excluded. Anything unlisted, listed twice or covered by a catch-all refuses before a single write.
- **Review permission isn't founder status** (G98). A repository can name the accounts allowed to approve founder-gated paths. Founder status, and the founder-only actions, still come from each person's role.

## Evidence
**What changes**

| Change | What it means |
|---|---|
| **`aios adopt --existing`** (new) | A company's own repository adopts the release files its plan lists, and only those. Every adopted file must be absent; every file it calls its own must exist and is never written. It must be a git repository with the plan and its own role policy committed. Never a folder move, never a line added to `CLAUDE.md`. |
| **Rollback of an adoption** | It's journaled before its first write, and each file is recorded once it exists. `aios rollback` takes back exactly what it created and left unchanged, whether the adoption finished or was killed partway. Each new file appears whole, and can never replace a file that appeared meanwhile. |
| **Upgrading an adopted repository** | It writes only what the plan adopts, and the plan must still be committed. A new release path must be classified first, or the upgrade refuses. A file the plan stops adopting stays as the repository's own. |
| **The ownership list is founder-gated** (new; C3 with A, from the delegated owner batch) | The install record and an adoption's plan say which files are the installer's own, and an upgrade or the undo acts on them. Both are now in the founder lane, by the same rule as the Starter's other sensitive files: a pull request from anyone who isn't a founder needs a founder's approval (or a declared founder-lane reviewer's) to change either, and Claude won't edit them for an operator. Every founder-lane path is now compared the way a Mac or Windows disk resolves names, so a capitalization or Windows spelling of one counts as that path. The Starter's role policy and CODEOWNERS template list both. A repository with its own role policy, like FF's, adds them itself with a CODEOWNERS rule for each; until it does, `instance check` fails and `start` shows founder review NOT RESTORED. |
| **`founder_lane_reviewers`** (new, optional) | It names who may approve founder-gated paths. `instance check` and the pull-request boundary check both honour it, and when it's set it's the whole permission. Unset, nothing changes for clients. |
| **Safer state files, for every workspace** | The installer's own records are written through unique temporary files, never a fixed name that something else could be. A release may never ship the installer's state paths, compared the way a Mac or Windows disk compares names. No install, adoption, upgrade, folder move or rollback writes under a submodule, initialized or not; each refuses before its first write. |
| **The committed install record isn't trusted, for every workspace** | Anyone's pull request can edit `.aios/install.json`. So upgrade and `verify --repo` check the record against the release source and git history: the pinned release, its managed files, its folder layout, the seed lines (and, for an upgrade, the seeds already handled), and whether the workspace was adopted. On a fresh clone an adopted repository's record may call a file the release's only if git history shows the installer made it. Rollback acts only on the record its last operation here wrote or, to undo an adoption, the one committed with it. An edit that fails these checks is refused by upgrade and rollback, with nothing changed, and reported by verify. A release or record pin that would reach git as an option (`--output=...`) is refused before git runs. Every command that reads the record or the plan is listed, with what it trusts, in the install guide. |
| **A shallow clone can't upgrade** | A `git clone --depth 1` can't show that history, so an upgrade, or undoing an adoption, refuses until `git fetch --unshallow`. In a client's repository, the workflows the Starter ships never upgrade or undo an adoption against their own checkout (the job that runs the installer's tests runs only in the Starter's own repository, on temporary repositories it makes), so CI is unaffected. |
| **Undoing a finished adoption** | It needs the release's source, `aios rollback --repo <your ff-aios-starter clone>`, so only that release's files are removed. On a fresh clone it refuses if an upgrade or rollback came after the adoption, or if the record was added more than once: undo it where it ran, or with git. |
| **Rolling back an upgrade made before 3.1** | Refused, changing nothing: those installers kept no copy of the record they wrote. Roll it back with that release's own installer (`python3 scripts/aios/aios.py rollback --target .`, run in the workspace) or with git. |

**Who reads the install record, and what each one trusts**
- **Upgrade, and its dry run:** each field checked against the release source and git history, plus this machine's note of its last operation when there is one; the plan file you committed, which it applies.
- **Verify:** with `--repo`, the same checks, reported rather than acted on. Without it, only the record's own consistency, its paths and its git history.
- **Rolling back an upgrade:** only a record equal to the copy that upgrade kept on this machine.
- **Undoing an adoption:** only the record and plan as committed with the adoption (added once), the release source, and git history since.
- **Recovering an interrupted operation:** its local journal, and a record that journal names.
- **Install and adopt:** they write the record, and read it only to refuse when one is already there.
- **`aios start`, `instance check` and the upgrade's closing notice:** the release line and any drift it shows, and which plan path an adoption names, so the founder-review check can require the record and that plan in the founder lane. They only report. The record is itself in that lane, so changing the plan path it names needs a founder's approval.
- **The new-release notice:** the installed version, which only changes the notice's text.
- **Clearing a dead lock:** only whether a record exists.
- **The notice and identity caches:** written only where the repository has no file of its own. Never read from a copy it tracks or reaches through a link or a submodule; a malformed one is ignored, so it can't switch off the edit check or break `aios start`.

**Every write, accounted for (the write-site inventory)**
`tests/aios/test_write_sites.py` reads the package's source and lists every call that writes to disk, git commands included (written out, through a wrapper, or built in a variable): 147 calls in 56 functions. A git command counts as reading only in a listed read-only form, flag by flag. Each function is classified, and the test fails on any write it doesn't list, or on a check taken out from before a write.

| Where | Functions (calls) | Checked how, before the first write |
|---|---|---|
| Install, adopt, upgrade, rollback and their recovery | 11 (47) | the function itself checks for another repository, by a named check |
| Their helpers | 10 (23) | reached only from those, after the check (the test follows every call chain) |
| The workspace lock and its guard | 5 (9) | the guard refuses a `.aios` or `.aios/backups` that is another repository; one removes only the guard file it made |
| `util` and `layout` write helpers, and `util.git` | 14 (43) | every call to one is itself a classified write; the temporary-file and local-cache helpers also check for themselves |
| Read-only git whose command is built in a variable | 2 (2) | allowlisted: `diff-tree`, `ls-files` and `ls-tree` only, which the scanner can't read from the variable |
| An HTTP request through `urllib` | 1 (1) | allowlisted: the scanner counts it because it can't tell what an attribute's `open` opens |
| Commands that write to an `--out` path, and release tooling | 6 (7) | allowlisted: not part of a workspace's install, adoption, upgrade or rollback |
| The vault tool (`aios workspace`), its git clone, fetch and merge included | 7 (15) | allowlisted: writes only in the vault's own folder, which holds no install record |

Its control tests remove one check (the rollback's), add an unlisted write, and add git writes through each wrapper; each makes it fail. At `75753b0` it finds the lock written before any check, the gap round 60 fixed. The submodule sweep then proves each check covers the paths that operation actually writes.

**And at runtime (the audit backstop)**
Python's audit hooks record every write the installer actually makes, whatever its source looks like, with every git command it runs. They run during the submodule sweep and in every command-line process of the integration test. In the pinned run's integration test that was 4,890 writes and 1,430 git runs across 27 processes (4,470 writes on GitHub's Linux runner). The checks: every write stays in the test's own folder or the system's temporary folder; nothing goes into a `.git` folder but the installer's guard; nothing goes into the Starter's source repository; every git command only reads. In the sweep, no write lands inside the other repository, not even one made and taken back before the refusal. Its control plants a write the static scanner can't read (an `open` reached through `getattr`, removed again before the refusal), and the audit catches it.

**How review findings are graded (from round 63)**
- **Medium or above:** a reachable write by the product, before its refusal or into another repository, that the runtime audit misses. Record-trust findings are graded as before.
- **NIT:** a gap in the static scanner's reading of the source, with no such write behind it. It's fixed like any finding: the review counts as clean only with none open.

**What was proven** (detail in `evidence/dispatch/p22-starter/release-3.1.0/`):
- **FF's own adoption, rehearsed on a throwaway copy of ai-os:** 18 files created and read back; no tracked file changed, `CLAUDE.md` and `01_Foundations` included; all 12 founder-lane paths pass with the declared reviewers, the install record and the plan among them, and both ownership checks pass; rollback returns the copy exactly. **15 checks passed, 0 failed.** Nothing was written to ai-os.
- **Every existing client:** upgrades to 3.1.0 from 3.0.0 and from every 2.x release keep each client file byte for byte, roll back exactly and recover from hard kills. **219 checks passed, 0 failed.**
- **915 tests** from a fresh clone, and GitHub's own checks are green on the exact head. Each code fix from review has a test shown to fail without it.
- **Independent review:** Codex approves `7ebf598` with no findings (69 rounds in all: through round 65 alongside Gemini, whose findings were all fixed; from round 66, Codex alone, per the delegated owner batch (#81 6234002893)).
- **Scans:** no client name in what 3.1 adds; FF's protected text: none at or over the overlap rule (7 single shared windows of generic code, under it), every protected file compared (0 unscanned).

## Recommendation
**Approve.** It's the implementation route your G81 approval set and your G98 approval shaped. It is carded only once the independent reviewer (Codex, one subscription reviewer, per the delegated owner batch) approves the exact pin with no findings. If four more rounds end with findings still open, they come to you together as one list instead, with no severity waived. Every code finding was fixed with a test shown to fail without its fix; findings in the documentation and this brief were corrected and checked by the next review round. For existing clients it changes nothing but safer internals and the hardening listed above.

## Consequence
- **If approved:**
  - Clients upgrade from 3.0.0 as usual, or from 2.x with the 3.0 folder move as before.
  - FF can then open its own adoption pull request into ai-os: the 18 files you approved (G98), FF's own role policy and plan with the ownership list in its founder lane, and two CODEOWNERS rules for it (committed first), and the people map and install record the adoption writes, all in one commit. That's one reviewed pull request, after a rehearsal on a copy.
- **Downsides:**
  - The adopt mode needs a disk with hard links. A Mac's APFS, Linux's usual file systems and Windows NTFS have them; FAT and exFAT drives don't, and adoption refuses there and takes back anything it made.
  - A repository's plan must be kept current: each release that ships a new path needs it classified before upgrading.
  - A shallow clone must fetch its full history before an upgrade.
  - After upgrading, an existing client adds two CODEOWNERS rules, for `/.aios/install.json` and `/.aios/adoption.json` (`docs/human_steps/restore_founder_review.md`). CODEOWNERS is theirs, so the upgrade doesn't write it; until they do, `instance check` fails.
  - An upgrade an older installer made is rolled back with that installer, not this one.
- **Recovery:** `aios rollback` undoes an adoption or an upgrade. Setting 3.1.0 to `withdrawn` makes the installer refuse it.
- **If not approved:** FF's adoption waits; clients stay on 3.0.0.

## Owner action
1. **Say:** "Approve starter 3.1.0 at 7ebf598".
2. CL03 records the approval:
   - a `releases/`-only commit, with the record re-cut byte-identical;
   - 3.0.0 marked `superseded`;
   - the tag `starter-3.1.0`, once `check-tag` passes.
3. **Platform approval:** one code owner's approval on the release pull request.
4. Chat Zero merges as the FF Agents App. **Success:** `main` equals the tag.

## What is not claimed
- **No run on Windows.** Its file lock, byte-for-byte record writes and permission check are tested with stand-ins only, and hard links on NTFS aren't tested.
- **FF's adoption hasn't happened.** It was rehearsed on a throwaway copy of ai-os, and nothing was written to ai-os.
- **The protected-text scan is a copy-and-paste tripwire,** as before.
