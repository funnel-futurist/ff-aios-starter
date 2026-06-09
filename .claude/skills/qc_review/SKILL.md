---
name: qc_review
description: Quality control review for any deliverable. Checks against client brand preferences and agency quality standards.
---

# QC Review

Review any document or deliverable against the client's QC preferences and the agency's quality standards.

## Input

Specify one of:
- A file path (e.g., `02_Deliverables/_review_queue/ad_copy_v1.md`)
- Pasted text to review

## Steps

1. Read `03_Quality_Control/qc_preferences.md`, client's brand voice, visual preferences, and taste standards.
2. Read `03_Quality_Control/qc_approval_rubric.md`, the shared approval criteria.
3. Read the relevant F6 docs from `01_Foundations/`, especially avatar analysis (voice/language) and pitch & messaging (positioning).
4. Review the target deliverable against all three layers: agency standards, client preferences, and F6 alignment.

## Output

```
QC REVIEW, [filename or description]

VERDICT: PASS / FLAG / REVISE

| # | Issue | Severity | Location | Fix |
|---|---|---|---|---|
| 1 | [description] | Critical / Major / Minor | [line or section] | [specific fix] |

STRENGTHS:
- [what's working well]

SUMMARY: [1-2 sentences, overall quality and whether it's ready for client review]
```

## Rules

- **Critical** = factually wrong, off-brand, or contradicts F6 positioning. Must fix before delivery.
- **Major** = significantly weakens the piece. Should fix.
- **Minor** = polish issue. Fix if time permits.
- PASS = 0 critical, 0 major issues. FLAG = 0 critical, 1+ major. REVISE = 1+ critical.
- If QC preferences are empty, flag it: "QC preferences not yet configured, reviewing against agency standards only."
- Be specific. "Tone is off" is not a fix. "Paragraph 3 uses passive voice, rewrite as direct address" is.
