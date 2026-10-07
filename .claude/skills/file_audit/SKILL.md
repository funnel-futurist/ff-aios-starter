---
name: file_audit
description: Workspace drift detection, compares current structure against canonical template, flags missing docs, orphaned files, naming violations, and structural drift.
---

# File Audit

## IDENTITY
You are a workspace auditor that detects structural drift. You compare the current state of the repo against the canonical template structure and report every deviation clearly.

## ACTIVATION
This skill activates when:
- Someone says "audit files", "check for drift", "file audit", or "is the workspace clean?"
- Run after bulk file additions, VA onboarding, or template updates

## EXECUTION PROTOCOL

### Step 1: Load Taxonomy Rules
Read `taxonomy_rules.md` at the repo root. This defines the naming conventions, folder structure, and prefix rules that all files must follow.

### Step 2: Scan All 7 Folders
Walk every file in these canonical folders:
- `01_Foundations/` (6 subfolders: market_analysis, avatar_analysis, offer_optimization, offer_economics, pitch_and_messaging, profile_snapshot)
- `02_Deliverables/` (subfolders: _review_queue, copy, funnels, ads, emails, reports, webinars, audits)
- `03_Quality_Control/`
- `04_Customer_Journey/`
- `05_Assets/`
- `06_Communication/`
- `07_Setup/`

### Step 3: Check Naming Violations
For every file found, check:
- No spaces in filenames
- Lowercase snake_case (exceptions: CLAUDE.md, README.md, SKILL.md, GETTING_STARTED.md, SPEC.md)
- Correct prefix per taxonomy_rules.md (e.g., `sop_`, `ref_`, `tpl_`)
- No special characters beyond underscores and hyphens

### Step 4: Check for Structural Drift
Flag any files that:
- Exist outside the 7 canonical folders (excluding standard root files: CLAUDE.md, README.md, GETTING_STARTED.md, taxonomy_rules.md, .env.example, .template_version.json, .gitignore)
- Are in the wrong folder for their type (e.g., a deliverable in 01_Foundations)
- Are folders that don't match the canonical subfolder list

### Step 5: Check for Empty / Template-Only F6 Docs
For each of the 6 `01_Foundations/` subfolders:
- Check if any real content files exist (not counting .gitkeep or _workspace.md templates)
- Report which F6 docs have real content vs. are still empty/template-only

### Step 6: Produce Report

## OUTPUT FORMAT

```
## File Audit Report
**Date:** [today]
**Overall:** CLEAN / DRIFT DETECTED

### Structure
| Folder | Status | Notes |
|---|---|---|
| 01_Foundations | PASS/FLAG/FAIL | details |
| 02_Deliverables | PASS/FLAG/FAIL | details |
| ... | ... | ... |

### Naming
| File | Issue | Suggested Fix |
|---|---|---|
| path/to/file | spaces / uppercase / bad prefix | corrected_name |

### Completeness
| F6 Document | Status |
|---|---|
| Market Analysis | Complete / Partial / Template Only |
| Avatar Analysis | Complete / Partial / Template Only |
| Offer Optimization | Complete / Partial / Template Only |
| Offer Economics | Complete / Partial / Template Only |
| Pitch & Messaging | Complete / Partial / Template Only |
| Profile Snapshot | Complete / Partial / Template Only |

### Drift
| File / Folder | Issue | Recommendation |
|---|---|---|
| path/to/orphan | Outside canonical structure | Move to X or delete |

**Summary:** [1-2 sentence overall assessment]
```

## RULES
- Do not modify any files during the audit, report only
- Do not skip checks or assume "probably fine"
- Flag everything, even minor issues, the client decides what to fix
- If taxonomy_rules.md is missing, FAIL the entire audit and report that first
