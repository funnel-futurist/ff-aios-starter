# Release brief: AIOS Starter 2.7.1

**Written for:** Phoenix, before approving. About three minutes.

**You may not need this one.** 2.7.2 (#28) contains everything here, plus the operator core, and one approval of 2.7.2 covers both. That is the recommendation; see the 2.7.2 brief on #28. Approve 2.7.1 on its own only if you want these fixes out before deciding on the core.

## The decision in one line
**Approve AIOS Starter 2.7.1 at `e27b25f`.** It is a set of safety and upgrade fixes, with no new features and nothing about the client's own files.

| Card | |
|---|---|
| **Wanted outcome** | The AI review step can't see a client's Slack token, the protection check tells the truth, and an upgrade that refuses tells the client exactly how to proceed. `main` equals a tagged release again. |
| **The problem and its evidence** | 1. **The AI review step received the Slack bot token** (finding AQ7; #24, which you merged on 10-07, so `main` now differs from every tag). 2. **The protection check printed "main is NOT protected", then exited green** (seen live, 10-07). It also called a rule it couldn't read "absent". 3. **The reviewer change #22 failed the AI check on every PR without a Claude key** (#23's run). 4. **An upgrade test of 2.7.0 found three gaps:** a refusal with no next step, setup docs still saying "Use this template", and no way to preview an upgrade. |
| **If we do nothing** | Clients on 2.7.0 keep the token exposure, a check that can show green over an unprotected `main`, and docs that contradict the README. |
| **What changes for a client** | 1. **The AI reviewer:** no Slack token, and no turn cap. A finished review counts, and with no Claude key the check stays green. 2. **The protection check:** honest, and "unknown" when it can't see. 3. **Setup docs:** the install route. 4. **Upgrades:** an edited system file is refused with its diff and two ways forward, and `upgrade --dry-run` previews. **Their own files, records and `CLAUDE.md` are untouched.** |
| **The chosen fix, and why** | All four ship together as one tagged release, so `main` equals a tag again and every client can upgrade in one step. |
| **The simpler alternative** | Merge each fix on its own. That is what made `main` stop equalling a tag (#24); clients would install untested combinations. |
| **The upgrade test** | **Passed,** with the real installer on 2.7.0 clients with their own edits and history. Every client file, history and config came through byte-identical; an edited system file was refused, not overwritten; the workspace rolled back cleanly. Also: 167 unit tests, 55 integration checks, every PR check green. |
| **Downside and recovery** | No client file is written. Without the turn cap, a review can run longer where a Claude key exists; the job's time limit still stops it. If anything is wrong, set 2.7.1 to `withdrawn` and the installer refuses it; `rollback` returns a workspace to 2.7.0. |
| **Why you** | Approval is a human act (ruling D3): a release installs only when a founder's own words approve it, and the record names who. Protection also requires a code owner's review on release files, and the agents' app can't give either. |
| **Exact place, steps and success** | 1. **G2 first:** in the Starter's Settings → Branches, change the rule pattern `Main` to `main`. 2. **Say:** "Approve starter 2.7.1 at e27b25f". 3. Lane 0.1 records it and tags `starter-2.7.1`. 4. **On #27:** Approve. 5. Chat Zero merges. **Success:** `main` equals the tag. **Note:** 2.7.2 then has to be re-cut on top, which means a new SHA and a second approval. |
| **State** | **A new decision.** Next owner: lane 0.1, then Chat Zero. |
| **Evidence** | `releases/starter-2.7.1.json` (a draft), #27's description, and lane 0.1's receipts. |
