# Remove someone from your GitHub organization

**What it's for:** when someone leaves, or no longer needs access, they lose access to every private repository in the organization at once. About 2 minutes. You must be an **owner** of the organization.

**Where:** `https://github.com/orgs/<your-org>/people`

## Steps
1. Sign in to GitHub. Click your profile picture (top right), then **Organizations**.
2. Click your organization's name.
3. Click the **People** tab.
4. Tick the box next to the person (or people) to remove.
5. Open the **X members selected...** menu above the list, and choose **Remove from organization**.
6. Read the confirmation, then click **Remove members**.

## It worked when
The person is no longer in the **People** list.

## Before you do it, know this
- They keep any copies already on their own computer. Removal stops future access; it can't take back what was downloaded.
- They lose access to private forks of your private repositories.
- GitHub keeps their membership details for three months, so you can reinstate them in that time.
- If your organization uses SSO with SCIM provisioning, remove them in your identity provider instead.
- Change any shared password or key they knew. Removal doesn't do that.

## Send back
"Removed `<their GitHub username>` from `<org>` on `<date>`", plus a list of any shared secrets you changed.

## Video and checks
- **Video: still to find.** No video found on 2026-10-01 showed these organization-removal steps; the closest ones remove a collaborator from a single repository, which is a different action. Per the `human_step` rule, the steps below stand on the official docs until a checked video is added.
- **Steps checked against:** GitHub Docs, "Removing a member from your organization" (https://docs.github.com/en/organizations/managing-membership-in-your-organization/removing-a-member-from-your-organization), read 2026-10-01.
