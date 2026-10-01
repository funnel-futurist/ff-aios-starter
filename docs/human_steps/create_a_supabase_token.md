# Create a Supabase access token

**What it's for:** it lets the Supabase command-line tool, or an agent, act on your Supabase projects without your password. Give it only the access the job needs. About 3 minutes.

**Where:** https://supabase.com/dashboard/account/tokens

## Steps
1. Sign in at supabase.com. Click your profile icon (top right), then **Account preferences**. In the left sidebar, click **Access Tokens**. (Or open the address above.)
2. Click **Generate new token**.
3. Name it for its one job, for example `cli-backup-<your-name>`.
4. **Scope it.** Choose the one project it's for, and only the permissions the person asking named. For example, a backup needs read access, not write. Supabase recommends scoped tokens "for everything, especially AI agents". A scoped token starts with `sbp_fc`.
5. Confirm. Supabase shows the token **once**. Copy it with the copy button.
6. Store it straight away, in your password manager, or as the line `SUPABASE_ACCESS_TOKEN=...` in your workspace's `.env` (which Git never uploads).

## It worked when
The token appears in the **Access Tokens** list with the name you gave it.

## Send back
The token's **name**, its project, and its permissions. **Never the token itself**: not in chat, a document, a screenshot or a commit. If an agent needs it, you put it in `.env` yourself.

## If it goes wrong
- You closed the window before copying: revoke that token on the same page and generate a new one.
- You think it leaked: revoke it on the same page at once, then make a new one.

## Video and checks
- **Video:** [How to Create a Personal Access Token in Supabase](https://www.youtube.com/watch?v=0XWUt89hpO0) (Shortcut Academy, 2 min 46 s).
- **Transcript checked 2026-10-01:** it follows steps 1, 2, 3, 5 and 6, including that the token is shown once and how to revoke it. **It doesn't show step 4 (scoping).** Do step 4 anyway; the video predates scoped tokens or skips them.
- **Steps checked against:**
  - Supabase Docs, "Personal access tokens" (https://supabase.com/docs/guides/platform/personal-access-tokens);
  - "supabase login" (https://supabase.com/docs/reference/cli/supabase-login).

  Both read 2026-10-01.
