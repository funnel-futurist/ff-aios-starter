# P22 STATE - current at every material change

last_updated: 2026-09-21 (writer: CHAT P22, Claude Opus 5)
branch: exec/p22-install-20260922
starting_repo_sha: c4387053c956e45a3a190c78d3331214a3b09fff (main, confirmed unmoved at preflight)
starting_master_revision: 71e063f83b202fbf914e3e4bbc2b4ca9fbc42656 (ff-delegation exec/operating-cutover-20260921)
lease: ACTIVE

## Preflight facts (measured 2026-09-21, not inherited)

| fact | value | how measured |
|---|---|---|
| main head | `c438705` | `git log`, matches the prompt |
| open PRs | 1 (#11, draft, MERGEABLE, +1,539/-0, head `3db0c78`) | `gh pr list`, `gh pr view 11` |
| `.github/CODEOWNERS` | every owner is a literal placeholder (`[REPO_OWNER]`, `[PRIMARY_REVIEWER]`, `[TECHNICAL_REVIEWER]`) | `cat` |
| branch protection on main | **none**: `protected:false`, 0 rulesets, 0 branch rules | `gh api .../branches/main`, `.../rulesets`, `.../rules/branches/main` |
| repo visibility | **public**, and `is_template: true` | `gh api repos/...` |
| collaborators | `Joburn-ai` admin, `phoenix-ship-it` write | `gh api .../collaborators` |
| repo Actions secrets | `total_count: 0` | `gh api .../actions/secrets` |
| `ai_review` root cause | action gets an empty `ANTHROPIC_API_KEY`: "Either ANTHROPIC_API_KEY, CLAUDE_CODE_OAUTH_TOKEN ... is required" | run 35038584858 log |
| `ai_review` history | failed on every PR since 2026-06-09T08:46Z; last success 2026-06-09T06:29Z | `gh run list` + per-run job conclusions |
| existing tests on main | static_checks 17/17 PASS, guard-dangerous-git 49/49 PASS | `node --test ...`, `node ...test.js` |
| client-name sweep (public repo) | 0 hits over tracked files and all 31 revisions (word-boundary) | private roster as runtime input, never committed |

## Work units

| # | unit | status |
|---|---|---|
| 1 | preflight + PROJECT/STATE | DONE |
| 2 | install contract lib + CLI (release, install, verify, upgrade, rollback, start) | IN PROGRESS |
| 3 | credential references + sanitization check | PENDING |
| 4 | governance: CODEOWNERS check + render + template split | PENDING |
| 5 | CI wiring + pr-review.yml fixes | PENDING |
| 6 | internal validation run on real content (clean env) | PENDING |
| 7 | Gemini PR #11 synthesis; DeepSeek sanitization attack; two-family review | PENDING |
| 8 | propagation sweep of other repos | PENDING |
| 9 | receipt + LANE_RECEIPT | PENDING |

## Open human gates

None raised yet. Being raised as they are found.
