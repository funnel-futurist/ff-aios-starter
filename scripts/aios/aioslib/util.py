"""Shared primitives for the AIOS install contract.

Python 3.9+, standard library only, on purpose: a client workspace must be able to run the
installer on a bare machine with no `pip install` step. The same constraint the PR floor
(`scripts/pr_review/static_checks.mjs`) accepted for Node.

Everything here is deterministic. No network, no clock-dependent behaviour except the
timestamps we deliberately record.
"""

import fnmatch
import hashlib
import json
import os
import re
import subprocess
import tarfile

# ─── Exit codes — the refusal contract ───────────────────────────────────────
# These are part of the interface. Tests assert on them, and so may CI. A refusal must be
# distinguishable from a crash: "it did not install" and "it blew up" are different facts.
EXIT_OK = 0
EXIT_ERROR = 1            # unexpected internal failure
EXIT_PACKAGE = 2          # not approved, not pinned, or content does not match the pin
EXIT_ROLE = 3             # identity/role not permitted
EXIT_CREDENTIAL = 4       # a credential reference is missing, invalid, or a literal value
EXIT_STATE = 5            # dirty, partial, or already-installed target
EXIT_VERIFY = 6           # readback did not match the manifest
EXIT_SANITIZE = 7         # sanitization found something that must not ship
EXIT_GOVERNANCE = 8       # CODEOWNERS / governance check failed

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
FULL_SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


class Refusal(Exception):
    """A deliberate, reported refusal carrying the exit code the CLI must return."""

    def __init__(self, code, message, details=None):
        super(Refusal, self).__init__(message)
        self.code = code
        self.message = message
        self.details = details or []


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path, obj):
    # sort_keys so a manifest is byte-stable across runs and machines: a rebuilt release
    # must hash the same, or "reproducible" is a word we do not get to use.
    text = json.dumps(obj, indent=2, sort_keys=True) + "\n"
    write_bytes(path, text.encode("utf-8"))
    return text


def write_bytes(path, data):
    """Write `data` exactly, atomically. Bytes, never text mode: on Windows text mode turns every LF
    into CRLF, and the installer compares and hashes its records byte for byte (independent review,
    3.1 round 44)."""
    ensure_parent(path)
    # Atomic. Mode "w" truncates before writing, so a kill mid-write left a half-written
    # install record that no recovery path could parse - the crash handler itself crashed.
    # The temporary file is new and uniquely named, never a fixed `<name>.tmp` that something else
    # could already be, or a link that would send the write elsewhere (independent review, 3.1).
    import tempfile

    fd, tmp = tempfile.mkstemp(prefix="." + os.path.basename(path) + ".", suffix=".tmp",
                               dir=os.path.dirname(os.path.abspath(path)))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, 0o644)
        fault("write_json.before_replace")
        os.replace(tmp, path)
    finally:
        if os.path.lexists(tmp):
            os.remove(tmp)


# The installer's own state in a workspace. A release may never ship these paths, and adopting
# into an existing repository refuses while one is already there (independent review, 3.1).
# Each with everything under it: a release path inside a state file's name would make it a folder
# (independent review, 3.1 round 12).
TOOL_RESERVED = (".aios/install.json/**", ".aios/config.json/**", ".aios/txn.json/**", ".aios/lock/**",
                 ".aios/backups/**",
                 # and the names its state writes give their temporary files (3.1 round 18)
                 ".aios/.install.json.*.tmp", ".aios/.config.json.*.tmp", ".aios/.txn.json.*.tmp")


# Files the Starter's own tools write and keep local, git-ignored by the shipped `.aios/.gitignore`: the
# daily release notice's cache and the boundary check's identity cache (independent review, 3.1 round 55).
TOOL_LOCAL_FILES = (".aios/release_notice.json", ".aios/usage/identity.json")


def write_local_cache(root, rel, data):
    """Write one of TOOL_LOCAL_FILES, unless that would touch a file of the repository's: one git tracks or has
    committed, or one reached through a link or that isn't a plain file. Returns whether it wrote. A cache
    not written costs only a repeated check."""
    rel = rel.replace(os.sep, "/")
    try:
        if not _local_cache_path_ok(root, rel):
            return False
        full = os.path.join(root, rel)
        if os.path.lexists(full) and not os.path.isfile(full):
            return False
        write_json(full, data)
        return True
    except (OSError, Refusal):
        return False


def read_local_cache(root, rel):
    """One of TOOL_LOCAL_FILES as a JSON object, or None. Under the same rule as write_local_cache: never a
    file git tracks or has committed, or one reached through a link at any folder on the way (a committed
    link there points the read at a file of the repository's), and never anything but an object. The
    tools that read a cache then never break on it or take its word for anything a pull request wrote
    (independent review, 3.1 round 56)."""
    rel = rel.replace(os.sep, "/")
    try:
        full = os.path.join(root, rel)
        if not _local_cache_path_ok(root, rel) or not os.path.isfile(full):
            return None
        data = read_json(full)
    except (OSError, ValueError, Refusal):
        return None
    return data if isinstance(data, dict) else None


def _local_cache_path_ok(root, rel):
    """Whether `rel` can be this machine's own cache: git neither tracks nor has committed it, no part of the
    path, folders included, is a link, and no folder on the way is another repository (a submodule's file is
    that repository's, which this one's tracking can't see; independent review, 3.1 round 57)."""
    if is_tracked(root, rel) or in_head(root, rel) or inside_another_repository(root, rel):
        return False
    here = root
    for part in rel.split("/"):
        here = os.path.join(here, part)
        if os.path.islink(here):
            return False
    return True


# A Windows short (8.3) name, such as AIOS~1 or INSTAL~1.JSO: it can stand for a long name.
_SHORT_NAME = re.compile(r"^[^.~]{1,6}~[0-9]{1,6}(\.[^.]{0,3})?$")


def path_key(path):
    """A path as a Mac or Windows disk resolves the name: case- and Unicode-folded, with either separator, and
    each part without a stream suffix (`name:stream` names the file itself) or the trailing periods and spaces
    Windows drops."""
    import unicodedata

    key = unicodedata.normalize("NFC", (path or "").replace("\\", "/")).casefold().lstrip("/")
    return "/".join(p.split(":", 1)[0].rstrip(". ") for p in key.split("/"))


def lane_match(patterns, path):
    """match_any for a founder-lane list (a role's paths_denied), with both sides compared as a Mac or Windows
    disk resolves the name (path_key): `.AIOS/Install.json` or `.aios/install.json.` is the lane's
    `.aios/install.json` there. A part that is a short (8.3) name could stand for any long name, so a path with
    one matches whenever the list holds anything (3.1, owner decision C3)."""
    patterns = [p for p in patterns or [] if p]
    if not patterns:
        return False
    key = path_key(path)
    if any(_SHORT_NAME.match(part) for part in key.split("/")):
        return True
    return any(match_pattern(path_key(p), key) for p in patterns)


def is_reserved(path):
    """Whether `path` is, or would be on a Mac or Windows disk, one of the installer's own state paths:
    compared case- and Unicode-folded, with either separator (independent review, 3.1 round 3). As
    Windows resolves a name, a stream suffix (`lock:x`) names the file itself and trailing periods and
    spaces are dropped; and a short name (`AIOS~1`) could be any long name, so a release path with
    one under `.aios` is refused too (independent review, 3.1 round 11)."""
    parts = path_key(path).split("/")
    if len(parts) > 1 and (parts[0] == ".aios" or _SHORT_NAME.match(parts[0])) and any(
            _SHORT_NAME.match(p) for p in parts):
        return True
    return match_any(TOOL_RESERVED, "/".join(parts))


def read_json_safe(path, what="file"):
    """read_json, but a corrupt file is a refusal with a way out, not a stack trace."""
    try:
        return read_json(path)
    except ValueError as exc:
        raise Refusal(
            EXIT_STATE,
            "%s at %s is corrupt and cannot be read (%s)" % (what, path, exc),
            ["this usually means a process was killed mid-write",
             "a snapshot of the last good record is under .aios/backups/"],
        )


def ensure_parent(path):
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)


def parse_semver(version):
    m = SEMVER_RE.match(version or "")
    if not m:
        return None
    return tuple(int(p) for p in m.groups())


def match_pattern(pattern, path):
    """Glob match with `**` meaning "this directory and everything under it"."""
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        return path == prefix or path.startswith(prefix + "/")
    return fnmatch.fnmatchcase(path, pattern)


def match_any(patterns, path):
    return any(match_pattern(p, path) for p in patterns or [])


def safe_relpath(path):
    """Reject anything that could escape the target directory.

    The package is extracted from a git tree, not from user input, but an installer that
    trusts its input is one malicious PR away from writing outside the workspace.
    """
    if not path or path.startswith("/") or path.startswith("\\"):
        return False
    if os.path.isabs(path):
        return False
    parts = path.replace("\\", "/").split("/")
    if any(p in ("..", "") for p in parts):
        return False
    # A colon anywhere: on Windows `D:name` is relative to drive D's current folder (os.path.join keeps
    # it, leaving the workspace), and `name:stream` is a hidden stream of another file. Neither is a path
    # the installer writes, on any system (independent review, 3.1 round 45).
    if any(":" in p for p in parts):
        return False
    if any(p == "." for p in parts):
        return False
    return True


# ─── git access ──────────────────────────────────────────────────────────────

def git(repo, args, binary=False, check=True):
    proc = subprocess.run(
        ["git", "-C", repo] + args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and proc.returncode != 0:
        raise Refusal(
            EXIT_ERROR,
            "git %s failed in %s" % (" ".join(args), repo),
            [proc.stderr.decode("utf-8", "replace").strip()],
        )
    return proc.stdout if binary else proc.stdout.decode("utf-8", "replace").strip()


def _is_option(rev):
    """Whether `rev` would reach git as an option rather than a revision: a release record or manifest names its pin,
    and `--output=<path>` there would make `git archive` write a file before anything refused (independent review,
    3.1 round 63)."""
    return not isinstance(rev, str) or not rev or rev.startswith("-")


def rev_exists(repo, rev):
    if _is_option(rev):
        return False
    proc = subprocess.run(
        ["git", "-C", repo, "cat-file", "-e", rev + "^{commit}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc.returncode == 0


def is_git_repo(path):
    proc = subprocess.run(
        ["git", "-C", path, "rev-parse", "--is-inside-work-tree"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    return proc.returncode == 0 and proc.stdout.decode().strip() == "true"


# Files the install tool itself creates while it works. They are never the operator's change,
# so they never make a workspace "dirty". The lock is the one that matters: an upgrade takes it
# BEFORE checking the worktree, so counting it meant every git-tracked workspace refused its
# own upgrade. Listed here as well as in .aios/.gitignore, because a workspace installed from
# 2.6.0 has the old .gitignore until its first upgrade succeeds.
TOOL_OWNED_PATHS = (".aios/lock",)


def worktree_dirty(path):
    """True when a git worktree has uncommitted changes. False for a non-repo."""
    if not is_git_repo(path):
        return False
    # Without optional locks: a plain status may refresh, and so write, the index (independent review, 3.1 round 62).
    out = git(path, ["--no-optional-locks", "status", "--porcelain", "--untracked-files=all"])
    changes = [line[3:].strip().strip('"') for line in out.splitlines() if line.strip()]
    return any(p not in TOOL_OWNED_PATHS for p in changes)


def read_tree(repo, rev, include_links=False):
    """Yield (path, mode_str, content_bytes) for every regular file in a git tree.

    One `git archive` process rather than one `git show` per file: 268 subprocesses is a
    second of wall clock we pay on every install and every test.

    Links are reported to the caller (mode `120000`/`hardlink`) rather than refused here,
    and refused later only if they are actually *in* the package. Refusing during iteration
    looks safer and is worse: PR #11's pre-push hook does exactly that, and one benign
    tracked symlink anywhere in a repo blocks every push (reproduced 2026-09-21). A link
    under `evidence/` must not be able to veto a release that does not ship it.
    """
    if _is_option(rev):
        raise Refusal(EXIT_PACKAGE, "%r isn't a revision; nothing was read or written" % (rev,))
    proc = subprocess.Popen(
        ["git", "-C", repo, "archive", "--format=tar", rev],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    tf = None
    try:
        tf = tarfile.open(fileobj=proc.stdout, mode="r|")
        for member in tf:
            if member.isdir():
                continue
            if not safe_relpath(member.name):
                raise Refusal(EXIT_PACKAGE, "unsafe path in package tree: %s" % member.name)
            if member.issym() or member.islnk():
                if include_links:
                    yield member.name, "120000", b""
                continue
            if not member.isfile():
                continue
            fh = tf.extractfile(member)
            data = fh.read() if fh is not None else b""
            mode = "100755" if member.mode & 0o111 else "100644"
            yield member.name, mode, data
    finally:
        # Callers legitimately stop early (load_spec breaks on the first hit), so this
        # generator has to clean up after a partial read, not just a full one.
        err = ""
        try:
            if tf is not None:
                tf.close()
        except Exception:
            pass
        for pipe in (proc.stdout, proc.stderr):
            try:
                if pipe is proc.stderr:
                    err = pipe.read().decode("utf-8", "replace").strip()
                pipe.close()
            except Exception:
                pass
        proc.wait()
        # SIGPIPE (-13) is the normal consequence of closing early; only a real failure
        # of a fully-read archive is an error.
        if proc.returncode not in (0, None, -13):
            raise Refusal(EXIT_ERROR, "git archive failed: %s" % err)


def write_file(target_root, relpath, data, mode):
    if not safe_relpath(relpath):
        raise Refusal(EXIT_PACKAGE, "unsafe path refused: %s" % relpath)
    dest = os.path.join(target_root, relpath)
    ensure_parent(dest)
    # A symlink at a managed path makes `open(dest, "wb")` write wherever it points -
    # outside the workspace, if that is where it points. Both review families found this
    # independently; reproduced 2026-09-22 writing a release file to an arbitrary path.
    # os.path.exists() is False for a BROKEN symlink, which is why the collision check
    # upstream missed it too; lexists() sees the link itself.
    if os.path.islink(dest):
        raise Refusal(
            EXIT_STATE,
            "refusing to write through a symlink: %s" % relpath,
            ["a link at a managed path would send the release's file wherever it points",
             "remove the link, then run the operation again"],
        )
    real_root = os.path.realpath(target_root)
    real_parent = os.path.realpath(os.path.dirname(dest))
    if real_parent != real_root and not real_parent.startswith(real_root + os.sep):
        raise Refusal(
            EXIT_STATE,
            "refusing to write outside the workspace: %s resolves to %s" % (relpath, real_parent),
        )
    # All at once: a kill leaves either no file or the whole file, never a half-written one that
    # recovery can't tell from the client's own (independent review). The temporary copy lives in
    # the git-ignored backups folder, so a kill can't leave a stray file in the workspace.
    tmp = private_temp(target_root)
    try:
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, 0o755 if mode == "100755" else 0o644)
        if os.path.islink(dest):  # checked again at the moment of the write
            raise Refusal(EXIT_STATE, "refusing to write through a symlink: %s" % relpath)
        os.replace(tmp, dest)
    finally:
        if os.path.lexists(tmp):
            os.remove(tmp)
    return sha256_bytes(data)


def create_new(target_root, relpath, data, mode, before_link=None):
    """Create `relpath` only if nothing is there, atomically: the whole file appears at once (a
    hard link from a finished temporary copy), and never replaces anything, even something that
    appeared a moment ago. Returns the temporary copy's path, still linked: the caller records the
    new file, then removes it. `before_link(tmp)` runs once the copy is ready (journal it there)."""
    if not safe_relpath(relpath):
        raise Refusal(EXIT_PACKAGE, "unsafe path refused: %s" % relpath)
    dest = os.path.join(target_root, relpath)
    ensure_parent(dest)
    real_root = os.path.realpath(target_root)
    real_parent = os.path.realpath(os.path.dirname(dest))
    if real_parent != real_root and not real_parent.startswith(real_root + os.sep):
        raise Refusal(EXIT_STATE, "refusing to write outside the workspace: %s resolves to %s"
                      % (relpath, real_parent))
    tmp = private_temp(target_root)
    journaled = False
    try:
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, 0o755 if mode == "100755" else 0o644)
        if before_link:
            before_link(tmp)
            # Only once that returned is the journal naming it on disk: if writing it failed, no journal
            # names it, so it goes below (independent review, 3.1 round 14).
            journaled = True
        try:
            os.link(tmp, dest)  # fails if anything is at dest, a link included: never a replace
        except FileExistsError:
            fault("create.link_refused")
            raise Refusal(EXIT_STATE, "%s appeared while this ran; it was not overwritten" % relpath)
        except OSError as exc:
            raise Refusal(EXIT_STATE, "this disk can't create %s without risking a replace (%s)"
                          % (relpath, exc), ["adopting into an existing instance needs a disk with hard links"])
    except BaseException:
        # Removed here only while no journal names it. Once one does, it stays until that journal's
        # rollback removes it, judging `dest` by whether it is this very inode: removing it first would
        # leave a kill in between with a journal that names a copy that's gone, and a file that merely
        # matches would be judged by its bytes (independent review, 3.1 round 13).
        if not journaled and os.path.lexists(tmp) and not (
                os.path.lexists(dest) and os.path.samestat(os.lstat(tmp), os.lstat(dest))):
            os.remove(tmp)
        raise
    return tmp


def ignored_paths(repo, relpaths):
    """Which of `relpaths` this repository's git ignore rules would ignore (none outside git)."""
    if not relpaths or not is_git_repo(repo):
        return []
    proc = subprocess.run(["git", "-C", repo, "check-ignore", "--no-index", "--stdin"],
                          input="\n".join(relpaths).encode("utf-8"),
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return sorted(l for l in proc.stdout.decode("utf-8", "replace").splitlines() if l)


def is_tracked(repo, relpath):
    """Whether git tracks `relpath` in the worktree at `repo`: the path taken literally, never as a
    pattern (`adopt*.json` would match another file), either exactly as git spells it or, on a disk
    that folds case, as a tracked spelling that is the very same file there (independent review, 3.1
    round 19)."""
    rel = relpath.replace(os.sep, "/")
    proc = subprocess.run(["git", "-C", repo, "ls-files", "-z", "--", ":(icase,literal)" + rel],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        return False
    full = os.path.join(repo, rel)
    for raw in proc.stdout.split(b"\0"):
        if not raw:
            continue
        tracked = raw.decode("utf-8", "surrogateescape")
        if tracked == rel:
            return True
        try:
            if os.path.lexists(full) and os.path.samestat(os.lstat(os.path.join(repo, tracked)), os.lstat(full)):
                return True
        except OSError:
            pass
    return False


def fold_path(path):
    """A path as a Mac or Windows disk compares names: case- and Unicode-folded, with `/` between parts."""
    import unicodedata
    return unicodedata.normalize("NFC", path.replace(os.sep, "/")).casefold()


def gitlinks(repo):
    """Every path this repository records as a submodule (a gitlink, mode 160000), in the index or in HEAD,
    initialized or not, each as fold_path gives it (independent review, 3.1 round 57)."""
    out = set()
    for args in (["ls-files", "-s", "-z"], ["ls-tree", "-r", "-z", "HEAD"]):
        proc = subprocess.run(["git", "-C", repo] + args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode != 0:
            continue
        for raw in proc.stdout.split(b"\0"):
            meta, sep, name = raw.partition(b"\t")
            if sep and meta.split()[:1] == [b"160000"]:
                out.add(fold_path(name.decode("utf-8", "surrogateescape")))
    return out


def another_repository(repo, rel_folder, links=None):
    """Whether the folder `rel_folder` is another repository: it holds a `.git` (an initialized submodule, or
    a repository inside this one), or this repository records it as a submodule, initialized or not. Files
    there are that repository's, which this one can't commit and whose tracking its checks can't see."""
    if os.path.lexists(os.path.join(repo, rel_folder, ".git")):
        return True
    return fold_path(rel_folder) in (gitlinks(repo) if links is None else links)


def inside_another_repository(repo, relpath, links=None):
    """The first folder on the way to `relpath` (not `relpath` itself) that is another repository, or None."""
    parts = relpath.replace(os.sep, "/").split("/")
    links = gitlinks(repo) if links is None else links
    for i in range(1, len(parts)):
        if another_repository(repo, "/".join(parts[:i]), links):
            return "/".join(parts[:i])
    return None


def head_spellings(repo, relpath):
    """Every path in the HEAD commit that a Mac or Windows disk would take for `relpath` (each component
    matched case- and Unicode-folded), found by following every equivalent folder, not just the first:
    `.aios/` and `.AIOS/` share one folder there (independent review, 3.1 rounds 31 and 32). Sorted."""
    import unicodedata

    def fold(name):
        return unicodedata.normalize("NFC", name).casefold()

    def entries(tree):
        proc = subprocess.run(["git", "-C", repo, "ls-tree", "-z", tree], stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE)
        if proc.returncode != 0:
            return []
        out = []
        for raw in proc.stdout.split(b"\0"):
            if not raw:
                continue
            meta, _, name = raw.partition(b"\t")
            fields = meta.split()
            out.append((name.decode("utf-8", "surrogateescape"), fields[1].decode(), fields[2].decode()))
        return out

    parts = relpath.replace(os.sep, "/").split("/")
    frontier, found = [("HEAD", [])], []
    for i, part in enumerate(parts):
        last = i == len(parts) - 1
        nxt = []
        for tree, spelled in frontier:
            for name, kind, sha in entries(tree):
                if fold(name) != fold(part):
                    continue
                if last:
                    found.append("/".join(spelled + [name]))
                elif kind == "tree":
                    nxt.append((sha, spelled + [name]))
        frontier = nxt
    return sorted(set(found))


def head_spelling(repo, relpath):
    """HEAD's one spelling of `relpath`, or None if it has none; the exact spelling if it is the only one,
    else the first other: callers that need the exact path refuse anything but [relpath] (round 32)."""
    found = head_spellings(repo, relpath)
    return None if not found else (relpath if found == [relpath] else [f for f in found if f != relpath][0])


def in_head(repo, relpath):
    """Whether `relpath` is in the HEAD commit's tree, committed, not merely staged (independent review,
    3.1 round 27), under any spelling a Mac or Windows disk would take for it (rounds 31 and 32)."""
    return bool(head_spellings(repo, relpath))


def private_temp(target_root):
    """A new, uniquely named, exclusively created regular file in the workspace's git-ignored
    backups folder: never a name something else planted (a link there would redirect the write).
    Same disk as the workspace, so the os.replace that follows is atomic (independent review)."""
    import tempfile

    tmp_dir = os.path.join(target_root, ".aios", "backups")
    for part in (os.path.join(target_root, ".aios"), tmp_dir):
        if os.path.islink(part) or (os.path.lexists(part) and not os.path.isdir(part)):
            raise Refusal(EXIT_STATE, "%s is a link or a file, not a folder" % part)
    # Nor another repository (a submodule, initialized or not): the copy would be that repository's file.
    # Every operation checks this before its first write; this is the last guard (3.1 round 58).
    links = gitlinks(target_root)
    for rel in (".aios", ".aios/backups"):
        if another_repository(target_root, rel, links):
            raise Refusal(EXIT_STATE, "%s is another repository (a submodule), not the installer's folder" % rel)
    os.makedirs(tmp_dir, exist_ok=True)
    fd, path = tempfile.mkstemp(prefix=".write-", dir=tmp_dir)
    os.close(fd)
    return path


def now_iso():
    import datetime

    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


_FAULT_HITS = {}


def fault(point):
    """Deterministic fault injection, used to prove crash recovery.

    `AIOS_FAULT=raise:<point>` raises at that point; `AIOS_FAULT=crash:<point>` exits the
    process hard, skipping every cleanup path, which is how a real kill -9 behaves.

    This can only ever *cause* a failure. There is no code path here that skips a check or
    grants a permission, so it is not a bypass — and rollback that has never been tested
    against a hard kill is a claim, not a capability.
    """
    spec = os.environ.get("AIOS_FAULT", "")
    if not spec or ":" not in spec:
        return
    kind, _, where = spec.partition(":")
    where, _, nth = where.partition("@")  # `<point>@3`: only its third hit in this process
    if where != point:
        return
    if nth:  # without one, every hit, as always
        _FAULT_HITS[point] = _FAULT_HITS.get(point, 0) + 1
        if _FAULT_HITS[point] != int(nth):
            return
    if kind == "raise":
        raise RuntimeError("injected fault at %s" % point)
    if kind == "crash":
        os._exit(137)


def eprint(msg):
    import sys

    sys.stderr.write(str(msg) + "\n")
