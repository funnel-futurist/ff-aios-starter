# Skill validation

Requires Git, a POSIX shell and Python 3.9 or newer. No external Python packages.

After cloning, install the versioned hook:

```sh
bash .githooks/install.sh
python3 scripts/verify_skills.py
python3 tests/test_verify_skills.py
```

The installer preserves other hooks. If a pre-push hook or core.hooksPath already exists, it refuses to replace it. Integrate the validation command into that hook deliberately; do not disable an existing secret scanner.

## What is checked

The report command inventories existing skills without changing them. The push gate checks changed skills in outgoing commits, including non-current branches and intermediate commits. Changes to referenced files also revalidate their consumers, including references shared between skills. It reads temporary snapshots without running skill scripts.

New or changed skills need a matching name, explicit scope boundaries, a definition of done with numbered or identified checklist items, literal Example: and Counter-example: labels, and resolvable local references. Producing skills need GATHER items such as G-1. The report also checks review/escalation and a named or explicitly unavailable quality example.

References must remain inside the repository. Workspace document links and recognized credential markers are refused in changed skills. This is a structural guard, not a complete secret scanner, IP classifier or quality review. Review every public change for private data, licensing and proprietary material.

Existing unchanged skills are not silently rewritten or grandfathered into an acceptance claim. Run the report to see their outstanding gaps.

## Rejected pushes

Fix the failing commit before publishing. A later good commit does not erase private or invalid content from outgoing Git history. The hook intentionally rejects bad intermediate commits too. Tests demonstrate this against disposable local bare remotes.

Git hooks are local and must be installed in each clone. They can be bypassed by a contributor; they are not server-side protection. Repository owners retain responsibility for reviewed PRs and protection settings.

## Verification

The test suite creates temporary repositories and exercises real good/bad pushes, working-tree mismatch, non-current branches, bad intermediate history, existing-hook preservation and missing-validator refusal, reference deletions, malformed skill roots and templated traversal. No public remote is changed.

No actual skill is added or ported by this validation package.
