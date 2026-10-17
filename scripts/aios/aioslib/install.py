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

import difflib
import json
import os
import re
import shutil
import stat
import time

from . import governance, hosting, layout as layout_mod, orgconfig, release as release_mod, roles, util
from .util import (EXIT_GOVERNANCE, EXIT_PACKAGE, EXIT_STATE, EXIT_VERIFY, Refusal, sha256_bytes,
                   sha256_file)

INSTALL_SCHEMA = "ff-aios-starter/install@1"
AIOS_DIR = ".aios"
INSTALL_PATH = os.path.join(AIOS_DIR, "install.json")
JOURNAL_PATH = os.path.join(AIOS_DIR, "txn.json")
BACKUP_DIR = os.path.join(AIOS_DIR, "backups")
LAYOUT_PLAN = "layout_plan.json"
LAYOUT_PROOF = "layout_proof.json"


# ─── records ────────────────────────────────────────────────────────────────

def install_record_path(target):
    return os.path.join(target, INSTALL_PATH)


def load_record(target):
    path = install_record_path(target)
    # The record and the folders on the way to it are real ones, never links: the record is committed,
    # and a committed link would have the installer trust bytes from anywhere (independent review, 3.1
    # round 45).
    rel = os.path.relpath(path, target).replace(os.sep, "/")
    if os.path.islink(path) or _linked_paths(target, [rel]):
        raise Refusal(EXIT_STATE, "the install record at %s is a link, or is reached through one (a link, or a "
                                  "folder that is another repository); nothing was changed" % path, ["restore .aios/install.json from git as a regular file, "
                                                     "then run this again"])
    if not os.path.isfile(path):
        raise Refusal(EXIT_STATE, "no install record at %s; this workspace was never installed "
                                  "from a release" % path)
    record = util.read_json_safe(path, "install record")
    problems = _record_shape_problems(record)
    if problems:
        raise Refusal(EXIT_STATE, "the install record at %s isn't in the shape the installer writes; nothing "
                                  "was changed" % path, problems[:20] + ["restore it from git"])
    return record


def _record_shape_problems(record):
    """What makes a record not the shape the installer writes, for every field the installer reads back.
    The record is committed, so a pull request could put any JSON there; a wrong type must refuse, not
    crash halfway (independent review, 3.1 rounds 41 and 42)."""
    if not isinstance(record, dict):
        return ["it isn't a JSON object"]
    problems = []

    def text(v, optional=True):
        return isinstance(v, str) or (optional and v is None)

    def number(v):
        return isinstance(v, int) and not isinstance(v, bool)

    def entries(key, fields, where=record, label=None):
        """Each entry an object whose `fields` ({name: test}) hold; a missing name fails its test with None."""
        label = label or key
        value = where.get(key)
        if value is None:
            return
        if not isinstance(value, list):
            problems.append("'%s' isn't a list" % label)
            return
        for i, entry in enumerate(value):
            bad = [n for n, ok in fields.items() if not isinstance(entry, dict) or not ok(entry.get(n), n in entry)]
            if bad:
                problems.append("%s[%d]: %s missing or of the wrong type" % (label, i, ", ".join(sorted(bad))))

    path = lambda v, _has: isinstance(v, str)  # noqa: E731
    sha = lambda v, _has: isinstance(v, str)  # noqa: E731
    opt_text = lambda v, _has: text(v)  # noqa: E731
    opt_bool = lambda v, has: not has or isinstance(v, bool)  # noqa: E731
    opt_number = lambda v, has: not has or number(v)  # noqa: E731

    # Every installer since 2.6.0 wrote these two exactly (independent review, 3.1 round 50).
    if record.get("schema") != INSTALL_SCHEMA:
        problems.append("'schema' isn't %s" % INSTALL_SCHEMA)
    if record.get("package") != release_mod.PACKAGE:
        problems.append("'package' isn't %s" % release_mod.PACKAGE)
    if "adopted" in record and not isinstance(record["adopted"], bool):
        problems.append("'adopted' isn't true or false")
    # Absent, or text: an explicit null is neither, and no installer writes one (3.1 round 51).
    if RECORD_SEAL in record and not isinstance(record[RECORD_SEAL], str):
        problems.append("'%s' isn't text" % RECORD_SEAL)
    rel = record.get("release")
    if not isinstance(rel, dict):
        problems.append("'release' isn't an object")
    else:
        problems += ["release.%s isn't text" % k for k in ("release_id", "version", "git_rev") if not text(rel.get(k))]
    entries("managed", {"path": path, "sha256": sha, "exec": opt_bool})
    entries("rendered", {"path": path, "sha256": opt_text})
    entries("seeded", {"path": path, "sha256": opt_text})
    entries("seed_lines", {"path": path, "line": path, "release": opt_text, "state": opt_text, "appended": opt_text})
    entries("seed_lines_added", {"path": path, "line": path, "release": opt_text, "appended": sha})
    entries("credentials", {"name": path, "ref": opt_text, "required": lambda v, _h: isinstance(v, bool),
                            "resolved": opt_bool})
    entries("created_seeds", {"path": path, "sha256": sha, "mode": opt_number})
    for key in ("seed_history", "pre_existing_dirs"):
        value = record.get(key)
        if value is not None and not (isinstance(value, list) and all(isinstance(p, str) for p in value)):
            problems.append("'%s' isn't a list of paths" % key)
    for key in ("layout", "status", "upgraded_at"):
        if not text(record.get(key)):
            problems.append("'%s' isn't text" % key)
    previous = record.get("previous")
    if previous is not None and not (isinstance(previous, dict) and isinstance(previous.get("backup"), str)
                                     and text(previous.get("version")) and text(previous.get("release_id"))):
        problems.append("'previous' isn't an object naming its backup, version and release")
    migration = record.get("layout_migration")
    if migration is not None and not (isinstance(migration, dict) and isinstance(migration.get("plan"), str)):
        problems.append("'layout_migration' isn't an object naming its plan")
    if "adoption" in record:
        # Adopted or not is whether the key is there; when it is, it's the whole object an adoption writes,
        # so an empty or partial one can't pass for either (independent review, 3.1 round 43).
        info = record["adoption"]
        if not isinstance(info, dict):
            problems.append("'adoption' isn't an object")
        else:
            problems += ["adoption.%s isn't text" % k for k in ("plan", "plan_sha256")
                         if not isinstance(info.get(k), str)]
            if not text(info.get("record_sha256")):
                problems.append("adoption.record_sha256 isn't text")
            for k in ADOPTION_CLASSES:
                value = info.get(k)
                if not (isinstance(value, list) and all(isinstance(p, str) for p in value)):
                    problems.append("adoption.%s isn't a list of patterns" % k)
            for k in ("created", "made_dirs"):
                if not isinstance(info.get(k), list):
                    problems.append("adoption.%s isn't a list" % k)
            entries("created", {"path": path, "sha256": sha, "mode": opt_number}, info, "adoption.created")
            entries("made_dirs", {"path": path, "dev": opt_number, "ino": opt_number, "reserved": opt_bool},
                    info, "adoption.made_dirs")
    return problems

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
        self.target = target
        self.path = os.path.join(target, LOCK_PATH)
        self.op = op
        self.fd = None

    def __enter__(self):
        # Taken under the workspace guard, so it can't land between a recovery's "this lock is
        # dead" and its removal (independent review, round 10). Its folder is made only there too,
        # after the guard has refused a `.aios` that is a link or a file (3.1 round 22).
        with _RecoveryGuard(self.target):
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
            words = ("%s pid=%d at %s\n" % (self.op, os.getpid(), util.now_iso())).encode("utf-8")
            os.write(self.fd, words)
            st = os.fstat(self.fd)
            self.ident = (st.st_dev, st.st_ino, words)
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if self.fd is not None:
                os.close(self.fd)
            # Only our own lock: if something replaced it, removing that would let a third
            # operation in alongside the one that holds it now (independent review). Checked and
            # removed under the guard, so nothing can take its place in between.
            with _RecoveryGuard(self.target):
                if _still_this_lock(self.path, getattr(self, "ident", None)):
                    os.remove(self.path)
        except (OSError, Refusal):
            pass
        return False


def _still_this_lock(path, ident):
    """Whether the lock at `path` is still the one identified as (device, inode, its words).

    The inode alone doesn't say: Linux hands a freed inode number to the next new file at once, so
    a lock replaced after we looked can carry the old one's inode (CI on Linux caught it). Its words
    (operation, pid, time) still differ."""
    if not ident:
        return False
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return False
    try:
        st = os.fstat(fd)
        return (st.st_dev, st.st_ino, os.read(fd, 4096)) == ident
    finally:
        os.close(fd)


def load_journal(target):
    """The installer's journal, or None when there is none: when nothing is at its path. Anything else
    there refuses, with nothing changed: a file git tracks, committed or staged (the installer's is
    never committed: .aios/.gitignore ignores it), a link or a folder, one that can't be read, or one
    that isn't a non-empty JSON object (independent review, 3.1 rounds 25 to 27)."""
    path = journal_path(target)
    rel = os.path.relpath(path, target).replace(os.sep, "/")
    # The folders on the way first, before anything there is looked at: through a linked `.aios` the
    # "journal" would be a file from anywhere (independent review, 3.1 round 46).
    if _linked_paths(target, [rel]):
        raise Refusal(EXIT_STATE, "%s is reached through a link, another repository, or a file in a folder's "
                                  "place; nothing was changed" % rel,
                      ["make .aios this repository's own real folder again (restore it from git), then run "
                       "this again"])
    if not os.path.lexists(path):
        return None
    if util.is_tracked(target, rel) or util.in_head(target, rel):
        raise Refusal(EXIT_STATE, "%s is a file this repository tracks, not the installer's journal; nothing "
                                  "was changed" % rel,
                      ["if an interrupted operation left it and it was committed by mistake, untrack it "
                       "(git rm --cached %s), commit, and run this again" % rel])
    if os.path.islink(path) or not os.path.isfile(path):
        raise Refusal(EXIT_STATE, "%s isn't a journal the installer wrote (a link or a folder); nothing was "
                                  "changed" % rel, ["move it aside, then run this again"])
    try:
        journal = util.read_json(path)
    except (OSError, ValueError) as exc:
        raise Refusal(EXIT_STATE, "the journal at %s can't be read (%s); nothing was changed" % (rel, exc),
                      ["move it aside, then run this again"])
    problems = _journal_problems(journal) if isinstance(journal, dict) and journal else ["not a JSON object"]
    if problems:
        raise Refusal(EXIT_STATE, "%s isn't a journal the installer wrote; nothing was changed" % rel,
                      problems[:10] + ["move it aside, then run this again"])
    return journal


# In a folder of its own under the backups folder: like each upgrade's snapshot, the installer's own
# git-ignored record, set apart from everything a person keeps.
STATE_PATH = os.path.join(BACKUP_DIR, "state", "head.json")
# Where every operation writes its temporary copies and its state note: checked with the paths it writes,
# before the first write (independent review, 3.1 round 58).
_INSTALLER_PATHS = [BACKUP_DIR.replace(os.sep, "/") + "/x", STATE_PATH.replace(os.sep, "/")]


def _state_problems(target):
    """Why the state note's folder isn't the installer's own: a link or a file on the way to it or at
    it, or anything in it git tracks (index or HEAD, any spelling). Checked before an operation changes
    anything, and again right before the note is written (independent review, 3.1 round 34)."""
    state_dir = os.path.dirname(STATE_PATH).replace(os.sep, "/")
    out = list(_linked_paths(target, [STATE_PATH.replace(os.sep, "/")]))
    note = os.path.join(target, STATE_PATH)
    if os.path.lexists(note) and (os.path.islink(note) or not os.path.isfile(note)):
        out.append(STATE_PATH.replace(os.sep, "/"))
    if _snapshot_owned(target, state_dir):
        out.append("%s holds files the repository tracks" % state_dir)
    return out


def _require_state_folder(target):
    problems = _state_problems(target)
    if problems:
        raise Refusal(EXIT_STATE, "the installer's state note isn't its own (a link, a file in a folder's place, "
                                  "or something git tracks); nothing was changed",
                      problems[:10] + ["move it aside (and untrack it), then run this again"])


def _write_state(target):
    """Note, locally (the backups folder is git-ignored), which install record the operation that just
    finished wrote: rollback trusts the committed record only while it is still that one, so a record
    a pull request changed, or an older one restored, is refused (independent review, 3.1 round 33)."""
    with open(install_record_path(target), "rb") as fh:
        sha = sha256_bytes(fh.read())
    _require_state_folder(target)
    util.ensure_parent(os.path.join(target, STATE_PATH))
    util.fault("state.after_dir")
    _require_state_folder(target)  # again, right before the write
    util.write_json(os.path.join(target, STATE_PATH), {"schema": "ff-aios-starter/state@1", "record_sha256": sha})


def _check_state(target):
    """Refuse, changing nothing, unless the install record is the one the last finished operation wrote
    (when this workspace has that note: a fresh clone has none, and no snapshots either)."""
    full = os.path.join(target, STATE_PATH)
    rel = STATE_PATH.replace(os.sep, "/")
    record_rel = INSTALL_PATH.replace(os.sep, "/")
    # Neither the note nor the record is read through a link: each, and the folders on the way, are
    # checked first (independent review, 3.1 round 46).
    if os.path.islink(install_record_path(target)) or _linked_paths(target, [record_rel, rel]):
        raise Refusal(EXIT_STATE, "the install record or the installer's note is a link, or is reached through "
                                  "one; nothing was changed", ["restore .aios from git as real files, then run "
                                                               "this again"])
    if not os.path.lexists(full):
        return
    if _repo_owned(target, rel) or os.path.islink(full) or not os.path.isfile(full):
        raise Refusal(EXIT_STATE, "%s isn't the installer's own note (tracked, a link or a folder); nothing "
                                  "was changed" % rel, ["move it aside, then run rollback again"])
    try:
        state = util.read_json(full)
        with open(install_record_path(target), "rb") as fh:
            current = sha256_bytes(fh.read())
    except (OSError, ValueError) as exc:
        raise Refusal(EXIT_STATE, "%s can't be read (%s); nothing was changed" % (rel, exc))
    if not isinstance(state, dict) or state.get("record_sha256") != current:
        raise Refusal(EXIT_STATE, "the install record isn't the one this workspace's last operation wrote: "
                                  "it changed, or an older one was restored; nothing was changed",
                      ["rollback works only from the record the last upgrade, rollback or adoption wrote "
                       "here; find what changed it (git log -- .aios/install.json)"])


def _snapshot_owned(target, backup_rel):
    """Whether git has anything in a snapshot folder (index or HEAD, any spelling): a snapshot is the
    installer's own, never committed, so one with tracked files could be a pull request's (3.1 round 33)."""
    rel = backup_rel.replace(os.sep, "/").rstrip("/")
    staged = util.git(target, ["ls-files", "-z", "--", ":(icase,literal)" + rel], binary=True, check=False)
    return bool(staged.strip(b"\0")) or util.in_head(target, rel)


def _require_trusted_snapshot(target, backup_rel, records, extra=()):
    """Before a rollback or a recovery acts on a snapshot: it is a folder inside the backups folder,
    reached without a link, holding nothing git tracks, and every path the records and the journal
    name is inside the workspace. Refuses, with nothing changed, otherwise (3.1 rounds 32 to 35)."""
    if not (isinstance(backup_rel, str) and util.safe_relpath(backup_rel)
            and backup_rel.replace(os.sep, "/").startswith(BACKUP_DIR.replace(os.sep, "/") + "/")
            and not _linked_paths(target, [backup_rel.replace(os.sep, "/") + "/x"])):
        raise Refusal(EXIT_STATE, "the snapshot isn't a folder inside %s; nothing was changed"
                      % BACKUP_DIR.replace(os.sep, "/"), [str(backup_rel)])
    if _snapshot_owned(target, backup_rel):
        raise Refusal(EXIT_STATE, "the snapshot %s holds files the repository tracks, so it could be a pull "
                                  "request's; nothing was changed" % backup_rel)

    def entries(rec):
        if not isinstance(rec, dict):
            return ["(not a record)"]
        out = []
        for key in ("managed", "created_seeds", "seeded"):
            value = rec.get(key)
            if value is None:  # only a missing or null list is empty (round 35)
                continue
            out += value if isinstance(value, list) else ["(%s isn't a list)" % key]
        return out
    unsafe = sorted(str(e.get("path") if isinstance(e, dict) else e)
                    for r in records for e in entries(r)
                    if not (isinstance(e, dict) and isinstance(e.get("path"), str) and util.safe_relpath(e["path"])))
    unsafe += sorted(str(p) for p in extra if not (isinstance(p, str) and util.safe_relpath(p)))
    if unsafe:
        raise Refusal(EXIT_STATE, "the install records name paths outside the workspace; nothing was changed",
                      unsafe[:20])


def _repo_owned(target, rel):
    """Whether git has `rel` as the repository's file: in the index, or committed in HEAD (a file
    `git rm --cached` left on disk is still the repository's). Cleanup never removes one (3.1 round 28)."""
    rel = rel.replace(os.sep, "/")
    # Inside another repository (a submodule), a file is that repository's, whatever this one's index says.
    if util.inside_another_repository(target, rel):
        return True
    return util.is_tracked(target, rel) or util.in_head(target, rel)


_JOURNAL_OPS = ("upgrade", "rollback", "adopt-existing", "adopt-undo")


def _journal_problems(journal):
    """What makes a journal one the installer didn't write: an operation it doesn't know, or a field an
    operation reads that is missing or of the wrong kind, or a backup outside the backups folder
    (independent review, 3.1 round 28)."""
    op = journal.get("op")
    if op not in _JOURNAL_OPS:
        return ["unknown operation %r" % (op,)]
    out = []
    if "phase" in journal and not isinstance(journal["phase"], str):
        out.append("phase isn't text")
    if op == "upgrade" or (op == "rollback" and journal.get("phase") != "complete"):  # the ones that read it
        backup = journal.get("backup")
        if not (isinstance(backup, str) and util.safe_relpath(backup)
                and backup.replace(os.sep, "/").startswith(BACKUP_DIR.replace(os.sep, "/") + "/")):
            out.append("backup isn't a folder inside %s" % BACKUP_DIR.replace(os.sep, "/"))
    if op == "upgrade":
        for key in ("adds", "seed_adds"):
            if key in journal and not (isinstance(journal[key], list) and all(isinstance(x, str) for x in journal[key])):
                out.append("%s isn't a list of paths" % key)
        for key, kind in (("add_provenance", dict), ("layout", dict)):
            if journal.get(key) is not None and not isinstance(journal[key], kind):
                out.append("%s has the wrong shape" % key)
    if op == "rollback":
        if not isinstance(journal.get("current_record"), dict):
            out.append("current_record is missing")
        if not isinstance(journal.get("created") or [], list):
            out.append("created isn't a list")
    if op == "adopt-existing":
        if not isinstance(journal.get("adoption"), dict):
            out.append("adoption is missing")
        if journal.get("pending") is not None and not isinstance(journal["pending"], dict):
            out.append("pending has the wrong shape")
    if op == "adopt-undo" and journal.get("phase") not in ("undoing", "complete"):
        out.append("phase isn't undoing or complete")
    return out


# ─── verification ───────────────────────────────────────────────────────────

# Windows keeps no executable bit (git there doesn't either), so it is only compared where it exists.
_EXEC_BITS = os.name != "nt"

def verify(target, record=None, source_repo=None):
    """Readback. Returns (problems, summary).

    Two different questions, and it matters which one you asked:

    * without `source_repo`: "does this workspace still match **what was installed**?" The
      answer comes from `.aios/install.json`, which lives in the workspace.
    * with `source_repo`: "...and does that record still match **the pinned release**?" The
      hashes are re-derived from the git tree at the pinned commit.

    The first is circular against a determined local editor: change a managed file, change
    its hash in the record, and the readback agrees with itself. A review found exactly that.
    The record is not a security boundary - it is in the operator's own repo - so the fix is
    to make the stronger check available and to say plainly which one ran.
    """
    record = record or load_record(target)
    problems = []
    checked = 0
    summary_pin = None
    # Every path the record names is checked before anything on disk is read: the record is committed,
    # so a pull request could point it outside the workspace (independent review, 3.1 round 40).
    unsafe = set()
    links = util.gitlinks(target)
    for kind in ("managed", "rendered", "seeded", "seed_lines", "seed_lines_added"):
        for entry in record.get(kind) or []:
            path = entry.get("path") if isinstance(entry, dict) else None
            if not isinstance(path, str) or not util.safe_relpath(path):
                problems.append("the install record names an unsafe path: %r" % (path,))
                unsafe.add(path if isinstance(path, str) else None)
            elif _linked_paths(target, [path], links):
                problems.append("the install record's %s is reached through a link or a file" % path)
                unsafe.add(path)
    lineage = _lineage_problem(target, record)
    if lineage:
        problems.append(lineage[0])
    problems.extend(p for p in _dropped_seed_lines(target, record) if p not in problems)
    if source_repo:
        # With the release source, as an upgrade checks it after this machine's note (independent review,
        # 3.1 round 54).
        # Without the note, so the answer is the same on every machine (independent review, 3.1 round 55).
        problems.extend(p for p in _adopted_ownership_problems(target, record, use_note=False) if p not in problems)
        rel = record.get("release") or {}
        rev = rel.get("git_rev")
        pin_problems, shipped = _pinned_release(record, source_repo)
        problems.extend(pin_problems + _seed_line_problems(record, source_repo))
        if shipped is not None:
            if _EXEC_BITS:
                # The record's own exec field is the operator's to edit, like its hashes; what the
                # release shipped is not (independent review).
                for entry in record.get("managed") or []:
                    path = entry.get("path") if isinstance(entry, dict) else None
                    info = shipped.get(path)
                    if path in unsafe or not info or info[0] != "managed":
                        continue
                    full = os.path.join(target, path)
                    if (os.path.isfile(full) and not os.path.islink(full)
                            and bool(os.lstat(full).st_mode & 0o100) != (info[1] == "100755")):
                        problems.append("executable permission of %s does not match the pinned release" % path)
            # The record's list is the operator's to edit too: drop a file and its entry and the
            # per-entry checks above have nothing to say. What the release shipped is the list
            # (independent review).
            want_managed = {p for p, info in shipped.items() if info[0] == "managed"}
            if "adoption" in record:
                want_managed = _adopted_subset(target, record["adoption"], set(shipped), want_managed, problems)
            listed = {e.get("path") for e in record.get("managed") or [] if isinstance(e, dict)}
            for path in sorted(want_managed - listed):
                problems.append("the pinned release manages %s, but the install record doesn't "
                                "list it" % path)
            if "adoption" in record:
                # Both ways for an adopted instance: a managed file its plan doesn't adopt is one
                # the record shouldn't claim (independent review, 3.1 round 12).
                for path in sorted(p for p in listed - want_managed if isinstance(p, str)):
                    problems.append("the install record lists %s as managed, but the adoption plan "
                                    "doesn't adopt it" % path)
        # And the pin itself: where the source's own record of this release names it.
        if rev and util.rev_exists(source_repo, rev):
            summary_pin = _pin_confirmation(source_repo, rel.get("release_id"), rev, [])
    for entry in record.get("managed") or []:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str) or entry["path"] in unsafe:
            continue  # reported above
        path = os.path.join(target, entry["path"])
        if not os.path.isfile(path):
            problems.append("missing managed file: %s" % entry["path"])
            continue
        st = os.lstat(path)
        if not stat.S_ISREG(st.st_mode):
            problems.append("managed file replaced by a link or something else: %s" % entry["path"])
            continue
        actual = sha256_file(path)
        checked += 1
        if actual != entry.get("sha256"):
            problems.append("modified managed file: %s (on disk %s, release %s)"
                            % (entry["path"], actual[:12], str(entry.get("sha256"))[:12]))
        # Permissions: only what git itself keeps (the executable bit), so a teammate's clone with
        # another umask still verifies; and never setuid, setgid or sticky (independent review).
        if st.st_mode & 0o7000:
            problems.append("managed file gained setuid, setgid or sticky permissions: %s" % entry["path"])
        elif _EXEC_BITS and "exec" in entry and bool(st.st_mode & 0o100) != entry["exec"]:
            problems.append("managed file's executable permission changed: %s" % entry["path"])
    for entry in record.get("rendered") or []:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str) or entry["path"] in unsafe:
            continue
        if not os.path.isfile(os.path.join(target, entry["path"])):
            problems.append("missing rendered file: %s" % entry["path"])
    # Seeds are yours, including the right to delete them: never checked here.
    summary = {
        "release_id": (record.get("release") or {}).get("release_id"),
        "version": (record.get("release") or {}).get("version"),
        "managed_checked": checked,
        "managed_total": len(record.get("managed") or []),
        "pin_confirmed_by": summary_pin,
    }
    return problems, summary


def _adopted_subset(target, info, shipped, managed, problems):
    """Which of the release's managed files an adopted instance must have: as its committed plan
    classifies them, not as the install record's own copy of the plan says. That copy is as editable
    as the record, so a file dropped with its entry, and reclassified there, would otherwise pass
    (independent review, 3.1 round 11)."""
    rel = (info.get("plan") or ADOPTION_PLAN).replace(os.sep, "/")
    try:
        plan, plan_sha = load_adoption_plan(target, rel)
    except Refusal as exc:
        problems.append("cannot read the adoption plan: %s" % exc.message)
        return {p for p in managed if _adoption_class(info, p) == "adopt"}
    # Only as committed: an untracked or locally edited plan could say anything (independent review,
    # 3.1 round 16).
    if not util.is_tracked(target, rel):
        problems.append("the adoption plan %s isn't committed" % rel)
    else:
        committed = util.git(target, ["show", "HEAD:" + rel], binary=True, check=False)
        with open(os.path.join(target, rel), "rb") as fh:
            if fh.read() != committed:
                problems.append("the adoption plan %s has changes that aren't committed" % rel)
    if plan_sha != info.get("plan_sha256"):
        problems.append("the adoption plan %s isn't the one this instance was adopted or last upgraded "
                        "with (upgrade to apply a changed plan)" % rel)
    if any(plan.get(c) != info.get(c) for c in ADOPTION_CLASSES):
        problems.append("the install record's copy of the adoption plan differs from %s" % rel)
    classes, unclassified = classify_adoption(plan, shipped)
    problems.extend("adoption plan: %s" % p for p in unclassified)
    return {p for p in managed if classes.get(p) == "adopt"}


def _source_release(source_repo, release_id):
    """The source's own record of a release, from its tag or else the checked-out tree, or None."""
    found = _source_record(source_repo, release_id)
    return found[1] if found else None


def _source_record(source_repo, release_id):
    """(where, record) for the source's own record of a release: its tag's, or else the checked-out
    tree's; None when it has none. A tag that carries only a draft is skipped: it was placed before the
    approval was recorded (the 2.6.0 shape, which `release check-tag` refuses too), and a clone made
    while such a tag was published keeps it after it's deleted (independent review, 3.1 round 44)."""
    if not release_id or not re.match(r"^starter-[0-9][A-Za-z0-9.+-]*$", str(release_id)):
        return None
    for ref in ("refs/tags/%s" % release_id, "HEAD"):
        text = util.git(source_repo, ["show", "%s:releases/%s.json" % (ref, release_id)], check=False)
        if not text:
            continue
        try:
            record = json.loads(text)
        except ValueError:
            continue
        if not isinstance(record, dict) or (ref != "HEAD" and record.get("status") == "draft"):
            continue
        return ("tag " + release_id if ref != "HEAD" else "HEAD") + ":releases/%s.json" % release_id, record
    return None


def _shipped_by(source_repo, rev, source):
    """What a release shipped, {path: (class, mode, sha256)}: its record's file list in the source, the
    very list its installer was given (each release's own code decided it, so it's never recomputed with
    this one's); a record without one is read from the pinned commit with the release's own package
    spec. Raises Refusal when neither can be read."""
    listed = source.get("files") if isinstance(source, dict) else None
    if isinstance(listed, list) and all(isinstance(f, dict) for f in listed):
        return {f.get("path"): (f.get("class"), f.get("mode"), f.get("sha256")) for f in listed}
    return {p: (c, m, sha) for p, c, m, sha in
            release_mod.select_files(source_repo, rev, release_mod.load_spec(source_repo, rev))}


def _pinned_release(record, source_repo):
    """(problems, shipped): whether the record is exactly a release the source knows, and what that
    release shipped ({path: (class, mode, sha256)}, or None when it can't be read). Its id must be
    starter-<its version>; the source's own record of that release must name the same pin and version;
    every managed entry must be a file that release ships as managed, with its bytes and executable bit.
    A pull request can't change the release source, so a record claiming a file of the instance's, a file
    the release doesn't ship, or another version, fails here. Upgrade and `verify --repo` both use it
    (independent review, 3.1 rounds 38 to 40)."""
    rel = record.get("release") or {}
    rev, release_id, version = rel.get("git_rev"), rel.get("release_id"), rel.get("version")
    if not rev or not util.rev_exists(source_repo, rev):
        return ["cannot cross-check: commit %s is not in %s" % ((rev or "?")[:12], source_repo)], None
    problems = []
    if release_id != "starter-%s" % version:
        problems.append("the record's release %r and version %r disagree" % (release_id, version))
    source = _source_release(source_repo, release_id)
    if not isinstance(source, dict):
        problems.append("%s has no record of %s" % (source_repo, release_id))
    else:
        _pin_confirmation(source_repo, release_id, rev, problems)
        if source.get("version") != version:
            problems.append("the source's record of %s is version %s, not %s"
                            % (release_id, source.get("version"), version))
    try:
        shipped = _shipped_by(source_repo, rev, source)
    except Refusal as exc:
        return problems + ["cannot read what %s ships: %s" % (release_id, exc.message)], None
    for entry in record.get("managed") or []:
        path = entry.get("path") if isinstance(entry, dict) else None
        info = shipped.get(path)
        if not info or info[0] != "managed":
            problems.append("%s isn't a managed file of the pinned release" % (path,))
        elif info[2] != entry.get("sha256"):
            problems.append("install record for %s does not match the pinned release (record %s, release %s)"
                            % (path, str(entry.get("sha256"))[:12], str(info[2])[:12]))
        elif "exec" in entry and bool(entry["exec"]) != (info[1] == "100755"):
            problems.append("executable permission of %s does not match the pinned release" % path)
    if "layout" in record and isinstance(source, dict) and record["layout"] != _installed_layout(record, source_repo):
        problems.append("the install record says folder layout %r, but %s is on layout %s"
                        % (record["layout"], release_id, _installed_layout(record, source_repo)))
    return problems, shipped


def _unlisted_for_upgrade(target, record, shipped):
    """Managed files of the pinned release that the record leaves out. An upgrade works from the record's
    list, so it would neither keep such a file current nor remove it when the new release stops shipping
    it. For an instance installed whole, every one, as `verify --repo` reports them. For an adopted one,
    each its committed plan adopts that is in the workspace: one that isn't is a file a changed plan newly
    adopts, which this upgrade applies (independent review, 3.1 round 48)."""
    want = {p for p, info in shipped.items() if info[0] == "managed"}
    if "adoption" in record:
        plan, _sha = load_adoption_plan(target, record["adoption"].get("plan"))
        classes, _unclassified = classify_adoption(plan, want)
        want = {p for p in want if classes.get(p) == "adopt" and os.path.lexists(os.path.join(target, p))}
    listed = {e.get("path") for e in record.get("managed") or [] if isinstance(e, dict)}
    return ["the pinned release manages %s, but the install record doesn't list it" % p
            for p in sorted(want - listed)]


_SEED_LINE_STATES = ("added", "present", "absent", "link", "missing")


def _seed_line_problems(record, source_repo):
    """Problems with the seed lines a record says releases appended. The record is committed, so a pull
    request could add an entry that names any file and any bytes, which a later rollback would then cut
    from that file. Each entry must be a line a release up to this workspace's own declared, in its
    source record, with exactly the bytes the installer appends; the lines the last upgrade appended
    must be its own release's (independent review, 3.1 round 41). That none was taken out is
    _dropped_seed_lines."""
    version = (record.get("release") or {}).get("version")
    current = util.parse_semver(version or "")
    declared = {}
    problems = []

    def declares(release):
        if release not in declared:
            src = _source_release(source_repo, "starter-%s" % release)
            declared[release] = {(sl.get("path"), sl.get("line")) for sl in (src or {}).get("seed_lines") or []
                                 if isinstance(sl, dict)}
        return declared[release]

    for kind in ("seed_lines", "seed_lines_added"):
        for entry in record.get(kind) or []:
            path, line, release = entry.get("path"), entry.get("line"), entry.get("release")
            at = util.parse_semver(release or "") if isinstance(release, str) else None
            if not current or not at or at > current or (kind == "seed_lines_added" and release != version):
                problems.append("%s: a seed line recorded for release %r, which this workspace hasn't had"
                                % (path, release))
            elif (path, line) not in declares(release):
                problems.append("%s: a seed line release %s never declared" % (path, release))
            elif (kind == "seed_lines" and entry.get("state") not in _SEED_LINE_STATES) or (
                    "appended" in entry and entry["appended"] not in ("\n%s\n" % line, "\n\n%s\n" % line)):
                problems.append("%s: a seed line recorded with bytes or a state the installer never writes" % path)
    return problems


def _pin_confirmation(source_repo, release_id, rev, problems):
    """Where the source records this release's pin (the release's tag, then the checked-out
    tree), or None when it has no record of it. A record naming another pin is a problem: the
    install record's pin was edited, or it is not this release."""
    found = _source_record(source_repo, release_id)
    if not found:
        return None
    where, record = found
    pin = (record.get("created_from") or {}).get("git_rev") if isinstance(record.get("created_from"), dict) else None
    if pin != rev:
        problems.append("the install record pins %s, but %s pins %s" % ((rev or "?")[:12], where, (pin or "?")[:12]))
    return where


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
    # Again right before writing, as private_temp does: the backups must stay inside the workspace
    # (independent review, 3.1 round 22). And the snapshot's own folder is made new, exclusively: one
    # already there (its name is predictable) could hold a link that sends the copies elsewhere
    # (round 23).
    linked = _linked_paths(target, [BACKUP_DIR.replace(os.sep, "/") + "/x"])
    if linked:
        raise Refusal(EXIT_STATE, "the backups would go through a link or a file: %s" % ", ".join(linked))
    os.makedirs(os.path.join(target, BACKUP_DIR), exist_ok=True)
    try:
        os.mkdir(backup_root)
    except FileExistsError:
        raise Refusal(EXIT_STATE, "the backup folder %s already exists; nothing was changed"
                      % os.path.relpath(backup_root, target).replace(os.sep, "/"),
                      ["move it aside, then upgrade again"])
    files_root = os.path.join(backup_root, "files")
    for entry in record.get("managed") or []:
        src = os.path.join(target, entry["path"])
        if not os.path.isfile(src):
            continue
        dst = os.path.join(files_root, entry["path"])
        util.ensure_parent(dst)
        shutil.copy2(src, dst)
    # The record's own bytes, not a re-serialization: rollback puts back exactly these, so a committed
    # record (an adoption's, which its undo compares byte for byte) comes back as it was, on any system
    # (independent review, 3.1 round 44).
    record_full = install_record_path(target)
    if os.path.isfile(record_full) and not os.path.islink(record_full):
        with open(record_full, "rb") as fh:
            util.write_bytes(os.path.join(backup_root, "install.json"), fh.read())
    else:
        util.write_json(os.path.join(backup_root, "install.json"), record)
    return backup_root


def _restore_record(target, backup_rel):
    """Put back the install record exactly as the snapshot keeps it (see _backup)."""
    with open(os.path.join(target, backup_rel, "install.json"), "rb") as fh:
        util.write_bytes(install_record_path(target), fh.read())


def _identical_regular(src, dest):
    """Both regular files (lstat: a link never counts), same bytes, same permission bits."""
    try:
        a, b = os.lstat(src), os.lstat(dest)
    except OSError:
        return False
    return (stat.S_ISREG(a.st_mode) and stat.S_ISREG(b.st_mode)
            and stat.S_IMODE(a.st_mode) == stat.S_IMODE(b.st_mode)
            and sha256_file(src) == sha256_file(dest))


def _restore_preflight(target, backup_root, record_to_restore, remove_paths, expected=None):
    """Every refusal a restore can make, made before anything changes. Rollback runs it before
    writing its own journal, so a refusal leaves the workspace exactly as it was."""
    # Every path this restore writes OR removes: removing through a link would delete a file
    # outside the workspace (independent review, round 4).
    linked = _linked_paths(target, [e["path"] for e in record_to_restore.get("managed") or []]
                           + list(remove_paths))
    if linked:
        raise Refusal(EXIT_STATE, "restoring would go through %d link(s) or file(s) in the way"
                      % len(linked), linked[:20] + ["replace them with real folders, then run rollback again"])
    folders = [e["path"] for e in record_to_restore.get("managed") or []
               if os.path.isdir(os.path.join(target, e["path"]))
               and not os.path.islink(os.path.join(target, e["path"]))]
    if folders:  # copying onto a folder would put the file inside it
        raise Refusal(EXIT_STATE, "restoring would put %d file(s) where a folder now is" % len(folders),
                      folders[:20] + ["move those folders aside, then run rollback again"])
    if expected is not None:
        files_root = os.path.join(backup_root, "files")
        collisions = []
        for entry in record_to_restore.get("managed") or []:
            rel = entry["path"]
            dest = os.path.join(target, rel)
            if rel in expected or not os.path.lexists(dest):
                continue
            src = os.path.join(files_root, rel)
            if _identical_regular(src, dest):
                continue  # identical; restoring it changes nothing (and it isn't touched)
            collisions.append(rel)
        if collisions:
            raise Refusal(
                EXIT_STATE,
                "restoring would overwrite %d file(s) this workspace does not manage"
                % len(collisions),
                sorted(collisions)[:20]
                + ["these paths were freed by a later release and now hold your own work",
                   "move them aside, then run rollback again"],
            )


def _restore(target, backup_root, record_to_restore, remove_paths, expected=None,
             write_record=True, keep_dirs=None, provenance=None):
    """Put the backed-up managed files back.

    `write_record=False` leaves the install record to the caller, which writes it last, once every
    other reversal is done: a kill in between must leave the record still describing what's on
    disk. `keep_dirs`: folders that existed before the operation, never pruned. `provenance`
    ({path: [sha256, mode]}): files removed only if they're still exactly what was written.
    Returns notes about anything left alone.

    `expected` is the set of paths this restore is allowed to overwrite: what the current
    release manages, plus anything the interrupted operation created. Anything else at a
    restore path is the operator's, created after the release stopped owning that path, and
    overwriting it silently is state loss - so it is refused instead.
    """
    _restore_preflight(target, backup_root, record_to_restore, remove_paths, expected)
    notes = []
    provenance = provenance or {}
    for rel in remove_paths:
        if rel in provenance:
            sha, mode = provenance[rel]
            note = _remove_if_ours(target, rel, sha, mode)
            if note:
                notes.append(note)
            continue
        path = os.path.join(target, rel)
        if os.path.islink(path) or os.path.isfile(path):
            os.remove(path)
    files_root = os.path.join(backup_root, "files")
    for entry in record_to_restore.get("managed") or []:
        src = os.path.join(files_root, entry["path"])
        dst = os.path.join(target, entry["path"])
        if os.path.isfile(src):
            if expected is not None and entry["path"] not in expected and _identical_regular(src, dst):
                continue  # not ours now, and already exactly the release's copy: leave it be
            util.ensure_parent(dst)
            if os.path.islink(dst):
                os.remove(dst)  # copying onto a link would write wherever it points
            shutil.copy2(src, dst)
    if write_record:
        snapshot = os.path.join(backup_root, "install.json")
        if os.path.isfile(snapshot) and not os.path.islink(snapshot):
            with open(snapshot, "rb") as fh:  # its own bytes (3.1 round 45)
                util.write_bytes(install_record_path(target), fh.read())
        else:
            util.write_json(install_record_path(target), record_to_restore)
    _prune_parents(target, remove_paths, keep_dirs)
    return notes


def _refuse_other_repositories(target, rels, what):
    """Refuse, with nothing changed, when any of `rels` (or the installer's own folders) lies inside another
    repository: a submodule, initialized or not, or a repository inside this one. Every resumed operation runs
    this before its first write, since one could appear while the operation was interrupted (independent
    review, 3.1 round 59). Links keep each step's own rule."""
    links = util.gitlinks(target)
    rels = [r.replace(os.sep, "/") for r in rels if isinstance(r, str) and r] + _INSTALLER_PATHS
    inside = sorted({util.inside_another_repository(target, r, links) for r in rels} - {None})
    if inside:
        raise Refusal(EXIT_STATE, "%s would write or remove files inside another repository (a submodule); "
                      "nothing was changed" % what,
                      inside[:20] + ["make each a plain folder of this repository again, then run rollback again"])


def _own_paths(target):
    """The install record and the org config, relative to the workspace."""
    return [os.path.relpath(install_record_path(target), target), os.path.relpath(
        orgconfig.default_config_path(target), target)]


def _plan_paths(the_plan, backup_rel=None):
    """Every path a folder move touches: each file it moves, at both ends; each it sets aside (where it was,
    and, given the backup, where it goes); and each folder it empties."""
    out = [m["from"] for m in the_plan["moves"]] + [m["to"] for m in the_plan["moves"]]
    out += [q["from"] for q in the_plan["quarantine"]]
    if backup_rel:
        out += [layout_mod.quarantine_path(backup_rel, q["from"]) for q in the_plan["quarantine"]]
    return out + [e[end] + "/x" for e in the_plan["empty_dirs"] for end in ("from", "to")]


def _linked_paths(target, rels, links=None):
    """Paths rollback would write whose way there runs through a link or a file (a client folder
    turned into a link after the upgrade would send the restored file outside the workspace), or
    through a folder that is another repository (a submodule: files in it are that repository's,
    which this one's tracking checks can't see; independent review, 3.1 round 47).
    Checked before anything changes (independent review)."""
    out = []
    if links is None:
        links = util.gitlinks(target) if rels else set()
    for rel in rels:
        parts = rel.replace(os.sep, "/").split("/")
        for i in range(1, len(parts)):
            full = os.path.join(target, *parts[:i])
            if os.path.islink(full) or (os.path.lexists(full) and not os.path.isdir(full)) \
                    or _another_repository(target, "/".join(parts[:i]), links):
                out.append("/".join(parts[:i]))
                break
    return sorted(set(out))


def _another_repository(target, rel_folder, links=None):
    """Whether the workspace folder `rel_folder` is another repository: it holds a `.git` (an initialized
    submodule, or a repository inside this one), or this repository records it as a submodule (a gitlink,
    in the index or in HEAD), initialized or not. Any folder, not only the installer's own: a file made
    under an uninitialized submodule could never be committed here (independent review, 3.1 round 57)."""
    return util.another_repository(target, rel_folder, links)


def _remove_if_ours(target, rel, sha=None, mode=None):
    """Remove a file this operation wrote, and only if it still is what it wrote: a regular file
    (not a link) with the recorded bytes and mode. Anything else is left alone and reported: it
    may be the client's (independent review). Returns a note, or None."""
    full = os.path.join(target, rel)
    if not os.path.lexists(full):
        return None
    if os.path.islink(full) or not os.path.isfile(full):
        return "%s isn't the file the upgrade wrote (a link or a folder now), so it was left" % rel
    if sha and sha256_file(full) != sha:
        return "%s changed since the upgrade wrote it, so it was left for you" % rel
    if mode is not None and stat.S_IMODE(os.lstat(full).st_mode) != mode:
        return "%s changed permissions since the upgrade wrote it, so it was left for you" % rel
    os.remove(full)
    return None


def _prune_parents(target, paths, keep=None):
    """Remove the folders that removing `paths` left empty, deepest first.

    Only those, and never one in `keep` (folders that existed before the operation, even if
    empty: a client's own empty folder). Until 3.0 this walked the whole workspace and removed
    every empty folder in it, so a rollback could not restore them.
    """
    keep = set(keep or ())
    dirs = set()
    for rel in paths:
        parts = rel.replace(os.sep, "/").split("/")[:-1]
        dirs.update("/".join(parts[:i]) for i in range(1, len(parts) + 1))
    for d in sorted(dirs, key=lambda p: -p.count("/")):
        if d.split("/")[0] == ".git" or d in keep:
            continue
        full = os.path.join(target, d)
        try:
            if os.path.isdir(full) and not os.path.islink(full) and not os.listdir(full):
                os.rmdir(full)
        except OSError:
            pass


# ─── install ────────────────────────────────────────────────────────────────

def install(target, manifest, source_repo, config, aios_lookup=None, render_governance=True):
    """Install an approved, pinned release into a clean target. Verified by readback."""
    release_mod.require_consumable(manifest, source_repo, aios_lookup)
    orgconfig.require_valid(config)

    if os.path.lexists(install_record_path(target)):
        raise Refusal(EXIT_STATE, "this workspace already has an install record; use upgrade",
                      [install_record_path(target)])
    if load_journal(target):
        raise Refusal(EXIT_STATE, "a previous operation did not finish; run rollback first",
                      [journal_path(target)])

    files = {e["path"]: e for e in manifest.get("files") or []}
    managed_paths = [p for p, e in files.items() if e["class"] == "managed"]
    occupied = [p for p in managed_paths if os.path.lexists(os.path.join(target, p))]
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
    # Everything that can refuse happens before the first write: rendering CODEOWNERS can refuse an
    # incomplete owners map, and must not leave a half-installed target (independent review).
    template_path = manifest.get("render_template") or "templates/governance/CODEOWNERS.template"
    owners_text = None
    if render_governance and (config.get("code_owners") or {}):
        for path, _mode, data in util.read_tree(source_repo, manifest["created_from"]["git_rev"]):
            if path == template_path and path in files:
                owners_text = governance.render(data.decode("utf-8"), config["repository"],
                                                config["code_owners"])
                break
    if owners_text is not None:
        # What GitHub would ignore must not install "successfully" (independent review).
        problems = governance.check_text(owners_text, ".github/CODEOWNERS", target,
                                         config["repository"], config)
        if problems:
            raise Refusal(EXIT_GOVERNANCE, "the rendered CODEOWNERS would not enforce anything",
                          problems)
        # The client's own CODEOWNERS is theirs: replacing it, or shadowing it from a location
        # GitHub reads first, would change who reviews what without a word.
        theirs = [rel for rel in governance.LOCATIONS if os.path.lexists(os.path.join(target, rel))]
        if theirs:
            raise Refusal(EXIT_STATE, "this workspace already has a CODEOWNERS file",
                          theirs + ["move it aside and install again, or install without "
                                    "code_owners in the config and keep yours"])
    config_path = orgconfig.default_config_path(target)
    if os.path.lexists(config_path):
        same = False
        if os.path.isfile(config_path) and not os.path.islink(config_path):
            try:
                same = util.read_json(config_path) == config
            except (ValueError, OSError, Refusal):
                same = False
        if not same:
            raise Refusal(EXIT_STATE, "this workspace already has a different organization config",
                          [config_path, "install with --config pointing at it, or move it aside"])
    written = [p for p, e in files.items() if e["class"] == "managed"
               or not os.path.lexists(os.path.join(target, p))]
    written += [".github/CODEOWNERS"] if owners_text is not None else []
    written += [os.path.relpath(config_path, target), os.path.relpath(install_record_path(target), target)]
    # And the installer's own folders, where its temporary copies and its state note go (3.1 round 58).
    linked = _linked_paths(target, written + _INSTALLER_PATHS)
    if linked:
        raise Refusal(EXIT_STATE, "install would write through a link, a file in a folder's place, or another "
                      "repository (a submodule)", linked[:20])
    for path, mode, data in util.read_tree(source_repo,
                                           manifest["created_from"]["git_rev"]):
        entry = files.get(path)
        if entry is None:
            continue
        if entry["sha256"] != sha256_bytes(data):
            raise Refusal(EXIT_PACKAGE, "content at the pin does not match the manifest: %s" % path)
        if path == template_path:
            template_text = data.decode("utf-8")
        dest = os.path.join(target, path)
        if entry["class"] == "seed" and os.path.lexists(dest):
            # Yours already; never overwritten. Recorded as a seed, as an upgrade records one, so
            # the next upgrade knows it's yours rather than refusing it as a collision.
            seeded.append({"path": path, "sha256": sha256_file(dest)
                           if os.path.isfile(dest) and not os.path.islink(dest) else ""})
            continue
        sha = util.write_file(target, path, data, entry.get("mode", "100644"))
        rec = {"path": path, "sha256": sha}
        if entry["class"] == "managed":
            rec["exec"] = entry.get("mode") == "100755"
        (managed if entry["class"] == "managed" else seeded).append(rec)

    if render_governance and template_text and owners_text is not None:
        sha = util.write_file(target, os.path.join(".github", "CODEOWNERS"),
                              owners_text.encode("utf-8"), "100644")
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
    if manifest.get("layout"):
        record["layout"] = layout_mod.version_of(manifest["layout"])
    if manifest.get("seed_lines"):
        # A fresh install seeds the file from the release, which the build proved carries the line.
        _kept, missing, settled = _seed_line_plan(target, {}, manifest)
        record["seed_lines"] = settled + [{k: v for k, v in e.items() if k != "appended"}
                                          for e in (dict(m, state="missing") for m in missing)]
    util.write_json(install_record_path(target), record)

    require_verified(target, record, "freshly installed workspace")
    return record, creds


# ─── upgrade ────────────────────────────────────────────────────────────────

def upgrade(target, manifest, source_repo, aios_lookup=None, no_vercel=False):
    """Replace managed files with a newer approved release. State is never touched.

    `no_vercel`: the founder's statement that this repository isn't deployed by Vercel, for a
    layout move made without a Vercel token (R-A). Recorded with the upgrade.
    """
    with _Lock(target, "upgrade"):
        return _upgrade_locked(target, manifest, source_repo, aios_lookup, no_vercel)


DRIFT_DIFF_LINES = 40


def _installed_layout(record, source_repo):
    """The folder layout this workspace is on: its pinned release's, from the release source's own record
    of that release, never the install record's `layout` field, which a pull request can edit and which a
    2.x-style `adopt` of a 3.0 copy never wrote (independent review, 3.1 round 49). A release without a
    layout is on 2.x's."""
    source = _source_release(source_repo, (record.get("release") or {}).get("release_id"))
    layout = source.get("layout") if isinstance(source, dict) else None
    return layout_mod.version_of(layout) if isinstance(layout, dict) else "2"


def _layout_preflight(target, record, manifest, files, old_managed, no_vercel=False, installed="2"):
    """The folder move this upgrade makes, if its release changes the layout: (plan, site rows,
    blocking problems). A plan that can't run safely refuses here, with nothing changed.

    Website folders are checked against Vercel before anything moves (founder requirement R-A):
    any problem in the third value blocks the upgrade.
    """
    new_layout = manifest.get("layout") or {}
    if not new_layout.get("moves") or layout_mod.version_of(new_layout) == installed:
        return None, [], []
    the_plan = layout_mod.plan(target, new_layout, set(old_managed),
                               {p: e["class"] for p, e in files.items()})
    found = layout_mod.sites(target, the_plan, new_layout)
    the_plan["sites"] = found
    slug = governance.target_repo_slug(target)
    rows, blocked = hosting.check(found, new_layout, slug, no_vercel=no_vercel,
                                  vercel_files=layout_mod.vercel_files(the_plan))
    return the_plan, rows, blocked


def founder_review_notice(target, retired_roots):
    """Lines telling the client to restore founder review at the new paths (R-C), or [] when
    CODEOWNERS names none of the retired folders."""
    rel, path = governance.find_file(target)
    roots = set(retired_roots)
    stale = []
    if path:
        with open(path, encoding="utf-8", errors="replace") as fh:
            stale = [pat for _n, pat, _o in governance.parse(fh.read())
                     if pat.lstrip("/").split("/", 1)[0] in roots]
    if path and not stale:
        return []
    return ["founder review: %s %s. GitHub stops asking a founder about the founder lane until "
            "it's restored at the new paths (card docs/human_steps/restore_founder_review.md); "
            "`aios instance check` fails until it's restored and enforced"
            % (rel or "CODEOWNERS", ("still guards %s" % ", ".join(stale)) if stale else "is missing")]


def ownership_review_notice(target, record):
    """A line telling the client the ownership list isn't held to founder review here yet (3.1, owner decision
    C3): the role policy leaves it open, or no CODEOWNERS rule sends it to founder-lane reviewers (no CODEOWNERS
    file at all included). [] when both hold it, or when there's no policy or people map to judge by. Reads only."""
    try:
        policy, config = roles.load_policy(target), orgconfig.load(target)
    except (Refusal, ValueError):
        return []
    paths = ownership_paths(record)
    # And the ownership paths the policy keeps in the founder lane though the record doesn't name them: a plain
    # install's policy holds the default plan path too, and `instance check` wants a founder rule for it
    # (independent review, 3.1 round 67).
    lane = governance.founder_lane_paths(policy)
    also = [rel for rel in (INSTALL_PATH.replace(os.sep, "/"), ADOPTION_PLAN.replace(os.sep, "/"))
            if rel not in paths and util.lane_match(lane, rel)]
    if governance.ownership_held(target, policy, config, paths, also):
        return []
    paths = paths + also
    return ["founder review: the ownership list (%s) says which files are the installer's own, and it isn't held "
            "to founder review here yet. Add each to the founder lane and give it a CODEOWNERS rule (card "
            "docs/human_steps/restore_founder_review.md, \"After upgrading to 3.1\"); `aios instance check` fails "
            "until it's done" % ", ".join(paths)]


def _founder_review_after_move(target, record, manifest, installed="2"):
    new_layout = manifest.get("layout") or {}
    if not new_layout.get("moves") or layout_mod.version_of(new_layout) == installed:
        return []
    return founder_review_notice(target, new_layout.get("retired_roots") or [])


def upgrade_plan(target, manifest, source_repo, aios_lookup=None, no_vercel=False):
    """What `upgrade` would do, writing nothing: the same refusals, then the managed-file changes."""
    record, _version, _min_from, _creds, files, old_managed, old_seeded, manifest = _upgrade_preflight(
        target, manifest, source_repo, aios_lookup)
    managed = {p: e for p, e in files.items() if e["class"] == "managed"}
    installed = _installed_layout(record, source_repo)
    the_plan, site_rows, blocked = _layout_preflight(target, record, manifest, files, old_managed,
                                                     no_vercel, installed)
    move_keys = layout_mod.destinations(the_plan)
    seed_keys = _seed_keys(record, manifest, source_repo, target)
    return {
        "layout": None if not the_plan else {
            "from": the_plan["from"], "to": the_plan["to"],
            "moves": [(m["from"], m["to"]) for m in the_plan["moves"]],
            "set_aside": [q["from"] for q in the_plan["quarantine"]],
            "empty_folders": [(e["from"], e["to"]) for e in the_plan["empty_dirs"]],
            "sites": site_rows,
            "blocked": blocked,
            "founder_review": _founder_review_after_move(target, record, manifest, installed),
        },
        "from": (record.get("release") or {}).get("version"),
        "to": manifest["version"],
        "changed": sorted(p for p, e in managed.items()
                          if p in old_managed and old_managed[p].get("sha256") != e["sha256"]),
        "added": sorted(p for p in managed if p not in old_managed),
        "removed": _to_drop(old_managed, files, manifest),
        "unchanged": sum(1 for p, e in managed.items()
                         if p in old_managed and old_managed[p].get("sha256") == e["sha256"]),
        "new_seeds": sorted(p for p, e in files.items() if e["class"] == "seed"
                            and layout_mod.key(p) not in seed_keys and layout_mod.key(p) not in move_keys
                            and not os.path.lexists(os.path.join(target, p))),
        "seed_lines": [{"path": e["path"], "line": e["line"]}
                       for e in _seed_line_plan(target, record, manifest, _moved_from(the_plan),
                                                _handled_seed_lines(target, record, source_repo))[1]],
    }


def drift_recipe(target, record, source_repo, problems):
    """For each managed file edited by hand: what changed, and the two ways forward.

    A bare "modified managed file" refusal was a dead end (Chat Zero's 2.7.0 -> 2.7.1 upgrade test).
    """
    prefix = "modified managed file: "
    drifted = [p[len(prefix):].split(" (on disk", 1)[0] for p in problems if p.startswith(prefix)]
    if not drifted:
        return []
    release = record.get("release") or {}
    rev = release.get("git_rev") or ""
    pinned = {}
    if rev and util.rev_exists(source_repo, rev):
        pinned = {path: data for path, _mode, data in util.read_tree(source_repo, rev) if path in drifted}
    out = []
    for path in drifted:
        out.append("%s was edited after install. What changed (the installed %s, then yours):"
                   % (path, release.get("version")))
        if path in pinned:
            with open(os.path.join(target, path), "rb") as fh:
                mine = fh.read()
            diff = list(difflib.unified_diff(pinned[path].decode("utf-8", "replace").splitlines(),
                                             mine.decode("utf-8", "replace").splitlines(),
                                             "release/%s" % path, "workspace/%s" % path, lineterm=""))
            out += ["    %s" % line for line in diff[:DRIFT_DIFF_LINES]]
            if len(diff) > DRIFT_DIFF_LINES:
                out.append("    ... %d more lines: git -C %s log -p -- %s"
                           % (len(diff) - DRIFT_DIFF_LINES, target, path))
            out.append("to revert it: git -C %s show %s:%s > %s, then commit"
                       % (source_repo, rev[:12], path, os.path.join(target, path)))
        else:
            out.append("    (the installed release isn't in %s; see your edit with: git -C %s log -p -- %s)"
                       % (source_repo, target, path))
            out.append("to revert it: put back the installed release's copy of %s, then commit" % path)
        out.append("to keep it: move your change into a file the release doesn't manage (your own file, "
                   "or a seed file such as CLAUDE.md), revert this one, commit, and upgrade again")
        if path == ".claude/settings.json":
            out.append("for this file specifically: put your own permission rules or settings in "
                       ".claude/settings.local.json. Claude Code merges it over this one, and no upgrade, "
                       "rollback or verify ever touches it (docs/INSTALL_AND_UPGRADE.md, \"Your own settings\")")
    return out


def _seed_line_target(target, rel):
    """The seed file a declared line goes into, or None when it is a link or leaves the workspace.

    Following a link would append to wherever it points (independent review).
    """
    full = os.path.join(target, rel)
    if os.path.islink(full) or not os.path.isfile(full):
        return None
    # Nor inside another repository (a submodule): the line would go into that repository's file
    # (independent review, 3.1 round 58).
    if util.inside_another_repository(target, rel):
        return None
    real_root, real = os.path.realpath(target), os.path.realpath(full)
    return full if real.startswith(real_root + os.sep) else None


def _seed_line_plan(target, record, manifest, moved_from=None, handled=()):
    """The declared seed lines this release adds, and the state of the ones it doesn't.

    A seed line is added once: never twice, never to a seed file the client deleted, never into a
    link, and never again after the client removed it. Returns (carried, add, settled): entries
    already recorded, entries this upgrade appends (with the exact bytes, so an undo removes only
    those), and new entries that need no write. Bytes throughout: the client's file may hold bytes
    that aren't UTF-8, and they must survive untouched.

    `moved_from` ({new path: old path}): a file the 3.0 move relocates is read where it is now,
    before the move; the line goes into it at its new path, after the move (independent review).

    `handled` ({(path, line)}): lines a release this workspace already had declared, which were due,
    and so handled, when it got that release, whatever the record lists (_handled_seed_lines).
    """
    moved_from = moved_from or {}
    recorded = list(record.get("seed_lines") or [])
    done = {(e["path"], e["line"]) for e in recorded} | set(handled)
    add, settled = [], []
    pending = {}  # path -> bytes as they will be once the earlier lines in this upgrade are added
    for sl in manifest.get("seed_lines") or []:
        if (sl["path"], sl["line"]) in done:
            continue
        entry = {"path": sl["path"], "line": sl["line"], "release": manifest["version"]}
        here = moved_from.get(sl["path"], sl["path"])
        full = os.path.join(target, here)
        if os.path.islink(full):
            settled.append(dict(entry, state="link"))  # never written through; reported instead
            continue
        if not os.path.isfile(full):
            settled.append(dict(entry, state="absent"))  # deleted by the client: theirs to keep deleted
            continue
        if _seed_line_target(target, here) is None:
            settled.append(dict(entry, state="link"))
            continue
        if sl["path"] not in pending:
            with open(full, "rb") as fh:
                pending[sl["path"]] = fh.read()
        data = pending[sl["path"]]
        line = sl["line"].encode("utf-8")
        if any(l.strip() == line for l in data.splitlines()):
            settled.append(dict(entry, state="present"))
            continue
        sep = b"" if data == b"" or data.endswith(b"\n") else b"\n"
        appended = sep + b"\n" + line + b"\n"
        pending[sl["path"]] = data + appended
        add.append(dict(entry, state="added", appended=appended.decode("utf-8")))
    return recorded, add, settled


def _replace_bytes(target, full, data):
    """Write a client file all at once: the old bytes or the new, never half of each. The
    temporary copy lives in the git-ignored backups folder, so a kill can't leave a stray file
    beside the client's own."""
    mode = stat.S_IMODE(os.lstat(full).st_mode)
    tmp = util.private_temp(target)
    try:
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, full)
    finally:
        if os.path.lexists(tmp):
            os.remove(tmp)


def _apply_seed_lines(target, adds):
    for e in adds:
        full = _seed_line_target(target, e["path"])
        if full is None:
            continue
        with open(full, "rb") as fh:
            data = fh.read()
        _replace_bytes(target, full, data + e["appended"].encode("utf-8"))


def _undo_seed_lines(target, adds):
    """Take back exactly what an upgrade appended, byte for byte. Safe to call again.

    Newest first: two lines appended by one upgrade (2.6.0 to 3.0 adds the core import and the
    folder-map line) only come off byte for byte in the reverse of the order they went on. Only
    the exact bytes recorded are removed: at the end of the file, or, if the client wrote after
    them, where they occur once. Anything less certain is left for the client and reported, never
    guessed (independent review). Returns notes for the person.
    """
    notes = []
    for e in reversed(list(adds)):
        full = _seed_line_target(target, e["path"])
        tail = (e.get("appended") or "").encode("utf-8")
        if full is None or not tail:
            continue
        with open(full, "rb") as fh:
            data = fh.read()
        if data.endswith(tail):
            _replace_bytes(target, full, data[:-len(tail)])
        elif data.count(tail) == 1:
            i = data.index(tail)
            _replace_bytes(target, full, data[:i] + data[i + len(tail):])
        elif e["line"].encode("utf-8") in data:
            notes.append("%s still has `%s`: it was edited around that line, so rollback left it for "
                         "you to remove" % (e["path"], e["line"]))
    return notes


def _moved_from(the_plan):
    return {m["to"]: m["from"] for m in (the_plan or {}).get("moves") or []}


_PINNED_SEEDS = {}


def _installed_release_seeds(record, source_repo):
    """Every seed of the installed release, from its pinned tree. A record written by a 2.x
    installer can leave some out (one the client already had at install, one absent at adopt),
    and those are the client's all the same (independent review). Empty when the source doesn't
    have the pin."""
    rev = (record.get("release") or {}).get("git_rev")
    if not source_repo or not rev or not util.FULL_SHA1_RE.match(rev):
        return set()
    cache_key = (os.path.abspath(source_repo), rev)
    if cache_key not in _PINNED_SEEDS:
        seeds = set()
        if util.rev_exists(source_repo, rev):
            try:
                seeds = {p for p, c, _m, _s in release_mod.select_files(
                    source_repo, rev, release_mod.load_spec(source_repo, rev)) if c == "seed"}
            except Refusal:
                seeds = set()
        _PINNED_SEEDS[cache_key] = seeds
    return _PINNED_SEEDS[cache_key]


def _lifetime_records(target, record):
    """The install record as each commit of its current lifetime committed it, on every side of every
    merge, for a release at or below this workspace's own: [(commit, record)], oldest lifetime commit
    first. Git history, which a pull request can only add to. A newer release's record is left out: a
    rollback, or a merge that set the record back, leaves that release's lines and seeds to be had again.
    [] while the record isn't committed. Refuses in a shallow clone (_latest_added)."""
    if not target:
        return []
    record_rel = os.path.relpath(install_record_path(target), target).replace(os.sep, "/")
    if not util.in_head(target, record_rel):
        return []
    anchor = _latest_added(target, record_rel)
    if not anchor:
        return []
    current = util.parse_semver((record.get("release") or {}).get("version") or "")
    commits = [anchor] + util.git(target, ["log", "--full-history", "--reverse", "--format=%H", "%s..HEAD" % anchor,
                                           "--", ":(literal)" + record_rel], check=False).split()
    found = []
    for commit in commits:
        raw = util.git(target, ["show", "%s:%s" % (commit, record_rel)], binary=True, check=False)
        try:
            then = json.loads(raw.decode("utf-8"))
        except ValueError:
            continue
        rel = then.get("release") if isinstance(then, dict) else None
        version = rel.get("version") if isinstance(rel, dict) else None
        at = util.parse_semver(version) if isinstance(version, str) else None
        if at and current and at <= current:
            found.append((commit, then))
    return found


def _release_seeds(source_repo, release_id):
    """The seeds a release shipped, as the release source's own record of it says; empty when the source
    has no record of it."""
    source = _source_release(source_repo, release_id) if source_repo else None
    pin = (source.get("created_from") or {}).get("git_rev") if isinstance(source, dict) and isinstance(
        source.get("created_from"), dict) else None
    if not pin or not util.rev_exists(source_repo, pin):
        return set()
    try:
        return {p for p, info in _shipped_by(source_repo, pin, source).items() if info[0] == "seed"}
    except Refusal:
        return set()


def _handled_seed_lines(target, record, source_repo):
    """(path, line) of every seed line a release this workspace has had declared: its pinned release, and
    each release at or below it that its committed record named in its current lifetime. Each line was
    due when the workspace got that release, so it was handled then (appended, found, or left out where
    the seed was gone), whatever the record lists now: a 2.x-style `adopt` of a 3.0 copy records none,
    and a pull request can take entries out. Read from the release source and git history (independent
    review, 3.1 round 49)."""
    if not source_repo:
        return set()
    releases = {(record.get("release") or {}).get("release_id")}
    releases |= {(then.get("release") or {}).get("release_id") for _c, then in _lifetime_records(target, record)}
    handled = set()
    for release_id in releases:
        source = _source_release(source_repo, release_id) if isinstance(release_id, str) else None
        handled |= {(sl.get("path"), sl.get("line")) for sl in (source or {}).get("seed_lines") or []
                    if isinstance(sl, dict)}
    return handled


def _seed_history(record, manifest, source_repo=None, target=None):
    """Every path a release has seeded into this workspace, under its old and its new name. Not only what
    the record says: also every seed a release it has had shipped, and every seed path its committed
    record listed, in its current lifetime, from the release source and git history, which a pull request
    can't take back (independent review, 3.1 round 49)."""
    paths = ({e["path"] for e in record.get("seeded") or []} | set(record.get("seed_history") or [])
             | _installed_release_seeds(record, source_repo))
    for _commit, then in _lifetime_records(target, record):
        paths |= {e.get("path") for e in then.get("seeded") or [] if isinstance(e, dict)
                  and isinstance(e.get("path"), str)}
        paths |= {p for p in then.get("seed_history") or [] if isinstance(p, str)}
        paths |= _release_seeds(source_repo, (then.get("release") or {}).get("release_id"))
    rules = (manifest.get("layout") or {}).get("moves") or []
    if rules:
        paths |= {layout_mod.destination(p, rules) or p for p in paths}
    return paths


def _seed_keys(record, manifest, source_repo=None, target=None):
    """Every name a release has seeded into this workspace, as a Mac or Windows disk compares names.
    A seed the client deleted, under its old name or its new one, in this release or an earlier one,
    must not come back (independent review)."""
    return {layout_mod.key(p) for p in _seed_history(record, manifest, source_repo, target)}


def _upgrade_preflight(target, manifest, source_repo, aios_lookup=None):
    """Every check an upgrade makes before it writes anything. The dry run makes the same ones."""
    record = load_record(target)
    if load_journal(target):
        raise Refusal(EXIT_STATE, "a previous operation did not finish; run rollback first",
                      [journal_path(target)])
    _require_state_folder(target)  # the note it writes at the end must be the installer's own (3.1 round 34)

    release_mod.require_consumable(manifest, source_repo, aios_lookup)
    manifest = dict(manifest)
    manifest.pop("_adoption", None)  # only ever set below, in this process, never read from a file
    # Adopted or not is read from git history, never only from the committed record a pull request can
    # edit: an adopted record that lost its adoption would get the plain upgrade, and a plain one that
    # gained one would get an adopted plan's upgrade (independent review, 3.1 round 39).
    lineage = _lineage_problem(target, record)
    if lineage:
        raise Refusal(EXIT_STATE, lineage[0] + "; nothing was changed", lineage[1])
    dropped = _dropped_seed_lines(target, record)
    if dropped:
        raise Refusal(EXIT_STATE, "the install record no longer lists seed lines its history recorded, so an "
                                  "upgrade could append a line you removed; nothing was changed",
                      dropped[:20] + ["restore the record from git, then upgrade"])
    if "adoption" in record:
        manifest = _adopted_upgrade_view(target, record, manifest)

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

    # Dirty or partial state is refused, never silently overwritten. An edited managed file comes
    # with its diff and the two ways forward.
    problems, _summary = verify(target, record)
    if problems:
        raise Refusal(EXIT_VERIFY, "workspace does not match its installed release",
                      problems + drift_recipe(target, record, source_repo, problems))
    # The record is committed, so anyone's pull request could change which files it calls managed. An
    # upgrade trusts it only while it is the one the last operation here wrote (when this workspace has
    # that note), and an adopted instance's record must also match the release it's pinned to, checked
    # against the release source, which a pull request can't change (independent review, 3.1 round 38).
    _check_state(target)
    # Every workspace, not only one whose record says it's adopted: a pull request could drop that key
    # (independent review, 3.1 round 39). An untouched record always passes: its managed files are its
    # pinned release's own.
    # And the list itself, not only each entry on it: an entry taken out would leave its file behind
    # (independent review, 3.1 round 48).
    pinned_problems, shipped = _pinned_release(record, source_repo)
    if shipped is not None:
        pinned_problems += _unlisted_for_upgrade(target, record, shipped)
    pinned_problems += _seed_line_problems(record, source_repo)
    pinned_problems += _adopted_ownership_problems(target, record)
    if pinned_problems:
        raise Refusal(EXIT_VERIFY, "this workspace's install record doesn't match the release it's pinned to; "
                                   "nothing was changed", pinned_problems[:20])
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

    # A path that was ever the client's seed can't become the release's: the upgrade would overwrite
    # it, and only release files are backed up. "Ever": a seed an older release stopped shipping
    # and the client then deleted is still theirs to recreate (independent review).
    # Compared as a Mac or Windows disk sees names: `Notes/Plan.md` and `notes/plan.md` are one file.
    seed_keys = _seed_keys(record, manifest, source_repo, target)
    reclassified = sorted(p for p, e in files.items()
                          if e["class"] == "managed" and layout_mod.key(p) in seed_keys)
    if reclassified:
        raise Refusal(EXIT_PACKAGE, "release %s would take over %d file(s) that are yours (seeded "
                      "by a release this workspace has had)" % (manifest["version"], len(reclassified)),
                      reclassified[:20] + ["a release must never make a seed file its own"])
    # A newly shipped path that already exists as something of yours is a collision. Refuse:
    # the alternative is silently eating a file the release never owned.
    collisions = []
    for path, entry in files.items():
        if path in old_managed or path in old_seeded:
            continue
        if entry["class"] == "seed" and layout_mod.key(path) in seed_keys:
            continue  # the client's seed under this name, or another spelling of it: kept as theirs
        if os.path.exists(os.path.join(target, path)):
            collisions.append(path)
    if collisions:
        raise Refusal(
            EXIT_STATE,
            "release %s ships %d path(s) that already exist in this workspace and are not "
            "managed by the installed release" % (manifest["version"], len(collisions)),
            sorted(collisions)[:20] + ["move or delete them, then upgrade again"],
        )
    # Nothing it will write may sit under a link, a file in a folder's place, or another repository (a
    # submodule, initialized or not, whose files this repository could never commit). Checked here, before
    # the first write: found after it, the undo of the half-made upgrade would refuse on the same folder
    # (independent review, 3.1 round 57).
    writes = sorted(p for p, e in files.items() if e["class"] == "managed"
                    or not (os.path.lexists(os.path.join(target, p)) or layout_mod.key(p) in seed_keys))
    record_rel = os.path.relpath(install_record_path(target), target).replace(os.sep, "/")
    # The files it removes or rewrites count too: the managed files of the release it replaces, and each seed
    # file a declared line goes into (independent review, 3.1 round 58).
    lines_into = sorted({sl["path"] for sl in manifest.get("seed_lines") or []
                         if isinstance(sl, dict) and isinstance(sl.get("path"), str)})
    linked = _linked_paths(target, writes + sorted(old_managed) + lines_into + [record_rel] + _INSTALLER_PATHS)
    if linked:
        raise Refusal(EXIT_STATE, "release %s would write under a link, a file in a folder's place, or another "
                      "repository (a submodule); nothing was changed" % manifest["version"],
                      linked[:20] + ["make each a plain folder of this repository, or keep the release's files "
                                     "out of it, then upgrade again"])
    return record, current_version, min_from, creds, files, old_managed, old_seeded, manifest


def _to_drop(old_managed, files, manifest):
    """Managed files an upgrade removes because the new release stopped shipping them. On an
    adopted instance, only those its plan still adopts: one the plan now calls the instance's, or
    excludes, or no longer lists, stays where it is (independent review, 3.1)."""
    dropped = set(old_managed) - set(files)
    adoption = manifest.get("_adoption")
    if adoption:
        shipped = set(adoption.get("shipped") or ())
        dropped = {p for p in dropped if p not in shipped and _adoption_class(adoption, p) == "adopt"}
    return sorted(dropped)


def _adopted_upgrade_view(target, record, manifest):
    """An adopted instance upgrades only what it adopted, as its plan says today: a path the new
    release ships that the plan doesn't classify exactly once refuses, with nothing changed."""
    info = record["adoption"]
    plan, plan_sha = load_adoption_plan(target, info.get("plan"))
    # The plan that decides an upgrade must be one git tracks: an ignored copy could say anything,
    # unseen by the clean-worktree check (independent review, 3.1 round 3).
    plan_path = (info.get("plan") or ADOPTION_PLAN).replace(os.sep, "/")
    if not util.is_tracked(target, plan_path) or util.head_spellings(target, plan_path) != [plan_path]:
        raise Refusal(EXIT_STATE, "the adoption plan isn't committed any more, exactly as %s" % plan_path,
                      [plan_path, "commit it under that name, then upgrade"])
    # Everything the adopted instance runs on stays committed: an ignored local copy would let the
    # upgrade succeed while the commit, and a fresh clone, lack it (independent review, 3.1 round 9).
    keep = [(info.get("plan") or ADOPTION_PLAN), os.path.relpath(orgconfig.default_config_path(target), target),
            roles.POLICY_PATH, os.path.relpath(install_record_path(target), target)]
    keep = [k.replace(os.sep, "/") for k in keep] + sorted(e["path"] for e in record.get("managed") or [])
    untracked = [k for k in keep if not util.is_tracked(target, k)]
    if untracked:
        raise Refusal(EXIT_STATE, "%d file(s) this adopted instance runs on aren't committed" % len(untracked),
                      untracked[:20] + ["commit them (un-ignore them first if needed), then upgrade"])
    entries = {e["path"]: e for e in manifest.get("files") or []}
    classes, problems = classify_adoption(plan, entries)
    if problems:
        raise Refusal(EXIT_STATE, "this instance's adoption plan doesn't classify every path release %s "
                      "ships exactly once" % manifest["version"],
                      problems[:30] + ["add each to adopt, instance_owned or exclude, then upgrade again"])
    old_managed = {e["path"] for e in record.get("managed") or []}
    ignored = util.ignored_paths(target, [p for p in sorted(classes)
                                          if classes[p] == "adopt" and p not in old_managed])
    if ignored:
        raise Refusal(EXIT_STATE, "%d path(s) this upgrade would create are ignored by this repository's git "
                      "rules" % len(ignored), ignored[:20] + ["un-ignore them, or exclude them in the plan"])
    _require_lifecycle_holder(roles.load_policy(target), orgconfig.load(target))
    missing = [p for p in sorted(classes) if classes[p] == "instance_owned"
               and not os.path.lexists(os.path.join(target, p))]
    seeds = [p for p in sorted(classes) if classes[p] == "adopt" and entries[p].get("class") != "managed"]
    if missing or seeds:
        raise Refusal(EXIT_STATE, "this instance's adoption plan doesn't fit release %s" % manifest["version"],
                      ["%s: the plan says it's the instance's, but it doesn't exist" % p for p in missing[:20]]
                      + ["%s: a seed can't be adopted (it would never be kept current)" % p for p in seeds[:20]])
    view = adopted_view(manifest, classes)
    view["_adoption"] = {"plan": info.get("plan"), "plan_sha256": plan_sha, "adopt": plan["adopt"],
                         "instance_owned": plan["instance_owned"], "exclude": plan["exclude"],
                         "shipped": sorted(classes)}
    return view


def _upgrade_locked(target, manifest, source_repo, aios_lookup=None, no_vercel=False):
    record, current_version, min_from, creds, files, old_managed, old_seeded, manifest = _upgrade_preflight(
        target, manifest, source_repo, aios_lookup)
    the_plan, site_rows, blocked = _layout_preflight(target, record, manifest, files, old_managed,
                                                     no_vercel, _installed_layout(record, source_repo))
    if blocked:
        raise Refusal(EXIT_STATE, "the folder move needs Vercel checked first (R-A); nothing was "
                                  "changed", blocked)
    move_keys = layout_mod.destinations(the_plan)
    seed_keys = _seed_keys(record, manifest, source_repo, target)
    seed_lines_kept, seed_lines_add, seed_lines_settled = _seed_line_plan(
        target, record, manifest, _moved_from(the_plan), _handled_seed_lines(target, record, source_repo))
    if the_plan:
        # The folder move too, before the first write: every file it moves, from and to, each it sets aside,
        # and each emptied folder (independent review, 3.1 round 58).
        linked = _linked_paths(target, _plan_paths(the_plan))
        if linked:
            raise Refusal(EXIT_STATE, "the folder move would go through a link, a file in a folder's place, or "
                          "another repository (a submodule); nothing was changed",
                          linked[:20] + ["make each a plain folder of this repository, then upgrade again"])

    # Folders that already exist on the way to anything this release writes. A rollback prunes
    # only the folders the upgrade made: an empty folder of the client's survives (independent review).
    pre_dirs = set()
    for p in files:
        parts = p.split("/")[:-1]
        for i in range(1, len(parts) + 1):
            d = "/".join(parts[:i])
            if os.path.isdir(os.path.join(target, d)):
                pre_dirs.add(d)
    pre_dirs = sorted(pre_dirs)

    # A random part too, so two upgrades in one second, or a retry after a kill, each get a new
    # snapshot folder, which _backup makes exclusively (independent review, 3.1 round 23).
    txn_id = "%s-%s-to-%s-%s" % (util.now_iso().replace(":", "").replace("-", ""),
                                 current_version, manifest["version"], os.urandom(3).hex())
    backup_root = _backup(target, record, txn_id)
    backup_rel = os.path.relpath(backup_root, target).replace(os.sep, "/")
    if the_plan:
        # The whole move, on disk before the first file moves. Rollback after a finished upgrade
        # reads it from here; recovery after a hard kill reads the journal's copy.
        util.write_json(os.path.join(backup_root, LAYOUT_PLAN), the_plan)
    util.write_json(journal_path(target), {
        "op": "upgrade", "txn": txn_id, "from_version": current_version,
        "to_version": manifest["version"], "backup": backup_rel,
        "phase": "applying", "started_at": util.now_iso(),
        # The record as it was: recovery accepts the record on disk only if it is this one or the one
        # this upgrade writes (journaled below, before it's written) (independent review, 3.1 round 35).
        "record_sha256_before": sha256_file(install_record_path(target)),
        # What this upgrade intends to ADD. A hard kill can stop anywhere, and the install
        # record on disk still describes the OLD release, so it cannot tell recovery about
        # files the aborted attempt already created. Without this, rollback leaves orphans.
        "adds": sorted({p for p, e in files.items()
                        if e["class"] == "managed" and p not in old_managed}),
        # The exact bytes and mode of each file this upgrade may write, so recovery removes a file
        # only while it is still that file, never a client's that appeared at the path later.
        "add_provenance": {p: [e["sha256"], 0o755 if e.get("mode") == "100755" else 0o644]
                           for p, e in files.items() if p not in old_managed},
        # Seeds this upgrade may create. A hard kill leaves them behind otherwise, and the
        # install record still describes the old release, so recovery cannot infer them.
        # Never a path a client file is moving to: recovery would delete the client's file.
        "seed_adds": sorted({p for p, e in files.items()
                             if e["class"] == "seed" and layout_mod.key(p) not in seed_keys
                             and layout_mod.key(p) not in move_keys
                             and not os.path.lexists(os.path.join(target, p))}),
        # The declared lines this upgrade appends to seed files, with their exact bytes, so a
        # recovery after a hard kill takes back only those.
        "seed_lines": seed_lines_add,
        # The folder move (3.0): every file, its hash and both paths, so recovery can put each
        # one back from any point of an interrupted move.
        "layout": the_plan,
        "pre_dirs": pre_dirs,
    })

    new_managed, new_seeded, created_seeds = [], [], []
    written = 0
    try:
        if the_plan:
            util.fault("layout.before_moves")
            layout_mod.apply(target, the_plan, backup_rel)
            problems = layout_mod.readback(target, the_plan, backup_rel)
            if problems:
                raise Refusal(EXIT_VERIFY, "the folder move did not keep every file's bytes",
                              problems[:20])
        util.fault("upgrade.before_write")
        for path, mode, data in util.read_tree(source_repo, manifest["created_from"]["git_rev"]):
            entry = files.get(path)
            if entry is None:
                continue
            if entry["sha256"] != sha256_bytes(data):
                raise Refusal(EXIT_PACKAGE,
                              "content at the pin does not match the manifest: %s" % path)
            if entry["class"] == "seed":
                dest = os.path.join(target, path)
                if os.path.lexists(dest):
                    # Already here: the client's own copy, or their file moved here by the layout
                    # move. Seeds are written once, never refreshed: the client's bytes win.
                    new_seeded.append({"path": path, "sha256": sha256_file(dest)
                                       if os.path.isfile(dest) else ""})
                elif layout_mod.key(path) in seed_keys:
                    # Seeded once already and the operator deleted it. "Written once, then
                    # never touched again" has to include not resurrecting it: an upgrade
                    # that undoes a deletion has not preserved state, whatever it reports.
                    # That holds under its new name after a folder move too.
                    new_seeded.append({"path": path, "sha256": ""})
                else:
                    sha = util.write_file(target, path, data, entry.get("mode", "100644"))
                    created_seeds.append(path)
                    new_seeded.append({"path": path, "sha256": sha})
                continue
            previous = old_managed.get(path)
            sha = util.write_file(target, path, data, entry.get("mode", "100644"))
            new_managed.append({"path": path, "sha256": sha, "exec": entry.get("mode") == "100755"})
            if previous and previous.get("sha256") != sha:
                # Fire only after a file that genuinely CHANGED. Crashing after writing a
                # byte-identical file leaves a workspace that still verifies clean, which
                # would make the recovery test pass without recovering anything.
                written += 1
                if written == 1:
                    util.fault("upgrade.mid_write")

        # Managed files the new release dropped. On an adopted instance, a file the release still
        # ships but the plan no longer adopts stays where it is and becomes the instance's: only a
        # file the release stopped shipping goes.
        dropped = _to_drop(old_managed, files, manifest)
        for path in dropped:
            full = os.path.join(target, path)
            if os.path.isfile(full):
                os.remove(full)
        _prune_parents(target, dropped)
        if the_plan:
            layout_mod.remove_emptied(target, the_plan, also=dropped)
            left = layout_mod.leftovers(target, the_plan)
            if left:
                raise Refusal(EXIT_STATE, "the folder move left %d thing(s) in the old folders"
                              % len(left), left[:20])
        _apply_seed_lines(target, seed_lines_add)
        util.fault("upgrade.before_record")

        new_record = dict(record)
        new_record.pop(RECORD_SEAL, None)  # the adoption's record keeps it, in `previous`
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
        if manifest.get("_adoption"):  # the plan as it stands now; set only by the preflight, in-process
            new_record["adoption"] = dict(record.get("adoption") or {},
                                          **{k: v for k, v in manifest["_adoption"].items() if k != "shipped"})
        new_record["seed_history"] = sorted(_seed_history(record, manifest, source_repo, target)
                                            | {p for p, e in files.items() if e["class"] == "seed"})
        if seed_lines_kept or seed_lines_add or seed_lines_settled:
            new_record["seed_lines"] = seed_lines_kept + seed_lines_settled + seed_lines_add
        # What this upgrade alone appended, written fresh by each upgrade: its rollback takes back these
        # and nothing carried in the record from before (independent review, 3.1 round 41).
        new_record["seed_lines_added"] = seed_lines_add
        new_record["credentials"] = [{"name": c["name"], "ref": c["ref"],
                                      "required": c["required"], "resolved": c["resolved"]}
                                     for c in creds]
        # Seeds this upgrade wrote, with their bytes, so rollback removes the ones still untouched
        # and the workspace goes back to exactly what it was.
        new_record["created_seeds"] = [{"path": p, "sha256": sha256_file(os.path.join(target, p)),
                                        "mode": stat.S_IMODE(os.lstat(os.path.join(target, p)).st_mode)}
                                       for p in sorted(created_seeds)]
        new_record["pre_existing_dirs"] = pre_dirs
        if manifest.get("layout"):
            new_record["layout"] = layout_mod.version_of(manifest["layout"])
        new_record.pop("layout_migration", None)
        if the_plan:
            proof_rel = "%s/%s" % (backup_rel, LAYOUT_PROOF)
            util.write_json(os.path.join(target, proof_rel),
                            layout_mod.proof(target, the_plan, backup_rel))
            new_record["layout_migration"] = {
                "from": the_plan["from"], "to": the_plan["to"],
                "moved": len(the_plan["moves"]), "set_aside": len(the_plan["quarantine"]),
                "empty_folders": len(the_plan["empty_dirs"]),
                "plan": "%s/%s" % (backup_rel, LAYOUT_PLAN), "proof": proof_rel,
                "sites": site_rows,
                "vercel": "checked with Vercel" if not no_vercel or os.environ.get(hosting.ENV_TOKEN)
                          else "not checked: the founder stated this repository isn't deployed by Vercel",
                # Reported, never rewritten: the client's own files that still name an old folder.
                "stale_references": layout_mod.stale_references(
                    target, manifest["layout"],
                    skip_paths={e["path"] for e in new_managed} | {INSTALL_PATH} | set(created_seeds)),
            }
        new_record["upgraded_at"] = util.now_iso()
        new_record["status"] = "installed"
        new_record["previous"] = {
            "release_id": (record.get("release") or {}).get("release_id"),
            "version": current_version,
            "backup": backup_rel,
        }
        progress = load_journal(target)
        progress["record_sha256_after"] = sha256_bytes(
            (json.dumps(new_record, indent=2, sort_keys=True) + "\n").encode("utf-8"))
        util.write_json(journal_path(target), progress)
        util.write_json(install_record_path(target), new_record)
        # The record this upgrade wrote, kept in its own snapshot (git-ignored, local): its rollback
        # trusts the committed record only while it is still exactly this (independent review, 3.1
        # round 32).
        util.write_json(os.path.join(backup_root, "after.json"), new_record)
        require_verified(target, new_record, "upgraded workspace")
    except BaseException as exc:
        # Any failure puts the workspace back where it started, then re-raises.
        #
        # Remove only MANAGED paths the new release introduced. An earlier version of this
        # line removed `set(files) - set(old_managed)`, which includes every *seed* path -
        # so a failed upgrade deleted CLAUDE.md, the foundations and the logs while
        # reporting a clean rollback. The state-fingerprint test caught it.
        new_managed_paths = {p for p, e in files.items() if e["class"] == "managed"}
        # Seed files this attempt created are part of what it changed, so they come out too.
        # Without this the workspace "rolled back" while carrying new files, and still
        # verified clean - the rollback reported a state it had not restored.
        removable = sorted(p for p in (new_managed_paths - set(old_managed)) | set(created_seeds)
                           if layout_mod.key(p) not in move_keys)
        _restore(target, backup_root, record, remove_paths=removable,
                 expected=set(old_managed) | new_managed_paths | set(created_seeds),
                 write_record=False, keep_dirs=pre_dirs,
                 provenance={p: [e["sha256"], 0o755 if e.get("mode") == "100755" else 0o644]
                             for p, e in files.items() if p not in old_managed})
        # The reverse of the order they happened: declared lines come off while their file is
        # still where the upgrade put it, then the folders go back (independent review, round 3).
        _undo_seed_lines(target, seed_lines_add)
        if the_plan:
            layout_mod.reverse(target, the_plan, backup_rel)
        _restore_record(target, backup_rel)  # its own bytes, as the other two restores (3.1 round 45)
        problems, _ = verify(target, record)
        if problems:  # the journal stays: `rollback` can finish the job
            raise Refusal(EXIT_VERIFY,
                          "upgrade failed AND the automatic rollback did not restore cleanly",
                          [str(exc)] + problems + ["run `aios rollback` to finish restoring"])
        _write_state(target)
        if os.path.isfile(journal_path(target)):
            os.remove(journal_path(target))
        if isinstance(exc, Refusal):
            exc.details = list(exc.details) + ["workspace was rolled back to %s and verified"
                                               % current_version]
            raise
        raise Refusal(EXIT_VERIFY,
                      "upgrade failed and the workspace was rolled back to %s (verified)"
                      % current_version, [str(exc)])

    _write_state(target)  # before the journal goes: a kill in between is recovered from the journal
    os.remove(journal_path(target))
    return new_record


# ─── rollback ───────────────────────────────────────────────────────────────

def _holder_alive(text):
    """Is the process named in a lock file still running on this machine? Only ever asked under the
    workspace guard, which every holder takes while it creates and writes its lock: so a lock that
    names no process lost its holder between the two, and is dead as well (independent review, 3.1
    round 11; before the lock was taken under the guard, such a lock had to count as alive)."""
    m = re.search(r"pid=(\d+)", text or "")
    if not m:
        return False
    try:
        os.kill(int(m.group(1)), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # running, as somebody else
    except OSError:
        return False
    return True


def rollback(target, source_repo=None):
    """Restore the previous release. Works after a clean upgrade, a hard kill, or a killed rollback.
    Undoing a finished adoption also needs `source_repo`, the release's source (3.1 round 24)."""
    # A killed holder leaves its lock behind. Recovery is exactly when you need to get in, so
    # rollback clears a stale lock. A LIVE holder's lock is never taken: two operations at once
    # would interleave their writes (independent review).
    with _RecoveryGuard(target):  # one recovery at a time decides about a stale lock
        stale_lock = _reclaim_stale_lock(os.path.join(target, LOCK_PATH), target)
    return _rollback_after_reclaim(target, stale_lock, source_repo)


try:
    import fcntl as _fcntl
except ImportError:  # Windows
    _fcntl = None
try:
    import msvcrt as _msvcrt
except ImportError:  # everywhere but Windows
    _msvcrt = None

# In the installer's own git-ignored backups folder, which every release since 2.6 reserves, so it
# can never be a file of the client's (independent review, round 12).
GUARD_PATH = os.path.join(BACKUP_DIR, "guard")


def _guard_path(target):
    """Where the guard lives: inside git's own folder when the workspace is a git repository, where
    git status never sees it (so a guard Windows can't delete never shows as a change, before or
    after an adoption; independent review, 3.1 round 7), else in the reserved backups folder."""
    git_dir = util.git(target, ["rev-parse", "--absolute-git-dir"], check=False) \
        if os.path.isdir(target) else ""
    if git_dir and os.path.isdir(git_dir):
        return os.path.join(git_dir, "aios-guard")
    return os.path.join(target, GUARD_PATH)


class _RecoveryGuard(object):
    """An OS-held lock around every decision about the workspace lock: taking it, releasing it,
    and judging and clearing a stale one. So two recoveries can't both clear it (independent
    review, round 3), and no new holder can take the lock between a recovery's "this one is dead"
    and its removal (round 10).

    flock on macOS and Linux; on Windows, msvcrt's lock on the file's first byte, which holds
    across processes the same way (round 11). A system with neither is refused rather than left
    unguarded. The file exists only while held: the holder deletes it before letting go, and a
    waiter that then gets the lock checks the name still means the file it locked, or starts
    again. So no file is left behind, not even after a refusal. (Windows can't delete an open
    file, so there it stays, in the git-ignored backups folder.) A killed holder's lock goes with
    its process."""

    def __init__(self, target):
        self.target = target
        self.path = _guard_path(target)
        self.in_backups = self.path == os.path.join(target, GUARD_PATH)
        self.fd = None

    def __enter__(self):
        if _fcntl is None and _msvcrt is None:
            raise Refusal(EXIT_STATE, "this system has no file lock the installer can use, so it won't "
                                      "change anything", ["run it on macOS, Linux or Windows"])
        # .aios and .aios/backups must be real folders wherever the guard lives: every lock, journal,
        # record and backup goes through them, and a link would send those writes outside the
        # workspace (independent review, 3.1 round 21: the guard's move into git's folder had skipped it).
        backups = os.path.join(self.target, BACKUP_DIR)
        for part in (os.path.dirname(backups), backups):
            if os.path.islink(part) or (os.path.lexists(part) and not os.path.isdir(part)):
                raise Refusal(EXIT_STATE, "%s is a link or a file, not a folder" % part)
        # Nor another repository (a submodule, initialized or not): the workspace lock, and outside git this
        # guard, would be written inside it before any operation's own checks ran (independent review, 3.1
        # round 60).
        links = util.gitlinks(self.target)
        for rel in (AIOS_DIR, BACKUP_DIR):
            rel = rel.replace(os.sep, "/")
            if util.another_repository(self.target, rel, links):
                raise Refusal(EXIT_STATE, "%s is another repository (a submodule), not the installer's own folder; "
                              "nothing was changed" % rel, ["make it a plain folder of this repository again, then "
                                                            "run this again"])
        if self.in_backups:
            os.makedirs(backups, exist_ok=True)
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        while True:
            # Made by this run, or already there (left on Windows, or a file of the repository's own,
            # which only a reserved path being taken could explain). Only one this run made is ever
            # deleted (independent review, 3.1 round 5).
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_RDWR | nofollow, 0o644)
                created = True
            except FileExistsError:
                try:
                    fd = os.open(self.path, os.O_RDWR | nofollow)
                except FileNotFoundError:
                    continue  # its holder deleted it a moment ago: make one
                created = False
            try:
                _os_lock(fd)
                held = os.fstat(fd)
                try:
                    named = os.lstat(self.path)
                except OSError:
                    named = None
            except BaseException:
                os.close(fd)
                raise
            if named is not None and (named.st_dev, named.st_ino) == (held.st_dev, held.st_ino):
                self.fd, self.created = fd, created
                return self
            _os_unlock(fd)  # the holder before us deleted it: lock the file that's there now
            os.close(fd)

    def __exit__(self, *exc):
        if self.fd is not None:
            if getattr(self, "created", False):
                try:
                    # Only if the name still means the very file this run holds: never a file that
                    # replaced it meanwhile (independent review, 3.1 round 6). While still held, so no
                    # one can be locking it as it goes.
                    held, named = os.fstat(self.fd), os.lstat(self.path)
                    if (held.st_dev, held.st_ino) == (named.st_dev, named.st_ino):
                        os.remove(self.path)
                except OSError:
                    pass  # gone already, or Windows (an open file can't be deleted; it stays, ignored)
            _os_unlock(self.fd)
            os.close(self.fd)
            self.fd = None
        return False


def _os_lock(fd):
    if _fcntl is not None:
        _fcntl.flock(fd, _fcntl.LOCK_EX)
        return
    os.lseek(fd, 0, os.SEEK_SET)
    while True:  # LK_LOCK gives up after 10 s; a holder may legitimately take longer
        try:
            _msvcrt.locking(fd, _msvcrt.LK_NBLCK, 1)
            return
        except OSError:
            time.sleep(0.05)


def _os_unlock(fd):
    if _fcntl is not None:
        return  # closing the file releases flock
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        _msvcrt.locking(fd, _msvcrt.LK_UNLCK, 1)
    except OSError:
        pass


def _reclaim_stale_lock(stale, target=None):
    """Clear a lock whose holder is dead. True if one was cleared."""
    if not os.path.exists(stale):
        return False
    if target is not None and _repo_owned(target, LOCK_PATH):
        # The installer's lock is never committed (.aios/.gitignore ignores it): a tracked one is the
        # repository's own file, whatever it says (independent review, 3.1 round 20).
        raise Refusal(EXIT_STATE, "%s is a file this repository tracks, not the installer's lock"
                      % LOCK_PATH.replace(os.sep, "/"),
                      ["if an interrupted operation left it and it was committed by mistake, untrack it "
                       "(git rm --cached %s), commit, and run this again; otherwise move the repository's "
                       "own file" % LOCK_PATH.replace(os.sep, "/")])
    text = ""
    ident = None
    try:
        fd = os.open(stale, os.O_RDONLY)
        try:
            st = os.fstat(fd)
            words = os.read(fd, 4096)
            ident = (st.st_dev, st.st_ino, words)
            text = words.decode("utf-8", "replace")
        finally:
            os.close(fd)
    except OSError:
        return False
    if _holder_alive(text):
        raise Refusal(EXIT_STATE, "another operation is still running in this workspace",
                      ["lock held by: %s" % text.strip(),
                       "let it finish, or stop that process, then run rollback. If you're sure "
                       "nothing is running, delete %s" % LOCK_PATH])
    try:
        if _still_this_lock(stale, ident):  # still the lock we judged dead
            os.remove(stale)
            return True
    except OSError:
        pass
    return False


def _rollback_after_reclaim(target, stale_lock, source_repo=None):
    with _Lock(target, "rollback"):
        journal = load_journal(target)  # refuses a tracked, non-file or non-journal one (3.1 rounds 25-28)
        _require_state_folder(target)  # before anything changes (3.1 round 34)
        if not journal and os.path.isfile(install_record_path(target)):
            _check_state(target)  # a finished operation: the record must be the one it wrote (round 33)
        record_full = install_record_path(target)
        if os.path.lexists(record_full):
            # The record too, before anything is decided: present but not a readable file is a refusal,
            # never "no record" or a crash (independent review, 3.1 round 28).
            if os.path.islink(record_full) or not os.path.isfile(record_full):
                raise Refusal(EXIT_STATE, ".aios/install.json isn't the install record (a link or a folder); "
                                          "nothing was changed", ["restore it from git, or move it aside"])
            try:
                with open(record_full, "rb") as fh:
                    fh.read(1)
            except OSError as exc:
                raise Refusal(EXIT_STATE, "the install record can't be read (%s); nothing was changed" % exc)
        if stale_lock and not journal and not os.path.isfile(install_record_path(target)):
            # Killed before its journal, with no release ever pinned here (an adoption that hadn't
            # started writing): nothing changed, so there is nothing to undo (independent review,
            # 3.1 round 8).
            result = (None, dict(NO_RELEASE_SUMMARY, unchanged=True), "an interrupted operation had not changed "
                      "anything; cleared its lock, nothing to roll back")
        elif stale_lock and not journal:
            # A killed upgrade or rollback with no journal either never changed anything (the
            # journal is written before the first change) or had already finished. Rolling back now
            # would undo the PREVIOUS release, which nobody asked for (found by the 3.0 rehearsal's
            # real SIGKILLs).
            record = load_record(target)
            problems, summary = verify(target, record)
            if problems:
                raise Refusal(EXIT_VERIFY, "an interrupted operation left no journal, but the workspace "
                              "doesn't match its release", problems)
            result = (record, summary, "an interrupted operation had either not changed anything yet or "
                                       "had finished; cleared its lock, rolled nothing back")
        elif journal and journal.get("op") == "adopt-existing":
            info, pending = journal.get("adoption") or {}, journal.get("pending")
            pending = pending if isinstance(pending, dict) else {}
            _refuse_other_repositories(target, [c.get("path") for c in info.get("created") or [] if isinstance(c, dict)]
                                       + [pending.get(k) for k in ("path", "temp")] + _own_paths(target),
                                       "undoing the interrupted adoption")
            notes = _undo_adoption(target, journal.get("adoption") or {}, journal.get("pending"))
            os.remove(journal_path(target))
            result = (None, dict(NO_RELEASE_SUMMARY, record_left=os.path.lexists(install_record_path(target))),
                      "an interrupted adoption was undone: every file it created and left unchanged is gone"
                      + "".join("; " + n for n in notes))
        elif (journal and journal.get("op") == "adopt-undo") or (not journal and _completed_adoption(target)):
            # What the adoption made comes only from its anchor (the record and plan as committed with it)
            # and the release source, on the first pass and on every resumed one: the journal holds
            # progress only (independent review, 3.1 rounds 22 to 26).
            # A resumed undo uses the anchor its first pass journaled: it never infers progress from a
            # record that's gone, which a pull request could have deleted (independent review, 3.1 round 36).
            anchored = _adoption_anchor(target, journal["anchor"]) if journal and "anchor" in journal \
                else _adoption_anchor(target)
            if anchored is not None:
                anchor_record, anchor_plan, anchor = anchored
                trusted = _release_adopted(anchor_record, anchor_plan, source_repo)
                info = anchor_record.get("adoption") or {}
                if anchor and not journal and not os.path.isfile(os.path.join(target, STATE_PATH)):
                    # No upgrade or rollback since the adoption, as git history shows it, unless this
                    # machine's own note says the record here is the one its last operation wrote (the note
                    # matched just above, or rollback refused). Otherwise a pull request could restore the
                    # adoption's exact record after an upgrade, and the undo would leave the upgrade's files
                    # behind (independent review, 3.1 round 47). An edit that kept the release, then undone,
                    # changes nothing this undo decides: that comes from the anchor commit.
                    record_rel = os.path.relpath(install_record_path(target), target).replace(os.sep, "/")
                    # And the anchor must be the only commit that ever added the record, on any side of any
                    # merge. A pull request could delete the record with the adoption's files and add them
                    # back with a forged record and a wider plan: the newest addition would then pass for the
                    # adoption, and the undo would remove a file the repository owned (independent review,
                    # 3.1 round 53).
                    added_by = _additions(target, record_rel)  # oldest first, merge commits' additions included
                    if len(added_by) > 1:
                        raise Refusal(EXIT_STATE, "the install record was added more than once in this history "
                                      "(commits %s), so which addition was the adoption can't be read from it, "
                                      "and this machine has no note of the operation that wrote the record here; "
                                      "nothing was changed" % ", ".join(c[:12] for c in added_by[:5]),
                                      ["undo it where the adoption ran, or with git: revert the commits from the "
                                       "first adoption on"])
                    since = []
                    # Every side of every merge: git's default walk follows only a parent the merge
                    # took this path from, so a branch that upgraded, merged with the record set back,
                    # would go unseen while its files came along (independent review, 3.1 round 48).
                    for commit in util.git(target, ["log", "--full-history", "--format=%H", "%s..HEAD" % anchor,
                                                    "--", ":(literal)" + record_rel], check=False).split():
                        raw = util.git(target, ["show", "%s:%s" % (commit, record_rel)], binary=True, check=False)
                        try:
                            then = json.loads(raw.decode("utf-8"))
                        except ValueError:
                            then = None
                        if not isinstance(then, dict) or then.get("release") != anchor_record.get("release") \
                                or then.get("previous"):
                            since.append(commit)
                    if since:
                        raise Refusal(EXIT_STATE, "an upgrade or rollback changed the install record after the "
                                      "adoption committed it (commit %s), and this machine has no note of the "
                                      "operation that wrote the record here; nothing was changed" % since[-1][:12],
                                      ["undo it where the last upgrade or rollback ran, or with git: revert the "
                                       "later commits, then the adoption commit %s" % anchor[:12]])
                if anchor:
                    # The commit that added the record must be the adoption itself: only files it added
                    # alongside the record can be ones the adoption made, and a record claiming any
                    # other path is refused outright (independent review, 3.1 round 29).
                    # And it must say exactly what that adoption made: every file the release adopts
                    # under the plan, all added by that commit, no more and no fewer. A record claiming
                    # less would leave files behind and still report the adoption undone (round 30).
                    added = _added_in(target, anchor)
                    config_rel = os.path.relpath(orgconfig.default_config_path(target), target).replace(os.sep, "/")
                    claimed = {str(c.get("path") if isinstance(c, dict) else c) for c in info.get("created") or []}
                    claimed.discard(config_rel)  # the people map keeps its own rule
                    not_added = sorted(p for p in trusted if p not in added)
                    unproven = sorted(claimed - set(trusted))
                    unclaimed = sorted(set(trusted) - claimed)
                    if not_added or unproven or unclaimed:
                        raise Refusal(EXIT_STATE, "the install record committed at %s doesn't match the adoption "
                                      "that commit made; nothing was changed" % anchor[:12],
                                      ["not added by that commit: %s" % p for p in not_added[:10]]
                                      + ["claimed but not the release's adopted file: %s" % p for p in unproven[:10]]
                                      + ["the release's adopted file, not claimed: %s" % p for p in unclaimed[:10]]
                                      + ["commit an adoption as one commit (git add -A, then git commit), or "
                                         "undo it by hand from git"])
            elif not journal:
                raise Refusal(EXIT_STATE, "there is no install record to undo")
            else:
                # Resuming an undo that already removed an uncommitted record, its last step: what it
                # made is gone; only its temporaries and folders are left to tidy.
                anchor, trusted, info = None, {}, {}
            if not journal or journal.get("phase") != "complete":
                # Nothing it removes may be inside another repository: a submodule a pull request made of an
                # adopted folder holds that repository's files. Checked before the first write, on the first
                # pass and on a resumed one, as every operation does (independent review, 3.1 rounds 58 and
                # 59). A file reached through a link is left and reported instead, as since round 20: the link
                # is this repository's own file.
                _refuse_other_repositories(target, sorted(trusted) + _own_paths(target), "undoing the adoption")
            if not journal:
                # Journaled before the first removal, so a kill partway through is finished by the
                # next rollback, not left half-undone (independent review, 3.1).
                journal = {"op": "adopt-undo", "phase": "undoing", "started_at": util.now_iso(),
                           "anchor": anchor,
                           "config": orgconfig.load(target) if os.path.isfile(
                               orgconfig.default_config_path(target)) else None}
                util.write_json(journal_path(target), journal)
            if journal.get("phase") != "complete":
                util.fault("adopt.undo_before")
                notes = _undo_adoption(target, info, trusted=trusted, anchor=anchor)
                journal["phase"] = "complete"
                journal["notes"] = notes
                util.write_json(journal_path(target), journal)
            left = os.path.lexists(install_record_path(target))
            result = (None, dict(NO_RELEASE_SUMMARY, record_left=left),
                      "the adoption was undone: every file it created and left unchanged is gone"
                      + ("" if left else ", and the workspace is no longer pinned to a release")
                      + "".join("; " + n for n in journal.get("notes") or []))
        elif journal and journal.get("op") == "rollback" and journal.get("phase") == "complete":
            # It had finished and noted the record it wrote: the record must still be that one before
            # anything is cleared (independent review, 3.1 round 37).
            _check_state(target)
            record = load_record(target)
            problems, summary = verify(target, record)
            if problems:  # (independent review, round 3) never report success over drift
                raise Refusal(EXIT_VERIFY, "the previous rollback had finished, but the workspace no "
                              "longer matches its release", problems)
            result = (record, summary, "the previous rollback had finished; cleared what it left, "
                                       "rolled nothing further back")
        else:
            result = _rollback_locked(target, journal)
        _sweep_temporaries(target)  # whatever a killed operation's state writes left (3.1 round 17)
    # A finished rollback keeps its journal, marked complete, until its lock is gone: a kill in
    # between must not make the next rollback go back one release too far (independent review).
    done = load_journal(target)
    if done and done.get("op") in ("rollback", "adopt-undo") and done.get("phase") == "complete":
        os.remove(journal_path(target))
    return result


def clear_dead_lock(target):
    """A dead holder's lock, when there is nothing at all to roll back: no journal, no install
    record. It never takes a live holder's lock. True if one was cleared."""
    if os.path.lexists(journal_path(target)) or os.path.lexists(install_record_path(target)):
        return False  # by the path, never by what a file there says (3.1 round 27)
    if not os.path.lexists(os.path.join(target, LOCK_PATH)):
        # Nothing to clear, so no guard either: outside git it would create `.aios/backups` in a folder
        # that has nothing of the installer's (independent review, 3.1 round 15). A lock that appears
        # after this look is a live holder's.
        return False
    with _RecoveryGuard(target):
        cleared = _reclaim_stale_lock(os.path.join(target, LOCK_PATH), target)
        if cleared:  # still under the guard, so no new holder is writing yet
            _sweep_temporaries(target)
        return cleared


# The temporary files the installer itself names: a state file's (util.write_json) and a copy being
# created (util.private_temp), each with tempfile's eight random characters. A kill leaves them.
_STATE_TEMP = re.compile(r"^\.(install|config|txn)\.json\.[a-z0-9_]{8}\.tmp$")
_COPY_TEMP = re.compile(r"^\.write-[a-z0-9_]{8}$")
_NOTE_TEMP = re.compile(r"^\.head\.json\.[a-z0-9_]{8}\.tmp$")


def _sweep_temporaries(target):
    """Remove the temporaries a killed operation left: only names the installer makes, only regular
    files, only in `.aios` and its backups folder. Run only while holding the lock or the guard, when
    no other operation can be writing one (independent review, 3.1 round 17)."""
    removed = []
    for rel_dir, pattern in ((AIOS_DIR, _STATE_TEMP), (BACKUP_DIR, _COPY_TEMP),
                             (os.path.dirname(STATE_PATH), _NOTE_TEMP)):
        folder = os.path.join(target, rel_dir)
        if _linked_paths(target, [rel_dir.replace(os.sep, "/") + "/x"]) or not os.path.isdir(folder):
            continue
        for name in sorted(os.listdir(folder)):
            full = os.path.join(folder, name)
            rel = os.path.join(rel_dir, name).replace(os.sep, "/")
            # A name is not proof: a file git tracks is the repository's, whatever it's called
            # (independent review, 3.1 round 18). Adoption also refuses to start over one.
            if pattern.match(name) and stat.S_ISREG(os.lstat(full).st_mode) and not _repo_owned(target, rel):
                os.remove(full)
                removed.append(rel)
    return removed


NO_RELEASE_SUMMARY = {"release_id": None, "version": None, "managed_checked": 0, "managed_total": 0}


def _completed_adoption(target):
    """An adopted instance with nothing before the adoption to go back to: rollback undoes it."""
    if not os.path.isfile(install_record_path(target)):
        return False
    record = load_record(target)
    return bool(record.get("adoption")) and not record.get("previous")


def _rollback_locked(target, journal):
    record_path = install_record_path(target)
    current = None
    if os.path.isfile(record_path):
        try:
            current = util.read_json(record_path)
        except ValueError:
            # A kill mid-write used to leave unparseable JSON here and the recovery command
            # died on it - the crash handler crashing is the worst possible failure mode.
            # The journal and the backup are enough to recover without it.
            if not journal:
                raise Refusal(
                    EXIT_STATE,
                    "the install record is corrupt and there is no journal to recover from",
                    [record_path, "restore .aios/install.json from a snapshot under "
                                  ".aios/backups/ and run verify"],
                )
            current = None

    if journal and journal.get("op") == "rollback":
        return _finish_rollback(target, journal, resumed=True)

    if journal:
        # Before anything changes: the record on disk must be the one this upgrade started from or the
        # one it was writing, and the snapshot and every path must be the installer's own (round 35).
        if journal.get("record_sha256_before"):
            # An upgrade never leaves the record missing or half-written (every write is atomic), so a
            # missing, unreadable or different one isn't the upgrade's (independent review, 3.1 round 36).
            try:
                if os.path.islink(record_path) or not os.path.isfile(record_path):
                    raise OSError("not a file")
                on_disk = sha256_file(record_path)
            except OSError:
                on_disk = None
            allowed = {h for h in (journal.get("record_sha256_before"), journal.get("record_sha256_after")) if h}
            if on_disk is None or on_disk not in allowed:
                raise Refusal(EXIT_STATE, "the install record isn't the one the interrupted upgrade started "
                                          "from or was writing; nothing was changed",
                              ["restore it from git, then run rollback again"])
        _require_trusted_snapshot(target, journal["backup"], ())  # the path first, before anything is read
        try:
            prior = util.read_json(os.path.join(target, journal["backup"], "install.json"))
        except (OSError, ValueError) as exc:
            raise Refusal(EXIT_STATE, "the snapshot's install record can't be read (%s); nothing was changed"
                          % exc)
        _require_trusted_snapshot(target, journal["backup"], (current or {}, prior),
                                  list(journal.get("adds") or []) + list(journal.get("seed_adds") or [])
                                  + list((journal.get("add_provenance") or {}).keys()))
        backup_root = os.path.join(target, journal["backup"])
        the_plan = journal.get("layout")
        if the_plan:
            # Checked before anything changes: a refusal here leaves the workspace as it was.
            blocked = layout_mod.reverse_conflicts(target, the_plan, journal["backup"])
            if blocked:
                raise Refusal(EXIT_STATE, "putting the folders back would overwrite %d file(s)"
                              % len(blocked), sorted(blocked)[:20]
                              + ["move those aside, then run rollback again"])
        move_keys = layout_mod.destinations(the_plan)
        # A hard kill can land anywhere, so remove every path the new release owns that the
        # old one did not, rather than trusting how far the write loop got. Never a path a
        # client file was moving to: that file goes back to its old path below.
        prior_paths = {e["path"] for e in prior.get("managed") or []}
        current_paths = {e["path"] for e in (current or {}).get("managed") or []}
        journal_adds = set(journal.get("adds") or []) | set(journal.get("seed_adds") or [])
        remove = sorted(p for p in (current_paths | journal_adds) - prior_paths
                        if layout_mod.key(p) not in move_keys)
        if the_plan:
            linked = _linked_paths(target, _plan_paths(the_plan, journal["backup"]))
            if linked:
                raise Refusal(EXIT_STATE, "putting the folders back would go through %d link(s)"
                              % len(linked), linked[:20] + ["replace them with real folders, then run rollback again"])
        # Every path this recovery puts back, removes or edits, before its first write (independent review, 3.1
        # round 59): a submodule could have appeared while the upgrade was interrupted.
        _refuse_other_repositories(target, sorted(current_paths | prior_paths | journal_adds)
                                   + [e.get("path") for e in journal.get("seed_lines") or [] if isinstance(e, dict)]
                                   + _own_paths(target), "recovering the interrupted upgrade")
        notes = _restore(target, backup_root, prior, remove, expected=current_paths | journal_adds,
                         write_record=False, keep_dirs=journal.get("pre_dirs"),
                         provenance=journal.get("add_provenance"))
        notes += _undo_seed_lines(target, journal.get("seed_lines") or [])
        if the_plan:
            layout_mod.reverse(target, the_plan, journal["backup"])
        _restore_record(target, journal["backup"])
        problems, summary = verify(target, prior)
        if problems:  # the journal stays, so this can be run again
            raise Refusal(EXIT_VERIFY, "rollback did not restore a verifiable workspace", problems)
        _write_state(target)
        os.remove(journal_path(target))
        return prior, summary, "; ".join(["recovered an interrupted %s" % journal.get("op", "operation")]
                                         + notes)

    if not current:
        raise Refusal(EXIT_STATE, "nothing to roll back: no install record and no journal")
    previous = current.get("previous")
    if not previous:
        raise Refusal(EXIT_STATE, "nothing to roll back: this is the first installed release")

    backup_rel = previous.get("backup")
    _require_trusted_snapshot(target, backup_rel, ())  # the path first, before anything is read there
    backup_root = os.path.join(target, backup_rel)
    if not os.path.isdir(backup_root):
        raise Refusal(EXIT_STATE,
                      "the snapshot for %s is gone, so rollback cannot restore it"
                      % previous.get("version"),
                      [backup_root, "re-install the previous release from its pin instead"])
    try:
        snapshot_prior = util.read_json(os.path.join(backup_root, "install.json"))
    except (OSError, ValueError) as exc:
        raise Refusal(EXIT_STATE, "the snapshot's install record can't be read (%s); nothing was changed" % exc)
    _require_trusted_snapshot(target, backup_rel, (current, snapshot_prior))
    after = os.path.join(backup_root, "after.json")
    if os.path.isfile(after) and not os.path.islink(after):
        with open(after, "rb") as fh_after, open(record_path, "rb") as fh_now:
            if fh_after.read() != fh_now.read():
                raise Refusal(EXIT_STATE, "the install record changed since the upgrade wrote it, so rollback "
                              "can't trust it; nothing was changed",
                              ["restore it from git (git checkout -- .aios/install.json), then run rollback "
                               "again"])
    else:
        # Every 3.1 upgrade keeps that copy. Without it, the upgrade was made by an earlier installer, and
        # only the committed record says what it changed: which files to remove, which seed lines to cut.
        # A pull request could have edited it since, so this installer doesn't act on it (independent
        # review, 3.1 rounds 33, 42 and 43). That release's own installer can still roll it back.
        raise Refusal(EXIT_STATE, "this upgrade was made by an installer before 3.1, which kept no copy of the "
                                  "record it wrote, so this installer can't trust the record to say what the "
                                  "upgrade changed; nothing was changed",
                      ["roll it back with that release's own installer, the one in this workspace: "
                       "python3 scripts/aios/aios.py rollback --target .",
                       "or go back with git, from the commit before the upgrade"])
    migration = current.get("layout_migration") or {}
    if migration:
        plan_path = os.path.join(target, migration.get("plan") or "")
        if not os.path.isfile(plan_path):
            raise Refusal(EXIT_STATE, "the folder-move plan for %s is gone, so rollback can't put "
                          "the folders back" % previous.get("version"),
                          [plan_path, "re-install the previous release from its pin instead"])
        blocked = layout_mod.reverse_conflicts(target, util.read_json(plan_path), previous["backup"])
        if blocked:
            raise Refusal(EXIT_STATE, "putting the folders back would overwrite %d file(s)"
                          % len(blocked), sorted(blocked)[:20]
                          + ["those old paths now hold something else: move it aside, then run "
                             "rollback again"])
    # Seeds the upgrade wrote come out too, unless the client has made them their own since.
    prior_record = util.read_json(os.path.join(backup_root, "install.json"))
    created = [e for e in current.get("created_seeds") or []
               if os.path.lexists(os.path.join(target, e["path"]))]
    current_paths = {e["path"] for e in current.get("managed") or []}
    # Before the journal, so any refusal changes nothing.
    _restore_preflight(target, backup_root, prior_record,
                       sorted(current_paths - {e["path"] for e in prior_record.get("managed") or []})
                       + [e["path"] for e in created],
                       expected=current_paths | {e["path"] for e in created})
    if migration:
        moved = util.read_json(os.path.join(target, migration["plan"]))
        linked = _linked_paths(target, _plan_paths(moved, previous["backup"]))
        if linked:
            raise Refusal(EXIT_STATE, "putting the folders back would go through %d link(s) or file(s)"
                          % len(linked), linked[:20] + ["replace them with real folders, then run rollback again"])
    # Written before the first change, so a kill during the rollback itself is recoverable: the
    # next `rollback` reads this and finishes the job (independent review).
    journal = {"op": "rollback", "backup": previous["backup"], "started_at": util.now_iso(),
               "from_version": (current.get("release") or {}).get("version"),
               "to_version": previous.get("version"), "current_record": current, "created": created}
    util.write_json(journal_path(target), journal)
    return _finish_rollback(target, journal)


def _finish_rollback(target, journal, resumed=False):
    """Undo a finished upgrade, from its rollback journal. Every step can be repeated, so a
    rollback killed partway runs again from the start and lands in the same place. The install
    record is written last; the journal goes only after the result verifies."""
    current = journal["current_record"]
    _require_trusted_snapshot(target, journal["backup"], ())  # the path first, before anything is read
    try:
        prior = util.read_json(os.path.join(target, journal["backup"], "install.json"))
    except (OSError, ValueError) as exc:
        raise Refusal(EXIT_STATE, "the snapshot's install record can't be read (%s); nothing was changed" % exc)
    _require_trusted_snapshot(target, journal["backup"], (current, prior),
                              [e.get("path") if isinstance(e, dict) else e for e in journal.get("created") or []])
    backup_root = os.path.join(target, journal["backup"])
    migration = current.get("layout_migration") or {}
    the_plan = util.read_json(os.path.join(target, migration["plan"])) if migration else None
    current_paths = {e["path"] for e in current.get("managed") or []}
    prior_paths = {e["path"] for e in prior.get("managed") or []}
    created = journal.get("created") or []
    remove = sorted(current_paths - prior_paths) + [e["path"] for e in created]
    version = (current.get("release") or {}).get("version")
    if "seed_lines_added" in current:
        # Exactly what that upgrade appended, recorded by it alone: an entry carried in the record from
        # before the upgrade, which a pull request could have written, is never acted on (independent
        # review, 3.1 round 41). The record here is the one the upgrade wrote: it matched that upgrade's
        # own copy before the journal was written (rounds 42 and 43).
        undo = current.get("seed_lines_added") or []
    else:
        # Only a rollback an earlier installer started, killed, and now finished from its own local journal:
        # finished by the rule it began with.
        undo = [e for e in current.get("seed_lines") or [] if e.get("state") == "added" and e.get("release") == version]
    # On every run, a resumed one too, before the first write (independent review, 3.1 round 59).
    _refuse_other_repositories(target, sorted(current_paths | prior_paths) + [e["path"] for e in created]
                               + [e.get("path") for e in undo if isinstance(e, dict)]
                               + (_plan_paths(the_plan, journal["backup"]) if the_plan else []) + _own_paths(target),
                               "the rollback")
    util.fault("rollback.before_restore")
    # A starter file the upgrade created comes out only if it is still exactly what it wrote; one
    # the client has changed (bytes or permissions) or replaced is theirs now (independent review).
    notes = _restore(target, backup_root, prior, remove, expected=current_paths | {e["path"] for e in created},
                     write_record=False, keep_dirs=current.get("pre_existing_dirs"),
                     provenance={e["path"]: [e["sha256"], e.get("mode")] for e in created})
    util.fault("rollback.after_restore")
    notes += _undo_seed_lines(target, undo)
    if the_plan:
        layout_mod.reverse(target, the_plan, journal["backup"])
    util.fault("rollback.after_reverse")
    _restore_record(target, journal["backup"])
    problems, summary = verify(target, prior)
    if problems:  # the journal stays, so this can be run again
        raise Refusal(EXIT_VERIFY, "rollback did not restore a verifiable workspace", problems)
    _write_state(target)
    util.write_json(journal_path(target), dict(journal, phase="complete", completed_at=util.now_iso()))
    how = ("finished an interrupted rollback to %s" if resumed else "rolled back to %s") \
        % prior["release"]["version"]
    return prior, summary, "; ".join([how] + notes)


# ─── adopt ──────────────────────────────────────────────────────────────────

# ─── adopting into an existing instance (3.1, G81) ──────────────────────────
#
# Phoenix, 2026-10-14 (ai-os #532): "safe Starter adoption into FF's existing AIOS with NO
# OVERWRITE. ... Implement approved components/explicit overrides with rehearsal and rollback; do not
# infer existing adoption works already." So: the instance's own plan names every path the release
# ships as adopted, the instance's own, or excluded; nothing is inferred; adoption only ever creates
# files; an existing instance never gets a folder move or a seed line.

ADOPTION_SCHEMA = "ff-aios-starter/adoption@1"
ADOPTION_PLAN = os.path.join(AIOS_DIR, "adoption.json")
ADOPTION_CLASSES = ("adopt", "instance_owned", "exclude")
# Paths no real plan names, in every shape: top level, nested, dotted, with and without an extension.
CATCH_ALL_PROBES = ("aios-probe-7f3a", "aios-probe-7f3a.md", ".aios-probe-7f3a", "aios-probe-7f3a/x",
                    "aios-probe-7f3a/x/y.z", ".aios-probe-7f3a/.x/y")


def ownership_paths(record):
    """The files that say which files are the installer's own: the install record, and after
    `adopt --existing` the plan it names. `instance check` and `start` require them in the founder
    lane (governance.ownership_lane_check; 3.1, owner decision C3)."""
    out = [INSTALL_PATH.replace(os.sep, "/")]
    adoption = record.get("adoption") if isinstance(record, dict) else None
    if isinstance(adoption, dict):
        plan = adoption.get("plan")
        out.append((plan if isinstance(plan, str) and plan else ADOPTION_PLAN).replace(os.sep, "/"))
    return out


def load_adoption_plan(target, rel=None):
    """(plan, sha256) of the instance's own adoption plan: a file the instance commits and owns."""
    rel = (rel or ADOPTION_PLAN).replace(os.sep, "/")
    if not util.safe_relpath(rel):
        raise Refusal(EXIT_STATE, "the adoption plan must be a path inside the workspace: %s" % rel)
    full = os.path.join(target, rel)
    linked = _linked_paths(target, [rel])
    if linked or os.path.islink(full) or not os.path.isfile(full):
        raise Refusal(EXIT_STATE, "no adoption plan at %s" % rel,
                      ["an existing instance names every path the release ships as adopt, "
                       "instance_owned or exclude (docs/INSTALL_AND_UPGRADE.md)"])
    plan = util.read_json_safe(full, "adoption plan")
    problems = _plan_problems(plan)
    if problems:
        raise Refusal(EXIT_STATE, "the adoption plan %s isn't usable" % rel, problems)
    return plan, sha256_file(full)


def _plan_problems(plan):
    """Why a plan can't be used: the wrong schema, a list that isn't paths, or a list that would
    classify every path at once. The same for the plan on disk and a committed one (3.1 round 29)."""
    problems = []
    if not isinstance(plan, dict) or plan.get("schema") != ADOPTION_SCHEMA:
        problems.append("schema is %r, expected %r" % ((plan or {}).get("schema") if isinstance(plan, dict)
                                                      else None, ADOPTION_SCHEMA))
    else:
        for cls in ADOPTION_CLASSES:
            items = plan.get(cls)
            if not isinstance(items, list) or not all(isinstance(x, str) and x.strip() for x in items):
                problems.append("%s must be a list of paths or patterns" % cls)
                continue
            # Judged by what the patterns match, not by how they're spelt (`***`, `?*` and `*` with
            # `*/**` all match everything): a list that covers every kind of path at once is refused.
            if all(util.match_any(items, probe) for probe in CATCH_ALL_PROBES):
                problems.append("%s would classify every path at once (%s); name what it covers "
                                "(independent review, 3.1)" % (cls, ", ".join(repr(i) for i in items[:5])))
    return problems


def classify_adoption(plan, paths):
    """({path: class}, problems). Every path in exactly one list: unlisted or twice-listed refuses."""
    classes, problems = {}, []
    for path in sorted(paths):
        hits = [c for c in ADOPTION_CLASSES if util.match_any(plan.get(c), path)]
        if len(hits) == 1:
            classes[path] = hits[0]
        elif not hits:
            problems.append("%s: not in the plan (adopt it, keep it as the instance's, or exclude it)" % path)
        else:
            problems.append("%s: in more than one list (%s)" % (path, ", ".join(hits)))
    return classes, problems


def _adoption_class(info, path):
    hits = [c for c in ADOPTION_CLASSES if util.match_any((info or {}).get(c), path)]
    return hits[0] if len(hits) == 1 else None


def adopted_view(manifest, classes):
    """The release as an adopted instance has it: only its adopted files, and never a folder move or
    a seed line (an existing instance keeps its own folders and its own CLAUDE.md)."""
    view = json.loads(json.dumps(manifest))
    view["files"] = [e for e in view.get("files") or [] if classes.get(e["path"]) == "adopt"]
    view.pop("layout", None)
    view.pop("seed_lines", None)
    return view


# An adopted instance's install record carries a hash of its own canonical bytes (without this
# field), so rollback can tell whether it is still exactly what was written: the record can't hold
# its own plain hash (independent review, 3.1 round 12).
RECORD_SEAL = "record_sha256"


def _record_bytes(record):
    return (json.dumps(record, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _sealed(record):
    body = {k: v for k, v in record.items() if k != RECORD_SEAL}
    return dict(body, **{RECORD_SEAL: sha256_bytes(_record_bytes(body))})


def _record_sealed(full):
    """Whether an adoption's install record still has the content it was written with: the same
    canonical bytes, and a seal that matches them. Only such a record says which files the adoption
    made (independent review, 3.1 round 22)."""
    try:
        with open(full, "rb") as fh:
            raw = fh.read()
        record = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError):
        return False
    return (isinstance(record, dict) and record.get(RECORD_SEAL) is not None
            and _sealed(record) == record and raw == _record_bytes(record))


def _record_unchanged(full):
    """Whether an adoption's install record is still what it was written as: sealed content, and the
    mode it was written with (0644, written and restored alike)."""
    mode = os.lstat(full).st_mode
    # Written and restored as 0644. Windows keeps no POSIX bits, only read-only, so there it must
    # still be writable (independent review, 3.1 round 13).
    same_mode = stat.S_IMODE(mode) == 0o644 if _EXEC_BITS else bool(mode & stat.S_IWRITE)
    return _record_sealed(full) and same_mode


_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _provenance_ok(entry):
    """A created file's entry as the adoption writes it: a path, its sha256 and its mode. One without
    them can't show the file is still what was made, so it's never removed (3.1 round 22)."""
    return (isinstance(entry, dict) and isinstance(entry.get("path"), str)
            and isinstance(entry.get("sha256"), str) and bool(_HEX64.match(entry["sha256"]))
            and isinstance(entry.get("mode"), int) and not isinstance(entry.get("mode"), bool))


def _config_text(config):
    return (json.dumps(config, indent=2, sort_keys=True) + "\n").encode("utf-8")


def adopt_existing(target, manifest, source_repo, config, plan_rel=None, aios_lookup=None):
    """Adopt an approved release into an instance that already exists: create-only, as its plan says.

    Refuses, with nothing changed, unless every path the release ships is classified exactly once;
    every adopted path is absent and reachable without a link; every path declared the instance's
    exists; the instance has its own role policy (rollback and upgrade read it); and the workspace
    is committed. Journaled before the first write, so `rollback` undoes even a killed adoption.
    """
    # Before the lock, which itself writes: the installer's own paths must be free, or be a guard
    # it left (empty, untracked), so a repository that was never a Starter keeps every file it has.
    if os.path.lexists(install_record_path(target)):
        raise Refusal(EXIT_STATE, "this workspace already has an install record; use upgrade",
                      [install_record_path(target)])
    problems = _reserved_before_adoption(target)
    if problems:
        raise Refusal(EXIT_STATE, "the installer's own paths aren't free in this workspace; nothing was "
                                  "changed", problems)
    # Also before the lock, which creates `.aios` if it's missing and, outside git, its guard in
    # `.aios/backups`: a refusal must leave every folder as it was (independent review, 3.1 round 14).
    if not util.is_git_repo(target):
        raise Refusal(EXIT_STATE, "this isn't a git repository; adopting into an existing instance needs "
                                  "one, so the plan is committed and git gives a second way back")
    if not os.path.isdir(os.path.join(target, AIOS_DIR)):
        raise Refusal(EXIT_STATE, "this instance has no role policy of its own (no %s folder)" % AIOS_DIR,
                      ["write %s first: upgrade and rollback read it, so without it an adoption "
                       "couldn't be rolled back" % roles.POLICY_PATH])
    with _Lock(target, "adopt"):
        return _adopt_existing_locked(target, manifest, source_repo, config, plan_rel, aios_lookup)


def _reserved_before_adoption(target):
    out = []
    # The lock is taken next, inside `.aios`: a link there would put it outside the repository
    # (independent review, 3.1 round 13).
    for rel in _linked_paths(target, [LOCK_PATH.replace(os.sep, "/")]):
        out.append("%s is a link or a file of this repository's own; the installer needs that folder" % rel)
    for rel in (LOCK_PATH, os.path.relpath(journal_path(target), target)):
        rel = rel.replace(os.sep, "/")
        if os.path.lexists(os.path.join(target, rel)):
            if _repo_owned(target, rel):
                out.append("%s is a file this repository tracks; the installer needs that path" % rel)
            else:
                out.append("%s exists: another operation is running, or one was interrupted "
                           "(`aios rollback` clears it)" % rel)
    # The files the Starter's own tools write and keep local (git-ignored): one this repository tracks
    # would be overwritten by the next session (independent review, 3.1 round 55).
    for rel in util.TOOL_LOCAL_FILES:
        if _repo_owned(target, rel):
            out.append("%s is a file this repository tracks; the Starter's tools write that path and keep it "
                       "local" % rel)
    aios = os.path.join(target, AIOS_DIR)
    if os.path.isdir(aios) and not os.path.islink(aios):
        for name in sorted(os.listdir(aios)):
            if _STATE_TEMP.match(name):
                # The names the installer gives its temporary files, which rollback removes (3.1 round 18).
                out.append("%s/%s has a name the installer uses for its temporary files; rename it, or "
                           "run `aios rollback` if an interrupted operation left it" % (AIOS_DIR, name))
    backups = os.path.join(target, BACKUP_DIR)
    if os.path.lexists(backups):
        rel = BACKUP_DIR.replace(os.sep, "/")
        if os.path.islink(backups) or not os.path.isdir(backups):
            out.append("%s is a link or a file of this repository's own; the installer needs that folder" % rel)
        elif os.listdir(backups):
            # The installer's own backups folder holding anything already would mix the repository's
            # files with the installer's records (independent review, 3.1 round 7).
            out.append("%s already holds files of this repository's own; the installer needs that folder "
                       "empty" % rel)
    # Nor another repository there (a submodule, initialized or not): the temporary copies and the state note
    # would be its files (independent review, 3.1 round 58).
    for rel in _linked_paths(target, _INSTALLER_PATHS):
        if not any(o.startswith(rel + " ") for o in out):
            out.append("%s is another repository (a submodule), a link or a file; the installer needs that "
                       "folder as this repository's own" % rel)
    return out


def _adopt_existing_locked(target, manifest, source_repo, config, plan_rel, aios_lookup):
    release_mod.require_consumable(manifest, source_repo, aios_lookup)
    orgconfig.require_valid(config)
    if os.path.lexists(install_record_path(target)):
        raise Refusal(EXIT_STATE, "this workspace already has an install record; use upgrade",
                      [install_record_path(target)])
    if load_journal(target):
        raise Refusal(EXIT_STATE, "a previous operation did not finish; run rollback first",
                      [journal_path(target)])
    if not util.is_git_repo(target):
        raise Refusal(EXIT_STATE, "this isn't a git repository; adopting into an existing instance needs "
                                  "one, so the plan is committed and git gives a second way back")
    if util.worktree_dirty(target):
        raise Refusal(EXIT_STATE, "the workspace has uncommitted git changes; commit them first, so the "
                                  "adoption is one reviewable diff")
    policy_path = os.path.join(target, roles.POLICY_PATH)
    try:
        roles.load_policy(target)
    except Refusal as exc:
        raise Refusal(EXIT_STATE, "this instance has no usable role policy of its own (%s)" % exc.message,
                      ["write %s first: upgrade and rollback read it, so without it an adoption "
                       "couldn't be rolled back" % roles.POLICY_PATH])
    if os.path.islink(policy_path):
        raise Refusal(EXIT_STATE, "%s is a link, not the instance's own file" % roles.POLICY_PATH)
    _require_lifecycle_holder(roles.load_policy(target), config)

    plan_rel = (plan_rel or ADOPTION_PLAN).replace(os.sep, "/")
    plan, plan_sha = load_adoption_plan(target, plan_rel)
    untracked = [rel for rel in (plan_rel, roles.POLICY_PATH.replace(os.sep, "/"))
                 if not util.is_tracked(target, rel)]
    if untracked:
        raise Refusal(EXIT_STATE, "the plan and the role policy must be committed, not just on disk",
                      untracked + ["git add them and commit, then adopt"])
    if util.head_spellings(target, plan_rel) != [plan_rel]:
        # Committed under exactly its own name, or rollback could never find it in the adoption's commit
        # (independent review, 3.1 round 33).
        raise Refusal(EXIT_STATE, "the plan must be committed as %s exactly, and only once" % plan_rel,
                      [", ".join(util.head_spellings(target, plan_rel)) or "not in HEAD",
                       "rename it with git mv, commit, then adopt"])
    entries = {e["path"]: e for e in manifest.get("files") or []}
    classes, problems = classify_adoption(plan, entries)
    if problems:
        raise Refusal(EXIT_STATE, "the adoption plan doesn't classify every path release %s ships exactly "
                      "once" % manifest["version"], problems[:30] + ["%d problem(s) in all" % len(problems)])
    adopt = [entries[p] for p in sorted(entries) if classes[p] == "adopt"]
    seeds = [e["path"] for e in adopt if e.get("class") != "managed"]
    if seeds:
        raise Refusal(EXIT_STATE, "the plan adopts %d seed file(s); a seed is written once and is then the "
                      "instance's, so it can't be kept current" % len(seeds),
                      seeds[:20] + ["exclude them, or copy one in yourself and keep it as instance_owned"])
    if not adopt:
        raise Refusal(EXIT_STATE, "the plan adopts no path release %s ships, so there is nothing to adopt"
                      % manifest["version"])
    present = [e["path"] for e in adopt if os.path.lexists(os.path.join(target, e["path"]))]
    if present:
        raise Refusal(EXIT_STATE, "%d path(s) the plan adopts already exist; adoption never overwrites"
                      % len(present), present[:20] + ["keep them as the instance's (instance_owned) or "
                                                       "exclude them"])
    missing = [p for p in sorted(entries) if classes[p] == "instance_owned"
               and not os.path.lexists(os.path.join(target, p))]
    if missing:
        raise Refusal(EXIT_STATE, "%d path(s) the plan says are the instance's don't exist" % len(missing),
                      missing[:20] + ["adopt them, exclude them, or restore the instance's own file"])
    config_path = orgconfig.default_config_path(target)
    config_rel = os.path.relpath(config_path, target).replace(os.sep, "/")
    config_created = not os.path.lexists(config_path)
    if not config_created:
        same = False
        if os.path.isfile(config_path) and not os.path.islink(config_path):
            try:
                same = util.read_json(config_path) == config
            except (ValueError, OSError, Refusal):
                same = False
        if not same:
            raise Refusal(EXIT_STATE, "this workspace already has a different organization config",
                          [config_path, "adopt with --config pointing at it, or move it aside"])
        if not util.is_tracked(target, config_rel):
            # An ignored or uncommitted people map would never reach the commit, and a fresh clone
            # couldn't tell who may run upgrades or approve the founder lane (independent review, 3.1
            # round 8).
            raise Refusal(EXIT_STATE, "the organization config already here isn't committed",
                          [config_rel, "commit it (it holds references, never secrets), or move it aside"])
    record_rel = os.path.relpath(install_record_path(target), target).replace(os.sep, "/")
    ignored = util.ignored_paths(target, [e["path"] for e in adopt] + [record_rel]
                                 + ([config_rel] if config_created else []))
    if ignored:
        # Written but ignored, it would never reach the commit, and a fresh clone would lack it
        # (independent review, 3.1 round 7).
        raise Refusal(EXIT_STATE, "%d path(s) adoption would create are ignored by this repository's git "
                      "rules" % len(ignored), ignored[:20] + ["un-ignore them, or exclude them in the plan"])
    linked = _linked_paths(target, [e["path"] for e in adopt] + [config_rel, record_rel])
    if linked:
        raise Refusal(EXIT_STATE, "adoption would write through a link, a file in a folder's place, or another "
                      "repository (a submodule, initialized or not)", linked[:20])
    creds = orgconfig.resolve(manifest.get("credentials"), config, target)
    orgconfig.require_resolved(creds)

    info = {
        "plan": plan_rel, "plan_sha256": plan_sha,
        "adopt": plan["adopt"], "instance_owned": plan["instance_owned"], "exclude": plan["exclude"],
        # Each folder this adoption makes, by identity, journaled as it's made: the undo removes only
        # those very folders, and only while they're empty. A folder it can't prove it made stays
        # (independent review, 3.1 rounds 15 and 16).
        "made_dirs": [],
        "created": [],
    }
    journal = {
        "op": "adopt-existing", "phase": "writing", "started_at": util.now_iso(),
        "release_id": manifest["release_id"], "to_version": manifest["version"], "adoption": info,
        # The file being created right now, and its temporary copy: until it's recorded below,
        # rollback removes it only if it's still that very copy (same inode), never a file that
        # merely matches (independent review, 3.1).
        "pending": None,
        # The people map rollback checks the operator against, if a kill comes before it lands.
        # References only: an org config never carries a credential value.
        "config": config if config_created else None,
    }
    util.write_json(journal_path(target), journal)
    util.fault("adopt.after_journal")

    def make_dirs(rel_dir):
        parts = rel_dir.split("/")
        for i in range(1, len(parts) + 1):
            d = "/".join(parts[:i])
            full = os.path.join(target, d)
            if not os.path.lexists(full):
                entry = {"path": d}
                if d == BACKUP_DIR.replace(os.sep, "/"):
                    # The installer's own reserved folder, which adoption needs absent or empty: its
                    # intent is journaled before it's made, so a kill in between can't leave it
                    # (independent review, 3.1 round 17). An instance's folder is removed only by
                    # identity, so one a kill catches in that window is left, empty.
                    entry["reserved"] = True
                    info["made_dirs"].append(entry)
                    util.write_json(journal_path(target), journal)
                os.mkdir(full)
                st = os.lstat(full)
                entry.update(dev=st.st_dev, ino=st.st_ino)
                if not entry.get("reserved"):
                    info["made_dirs"].append(entry)
                util.write_json(journal_path(target), journal)

    def create(rel, data, mode, provenance=True):
        if "/" in rel:
            make_dirs(rel.rsplit("/", 1)[0])

        def pending(tmp):
            journal["pending"] = {"path": rel, "temp": os.path.relpath(tmp, target).replace(os.sep, "/"),
                                  "sha256": sha256_bytes(data), "mode": stat.S_IMODE(os.lstat(tmp).st_mode)}
            util.write_json(journal_path(target), journal)
        # If the link fails, the temporary copy stays with `pending` naming it: the undo below (or a
        # later rollback) removes it and keeps whatever is at `rel` unless it is that very inode, so a
        # file that appeared meanwhile, even with identical bytes, is never taken (independent review,
        # 3.1 rounds 12 and 13).
        tmp = util.create_new(target, rel, data, mode, pending)
        if provenance:
            st = os.lstat(os.path.join(target, rel))
            # The mode as the disk keeps it, so rollback compares like with like on every system.
            info["created"].append({"path": rel, "sha256": sha256_bytes(data),
                                    "mode": stat.S_IMODE(st.st_mode)})
            util.write_json(journal_path(target), journal)
        util.fault("adopt.after_link" if provenance else "adopt.record_after_link")
        # The temporary copy goes before `pending` is cleared, so a kill in between still names it
        # and rollback removes it (independent review, 3.1 round 2).
        os.remove(tmp)
        util.fault("adopt.after_temp" if provenance else "adopt.record_after_temp")
        journal["pending"] = None
        util.write_json(journal_path(target), journal)

    try:
        make_dirs(BACKUP_DIR.replace(os.sep, "/"))  # where the temporary copies are made
        if config_created:  # first, so a rollback after any later kill can tell who is asking
            create(config_rel, _config_text(config), "100644")
        managed, seeded, written = [], [], 0
        for path, _mode, data in util.read_tree(source_repo, manifest["created_from"]["git_rev"]):
            entry = entries.get(path)
            if entry is None or classes[path] != "adopt":
                continue
            if entry["sha256"] != sha256_bytes(data):
                raise Refusal(EXIT_PACKAGE, "content at the pin does not match the manifest: %s" % path)
            create(path, data, entry.get("mode", "100644"))
            written += 1
            if written == 1:
                util.fault("adopt.mid_write")
            rec = {"path": path, "sha256": entry["sha256"]}
            if entry["class"] == "managed":
                rec["exec"] = entry.get("mode") == "100755"
                managed.append(rec)
            else:
                seeded.append(rec)
        bad = [e["path"] for e in adopt if not _same_bytes_and_mode(target, e)]
        if bad:
            raise Refusal(EXIT_VERIFY, "the adopted files did not read back as the release", bad[:20])
        util.fault("adopt.before_record")
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
            "source": os.path.abspath(source_repo),
            "status": "installed",
            "credentials": [{"name": c["name"], "ref": c["ref"], "required": c["required"],
                             "resolved": c["resolved"]} for c in creds],
            "managed": sorted(managed, key=lambda e: e["path"]),
            "seeded": sorted(seeded, key=lambda e: e["path"]),
            "seed_history": sorted(e["path"] for e in seeded),
            "rendered": [],
            "previous": None,
            "adoption": info,
        }
        # Its own entry can't be inside it: rollback knows it by the plan's hash, and by its seal
        # whether it is still what was written.
        record = _sealed(record)
        create(record_rel, _record_bytes(record), "100644", provenance=False)
        # Inside the undo: a state note that can't be written takes the adoption back, never leaves it half
        # done (independent review, 3.1 round 58).
        _write_state(target)
    except Refusal:
        _undo_adoption(target, info, journal.get("pending"))
        if os.path.isfile(journal_path(target)):
            os.remove(journal_path(target))
        raise
    os.remove(journal_path(target))
    require_verified(target, record, "adopted workspace")
    return record


def _require_lifecycle_holder(policy, config):
    """Someone in the people map holds a role the instance's own policy lets both upgrade and roll back:
    otherwise an adoption, or an upgrade of one, could never be rolled back (independent review, 3.1
    rounds 9 and 10)."""
    able = {name for name, role in (policy.get("roles") or {}).items()
            if {"upgrade", "rollback"} <= set(role.get("lifecycle") or [])}
    if not any(p.get("role") in able for p in (config or {}).get("people") or []):
        raise Refusal(EXIT_STATE, "nobody in the people map holds a role the instance's policy lets upgrade "
                      "and roll back", ["give a role in %s the lifecycle actions upgrade and rollback, and "
                                        "someone in the people map that role" % roles.POLICY_PATH])


def _same_bytes_and_mode(target, entry):
    full = os.path.join(target, entry["path"])
    try:
        st = os.lstat(full)
    except OSError:
        return False
    if not stat.S_ISREG(st.st_mode) or sha256_file(full) != entry["sha256"]:
        return False
    return not _EXEC_BITS or bool(st.st_mode & 0o100) == (entry.get("mode") == "100755")


def _reachable(target, rel):
    """A path the undo may act on: inside the workspace, and reached without a link or a file in a
    folder's place. The journal and the record are editable, and a folder may since have been
    replaced by a link out of the repository (independent review, 3.1 round 20)."""
    return bool(rel) and util.safe_relpath(rel) and not _linked_paths(target, [rel])


def _committed_plan(target, rel, rev="HEAD"):
    """The adoption plan as git has it committed (at `rev`), or None: the working tree's copy could say
    anything (independent review, 3.1 round 24)."""
    rel = (rel or ADOPTION_PLAN).replace(os.sep, "/")
    if not util.safe_relpath(rel):
        return None
    text = util.git(target, ["show", "%s:%s" % (rev, rel)], check=False)
    try:
        plan = json.loads(text) if text else None
    except ValueError:
        return None
    if _plan_problems(plan):
        return None
    return plan


def _added_in(target, commit):
    """The paths `commit` added: each one in it that none of its parents has (every path, for a root commit).
    The same rule as _additions, so a merge commit that adds the adoption is read too: `git diff-tree` on a
    merge alone shows nothing, and the undo then took none of its files for the adoption's (independent
    review, 3.1 round 56)."""
    parents = util.git(target, ["rev-list", "--parents", "-n", "1", commit], check=False).split()[1:]
    added = None
    for parent in parents or [None]:
        args = ["diff-tree", "--no-commit-id", "-r", "--no-renames", "--diff-filter=A", "--name-only", "-z"]
        args += [parent, commit] if parent else ["--root", commit]
        out = util.git(target, args, binary=True, check=False)
        paths = {p.decode("utf-8", "surrogateescape") for p in out.split(b"\0") if p}
        added = paths if added is None else added & paths
    return added


def _require_whole_history(target):
    """Refuses in a shallow clone. Git takes the cut-off commit for a root that added every file, so
    when the install record was added, by what, and what changed it since can't be read from such a
    history (independent review, 3.1 rounds 39 and 48)."""
    if util.git(target, ["rev-parse", "--is-shallow-repository"], check=False) == "true":
        raise Refusal(EXIT_STATE, "this clone's history is cut short, so what the install record went "
                                  "through can't be read from it", ["git fetch --unshallow, then run this again"])


def _has_file(target, commit, rel):
    """Whether `rel` is a file in `commit`'s tree."""
    return util.git(target, ["cat-file", "-t", "%s:%s" % (commit, rel)], check=False) == "blob"


def _additions(target, rel):
    """Every commit that added `rel` (the path taken literally), oldest first, on every side of every merge:
    each commit where it is a file and none of its parents has it. A merge commit that adds it, from no
    parent, counts, which `git log --diff-filter=A` misses; a merge that brings it in from a side that
    already had it doesn't (independent review, 3.1 round 54). Refuses in a shallow clone."""
    _require_whole_history(target)
    # --topo-order: an ancestor always before its descendants, whatever dates their authors set.
    out = util.git(target, ["log", "--full-history", "--topo-order", "--reverse", "--format=%H %P", "--",
                            ":(literal)" + rel], check=False)
    found = []
    for line in out.splitlines():
        commit, _, parents = line.partition(" ")
        if commit and _has_file(target, commit, rel) and not any(_has_file(target, q, rel) for q in parents.split()):
            found.append(commit)
    return found


def _vouched_by_note(target):
    """Whether this machine's note of its last operation names exactly the install record on disk."""
    full = os.path.join(target, STATE_PATH)
    try:
        if os.path.islink(full) or not os.path.isfile(full) or _repo_owned(target, STATE_PATH.replace(os.sep, "/")):
            return False
        state = util.read_json(full)
        with open(install_record_path(target), "rb") as fh:
            return isinstance(state, dict) and state.get("record_sha256") == sha256_bytes(fh.read())
    except (OSError, ValueError):
        return False


def _adopted_ownership_problems(target, record, use_note=True):
    """An adopted instance's record calls a file managed, the installer's to update and to remove, only if git
    history shows the installer made it: every commit that ever added it, on any side of any merge (the
    adoption's, or an upgrade's), listed it in the record it committed. Every one, not the first: commit dates
    are an author's to set, so "first" could be a backdated commit on a merged branch (independent review,
    3.1 round 55). The record is committed, so a pull request could add
    one of the repository's own files to `managed`, with the release's hash where its bytes match, and an
    upgrade would then overwrite it or, once a release retires it, delete it. Checked when this machine's note
    doesn't vouch for the record (a fresh clone): with one, the record is the one this machine's last
    operation wrote. A file the repository had before an upgrade created it under the same name is refused
    here too; run that upgrade where the last operation ran (independent review, 3.1 round 54)."""
    if "adoption" not in record or (use_note and _vouched_by_note(target)):
        return []
    record_rel = os.path.relpath(install_record_path(target), target).replace(os.sep, "/")
    # Only the record exactly as committed: one an operation here just wrote, or one not committed yet, is
    # this machine's own local state (and an upgrade refuses uncommitted changes anyway).
    committed_now = util.git(target, ["show", "HEAD:" + record_rel], binary=True, check=False)
    try:
        with open(install_record_path(target), "rb") as fh:
            if not committed_now or fh.read() != committed_now:
                return []
    except OSError:
        return []
    try:
        added = _additions(target, record_rel)
    except Refusal as exc:
        return [exc.message]
    if len(added) != 1:
        return ["the install record was added %d times in this history, so which addition was the adoption "
                "can't be read from it" % len(added)]

    def committed(commit):
        raw = util.git(target, ["show", "%s:%s" % (commit, record_rel)], binary=True, check=False)
        try:
            then = json.loads(raw.decode("utf-8"))
        except ValueError:
            return {}
        return then if isinstance(then, dict) else {}

    def managed_in(then):
        return {e.get("path") for e in then.get("managed") or [] if isinstance(e, dict)}

    problems = []
    for entry in record.get("managed") or []:
        path = entry.get("path") if isinstance(entry, dict) else None
        if not isinstance(path, str):
            continue
        try:
            additions = _additions(target, path)
        except Refusal as exc:
            return problems + [exc.message]
        unlisted = [c for c in additions if path not in managed_in(committed(c))]
        if not additions or unlisted:
            problems.append("%s: the install record calls it the release's, but git history doesn't show the "
                            "installer made it (%s added it without listing it)"
                            % (path, ("commit " + unlisted[0][:12]) if unlisted else "no commit"))
    return problems


def _latest_added(target, rel):
    """The commit that most recently added `rel` (the path taken literally): the start of its current
    lifetime in this history. None if it was never committed. Refuses in a shallow clone. From _additions, so
    an addition made inside a merge commit counts, which `git log --diff-filter=A` misses (independent review,
    3.1 round 55)."""
    added = _additions(target, rel)
    return added[-1] if added else None


def _adoption_anchor(target, journaled=False):
    """(record, plan, commit) of the adoption a rollback undoes, from what can't be edited after the
    fact (independent review, 3.1 rounds 24 to 26): the install record and the plan as committed in the
    commit that most recently added the record, the plan checked against the record's plan_sha256, and
    the record on disk required to be that committed copy. While the record isn't committed yet it is
    local: then the sealed record on disk, with the plan as committed at HEAD, which must be the plan it
    was made with. None when there is no record left to anchor to (an undo that already removed an
    uncommitted one). Refuses, with nothing changed, otherwise."""
    record_rel = os.path.relpath(install_record_path(target), target).replace(os.sep, "/")
    record_full = install_record_path(target)
    present = os.path.lexists(record_full)
    if present and (os.path.islink(record_full) or not os.path.isfile(record_full)):
        # Present but not a file: never taken for "no record" (independent review, 3.1 round 27).
        raise Refusal(EXIT_STATE, "%s isn't the install record (a link or a folder); nothing was changed"
                      % record_rel, ["restore it from git, or move it aside, then run rollback again"])
    if journaled is not False:
        # Resuming: the anchor the first pass journaled (a commit, or None for an uncommitted adoption).
        anchor = journaled
        if anchor is not None and not re.match(r"^[0-9a-f]{40}$", str(anchor)):
            raise Refusal(EXIT_STATE, "the undo's journal names no usable anchor; nothing was changed")
        if anchor is not None:
            _require_whole_history(target)  # what the anchor commit added is read from history
    else:
        # Committed means in HEAD's tree, not merely staged (3.1 round 27), under any spelling a Mac or
        # Windows disk takes for this path; committed under another spelling, it's refused, never read as
        # local (3.1 round 31).
        spellings = util.head_spellings(target, record_rel)
        if spellings and spellings != [record_rel]:
            raise Refusal(EXIT_STATE, "the install record is committed as %s, not just %s; nothing was changed"
                          % (", ".join(spellings), record_rel),
                          ["keep one copy, under its own name (git mv / git rm), commit, then run rollback again"])
        anchor = _latest_added(target, record_rel) if spellings else None
        if spellings and not anchor:
            # Committed, so never read as local state, whose seal and HEAD plan would then be trusted
            # (independent review, 3.1 round 55).
            raise Refusal(EXIT_STATE, "the install record is committed, but no commit in this history adds it, so "
                                      "the adoption can't be read from it; nothing was changed",
                          ["undo it where the adoption ran, or with git"])
    if anchor:
        raw = util.git(target, ["show", "%s:%s" % (anchor, record_rel)], binary=True, check=False)
        try:
            record = json.loads(raw.decode("utf-8"))
        except ValueError:
            record = None
        if not isinstance(record, dict):
            raise Refusal(EXIT_STATE, "the install record committed with the adoption can't be read; nothing "
                                      "was changed", [anchor[:12]])
        if present:
            try:
                with open(record_full, "rb") as fh:
                    on_disk = fh.read()
            except OSError as exc:
                raise Refusal(EXIT_STATE, "the install record can't be read (%s); nothing was changed" % exc)
            if on_disk != raw:
                raise Refusal(EXIT_STATE, "the install record differs from the one committed with the "
                              "adoption, so rollback can't trust which files the adoption made; nothing "
                              "was changed", ["restore it from git (git checkout -- %s), then run rollback "
                                              "again" % record_rel])
        rev = anchor
    else:
        if not present:
            return None
        if not _record_sealed(record_full):
            raise Refusal(EXIT_STATE, "the install record changed since the adoption wrote it, so rollback "
                          "can't trust which files the adoption made; nothing was changed",
                          ["restore it from git (git checkout -- .aios/install.json), then run rollback again"])
        record = util.read_json(record_full)
        rev = "HEAD"
    info = record.get("adoption") or {}
    plan_rel = (info.get("plan") or ADOPTION_PLAN).replace(os.sep, "/")
    blob = util.git(target, ["show", "%s:%s" % (rev, plan_rel)], binary=True, check=False) \
        if util.safe_relpath(plan_rel) else b""
    if not blob or sha256_bytes(blob) != info.get("plan_sha256"):
        raise Refusal(EXIT_STATE, "the adoption plan as committed isn't the one the adoption was made with; "
                                  "nothing was changed",
                      ["restore %s to the version the adoption used, commit it, then run rollback again"
                       % plan_rel])
    plan = _committed_plan(target, plan_rel, rev)
    if plan is None:
        raise Refusal(EXIT_STATE, "the adoption plan the adoption was made with can't be read; nothing was "
                                  "changed", [plan_rel])
    return record, plan, anchor


def _release_adopted(record, plan, source_repo):
    """{path: sha256}: the files the anchored record's pinned release ships, as the release's own source
    confirms, that the anchored plan adopts. Only such a file, with exactly those bytes, can be one a
    finished adoption made (independent review, 3.1 rounds 24 to 26). Refuses, with nothing changed,
    without that proof."""
    rel = record.get("release") or {}
    rev = rel.get("git_rev")
    how = ["run it with the release's source: aios rollback --target . --repo <your ff-aios-starter clone>"]
    if not source_repo:
        raise Refusal(EXIT_STATE, "undoing a finished adoption needs the release it came from, so only that "
                                  "release's files are removed; nothing was changed", how)
    if not rev or not util.rev_exists(source_repo, rev):
        raise Refusal(EXIT_STATE, "the release source doesn't have the pinned commit %s; nothing was changed"
                      % (rev or "?")[:12], how)
    problems = []
    where = _pin_confirmation(source_repo, rel.get("release_id"), rev, problems)
    if where is None or problems:
        raise Refusal(EXIT_STATE, "the release source doesn't confirm this install record's pin; nothing was "
                                  "changed", problems or ["%s has no record of %s" % (source_repo, rel.get("release_id"))])
    shipped = release_mod.select_files(source_repo, rev, release_mod.load_spec(source_repo, rev))
    return {p: s for p, _c, _m, s in shipped if _adoption_class(plan, p) == "adopt"}


def _adopted_lineage(target):
    """(commit, adoption) for the latest commit that added the install record with an adoption in it,
    from git history, which a pull request can only add to; None if no commit ever did. A record that
    was ever committed as an adoption stays one: a later edit can't drop or swap its adoption to get
    the plain upgrade, which writes the whole release (independent review, 3.1 round 39)."""
    record_rel = os.path.relpath(install_record_path(target), target).replace(os.sep, "/")
    if not util.head_spellings(target, record_rel) and not util.git(
            target, ["log", "-1", "--format=%H", "--", ":(literal)" + record_rel], check=False):
        return None
    _require_whole_history(target)
    # Every side of a merge, not only the one git would follow for this path: "ever" includes a branch
    # whose record a merge then set aside (independent review, 3.1 round 48).
    for commit in reversed(_additions(target, record_rel)):
        raw = util.git(target, ["show", "%s:%s" % (commit, record_rel)], binary=True, check=False)
        try:
            added = json.loads(raw.decode("utf-8"))
        except ValueError:
            continue
        if isinstance(added, dict) and isinstance(added.get("adoption"), dict):
            return commit, added["adoption"]
    return None


def _lineage_problem(target, record):
    """(problem, ways forward) if the record's adoption doesn't match git history, else None: a record a
    commit added as an adoption must still say so, naming the same plan, and a committed record can't
    claim an adoption no commit made (independent review, 3.1 rounds 39 and 40)."""
    try:
        lineage = _adopted_lineage(target)
    except Refusal as exc:
        return exc.message, list(exc.details or [])
    info = record.get("adoption")
    back = ["restore the install record's adoption from git, then run this again"]
    if lineage and not isinstance(info, dict):
        return ("this workspace was adopted (commit %s added its install record with the adoption), but the "
                "record doesn't say so any more" % lineage[0][:12]), back
    if lineage and (info.get("plan") or ADOPTION_PLAN) != (lineage[1].get("plan") or ADOPTION_PLAN):
        return ("the install record names another adoption plan than the adoption made (commit %s)"
                % lineage[0][:12]), back
    if info and not lineage and util.in_head(target, os.path.relpath(install_record_path(target), target)):
        return "the install record says this workspace was adopted, but no commit added it as an adoption", back
    return None


def _dropped_seed_lines(target, record):
    """Seed lines this record's history says were handled that it no longer lists: any entry the record
    held when committed, since the commit that began its current lifetime, for a release up to its own.
    No installer drops one (an upgrade carries every entry; a rollback goes back to a record that never
    had the newer release's), so one gone was taken out by an edit, and an upgrade would then append the
    line again where the client removed it. Read from git history, which a pull request can only add to,
    not from what the record says (independent review, 3.1 rounds 43 and 44)."""
    record_rel = os.path.relpath(install_record_path(target), target).replace(os.sep, "/")
    if not util.in_head(target, record_rel):
        return []
    try:
        anchor = _latest_added(target, record_rel)
    except Refusal as exc:
        return [exc.message]  # a shallow clone: what was dropped can't be read
    commits = util.git(target, ["log", "--format=%H", "--", ":(literal)" + record_rel], check=False).split()
    if anchor in commits:
        commits = commits[:commits.index(anchor) + 1]
    current = util.parse_semver((record.get("release") or {}).get("version") or "")
    now = {(e.get("path"), e.get("line")) for e in record.get("seed_lines") or []}
    dropped = set()
    for commit in commits:
        raw = util.git(target, ["show", "%s:%s" % (commit, record_rel)], binary=True, check=False)
        try:
            then = json.loads(raw.decode("utf-8"))
        except ValueError:
            continue
        for e in (then.get("seed_lines") if isinstance(then, dict) else None) or []:
            at = util.parse_semver(e.get("release") or "") if isinstance(e, dict) and isinstance(
                e.get("release"), str) else None
            if at and current and at <= current and (e.get("path"), e.get("line")) not in now:
                dropped.add((str(e.get("path")), str(e.get("line")), commit[:12]))
    return ["%s: the seed line `%s` was recorded (commit %s) but the record no longer lists it" % d
            for d in sorted(dropped)]


def _config_came_with_adoption(target, config_rel, anchor):
    """Whether the org config arrived with the adoption, as git shows it: never committed (so it was
    never the repository's file); or added in the very commit that began the install record's current
    lifetime, and unchanged since, whatever hash a record claims; or, before that commit, only staged
    with it (independent review, 3.1 rounds 24 to 26). A config the repository had before stays."""
    spellings = util.head_spellings(target, config_rel)
    if not spellings:
        return True  # never committed, at most staged: not the repository's committed file (3.1 round 27)
    if spellings != [config_rel] or anchor is None or _latest_added(target, config_rel) != anchor:
        return False  # committed under another spelling too (rounds 31, 32), or not with the adoption
    committed = util.git(target, ["show", "%s:%s" % (anchor, config_rel)], binary=True, check=False)
    try:
        with open(os.path.join(target, config_rel), "rb") as fh:
            return fh.read() == committed
    except OSError:
        return False


def _undo_may_remove(target, info):
    """For an interrupted adoption: the org config it was making, and what the instance's plan, as
    committed at HEAD, says it adopts: the plan it was made with (its hash must match), or nothing is
    removed (independent review, 3.1 rounds 23, 24 and 26). None when the plan can't be read."""
    plan_rel = (info.get("plan") or ADOPTION_PLAN).replace(os.sep, "/")
    blob = util.git(target, ["show", "HEAD:" + plan_rel], binary=True, check=False) \
        if util.safe_relpath(plan_rel) else b""
    if not blob or sha256_bytes(blob) != info.get("plan_sha256"):
        raise Refusal(EXIT_STATE, "the adoption plan as committed isn't the one the interrupted adoption was "
                                  "made with; nothing was changed",
                      ["restore %s to that version, commit it, then run rollback again" % plan_rel])
    plan = _committed_plan(target, plan_rel)
    if plan is None:
        return None
    config_rel = os.path.relpath(orgconfig.default_config_path(target), target).replace(os.sep, "/")
    return lambda rel: rel == config_rel or _adoption_class(plan, rel) == "adopt"


def _pending_ok(pending):
    """The journal's `pending` entry exactly as create() writes it: a path, its sha256 and mode, and a
    temporary copy named as util.private_temp names one, in the backups folder."""
    temp = pending.get("temp") if isinstance(pending, dict) else None
    return (_provenance_ok(pending) and isinstance(temp, str)
            and os.path.dirname(temp) == BACKUP_DIR.replace(os.sep, "/")
            and bool(_COPY_TEMP.match(os.path.basename(temp))))


def _remove_copy_temp(target, rel):
    """Remove an installer temporary copy: a regular file git doesn't track, in its own namespace."""
    full = os.path.join(target, rel)
    try:
        st = os.lstat(full)
    except OSError:
        return
    if stat.S_ISREG(st.st_mode) and not _repo_owned(target, rel):
        os.remove(full)


def _undo_adoption(target, info, pending=None, trusted=None, anchor=None):
    """Take back exactly what an adoption created: the files it recorded, while each is still the
    bytes and mode it wrote, and a file it was creating when killed only if it is still that very
    copy (same inode as its temporary file). Returns notes about anything left. Never removes the
    journal: the caller does, last."""
    notes = []
    created = [c["path"] for c in info.get("created") or [] if _provenance_ok(c)]
    decided = set()
    record_rel = os.path.relpath(install_record_path(target), target).replace(os.sep, "/")
    if trusted is not None:
        # A finished adoption: only the release's own adopted files, with exactly its bytes, and the org
        # config only if git shows it arrived with the adoption.
        config_rel = os.path.relpath(orgconfig.default_config_path(target), target).replace(os.sep, "/")
        config_ok = _config_came_with_adoption(target, config_rel, anchor)
        may_remove = lambda rel: rel in trusted or (rel == config_rel and config_ok)  # noqa: E731
    else:
        may_remove = _undo_may_remove(target, info) or (lambda rel: False)
    if pending:
        # First, the file a kill caught being created, whatever else says about it: removed only if
        # it is still that very copy (the same inode as its temporary file) with the bytes and mode
        # written, or, once the temporary copy has gone, still those bytes and mode. Anything else at
        # that path, edited in place or put there by a replace, is the instance's (independent review,
        # 3.1 rounds 10 to 12).
        if not _pending_ok(pending):
            # The journal is editable: an entry that isn't exactly what create() writes, with its
            # temporary copy in the installer's own namespace, is never acted on (independent review,
            # 3.1 round 23).
            notes.append("an interrupted adoption's journal entry wasn't usable, so it was left alone")
            pending = None
    if pending:
        dest = os.path.join(target, pending["path"])
        tmp = os.path.join(target, pending["temp"])
        decided.add(pending["path"])
        if not (_reachable(target, pending["path"]) and _reachable(target, pending["temp"])):
            notes.append("%s is reached through a link now, so it was left" % pending["path"])
        elif pending["path"] != record_rel and not may_remove(pending["path"]):
            notes.append("%s isn't a path the instance's plan adopts, so it was left" % pending["path"])
            _remove_copy_temp(target, pending["temp"])
        else:
            if os.path.lexists(dest):
                st = os.lstat(dest)
                ours = (stat.S_ISREG(st.st_mode) and sha256_file(dest) == pending.get("sha256")
                        and stat.S_IMODE(st.st_mode) == pending.get("mode")
                        and (not os.path.lexists(tmp) or os.path.samestat(st, os.lstat(tmp))))
                if ours:
                    os.remove(dest)
                    created.append(pending["path"])
                else:
                    notes.append("%s isn't exactly what an interrupted adoption made, so it was left for "
                                 "you" % pending["path"])
            _remove_copy_temp(target, pending["temp"])
    for i, c in enumerate(info.get("created") or []):
        if not _provenance_ok(c):
            notes.append("an entry without a usable hash and mode was left alone: %s"
                         % (c.get("path") if isinstance(c, dict) else c))
        elif c["path"] not in decided and not _reachable(target, c["path"]):
            notes.append("%s is reached through a link now, so it was left" % c["path"])
        elif c["path"] not in decided and not may_remove(c["path"]):
            notes.append("%s isn't a path the instance's plan adopts from the release, so it was left"
                         % c["path"])
        elif c["path"] not in decided and trusted is not None and c["path"] in trusted \
                and c["sha256"] != trusted[c["path"]]:
            notes.append("%s isn't the release's own file, so it was left" % c["path"])
        elif c["path"] not in decided:
            note = _remove_if_ours(target, c["path"], c["sha256"], c.get("mode"))
            if note:
                notes.append(note)
        if i == 0:
            util.fault("adopt.undo_mid")
    record_full = install_record_path(target)
    record_rel = os.path.relpath(record_full, target).replace(os.sep, "/")
    if record_rel not in decided and _reachable(target, record_rel) and os.path.isfile(record_full) \
            and not os.path.islink(record_full):
        # This adoption's record (it names the plan's hash), and only while it is still what was
        # written: one edited since stays, like any file the adoption made (independent review, 3.1
        # round 12).
        try:
            if (util.read_json(record_full).get("adoption") or {}).get("plan_sha256") == info.get("plan_sha256"):
                if _record_unchanged(record_full):
                    os.remove(record_full)
                else:
                    notes.append("%s changed since the adoption wrote it, so it was left for you" % record_rel)
        except (ValueError, OSError):
            notes.append("the install record couldn't be read, so it was left")
    _sweep_temporaries(target)  # before the folders, so a backups folder it made can go too
    state = os.path.join(target, STATE_PATH)
    if _reachable(target, STATE_PATH.replace(os.sep, "/")) and not _state_problems(target):
        if os.path.isfile(state):
            os.remove(state)  # the note of the record this undo removed
        try:
            os.rmdir(os.path.dirname(state))  # its folder, if a kill left it empty or the note is gone
        except OSError:
            pass
    backups_rel = BACKUP_DIR.replace(os.sep, "/")
    for d in sorted(info.get("made_dirs") or [], key=lambda e: -e["path"].count("/")):
        if not isinstance(d, dict) or not isinstance(d.get("path"), str):
            continue
        if not _reachable(target, d["path"] + "/x"):  # the folder itself, and each folder on the way
            continue
        if trusted is not None and d["path"] != backups_rel and not any(
                p.startswith(d["path"] + "/") for p in trusted):
            continue  # a finished adoption's folders are only those on the way to the release's files
        full = os.path.join(target, d["path"])
        try:
            st = os.lstat(full)
            ours = ((st.st_dev, st.st_ino) == (d.get("dev"), d.get("ino"))
                    or (d.get("reserved") and d["path"] == BACKUP_DIR.replace(os.sep, "/") and "dev" not in d))
            if stat.S_ISDIR(st.st_mode) and ours and not os.listdir(full):
                os.rmdir(full)
        except OSError:
            pass
    return notes


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
    # Before the first write, as every operation: no file it pins or writes, and none of the installer's own
    # folders, may sit under a link, a file in a folder's place, or another repository (a submodule, whose
    # files this repository can't commit); verify would refuse it only after the record was written
    # (independent review, 3.1 round 58).
    config_rel = os.path.relpath(orgconfig.default_config_path(target), target).replace(os.sep, "/")
    record_rel = os.path.relpath(install_record_path(target), target).replace(os.sep, "/")
    linked = _linked_paths(target, [e["path"] for e in manifest.get("files") or []]
                           + [config_rel, record_rel] + _INSTALLER_PATHS)
    if linked:
        raise Refusal(EXIT_STATE, "adopt would pin or write files under a link, a file in a folder's place, or "
                      "another repository (a submodule); nothing was changed", linked[:20])

    managed, seeded, mismatches = [], [], []
    for entry in manifest.get("files") or []:
        path = os.path.join(target, entry["path"])
        if entry["class"] == "seed":
            # Every seed, present or not: one the client deleted before adopting is still theirs,
            # and an upgrade must not bring it back (independent review).
            seeded.append({"path": entry["path"], "sha256": sha256_file(path)
                           if os.path.isfile(path) and not os.path.islink(path) else ""})
            continue
        if not os.path.lexists(path):
            mismatches.append("missing: %s" % entry["path"])
            continue
        st = os.lstat(path)
        if not stat.S_ISREG(st.st_mode):
            mismatches.append("not a regular file: %s" % entry["path"])
            continue
        actual = sha256_file(path)
        if actual != entry["sha256"]:
            mismatches.append("differs: %s" % entry["path"])
            continue
        # The bytes are not the whole file: a hook without its executable bit never runs
        # (independent review). Pinned like an install pins it, so verify keeps checking it.
        want_exec = entry.get("mode") == "100755"
        if st.st_mode & 0o7000 or (_EXEC_BITS and bool(st.st_mode & 0o100) != want_exec):
            mismatches.append("permissions differ: %s" % entry["path"])
            continue
        managed.append({"path": entry["path"], "sha256": actual, "exec": want_exec})
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
