# Release brief: AIOS Starter 2.7.2

**Written for:** Phoenix, before approving. About three minutes.

> **Approved 2026-10-08 at `d988d2c`**, the exact commit this brief names. Phoenix's words and where they are recorded are in `releases/starter-2.7.2.json`.

**One approval can cover both 2.7.1 and 2.7.2.** 2.7.2 contains everything in 2.7.1 (#27), plus the operator core. Approving 2.7.2 alone means one sentence from you, one PR approval and one merge, and 2.7.1 is never tagged, as 2.6.1 never was. **That is the recommendation.** The 2.7.1 brief, on #27, covers the other route.

## The decision in one line
**Approve AIOS Starter 2.7.2 at `d988d2c`.** It is every 2.7.1 fix, plus the AIOS Operator Core in every client workspace.

| Card | |
|---|---|
| **Wanted outcome** | Every client's AI explains its work, asks people for things and records what it did the same way FF's own sessions do. Every 2.7.1 safety fix reaches them in the same step. |
| **The problem and its evidence** | The core exists only in ai-os (v1.1.1, ai-os #408). Client workspaces never get it: nothing ships it, and a file the AI isn't told to read is never loaded. The 2.7.1 problems are on its brief: a Slack token visible to the AI review step, a protection check that went green over an unprotected `main`, setup docs that contradicted the README, and an upgrade refusal with no way forward. |
| **If we do nothing** | Clients keep the 2.7.0 behaviour, including the AI review step that can see the Slack token. FF's operating standard stays FF-only. |
| **What changes for a client** | 1. **Everything in 2.7.1.** 2. **The new file** `.aios/operator_core/OPERATOR_CORE.md`. It is a client edition: section 9 points to the client's own voice rules and `/humanize` instead of FF's private writing repo. 3. **One line in their `CLAUDE.md`** imports it. Nothing else of theirs changes. |
| **The chosen fix, and why** | The core ships as a managed file, so upgrades keep it current and `verify` flags a hand edit. The one import line is added once by the upgrade. That is the only way an existing workspace's AI starts reading it. |
| **The simpler alternative** | Ship the file without the line: existing clients' AI would never load it. Or paste the core into each `CLAUDE.md` by hand: it would drift, and no upgrade could fix it. |
| **The upgrade test** | **Passed,** with the real installer and two 2.7.0 clients that had their own `CLAUDE.md` rules, records and git history. One went straight to 2.7.2, one through 2.7.1. Both got the core. `CLAUDE.md` was their own text plus exactly one line. **All 38 other client files were byte-identical.** `verify` matched. Also: 184 unit tests, 55 integration checks, every PR check green. |
| **Downside and recovery** | **This is the first time an upgrade writes into a client's own file:** one line in `CLAUDE.md`. It is declared in the release, added once, never twice, never into a deleted `CLAUDE.md`, and never re-added after the client removes it. `rollback` takes it back exactly; tested, `CLAUDE.md` came back byte for byte. **The core becomes public:** the Starter is a public template, and v1.1.1 holds no FF-specific detail. If anything is wrong after approving, set 2.7.2 to `withdrawn` and the installer refuses it. |
| **Why you** | Approval is a human act (ruling D3): a release installs only when a founder's own words approve it, and the record names who. Protection also requires a code owner's review on release files, and the agents' app can't give either. |
| **Exact place, steps and success** | 1. **G2 first:** in the Starter's Settings → Branches, change the rule pattern `Main` to `main`. 2. **Say:** "Approve starter 2.7.2 at d988d2c". 3. Lane 0.1 records the approval and tags `starter-2.7.2` once `check-tag` passes. It also marks 2.7.1 (never released) and 2.7.0 `superseded`, so new installs get 2.7.2; add "keep 2.7.0" if you'd rather not. 4. #28 is retargeted from #27's branch to `main` and marked ready. **On #28:** Files changed → Review changes → Approve. 5. Chat Zero merges with a merge commit, and closes #27 as included. **Success:** `main` equals the `starter-2.7.2` tag and shows `protected: true`. |
| **State** | **A new decision.** Next owner: lane 0.1 (the approval commit and the tag), then Chat Zero (the merge). |
| **Evidence** | `releases/starter-2.7.2.json` (a draft until approved), #28's description, and lane 0.1's receipts. |
