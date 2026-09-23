# Two-family review of the install contract

Both families reviewed the same change independently, in parallel, with the same packet:
the full diff, the full source of every module, the test files, and the local test output.

| | Gemini | DeepSeek |
|---|---|---|
| requested | gemini | deepseek |
| `answered_model` | `gemini-3.1-pro-preview` | `deepseek-v4-pro` |
| `fell_back` | false | false |
| verdict | **CHANGES_REQUIRED** | **CHANGES_REQUIRED** |
| tokens | 161,525 | 148,750 |
| latency | 231s | 723s |

Both answered, so this is a genuine two-family review rather than one family twice.

## What they found

Seven distinct defects. **All seven reproduced** deterministically against the real module
before anything was changed, and all seven are now closed and pinned by regression tests.

**Two were found by both families independently**, which is the clearest argument for routing
to two model families rather than one:

| # | defect | found by | severity |
|---|---|---|---|
| 1 | `upgrade` writes **through a symlink**, so a link left at a path the next release ships sends that file outside the workspace. `os.path.exists()` is False for a broken link, so the collision check missed it too | **both** | highest - arbitrary write outside the workspace |
| 2 | `adopt` is a founder lifecycle action in policy and was never checked in the CLI | **both** | role bypass |
| 3 | `rollback` restored over an operator's file in a path a later release had freed | Gemini | silent state loss |
| 4 | `verify` trusted the record it was verifying: tamper with a managed file *and* its hash in `install.json` and the readback agrees with itself | Gemini | false "verified" |
| 5 | a kill mid-write left unparseable JSON, and recovery died on it - the crash handler crashing | Gemini | unrecoverable workspace |
| 6 | `upgrade` re-created a seed file the operator had deliberately deleted | DeepSeek | state not preserved |
| 7 | a failed upgrade left behind seed files it had created, then reported a clean rollback and verified green | DeepSeek | state not preserved |

## What was rejected, and why

**"Concatenated client-name domains are missed"** (from the earlier sanitization attack) was
**rejected with evidence**: `acmefixture.atlassian.net` *is* matched, because the separator
between denylist words is optional. The claim assumed a separator was required. Recorded so it
cannot be "fixed" back by the next reader.

**"Approval is self-asserted and can be forged locally"** (DeepSeek #7) is **true and already
documented** rather than fixed. A local editor can write `"status": "approved"` into a manifest
on their own disk. The integrity of approval comes from the release manifest living on a
code-owner-reviewed path behind branch protection - which is exactly the gate this package
found to be nonfunctional, and exactly why `P22-GOV-001` exists. Fixing it inside the installer
is not possible: a tool cannot tell a real signature from a typed one without a signature.

## The fix that was wrong first

The guard against defect 3 initially allowed a restore to overwrite any path the *prior*
release managed. That is the freed path by definition, so the first version of the fix waved
through the exact case it existed for. The regression test caught it immediately. The allowed
set is what the release manages **now**, plus whatever the interrupted transaction created.

## Process note

The review packet was 383,562 characters and DeepSeek took just over twelve minutes. Both
results were checked for `ok`, `answered_model` and `fell_back` before being read, after an
earlier call in this package produced a zero-byte file while the surrounding shell reported
success.
