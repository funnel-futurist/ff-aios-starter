"""Sanitization: what must never ship inside a package.

Three classes of thing:

1. **Credential-shaped literals.** Patterns are kept in parity with the PR floor
   (`scripts/pr_review/static_checks.mjs`), which is the repo's single source of truth for
   secret shapes. A parity test parses that file and fails if this list drifts behind it, so
   two scanners cannot quietly disagree about what a secret looks like.

2. **Client names.** The denylist is **never committed**. This repo is public: a file listing
   every client name would itself be the leak it is meant to prevent. The list is supplied at
   run time (`--denylist <file>`), and in release mode a missing list is a hard failure -
   "no client names found" is not a claim you get to make without having looked.

3. **Internal infrastructure.** Deployment hosts, workspace URLs and chat/CRM object links
   that mean nothing to a client and quietly describe our estate.

Matching is **word-boundary**, learned the expensive way: a substring scan of this repo
flagged `Reporter` and `compounds` as client names. A check that cries wolf gets switched
off, so precision is a safety property, not a nicety.
"""

import os
import re

from . import util
from .util import EXIT_SANITIZE, Refusal

# Assembled from fragments for the same reason static_checks.mjs does it: a scanner whose own
# source contains a contiguous matchable literal flags itself and every PR that touches it.
SECRET_FRAGMENTS = [
    "sk-ant" + "-",
    "sk-[a-zA-Z0-9]{20,}",
    "xoxb" + "-",
    "xoxp" + "-",
    "AKIA[A-Z0-9]{16}",
    "ghp_[a-zA-Z0-9]{36}",
    "github_pat" + "_[A-Za-z0-9_]{20,}",
    "sk_live" + "_[A-Za-z0-9]{20,}",
    "AIza[0-9A-Za-z_-]{35}",
    "pit-[0-9a-f]{8}-[0-9a-f]{4}",
    "postgresql:" + r"\/\/[^\s\"']*:[^\s\"']+@",
    "mongodb" + r"\+srv:\/\/[^\s\"']*:[^\s\"']+@",
    "-----BEGIN (RSA |EC |OPENSSH )?PRIVATE" + "[ ]KEY",
    "eyJ[A-Za-z0-9_-]{10,}\\.eyJ[A-Za-z0-9_-]{10,}\\.[A-Za-z0-9_-]{10,}",
]
SECRET_RE = re.compile("(" + "|".join(SECRET_FRAGMENTS) + ")", re.I)

INTERNAL_PATTERNS = [
    (r"[A-Za-z0-9-]+\.up\.railway\.app", "deployment host"),
    (r"[A-Za-z0-9-]+\.supabase\.co", "database host"),
    (r"hooks\.slack\.com/services/\S+", "chat webhook"),
    (r"app\.clickup\.com/t/\w+", "task object"),
    (r"[A-Za-z0-9-]+\.ngrok(-free)?\.(io|app)", "tunnel host"),
    (r"https://drive\.google\.com/(file|drive)/\S+", "workspace document"),
    (r"https://docs\.google\.com/\S+", "workspace document"),
]
INTERNAL_RE = [(re.compile(p, re.I), label) for p, label in INTERNAL_PATTERNS]

# Lines that legitimately *describe* a shape rather than carrying one.
ALLOW_LINE_RE = re.compile(
    r"(your-|example\.com|placeholder|changeme|\bxxx\b|sample|fragment|"
    r"process\.env\.|os\.environ|getenv|\benv:[A-Z]|\bdotenv:[A-Z])", re.I)

MAX_SCAN_BYTES = 4 * 1024 * 1024


def load_denylist(path):
    """One term per line; `#` comments ignored. Terms are never echoed in full."""
    terms = []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            term = line.strip()
            if term and not term.startswith("#"):
                terms.append(term)
    return terms


def _denylist_re(terms):
    parts = []
    for term in terms:
        words = [re.escape(w) for w in re.split(r"[\s_-]+", term.strip()) if w]
        if not words:
            continue
        parts.append(r"\b" + r"[\s_-]?".join(words) + r"\b")
    if not parts:
        return None
    return re.compile("|".join(parts), re.I)


def fingerprint(text):
    """A stable short hash, so a finding can be reported without repeating the secret."""
    return util.sha256_bytes(text.lower().encode("utf-8"))[:12]


def scan_bytes(path, data, deny_re=None):
    """Findings for one file. A finding never carries the matched value, only a fingerprint.

    Binary files are scanned too, as latin-1. A secret pasted into a .docx is still a secret,
    and "we skipped the binaries" is how scanners come to mean nothing.
    """
    findings = []
    if len(data) > MAX_SCAN_BYTES:
        data = data[:MAX_SCAN_BYTES]
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("latin-1", "replace")

    for lineno, line in enumerate(text.splitlines(), 1):
        if len(line) > 8000:
            line = line[:8000]
        allowed = ALLOW_LINE_RE.search(line)
        m = SECRET_RE.search(line)
        if m and not allowed:
            findings.append({
                "path": path, "line": lineno, "kind": "secret",
                "detail": "credential-shaped literal", "fingerprint": fingerprint(m.group(0)),
            })
        for rx, label in INTERNAL_RE:
            m2 = rx.search(line)
            if m2 and not allowed:
                findings.append({
                    "path": path, "line": lineno, "kind": "internal",
                    "detail": label, "fingerprint": fingerprint(m2.group(0)),
                })
        if deny_re is not None:
            m3 = deny_re.search(line)
            if m3:
                findings.append({
                    "path": path, "line": lineno, "kind": "client_name",
                    "detail": "denylisted name", "fingerprint": fingerprint(m3.group(0)),
                })
    return findings


def scan_files(files, deny_re=None):
    findings = []
    for path, data in files:
        findings.extend(scan_bytes(path, data, deny_re))
    return findings


def scan_release(repo, rev, spec_paths, denylist_path=None, mode="release"):
    """Scan exactly the file set a release would ship.

    `mode='release'` requires a denylist: a portability claim made without the list of names
    you are checking for is not a claim, it is a hope.
    """
    deny_re = None
    if denylist_path:
        deny_re = _denylist_re(load_denylist(denylist_path))
    elif mode == "release":
        raise Refusal(
            EXIT_SANITIZE,
            "release-mode sanitization needs a client-name denylist",
            ["pass --denylist <file> (one name per line; keep the file OUT of this repo)",
             "the denylist is a reference supplied at run time, never committed here"],
        )

    wanted = set(spec_paths)
    files = []
    for path, mode_str, data in util.read_tree(repo, rev):
        if path in wanted:
            files.append((path, data))
    findings = scan_files(files, deny_re)
    return findings, len(files)


def require_clean(findings, what="package"):
    if findings:
        lines = ["%s:%s %s (%s, fp %s)" % (f["path"], f["line"], f["kind"], f["detail"],
                                           f["fingerprint"]) for f in findings[:40]]
        if len(findings) > 40:
            lines.append("... and %d more" % (len(findings) - 40))
        raise Refusal(EXIT_SANITIZE, "%s failed sanitization" % what, lines)


def js_floor_fragments(js_path):
    """Parse SECRET_FRAGMENTS out of static_checks.mjs so the parity test can compare."""
    with open(js_path, "r", encoding="utf-8") as fh:
        src = fh.read()
    m = re.search(r"const SECRET_FRAGMENTS = \[(.*?)\];", src, re.S)
    if not m:
        return []
    out = []
    for raw in re.findall(r"'((?:[^'\\]|\\.)*)'(?:\s*\+\s*)?", m.group(1)):
        out.append(raw)
    # The JS list concatenates adjacent quoted fragments with `+`; rebuild per line.
    fragments = []
    for line in m.group(1).splitlines():
        line = line.strip().rstrip(",")
        if not line or line.startswith("//"):
            continue
        pieces = re.findall(r"'((?:[^'\\]|\\.)*)'", line)
        if pieces:
            fragments.append("".join(pieces))
    return fragments or out
