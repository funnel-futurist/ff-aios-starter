# Setting up `ff-<NN>-<domain>`

**What this is:** a Funnel Futurist Intelligence repository: methods, capabilities, standards, curriculum and contracts for one domain. **No company's data, ever.** Architecture Health's boundary check flags any.

## 1. Name and registry row
- **Name:** `ff-<NN>-<domain>`, where NN is the owning project's number.
- **Registry:** the row is approved, and added by the bootstrap, *before* the repository exists (R22). `estate.yaml` here mirrors that row, and `.ff/system.json` is written by the bootstrap.

## 2. Access to grant (all at once)
| Who or what | Gets |
|---|---|
| The lane owner | Maintain |
| FF Agents App | Installed on this repository with its standard permissions |
| Every person with access | Two-factor sign-in on (card: [Turn on GitHub 2FA](https://github.com/funnel-futurist/ff-aios-starter/blob/main/docs/human_steps/turn_on_github_2fa.md)) |
| Leavers | Removed the same day (card: [Remove an org member](https://github.com/funnel-futurist/ff-aios-starter/blob/main/docs/human_steps/remove_an_org_member.md)) |

## 3. Secrets
Names only, here. Values live in the runtime that uses them (GitHub Actions secrets or the Bridge), never in the repository.

| Name | For |
|---|---|
| `<SECRET_NAME>` | `<what uses it>` |

## 4. Reviewer
The org's AI reviewer policy is declared in the registry record (control B7). `standards/rubrics/` is private: confirm it's excluded from every client export.

## 5. Hosting
None by default. An Intelligence repository isn't deployed. Its capabilities run through the Bridge.

## 6. First-run checks
- Architecture Health shows this repository certified.
- The boundary check is clean (no `instance/`, `clients/`, outputs or `.tmp/`).
- `curriculum/manifest.yaml` validates against P16's schema.
- The first release is tagged.

## 7. What protects it, and when it doesn't
Default-branch protection (B8) blocks unreviewed merges for everyone except an organization owner, who can bypass it. An owner bypass is still recorded.
