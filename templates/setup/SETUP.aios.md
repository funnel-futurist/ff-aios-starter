# Setting up `ai-os`

**What this is:** the AIOS brain and the control plane: the constitution, schemas and declared registry (`00_Foundations/control_plane/`), plus R&D in `00_R_and_D_Refinement/`. Company instances aren't here; they live in their own repositories.

## 1. Name and registry row
`ai-os` is a registered name exception. Its registry row is the first one in `00_Foundations/control_plane/registry/`.

## 2. Access to grant (all at once)
| Who or what | Gets | Card |
|---|---|---|
| The founders | Admin, with 2FA on | [Turn on GitHub 2FA](https://github.com/funnel-futurist/ff-aios-starter/blob/main/docs/human_steps/turn_on_github_2fa.md) |
| Lane owners | Write, through reviewed pull requests | |
| FF Agents App | Installed with its standard permissions | |
| Leavers | Removed the same day | [Remove an org member](https://github.com/funnel-futurist/ff-aios-starter/blob/main/docs/human_steps/remove_an_org_member.md) |

## 3. Secrets
`.env` at the root holds the values and is never committed. Its variable names are documented in `00_Foundations/ref_tools_and_integrations.md`.

## 4. Reviewer
Declared in the registry record (B7).

## 5. Hosting
None. Embedded apps move to `ff-01-aios-tools`.

## 6. First-run checks
- The estate map regenerates from the registry.
- Architecture Health runs read-only over the estate.
- Every Starter-derived instance is registered.

## 7. What protects it, and when it doesn't
- Branch protection, except an owner bypass (recorded).
- The `generated/` folder is written only by its generator; a check fails any other pull request touching it.
