"""The Workspace Kit: one Obsidian vault over separate, authorized Git repositories.

Obsidian reads ordinary local files. A vault is a folder, not an account, so the basic
experience needs no API key, no Publish subscription and no community plugin. This module
builds that folder safely:

    <parent>/                    not a Git repository, and never becomes one
      .obsidian/                 vetted core-plugin defaults, no secrets, no community plugins
      WORKSPACE.json             the manifest: names -> repository URLs, branches, states
      START-HERE.md              the entry page
      00-MAPS/                   generated maps, labelled generated, with source revisions
      aios/  creation/  ...      independent Git checkouts, each with its own history

What it promises, stated so nobody has to discover it:

* It only clones what the manifest marks `active` and what this machine can already read.
  An unreadable repository is reported as not connected; the rest still set up.
* It never resets, stashes, force-pushes or rewrites a checkout. A dirty, diverged or
  off-branch checkout is left exactly as it is, with the next action written down. A clean
  checkout that is simply behind moves forward with `--ff-only`, which cannot lose work.
* Generated maps are disposable. If someone edited one, the edit is kept and the fresh map
  is written beside it as `<name>.new.md` instead.
* Hiding a file in Obsidian is not access control. The kit keeps private material out by
  never cloning it; the manifest refuses a URL that carries a credential.
"""

import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
from urllib.parse import unquote

from . import util
from .util import EXIT_OK, EXIT_PACKAGE, EXIT_STATE, Refusal

SCHEMA = "ff-aios-starter/workspace@1"
KIT_VERSION = "1"
MANIFEST_NAME = "WORKSPACE.json"
MAPS_DIR = "00-MAPS"
START_HERE = "START-HERE.md"
STATES = ("active", "inactive", "reference")
DOMAINS = ("aios", "creation", "team-ops", "command-os", "revops", "attention", "other")
# Where each domain sits on the Operating System canvas: AIOS on top as company context, the
# operating domains in the middle, Command OS below as visibility.
ROWS = {"aios": 0, "creation": 1, "team-ops": 1, "revops": 1, "attention": 1, "other": 1,
        "command-os": 2}
EDGE_LABELS = ("context", "asset reference", "capability call", "client-specific output",
               "operational data")

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
CRED_REF_RE = re.compile(r"^(env|dotenv):([A-Z][A-Z0-9_]*)$")
# https://user:secret@host/... or https://token@host/... Both put a credential in a file.
URL_CREDENTIAL_RE = re.compile(r"^[a-z][a-z0-9+.-]*://[^/@\s]+@", re.I)
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
OVERSIZED_BYTES = 200 * 1024
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".next",
             "coverage", ".obsidian"}

KIT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..",
                       "templates", "workspace-kit")


# ---------------------------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------------------------

def validate(manifest):
    """A list of problems. Never echoes what looks like a credential."""
    problems = []
    if manifest.get("schema") != SCHEMA:
        problems.append("schema is %r, expected %r" % (manifest.get("schema"), SCHEMA))
    repos = manifest.get("repos")
    if not isinstance(repos, dict) or not repos:
        return problems + ["the manifest lists no repositories"]
    paths = {}
    for name, spec in sorted(repos.items()):
        if not NAME_RE.match(name):
            problems.append("repository name %r is not a lowercase slug" % name)
        if not isinstance(spec, dict):
            problems.append("%s: not an object" % name)
            continue
        url = spec.get("url") or ""
        if not url:
            problems.append("%s: no url" % name)
        elif URL_CREDENTIAL_RE.match(url):
            problems.append("%s: the url carries a credential. Use a plain URL; git reads your "
                            "sign-in from gh or your credential helper" % name)
        if spec.get("state") not in STATES:
            problems.append("%s: state %r is not one of %s" % (name, spec.get("state"),
                                                              ", ".join(STATES)))
        if spec.get("domain") not in DOMAINS:
            problems.append("%s: domain %r is not one of %s" % (name, spec.get("domain"),
                                                               ", ".join(DOMAINS)))
        path = spec.get("path") or name
        if path in (MAPS_DIR, ".obsidian", MANIFEST_NAME, START_HERE) or \
                not re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]*$", path):
            problems.append("%s: path %r must be one plain folder name inside the workspace"
                            % (name, path))
        elif path in paths:
            problems.append("%s: path %r is already used by %s" % (name, path, paths[path]))
        paths[path] = name
        ref = spec.get("credential_ref")
        if ref is not None and not CRED_REF_RE.match(str(ref)):
            problems.append("%s: credential_ref must be a reference like env:GITHUB_TOKEN, "
                            "never a value" % name)
        start = spec.get("start_page")
        if start is not None and not util.safe_relpath(start):
            problems.append("%s: start_page %r is not a path inside the repository"
                            % (name, start))
    for cap in manifest.get("capabilities") or []:
        if not cap.get("name"):
            problems.append("a capability has no name")
    return problems


def load(parent):
    path = os.path.join(parent, MANIFEST_NAME)
    if not os.path.isfile(path):
        raise Refusal(EXIT_STATE, "%s is not a workspace: it has no %s" % (parent, MANIFEST_NAME),
                      ["run `aios workspace init --manifest <file> --parent %s` first" % parent])
    manifest = util.read_json(path)
    problems = validate(manifest)
    if problems:
        raise Refusal(EXIT_PACKAGE, "%s is not a valid workspace manifest" % path, problems)
    return manifest


def _repos(manifest):
    for name, spec in sorted(manifest["repos"].items(),
                             key=lambda kv: (ROWS.get(kv[1].get("domain"), 1), kv[0])):
        yield name, dict(spec, path=spec.get("path") or name, branch=spec.get("branch") or "main")


# ---------------------------------------------------------------------------------------------
# Git, without ever prompting and without ever touching work
# ---------------------------------------------------------------------------------------------

def _run(args, cwd=None, timeout=120):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")
    try:
        proc = subprocess.run(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              env=env, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, "", str(exc)
    return (proc.returncode, proc.stdout.decode("utf-8", "replace").strip(),
            proc.stderr.decode("utf-8", "replace").strip())


def _git(path, *args, timeout=120):
    return _run(["git", "-C", path] + list(args), timeout=timeout)


def can_read(url, timeout=30):
    """True when this machine can already read the repository. Nothing is stored."""
    code, _out, _err = _run(["git", "ls-remote", "--heads", url], timeout=timeout)
    return code == 0


def inside_git_repo(path):
    """True when `path`, or the nearest existing folder above it, is inside a Git worktree."""
    probe = os.path.abspath(path)
    while not os.path.isdir(probe):
        parent = os.path.dirname(probe)
        if parent == probe:
            return False
        probe = parent
    return util.is_git_repo(probe)


def checkout_state(path, branch):
    """(state, detail, revision) for one checkout, read-only except for `git fetch`."""
    if not os.path.exists(path):
        return "missing", "not cloned yet", None
    if not os.path.isdir(os.path.join(path, ".git")) and not os.path.isfile(
            os.path.join(path, ".git")):
        return "not-git", "the folder exists but is not a Git checkout", None
    code, rev, _ = _git(path, "rev-parse", "HEAD")
    rev = rev if code == 0 else None
    if util.worktree_dirty(path):
        return "dirty", "has uncommitted changes", rev
    code, current, _ = _git(path, "symbolic-ref", "--quiet", "--short", "HEAD")
    if code != 0:
        return "detached", "is not on a branch", rev
    if current != branch:
        return "other-branch", "is on %s, the manifest expects %s" % (current, branch), rev
    code, counts, _ = _git(path, "rev-list", "--left-right", "--count",
                           "HEAD...refs/remotes/origin/%s" % branch)
    if code != 0:
        return "clean", "clean (no remote-tracking branch to compare)", rev
    ahead, behind = (int(x) for x in counts.split())
    if ahead and behind:
        return "diverged", "%d local and %d remote commits differ" % (ahead, behind), rev
    if behind:
        return "behind", "%d commit(s) behind origin/%s" % (behind, branch), rev
    if ahead:
        return "ahead", "%d local commit(s) not pushed" % ahead, rev
    return "clean", "up to date", rev


NEXT_ACTION = {
    "dirty": "Open a terminal in {path}, then commit your changes (or move them to a branch). "
             "Run `aios workspace sync` again afterwards. Nothing was changed.",
    "diverged": "Your copy and GitHub both have new commits. In {path}, run `git pull` and "
                "resolve it, or ask for help. Nothing was changed.",
    "other-branch": "{path} is on another branch. Switch back with `git switch {branch}` when "
                    "you are ready. Nothing was changed.",
    "detached": "{path} is not on a branch. Run `git switch {branch}`. Nothing was changed.",
    "not-git": "{path} exists but is not a Git checkout. Move it aside, then sync again. "
               "Nothing was changed.",
    "ahead": "{path} has commits that are not on GitHub yet. Push them when they are ready.",
    "unavailable": "This computer cannot read {url}. Sign in with `gh auth login` as someone "
                   "who has access, or ask an owner to grant it. The rest of the workspace "
                   "still works.",
}


# ---------------------------------------------------------------------------------------------
# Plan, init, sync
# ---------------------------------------------------------------------------------------------

def plan(manifest, parent, check_remote=True):
    """What sync would do, without doing it. One row per repository."""
    rows = []
    for name, spec in _repos(manifest):
        local = os.path.join(parent, spec["path"])
        row = {"name": name, "domain": spec["domain"], "state": spec["state"],
               "path": spec["path"], "branch": spec["branch"], "url": spec["url"]}
        if spec["state"] != "active":
            row.update(local="-", action="show as %s; nothing is cloned" % spec["state"])
        else:
            local_state, detail, rev = checkout_state(local, spec["branch"])
            row.update(local=local_state, detail=detail, revision=rev)
            if local_state == "missing":
                readable = can_read(spec["url"]) if check_remote else None
                row["readable"] = readable
                row["action"] = ("clone %s into %s" % (spec["url"], spec["path"])
                                 if readable is not False else "report as not connected")
            elif local_state in ("clean", "behind"):
                row["action"] = "fetch; fast-forward only if behind"
            else:
                row["action"] = "leave untouched"
        rows.append(row)
    return rows


def _copy_kit_settings(parent):
    """Add the baseline .obsidian files that are missing. Existing settings are the owner's."""
    src = os.path.join(KIT_DIR, "obsidian")
    dst = os.path.join(parent, ".obsidian")
    os.makedirs(dst, exist_ok=True)
    written = []
    for name in sorted(os.listdir(src)):
        target = os.path.join(dst, name)
        if not os.path.exists(target):
            shutil.copyfile(os.path.join(src, name), target)
            written.append(name)
    return written


def init(manifest, parent, clone_filter=None, now=None):
    problems = validate(manifest)
    if problems:
        raise Refusal(EXIT_PACKAGE, "the workspace manifest is not valid", problems)
    parent = os.path.abspath(parent)
    if inside_git_repo(parent):
        raise Refusal(EXIT_STATE, "%s is inside a Git repository" % parent, [
            "the workspace folder must not be a combined Git repository: each child keeps its "
            "own history. Choose a folder outside any repository, for example "
            "~/Documents/<Company>-Operating-System"])
    if os.path.isdir(parent) and os.listdir(parent) and \
            not os.path.isfile(os.path.join(parent, MANIFEST_NAME)):
        raise Refusal(EXIT_STATE, "%s already has files and is not a workspace" % parent,
                      ["choose an empty or new folder; nothing was changed"])
    existing = os.path.join(parent, MANIFEST_NAME)
    if os.path.isfile(existing) and util.read_json(existing) != manifest:
        raise Refusal(EXIT_STATE, "%s already has a different %s" % (parent, MANIFEST_NAME),
                      ["edit that file and run `aios workspace sync` instead; nothing was changed"])
    os.makedirs(parent, exist_ok=True)
    util.write_json(existing, manifest)
    settings = _copy_kit_settings(parent)
    report = sync(parent, clone_filter=clone_filter, now=now)
    report["settings_written"] = settings
    return report


def sync(parent, clone_filter=None, now=None):
    """Clone newly active repositories, move clean ones forward, leave everything else alone."""
    parent = os.path.abspath(parent)
    manifest = load(parent)
    results = []
    for name, spec in _repos(manifest):
        local = os.path.join(parent, spec["path"])
        res = {"name": name, "domain": spec["domain"], "state": spec["state"],
               "path": spec["path"], "branch": spec["branch"]}
        if spec["state"] != "active":
            res.update(status="not active" if spec["state"] == "inactive" else "reference",
                       revision=None)
            results.append(res)
            continue
        local_state, detail, rev = checkout_state(local, spec["branch"])
        if local_state == "missing":
            if not can_read(spec["url"]):
                res.update(status="not connected", revision=None,
                           next=NEXT_ACTION["unavailable"].format(url=spec["url"]))
                results.append(res)
                continue
            args = ["git", "clone", "--branch", spec["branch"]]
            if clone_filter:
                args += ["--filter=%s" % clone_filter]
            code, _o, err = _run(args + [spec["url"], local], timeout=3600)
            if code != 0:
                res.update(status="error", revision=None, detail=err.splitlines()[-1:] or [""],
                           next=NEXT_ACTION["unavailable"].format(url=spec["url"]))
                if os.path.isdir(local) and not os.listdir(local):
                    os.rmdir(local)
                results.append(res)
                continue
            local_state, detail, rev = checkout_state(local, spec["branch"])
            res["cloned"] = True
        elif local_state in ("clean", "behind", "ahead", "diverged"):
            _git(local, "fetch", "--quiet", "origin", timeout=600)
            local_state, detail, rev = checkout_state(local, spec["branch"])
            if local_state == "behind":
                code, _o, err = _git(local, "merge", "--ff-only", "--quiet",
                                     "refs/remotes/origin/%s" % spec["branch"])
                if code == 0:
                    res["fast_forwarded"] = True
                local_state, detail, rev = checkout_state(local, spec["branch"])
        res.update(status=local_state, detail=detail, revision=rev)
        if local_state in NEXT_ACTION:
            res["next"] = NEXT_ACTION[local_state].format(path=spec["path"],
                                                          branch=spec["branch"], url=spec["url"])
        if os.path.isdir(os.path.join(local, ".obsidian")):
            res["nested_vault"] = True
            res.setdefault("warnings", []).append(
                "%s has its own .obsidian folder. Open the parent workspace, not this folder, "
                "or links between repositories will not resolve." % spec["path"])
        results.append(res)
    maps = write_maps(parent, manifest, results, now=now)
    attention = [r for r in results if r.get("next") and r["status"] != "ahead"]
    return {"parent": parent, "repos": results, "maps": maps,
            "code": EXIT_STATE if attention else EXIT_OK}


def status(parent):
    """The Command OS view of each repository, without fetching."""
    manifest = load(parent)
    out = []
    for name, spec in _repos(manifest):
        if spec["state"] != "active":
            out.append({"name": name, "status": "not active" if spec["state"] == "inactive"
                        else "reference"})
            continue
        local_state, detail, rev = checkout_state(os.path.join(parent, spec["path"]),
                                                  spec["branch"])
        out.append({"name": name, "status": "not cloned" if local_state == "missing"
                    else local_state, "detail": detail, "revision": rev})
    return out


# ---------------------------------------------------------------------------------------------
# Generated maps
# ---------------------------------------------------------------------------------------------

def _now(now):
    return now or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _body_hash(body):
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


GENERATED_RE = re.compile(r"\A---\ngenerated: true\n(?:.*\n)*?body_sha256: ([0-9a-f]{64})\n"
                          r"(?:.*\n)*?---\n", re.M)


def _write_generated(path, body, revisions, now):
    """Write a generated page, unless someone edited the last one; then write <name>.new."""
    header = ("---\ngenerated: true\ngenerator: aios workspace (kit %s)\ngenerated_at: %s\n"
              "source_revisions: %s\nbody_sha256: %s\n---\n"
              % (KIT_VERSION, now, json.dumps(revisions, sort_keys=True), _body_hash(body)))
    target = path
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            current = fh.read()
        m = GENERATED_RE.match(current)
        edited = not m or _body_hash(current[m.end():]) != m.group(1)
        if edited:
            stem, ext = os.path.splitext(path)
            target = stem + ".new" + ext
    util.ensure_parent(target)
    with open(target, "w", encoding="utf-8") as fh:
        fh.write(header + body)
    return os.path.basename(target), target != path


def _write_generated_json(path, obj):
    """Canvas files are JSON, so they cannot carry front matter; edits are detected by hash."""
    body = json.dumps(obj, indent=2, sort_keys=True) + "\n"
    stamp = path + ".sha256"
    target = path
    if os.path.isfile(path) and os.path.isfile(stamp):
        with open(path, encoding="utf-8") as fh, open(stamp, encoding="utf-8") as sh:
            if _body_hash(fh.read()) != sh.read().strip():
                target = os.path.splitext(path)[0] + ".new.canvas"
    elif os.path.isfile(path):
        target = os.path.splitext(path)[0] + ".new.canvas"
    with open(target, "w", encoding="utf-8") as fh:
        fh.write(body)
    if target == path:
        with open(stamp, "w", encoding="utf-8") as sh:
            sh.write(_body_hash(body) + "\n")
    return os.path.basename(target), target != path


def _start_page(parent, spec):
    root = os.path.join(parent, spec["path"])
    for candidate in ([spec["start_page"]] if spec.get("start_page") else []) + \
            ["START_HERE.md", "START-HERE.md", "README.md"]:
        if os.path.isfile(os.path.join(root, candidate)):
            return "%s/%s" % (spec["path"], candidate)
    return None


def _label(res):
    return {"not active": "inactive - not part of this plan yet",
            "reference": "reference - shown as an interface, not cloned",
            "not connected": "not connected - this computer cannot read it",
            "error": "error - could not be cloned"}.get(res["status"], res["status"])


def write_maps(parent, manifest, results, now=None):
    now = _now(now)
    revisions = {r["name"]: (r.get("revision") or "")[:12] or None for r in results}
    specs = dict(_repos(manifest))
    written = {}

    # Repository Map
    lines = ["# Repository Map", "",
             "Each folder below is its own Git repository with its own history. This page is "
             "generated; put your own notes inside the right repository, not here.", "",
             "| Name | Domain | Status | Branch | Revision | Start page |",
             "|---|---|---|---|---|---|"]
    for r in results:
        start = _start_page(parent, specs[r["name"]]) if r.get("revision") else None
        lines.append("| %s | %s | %s | %s | %s | %s |" % (
            specs[r["name"]].get("title") or r["name"], r["domain"], _label(r), r["branch"],
            ("`%s`" % r["revision"][:12]) if r.get("revision") else "-",
            ("[open](../%s)" % start) if start else "-"))
    actions = [r for r in results if r.get("next")]
    if actions:
        lines += ["", "## Needs attention", ""]
        lines += ["- **%s:** %s" % (r["name"], r["next"]) for r in actions]
    written["Repository Map.md"] = _write_generated(
        os.path.join(parent, MAPS_DIR, "Repository Map.md"), "\n".join(lines) + "\n",
        revisions, now)

    # System Relationships
    edges = relationships(manifest, results)
    lines = ["# System Relationships", "",
             "What each part gives the others. Execution does not pass through Obsidian or "
             "Command OS: they show the system, they do not run it.", "",
             "| From | To | Relationship |", "|---|---|---|"]
    lines += ["| %s | %s | %s |" % (a, b, label) for a, b, label in edges]
    caps = manifest.get("capabilities") or []
    if caps:
        lines += ["", "## Capabilities provided from outside this workspace", "",
                  "These are interfaces. You can ask for the job and receive your result in "
                  "your own systems. The method that produces it is not in this workspace.", ""]
        lines += ["- **%s** (%s, %s): %s" % (c["name"], c.get("provider", "provider"),
                                              c.get("status", "interface"),
                                              c.get("description", "")) for c in caps]
    written["System Relationships.md"] = _write_generated(
        os.path.join(parent, MAPS_DIR, "System Relationships.md"), "\n".join(lines) + "\n",
        revisions, now)

    # Knowledge Health
    written["Knowledge Health.md"] = _write_generated(
        os.path.join(parent, MAPS_DIR, "Knowledge Health.md"),
        knowledge_health(parent, results, specs), revisions, now)

    # Canvas
    written["Operating System.canvas"] = _write_generated_json(
        os.path.join(parent, MAPS_DIR, "Operating System.canvas"),
        canvas(parent, manifest, results))

    # START-HERE: generated once, then the owner's page (edits are kept the same way).
    written[START_HERE] = _write_generated(os.path.join(parent, START_HERE),
                                           start_here(manifest, results, specs, parent),
                                           revisions, now)
    return {k: {"file": v[0], "kept_your_edit": v[1]} for k, v in written.items()}


def relationships(manifest, results):
    present = {r["domain"]: r["name"] for r in results}
    edges = []
    for r in results:
        if r["domain"] in ("aios", "command-os"):
            continue
        if "aios" in present:
            edges.append((present["aios"], r["name"], "context"))
        if "command-os" in present:
            edges.append((r["name"], present["command-os"], "operational data"))
    if "creation" in present:
        for r in results:
            if r["domain"] in ("team-ops", "revops", "attention"):
                edges.append((present["creation"], r["name"], "asset reference"))
    for cap in manifest.get("capabilities") or []:
        target = present.get(cap.get("domain"))
        if target:
            edges.append((target, cap["name"], "capability call"))
            edges.append((cap["name"], target, "client-specific output"))
    return edges


def canvas(parent, manifest, results):
    """JSON Canvas 1.0. Client-owned repositories inside one group; FF capabilities outside."""
    nodes, edges = [], []
    specs = dict(_repos(manifest))
    width, height, gap = 300, 120, 60
    row_members = {}
    for r in results:
        row_members.setdefault(ROWS.get(r["domain"], 1), []).append(r)
    widest = max(len(v) for v in row_members.values())
    group_w = widest * (width + gap) + gap
    ids = {}
    for row, members in sorted(row_members.items()):
        offset = (group_w - len(members) * (width + gap) - gap) // 2 + gap
        for i, r in enumerate(members):
            node_id = "repo-" + r["name"]
            ids[r["name"]] = node_id
            x, y = offset + i * (width + gap), gap + row * (height + 2 * gap)
            title = specs[r["name"]].get("title") or r["name"]
            start = _start_page(parent, specs[r["name"]]) if r.get("revision") else None
            if start:
                nodes.append({"id": node_id, "type": "file", "file": start, "x": x, "y": y,
                              "width": width, "height": height})
            else:
                nodes.append({"id": node_id, "type": "text", "x": x, "y": y, "width": width,
                              "height": height, "color": "0" if r["status"] == "not active"
                              else "3", "text": "**%s**\n\n%s" % (title, _label(r))})
    rows_used = max(row_members) + 1
    group_h = rows_used * (height + 2 * gap)
    nodes.insert(0, {"id": "client-boundary", "type": "group", "x": 0, "y": 0,
                     "width": group_w, "height": group_h,
                     "label": "%s - owned by the company" % (manifest.get("company")
                                                             or "This workspace")})
    caps = manifest.get("capabilities") or []
    for i, cap in enumerate(caps):
        node_id = "cap-%d" % i
        ids[cap["name"]] = node_id
        nodes.append({"id": node_id, "type": "text", "x": group_w + 2 * gap,
                      "y": gap + i * (height + gap), "width": width, "height": height,
                      "color": "5", "text": "**%s**\n\nInterface only - provided by %s"
                      % (cap["name"], cap.get("provider", "a provider"))})
    for n, (a, b, label) in enumerate(relationships(manifest, results)):
        if a in ids and b in ids:
            edges.append({"id": "edge-%d" % n, "fromNode": ids[a], "toNode": ids[b],
                          "label": label, "toEnd": "arrow"})
    return {"nodes": nodes, "edges": edges}


def _markdown_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for f in sorted(filenames):
            if f.lower().endswith(".md"):
                yield os.path.join(dirpath, f)


def knowledge_health(parent, results, specs):
    """Deterministic checks only. Every item is a candidate for review, not a verdict."""
    lines = ["# Knowledge Health", "",
             "Mechanical checks over the files on this computer. Each item is a candidate to "
             "review, not a defect: an old changelog or a rarely changing standard is "
             "allowed to be old, and two files with one title are not proof of one content.", ""]
    titles = {}
    for r in results:
        if not r.get("revision"):
            continue
        root = os.path.join(parent, specs[r["name"]]["path"])
        broken, oversized, count = [], [], 0
        for path in _markdown_files(root):
            count += 1
            rel = os.path.relpath(path, parent).replace(os.sep, "/")
            size = os.path.getsize(path)
            if size > OVERSIZED_BYTES:
                oversized.append("`%s` (%d KB)" % (rel, size // 1024))
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
            for lineno, line in enumerate(text.splitlines(), 1):
                if lineno == 1 and line.startswith("# "):
                    titles.setdefault(line[2:].strip().lower(), []).append(rel)
                for target in LINK_RE.findall(line):
                    if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.I) or target.startswith("#"):
                        continue
                    target = target.split("#", 1)[0]
                    if not target:
                        continue
                    resolved = os.path.normpath(os.path.join(os.path.dirname(path),
                                                             unquote(target)))
                    if not os.path.exists(resolved):
                        broken.append("`%s:%d` -> `%s`" % (rel, lineno, target))
        lines += ["## %s" % r["name"], "",
                  "- Revision `%s`, %d Markdown files." % (r["revision"][:12], count)]
        lines.append("- Links that point at a missing file: %d" % len(broken))
        lines += ["  - %s" % b for b in broken[:25]]
        if len(broken) > 25:
            lines.append("  - ... and %d more" % (len(broken) - 25))
        lines.append("- Unusually large documents (over %d KB): %d"
                     % (OVERSIZED_BYTES // 1024, len(oversized)))
        lines += ["  - %s" % o for o in oversized[:10]]
        if r.get("nested_vault"):
            lines.append("- This repository has its own `.obsidian` folder (a nested vault).")
        lines.append("")
    dupes = {t: p for t, p in titles.items() if len(p) > 1}
    lines += ["## Same title in more than one file", "",
              "Candidates for a canonical-document decision. Compare the content before "
              "merging anything.", ""]
    if dupes:
        for title, paths in sorted(dupes.items())[:25]:
            lines.append("- \"%s\": %s" % (title, ", ".join("`%s`" % p for p in paths)))
    else:
        lines.append("- none found")
    return "\n".join(lines) + "\n"


def start_here(manifest, results, specs, parent):
    name = manifest.get("workspace_name") or "Operating System"
    lines = ["# %s - start here" % name, "",
             "This folder is a map over the company's repositories. Each folder is its own "
             "repository; this page and everything in `00-MAPS` are generated and can be "
             "rebuilt at any time with `aios workspace sync`.", "",
             "## Open a part of the system", ""]
    for r in results:
        start = _start_page(parent, specs[r["name"]]) if r.get("revision") else None
        title = specs[r["name"]].get("title") or r["name"]
        lines.append("- %s - %s" % (("[%s](%s)" % (title, start)) if start else
                                    "**%s**" % title, _label(r)))
    lines += ["", "## See how it fits together", "",
              "- [Operating System canvas](00-MAPS/Operating%20System.canvas)",
              "- [Repository Map](00-MAPS/Repository%20Map.md)",
              "- [System Relationships](00-MAPS/System%20Relationships.md)",
              "- [Knowledge Health](00-MAPS/Knowledge%20Health.md)", "",
              "## Where your work goes", "",
              "- A note that matters belongs inside the repository it is about, where it is "
              "saved in Git and reviewed. Not in `00-MAPS`, which is rebuilt.",
              "- Folders shown as **reference** or **inactive** are not missing or broken. "
              "They are parts of the system that are not set up for this company yet.",
              "- Hiding a file in Obsidian does not protect it. Only the repositories this "
              "company owns are in this folder.", "",
              "## If something looks wrong", "",
              "Run `aios workspace status`. It says which repository needs attention and the "
              "exact next step. The setup never deletes, resets or overwrites your work.", ""]
    return "\n".join(lines)
