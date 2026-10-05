# Connect Vercel to a GitHub repository

**What it's for:** your site deploys from the repository's `main` branch on every merge, with a preview for every pull request, instead of from someone's laptop. About 10 minutes.

**You need:**
- a Vercel account in your company's team;
- **owner** or **member with access** to the repository on GitHub (an outside collaborator can't connect it).

## A new Vercel project from a repository
1. Open https://vercel.com/new.
2. Under **Import Git Repository**, choose your GitHub account or organization from the menu at the top left of the list.
   - The repository isn't listed? Click the option to adjust the GitHub App's permissions, give the Vercel app access to that repository, then come back.
3. Click **Import** next to the repository.
4. **Project Name:** use the repository's exact name (that's the naming rule).
5. **Root Directory:** click **Edit** and choose the folder that holds the site. In a company workspace that's `03_RevOps/site`.
6. Leave the framework and build settings Vercel detected, unless the person asking told you otherwise.
7. Click **Deploy**.

## An existing project that isn't connected yet
1. Open the project in Vercel, then **Settings > Git**.
2. Under **Connected Git Repository**, connect the repository.
3. **Settings > Build and Deployment > Root Directory:** enter the folder path, then click **Save**. This applies from the next deployment.

## It worked when
- the first deployment finishes and its page opens;
- on GitHub, the next pull request shows a Vercel check with a preview link.

## Send back
- the Vercel project name and its address (`<project>.vercel.app`);
- the Root Directory you set;
- the repository it's connected to.

## If it goes wrong
"Unable to find your GitHub repository": you're an outside collaborator, or the Vercel app hasn't been given that repository. An organization owner can fix either.

## Video and checks
- **Video: still to find.** On 2026-10-01 YouTube refused the transcript requests for every candidate, so none could be checked. Per the `human_step` rule, the steps stand on the official docs until a checked video is added.
- **Steps checked against:**
  - Vercel Docs, "Deploying Git Repositories with Vercel" (https://vercel.com/docs/git);
  - "Deploying GitHub Projects with Vercel" (https://vercel.com/docs/git/vercel-for-github);
  - "Configuring a Build", for Root Directory (https://vercel.com/docs/builds/configure-a-build).

  All read 2026-10-01.
