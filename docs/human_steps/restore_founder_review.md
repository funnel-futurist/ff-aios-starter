# Restore founder review after the 3.0 move

**What it's for:** your workspace's `.github/CODEOWNERS` file tells GitHub whose review a change to certain paths needs. The founder-only folder (the founder lane: pricing and offer economics) moved from `01_Foundations/offer_economics/` to `00_AIOS/company/offer_economics/`. CODEOWNERS belongs to your workspace, so the upgrade doesn't rewrite it, and it still names the old path. Until you fix that line, GitHub stops asking a founder about changes to that folder. About 15 minutes.

Until the line is fixed, `start` shows `founder review: NOT RESTORED`. Until it's fixed **and** GitHub enforces code-owner review, `python3 scripts/aios/aios.py instance check` fails.

**You need:**
- a founder, to approve the pull request in step 3;
- admin access to the repository on GitHub, for step 4;
- the GitHub CLI (`gh`) signed in, for step 5: the check reads your repository's settings from GitHub. `gh auth status` tells you;
- for a **private** repository, a paid GitHub plan. GitHub offers protected branches and rulesets in private repositories only with GitHub Pro, GitHub Team or GitHub Enterprise. On GitHub Free they're available only in public repositories.

## Steps
1. **Fix the line.** In your workspace, start a branch: `git switch -c restore-founder-review`. Open `.github/CODEOWNERS` and find the line that starts `/01_Foundations/offer_economics/`. Change only that path to `/00_AIOS/company/offer_economics/` and keep the handles after it as they are. For example:
   - before: `/01_Foundations/offer_economics/  @founder-handle`
   - after: `/00_AIOS/company/offer_economics/  @founder-handle`

   Never changed CODEOWNERS since install? You can rewrite the whole file from the release's template instead:
   ```
   python3 scripts/aios/aios.py governance render --repo-slug <owner>/<repo> --owner "REPO_OWNER=@founder-handle" --owner "PRIMARY_REVIEWER=@reviewer-handle" --out .github/CODEOWNERS
   ```
   It replaces the file, so any line you added yourself is lost. If you're not sure, edit the one line instead.
2. **Check the file.** In your workspace, run `python3 scripts/aios/aios.py governance check`. Expect `verdict:    names real owners, bound to this repository`.
3. **Merge it with a founder's approval.** `git add .github/CODEOWNERS`, then `git commit -m "Restore founder review at the 3.0 path"`. Push the branch and open a pull request. A founder approves it, then merge. GitHub reads CODEOWNERS from the branch a pull request merges into, so the fix only counts once it's on `main`.
4. **Make GitHub enforce it.** On GitHub, open the repository and click **Settings**. `main` is protected in one of two ways. Use whichever your repository has:
   - **Classic branch protection:** in the **Code, planning, and automation** section of the sidebar, click **Branches**. To the right of the rule for `main`, click **Edit**. (No rule yet? Click **Add classic branch protection rule** and type `main` under **Branch name pattern**.) Under **Protect matching branches**, select **Require a pull request before merging**, then **Require review from Code Owners**. Click **Save changes** (or **Create** for a new rule).
   - **Ruleset:** in the same sidebar section, open **Rulesets**, then click the ruleset that targets `main`. In its **Require a pull request before merging** rule, turn on the option to require review from code owners. At the bottom of the page, click **Save changes**.
5. **Check it's in force.** In your workspace, run `python3 scripts/aios/aios.py instance check`. Every line marked `founder` must say `PASS`.

## After upgrading to 3.1
3.1 adds two files to the founder lane: the install record and the adoption plan, which say which files the installer treats as its own. Your CODEOWNERS needs a rule for each. In step 1, add these two lines under your `/.aios/roles.json` line, with the same handles it has:
```
/.aios/install.json   @founder-handle
/.aios/adoption.json  @founder-handle
```
Adopted a repository with its plan somewhere else? Use that path in the second line instead: it's `adoption.plan` in `.aios/install.json` (for example `/ops/our_plan.json`). Add the same path to your role policy's `paths_denied` too. `instance check` names the exact path it needs.

Then follow steps 2 to 5 as written. Never changed CODEOWNERS since install? Rendering the file from the 3.1 template (step 1) includes both lines.

## It worked when
- `instance check` shows `PASS` on every `founder` line, including `GitHub requires code-owner review on main`, and its last line reads `verdict:  meets the instance contract's checks`;
- a test pull request (not a draft) that changes a file in `00_AIOS/company/offer_economics/` asks the founder for review, and can't merge until they approve. Close it afterwards without merging.

## Send back
- the output of `instance check`;
- the CODEOWNERS line now in place, for example `/00_AIOS/company/offer_economics/  @founder-handle`.

## If it goes wrong
- **`couldn't read main's protection (...); a repository admin can run this check`.** GitHub only shows classic branch protection to people with admin access to the repository. Ask a repository admin to run step 5. (Anyone who can read the repository can see a ruleset, so this only happens with classic branch protection.)
- **`the rule that applies (...) names ..., no founder`.** The path is right but the handles on that line aren't a founder's. Put the founder's GitHub handle there, the one in your workspace's people map. GitHub also requires every code owner to have write access to the repository.
- **`... still guards /01_Foundations/..., a folder that no longer exists`.** Another line still names an old folder, so it now protects nothing. Change its path to the new folder (`00_AIOS/routing.md` lists every old folder and its new home), or delete the line.
- **GitHub shows errors in CODEOWNERS.** GitHub skips any line with invalid syntax. Open `.github/CODEOWNERS` on GitHub: any errors are highlighted. Fix the line it marks. `gh api repos/<owner>/<repo>/codeowners/errors` lists the same errors.
- **`main is not protected`.** There's no rule for `main` yet: do step 4. If GitHub won't let you add one, the repository is private on GitHub Free (see **You need**).

## Video and checks
- **Video: still to find.** This card was written on 2026-10-14 and no video has been checked against it yet. The steps stand on the official docs until a checked video is added.
- **Steps checked against:**
  - GitHub Docs, "About code owners" (https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners);
  - "Managing a branch protection rule" (https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/managing-a-branch-protection-rule);
  - "About protected branches", for the plans (https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches);
  - "About rulesets", for the plans and who can see a ruleset (https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets);
  - "Managing rulesets for a repository" (https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/managing-rulesets-for-a-repository);
  - "Available rules for rulesets" (https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets);
  - "REST API endpoints for protected branches", for the admin permission (https://docs.github.com/en/rest/branches/branch-protection);
  - "REST API endpoints for repositories", for the CODEOWNERS errors list (https://docs.github.com/en/rest/repos/repos#list-codeowners-errors).

  All read 2026-10-14.
- **Not stated in those docs:** the exact label of the code-owner option inside a ruleset's pull-request rule (the docs only describe it as requiring reviews from code owners), and what a pull request's merge box says while a code owner's review is missing. The docs name the ruleset menu **Rulesets**, then **Rulesets**, but the same page's Insights steps call that sidebar menu **Rules**, so it may read **Rules**, then **Rulesets**. "Only admins can see classic branch protection" is our reading of the API page, which asks for the repository's Administration permission.
