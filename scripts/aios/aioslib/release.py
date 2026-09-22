"""Release manifests: build a draft, verify a pin, decide whether it may be consumed.

Consumes founder ruling **D3** (owned by P01, not by this package): a Starter or organization
deployment installs an *approved, versioned release*, never mutable `main`. This module is the
gate that makes D3 executable here.

Three independent properties, checked separately because they fail for different reasons and a
human needs to know which one failed:

  pinned    - the manifest names one exact immutable tree (a full 40-char commit) and the
              sha256 of every file in it.
  intact    - the content at that pin still hashes to what the manifest recorded.
  approved  - a human set `status: approved` and signed `approval.approved_by`.

The builder can only ever emit `status: draft`. That is enforced by a test that also greps this
source, the same way P01 enforces it, because a generator that can approve its own release makes
the approval boundary decorative.
"""

import os
import re

from . import util
from .util import EXIT_PACKAGE, Refusal

SCHEMA = "ff-aios-starter/release@1"
PACKAGE = "ff-aios-starter"
VALID_STATUS = ("draft", "approved", "superseded", "withdrawn")
CRED_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


def load_spec(repo, rev=None, spec_path="release/package_spec.json"):
    """The package spec says which paths ship and which class each one is.

    Read from the pinned tree when a rev is given, so a release describes the spec that was
    in force when it was cut, not whatever the working copy says today.
    """
    if rev:
        for path, _mode, data in util.read_tree(repo, rev):
            if path == spec_path:
                import json

                return json.loads(data.decode("utf-8"))
        raise Refusal(EXIT_PACKAGE, "no %s in tree %s" % (spec_path, rev))
    return util.read_json(os.path.join(repo, spec_path))


def classify(spec, path):
    """Return 'managed', 'seed' or None (excluded) for a repo-relative path."""
    if util.match_any(spec.get("exclude"), path):
        return None
    if util.match_any(spec.get("seed"), path):
        return "seed"
    return "managed"


def select_files(repo, rev, spec):
    """The package file set at a pin: [(path, class, mode, sha256)], sorted.

    A link is refused only when it is *inside* the package. A link under an excluded path
    is somebody else's business and must not veto the release.
    """
    out = []
    for path, mode, data in util.read_tree(repo, rev, include_links=True):
        cls = classify(spec, path)
        if cls is None:
            continue
        if mode == "120000":
            raise Refusal(
                EXIT_PACKAGE,
                "the package would ship a link, which dangles on a fresh clone: %s" % path,
                ["untrack it, or commit a real file, or exclude it in release/package_spec.json"],
            )
        out.append((path, cls, mode, util.sha256_bytes(data)))
    out.sort(key=lambda r: r[0])
    return out


def build(repo, rev, version, spec=None, branch=None, credentials=None, min_upgrade_from=None,
          aios_release=None):
    """Emit a DRAFT release manifest. There is deliberately no approve path in this function."""
    if not util.FULL_SHA1_RE.match(rev or ""):
        # A branch name or short sha is not a pin: both move, and a package that moves is
        # exactly what D3 forbids.
        raise Refusal(EXIT_PACKAGE, "release must pin a full 40-character commit sha, got %r" % rev)
    if not util.rev_exists(repo, rev):
        raise Refusal(EXIT_PACKAGE, "commit %s does not exist in %s" % (rev, repo))
    if not util.parse_semver(version):
        raise Refusal(EXIT_PACKAGE, "version must be semver, got %r" % version)

    spec = spec or load_spec(repo, rev)
    files = select_files(repo, rev, spec)
    if not files:
        raise Refusal(EXIT_PACKAGE, "package spec selected no files at %s" % rev)

    skills = sorted({
        p.split("/")[2] for p, _c, _m, _s in files
        if p.startswith(".claude/skills/") and p.count("/") >= 3
    })

    return {
        "schema": SCHEMA,
        "release_id": "starter-%s" % version,
        "package": PACKAGE,
        "version": version,
        "created_from": {"git_rev": rev, "branch": branch or ""},
        "status": "draft",
        "approval": {"approved_by": None, "approved_at": None},
        "compatibility": {"min_upgrade_from": min_upgrade_from, "breaking": []},
        # P01 owns AIOS releases. When this is set it must name an APPROVED aios-X.Y.Z;
        # today nothing is approved, so it stays null and consume() enforces that.
        "consumes": {"aios_release": aios_release},
        "credentials": credentials or [],
        "counts": {
            "files": len(files),
            "managed": sum(1 for f in files if f[1] == "managed"),
            "seed": sum(1 for f in files if f[1] == "seed"),
            "skills": len(skills),
        },
        "skills": skills,
        "files": [
            {"path": p, "class": c, "mode": m, "sha256": s} for p, c, m, s in files
        ],
    }


# ─── checks ──────────────────────────────────────────────────────────────────

def check_shape(man):
    problems = []
    if man.get("schema") != SCHEMA:
        problems.append("schema is %r, expected %r" % (man.get("schema"), SCHEMA))
    if man.get("package") != PACKAGE:
        problems.append("package is %r, expected %r" % (man.get("package"), PACKAGE))
    if not util.parse_semver(man.get("version", "")):
        problems.append("version %r is not semver" % man.get("version"))
    if man.get("release_id") != "starter-%s" % man.get("version"):
        problems.append("release_id %r does not match version %r"
                        % (man.get("release_id"), man.get("version")))
    if man.get("status") not in VALID_STATUS:
        problems.append("status %r is not one of %s" % (man.get("status"), list(VALID_STATUS)))
    for cred in man.get("credentials") or []:
        name = cred.get("name")
        if not CRED_NAME_RE.match(name or ""):
            problems.append("credential name %r is not an env-var name" % name)
        # References only. A manifest that can carry a value will eventually carry one.
        for banned in ("value", "secret", "token"):
            if banned in cred:
                problems.append("credential %s carries a %r field; references only" % (name, banned))
    return problems


def check_pinned(man):
    problems = []
    rev = (man.get("created_from") or {}).get("git_rev", "")
    if not util.FULL_SHA1_RE.match(rev or ""):
        problems.append("created_from.git_rev %r is not a full 40-character commit sha" % rev)
    files = man.get("files")
    if not files:
        problems.append("manifest pins no files")
    for entry in files or []:
        if not util.SHA256_RE.match(entry.get("sha256", "") or ""):
            problems.append("file %s has no valid sha256" % entry.get("path"))
        if not util.safe_relpath(entry.get("path", "")):
            problems.append("file path %r is unsafe" % entry.get("path"))
        if entry.get("class") not in ("managed", "seed"):
            problems.append("file %s has class %r" % (entry.get("path"), entry.get("class")))
    return problems


def check_approved(man):
    problems = []
    status = man.get("status")
    approval = man.get("approval") or {}
    if status != "approved":
        problems.append("release status is %r; only 'approved' may be installed (founder ruling D3)"
                        % status)
    if not (approval.get("approved_by") or "").strip():
        problems.append("approval.approved_by is empty; approval is a human act")
    if not (approval.get("approved_at") or "").strip():
        problems.append("approval.approved_at is empty")
    return problems


def check_intact(man, repo):
    """The content at the pin must still hash to what the manifest recorded.

    This is what makes "installed from release X" a statement about bytes rather than about a
    label somebody typed.
    """
    problems = []
    rev = (man.get("created_from") or {}).get("git_rev", "")
    if not util.rev_exists(repo, rev):
        return ["commit %s is not present in the source repo %s" % (rev, repo)]

    spec = load_spec(repo, rev)
    actual = {p: (c, m, s) for p, c, m, s in select_files(repo, rev, spec)}
    declared = {e["path"]: (e.get("class"), e.get("mode"), e.get("sha256"))
                for e in man.get("files") or []}

    for path, (cls, mode, sha) in sorted(declared.items()):
        if path not in actual:
            problems.append("manifest lists %s, which is not in the package at the pin" % path)
            continue
        a_cls, a_mode, a_sha = actual[path]
        if a_sha != sha:
            problems.append("content drift at %s: pin has %s, manifest says %s"
                            % (path, a_sha[:12], (sha or "")[:12]))
        if a_cls != cls:
            problems.append("class drift at %s: %s vs %s" % (path, a_cls, cls))
        if a_mode != mode:
            problems.append("mode drift at %s: %s vs %s" % (path, a_mode, mode))
    for path in sorted(set(actual) - set(declared)):
        # An omission is as dangerous as a mutation: a file silently missing from the manifest
        # is a file nobody verifies on install.
        problems.append("package at the pin contains %s, which the manifest does not list" % path)
    return problems


def consumable(man, repo, aios_release_lookup=None):
    """Every reason this release may not be installed. Empty list means it may be."""
    problems = []
    problems += check_shape(man)
    problems += check_pinned(man)
    problems += check_approved(man)
    if not problems:
        problems += check_intact(man, repo)

    aios_id = (man.get("consumes") or {}).get("aios_release")
    if aios_id:
        if aios_release_lookup is None:
            problems.append(
                "release consumes AIOS release %s but no AIOS release catalogue was supplied to "
                "check it is approved" % aios_id)
        else:
            aios = aios_release_lookup(aios_id)
            if aios is None:
                problems.append("AIOS release %s not found" % aios_id)
            elif aios.get("status") != "approved":
                problems.append(
                    "AIOS release %s has status %r; a Starter release may only consume an approved "
                    "AIOS release (founder ruling D3)" % (aios_id, aios.get("status")))
    return problems


def require_consumable(man, repo, aios_release_lookup=None):
    problems = consumable(man, repo, aios_release_lookup)
    if problems:
        raise Refusal(
            EXIT_PACKAGE,
            "release %s may not be installed" % (man.get("release_id") or "<unknown>"),
            problems,
        )
