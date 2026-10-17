"""Starter 3.1: the static write-site inventory (Chat Zero, review round 60).

Every filesystem write call in the AIOS package, found by reading its source, by the function it's in: a file
opened for writing, os.open with a write flag, mkdir, replace, rename, link, remove, rmdir, chmod, shutil
copies and moves, temporary files, a git command that writes, and calls to the package's own write helpers
(util's and layout's). Each function holding one is classified in WRITES and TABLE below, after review:

- own: the function itself calls the named check for another repository (or the workspace guard, for the
  lock's own files) before its first write;
- callers: every function in the package that calls it does, before the call (followed up the call chain);
- primitive: a util or layout write helper, whose every call is itself a write site classified here;
- allowlist: not part of a workspace's install, adoption, upgrade or rollback, with the reason.

A write call the table doesn't list, or a count that changed, fails until it's reviewed and classified. So
does a check removed from before a write. The dynamic sweep (SubmoduleSweep, in test_adopt_existing_3_1.py)
proves the checks cover the paths; this proves no write runs without one first.
"""

import ast
import collections
import os
import re
import shutil
import tempfile
import unittest

import harness

OS_W = {"makedirs", "mkdir", "rename", "replace", "remove", "unlink", "rmdir", "link", "symlink", "chmod", "write",
        "truncate", "ftruncate", "utime", "removedirs", "renames", "open"}
SH_W = {"rmtree", "copy", "copy2", "copyfile", "copytree", "move", "copymode", "copystat"}
TMP_W = {"mkstemp", "mkdtemp", "NamedTemporaryFile", "TemporaryDirectory"}
PATH_W = {"write_text", "write_bytes", "touch", "mkdir", "unlink", "rmdir", "symlink_to", "hardlink_to", "chmod",
          "lchmod", "link_to"}
_MODE = re.compile(r"^[rwxabtU+]{1,4}([:|][a-z0-9]*)?$")  # with tarfile's suffixes: "w:gz", "r|" (round 64)
_READ_FLAGS = {"O_RDONLY", "O_NOFOLLOW", "O_CLOEXEC", "O_NONBLOCK", "O_DIRECTORY", "O_NOCTTY", "O_BINARY"}


def _read_only_flags(node):
    """Whether os.open's flags are written out as read-only: O_RDONLY, alone or or-ed with flags that can't write."""
    names = [n.attr if isinstance(n, ast.Attribute) else n.id for n in ast.walk(node)
             if isinstance(n, (ast.Attribute, ast.Name)) and not (isinstance(n, ast.Name) and n.id == "os")]
    others = [n for n in ast.walk(node) if not isinstance(n, (ast.Attribute, ast.Name, ast.BinOp, ast.BitOr, ast.Load))]
    return "O_RDONLY" in names and set(names) <= _READ_FLAGS and not others


GIT_WRAPPERS = {"git", "_git"}
GIT_READ = {  # each subcommand that only reads, with the only flags it may carry and still only read
    "rev-parse": {"--abbrev-ref", "--absolute-git-dir", "--is-inside-work-tree", "--is-shallow-repository", "--quiet",
                  "-q", "--verify", "--git-dir", "--show-toplevel", "--short"},
    "ls-files": {"--", "-z", "-s", "--stage", "--error-unmatch", "--cached", "-c"},
    "ls-tree": {"--name-only", "-z", "-r", "-d", "--full-tree"},
    "ls-remote": {"--heads", "--tags", "--refs", "-q", "--quiet"},
    "cat-file": {"-e", "-t", "-p", "-s"},
    "show": {"--format", "--pretty", "--name-only", "--no-patch", "-s"},
    "log": {"--", "--branches", "--format", "--pretty", "--full-history", "--not", "--oneline", "--remotes", "--reverse",
            "--topo-order", "-1", "-n", "--max-count", "--all", "--first-parent", "--diff-filter", "--name-only", "-z"},
    "diff": {"--name-only", "--no-renames", "--name-status", "--stat", "--cached", "--quiet", "--exit-code", "-z"},
    "diff-tree": {"--no-commit-id", "-r", "--root", "--no-renames", "--diff-filter", "--name-only", "-z"},
    "rev-list": {"--count", "--left-right", "--parents", "-n", "--max-count", "--all", "--reverse", "--topo-order"},
    "merge-base": {"--is-ancestor", "--all"},
    "check-ignore": {"--no-index", "--stdin", "-q", "--quiet", "-v", "--verbose", "-z", "-n"},
    "archive": {"--format", "--prefix"},
    "status": {"--porcelain", "--untracked-files", "-z", "--short", "-s", "-b", "--branch"},
    "symbolic-ref": {"--quiet", "-q", "--short"},
    "config": {"--get", "--get-all", "--get-regexp", "--list", "-l", "--local", "--global", "--system", "--type",
               "--bool", "--int", "--null", "-z", "--name-only", "--show-origin", "--default"},
    "remote": {"-v", "--verbose"},
    "stash": {"--stat", "--name-only"},
    "worktree": {"--porcelain", "-z"},
    "notes": set(),
    "branch": {"--list", "-l", "--show-current", "--contains", "-a", "-r", "--all", "--remotes", "--format", "-v"},
    "tag": {"--list", "-l", "--contains", "--points-at", "--format", "--sort"},
}

# The package's own write helpers: a call to one is a write at the call site.
UTIL_W = {"write_file", "write_json", "write_bytes", "ensure_parent", "create_new", "private_temp"}
LAYOUT_W = {"apply", "reverse", "link_probe", "plan", "remove_emptied"}
# The checks for another repository a write may follow (the upgrade's preflight runs _require_state_folder and
# _linked_paths over everything it writes); the lock and the guard count only in LOCK_SCOPE.
GUARDS = {"_upgrade_preflight", "_refuse_other_repositories", "_linked_paths", "_require_state_folder",
          "_reserved_before_adoption",
          "_state_problems", "_restore_preflight", "inside_another_repository", "another_repository",
          "_another_repository", "_local_cache_path_ok"}
LOCK_CLASSES = {"_Lock", "_RecoveryGuard"}


def _modules(root):
    files = [os.path.join(root, "aios.py")] + sorted(
        os.path.join(root, "aioslib", f) for f in os.listdir(os.path.join(root, "aioslib")) if f.endswith(".py"))
    for f in files:
        name = os.path.basename(f)[:-3]
        with open(f) as fh:
            yield name, ast.parse(fh.read(), f)


def _aliases(tree):
    """{local name: module name} for `from . import x as y`, `from aioslib import x`, `import x`."""
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module in (None, "aioslib") or node.level):
            for a in node.names:
                out[a.asname or a.name] = a.name
        elif isinstance(node, ast.Import):
            for a in node.names:
                out[a.asname or a.name] = a.name
    return out


def write_kind(node, alias, mod=None):
    fn = node.func
    if isinstance(fn, ast.Name) and mod == "util" and fn.id in UTIL_W:
        return "util." + fn.id
    if isinstance(fn, ast.Name) and mod == "layout" and fn.id in LAYOUT_W | {"_link_move"}:
        return "layout." + fn.id
    if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name):
        mod, attr = alias.get(fn.value.id, fn.value.id), fn.attr
        if mod == "os" and attr in OS_W:
            if attr == "open" and len(node.args) > 1 and _read_only_flags(node.args[1]):
                return None  # plainly read-only; flags in a variable, or anything else, count (independent review, round 61)
            return "os." + attr
        if mod == "shutil" and attr in SH_W:
            return "shutil." + attr
        if mod == "tempfile" and attr in TMP_W:
            return "tempfile." + attr
        if mod == "util" and attr in UTIL_W:
            return "util." + attr
        if mod == "layout" and attr in LAYOUT_W:
            return "layout." + attr
    if isinstance(fn, ast.Name) and fn.id == "open":
        mode = "r"
        if len(node.args) > 1:
            mode = node.args[1].value if isinstance(node.args[1], ast.Constant) else "?"
        for k in node.keywords:
            if k.arg == "mode":
                mode = k.value.value if isinstance(k.value, ast.Constant) else "?"
        if _unpacked(node):
            mode = "?"  # open(*args), open(f, **kwargs): the mode could be anything (independent review, round 65)
        if mode == "?" or _writes(mode):
            return "open:" + str(mode)
    # pathlib: every method that writes. rename and replace take one argument there, two on str, so a one-argument
    # call counts (independent review, round 61).
    if isinstance(fn, ast.Attribute) and not (isinstance(fn.value, ast.Name) and alias.get(fn.value.id, fn.value.id)
                                              in ("os", "util", "layout", "shutil", "tempfile")):
        if fn.attr in PATH_W:
            return "path." + fn.attr
        if fn.attr in ("rename", "replace") and (
                (len(node.args) == 1 and not node.keywords)
                or (not node.args and [k.arg for k in node.keywords] == ["target"])):
            return "path." + fn.attr
        if fn.attr == "open":
            # Path.open(mode), io.open(file, mode), tarfile.open(..., mode=...): by the mode; when the mode can't be
            # read, or what's opened isn't a file the scanner can tell, it counts (independent review, round 62).
            # The mode is a mode-shaped string among the first two arguments (Path.open("w"), io.open(f, "w")),
            # never a file name read as one (independent review, round 63).
            given = [k.value for k in node.keywords if k.arg == "mode"]
            modes = [a.value for a in node.args[:2] if isinstance(a, ast.Constant) and isinstance(a.value, str)
                     and _MODE.match(a.value)]
            # A writing mode wins; then an argument the scanner can't read, which could hold one ("r" beside a
            # variable could be a file named r); then a reading mode (independent review, round 65).
            if given:
                mode = given[0].value if isinstance(given[0], ast.Constant) else "?"
            elif any(_writes(m) for m in modes):
                mode = "".join(m for m in modes if _writes(m))
            elif _unpacked(node) or any(not isinstance(a, ast.Constant) for a in node.args[:2]):
                mode = "?"
            else:
                mode = "".join(modes) or "r"
            if mode == "?" or _writes(mode):
                return "open:" + str(mode)
    # A git wrapper (util.git, workspace._git): the subcommand comes in its arguments (independent review, round 61).
    called = fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else None
    if called in GIT_WRAPPERS and len(node.args) > 1:
        rest = node.args[1:]
        if isinstance(rest[0], (ast.List, ast.BinOp)):
            words = _words(rest[0])
        elif isinstance(rest[0], ast.Constant):
            words = [_word(a) for a in rest if not isinstance(a, ast.Starred)] + (
                [MORE] if any(isinstance(a, ast.Starred) for a in rest) else [])
        else:
            words = [MORE]
        return git_kind(words)
    return None


def _writes(mode):
    """Whether an open mode writes, judged by its access part only: "r:xz" reads, its "x" naming the compression
    (independent review, round 65)."""
    return any(c in re.split(r"[:|]", str(mode), 1)[0] for c in "wax+")


def _unpacked(call):
    """Whether a call passes *args or **kwargs, whose contents the scanner can't read."""
    return any(isinstance(a, ast.Starred) for a in call.args) or any(k.arg is None for k in call.keywords)


def _word(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


MORE = "<more>"  # more words added that the scanner can't read: any of them could be a flag


def _words(node):
    """The words of a command written as a list, or a list with more added (`[...] + args`): None for a word that is
    an expression (taken as an operand: a path or a revision), and MORE when more words are added."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _words(node.left) + [MORE]
    if isinstance(node, ast.List):
        return [_word(e) for e in node.elts]
    return [MORE]


def git_kind(words):
    """The write a git command makes, or None when it only reads. Fails closed: only a form in GIT_READ is read-only,
    with every flag in its list and no words added that the scanner can't read; anything else counts, a subcommand
    not written out as "git ?" (independent review, rounds 61 and 62)."""
    i, globals_ = 0, []
    while i < len(words) and words[i] not in (None, MORE) and words[i].startswith("-"):
        if words[i] not in ("-C", "--no-optional-locks"):
            return "git ?"  # any other global option, -c among them, can make a reading command write (round 63)
        globals_.append(words[i])
        i += 2 if words[i] == "-C" else 1
    if i >= len(words) or words[i] in (None, MORE):
        return "git ?"
    sub, rest = words[i], words[i + 1:]
    if sub not in GIT_READ or MORE in rest:
        return "git " + sub
    flags = {w.split("=")[0] for w in rest if w is not None and w.startswith("-")}
    operands = [w for w in rest if w is None or not w.startswith("-")]
    allowed, form_ok = GIT_READ[sub], True
    if sub == "status":
        form_ok = "--no-optional-locks" in globals_  # else it may refresh, and write, the index
    elif sub == "symbolic-ref":
        form_ok = len(operands) <= 1
    elif sub == "config":
        form_ok = bool(flags & {"--get", "--get-all", "--get-regexp", "--list", "-l"})
    elif sub == "remote":
        form_ok = not operands or operands[0] in ("get-url", "show")
    elif sub in ("stash", "worktree", "notes"):
        form_ok = bool(operands) and operands[0] in ("list", "show")
    elif sub in ("branch", "tag"):
        form_ok = not operands or bool(flags & {"--list", "-l"})
    return None if form_ok and flags <= allowed else "git " + sub


def _added_to(lst, parent):
    """Whether the list literal `lst` is the left side of a `+` in `parent` (more words follow)."""
    return isinstance(parent, ast.BinOp) and isinstance(parent.op, ast.Add) and parent.left is lst


def scan(root):
    """{"mod:qualname": {"writes": Counter(kind), "first": line, "guards": [(name, line)], "refs": [(target, line)]}}"""
    out = {}
    defs = collections.defaultdict(set)  # module -> qualnames
    trees = list(_modules(root))
    for mod, tree in trees:
        def collect(node, stack):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.ClassDef)):
                    defs[mod].add(".".join(stack + [child.name]))
                    collect(child, stack + [child.name])
        collect(tree, [])
    for mod, tree in trees:
        alias = _aliases(tree)

        def resolve(name, stack, owner=None):
            """The function `name` refers to here, qualified, or None: a method of the enclosing class through
            `self`, a function of another of the package's modules through its import name, or else the nearest
            enclosing definition of that name in this module."""
            if owner == "self":
                cls = next((part for part in reversed(stack) if part.lstrip("_")[:1].isupper()), None)
                q = "%s.%s" % (cls, name)
                return "%s:%s" % (mod, q) if cls and q in defs[mod] else None
            if owner is not None:
                other = alias.get(owner)
                return "%s:%s" % (other, name) if other and name in defs.get(other, ()) else None
            for i in range(len(stack), -1, -1):
                q = ".".join(stack[:i] + [name])
                if q in defs[mod]:
                    return "%s:%s" % (mod, q)
            return None

        def visit(node, stack):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.ClassDef)):
                    visit(child, stack + [child.name])
                    continue
                q = "%s:%s" % (mod, ".".join(stack) or "<module>")
                rec = out.setdefault(q, {"writes": collections.Counter(), "first": None, "guards": [], "refs": []})
                kinds = []
                if isinstance(child, ast.Call):
                    kinds.append(write_kind(child, alias, mod))
                if isinstance(child, ast.List) and child.elts and _word(child.elts[0]) == "git":
                    # A git command written out anywhere (`args = ["git", "clone", ...]`, then run): counted where
                    # it's written, with whatever is added to it unknown (independent review, round 61).
                    kinds.append(git_kind(_words(child)[1:] + ([MORE] if _added_to(child, node) else [])))
                for k in kinds:
                    if k:
                        rec["writes"][k] += 1
                        rec["first"] = child.lineno if rec["first"] is None else min(rec["first"], child.lineno)
                if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
                    if child.id in GUARDS | LOCK_CLASSES:
                        rec["guards"].append((child.id, child.lineno))
                    t = resolve(child.id, stack)
                    if t:
                        rec["refs"].append((t, child.lineno))
                if isinstance(child, ast.Attribute) and isinstance(child.value, ast.Name):
                    if child.attr in GUARDS | LOCK_CLASSES:
                        rec["guards"].append((child.attr, child.lineno))
                    t = resolve(child.attr, stack, child.value.id)
                    if t:
                        rec["refs"].append((t, child.lineno))
                visit(child, stack)
        visit(tree, [])
    return out


WRITES = {
    'aios:cmd_adapters_render': {'open:w': 1},
    'aios:cmd_governance_render': {'open:w': 1, 'util.ensure_parent': 1},
    'aios:cmd_install': {'os.makedirs': 1},
    'aios:cmd_protected_fingerprint': {'util.write_json': 1},
    'aios:cmd_release_build': {'util.write_json': 1},
    'hosting:_get': {'open:?': 1},
    'install:_Lock.__enter__': {'os.open': 1, 'os.write': 1, 'util.ensure_parent': 1},
    'install:_Lock.__exit__': {'os.remove': 1},
    'install:_RecoveryGuard.__enter__': {'os.makedirs': 1, 'os.open': 2},
    'install:_RecoveryGuard.__exit__': {'os.remove': 1},
    'install:_added_in': {'git ?': 1},
    'install:_adopt_existing_locked': {'os.remove': 2, 'util.write_json': 1},
    'install:_adopt_existing_locked.create': {'os.remove': 1, 'util.create_new': 1, 'util.write_json': 2},
    'install:_adopt_existing_locked.create.pending': {'util.write_json': 1},
    'install:_adopt_existing_locked.make_dirs': {'os.mkdir': 1, 'util.write_json': 2},
    'install:_backup': {'os.makedirs': 1, 'os.mkdir': 1, 'shutil.copy2': 1, 'util.ensure_parent': 1, 'util.write_bytes': 1, 'util.write_json': 1},
    'install:_finish_rollback': {'layout.reverse': 1, 'util.write_json': 1},
    'install:_layout_preflight': {'layout.plan': 1},
    'install:_prune_parents': {'os.rmdir': 1},
    'install:_reclaim_stale_lock': {'os.remove': 1},
    'install:_remove_copy_temp': {'os.remove': 1},
    'install:_remove_if_ours': {'os.remove': 1},
    'install:_replace_bytes': {'open:wb': 1, 'os.chmod': 1, 'os.remove': 1, 'os.replace': 1, 'util.private_temp': 1},
    'install:_restore': {'os.remove': 2, 'shutil.copy2': 1, 'util.ensure_parent': 1, 'util.write_bytes': 1, 'util.write_json': 1},
    'install:_restore_record': {'util.write_bytes': 1},
    'install:_rollback_after_reclaim': {'os.remove': 2, 'util.write_json': 2},
    'install:_rollback_locked': {'layout.reverse': 1, 'os.remove': 1, 'util.write_json': 1},
    'install:_sweep_temporaries': {'os.remove': 1},
    'install:_undo_adoption': {'os.remove': 3, 'os.rmdir': 2},
    'install:_upgrade_locked': {'layout.apply': 1, 'layout.remove_emptied': 1, 'layout.reverse': 1, 'os.remove': 3, 'util.write_file': 2, 'util.write_json': 6},
    'install:_write_state': {'util.ensure_parent': 1, 'util.write_json': 1},
    'install:adopt': {'util.write_json': 2},
    'install:install': {'util.write_file': 2, 'util.write_json': 2},
    'layout:_link_move': {'os.link': 1, 'os.makedirs': 1, 'os.unlink': 2},
    'layout:apply': {'layout._link_move': 2, 'layout.remove_emptied': 1, 'os.makedirs': 1},
    'layout:link_probe': {'open:wb': 1, 'os.link': 1, 'os.makedirs': 1, 'os.remove': 2, 'os.rmdir': 1},
    'layout:plan': {'layout.link_probe': 1},
    'layout:remove_emptied': {'os.rmdir': 1},
    'layout:reverse': {'layout._link_move': 2, 'os.makedirs': 1, 'os.rmdir': 1},
    'protected:pin_allowlist': {'open:w': 1},
    'util:create_new': {'open:wb': 1, 'os.chmod': 1, 'os.link': 1, 'os.remove': 1, 'util.ensure_parent': 1, 'util.private_temp': 1},
    'util:ensure_parent': {'os.makedirs': 1},
    'util:git': {'git ?': 1},
    'util:gitlinks': {'git ?': 1},
    'util:private_temp': {'os.makedirs': 1, 'tempfile.mkstemp': 1},
    'util:write_bytes': {'os.chmod': 1, 'os.remove': 1, 'os.replace': 1, 'tempfile.mkstemp': 1, 'util.ensure_parent': 1},
    'util:write_file': {'open:wb': 1, 'os.chmod': 1, 'os.remove': 1, 'os.replace': 1, 'util.ensure_parent': 1, 'util.private_temp': 1},
    'util:write_json': {'util.write_bytes': 1},
    'util:write_local_cache': {'util.write_json': 1},
    'workspace:_copy_kit_settings': {'os.makedirs': 1, 'shutil.copyfile': 1},
    'workspace:_git': {'git ?': 1},
    'workspace:_write_generated': {'open:w': 1, 'util.ensure_parent': 1},
    'workspace:_write_generated_json': {'open:w': 2},
    'workspace:init': {'os.makedirs': 1, 'util.write_json': 1},
    'workspace:move_retired': {'os.makedirs': 1, 'shutil.move': 1},
    'workspace:sync': {'git clone': 1, 'git fetch': 1, 'git merge': 1, 'os.rmdir': 1},
}

_VAULT = ("the multi-repository vault tool (aios workspace init and sync): writes in the vault's own folder, which "
          "holds no install record; not part of a workspace's install, adoption, upgrade or rollback")
_READ_GIT = "runs only read-only git (%s); its command is built in a variable in this function, so the scanner can't read it"
_RELEASE = "release tooling, run in the Starter's own repository: writes the file named with --out"
TABLE = {
    "aios:cmd_adapters_render": ("allowlist", "writes the rendered adapter file to the path given with --out"),
    "aios:cmd_governance_render": ("allowlist", "writes the rendered CODEOWNERS to the path given with --out"),
    "aios:cmd_install": ("allowlist", "makes the workspace folder itself when it doesn't exist; install() then checks "
                                      "every path under it before its first write"),
    "aios:cmd_protected_fingerprint": ("allowlist", _RELEASE),
    "aios:cmd_release_build": ("allowlist", _RELEASE),
    "hosting:_get": ("allowlist", "an HTTP request through urllib's opener (_OPENER.open(req)), not a file; counted "
                                  "because the scanner can't tell what an attribute's open opens"),
    "install:_Lock.__enter__": ("own", "_RecoveryGuard"),
    "install:_Lock.__exit__": ("own", "_RecoveryGuard"),
    "install:_RecoveryGuard.__enter__": ("own", "another_repository"),
    "install:_RecoveryGuard.__exit__": ("allowlist", "removes only the guard file its own __enter__ made, after that "
                                                     "__enter__ refused a .aios or .aios/backups that is another repository"),
    "install:_added_in": ("allowlist", _READ_GIT % "diff-tree"),
    "install:_adopt_existing_locked": ("own", "_linked_paths"),
    "install:_adopt_existing_locked.create": ("callers", None),
    "install:_adopt_existing_locked.create.pending": ("callers", None),
    "install:_adopt_existing_locked.make_dirs": ("callers", None),
    "install:_backup": ("own", "_linked_paths"),
    "install:_finish_rollback": ("own", "_refuse_other_repositories"),
    "install:_layout_preflight": ("callers", None),
    "install:_prune_parents": ("callers", None),
    "install:_reclaim_stale_lock": ("callers", None),
    "install:_remove_copy_temp": ("callers", None),
    "install:_remove_if_ours": ("callers", None),
    "install:_replace_bytes": ("callers", None),
    "install:_restore": ("own", "_restore_preflight"),
    "install:_restore_record": ("callers", None),
    "install:_rollback_after_reclaim": ("own", "_require_state_folder"),
    "install:_rollback_locked": ("own", "_refuse_other_repositories"),
    "install:_sweep_temporaries": ("own", "_linked_paths"),
    "install:_undo_adoption": ("callers", None),
    "install:_upgrade_locked": ("own", "_upgrade_preflight"),
    "install:_write_state": ("own", "_require_state_folder"),
    "install:adopt": ("own", "_linked_paths"),
    "install:install": ("own", "_linked_paths"),
    "layout:_link_move": ("primitive", None),
    "layout:apply": ("primitive", None),
    "layout:link_probe": ("primitive", None),
    "layout:plan": ("primitive", None),
    "layout:remove_emptied": ("primitive", None),
    "layout:reverse": ("primitive", None),
    "protected:pin_allowlist": ("allowlist", "release tooling: writes the protected-text allow-list in the Starter's own "
                                             "repository"),
    "util:create_new": ("primitive", None),
    "util:ensure_parent": ("primitive", None),
    "util:git": ("primitive", None),
    "util:gitlinks": ("allowlist", _READ_GIT % "ls-files -s and ls-tree -r, from a fixed list"),
    "util:private_temp": ("own", "another_repository"),
    "util:write_bytes": ("primitive", None),
    "util:write_file": ("primitive", None),
    "util:write_json": ("primitive", None),
    "util:write_local_cache": ("own", "_local_cache_path_ok"),
    "workspace:_copy_kit_settings": ("allowlist", _VAULT),
    "workspace:_git": ("allowlist", _VAULT),
    "workspace:_write_generated": ("allowlist", _VAULT),
    "workspace:_write_generated_json": ("allowlist", _VAULT),
    "workspace:init": ("allowlist", _VAULT),
    "workspace:move_retired": ("allowlist", _VAULT),
    "workspace:sync": ("allowlist", _VAULT),
}
# The lock's own files: the workspace guard counts as the check for these, and only these (it covers .aios and
# .aios/backups, where the lock and the guard live, not the paths an operation writes).
LOCK_SCOPE = {"install:_Lock.__enter__", "install:_Lock.__exit__", "install:_reclaim_stale_lock"}


def problems(root):
    """Everything wrong with the inventory for the package at `root` (its scripts/aios folder)."""
    found = scan(root)
    writes = {q: dict(r["writes"]) for q, r in found.items() if r["writes"]}
    out = []
    for q in sorted(set(writes) | set(WRITES)):
        if writes.get(q) != WRITES.get(q):
            out.append("%s: writes %r, the inventory says %r (review and classify it)" % (q, writes.get(q), WRITES.get(q)))
        if q in writes and q not in TABLE:
            out.append("%s: not classified" % q)
    callers = collections.defaultdict(list)
    for q, r in found.items():
        for target, line in r["refs"]:
            if target != q:
                callers[target].append((q, line))

    def guarded(q, line, allowed, seen):
        rec = found.get(q)
        if rec is None:
            return False
        if any(name in allowed and at < line for name, at in rec["guards"]):
            return True
        up = [(c, at) for c, at in callers.get(q, ()) if c not in seen]
        if not callers.get(q):
            return False
        return all(guarded(c, at, allowed, seen | {q}) for c, at in up)

    for q, (mode, detail) in sorted(TABLE.items()):
        rec = found.get(q)
        if rec is None or not rec["writes"]:
            out.append("%s: classified, but it writes nothing now (take it out of the inventory)" % q)
            continue
        allowed = GUARDS | (LOCK_CLASSES if q in LOCK_SCOPE else set())
        if mode == "own":
            names = set(detail.split("|"))
            if not any(name in names and at < rec["first"] for name, at in rec["guards"]):
                out.append("%s: no %s before its first write (line %d)" % (q, detail, rec["first"]))
        elif mode == "callers":
            if not guarded(q, rec["first"], allowed, set()):
                out.append("%s: a call chain reaches it with no check for another repository first" % q)
        elif mode == "primitive":
            if q.split(":")[0] not in ("util", "layout"):
                out.append("%s: only util and layout hold write helpers" % q)
        elif mode == "allowlist":
            if not detail:
                out.append("%s: allowlisted without a reason" % q)
        else:
            out.append("%s: unknown mode %r" % (q, mode))
    return out


class WriteSiteInventory(unittest.TestCase):

    ROOT = os.path.join(harness.REPO_ROOT, "scripts", "aios")

    def test_every_write_call_is_classified_and_each_is_reached_only_after_a_check(self):
        self.assertEqual(problems(self.ROOT), [])

    def copy(self):
        tmp = tempfile.mkdtemp(prefix="aios-writesites-")
        self.addCleanup(shutil.rmtree, tmp, True)
        dst = os.path.join(tmp, "aios")
        shutil.copytree(self.ROOT, dst, ignore=shutil.ignore_patterns("__pycache__"))
        return dst

    def test_control_a_removed_check_fails(self):
        dst = self.copy()
        path = os.path.join(dst, "aioslib", "install.py")
        with open(path) as fh:
            text = fh.read()
        tree = ast.parse(text)
        fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_finish_rollback")
        call = next(n for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                    and n.func.id == "_refuse_other_repositories")
        lines = text.split("\n")
        indent = re.match(r"\s*", lines[call.lineno - 1]).group(0)
        lines[call.lineno - 1:call.end_lineno] = [indent + "pass"]
        with open(path, "w") as fh:
            fh.write("\n".join(lines))
        self.assertEqual([p.split(" (line")[0] for p in problems(dst)],
                         ["install:_finish_rollback: no _refuse_other_repositories before its first write"])

    def test_control_a_new_write_call_fails_closed(self):
        dst = self.copy()
        with open(os.path.join(dst, "aioslib", "layout.py"), "a") as fh:
            fh.write("\n\ndef _new_writer(path, flags):\n"
                     "    with open(path, \"w\") as fh:\n        fh.write(\"x\")\n"
                     "    import pathlib\n    pathlib.Path(path).unlink()\n    pathlib.Path(path).replace(path + \"~\")\n"
                     "    pathlib.Path(path).open(\"w\").close()\n"
                     "    pathlib.Path(path).open(mode=\"a\").close()\n"
                     "    pathlib.Path(path).rename(target=path + \"1\")\n"
                     "    pathlib.Path(path).replace(target=path + \"2\")\n"
                     "    pathlib.Path(path).open().close()\n"  # read: not counted
                     "    import io\n    io.open(path, \"w\").close()\n"  # a file name first, the mode second
                     "    io.open(\"rw.txt\").close()\n"  # a file name alone: read
                     "    import tarfile\n    tarfile.open(\"a.tar.gz\", \"w:gz\").close()\n"  # a mode with a suffix
                     "    tarfile.open(\"b.tar\", \"r|\").close()\n"  # read
                     "    tarfile.open(\"c.tar.xz\", \"r:xz\").close()\n"  # read: its x is the compression
                     "    io.open(\"r\", flags).close()\n"  # a constant beside a variable: counted
                     "    open(*[path, \"w\"]).close()\n"  # unpacked arguments: counted
                     "    open(path, **{\"mode\": \"w\"}).close()\n"
                     "    os.close(os.open(path, flags))\n"  # flags in a variable: counted
                     "    os.close(os.open(path, os.O_RDONLY))\n"  # plainly read-only: not
                     "    return \"a\".replace(\"a\", \"b\")\n")  # str.replace: not
        found = problems(dst)
        self.assertIn("layout:_new_writer: not classified", found)
        self.assertIn("layout:_new_writer: writes {'open:w': 3, 'path.unlink': 1, 'path.replace': 2, 'open:a': 1, "
                      "'path.rename': 1, 'open:w:gz': 1, 'open:?': 3, 'os.open': 1}", "\n".join(found))

    def test_control_a_git_write_through_a_wrapper_fails_closed(self):
        dst = self.copy()
        with open(os.path.join(dst, "aioslib", "workspace.py"), "a") as fh:
            fh.write("\n\ndef _new_git_writer(path, args):\n"
                     "    _git(path, \"commit\", \"-qm\", \"x\")\n"         # the vault's wrapper: counted
                     "    util.git(path, [\"update-index\", \"--add\", \"x\"])\n"  # util's wrapper: counted
                     "    cmd = [\"git\", \"-C\", path, \"tag\", \"v1\"]\n"       # a command built first: counted
                     "    _run(cmd)\n"
                     "    util.git(path, args)\n"                         # a subcommand not written out: counted
                     "    _git(path, \"rev-parse\", \"HEAD\")\n"            # read-only: not
                     "    _git(path, \"config\", \"--get\", \"user.name\")\n"  # read-only form: not
                     "    _git(path, \"--no-optional-locks\", \"status\", \"--porcelain\")\n"  # read: not
                     "    _git(path, \"symbolic-ref\", \"--short\", \"HEAD\")\n"  # read: not
                     "    _git(path, \"archive\", \"--output=a.tar\", \"HEAD\")\n"  # a read subcommand writing a file
                     "    _git(path, \"diff\", \"--output=d.patch\")\n"
                     "    _git(path, \"symbolic-ref\", \"--delete\", \"HEAD\")\n"
                     "    _git(path, \"status\", \"--porcelain\")\n"  # may refresh, and write, the index
                     "    _run([\"git\", \"-C\", path, \"log\"] + args)\n"  # words added it can't read
                     "    _run([\"git\", \"-c\", \"diff.external=w\", \"diff\"])\n")  # a global option: counted
        found = "\n".join(problems(dst))
        self.assertIn("workspace:_new_git_writer: writes {'git commit': 1, 'git update-index': 1, 'git tag': 1, "
                      "'git ?': 2, 'git archive': 1, 'git diff': 1, 'git symbolic-ref': 1, 'git status': 1, "
                      "'git log': 1}", found)


if __name__ == "__main__":
    unittest.main()


class RuntimeAuditHook(unittest.TestCase):
    """audit_writes.parse reads a write on a file descriptor too (independent review, round 63), and judges a mode by
    its access part (round 65)."""

    def test_a_mode_is_judged_by_its_access_part(self):
        import audit_writes
        self.assertEqual(audit_writes.parse("open", ("f.tar.xz", "r:xz", 0)), [])
        self.assertEqual(len(audit_writes.parse("open", ("f.tar.gz", "w:gz", 0))), 1)

    def test_an_open_on_a_descriptor_counts(self):
        import audit_writes
        tmp = tempfile.mkdtemp(prefix="aios-auditfd-")
        self.addCleanup(shutil.rmtree, tmp, True)
        path = os.path.join(tmp, "f")
        fd = os.open(path, os.O_WRONLY | os.O_CREAT)
        try:
            with audit_writes.Recording() as rec:
                os.fdopen(os.dup(fd), "w").close()
        finally:
            os.close(fd)
        self.assertIn(("f", False), rec.under(tmp))


class RuntimeAuditCheck(unittest.TestCase):
    """The integration test's runtime checks (audit_check.py, over the log audit_site/sitecustomize.py writes) each
    fail on the violation they look for (Chat Zero, review round 63)."""

    def test_control_each_check_fails_on_its_violation(self):
        import json
        import subprocess
        import sys
        tmp = tempfile.mkdtemp(prefix="aios-auditcheck-")
        self.addCleanup(shutil.rmtree, tmp, True)
        work, source = os.path.join(tmp, "work"), os.path.join(tmp, "work", "source")
        os.makedirs(os.path.join(source, ".git"))
        rows = [{"kind": "open", "path": os.path.join(work, "workspace", "f%d" % i), "folder": False, "pid": 1,
                 "cmd": ["upgrade"]} for i in range(60)]
        rows += [{"git": ["git", "-C", work, "rev-parse", "HEAD"], "cwd": work, "pid": 1, "cmd": ["upgrade"]}] * 11
        rows += [{"kind": "open", "path": "/elsewhere/x", "folder": False, "pid": 1, "cmd": ["upgrade"]},
                 {"kind": "os.remove", "path": os.path.join(work, "workspace", ".git", "index"), "folder": False,
                  "pid": 1, "cmd": ["upgrade"]},
                 {"kind": "open", "path": os.path.join(source, "x.md"), "folder": False, "pid": 1, "cmd": ["upgrade"]},
                 {"git": ["git", "-C", work, "commit", "-m", "x"], "cwd": work, "pid": 1, "cmd": ["upgrade"]}]
        log = os.path.join(tmp, "audit.jsonl")
        with open(log, "w") as fh:
            fh.write("".join(json.dumps(r) + "\n" for r in rows))
        out = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "audit_check.py"),
                              log, work, source], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             universal_newlines=True).stdout
        verdicts = [l.split("  ", 1)[0] for l in out.splitlines() if l.startswith(("PASS", "FAIL"))]
        self.assertEqual(verdicts, ["PASS", "FAIL", "FAIL", "FAIL", "FAIL"], out)
