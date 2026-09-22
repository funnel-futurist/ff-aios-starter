"""Install, verify, upgrade, rollback.

The whole design rests on one boundary:

* **managed** files belong to the release. The installer writes them, upgrade replaces them,
  rollback restores them, and `verify` re-hashes them. If you edit one, the workspace is
  *dirty* and upgrade refuses until you deal with it.
* **seed** files are yours the moment they land: `CLAUDE.md`, your foundations, your
  deliverables, your logs. Seeded once if absent, then **never touched again** by any
  lifecycle operation. This is what "upgrade preserves state" actually means.
* **everything else you create** is invisible to the installer. It is not in the manifest,
  so no operation can delete or overwrite it.

Verification is always **readback**: re-hash what is on disk and compare it to the manifest.
The installer reporting "done" proves nothing; the bytes on disk are the evidence.

Crash safety: every mutation runs inside a transaction that writes a journal *before*
touching anything and snapshots the managed files it is about to replace. A hard kill leaves
the journal on disk, and `rollback` uses it to put the workspace back. Recovery that has only
been tested against a clean exception is not recovery.
"""

import os
import shutil

from . import governance, orgconfig, release as release_mod, roles, util
from .util import (EXIT_PACKAGE, EXIT_STATE, EXIT_VERIFY, Refusal, sha256_bytes, sha256_file)

INSTALL_SCHEMA = "ff-aios-starter/install@1"
AIOS_DIR = ".aios"
INSTALL_PATH = os.path.join(AIOS_DIR, "install.json")
JOURNAL_PATH = os.path.join(AIOS_DIR, "txn.json")
BACKUP_DIR = os.path.join(AIOS_DIR, "backups")


# ─── records ────────────────────────────────────────────────────────────────

def install_record_path(target):
    return os.path.join(target, INSTALL_PATH)


def load_record(target):
    path = install_record_path(target)
    if not os.path.isfile(path):
        raise Refusal(EXIT_STATE, "no install record at %s; this workspace was never installed "
                                  "from a release" % path)
    return util.read_json(path)


def journal_path(target):
    return os.path.join(target, JOURNAL_PATH)


LOCK_PATH = os.path.join(AIOS_DIR, "lock")


class _Lock(object):
    """An exclusive lock for the duration of a mutation.

    The journal already makes a half-finished upgrade recoverable, but it is written *after*
    the workspace has been verified clean. Two upgrades started in the same second would both
    pass verification and then interleave their writes. `O_CREAT | O_EXCL` is atomic on every
    filesystem worth supporting, so the second one refuses instead of racing.

    A stale lock (the holder was killed) is recoverable: the message says how, and `rollback`
    clears it, because a lock that can wedge a workspace forever is its own outage.
    """

    def __init__(self, target, op):
        self.path = os.path.join(target, LOCK_PATH)
        self.op = op
        self.fd = None

    def __enter__(self):
        util.ensure_parent(self.path)
        try:
            self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except OSError:
            holder = ""
            try:
                with open(self.path) as fh:
                    holder = fh.read().strip()
            except OSError:
                pass
            raise Refusal(
                EXIT_STATE,
                "another %s is already running in this workspace" % self.op,
                [("lock held by: %s" % holder) if holder else "lock file: %s" % self.path,
                 "if nothing is running, the previous attempt was killed: run `aios rollback`, "
                 "or delete %s once you are sure" % LOCK_PATH],
            )
        os.write(self.fd, ("%s pid=%d at %s\n"
                           % (self.op, os.getpid(), util.now_iso())).encode("utf-8"))
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if self.fd is not None:
                os.close(self.fd)
            if os.path.exists(self.path):
                os.remove(self.path)
        except OSError:
            pass
        return False


def load_journal(target):
    path = journal_path(target)
    if os.path.isfile(path):
        return util.read_json(path)
    return None


# ─── verification ───────────────────────────────────────────────────────────

def verify(target, record=None):
    """Readback. Returns (problems, summary). Never trusts the record's own word."""
    record = record or load_record(target)
    problems = []
    checked = 0
    for entry in record.get("managed") or []:
        path = os.path.join(target, entry["path"])
        if not os.path.isfile(path):
            problems.append("missing managed file: %s" % entry["path"])
            continue
        actual = sha256_file(path)
        checked += 1
        if actual != entry["sha256"]:
            problems.append("modified managed file: %s (on disk %s, release %s)"
                            % (entry["path"], actual[:12], entry["sha256"][:12]))
    for entry in record.get("rendered") or []:
        if not os.path.isfile(os.path.join(target, entry["path"])):
            problems.append("missing rendered file: %s" % entry["path"])
    for entry in record.get("seeded") or []:
        if not os.path.isfile(os.path.join(target, entry["path"])):
            # Seeds are yours, including the right to delete them. Report, never fail.
            pass
    summary = {
        "release_id": (record.get("release") or {}).get("release_id"),
        "version": (record.get("release") or {}).get("version"),
        "managed_checked": checked,
        "managed_total": len(record.get("managed") or []),
    }
    return problems, summary


def require_verified(target, record=None, what="workspace"):
    problems, summary = verify(target, record)
    if problems:
        raise Refusal(EXIT_VERIFY, "%s does not match its installed release" % what, problems)
    return summary


def state_fingerprint(target):
    """Hash every file that is NOT owned by the release.

    Used by the tests to prove an upgrade and a rollback left state untouched: managed files
    change by design, everything else must be byte-identical afterwards.
    """
    record = load_record(target)
    managed = {e["path"] for e in record.get("managed") or []}
    out = {}
    skip_dirs = {".git", os.path.join(AIOS_DIR, "backups")}
    for root, dirs, files in os.walk(target):
        rel_root = os.path.relpath(root, target)
        rel_root = "" if rel_root == "." else rel_root
        dirs[:] = [d for d in dirs
                   if os.path.join(rel_root, d) not in skip_dirs and d != ".git"]
        for name in files:
            rel = os.path.normpath(os.path.join(rel_root, name)) if rel_root else name
            rel = rel.replace(os.sep, "/")
            if rel in managed or rel in (INSTALL_PATH, JOURNAL_PATH, LOCK_PATH):
                continue
            if rel.startswith(BACKUP_DIR.replace(os.sep, "/")):
                continue
            out[rel] = sha256_file(os.path.join(target, name) if not rel_root
                                   else os.path.join(target, rel))
    return out


# ─── transactions ───────────────────────────────────────────────────────────

def _backup(target, record, txn_id):
    """Snapshot the managed files and the install record before mutating either."""
    backup_root = os.path.join(target, BACKUP_DIR, txn_id)
    files_root = os.path.join(backup_root, "files")
    for entry in record.get("managed") or []:
        src = os.path.join(target, entry["path"])
        if not os.path.isfile(src):
            continue
        dst = os.path.join(files_root, entry["path"])
        util.ensure_parent(dst)
        shutil.copy2(src, dst)
    util.write_json(os.path.join(backup_root, "install.json"), record)
    return backup_root


def _restore(target, backup_root, record_to_restore, remove_paths):
    for rel in remove_paths:
        path = os.path.join(target, rel)
        if os.path.isfile(path):
            os.remove(path)
    files_root = os.path.join(backup_root, "files")
    for entry in record_to_restore.get("managed") or []:
        src = os.path.join(files_root, entry["path"])
        dst = os.path.join(target, entry["path"])
        if os.path.isfile(src):
            util.ensure_parent(dst)
            shutil.copy2(src, dst)
    util.write_json(install_record_path(target), record_to_restore)
    _prune_empty_dirs(target)


def _prune_empty_dirs(target):
    for root, dirs, files in os.walk(target, topdown=False):
        if os.path.abspath(root) == os.path.abspath(target):
            continue
        if ".git" in root.split(os.sep):
            continue
        try:
            if not os.listdir(root):
                os.rmdir(root)
        except OSError:
            pass


# ─── install ────────────────────────────────────────────────────────────────

def install(target, manifest, source_repo, config, aios_lookup=None, render_governance=True):
    """Install an approved, pinned release into a clean target. Verified by readback."""
    release_mod.require_consumable(manifest, source_repo, aios_lookup)
    orgconfig.require_valid(config)

    if os.path.isfile(install_record_path(target)):
        raise Refusal(EXIT_STATE, "this workspace already has an install record; use upgrade",
                      [install_record_path(target)])
    if load_journal(target):
        raise Refusal(EXIT_STATE, "a previous operation did not finish; run rollback first",
                      [journal_path(target)])

    files = {e["path"]: e for e in manifest.get("files") or []}
    managed_paths = [p for p, e in files.items() if e["class"] == "managed"]
    occupied = [p for p in managed_paths if os.path.exists(os.path.join(target, p))]
    if occupied:
        raise Refusal(
            EXIT_STATE,
            "target is not a clean environment: %d managed path(s) already exist" % len(occupied),
            sorted(occupied)[:20],
        )

    creds = orgconfig.resolve(manifest.get("credentials"), config, target)
    orgconfig.require_resolved(creds)

    managed, seeded, rendered = [], [], []
    template_text = None
    for path, mode, data in util.read_tree(source_repo,
                                           manifest["created_from"]["git_rev"]):
        entry = files.get(path)
        if entry is None:
            continue
        if entry["sha256"] != sha256_bytes(data):
            raise Refusal(EXIT_PACKAGE, "content at the pin does not match the manifest: %s" % path)
        if path == (manifest.get("render_template") or "templates/governance/CODEOWNERS.template"):
            template_text = data.decode("utf-8")
        dest_exists = os.path.exists(os.path.join(target, path))
        if entry["class"] == "seed" and dest_exists:
            continue  # yours already; never overwritten
        sha = util.write_file(target, path, data, entry.get("mode", "100644"))
        (managed if entry["class"] == "managed" else seeded).append(
            {"path": path, "sha256": sha})

    if render_governance and template_text:
        owners = config.get("code_owners") or {}
        if owners:
            text = governance.render(template_text, config["repository"], owners)
            sha = util.write_file(target, os.path.join(".github", "CODEOWNERS"),
                                  text.encode("utf-8"), "100644")
            rendered.append({"path": ".github/CODEOWNERS", "sha256": sha})

    util.write_json(orgconfig.default_config_path(target), config)

    record = {
        "schema": INSTALL_SCHEMA,
        "package": manifest["package"],
        "release": {
            "release_id": manifest["release_id"],
            "version": manifest["version"],
            "git_rev": manifest["created_from"]["git_rev"],
            "status": manifest["status"],
            "approved_by": (manifest.get("approval") or {}).get("approved_by"),
            "approved_at": (manifest.get("approval") or {}).get("approved_at"),
            "min_upgrade_from": (manifest.get("compatibility") or {}).get("min_upgrade_from"),
        },
        "installed_at": util.now_iso(),
        "source": os.path.abspath(source_repo),
        "status": "installed",
        # References only, plus whether they resolved at install time. No values, ever.
        "credentials": [{"name": c["name"], "ref": c["ref"], "required": c["required"],
                         "resolved": c["resolved"]} for c in creds],
        "managed": sorted(managed, key=lambda e: e["path"]),
        "seeded": sorted(seeded, key=lambda e: e["path"]),
        "rendered": rendered,
        "previous": None,
    }
    util.write_json(install_record_path(target), record)

    require_verified(target, record, "freshly installed workspace")
    return record, creds


# ─── upgrade ────────────────────────────────────────────────────────────────

def upgrade(target, manifest, source_repo, aios_lookup=None):
    """Replace managed files with a newer approved release. State is never touched."""
    with _Lock(target, "upgrade"):
        return _upgrade_locked(target, manifest, source_repo, aios_lookup)


def _upgrade_locked(target, manifest, source_repo, aios_lookup=None):
    record = load_record(target)
    if load_journal(target):
        raise Refusal(EXIT_STATE, "a previous operation did not finish; run rollback first",
                      [journal_path(target)])

    release_mod.require_consumable(manifest, source_repo, aios_lookup)

    current_version = (record.get("release") or {}).get("version")
    cur = util.parse_semver(current_version or "")
    new = util.parse_semver(manifest["version"])
    if cur and new and new <= cur:
        raise Refusal(EXIT_PACKAGE,
                      "release %s is not newer than the installed %s; use rollback to go back"
                      % (manifest["version"], current_version))
    min_from = (manifest.get("compatibility") or {}).get("min_upgrade_from")
    if min_from:
        mf = util.parse_semver(min_from)
        if cur and mf and cur < mf:
            raise Refusal(EXIT_PACKAGE,
                          "release %s cannot upgrade from %s (min_upgrade_from %s)"
                          % (manifest["version"], current_version, min_from))

    # Dirty or partial state is refused, never silently overwritten.
    require_verified(target, record, "workspace")
    if util.worktree_dirty(target):
        raise Refusal(EXIT_STATE,
                      "the workspace has uncommitted git changes; commit or stash them so the "
                      "upgrade is a reviewable diff and git gives you a second way back")

    config = orgconfig.load(target)
    creds = orgconfig.resolve(manifest.get("credentials"), config, target)
    orgconfig.require_resolved(creds)

    files = {e["path"]: e for e in manifest.get("files") or []}
    old_managed = {e["path"]: e for e in record.get("managed") or []}
    old_seeded = {e["path"] for e in record.get("seeded") or []}

    # A newly shipped path that already exists as something of yours is a collision. Refuse:
    # the alternative is silently eating a file the release never owned.
    collisions = []
    for path, entry in files.items():
        if path in old_managed or path in old_seeded:
            continue
        if os.path.exists(os.path.join(target, path)):
            collisions.append(path)
    if collisions:
        raise Refusal(
            EXIT_STATE,
            "release %s ships %d path(s) that already exist in this workspace and are not "
            "managed by the installed release" % (manifest["version"], len(collisions)),
            sorted(collisions)[:20] + ["move or delete them, then upgrade again"],
        )

    txn_id = "%s-%s-to-%s" % (util.now_iso().replace(":", "").replace("-", ""),
                              current_version, manifest["version"])
    backup_root = _backup(target, record, txn_id)
    util.write_json(journal_path(target), {
        "op": "upgrade", "txn": txn_id, "from_version": current_version,
        "to_version": manifest["version"], "backup": os.path.relpath(backup_root, target),
        "phase": "applying", "started_at": util.now_iso(),
        # What this upgrade intends to ADD. A hard kill can stop anywhere, and the install
        # record on disk still describes the OLD release, so it cannot tell recovery about
        # files the aborted attempt already created. Without this, rollback leaves orphans.
        "adds": sorted({p for p, e in files.items()
                        if e["class"] == "managed" and p not in old_managed}),
    })

    new_managed, new_seeded = [], []
    written = 0
    try:
        util.fault("upgrade.before_write")
        for path, mode, data in util.read_tree(source_repo, manifest["created_from"]["git_rev"]):
            entry = files.get(path)
            if entry is None:
                continue
            if entry["sha256"] != sha256_bytes(data):
                raise Refusal(EXIT_PACKAGE,
                              "content at the pin does not match the manifest: %s" % path)
            if entry["class"] == "seed":
                if not os.path.exists(os.path.join(target, path)):
                    sha = util.write_file(target, path, data, entry.get("mode", "100644"))
                    new_seeded.append({"path": path, "sha256": sha})
                else:
                    new_seeded.append({"path": path,
                                       "sha256": sha256_file(os.path.join(target, path))})
                continue
            previous = old_managed.get(path)
            sha = util.write_file(target, path, data, entry.get("mode", "100644"))
            new_managed.append({"path": path, "sha256": sha})
            if previous and previous.get("sha256") != sha:
                # Fire only after a file that genuinely CHANGED. Crashing after writing a
                # byte-identical file leaves a workspace that still verifies clean, which
                # would make the recovery test pass without recovering anything.
                written += 1
                if written == 1:
                    util.fault("upgrade.mid_write")

        # Managed files the new release dropped.
        for path in sorted(set(old_managed) - set(files)):
            full = os.path.join(target, path)
            if os.path.isfile(full):
                os.remove(full)
        _prune_empty_dirs(target)
        util.fault("upgrade.before_record")

        new_record = dict(record)
        new_record["release"] = {
            "release_id": manifest["release_id"],
            "version": manifest["version"],
            "git_rev": manifest["created_from"]["git_rev"],
            "status": manifest["status"],
            "approved_by": (manifest.get("approval") or {}).get("approved_by"),
            "approved_at": (manifest.get("approval") or {}).get("approved_at"),
            "min_upgrade_from": min_from,
        }
        new_record["managed"] = sorted(new_managed, key=lambda e: e["path"])
        new_record["seeded"] = sorted(new_seeded, key=lambda e: e["path"])
        new_record["credentials"] = [{"name": c["name"], "ref": c["ref"],
                                      "required": c["required"], "resolved": c["resolved"]}
                                     for c in creds]
        new_record["upgraded_at"] = util.now_iso()
        new_record["status"] = "installed"
        new_record["previous"] = {
            "release_id": (record.get("release") or {}).get("release_id"),
            "version": current_version,
            "backup": os.path.relpath(backup_root, target),
        }
        util.write_json(install_record_path(target), new_record)
        require_verified(target, new_record, "upgraded workspace")
    except BaseException as exc:
        # Any failure puts the workspace back where it started, then re-raises.
        #
        # Remove only MANAGED paths the new release introduced. An earlier version of this
        # line removed `set(files) - set(old_managed)`, which includes every *seed* path -
        # so a failed upgrade deleted CLAUDE.md, the foundations and the logs while
        # reporting a clean rollback. The state-fingerprint test caught it.
        new_managed_paths = {p for p, e in files.items() if e["class"] == "managed"}
        _restore(target, backup_root, record,
                 remove_paths=sorted(new_managed_paths - set(old_managed)))
        problems, _ = verify(target, record)
        if os.path.isfile(journal_path(target)):
            os.remove(journal_path(target))
        if problems:
            raise Refusal(EXIT_VERIFY,
                          "upgrade failed AND the automatic rollback did not restore cleanly",
                          [str(exc)] + problems)
        if isinstance(exc, Refusal):
            exc.details = list(exc.details) + ["workspace was rolled back to %s and verified"
                                               % current_version]
            raise
        raise Refusal(EXIT_VERIFY,
                      "upgrade failed and the workspace was rolled back to %s (verified)"
                      % current_version, [str(exc)])

    os.remove(journal_path(target))
    return new_record


# ─── rollback ───────────────────────────────────────────────────────────────

def rollback(target):
    """Restore the previous release. Works after a clean upgrade or a hard kill."""
    # A killed holder leaves its lock behind. Recovery is exactly when you need to get in, so
    # rollback clears it rather than telling the operator their workspace is wedged.
    stale = os.path.join(target, LOCK_PATH)
    if os.path.exists(stale):
        os.remove(stale)
    with _Lock(target, "rollback"):
        return _rollback_locked(target)


def _rollback_locked(target):
    journal = load_journal(target)
    record_path = install_record_path(target)
    current = util.read_json(record_path) if os.path.isfile(record_path) else None

    if journal:
        backup_root = os.path.join(target, journal["backup"])
        prior = util.read_json(os.path.join(backup_root, "install.json"))
        # A hard kill can land anywhere, so remove every path the new release owns that the
        # old one did not, rather than trusting how far the write loop got.
        prior_paths = {e["path"] for e in prior.get("managed") or []}
        current_paths = {e["path"] for e in (current or {}).get("managed") or []}
        remove = sorted((current_paths | set(journal.get("adds") or [])) - prior_paths)
        _restore(target, backup_root, prior, remove)
        os.remove(journal_path(target))
        problems, summary = verify(target, prior)
        if problems:
            raise Refusal(EXIT_VERIFY, "rollback did not restore a verifiable workspace", problems)
        return prior, summary, "recovered an interrupted %s" % journal.get("op", "operation")

    if not current:
        raise Refusal(EXIT_STATE, "nothing to roll back: no install record and no journal")
    previous = current.get("previous")
    if not previous:
        raise Refusal(EXIT_STATE, "nothing to roll back: this is the first installed release")

    backup_root = os.path.join(target, previous["backup"])
    if not os.path.isdir(backup_root):
        raise Refusal(EXIT_STATE,
                      "the snapshot for %s is gone, so rollback cannot restore it"
                      % previous.get("version"),
                      [backup_root, "re-install the previous release from its pin instead"])
    prior = util.read_json(os.path.join(backup_root, "install.json"))
    remove = sorted({e["path"] for e in current.get("managed") or []}
                    - {e["path"] for e in prior.get("managed") or []})
    _restore(target, backup_root, prior, remove)
    problems, summary = verify(target, prior)
    if problems:
        raise Refusal(EXIT_VERIFY, "rollback did not restore a verifiable workspace", problems)
    return prior, summary, "rolled back to %s" % prior["release"]["version"]


# ─── adopt ──────────────────────────────────────────────────────────────────

def adopt(target, manifest, source_repo, config, aios_lookup=None):
    """Pin an existing workspace that matches a release byte for byte.

    The "Use this template" button copies mutable `main`, which is the one thing founder
    ruling D3 forbids. Adopt is the way back onto the contract without reinstalling: it
    proves the tree on disk *is* an approved release, then writes the pin.
    """
    release_mod.require_consumable(manifest, source_repo, aios_lookup)
    orgconfig.require_valid(config)
    if os.path.isfile(install_record_path(target)):
        raise Refusal(EXIT_STATE, "this workspace already has an install record")

    managed, seeded, mismatches = [], [], []
    for entry in manifest.get("files") or []:
        path = os.path.join(target, entry["path"])
        if entry["class"] == "seed":
            if os.path.isfile(path):
                seeded.append({"path": entry["path"], "sha256": sha256_file(path)})
            continue
        if not os.path.isfile(path):
            mismatches.append("missing: %s" % entry["path"])
            continue
        actual = sha256_file(path)
        if actual != entry["sha256"]:
            mismatches.append("differs: %s" % entry["path"])
            continue
        managed.append({"path": entry["path"], "sha256": actual})
    if mismatches:
        raise Refusal(
            EXIT_VERIFY,
            "this workspace does not match release %s, so it cannot be pinned to it"
            % manifest["release_id"],
            mismatches[:20] + ["%d difference(s) total" % len(mismatches)],
        )

    creds = orgconfig.resolve(manifest.get("credentials"), config, target)
    orgconfig.require_resolved(creds)
    util.write_json(orgconfig.default_config_path(target), config)
    record = {
        "schema": INSTALL_SCHEMA,
        "package": manifest["package"],
        "release": {
            "release_id": manifest["release_id"], "version": manifest["version"],
            "git_rev": manifest["created_from"]["git_rev"], "status": manifest["status"],
            "approved_by": (manifest.get("approval") or {}).get("approved_by"),
            "approved_at": (manifest.get("approval") or {}).get("approved_at"),
            "min_upgrade_from": (manifest.get("compatibility") or {}).get("min_upgrade_from"),
        },
        "installed_at": util.now_iso(),
        "adopted": True,
        "source": os.path.abspath(source_repo),
        "status": "installed",
        "credentials": [{"name": c["name"], "ref": c["ref"], "required": c["required"],
                         "resolved": c["resolved"]} for c in creds],
        "managed": sorted(managed, key=lambda e: e["path"]),
        "seeded": sorted(seeded, key=lambda e: e["path"]),
        "rendered": [],
        "previous": None,
    }
    util.write_json(install_record_path(target), record)
    require_verified(target, record, "adopted workspace")
    return record
