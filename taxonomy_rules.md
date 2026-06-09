# Taxonomy Rules

Simple naming conventions so everything stays organized as the workspace grows.

---

## File Naming

- **All lowercase**, underscores between words: `market_analysis_v2.md` not `Market Analysis V2.md`
- **No spaces.** Ever.
- **Descriptive names.** The file name should tell you what's inside without opening it.

### Prefixes

| Prefix | Meaning | Example |
|---|---|---|
| `ref_` | Reference document, read, don't edit | `ref_buyer_awareness_journey.md` |
| `sop_` | Standard operating procedure | `sop_content_review_process.md` |
| `qc_` | Quality control document | `qc_preferences.md` |
| (none) | Working document, edit freely | `market_analysis.md` |

### Versioning

When a document gets a major revision, append `_v2`, `_v3`, etc. Keep the previous version in the same folder for reference.

Example: `offer_stack.md` → `offer_stack_v2.md`

---

## Folder Rules

- Folder names are **lowercase with underscores**: `brand_guide/` not `Brand Guide/`
- Each numbered folder has a specific purpose (see README.md)
- Don't create new top-level folders, if something doesn't fit, put it in the closest match and flag it

---

## What Goes Where

| Content Type | Folder |
|---|---|
| Strategy, research, positioning | `01_Foundations/` |
| Finished deliverables (copy, ads, emails, funnels, reports) | `02_Deliverables/` |
| Your brand preferences, revision notes | `03_Quality_Control/` |
| Timeline, milestones, KPIs | `04_Customer_Journey/` |
| Logos, fonts, colors, existing content | `05_Assets/` |
| Decisions, feedback, meeting notes | `06_Communication/` |
| Setup walkthroughs, onboarding, how-to | `07_Setup/` |
| Scheduled + triggered automations, runbooks | `08_Automations/` |
| Completed, retired, or superseded work | `09_Archive/` |
| Department workspaces, sales / content / ops (optional, for teams) | `10_Departments/` |
| Deployable sites, apps, internal tools, one folder each; Vercel Root Directory points at the subfolder (optional) | `11_Projects/` |
