"""Folder layout moves: Starter 2.x's numbered folders to the 3.0 instance layout.

The map is part of the release (`layout` in release/package_spec.json, copied into the release
record by `release build`), so the founder approves the exact moves with the release.

What it promises, stated so nobody has to discover it:

* Every file under a 2.x folder that the release does not manage moves: the starter files,
  and anything the person created there. The longest matching rule wins, and each 2.x top
  folder has a catch-all, so no file is without a destination.
* Nothing is overwritten. A destination that already exists with different bytes refuses the
  whole move before anything changes. Identical bytes count as already moved.
* Nothing is left behind. After the moves, any file still under a 2.x folder is a failure, and
  the caller rolls the whole upgrade back.
* Every move is recorded, so a rollback (or recovery after a hard kill) can reverse it.
* It never rewrites what is inside a file. References to old folder names in the person's own
  files are reported, not edited.
"""

import os
import re
import shutil

from . import util
from .util import EXIT_STATE, Refusal

TEXT_SUFFIXES = (".md", ".txt", ".json", ".yaml", ".yml")


def version_of(layout):
    return str((layout or {}).get("version") or "2")


def _destination(rel, moves):
    """The 3.0 path for one 2.x path, or None if no rule covers it."""
    best = None
    for move in moves:
        src = move["from"]
        if src.endswith("/"):
            if rel.startswith(src) and (best is None or len(src) > len(best["from"])):
                best = move
        elif rel == src and (best is None or len(src) > len(best["from"])):
            best = move
    if best is None:
        return None
    src, dst = best["from"], best["to"]
    return dst + rel[len(src):] if src.endswith("/") else dst


def _files_under(target, root):
    base = os.path.join(target, root)
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if d != ".git")
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            yield os.path.relpath(full, target).replace(os.sep, "/")


def plan_moves(target, layout, managed_paths):
    """[(from, to)] for every file to move. Refuses, changing nothing, on any conflict."""
    moves, conflicts, uncovered = [], [], []
    seen_dst = {}
    for root in layout.get("retired_roots") or []:
        for rel in _files_under(target, root):
            if rel in managed_paths:
                continue  # the release replaces or retires its own files
            dst = _destination(rel, layout.get("moves") or [])
            if dst is None:
                uncovered.append(rel)
                continue
            if dst in seen_dst:
                conflicts.append("%s and %s would both move to %s" % (seen_dst[dst], rel, dst))
                continue
            seen_dst[dst] = rel
            full_dst = os.path.join(target, dst)
            if os.path.lexists(full_dst):
                if os.path.isfile(full_dst) and \
                        util.sha256_file(full_dst) == util.sha256_file(os.path.join(target, rel)):
                    moves.append((rel, dst))  # identical: the move just removes the old copy
                    continue
                conflicts.append("%s would overwrite %s, which already exists with different "
                                 "content" % (rel, dst))
                continue
            moves.append((rel, dst))
    if uncovered or conflicts:
        raise Refusal(EXIT_STATE,
                      "the 2.x to 3.0 folder move cannot run safely; nothing was changed",
                      sorted(conflicts)[:20] + ["no destination for %s" % u for u in uncovered[:20]]
                      + ["move or rename those files yourself, commit, then upgrade again"])
    return moves


def apply_moves(target, moves):
    """Move each file. An identical copy at the destination means the source is removed."""
    for src, dst in moves:
        full_src, full_dst = os.path.join(target, src), os.path.join(target, dst)
        if os.path.lexists(full_dst):
            os.remove(full_src)
            continue
        util.ensure_parent(full_dst)
        shutil.move(full_src, full_dst)


def reverse_moves(target, moves):
    """Put moved files back. A file the person later deleted stays deleted; one whose old path
    is now occupied by something else is refused rather than overwritten."""
    blocked = []
    for src, dst in reversed(moves):
        full_src, full_dst = os.path.join(target, src), os.path.join(target, dst)
        if not os.path.lexists(full_dst):
            continue
        if os.path.lexists(full_src):
            if os.path.isfile(full_src) and util.sha256_file(full_src) == util.sha256_file(full_dst):
                continue
            blocked.append(src)
            continue
        util.ensure_parent(full_src)
        shutil.move(full_dst, full_src)
    if blocked:
        raise Refusal(EXIT_STATE, "reversing the folder move would overwrite %d file(s)"
                      % len(blocked), sorted(blocked)[:20]
                      + ["move those aside, then run rollback again"])


def leftovers(target, layout):
    """Every file still under a 2.x folder. Must be empty after a 3.0 upgrade."""
    out = []
    for root in layout.get("retired_roots") or []:
        out.extend(_files_under(target, root))
    return out


DEPLOY_MARKERS = ("package.json", "vercel.json", "netlify.toml", "next.config.js",
                  "next.config.mjs", "next.config.ts", "index.html")


def moved_deployables(moves):
    """Folders that look like a deployable site and changed path. A hosting setting (Vercel's
    Root Directory, for one) still points at the old path, and the person has to change it."""
    out = {}
    for src, dst in moves:
        if os.path.basename(src) in DEPLOY_MARKERS:
            out[os.path.dirname(src)] = os.path.dirname(dst)
    return sorted(out.items())


def stale_references(target, layout, skip_paths=()):
    """Files of the person's own that still name a 2.x folder. Reported, never rewritten."""
    roots = layout.get("retired_roots") or []
    if not roots:
        return []
    pattern = re.compile(r"\b(%s)\b" % "|".join(re.escape(r) for r in roots))
    out = []
    skip = set(skip_paths)
    for dirpath, dirnames, filenames in os.walk(target):
        rel_dir = os.path.relpath(dirpath, target).replace(os.sep, "/")
        dirnames[:] = [d for d in dirnames
                       if d not in (".git",) and not (rel_dir == "." and d == ".aios")]
        for name in filenames:
            if not name.endswith(TEXT_SUFFIXES):
                continue
            rel = os.path.normpath(os.path.join(rel_dir, name)).replace(os.sep, "/")
            if rel in skip:
                continue
            try:
                with open(os.path.join(target, rel), encoding="utf-8", errors="replace") as fh:
                    if pattern.search(fh.read()):
                        out.append(rel)
            except OSError:
                continue
    return sorted(out)


# ─── the instance contract (workspace kind) ─────────────────────────────────────────────────

DOMAIN_FOLDERS = ("00_AIOS", "01_Creation", "02_Team_Ops", "03_RevOps", "04_Attention",
                  "05_Jobs", "99_Archive")
BASELINE = (  # control id, path, what it is
    ("B1", "README.md", "the quick start"),
    ("B2", "CLAUDE.md", "the instructions Claude reads"),
    ("B3", "estate.yaml", "this repository's registry row"),
    ("B4", ".github/CODEOWNERS", "who reviews the founder-only files"),
    ("B5", "SETUP.md", "setup: access, secrets, reviewer, hosting, first-run checks"),
    ("B11", "REPO_CONTEXT.md", "what this repository is and why it's separate"),
)


def instance_checks(target):
    """The workspace-kind controls that can be checked from the files alone.

    Returns [(control, status, detail)], status PASS / FAIL / FLAG / INFO. Read-only. This is
    the set an Architecture Health collector can run per instance; it doesn't replace the
    registry's own checks or the review of whether only this company's material is here.
    """
    out = []
    for control, rel, what in BASELINE:
        ok = os.path.isfile(os.path.join(target, rel))
        out.append((control, "PASS" if ok else "FAIL", "%s (%s)%s" % (rel, what,
                                                                    "" if ok else ": missing")))
    decisions = os.path.join(target, "docs", "decisions")
    has_adr = os.path.isdir(decisions) and any(n.endswith(".md") for n in os.listdir(decisions))
    out.append(("B11", "PASS" if has_adr else "FAIL", "docs/decisions/ holds the decision notes"))
    owners = os.path.join(target, ".github", "CODEOWNERS")
    if os.path.isfile(owners):
        with open(owners, encoding="utf-8") as fh:
            placeholder = "[REPO_OWNER]" in fh.read()
        out.append(("B4", "FAIL" if placeholder else "PASS",
                    "CODEOWNERS names real owners" if not placeholder
                    else "CODEOWNERS still has [REPO_OWNER] placeholders, so it enforces nothing"))
    row = os.path.join(target, "estate.yaml")
    if os.path.isfile(row):
        with open(row, encoding="utf-8") as fh:
            text = fh.read()
        kind_ok = re.search(r'^kind_target:\s*"?instance"?', text, re.M) is not None
        named = re.search(r'^repo:\s*"?([^"\s#]+)', text, re.M)
        out.append(("B3", "PASS" if kind_ok else "FAIL", "estate.yaml says kind_target: instance"))
        out.append(("B3", "PASS" if named else "FLAG",
                    "estate.yaml names this repository" if named
                    else "estate.yaml has no repo name yet: fill it in (SETUP.md step 2)"))
    pointer = os.path.join(target, ".ff", "system.json")
    out.append(("B3", "PASS" if os.path.isfile(pointer) else "INFO",
                ".ff/system.json (the registry pointer)" if os.path.isfile(pointer)
                else ".ff/system.json not present: the provider's bootstrap writes it when the "
                     "repository is registered"))
    missing = [d for d in DOMAIN_FOLDERS if not os.path.isdir(os.path.join(target, d))]
    out.append(("workspace", "FAIL" if missing else "PASS",
                "the seven domain folders" + (": missing %s" % ", ".join(missing) if missing else "")))
    old = [d for d in ("01_Foundations", "02_Deliverables", "03_Quality_Control",
                       "04_Customer_Journey", "05_Assets", "06_Communication", "07_Setup",
                       "08_Automations", "09_Archive", "11_Projects")
           if os.path.exists(os.path.join(target, d))]
    out.append(("workspace", "FAIL" if old else "PASS",
                "no Starter 2.x folders left" + (": %s still there" % ", ".join(old) if old else "")))
    out.append(("workspace", "INFO", "only this company's material is here: a person or the "
                "boundary review confirms it; the files alone can't prove it"))
    return out
