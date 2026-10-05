---
name: workspace_health
description: 10-point workspace audit, checks folders, F6 completeness, taxonomy, staleness, security, and QC setup. Run weekly.
---

# Workspace Health Check

## IDENTITY
You are a workspace auditor. You scan the entire repo structure and report what's healthy, what's missing, and what needs fixing, clearly and without sugarcoating.

## ACTIVATION
This skill activates when:
- Someone says "check workspace health", "audit the workspace", or "is everything set up right?"
- Run weekly as a hygiene check, or after any major update

## EXECUTION PROTOCOL

Run all 10 checks. For each, assign PASS, FLAG, or FAIL.

### Check 1: Folder Structure
Verify the Starter 3.0 domain folders exist:
- `00_AIOS/` with `company/` (6 subfolders: market_analysis, avatar_analysis, offer_optimization, offer_economics, pitch_and_messaging, profile_snapshot), `systems/`, `review_queue/`, `routing.md` and `decisions_log.md`
- `01_Creation/` with `brand/`, `asset_library/`, `preferences/`, `outputs/`
- `02_Team_Ops/` with `projects/` and `routines/`
- `03_RevOps/` with `customer_journey/` and `automations/`
- `04_Attention/`, `05_Jobs/`, `99_Archive/`

FAIL if any top-level domain folder is missing. FLAG if subfolders are missing. FAIL if a Starter 2.x folder (`01_Foundations/` ... `11_Projects/`) still exists: the 3.0 upgrade moves everything out of them.

### Check 2: F6 Completeness
Check each `00_AIOS/company/` subfolder for at least one document (not counting .gitkeep or _workspace.md).
Report: "X/6 F6 docs loaded" with list of which are missing.
PASS = 6/6. FLAG = 1-5. FAIL = 0.

### Check 3: Taxonomy Compliance
Scan all files for:
- Spaces in filenames → FAIL
- Uppercase in filenames (excluding CLAUDE.md, README.md, SKILL.md, GETTING_STARTED.md) → FLAG
- Files at root that should be in a subfolder → FLAG

### Check 4: Task Tracker Freshness
Read `03_RevOps/customer_journey/task_tracker.md`:
- Are there active tasks? PASS if yes, FLAG if empty.
- Are any tasks >30 days old with no update? FLAG with list.

### Check 5: QC Preferences
Read `00_AIOS/review_queue/qc_preferences.md`:
- Is it filled in (not just template placeholders)? PASS if customized, FLAG if still template defaults.

### Check 6: Security, Settings
Verify `.claude/settings.json` exists and contains deny rules for:
- `.env*`, `*.pem`, `*.key`, `credentials.json`, `secrets.*`
FAIL if file missing. FAIL if deny rules are incomplete.

### Check 7: Security, Gitignore
Verify `.gitignore` blocks: `.env`, `.env.*`, `*.pem`, `*.key`, `credentials.json`, `.claude/settings.local.json`
FAIL if file missing or rules incomplete.

### Check 8: Engagement Timeline
Read `03_RevOps/customer_journey/engagement_timeline.md`:
- Is client name filled in? PASS/FAIL
- Is current phase set? PASS/FAIL
- Is start date set? PASS/FLAG

### Check 9: Communication Files
Check these exist:
- `02_Team_Ops/routines/daily_handoff.md`, with at least 1 entry?
- `00_AIOS/decisions_log.md`
- `02_Team_Ops/routines/feedback_log.md`
FLAG if files exist but are empty. FAIL if files missing.

### Check 10: Orphan Files
Check for files at root level that aren't standard (START_HERE.md, README.md, CLAUDE.md, SETUP.md, REPO_CONTEXT.md, estate.yaml, GETTING_STARTED.md, taxonomy_rules.md, .env.example, .template_version.json, and the license and policy files). FLAG any unexpected files.

## OUTPUT FORMAT

```
## Workspace Health Report
**Date:** [today]
**Score:** X/10

| # | Check | Status | Notes |
|---|---|---|---|
| 1 | Folder Structure | PASS/FLAG/FAIL | details |
| 2 | F6 Completeness | PASS/FLAG/FAIL | X/6 loaded |
| 3 | Taxonomy Compliance | PASS/FLAG/FAIL | details |
| 4 | Task Tracker | PASS/FLAG/FAIL | details |
| 5 | QC Preferences | PASS/FLAG | details |
| 6 | Security Settings | PASS/FAIL | details |
| 7 | Security Gitignore | PASS/FAIL | details |
| 8 | Engagement Timeline | PASS/FLAG/FAIL | details |
| 9 | Communication Files | PASS/FLAG/FAIL | details |
| 10 | Orphan Files | PASS/FLAG | details |

**Fix List:**
1. [specific fix with exact file path]
2. [next fix]
```

## FORBIDDEN
- Do not modify any files during the health check, report only
- Do not skip checks because "it's probably fine"
