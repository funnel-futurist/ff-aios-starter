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

## What this does NOT prove

Written down because an unbounded claim is worse than a narrow one. An adversarial review
(DeepSeek V4 Pro, 2026-09-22) found thirteen real gaps; the ones below are the residue that
is documented rather than fixed:

* **A secret assembled across lines** (`"AKIA" + "IOSF..."`) is not detected. Detecting
  arbitrary string construction means evaluating the code.
* **Encodings beyond UTF-8/UTF-16 and base64** - other encodings, encryption, or a secret
  split inside an archive member are not decoded.
* **Internal hosts are a known-pattern list**, not a proof. It catches the providers this
  estate actually uses plus private address space; an arbitrary staging domain is not
  recognised unless it is on the operator's denylist.
* **The scan covers the pinned release tree.** It says nothing about what a "Use this
  template" copy contains, because that copies a mutable default branch instead of a pin -
  which is exactly why founder ruling D3 says a workspace installs from an approved release.
"""

import re

from . import util
from .util import EXIT_SANITIZE, Refusal

# Assembled from fragments for the same reason static_checks.mjs does it: a scanner whose own
# source contains a contiguous matchable literal flags itself and every PR that touches it.
# Each pattern requires a plausible key BODY, not just a prefix. A bare `sk-ant-` in a
# sentence is documentation - the security_check skill has to be able to name the shapes it
# looks for without tripping the scanner that reads it.
SECRET_FRAGMENTS = [
    "sk-ant" + "-[A-Za-z0-9_-]{16,}",
    "sk-[a-zA-Z0-9]{20,}",
    "xoxb" + "-[0-9A-Za-z-]{12,}",
    "xoxp" + "-[0-9A-Za-z-]{12,}",
    "AKIA[A-Z0-9]{16}",
    "ghp_[a-zA-Z0-9]{36}",
    "github_pat" + "_[A-Za-z0-9_]{20,}",
    "sk_live" + "_[A-Za-z0-9]{20,}",
    "sk_test" + "_[A-Za-z0-9]{20,}",
    "sk-" + "(?:proj|admin|svcacct)-[A-Za-z0-9_-]{20,}",
    "glpat" + "-[A-Za-z0-9_-]{20,}",
    "AIza[0-9A-Za-z_-]{35}",
    "pit-[0-9a-f]{8}-[0-9a-f]{4}",
    "postgresql:" + r"\/\/[^\s\"']{0,200}:[^\s\"']{1,200}@",
    "mongodb" + r"(\+srv)?:\/\/[^\s\"']{0,200}:[^\s\"']{1,200}@",
    "mysql" + r":\/\/[^\s\"']{0,200}:[^\s\"']{1,200}@",
    "redis" + r"s?:\/\/[^\s\"']{0,200}:[^\s\"']{1,200}@",
    "-----BEGIN (RSA |EC |OPENSSH )?PRIVATE" + "[ ]KEY-----",
    "eyJ[A-Za-z0-9_-]{10,}\\.eyJ[A-Za-z0-9_-]{10,}\\.[A-Za-z0-9_-]{10,}",
]
SECRET_RE = re.compile("(" + "|".join(SECRET_FRAGMENTS) + ")", re.I)

INTERNAL_PATTERNS = [
    (r"[A-Za-z0-9-]{1,63}\.up\.railway\.app", "deployment host"),
    (r"[A-Za-z0-9-]{1,63}\.supabase\.co", "database host"),
    (r"hooks\.slack\.com/services/\S{1,200}", "chat webhook"),
    (r"app\.clickup\.com/t/\w+", "task object"),
    (r"[A-Za-z0-9-]{1,63}\.ngrok(-free)?\.(io|app)", "tunnel host"),
    (r"https://drive\.google\.com/(file|drive)/\S{1,300}", "workspace document"),
    (r"https://docs\.google\.com/\S{1,300}", "workspace document"),
]
INTERNAL_PATTERNS += [
    # Private address space and internal-only hostnames. Not exhaustive - the claim this
    # module supports is bounded accordingly, see "What this does NOT prove" below.
    (r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
     r"|192\.168\.\d{1,3}\.\d{1,3}"
     r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b", "private address"),
    (r"\b[A-Za-z0-9-]{1,63}\.(?:internal|intranet|lan)\b", "internal hostname"),
]
INTERNAL_RE = [(re.compile(p, re.I), label) for p, label in INTERNAL_PATTERNS]

# A MATCH that describes a shape rather than carrying one. Checked against the matched text,
# never against the whole line.
#
# This was a line-wide suppression, and an adversarial review broke it in one line:
#     const k = process.env.STRIPE_KEY || "sk_live_<22 chars>"
# A real hard-coded fallback key sat on a line mentioning `process.env`, so every finding on
# that line vanished. Fallback keys live next to env reads precisely BECAUSE that is where
# fallbacks go, so the allowlist was most permissive exactly where it mattered most.
# Reproduced 2026-09-22, then fixed.
PLACEHOLDER_MATCH_RE = re.compile(
    r"(your[-_]|example|placeholder|changeme|xxx|sample|dummy|fake|redacted)", re.I)

# Beyond this a file is REPORTED AS UNSCANNED rather than silently truncated. A clean scan of
# the first N bytes says nothing whatsoever about byte N+1.
MAX_SCAN_BYTES = 25 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 500
MAX_ARCHIVE_MEMBER_BYTES = 8 * 1024 * 1024
B64_RE = re.compile(rb"[A-Za-z0-9+/]{24,}={0,2}")


def load_allowlist(path):
    """Terms that are intentional in this package (the publisher's own name, for example)."""
    if not path:
        return None
    terms = [t.strip() for t in open(path, "r", encoding="utf-8") if t.strip()
             and not t.startswith("#")]
    if not terms:
        return None
    return re.compile("|".join(
        r"\b" + r"[\s_-]?".join(re.escape(w) for w in re.split(r"[\s_-]+", t)) + r"\b"
        for t in terms), re.I)


def load_denylist(path):
    """One term per line; `#` comments ignored. Terms are never echoed in full."""
    terms = []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            term = line.strip()
            if term and not term.startswith("#"):
                terms.append(term)
    return terms


# Single words that are ordinary English before they are anybody's name. A denylist built
# mechanically from folder names picks these up, and a scan of this repo with such a list
# returned 178 "client names", every one of them a word like `template` or `internal`.
# A scanner that cries wolf gets switched off, so precision is a safety property.
COMMON_WORDS = frozenset("""
template internal external enable enabled supported support weekly daily monthly client
clients team project projects brand content main start review reviews global local test
tests demo example sample draft final new old core base common shared public private
admin owner user users guide guides doc docs note notes task tasks work works asset assets
report reports plan plans setup config data info page pages site sites app apps service
""".split())


def _denylist_re(terms, allow_generic=False):
    """Returns (compiled_regex_or_None, ignored_terms).

    Generic single words are NOT silently dropped: a real client can be called Enable, and a
    silent drop is a false negative, which is worse than a false positive. They are reported
    so the operator decides, and `allow_generic` includes them.
    """
    parts, ignored = [], []
    for term in terms:
        words = [w for w in re.split(r"[\s_-]+", term.strip()) if w]
        if not words:
            continue
        if not allow_generic and len(words) == 1 and words[0].lower() in COMMON_WORDS:
            ignored.append(term)
            continue
        parts.append(r"\b" + r"[\s_-]?".join(re.escape(w) for w in words) + r"\b")
    if not parts:
        return None, ignored
    return re.compile("|".join(parts), re.I), ignored


def fingerprint(text, enumerable=False):
    """A stable short hash, so a finding can be reported without repeating the secret.

    `enumerable=True` returns no hash at all. A hash of a high-entropy API key is safe to
    publish; a hash of a client name or an internal URL is not, because anyone with a
    candidate list can confirm a guess against it. Those findings are located by path and
    line instead, which is all the operator needs to fix them.
    """
    if enumerable:
        return "-"
    return util.sha256_bytes(text.lower().encode("utf-8"))[:12]


def _text_views(data):
    """[(label, text)] - every way this byte string might be readable text.

    A latin-1 fallback is not a substitute for real decoding: a UTF-16 key decodes to
    `A\\x00K\\x00I\\x00A...`, which no pattern matches, and the file still ships the
    credential in plain sight of any editor. Reproduced 2026-09-22.
    """
    views = []
    try:
        views.append(("", data.decode("utf-8")))
    except UnicodeDecodeError:
        views.append(("", data.decode("latin-1", "replace")))
    if b"\x00" in data:
        for enc in ("utf-16-le", "utf-16-be"):
            try:
                decoded = data.decode(enc)
            except (UnicodeDecodeError, LookupError):
                continue
            if decoded and decoded.isprintable() or "\n" in decoded:
                views.append((" (%s)" % enc, decoded))
                break
        else:
            views.append((" (null-stripped)", data.replace(b"\x00", b"").decode("latin-1",
                                                                                "replace")))
    return views


def _archive_members(path, data):
    """[(member_path, bytes)] for a zip-based file (.zip, .docx, .xlsx, .pptx).

    A compressed member is unreadable to a regex, so an unopened archive is an unscanned
    file wearing a scanned file's clothes.
    """
    if not data[:4] == b"PK\x03\x04":
        return []
    import zipfile, io  # noqa: E401  (local: only needed for archives)
    out = []
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for info in zf.infolist()[:MAX_ARCHIVE_MEMBERS]:
                if info.is_dir() or info.file_size > MAX_ARCHIVE_MEMBER_BYTES:
                    continue
                try:
                    out.append(("%s!%s" % (path, info.filename), zf.read(info)))
                except Exception:
                    continue
    except Exception:
        return []
    return out


def _decoded_b64_blobs(data):
    """Base64 blobs decoded back to text, so an encoded key is not invisible."""
    import base64
    out = []
    for m in B64_RE.finditer(data[:MAX_SCAN_BYTES]):
        blob = m.group(0)
        if len(blob) > 4096:
            continue
        try:
            decoded = base64.b64decode(blob, validate=True)
        except Exception:
            continue
        if not decoded:
            continue
        try:
            out.append(decoded.decode("utf-8"))
        except UnicodeDecodeError:
            continue
    return out


def scan_bytes(path, data, deny_re=None, allow_re=None, _depth=0):
    """Findings for one file. A finding never carries the matched value.

    Binary files are scanned too. A secret pasted into a .docx is still a secret, and "we
    skipped the binaries" is how scanners come to mean nothing.
    """
    findings = []
    if len(data) > MAX_SCAN_BYTES:
        # Fail closed and say so, rather than scanning a prefix and reporting success.
        return [{"path": path, "line": 0, "kind": "unscanned",
                 "detail": "file is %d bytes, larger than the %d-byte scan limit"
                           % (len(data), MAX_SCAN_BYTES),
                 "fingerprint": "-"}]

    def add(kind, detail, lineno, matched, enumerable):
        findings.append({"path": path, "line": lineno, "kind": kind, "detail": detail,
                         "fingerprint": fingerprint(matched, enumerable=enumerable)})

    # The path itself can carry a client name even when the contents are innocent.
    if deny_re is not None and _depth == 0:
        pm = deny_re.search(path.replace("/", " "))
        if pm and not (allow_re is not None and allow_re.search(path.replace("/", " "))):
            add("client_name", "denylisted name in the file path", 0, pm.group(0), True)

    for suffix, text in _text_views(data):
        for lineno, line in enumerate(text.splitlines(), 1):
            allow_hit = allow_re.search(line) if allow_re is not None else None
            for m in SECRET_RE.finditer(line):
                if PLACEHOLDER_MATCH_RE.search(m.group(0)):
                    continue  # the MATCH is a placeholder, not the line it sits on
                add("secret", "credential-shaped literal" + suffix, lineno, m.group(0), False)
                break
            for rx, label in INTERNAL_RE:
                m2 = rx.search(line)
                if m2 and not PLACEHOLDER_MATCH_RE.search(m2.group(0)):
                    add("internal", label + suffix, lineno, m2.group(0), True)
            if deny_re is not None:
                m3 = deny_re.search(line)
                if m3 and not (allow_hit
                               and allow_hit.group(0).lower() == m3.group(0).lower()):
                    add("client_name", "denylisted name" + suffix, lineno, m3.group(0), True)

    for blob in _decoded_b64_blobs(data):
        m = SECRET_RE.search(blob)
        if m and not PLACEHOLDER_MATCH_RE.search(m.group(0)):
            add("secret", "credential-shaped literal (base64-encoded)", 0, m.group(0), False)

    if _depth < 2:
        for member_path, member_data in _archive_members(path, data):
            findings.extend(scan_bytes(member_path, member_data, deny_re, allow_re,
                                       _depth + 1))
    return findings


def scan_files(files, deny_re=None, allow_re=None):
    findings = []
    for path, data in files:
        findings.extend(scan_bytes(path, data, deny_re, allow_re))
    return findings


def scan_release(repo, rev, spec_paths, denylist_path=None, mode="release",
                 allow_generic=False, allowlist_path=None, acknowledge_generic=False):
    """Scan exactly the file set a release would ship.

    `mode='release'` requires a denylist: a portability claim made without the list of names
    you are checking for is not a claim, it is a hope.
    """
    deny_re, ignored = None, []
    if denylist_path:
        deny_re, ignored = _denylist_re(load_denylist(denylist_path), allow_generic)
        if ignored and mode == "release" and not acknowledge_generic:
            # Fail closed. With terms skipped, "no client names found" is only true of the
            # terms that were actually checked, and the report does not carry that caveat
            # into whatever reads it next.
            raise Refusal(
                EXIT_SANITIZE,
                "%d denylist term(s) are ordinary English words and were not checked"
                % len(ignored),
                ["terms: %s" % ", ".join(sorted(ignored)[:10]),
                 "either --allow-generic (check them, expect noise), or curate the denylist, "
                 "or --acknowledge-generic to record that you looked and accepted the gap"],
            )
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
    findings = scan_files(files, deny_re, load_allowlist(allowlist_path))
    return findings, len(files), ignored


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
