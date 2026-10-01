# Routing: which domain takes which request

When a request comes in, it goes to one folder. If two seem to fit, the first match below wins.

| A request about... | Goes to |
|---|---|
| Who we are, what we sell, pricing, positioning, the ideal client | `00_AIOS/company/` |
| Something waiting on a person to review | `00_AIOS/review_queue/` |
| Brand, a design, an asset, a finished document or deck | `01_Creation/` |
| People, roles, a project, onboarding, a policy, the daily routine | `02_Team_Ops/` |
| The website, funnels, CRM, automations, sales, the customer journey, audits, reports, payments, support | `03_RevOps/` |
| Content, campaigns, publishing, social accounts, performance | `04_Attention/` |
| A recurring job, or which FF Core Jobs are connected | `05_Jobs/` |
| Something finished and no longer used | `99_Archive/` |

A decision that changes how the company works goes in `00_AIOS/decisions_log.md`.
