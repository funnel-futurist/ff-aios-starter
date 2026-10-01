# 0001 · The instance layout is seven domain folders (Starter 3.0)

**Scope:** operator. **Status:** accepted 2026-10-01 (estate plan §3.2, founder ruling C1). **Superseded by:** none.

## Problem
Starter 2.x had numbered folders (`01_Foundations` ... `11_Projects`) named after kinds of document. The business runs as AIOS, with Creation, Team Ops, RevOps and Attention under it, and the 2.x folders didn't show that. Every company's instance also had to look the same, Funnel Futurist's own included, so that one way of working carries across.

## Options
1. Keep 2.x and add a map document.
2. Rename the folders in place.
3. Move to domain folders, with an upgrade that moves every file.

## Decision
Option 3:
- the folders are `00_AIOS`, `01_Creation`, `02_Team_Ops`, `03_RevOps`, `04_Attention`, `05_Jobs` and `99_Archive`;
- `release/package_spec.json` declares the 2.x-to-3.0 map;
- the map ships inside the release record, so it's approved with the release.

## Why
The folders now say which part of the business owns what, and `00_AIOS/routing.md` turns that into a rule. A declared map, checked before any file moves, means an upgrade can't overwrite anything or strand a file.

## Consequences
- `upgrade` moves the person's files, including ones they made themselves.
- `rollback` reverses the moves.
- References to old folders inside the person's own files are reported, never rewritten.
- `07_Setup/` (three walkthroughs written for "Use this template" and Claude Code on the web) retires. `SETUP.md` and `docs/human_steps/` replace it; anything a person had added to `07_Setup/` moves to `99_Archive/07_Setup/`.
- Three 2.x deliverable folders (`ads`, `emails`, `webinars`) keep their names under `04_Attention/campaigns/`, so files can't collide.
- `11_Projects/` moves to `02_Team_Ops/projects/` as ruled. In 3.0 a deployed site lives in `03_RevOps/site/`, and the upgrade names any moved site whose host setting must change.
- `REPO_CONTEXT.md` is at the root, and the decision notes are in `docs/decisions/`. §3.2 doesn't list either at the root, and R22 forbids new top-level folders; the repo contract (B11) requires both. This placement is proposed for the registry, not assumed.
