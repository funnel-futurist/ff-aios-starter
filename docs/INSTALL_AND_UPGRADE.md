# Installing and upgrading your AIOS

Your workspace has two kinds of file, and everything here follows from the difference.

| | |
|---|---|
| **Managed** | The system layer the release owns: skills, hooks, scripts, workflows, the setup docs. An upgrade replaces these. |
| **Yours** | Everything else: `CLAUDE.md`, your foundations, deliverables, logs, and every file you create. **No upgrade, rollback or install ever writes to these.** |

An upgrade changes the machine. It never touches your work.

## Why a release and not just "pull main"

A release is a **pin**: one exact commit, plus the sha256 of every file in it, plus a human's
approval. That means your workspace can answer three questions that "I cloned it in June"
cannot: exactly what you have, whether it still matches, and what changes if you upgrade.

Founder ruling **D3**: a workspace installs an **approved, versioned release**, never mutable
`main`. The installer enforces it - an unapproved or unpinned release is refused, and so is
one whose files no longer hash to what the manifest recorded.

## The commands

```bash
python3 scripts/aios/aios.py start                 # who you are, what you may do, what is installed
python3 scripts/aios/aios.py verify --target .     # does this workspace still match its release?
python3 scripts/aios/aios.py verify --target . --repo ../ff-aios-starter   # ...and does the record still match the pin?
python3 scripts/aios/aios.py rollback --target .   # back to the previous release
```

**Upgrade runs from a fresh copy of the Starter, not from inside your workspace.** The releases
and the exact commits they pin live in the Starter repository, and your workspace carries
neither. So, from an up-to-date clone of `ff-aios-starter` next to your workspace:

```bash
cd ../ff-aios-starter && git pull
python3 scripts/aios/aios.py upgrade --release releases/starter-X.Y.Z.json --target ../my-workspace --dry-run   # what would change; writes nothing
python3 scripts/aios/aios.py upgrade --release releases/starter-X.Y.Z.json --target ../my-workspace
```

That also means the upgrade always runs the *new* release's tool, so a fix in the tool reaches
you on the upgrade that installs it. Commit your workspace first: an upgrade refuses a workspace
with uncommitted work.

`start` and `verify` are safe to run any time and change nothing. `upgrade` and `rollback` are
founder-only.

## Upgrading from Starter 2.x to 3.0 (the folder move)

3.0 replaces the numbered folders (`01_Foundations` ... `11_Projects`) with seven domain folders (`00_AIOS` ... `05_Jobs`, `99_Archive`). The upgrade moves your files for you. The exact map is in the release record, so it was approved with the release. `00_AIOS/routing.md` lists every old folder and its new home.

This is the one time an upgrade changes where your files are. It still never changes what's in them.

**What it does:**
- **Moves every file in an old folder,** including files you made yourself and files git ignores (your `.env`, `node_modules`). Each file keeps its exact bytes, size and permissions: only its path changes. Afterwards every moved file is re-hashed, and `layout_proof.json` in the upgrade's backup lists each file's old path, new path and hash.
- **Never rewrites a starter file.** Starter files are yours once installed, so the 3.0 wording of a file you already have doesn't replace yours, edited or not. New folders get their new starter files.
- **Adds one line to your `CLAUDE.md`:** `@00_AIOS/routing.md`, so Claude reads the new folder map. The dry run shows it first. It's added once, never twice, and every other byte of your `CLAUDE.md` stays the same. Rollback takes it back.
- **Keeps empty folders.** An empty folder of yours moves too.
- **Sets aside system junk.** `.DS_Store`, `Thumbs.db` and `desktop.ini` aren't moved: they're kept in the upgrade's backup, and rollback puts them back.
- **Lists what you should check:** files of yours that still mention an old folder. They aren't edited, so update them when you're ready.

**What it refuses, changing nothing:**
- uncommitted work;
- a file that would land where something already exists, including a name that differs only in capital letters or accents (a Mac or Windows disk treats `Plan.md` and `plan.md` as one file);
- two of your files that would land on one name;
- a symbolic link, a nested repository or submodule, or a file on another disk, inside an old folder;
- **a Vercel project that still builds a folder it moves.** The upgrade asks Vercel, read-only, with your token (`VERCEL_TOKEN`), and refuses until every such project's Root Directory names the new folder. If this repository isn't deployed by Vercel at all, say so with `--no-vercel` instead; that's recorded with the upgrade, and refused if Vercel's own files are in the folders that move. Card: [Move a Vercel site to its 3.0 folder](human_steps/move_a_vercel_site.md).

**Afterwards:**
1. Commit. Git shows the change as renames, so the history of each file follows it.
2. **Restore founder review at the new paths.** `.github/CODEOWNERS` is yours, so the upgrade doesn't rewrite it, and it still names the old founder-only folder. Until you fix it, GitHub doesn't ask a founder about changes there, and `aios instance check` fails. Card: [Restore founder review after the 3.0 move](human_steps/restore_founder_review.md).

**If it's interrupted** (power cut, killed terminal): the whole move was written down before the first file moved. `rollback` puts every file back from wherever it stopped.

**Going back:** `rollback` reverses every move, puts the set-aside files back, removes the 3.0 starter files you haven't touched, and takes back the `CLAUDE.md` line. Right after an upgrade, the workspace comes back exactly as it was. A file you edited after upgrading goes back to its old path with your edit; one you deleted stays deleted. If something of yours now sits at an old path, rollback refuses before changing anything.

## Upgrading to 3.1 (two CODEOWNERS rules)

From 3.0.0 it's an ordinary upgrade: nothing moves. One step afterwards. The upgrade adds the install record (`.aios/install.json`) and the adoption plan (`.aios/adoption.json`) to the founder lane in `.aios/roles.json`, because they say which files are the installer's own. `.github/CODEOWNERS` is yours, so the upgrade doesn't write it. Add a rule for each, with the same handles as your `/.aios/roles.json` line (an adopted repository with its plan elsewhere uses that plan's path, `adoption.plan` in the record), and merge it with a founder's approval. The upgrade's output ends with a `NEXT:` line saying so while it isn't done. Until you do, `aios instance check` fails and `start` shows `founder review: NOT RESTORED`. Card: [Restore founder review](human_steps/restore_founder_review.md), section "After upgrading to 3.1".

## Getting an exact release

Every release is a record, `releases/starter-X.Y.Z.json`, plus a tag, `starter-X.Y.Z`. The
record lives in `releases/`, which the package never ships, so the commit that records a
founder's approval installs exactly the same files as the commit it pins. **That approval
commit is the one tagged.** A checkout of the tag then carries the approved record, and the
installer accepts it.

```bash
git clone https://github.com/funnel-futurist/ff-aios-starter.git
cd ff-aios-starter
python3 scripts/aios/aios.py release check-tag starter-X.Y.Z --release-id starter-X.Y.Z
git checkout starter-X.Y.Z        # only once check-tag says the tag is the approved release
```

`check-tag` proves both halves: the record at the tag is approved and pinned, and every
package file at the tag is byte-identical to the pin. If it refuses, don't install from the
tag.

Published tags are never moved. One was withdrawn: `starter-2.6.0`, on 2026-10-14. That
release bundled third-party document-skill files whose licence doesn't allow redistribution,
and it was already superseded, so it can't be installed. Workspaces still on 2.6.0 upgrade
as usual; the upgrade removes those copies.

## Installing a new workspace

```bash
python3 scripts/aios/aios.py install \
  --release releases/starter-X.Y.Z.json \
  --target ../my-new-workspace \
  --config my-org.json
```

The target must be clean. The installer materialises every file from the pinned commit,
verifies the result by **re-hashing what landed on disk**, and writes `.aios/install.json`
recording exactly what you have. If the readback disagrees with the manifest, the install fails
- "the installer said it worked" is not evidence.

It checks everything before it writes the first file, and refuses with nothing changed if:
- a release file is already in the target;
- you already have a `CODEOWNERS` file (in `.github/`, the top folder or `docs/`). Yours is never
  replaced, and never shadowed by one GitHub would read first;
- `.aios/config.json` holds a different config;
- a folder it would write into is a link;
- an owner in `code_owners` isn't `@user`, `@org/team` or an email, or isn't one of your `people`.
  GitHub silently ignores such an owner, so the rule would protect nothing.

A starter file you already have, such as your own `README.md`, stays exactly as it is and is
recorded as yours.

Anything you have to do by hand along the way (2FA, a scoped token, a backup, connecting Vercel, removing someone, running a command Claude gives you) has a click-by-click card in [`docs/human_steps/`](human_steps/README.md).

### Your organization config

```json
{
  "schema": "ff-aios-starter/org-config@1",
  "org_id": "acme",
  "repository": "acme/acme-aios",
  "people": [
    {"github": "acme-founder", "role": "founder", "display_name": "Dana"},
    {"github": "acme-va", "role": "operator", "display_name": "Sam"}
  ],
  "credentials": {"ANTHROPIC_API_KEY": "env:ANTHROPIC_API_KEY"},
  "code_owners": {"REPO_OWNER": ["@acme-founder"], "PRIMARY_REVIEWER": ["@acme-founder"]}
}
```

**Credentials are references, never values.** `env:NAME` reads an environment variable;
`dotenv:NAME` reads a name from your `.env`. The config records *where* the key lives, never
the key. A config carrying an actual key is refused.

A missing **required** credential fails the install loudly and writes nothing. A missing
**optional** one installs and says so on every `start` and `verify`. Neither one leaves you
with a workspace that looks fine and quietly does half its job.

### Optional FF Intelligence capability

An entitled workspace can use the managed thin client at `.aios/core_bridge/core_call.py`.
The private method stays on FF's side. Copy its example configuration to the ignored,
client-owned `instance.json`, store the issued key as `FF_CORE_KEY`, and run the capability
named by FF. The client keeps the returned reports even if future access is withdrawn.

The Starter does not imply entitlement or a live endpoint. A missing optional key remains an
explicit not-configured state, and the caller refuses insecure remote endpoints, oversized
responses and output paths that escape the instance.

## Already have a workspace from "Use this template"?

That button copies whatever was on the default branch that day, so nothing records which
version you have. `start` will say `UNPINNED`. To put it on the contract:

```bash
python3 scripts/aios/aios.py adopt --release releases/starter-X.Y.Z.json --target . --config .aios/config.json
```

Adopt succeeds only if your files match that release byte for byte, executable bits included. If it refuses, you have
local changes to the system layer - that is information, not a failure.

## Adopting into a repository you already have (3.1)

If your company already runs its own repository and it was never a Starter copy, `adopt --existing`
brings in the parts of a release you choose, and nothing else. It only ever **creates** files. It
never overwrites, merges or deletes one of yours.

You decide everything in a plan file you commit first, `.aios/adoption.json`. It lists every path
the release ships under exactly one heading:

```json
{
  "schema": "ff-aios-starter/adoption@1",
  "adopt":          ["scripts/aios/**", ".aios/.gitignore", ".template_version.json"],
  "instance_owned": ["CLAUDE.md", "README.md", ".gitignore", ".aios/roles.json", "..."],
  "exclude":        ["docs/**", "00_AIOS/**", "..."]
}
```

- **adopt:** files the release manages. It creates them, and later upgrades keep them current.
  They must not exist yet. A plan that adopts a seed file (such as `CLAUDE.md` or `.gitignore`)
  is refused: a seed is written once and is then yours, so it can't be kept current.
- **instance_owned:** yours, even where the release ships a file at the same path. Never written,
  now or on any upgrade. They must exist.
- **exclude:** never written. The release's copy simply isn't used here.

Then commit your own role policy (`.aios/roles.json`) and run it as someone that policy lets
`adopt` (your instance's policy decides, not the release's). Run it from an up-to-date clone of
`ff-aios-starter`, which is the release's source, beside your repository. Your repository doesn't
have the installer yet, and the people map file must stay outside it (an uncommitted file inside it
is uncommitted work, which refuses):

```bash
cd ../ff-aios-starter
python3 scripts/aios/aios.py adopt --existing --release releases/starter-X.Y.Z.json --target ../my-repo --config ../my-org.json
```

**It refuses, with nothing changed, if:**
- a path the release ships isn't in the plan, or is under two headings;
- the plan uses a catch-all such as `**` (name what each heading covers, so nothing is
  classified silently), or adopts nothing;
- the plan or the role policy isn't committed, or this isn't a git repository;
- one of the installer's own paths (`.aios/lock`, `.aios/txn.json`, or a name it gives its
  temporary files) is taken, `.aios` itself is a link, or `.aios/backups/` already holds files;
- your repository tracks a file at a path the Starter's tools write and keep local
  (`.aios/release_notice.json`, `.aios/usage/identity.json`);
- a file it would create is ignored by your git rules (it would never reach your commit);
- an adopted path already exists, or the way to it runs through a link or another repository (a
  submodule, initialized or not, whose files your repository could never commit);
- a path you called yours is missing;
- you have no role policy of your own (rollback and upgrade read it), or nobody in the people map
  holds a role it lets both upgrade and roll back;
- you have uncommitted work, or the workspace is already pinned to a release.

**An existing instance never gets a folder move or a seed line.** Your folders stay where they
are, even one with a Starter 2.x name, and your `CLAUDE.md` is never edited.

**Undoing it:**
- The adoption is journaled before its first write, and each file is recorded once it exists.
- Each new file appears whole and can never replace one that appeared meanwhile.
- `aios rollback` takes back exactly what it created and left unchanged, whether the adoption
  finished or was killed partway.
- Undoing a finished adoption needs the release's source, as an upgrade does:
  `aios rollback --target . --repo <your ff-aios-starter clone>`. The install record is committed,
  so anyone's pull request could change it. So, to decide what to remove, rollback trusts the
  release source and the install record and plan as they were committed with the adoption. Before
  you commit, it trusts the sealed record on disk and the plan at `HEAD`.
  - It removes only files the pinned release ships, that the plan adopted, and that still have the
    release's bytes and mode. Once the adoption is committed, that commit must have added every one
    of them, and the record must claim exactly them; otherwise rollback refuses and changes nothing.
    So commit an adoption as one commit (`git add -A`, then `git commit`), as `adopt` says.
  - It removes the people map only if git shows it arrived with the adoption and hasn't changed
    since.
  - It refuses, changing nothing, if the record on disk differs from the copy committed with the
    adoption, or if the plan committed with the adoption isn't the one the adoption was made with.
    A plan you change later is never read by rollback, so it can't widen what rollback removes.
  - A rollback killed partway needs `--repo` again to finish.
- A file you've changed since is left in place, and the message says so.
- The install record (`.aios/install.json`) is what says which files the adoption made, so it is
  sealed. If its content has been edited, rollback refuses and changes nothing until you restore
  it from git (`git checkout -- .aios/install.json`). If only its permissions changed, rollback
  undoes the adoption, leaves the record, and says the workspace stays pinned until you delete it.
- Folders the adoption made are removed once they're empty again; a folder it can't prove it
  made (one you replaced, say) is left. So is a folder of yours that a kill caught between being
  made and being recorded: an empty folder, left rather than risk removing one that isn't the
  adoption's.
- Temporary files a killed operation left in `.aios` are removed by `aios rollback`: only the
  names the installer itself makes.
- A lock left by an adoption killed before it changed anything is cleared by `aios rollback`
  with no role needed. A running operation's lock is never taken; one that names no process
  (its holder was killed while writing it) is cleared like any dead one.

**What adoption and its rollback trust:**
- **Who may change the ownership list (3.1).** The install record and the plan say which files are the
  installer's own, and an upgrade or the undo acts on them. So both are in the founder lane: a pull
  request from anyone who isn't a founder needs a founder's approval (or a declared founder-lane
  reviewer's) to change either, and Claude won't edit them for an operator. An instance with its own
  role policy puts both in that policy's `paths_denied` for every role that isn't a founder, and gives
  each a CODEOWNERS rule (a plan kept somewhere else than `.aios/adoption.json` too, at its own path).
  Until it does, `instance check` fails and `start` shows `founder review: NOT RESTORED`.
- Rollback trusts the release source, and what your repository has committed: the install record
  and plan exactly as committed with the adoption.
- To decide what to remove, it never trusts a file that anyone's pull request could change after
  that. Who may run rollback still comes from the current role policy and people map. A changed
  record or a committed journal makes rollback refuse, changing nothing. A plan changed later isn't read at all:
  rollback uses the plan as committed with the adoption (before the adoption is committed, the one
  at `HEAD`, which must still be the plan the adoption was made with).
- The same holds for rolling back an upgrade. The upgrade keeps a copy of the record it wrote in its
  own snapshot under `.aios/backups/`, which is local. Rollback refuses unless the committed record is
  still exactly that copy. An adopted instance's upgrade always keeps one.
- Each adoption, upgrade and rollback also notes, locally (`.aios/backups/state/head.json`), which
  record it wrote. When this machine has that note, rollback refuses unless the record is still that
  one. So a changed record, or an older one restored to replay an earlier rollback, is refused.
- An upgrade trusts the record the same way. It must be the one the note names, when there is a
  note. Every workspace's record must also match the release it's pinned to, checked against the
  release source: the source's own record of that release names the same commit and version, and
  each file the record calls managed is one that release ships as managed, with its bytes and
  executable bit. The record must also list every file that release manages (for an adopted
  workspace, each its committed plan adopts that is in the workspace), so an upgrade removes every
  managed file the new release stops shipping. On an adopted workspace it removes only the ones the
  plan still adopts; the rest stay, as yours. The folder layout is the pinned release's, as the
  release source records it; a record that names another layout is refused.
- A seed line the record says a release appended must be one that release (yours or an earlier one)
  declared, with exactly the bytes the installer appends. Rolling back an upgrade takes back only the
  lines that upgrade itself appended, never one carried in the record from before. An entry the
  record's git history had can't be taken out. And a line declared by a release this workspace has
  had (its own, or one at or below it that the record's git history names) is never appended again,
  whatever the record lists, so a line you removed stays out. After a rollback, or a merge that sets
  the record back to an older release, a newer release's line counts as not had yet: the next
  upgrade may append it again, as that release did.
- Every seed a release this workspace has had shipped, and every seed path the record's git history
  listed (for its release or an older one), stays yours: a later release never recreates it where
  you deleted it, nor takes it over, whatever the record now lists.
- On a machine with no note of the last operation, an adopted workspace's record may call a file
  managed (the release's to update, and to remove once a release retires it) only if git history
  shows the installer made it: every commit that ever added it, on any side of any merge (the
  adoption's, or an upgrade's), listed it in the record it committed. Otherwise upgrade refuses,
  changing nothing, and `verify --repo` reports it, on every machine. So commit each upgrade as one commit (`git add -A`, then
  `git commit`), as for the adoption. If you once had a file of your own at a path a later upgrade
  created, a fresh clone can't tell the two apart and refuses: run the next upgrade where the last
  operation ran.
- Every field of the record is accounted for. `release`, `managed`, `layout`, `seeded`,
  `seed_history`, `seed_lines`, `seed_lines_added` and `adoption` are checked as above. `schema`
  and `package` must be the installer's own. `created_seeds`, `pre_existing_dirs` and
  `layout_migration` are read only by rolling back an upgrade, which needs the record to equal the
  copy that upgrade kept on this machine. `previous` is read there too, and in two more places:
  rollback treats an adopted record that has one as an upgrade to roll back (which needs that
  copy), not as the adoption to undo; and a committed record that has one, after the adoption,
  makes undoing the adoption on a fresh clone refuse. `upgrade` shows the one it just wrote.
  `record_sha256` (an adoption's seal)
  is trusted only while the adopted record isn't committed yet, as your own local state; when an
  adoption is undone, a record whose seal no longer matches is left in place. `rendered` is only
  checked for presence by `verify`. `credentials` is only shown, by `verify`, as references.
  `status`, `adopted` and `upgraded_at` only have their type checked; `installed_at` and `source`
  are never read. `aios start` checks founder review from the files in every pinned workspace (the
  local check `aios instance check` also makes), whatever the record says about its layout; with no
  usable install record it says UNPINNED instead.
- Every command that reads the record or the plan, and what it trusts:
  - `upgrade` and its dry run: each field as described above (the release source, git history, and
    this machine's note when there is one), and the plan file you committed, which it applies.
  - `verify --repo`: the same checks, reported rather than acted on, without the note. Plain
    `verify` checks only the record's own consistency, its paths and its git history.
  - Rolling back an upgrade: only a record equal to the copy that upgrade kept on this machine.
  - Undoing an adoption: only the record and plan as committed with the adoption, the release
    source, and git history since; with a note, the record that note names.
  - Recovering an interrupted operation: its local journal, and a record it names.
  - `install`, `adopt` and `adopt --existing`: they write the record, and read it only to refuse
    when one is already there.
  - `aios start`: the release line and any drift it shows; the founder-review check doesn't use it.
  - The new-release notice (also run by the session hook): the installed version, to say whether a
    newer approved release exists. Only the notice's text depends on it.
  - Clearing a dead lock: only whether a record exists.
  - The release notice's cache and the session's identity cache are written only where your
    repository has no file of its own. A copy your repository tracks, or one reached through a link
    or a submodule in any folder on its path, is never read as a cache, and a cache that isn't a
    JSON object is ignored, never an error.
- An upgrade made before 3.1 kept no copy of the record it wrote, so this installer won't roll it
  back: only the committed record could say what that upgrade changed. It refuses, changing nothing.
  Roll it back with that release's own installer, the one in the workspace
  (`python3 scripts/aios/aios.py rollback --target .`), or with git.
- A record that isn't in the shape the installer writes (a list that isn't a list, a path that isn't
  text, an adoption missing any of its parts) is refused when it's read, before anything else.
- Whether a workspace was adopted comes from git history, not from the record: if any commit added
  the record with an adoption in it, the record must still say so, naming the same plan. A record
  that says adopted when no commit added it that way is refused too. That counts every branch a
  merge brought in.
- A shallow clone can't show the committed record's history, so an upgrade, and undoing a
  committed adoption, refuse there, and `verify` reports it, until you run `git fetch --unshallow`.
- A snapshot holding anything git tracks is refused.
- The installer's folder `.aios` must be this repository's own: never a link, and never another
  repository (a submodule, or a repository inside this one), whose files this repository's checks
  can't see. No file an install, adoption, upgrade or rollback writes goes under another repository
  anywhere: a folder with its own `.git`, or one your repository records as a submodule,
  initialized or not. That covers every path each one touches: the files it writes or removes, a
  2.x to 3.0 folder move's paths at both ends, the file a seed line goes into, and the installer's
  own lock, temporary and state folders under `.aios/`. Each refuses before its first write, and so
  does a rollback that finishes or undoes an interrupted operation: it checks again, since a submodule
  could have appeared while the operation was stopped.
- Undoing a committed adoption on a machine with no note of the last operation (a fresh clone)
  needs no upgrade or rollback since the adoption, as the record's git history shows, on every
  branch a merge brought in (even when the merge set the record back). It also needs the record to
  have been added only once in that history: if it was added again (an adoption undone and made
  again, or a pull request that removed the record and added one back), git can't say which
  addition was the adoption. In either case it refuses, changing nothing: undo the adoption where
  it ran, or with git. The adoption may be committed in a merge commit; what it added is then what
  that commit has and none of its parents had.
- An adoption plan must be committed under exactly its own name.
- It trusts your own local, uncommitted state: the ignored journal of an operation that was
  interrupted, and a record not yet committed. Whoever can edit those can already change any file
  in the repository directly.
- It doesn't defend against another program changing the repository while it runs, beyond refusing
  links and checking again before each write.
- Files are compared byte for byte, as every release has. A checkout that converts line endings
  (`core.autocrlf=true`) reads as changed, so keep it off for this repository, or use a
  `.gitattributes` with `* text=auto eol=lf`. The installer writes its own records as the same
  bytes on every system, Windows included, and a rollback puts the install record back exactly as
  it was.

**Upgrades** write only what the plan adopts:
- A new path the release ships must be added to the plan first, or the upgrade refuses.
- A file you move from `adopt` to `instance_owned` stays where it is, and becomes yours when the
  next upgrade applies the plan. Until then it's still checked as a release file, so editing it
  first makes that upgrade refuse.
- Your role policy must still let someone in the people map both upgrade and roll back, or the
  upgrade refuses.
- `aios verify --repo` takes the adopted files from your plan file, not from the install record,
  and reports a plan that isn't committed or has uncommitted changes. A plan you've changed since the last adoption or upgrade is reported until an upgrade
  applies it.

## What upgrade actually does

1. Refuses unless the new release is approved, pinned and intact.
2. Refuses if your workspace has **drifted** (a managed file edited by hand) or if git has
   uncommitted changes. Both are refusals rather than overwrites, on purpose. For an edited
   file it prints the diff and the two ways forward: revert it, or keep your change by moving
   it into a file the release doesn't manage. For `.claude/settings.json` that file is
   `.claude/settings.local.json` (see "Your own settings" below).
3. Refuses if the new release ships a path that already exists as your own file. The likeliest
   one is `AGENTS.md`, which the Starter generates for Codex from `CLAUDE.md` and the operator
   core. If you wrote your own, move your rules to `~/.codex/AGENTS.md` (Codex reads it in every
   project) or to an `AGENTS.md` inside one of your folders, delete the root one, then upgrade.
4. Snapshots every managed file and writes a journal **before** changing anything.
5. Replaces managed files. Adds new seed files only where they do not already exist.
   **Seed files are never upgraded:** `CLAUDE.md` and the foundation folders are written once and
   are yours from then on, so an improvement to them reaches an existing workspace only through
   the release notes. **One exception, declared in the release:** a *seed line*, one line a
   release adds once to a seed file that predates it. From 2.7.2 that is the operator core's
   import in `CLAUDE.md` (`@.aios/operator_core/OPERATOR_CORE.md`). It is added once, never
   twice, never into a `CLAUDE.md` you deleted, never through a link or into a submodule, and never
   again after you remove it; a rollback
   takes it back; `--dry-run` shows it; `verify` reports whether it is still there.
6. Re-hashes everything and compares it to the new manifest.

If any step fails, it puts the workspace back and verifies that it did. If the machine dies
mid-upgrade, the journal survives and `rollback` recovers from it. Both paths are tested,
including against a hard kill.

## Your own settings (changes that never block an upgrade)

`.claude/settings.json` is managed: it carries the safety deny rules, the three hooks and the
document-skills plugin, and **editing it by hand blocks the next upgrade** (the refusal prints your
diff and says why). The supported way to change Claude Code's behaviour in your workspace is a file
you own:

```
.claude/settings.local.json
```

Claude Code reads it natively and applies it over `.claude/settings.json` (its settings
documentation lists project-local above shared-project settings). List settings such as
`permissions.allow` and `permissions.deny` **merge**: yours are added to ours, they do not replace them.

```json
{
  "permissions": {
    "deny": ["Read(./clients-private/**)"]
  }
}
```

| | |
|---|---|
| **Who owns it** | You. It is listed under `client_owned` in the package spec: no release ever ships it, and install, upgrade, rollback and `verify` never write, replace, verify or remove it. A release build refuses a source that tracks one. |
| **What it can do** | Add permission rules (`allow`, `deny`, `ask`) and set options. This is what Claude Code's settings documentation describes for the project-local file. |
| **What it cannot do** | Take away a permission rule the release ships: lists merge, so ours stay. If you need one removed or changed, that is a request for a release, not a local edit. How a local file interacts with the release's three hooks is not something this guide has verified, so do not rely on it to change or remove them. |
| **Git** | The Starter's `.gitignore` already ignores it, so it is personal and per machine. To share one override with your whole team, delete that line from your `.gitignore` (the file is yours) and commit the override on purpose; Claude Code then asks for workspace trust before it applies the file's `allow` rules. |
| **Proof** | The test suite asserts the override is byte-identical after an upgrade and after a rollback, with the workspace under git, committed or not. |

What it does not give you, honestly: an untracked file never reaches a pull request, so the
`boundary` check cannot see it, and the in-session founder-lane guard is only as strong as each
person's own settings on their own machine. It protects your ability to upgrade, not anyone's
ability to be held to the lane.

## Rollback

```bash
python3 scripts/aios/aios.py rollback --target .
```

Restores the previous release's managed files, removes what the newer one added, and verifies
the result by readback. Your work is untouched in both directions - the test suite asserts the
fingerprint of every non-managed file is identical after an upgrade *and* after a rollback.

## Roles, honestly

Identity comes from your authenticated GitHub CLI. Your role comes from the people map in
`.aios/config.json`. An operator gets the operator lane; upgrades, rollbacks and governance are
founder-only, and the tool refuses anyone else.

Some paths belong to the founder lane: the offer economics folder, `.github/`, the people map and
role policy, the install record and an adoption's plan, Claude's safety settings and hooks, and the
install tool itself (the full list is `paths_denied` in `.aios/roles.json`). They are held in two places:

1. **In the session.** Claude will not edit them for an operator, or for anyone it cannot
   identify. It says why and offers to hand the change to a founder.
2. **At the pull request.** The `boundary` check fails a pull request that changes them, unless
   the author is a founder or a founder has approved that exact commit (when your role policy names
   founder-lane reviewers, one of them instead; never the author). It reads the rules from
   the base branch, so a pull request cannot loosen its own check.

Both compare each path the way a Mac or Windows disk resolves the name (3.1): a different
capitalization, a Windows spelling (a trailing period or space, a stream suffix like `:x`) or another
Unicode form of a founder-lane path counts as that path. A name that could be a Windows short name
(like `INSTAL~1.JSO`) counts as founder-lane wherever it is, because it could stand for any long name.

What neither stops, honestly: somebody editing files by hand in their own terminal and pushing
straight to `main`. Only GitHub can stop that, with branch protection that requires pull
requests, code-owner review and the `boundary` check. Turn it on, then prove it:

```bash
python3 scripts/aios/aios.py governance check
bash scripts/team/verify-branch-protection.sh
```

A `CODEOWNERS` file full of `[REPO_OWNER]` placeholders enforces **nothing** - GitHub matches
no one - and neither does a perfectly filled one if branch protection is off.

**Who may approve the founder lane is not who is a founder.** By default, `aios instance check`
expects every owner on a founder-lane CODEOWNERS rule to be a founder or co-founder in your people
map, because GitHub accepts any one listed owner's approval. If other accounts are trusted to
approve those paths without being founders, list every account that may approve them in your role
policy, founders included. Once set, the list replaces the founder default:

```json
"founder_lane_reviewers": ["@founder-account", "@co-owner-account"]
```

They must be single accounts in your people map (a team can't be checked).

- **The checks then accept only those accounts** (`aios instance check` and the pull request's
  boundary check), and call them approved founder-lane reviewers.
- **It's review permission only.** Founder status, and the founder-only actions (upgrade,
  rollback, governance), still come from each person's `role` in the people map.

## What protects you, and when it doesn't

A safeguard that did not run is not a safeguard. Claude Code treats a hook that fails to start
(for example, because its program is missing) as a non-blocking error and carries on, and there
is no setting that makes a failed hook block. So each protection below holds only under its
condition.

| Protection | Holds when | When it does not hold |
|---|---|---|
| Founder-lane edits refused in the session | Python 3 is installed and `gh` is signed in (an unidentified person gets operator limits) | Python 3 missing on that computer: the hook can't start and Claude Code skips it. Nothing in the session can warn, because the warning needs Python too |
| Risky git commands stop and ask you first (force-push, `reset --hard` and similar). They are not blocked: you can still say yes | Node.js is installed | Node.js missing: the hook is skipped, so there is no extra question. `start` warns, and the warning is not protection |
| Pull request that touches the founder lane shows red | GitHub Actions runs (server-side, independent of the laptop) | Always runs; it can only **block** a merge with branch protection on |
| Branch protection | The repository belongs to a paid plan, or is public | A private repository on a personal free account can't have it. GitHub answers "Upgrade to GitHub Pro or make this repository public" |
| Installed files match the release | `verify --repo` against the source | Without `--repo`, `verify` only checks the local record, which a local editor could also change |

## Two questions `verify` can answer

Without `--repo` it asks *"does this workspace still match what was installed?"*, using the record
in `.aios/install.json`. That record lives in your own repo, so a determined local editor could
change a managed file **and** its recorded hash, and the check would agree with itself.

With `--repo` it also checks the record against the source repository, as an upgrade does before
it writes (an upgrade also checks this machine's note of its last operation). Every file the record calls managed must be one the release ships as managed, with
the release's hash and executable bit, which catches exactly that. It takes the list of release
files from the source's own record of the release (its tag, then `releases/` as committed at the
source's `HEAD`), so a file dropped from the record and the disk together is caught. That record
must name the same commit and version as yours, and verify fails, as drifted, when the source has
no such record. The
output always says which of the two it ran. Use `--repo` when the answer matters to somebody other
than you.

Either way, a path in the record that would lead outside the workspace (an absolute path, `..`, a
drive letter or any other colon, or a folder that is a link) is reported without reading anything
there, and a record whose adoption doesn't match git history (see "What adoption and its rollback
trust") is reported. An install record that is itself a link, or sits under one, is refused.

## Hearing about a new release

Once a day, `aios start` and the session-start check look up the Starter's public release tags and
tell you in one line when a newer approved release exists: "Starter X is approved; this workspace
has Y". It only reads (the tag list and two public release records on GitHub), never changes
anything, and says nothing when you're offline. It names a release only when the record on `main`
and the one inside its tag both say approved, pinned to the same commit, so a withdrawn or replaced
release is never advertised. Before you upgrade, still run `check-tag` (above). To switch the check
off, set `AIOS_NO_RELEASE_NOTICE=1` in your environment.

## For maintainers: approving a release

1. Cut the draft: `python3 scripts/aios/aios.py release build --version X.Y.Z --rev <commit on main>`.
   The builder can only write `draft`.
2. The founder approves that exact commit, in their own words. Record it in
   `releases/starter-X.Y.Z.json` (`status: approved`, `approval.approved_by`, `approved_at`,
   `basis`) and merge that change to `main`.
3. Tag **the commit that recorded the approval** with an annotated tag, then prove it:
   `python3 scripts/aios/aios.py release check-tag starter-X.Y.Z --release-id starter-X.Y.Z`.
   Push the tag only once that passes. Never move a tag that is already published.

## Exit codes

`0` ok · `2` package (unapproved, unpinned, drifted) · `3` role · `4` credential ·
`5` state (dirty or partial) · `6` verification failed · `7` sanitization · `8` governance.
