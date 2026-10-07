# Installing and upgrading your AIOS

Your workspace has two kinds of file, and everything here follows from the difference.

| | |
|---|---|
| **Managed** | The system layer the release owns: skills, hooks, scripts, workflows, the setup docs. An upgrade replaces these. |
| **Yours** | Everything else: `CLAUDE.md`, your foundations, deliverables, logs, and every file you create. **No upgrade, rollback or install ever writes to these.** |

An upgrade changes the machine. It never touches your work.

## Why a release and not just "pull main"

A release is a **pin**: one exact commit, plus the sha256 of every file in it, plus a human's
approval. That means your workspace can answer three questions that "I cloned it in June"
cannot: exactly what you have, whether it still matches, and what changes if you upgrade.

Founder ruling **D3**: a workspace installs an **approved, versioned release**, never mutable
`main`. The installer enforces it - an unapproved or unpinned release is refused, and so is
one whose files no longer hash to what the manifest recorded.

## The commands

```bash
python3 scripts/aios/aios.py start                 # who you are, what you may do, what is installed
python3 scripts/aios/aios.py verify --target .     # does this workspace still match its release?
python3 scripts/aios/aios.py verify --target . --repo ../ff-aios-starter   # ...and does the record still match the pin?
python3 scripts/aios/aios.py rollback --target .   # back to the previous release
```

**Upgrade runs from a fresh copy of the Starter, not from inside your workspace.** The releases
and the exact commits they pin live in the Starter repository, and your workspace carries
neither. So, from an up-to-date clone of `ff-aios-starter` next to your workspace:

```bash
cd ../ff-aios-starter && git pull
python3 scripts/aios/aios.py upgrade --release releases/starter-X.Y.Z.json --target ../my-workspace
```

That also means the upgrade always runs the *new* release's tool, so a fix in the tool reaches
you on the upgrade that installs it. Commit your workspace first: an upgrade refuses a workspace
with uncommitted work.

`start` and `verify` are safe to run any time and change nothing. `upgrade` and `rollback` are
founder-only.

## Getting an exact release

Every release is a record, `releases/starter-X.Y.Z.json`, plus a tag, `starter-X.Y.Z`. The
record lives in `releases/`, which the package never ships, so the commit that records a
founder's approval installs exactly the same files as the commit it pins. **That approval
commit is the one tagged.** A checkout of the tag then carries the approved record, and the
installer accepts it.

```bash
git clone https://github.com/funnel-futurist/ff-aios-starter.git
cd ff-aios-starter
python3 scripts/aios/aios.py release check-tag starter-X.Y.Z --release-id starter-X.Y.Z
git checkout starter-X.Y.Z        # only once check-tag says the tag is the approved release
```

`check-tag` proves both halves: the record at the tag is approved and pinned, and every
package file at the tag is byte-identical to the pin. If it refuses, don't install from the
tag.

**starter-2.6.0 is the known exception.** Its tag was placed on the pinned commit before the
approval was recorded, so the record inside the tag is an earlier draft and `check-tag`
refuses it. Published tags are never moved. Install 2.6.0 from the normal copy instead: the
installer still materialises only the pinned 2.6.0 files and re-hashes them on disk.

## Installing a new workspace

```bash
python3 scripts/aios/aios.py install \
  --release releases/starter-X.Y.Z.json \
  --target ../my-new-workspace \
  --config my-org.json
```

The target must be clean. The installer materialises every file from the pinned commit,
verifies the result by **re-hashing what landed on disk**, and writes `.aios/install.json`
recording exactly what you have. If the readback disagrees with the manifest, the install fails
- "the installer said it worked" is not evidence.

### Your organization config

```json
{
  "schema": "ff-aios-starter/org-config@1",
  "org_id": "acme",
  "repository": "acme/acme-aios",
  "people": [
    {"github": "acme-founder", "role": "founder", "display_name": "Dana"},
    {"github": "acme-va", "role": "operator", "display_name": "Sam"}
  ],
  "credentials": {"ANTHROPIC_API_KEY": "env:ANTHROPIC_API_KEY"},
  "code_owners": {"REPO_OWNER": ["@acme-founder"], "PRIMARY_REVIEWER": ["@acme-founder"]}
}
```

**Credentials are references, never values.** `env:NAME` reads an environment variable;
`dotenv:NAME` reads a name from your `.env`. The config records *where* the key lives, never
the key. A config carrying an actual key is refused.

A missing **required** credential fails the install loudly and writes nothing. A missing
**optional** one installs and says so on every `start` and `verify`. Neither one leaves you
with a workspace that looks fine and quietly does half its job.

## Already have a workspace from "Use this template"?

That button copies whatever was on the default branch that day, so nothing records which
version you have. `start` will say `UNPINNED`. To put it on the contract:

```bash
python3 scripts/aios/aios.py adopt --release releases/starter-X.Y.Z.json --target . --config .aios/config.json
```

Adopt succeeds only if your files match that release byte for byte. If it refuses, you have
local changes to the system layer - that is information, not a failure.

## What upgrade actually does

1. Refuses unless the new release is approved, pinned and intact.
2. Refuses if your workspace has **drifted** (a managed file edited by hand) or if git has
   uncommitted changes. Both are refusals rather than overwrites, on purpose.
3. Refuses if the new release ships a path that already exists as your own file.
4. Snapshots every managed file and writes a journal **before** changing anything.
5. Replaces managed files. Adds new seed files only where they do not already exist.
   **Seed files are never upgraded:** `CLAUDE.md` and the foundation folders are written once and
   are yours from then on, so an improvement to them reaches an existing workspace only through
   the release notes.
6. Re-hashes everything and compares it to the new manifest.

If any step fails, it puts the workspace back and verifies that it did. If the machine dies
mid-upgrade, the journal survives and `rollback` recovers from it. Both paths are tested,
including against a hard kill.

## Rollback

```bash
python3 scripts/aios/aios.py rollback --target .
```

Restores the previous release's managed files, removes what the newer one added, and verifies
the result by readback. Your work is untouched in both directions - the test suite asserts the
fingerprint of every non-managed file is identical after an upgrade *and* after a rollback.

## Roles, honestly

Identity comes from your authenticated GitHub CLI. Your role comes from the people map in
`.aios/config.json`. An operator gets the operator lane; upgrades, rollbacks and governance are
founder-only, and the tool refuses anyone else.

Some paths belong to the founder lane: the offer economics folder, `.github/`, the people map and
role policy, Claude's safety settings and hooks, and the install tool itself (the full list is
`paths_denied` in `.aios/roles.json`). They are held in two places:

1. **In the session.** Claude will not edit them for an operator, or for anyone it cannot
   identify. It says why and offers to hand the change to a founder.
2. **At the pull request.** The `boundary` check fails a pull request that changes them, unless
   the author is a founder or a founder has approved that exact commit. It reads the rules from
   the base branch, so a pull request cannot loosen its own check.

What neither stops, honestly: somebody editing files by hand in their own terminal and pushing
straight to `main`. Only GitHub can stop that, with branch protection that requires pull
requests, code-owner review and the `boundary` check. Turn it on, then prove it:

```bash
python3 scripts/aios/aios.py governance check
bash scripts/team/verify-branch-protection.sh
```

A `CODEOWNERS` file full of `[REPO_OWNER]` placeholders enforces **nothing** - GitHub matches
no one - and neither does a perfectly filled one if branch protection is off.

## What protects you, and when it doesn't

A safeguard that did not run is not a safeguard. Claude Code treats a hook that fails to start
(for example, because its program is missing) as a non-blocking error and carries on, and there
is no setting that makes a failed hook block. So each protection below holds only under its
condition.

| Protection | Holds when | When it does not hold |
|---|---|---|
| Founder-lane edits refused in the session | Python 3 is installed and `gh` is signed in (an unidentified person gets operator limits) | Python 3 missing on that computer: the hook can't start and Claude Code skips it. Nothing in the session can warn, because the warning needs Python too |
| Risky git commands stop and ask you first (force-push, `reset --hard` and similar). They are not blocked: you can still say yes | Node.js is installed | Node.js missing: the hook is skipped, so there is no extra question. `start` warns, and the warning is not protection |
| Pull request that touches the founder lane shows red | GitHub Actions runs (server-side, independent of the laptop) | Always runs; it can only **block** a merge with branch protection on |
| Branch protection | The repository belongs to a paid plan, or is public | A private repository on a personal free account can't have it. GitHub answers "Upgrade to GitHub Pro or make this repository public" |
| Installed files match the release | `verify --repo` against the source | Without `--repo`, `verify` only checks the local record, which a local editor could also change |

## Two questions `verify` can answer

Without `--repo` it asks *"does this workspace still match what was installed?"*, using the record
in `.aios/install.json`. That record lives in your own repo, so a determined local editor could
change a managed file **and** its recorded hash, and the check would agree with itself.

With `--repo` it also re-derives every hash from the pinned commit in the source repository, which
catches exactly that. The output always says which of the two it ran. Use `--repo` when the answer
matters to somebody other than you.

## For maintainers: approving a release

1. Cut the draft: `python3 scripts/aios/aios.py release build --version X.Y.Z --rev <commit on main>`.
   The builder can only write `draft`.
2. The founder approves that exact commit, in their own words. Record it in
   `releases/starter-X.Y.Z.json` (`status: approved`, `approval.approved_by`, `approved_at`,
   `basis`) and merge that change to `main`.
3. Tag **the commit that recorded the approval** with an annotated tag, then prove it:
   `python3 scripts/aios/aios.py release check-tag starter-X.Y.Z --release-id starter-X.Y.Z`.
   Push the tag only once that passes. Never move a tag that is already published.

## Exit codes

`0` ok · `2` package (unapproved, unpinned, drifted) · `3` role · `4` credential ·
`5` state (dirty or partial) · `6` verification failed · `7` sanitization · `8` governance.
