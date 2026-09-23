# P22 STATE - current at every material change

last_updated: 2026-09-22, resumed session (writer: CHAT P22, Claude Opus 5.5)
branch: exec/p22-install-20260922
starting_repo_sha: c4387053c956e45a3a190c78d3331214a3b09fff (main, confirmed unmoved at preflight)
starting_master_revision: 71e063f83b202fbf914e3e4bbc2b4ca9fbc42656 (delegation repo, exec/operating-cutover-20260921)
lease: ACTIVE -> released with the receipt
receipt: P22-001-2026-09-22.md (in this folder)

## Where the work is

| thing | path |
|---|---|
| the install contract | `scripts/aios/aios.py` + `scripts/aios/aioslib/` |
| what ships and who owns it after install | `release/package_spec.json` |
| credential references (all optional) | `release/credential_refs.json` |
| publisher-branding allowlist for the sanitizer | `release/sanitize_allow.txt` |
| the release manifest (DRAFT - a human approves it) | `releases/starter-2.6.0.json` |
| role policy | `.aios/roles.json` |
| CODEOWNERS template (placeholders live HERE, not in `.github/`) | `templates/governance/CODEOWNERS.template` |
| role-scoped entry skill | `.claude/skills/start/SKILL.md` |
| operator docs | `docs/INSTALL_AND_UPGRADE.md` |
| unit tests (71) | `tests/aios/test_*.py` |
| end-to-end on real content (38 assertions) | `tests/aios/integration_real_content.sh` |
| CI | `.github/workflows/install-contract.yml` |

## How to re-verify everything in two commands

```bash
python3 -m unittest discover -s tests/aios -t tests/aios     # 71 tests
bash tests/aios/integration_real_content.sh                  # 38 assertions, real content
```

The client-name denylist is **not in this repo** and never will be. Build one at run time from
the internal client roster and pass `--denylist`.

## Work units

| # | unit | status |
|---|---|---|
| 1 | preflight + PROJECT/STATE | DONE |
| 2 | install contract lib + CLI | DONE - 71 unit tests |
| 3 | credential references + sanitization | DONE - hardened against an adversarial review |
| 4 | governance: CODEOWNERS check + render + template split | DONE - check fails on the real file, by design |
| 5 | CI wiring + pr-review.yml portability fixes | DONE |
| 6 | internal validation on real content, clean env | DONE - 47/47, also green in CI |
| 7 | Gemini #11 synthesis; DeepSeek sanitization attack; two-family review | DONE |
| 8 | propagation sweep (32 repos) | DONE |
| 9 | receipt + LANE_RECEIPT | DONE |

## Verified state (CI, Ubuntu runner, not a laptop)

- `Install contract / tests`: **PASS** - 87 unit tests + 47 end-to-end checks. Now fenced to this
  repository, so generated client repos no longer pay for it on every push.
- `Install contract / governance`: **PASS** - CODEOWNERS names real accounts. Runs everywhere.
- `PR Review`: **PASS** - floor clean, `ai_review` reports "not configured"
- release `starter-2.6.0`: status **draft**, currently pinned to a PR-branch commit. **Must be
  re-cut from the merge commit on main before it is approved** - see the brief.
- sanitization: **0 findings** across 282 files
- PR: #12, MERGEABLE, CLEAN, zero human reviews
- **Release brief:** `releases/starter-2.6.0.BRIEF.md` - read this before asking Phoenix to
  approve anything. Asking for approval without it is the defect it was written to fix.

## Open gates (nothing here blocks the next instance from working)

1. **Release approval** - Phoenix. HUMAN_DECISION. The ask is `releases/starter-2.6.0.BRIEF.md`,
   not "reply approved". Order matters: merge PR #12, re-cut 2.6.0 from the merge commit on main,
   re-run every check, THEN record his approval. The current pin sits on the PR branch, and this
   repo squash-merges, so a pin approved now would survive only until the branch is deleted.
   Approval must come from Phoenix directly, never through a relay.
2. **Code owners - DONE.** Phoenix named Phoenix/John/Justine; GitHub was asked who actually has
   access. `.github/CODEOWNERS` now names @phoenix-ship-it (write) and @Joburn-ai (admin), the
   check passes, and the CI `governance` job is GREEN. Remaining: `justine-del` has org-level
   read only and is not a collaborator, returned as an exact access mismatch; and branch
   protection still needs the admin account, without which the file enforces nothing.
3. **AI reviewer credential** - admin. Zero Actions secrets is why `ai_review` has failed since
   2026-06-09. Recommendation recorded: accept manual review here.
4. **The Google Doc - CLOSED by founder decision.** Classified LEGACY_SOURCE /
   SUPERSEDED_BY_OPERATORS_RESET. The material lives in Operator's Reset SOP 2 of 5 (verified in
   ai-os). The skill no longer presents the doc as current authority. Residual, not ours:
   `funnelfuturist.com/operators-reset` returns 404, so there is no live link to point clients
   at yet - the skill names the source instead of shipping a broken URL.
5. **Reader access** - Phoenix. This repo is public and a template; evidence here is published.

Full runbooks for all five are in the receipt, section 11.

## What NOT to do next

- Do not merge PR #11 to get around the broken code-owner gate. It also has a reproduced defect:
  one tracked symlink anywhere makes its pre-push hook fail closed and block every push.
- Do not approve a release by editing the manifest without reading what it pins.
- Do not commit a client-name denylist to this repository.

## Successor

`P22-002` (client portability) is eligible: internal validation passed. `P22-GOV-001` is the
governance half, split out so the install work is not held behind a naming decision.
