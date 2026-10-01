# Download a backup of a Supabase database

**What it's for:** a copy of your database's roles, structure and data, saved on your own computer, before a risky change or on a schedule. About 15 minutes the first time.

**Why not a dashboard button:** Supabase's docs say the dashboard's downloadable backups exist "only for older projects that still use logical backups". The way that works for every project and every plan is the Supabase command-line tool. Daily backups on paid plans can be *restored* from **Database > Backups**, but that isn't a copy you hold.

**You need:**
- **Docker Desktop**, installed and running: https://www.docker.com/products/docker-desktop/
- **The Supabase CLI.** On a Mac, run `brew install supabase/tap/supabase`. Other systems: https://supabase.com/docs/guides/local-development/cli/getting-started
- **The database password** for the project (the owner set it when the project was created).
- **A folder outside every Git repository**, so the backup can never be committed.

## Steps
1. Open the project at https://supabase.com/dashboard. Click **Connect** at the top, and copy the connection string it shows. Put your database password where it says `[YOUR-PASSWORD]`.
2. Open Terminal (see `run_a_terminal_command_from_claude.md`), and go to your backup folder: `cd ~/Documents/supabase-backups` (create it first if it doesn't exist).
3. Run these three commands. Paste your connection string where it says `CONNECTION_STRING`, keeping the quotes.
   ```sh
   supabase db dump --db-url "CONNECTION_STRING" -f roles.sql --role-only
   supabase db dump --db-url "CONNECTION_STRING" -f schema.sql
   supabase db dump --db-url "CONNECTION_STRING" -f data.sql --use-copy --data-only -x "storage.buckets_vectors" -x "storage.vector_indexes"
   ```
4. Close Terminal, so the password isn't left on screen.

## It worked when
The folder holds `roles.sql`, `schema.sql` and `data.sql`, and `data.sql` isn't empty (unless the database really is).

## Send back
"Backup of `<project name>` taken `<date>`: roles, schema and data, stored at `<where>`". Never the connection string, the password or the files themselves.

## If it goes wrong
- "Cannot connect to the Docker daemon": open Docker Desktop, wait until it says it's running, and try again.
- "password authentication failed": the password in the connection string is wrong. The project owner can reset it in the project's **Database** settings.

## Video and checks
- **Video: still to find.** The 2026-10-01 candidates showed the old dashboard download, which most projects no longer have, so none matches these steps. Per the `human_step` rule, the steps stand on the official docs until a checked video is added.
- **Steps checked against:**
  - Supabase Docs, "Backup and Restore using the CLI" (https://supabase.com/docs/guides/platform/migrating-within-supabase/backup-restore), the source of the three commands;
  - "Database Backups" (https://supabase.com/docs/guides/platform/backups);
  - "supabase db dump" (https://supabase.com/docs/reference/cli/supabase-db-dump).

  All read 2026-10-01.
