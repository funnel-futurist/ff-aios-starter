# This repository, in context

**What it is:** one company's instance: its context, decisions, people, projects, work and records, in the Starter 3.0 layout. It's installed from an approved, versioned AIOS Starter release.

**Why it exists, and why it's separate:** one repository per company (estate decision 1). Keeping a company's own material in its own repository means it owns it outright, can move it, and never mixes it with another company's. Methods and code that serve many companies live in their own repositories. A part of this company only gets a repository of its own when it outgrows its folder, a deployable website for example, and only after it's registered.

**How it's arranged:** the seven domain folders in `CLAUDE.md`, with `00_AIOS/routing.md` deciding which folder takes which request. The machinery the release owns is `.claude/`, `.aios/roles.json`, `scripts/aios/`, `docs/` and `templates/`. An upgrade replaces those and never writes to the domain folders, except to move files out of 2.x folders once.

**Setup and operation:**
- **Setup:** `SETUP.md`.
- **Daily operation:** `START_HERE.md`.
- **Install, upgrade and rollback:** `docs/INSTALL_AND_UPGRADE.md`, including what protects you and when it doesn't.

**What health checks look at:**
- whether the files match the installed release (`verify`);
- that founder-only files are held (the session hook and the pull-request check);
- that the layout is 3.0 with no 2.x folder left;
- that only this company's material is here.

**Known limits:**
- A safety hook whose program (Python 3 or Node.js) is missing is skipped silently by Claude Code.
- A private repository on a personal free GitHub account can't block merges.
- Claude Code on the web isn't guaranteed to have a signed-in `gh`.

**Upgrade behaviour:** releases are pinned and approved. `upgrade` refuses uncommitted work, unapproved releases and conflicts, and `rollback` restores the previous release, folder moves included.

**Where its dependencies live:**
- the Starter release that installed it: `.aios/install.json`;
- its registry row: `estate.yaml`;
- the decisions behind the layout: `docs/decisions/`.
