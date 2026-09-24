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
    ensure_parent(path)
    # sort_keys so a manifest is byte-stable across runs and machines: a rebuilt release
    # must hash the same, or "reproducible" is a word we do not get to use.
    text = json.dumps(obj, indent=2, sort_keys=True) + "\n"
    # Atomic. Mode "w" truncates before writing, so a kill mid-write left a half-written
    # install record that no recovery path could parse - the crash handler itself crashed.
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    return text


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


def rev_exists(repo, rev):
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
    out = git(path, ["status", "--porcelain", "--untracked-files=all"])
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
    with open(dest, "wb") as fh:
        fh.write(data)
    os.chmod(dest, 0o755 if mode == "100755" else 0o644)
    return sha256_bytes(data)


def now_iso():
    import datetime

    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
    if where != point:
        return
    if kind == "raise":
        raise RuntimeError("injected fault at %s" % point)
    if kind == "crash":
        os._exit(137)


def eprint(msg):
    import sys

    sys.stderr.write(str(msg) + "\n")
