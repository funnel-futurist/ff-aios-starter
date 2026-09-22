---
name: start
description: The role-scoped way into this workspace. Use at the very start of a session, when someone asks "what can I do here", "where do I start", "what's installed", "which version am I on", when a new teammate opens the repo for the first time, or before any upgrade, rollback or credential change. Establishes who is working, what their role may do, which release is installed, whether the workspace still matches it, and whether credentials and governance are actually configured. Pairs with /start-my-day, which handles the git rhythm.
---

# /start - who you are, what you may do, what is installed

`/start-my-day` gets you safely onto a branch. **This gets you safely into the right lane.**

Run it and read the output back to the operator in plain language. One command:

```bash
python3 scripts/aios/aios.py start
```

Add `--entry founder` only if they explicitly ask for the founder lane. If their role does not
carry it, the command refuses with exit code 3. **That refusal is the feature. Do not work
around it, do not suggest editing `.aios/config.json` to grant themselves a role, and do not
re-run with different arguments to get a different answer.** If they believe their role is
wrong, a founder changes the people map through a reviewed pull request.

## What the output means

| Line | What to tell them |
|---|---|
| `you:` | who GitHub says they are. Not the name in a local file, the authenticated account. |
| `role:` | founder / co_founder / operator, from the workspace's people map. |
| `entry:` | the lane they are in, and the moves that belong to it. |
| `release:` | the pinned release this workspace runs, and whether the files still match it. |
| `UNPINNED` | this workspace was never installed from an approved release. See below. |
| `DRIFTED` | a file the release owns has been edited by hand. See below. |
| `cred:` | each credential **reference** and whether it resolves. Never a value. |

## The three answers that need a human sentence, not a shrug

**UNPINNED.** The workspace was created with "Use this template", which copies whatever was on
`main` that day. Nothing records which version they have, so nothing can tell them what changed
or upgrade them safely. Say that plainly, then offer to pin it:

```bash
python3 scripts/aios/aios.py adopt --release releases/<approved>.json --target . --config .aios/config.json
```

Adopt only succeeds if their files match that release byte for byte. If it refuses, they have
local changes to the system layer - that is information, not a failure.

**DRIFTED.** Somebody hand-edited a file the release owns. Upgrades are refused until it is
resolved, deliberately: the alternative is an upgrade that silently overwrites their change.
Show them which file, and ask whether the edit should be kept (move it into their own file, or
propose it upstream) or discarded (restore it from the release).

**A missing required credential.** The install already refused, loudly, on purpose. A workspace
that starts up looking fine while half-configured is the expensive failure. Credentials are
always references - `env:NAME` or `dotenv:NAME` - and the value lives in `.env` or their
password manager. **Never put a key in `.aios/config.json`, in a skill, or in chat.**

## Before an upgrade

```bash
python3 scripts/aios/aios.py verify --target .      # does the workspace still match its release?
python3 scripts/aios/aios.py upgrade --release releases/<next>.json --target .
```

Upgrade only touches files the release owns. Their foundations, deliverables, logs, `CLAUDE.md`
and anything they created are never written to. If it fails part way, it puts the workspace back
and verifies that it did. If the machine dies mid-upgrade, `aios rollback` recovers it from the
journal on disk.

Founder-only, and it refuses any other role.

## Honesty about what role scoping is

It stops an honest operator wandering into the founder's lane by accident. It is **not**
authentication: anyone who can edit files on that laptop can edit the people map. The real
boundary is GitHub repository permissions plus branch protection and code-owner review on
`.aios/config.json`. If someone asks "could a VA just change this?", the honest answer is: they
could locally, and it would have to survive a reviewed pull request to affect anyone else -
which is exactly why the code-owner gate has to be real.
