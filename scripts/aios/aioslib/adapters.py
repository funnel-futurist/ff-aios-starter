"""Tool adapters: which shipped files work with only one AI tool, and which with any.

The Starter's behaviour (instructions, skills, hooks, safety settings, the AI reviewer) is
built on Claude Code. `release/adapters.json` says so, file by file, and says honestly where
nothing else is supported. This module checks that the declaration and the tree agree:

* a file in a tool-specific location (`.claude/*`, `CLAUDE.md`, `AGENTS.md`, `.cursor/*` ...)
  that is not declared for that tool is a problem, so a new tool-specific file cannot arrive
  unnoticed;
* a declared file that no longer exists is a problem;
* a tool is `verified` only when it names evidence, and each piece of evidence must resolve to
  a real test. Every other tool is `not verified`, and declares no evidence.

What "verified" means here, and does not: the named tests exercise the file layout and the
hook contract (simulated hook input, the real hook command). They are not a recording of a
live session in that tool. The manifest says which.

Python 3.9+, standard library only.
"""

import os
import re

from . import util
from .util import EXIT_PACKAGE, Refusal

SCHEMA = "ff-aios-starter/adapters@1"
MANIFEST_PATH = "release/adapters.json"
STATUSES = ("verified", "not verified")


def load(repo):
    path = os.path.join(repo, MANIFEST_PATH)
    if not os.path.isfile(path):
        raise Refusal(EXIT_PACKAGE, "no adapter manifest at %s" % MANIFEST_PATH,
                      ["it lives in the Starter's own repository; an installed workspace does not carry it"])
    data = util.read_json(path)
    if data.get("schema") != SCHEMA:
        raise Refusal(EXIT_PACKAGE, "%s is not a %s file" % (MANIFEST_PATH, SCHEMA))
    return data


def _evidence_problem(repo, ref):
    """None if `path` or `path::Class::method` names something that exists."""
    parts = ref.split("::")
    path = parts[0]
    full = os.path.join(repo, path)
    if not os.path.isfile(full):
        return "evidence %r: no such file" % ref
    if len(parts) == 1:
        return None
    if len(parts) != 3:
        return "evidence %r: use path or path::Class::method" % ref
    with open(full, encoding="utf-8") as fh:
        text = fh.read()
    cls = re.search(r"^class %s\b.*?(?=^class |\Z)" % re.escape(parts[1]), text, re.S | re.M)
    if not cls:
        return "evidence %r: no class %s" % (ref, parts[1])
    if not re.search(r"^\s+def %s\(" % re.escape(parts[2]), cls.group(0), re.M):
        return "evidence %r: no test %s in %s" % (ref, parts[2], parts[1])
    return None


def problems(repo, files):
    """Every way the manifest and the tree disagree. `files` = repo-relative tracked paths."""
    manifest = load(repo)
    out = []
    tools = manifest.get("tools") or {}
    if not tools:
        return ["the manifest declares no tools"]
    fileset = set(files)
    owner = {}

    for name, tool in sorted(tools.items()):
        status = tool.get("status")
        if status not in STATUSES:
            out.append("%s: status must be one of %s, got %r" % (name, STATUSES, status))
        evidence = tool.get("evidence") or []
        if status == "verified":
            if not evidence:
                out.append("%s is marked verified but names no test that proves it" % name)
            for ref in evidence:
                bad = _evidence_problem(repo, ref)
                if bad:
                    out.append("%s: %s" % (name, bad))
        elif evidence:
            out.append("%s is 'not verified' but lists evidence: either it is verified or it is not" % name)

        declared = tool.get("files") or []
        for path in declared:
            if path in owner:
                out.append("%s is declared for both %s and %s" % (path, owner[path], name))
            owner[path] = name
            if path not in fileset:
                out.append("%s declares %s, which does not exist: remove the entry" % (name, path))
        for path in sorted(fileset):
            if util.match_any(tool.get("signatures"), path) and path not in declared:
                out.append("%s is tool-specific to %s (matches its signatures) but is not declared in "
                           "release/adapters.json" % (path, name))

    neutral = manifest.get("tool_neutral") or []
    for pattern in neutral:
        hits = [p for p in fileset if util.match_pattern(pattern, p)]
        if not hits:
            out.append("tool_neutral %r matches no file: remove or fix the entry" % pattern)
        for p in hits:
            if p in owner:
                out.append("%s is declared tool-specific (%s) and tool-neutral" % (p, owner[p]))

    for entry in manifest.get("mixed") or []:
        if entry.get("path") not in fileset:
            out.append("mixed entry %r does not exist" % entry.get("path"))
        if not (entry.get("tool_specific_part") and entry.get("neutral_part")):
            out.append("mixed entry %r must say which part is tool-specific and which is neutral"
                       % entry.get("path"))
    return out
