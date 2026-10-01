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
| Who we are: strategy, research, positioning, offers, pricing, avatar | `00_AIOS/company/` |
| Which domain takes which request | `00_AIOS/routing.md` |
| Company decisions | `00_AIOS/decisions_log.md` |
| Waiting for review, QC rubric, QC preferences, revision notes | `00_AIOS/review_queue/` |
| Tools and connected capabilities | `00_AIOS/systems/` |
| Brand guide | `01_Creation/brand/` |
| Logos, photos, videos, testimonials (one record each) | `01_Creation/asset_library/` |
| How you like work made | `01_Creation/preferences/` |
| Finished documents, decks, copy, training | `01_Creation/outputs/` |
| People, roles, org chart | `02_Team_Ops/people/`, `roles/`, `org_chart.md` |
| Projects (one folder each, `PROJECT.md` first) | `02_Team_Ops/projects/` |
| Daily handoff, standups, meeting notes, feedback, unstuck protocol | `02_Team_Ops/routines/` |
| Website, funnels, CRM, automations, sales | `03_RevOps/site/`, `funnels/`, `crm/`, `automations/`, `sales/` |
| Timeline, milestones, KPIs, the customer journey | `03_RevOps/customer_journey/` |
| Audits and reports | `03_RevOps/audits/`, `reports/` |
| Payments, onboarding, support, client-success records | `03_RevOps/records/` |
| Content, ads, emails, webinars, publishing | `04_Attention/` (`campaigns/` holds ads, emails, webinars) |
| Recurring jobs | `05_Jobs/` |
| Completed, retired, or superseded work | `99_Archive/` |

A website that becomes a deployable app gets its own repository, registered first; until then it lives in `03_RevOps/site/`. Setup lives in `SETUP.md` and the step-by-step cards in `docs/human_steps/`.
