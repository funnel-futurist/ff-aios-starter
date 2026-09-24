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
python3 scripts/aios/aios.py upgrade --release releases/starter-X.Y.Z.json --target .
python3 scripts/aios/aios.py rollback --target .   # back to the previous release
```

`start` and `verify` are safe to run any time and change nothing. `upgrade` and `rollback` are
founder-only.

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

## Two questions `verify` can answer

Without `--repo` it asks *"does this workspace still match what was installed?"*, using the record
in `.aios/install.json`. That record lives in your own repo, so a determined local editor could
change a managed file **and** its recorded hash, and the check would agree with itself.

With `--repo` it also re-derives every hash from the pinned commit in the source repository, which
catches exactly that. The output always says which of the two it ran. Use `--repo` when the answer
matters to somebody other than you.

## Exit codes

`0` ok · `2` package (unapproved, unpinned, drifted) · `3` role · `4` credential ·
`5` state (dirty or partial) · `6` verification failed · `7` sanitization · `8` governance.
