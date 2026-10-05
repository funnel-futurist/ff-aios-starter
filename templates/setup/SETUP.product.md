# Setting up `ff-<NN>-<domain>-<surface>`

**What this is:** an app or site that serves many companies. **Code only**: no company's data, no copied methods (read them from the Intelligence repository), no committed outputs.

## 1. Name and registry row
- **Name:** `ff-<NN>-<domain>-<surface>`. The Vercel project has exactly the repository's name. A Supabase project this repository alone owns has it too.
- **Registry:** the row comes first (R22). `estate.yaml` mirrors it.

## 2. Access to grant (all at once)
| Who or what | Gets | Card |
|---|---|---|
| The lane owner | Maintain | |
| FF Agents App | Installed on this repository | |
| Vercel | Access to this repository; production from `main` only | [Connect Vercel to a GitHub repository](https://github.com/funnel-futurist/ff-aios-starter/blob/main/docs/human_steps/connect_vercel_to_a_repo.md) |
| Supabase (if it owns a schema) | A token scoped to its one project and only the permissions it needs | [Create a Supabase access token](https://github.com/funnel-futurist/ff-aios-starter/blob/main/docs/human_steps/create_a_supabase_token.md) |
| Every person | 2FA on | [Turn on GitHub 2FA](https://github.com/funnel-futurist/ff-aios-starter/blob/main/docs/human_steps/turn_on_github_2fa.md) |

## 3. Secrets
Names only, here. Values are set in Vercel (marked **Sensitive**) or in GitHub Actions.

| Name | Environment | For |
|---|---|---|
| `<SECRET_NAME>` | Production / Preview | `<what uses it>` |

## 4. Reviewer
Declared in the registry record (B7).

## 5. Hosting
- Vercel, deploying from `main`.
- Previews are protected; check one signed out, which should answer 302 or 401.
- The production `*.vercel.app` address isn't covered by standard protection, so a custom domain or full protection is decided before the first deploy.

## 6. First-run checks
- CI tests pass on `main`.
- The production deploy shows the commit on `main`.
- `.gitignore` covers `.tmp/`, `out/`, `payloads/` and `captures/`.
- If it owns a schema, a backup has been taken before the first migration (card: [Download a Supabase backup](https://github.com/funnel-futurist/ff-aios-starter/blob/main/docs/human_steps/download_a_supabase_backup.md)).

## 7. What protects it, and when it doesn't
Branch protection blocks unreviewed merges, except an owner bypass, which is recorded. Migrations run only through the guard. A deploy made from a laptop isn't "from `main`", and the hosting record flags it.
