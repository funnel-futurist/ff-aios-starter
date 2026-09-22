# P22 STATE - current at every material change

last_updated: 2026-09-22 (writer: CHAT P22, Claude Opus 5)
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

## Verified state at release (CI, Ubuntu runner, not a laptop)

- `Install contract / tests`: **PASS** - 85 unit tests + 47 end-to-end assertions
- `Install contract / governance`: **FAIL, by design** - the placeholder CODEOWNERS
- `PR Review`: **PASS** - floor clean, `ai_review` reports "not configured", `pr-gate` says
  "AI review not configured - manual merge only"
- release `starter-2.6.0` pins `fe8e6afa006fac2795552ebcec7a7cdc3ceaaca4`, status **draft**
- sanitization: 1 finding, the real one (HUMAN_ACTION 4)
- PR: #12

## Open gates (nothing here blocks the next instance from working)

1. **Release approval** - Phoenix. `releases/starter-2.6.0.json` is `draft`. Internal validation
   used a sandbox-only fixture approval; nothing in this repo claims a human approved anything.
2. **Code owners** - Phoenix names them; an admin turns on branch protection. `main` currently has
   NO protection, so the CI `governance` job is red on purpose.
3. **AI reviewer credential** - admin. Zero Actions secrets is why `ai_review` has failed since
   2026-06-09. Recommendation recorded: accept manual review here.
4. **One sanitization finding** - Phoenix. A publicly-readable Google Doc in a client-facing
   skill, now IDENTIFIED and measured per founder correction 97f2671: public (HTTP 200, full
   45,328 bytes to an anonymous request) but carrying nothing sensitive (0 findings from our own
   scanner, including the generic-term pass). Governance, not exposure. One line from Phoenix
   closes it, and it does not hold the release.
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
