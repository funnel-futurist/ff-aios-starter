"""Protected-text scan: stop FF's protected method text from shipping in the public tree.

This repository is public and is a GitHub template. Some method text is deliberately public
(the files named in `release/public_methods.json`). Everything else FF holds as protected must
never land here, and "we were careful" is not a control. This module is the control.

## How it works, in four lines

1. A maintainer, privately, turns protected source files into a **fingerprint list**:
   every run of `window_tokens` consecutive words is normalised (lowercase, letters and digits
   only) and hashed with HMAC-SHA256 under a random salt, keeping the first 8 bytes.
2. That list lives **outside this repository**. Only fingerprints are in it, never text.
3. `aios protected scan` normalises every file in the public tree the same way and counts how
   many of its word-windows are in the list. `min_hits` or more from one source fails, so a
   pasted paragraph is caught however it is wrapped, re-cased or re-formatted.
4. The scan names the path and an opaque source label (`P-001`). It never prints text.

## What a fingerprint list can and cannot do

* It cannot be turned back into the text. Each entry is a keyed, truncated hash of one
  12-word window; there is no text in it, and 64 bits per window cannot be inverted.
* It CAN confirm a guess. Whoever holds the list and a candidate passage can test it. That is
  why the list is kept private anyway: the hash is a second wall, not the first.
* It does not catch a paraphrase, a translation, or text spread so thin that no 12 words in a
  row survive. It is a tripwire for copy and paste, which is how protected text actually leaks.
  It is not a proof that no protected idea is present.
* The allow-list (`release/public_methods.json`) exempts named files, and only the exact
  bytes a founder looked at: each entry pins the file's sha256, so adding protected text to an
  allowed file turns the check red until the entry is deliberately re-pinned.

Where it runs: the public CI runs the fixture tests (planted text must fail) and checks the
allow-list. The real scan runs where the private list lives (a maintainer's machine or a CI
secret). If the list is not there, the scan refuses to say "clean": not having looked is not
a result.

Python 3.9+, standard library only.
"""

import hashlib
import hmac
import json
import os
import re
import secrets
import subprocess
import unicodedata

from . import sanitize, util
from .util import EXIT_SANITIZE, Refusal

FINGERPRINT_SCHEMA = "ff-aios-starter/protected-fingerprints@1"
ALLOWLIST_SCHEMA = "ff-aios-starter/public-methods@1"
ALGORITHM = "hmac-sha256-trunc64"
DEFAULT_WINDOW = 12
DEFAULT_MIN_HITS = 3
DIGEST_BYTES = 8
ENV_LIST = "AIOS_PROTECTED_FINGERPRINTS"
DEFAULT_ALLOWLIST = "release/public_methods.json"

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_SKIP_DIRS = {".git", "node_modules", "__pycache__"}


# --- normalisation and hashing ------------------------------------------------------------

def tokens(text):
    """Lowercase words, letters and digits only. Punctuation, markdown and wrapping vanish."""
    return _TOKEN_RE.findall(unicodedata.normalize("NFKC", text).lower())


def _digest(salt, window):
    return hmac.new(salt, " ".join(window).encode("utf-8"), hashlib.sha256).digest()[:DIGEST_BYTES].hex()


def window_digests(text, salt, window_tokens):
    toks = tokens(text)
    if len(toks) < window_tokens:
        return set()
    return {_digest(salt, toks[i:i + window_tokens]) for i in range(len(toks) - window_tokens + 1)}


# --- building a list (private side) -------------------------------------------------------

def build_list(sources, window_tokens=DEFAULT_WINDOW, min_hits=DEFAULT_MIN_HITS, salt_hex=None):
    """sources: [(label, text)]. Returns the fingerprint-list dict. Carries no text.

    A source with fewer words than one window cannot be fingerprinted, and is refused rather
    than silently contributing nothing: a protected passage that is not in the list is a
    passage the scan will never find.
    """
    if window_tokens < 6:
        raise Refusal(EXIT_SANITIZE, "window_tokens must be at least 6: shorter windows match ordinary prose")
    if min_hits < 1:
        raise Refusal(EXIT_SANITIZE, "min_hits must be at least 1")
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    out = {}
    for label, text in sources:
        if not re.match(r"^[A-Za-z0-9_.-]{1,40}$", label):
            raise Refusal(EXIT_SANITIZE, "source label %r must be a short opaque id such as P-001" % label)
        digests = window_digests(text, salt, window_tokens)
        if not digests:
            raise Refusal(EXIT_SANITIZE,
                          "source %s has fewer than %d words, so nothing of it can be fingerprinted"
                          % (label, window_tokens))
        out[label] = sorted(digests)
    return {
        "schema": FINGERPRINT_SCHEMA,
        "algorithm": ALGORITHM,
        "window_tokens": window_tokens,
        "min_hits": min_hits,
        "salt": salt.hex(),
        "sources": out,
    }


def load_list(path):
    if not path or not os.path.isfile(path):
        raise Refusal(
            EXIT_SANITIZE,
            "no protected-fingerprint list: the scan cannot say 'clean' without having looked",
            ["pass --fingerprints <file>, or set %s" % ENV_LIST,
             "the list is private and lives OUTSIDE this repository; see release/PROTECTED_TEXT_SCAN.md"])
    data = util.read_json(path)
    if data.get("schema") != FINGERPRINT_SCHEMA or data.get("algorithm") != ALGORITHM:
        raise Refusal(EXIT_SANITIZE, "%s is not a %s list" % (path, FINGERPRINT_SCHEMA))
    for key in ("window_tokens", "min_hits", "salt", "sources"):
        if key not in data:
            raise Refusal(EXIT_SANITIZE, "fingerprint list is missing %r" % key)
    if not data["sources"]:
        raise Refusal(EXIT_SANITIZE, "the fingerprint list has no sources, so it would match nothing")
    return data


# --- the allow-list (public side) ---------------------------------------------------------

def load_allowlist(path):
    if not os.path.isfile(path):
        raise Refusal(EXIT_SANITIZE, "no public-methods allow-list at %s" % path,
                      ["the scan needs the explicit list of method files that are public on purpose"])
    data = util.read_json(path)
    if data.get("schema") != ALLOWLIST_SCHEMA:
        raise Refusal(EXIT_SANITIZE, "%s is not a %s file" % (path, ALLOWLIST_SCHEMA))
    return data


def check_allowlist(repo, allowlist):
    """Problems with the allow-list itself: stale paths, missing reasons, drifted bytes."""
    problems = []
    seen = set()
    for entry in allowlist.get("public_methods", []):
        path = entry.get("path", "")
        if path in seen:
            problems.append("%s is listed twice" % path)
        seen.add(path)
        if not util.safe_relpath(path):
            problems.append("unsafe path in the allow-list: %r" % path)
            continue
        if not (entry.get("reason") or "").strip():
            problems.append("%s has no reason: every public method file says why it is public" % path)
        full = os.path.join(repo, path)
        if not os.path.isfile(full):
            problems.append("%s is allow-listed but does not exist: remove the entry" % path)
            continue
        with open(full, "rb") as fh:
            now = util.sha256_bytes(fh.read())
        if now != entry.get("sha256"):
            problems.append("%s changed since a founder approved it as public (sha256 %s, approved %s): "
                            "re-review the change, then run `aios protected pin`"
                            % (path, now[:12], str(entry.get("sha256"))[:12]))
    return problems


def pin_allowlist(repo, allowlist_path):
    """Re-pin every entry to the file's current bytes. A reviewed act: the diff shows it."""
    data = load_allowlist(allowlist_path)
    for entry in data.get("public_methods", []):
        full = os.path.join(repo, entry["path"])
        with open(full, "rb") as fh:
            entry["sha256"] = util.sha256_bytes(fh.read())
    with open(allowlist_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    return data


# --- scanning the public tree -------------------------------------------------------------

def tracked_or_walked(repo):
    """Every file in the public tree: what git tracks, else everything under the directory."""
    if os.path.isdir(os.path.join(repo, ".git")):
        try:
            out = subprocess.check_output(["git", "-C", repo, "ls-files", "-z"], stderr=subprocess.DEVNULL)
            names = [n for n in out.decode("utf-8", "replace").split("\0") if n]
            return sorted(n for n in names if os.path.isfile(os.path.join(repo, n)))
        except (OSError, subprocess.CalledProcessError):
            pass
    found = []
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for name in files:
            found.append(os.path.relpath(os.path.join(root, name), repo).replace(os.sep, "/"))
    return sorted(found)


def _views(path, data):
    """Every readable text view of a file: itself (all encodings) and any archive members."""
    views = [text for _label, text in sanitize._text_views(data)]
    for _member, member_data in sanitize._archive_members(path, data):
        views.extend(text for _label, text in sanitize._text_views(member_data))
    return views


def scan_tree(repo, fp_list, allowlist=None):
    """Findings for the whole public tree. A finding never carries protected text.

    Returns (findings, scanned_count, allowed_paths).
    """
    salt = bytes.fromhex(fp_list["salt"])
    window = int(fp_list["window_tokens"])
    min_hits = int(fp_list["min_hits"])
    sources = {label: set(vals) for label, vals in fp_list["sources"].items()}
    allowed = {e["path"] for e in (allowlist or {}).get("public_methods", [])}
    findings, scanned, skipped = [], 0, []

    for rel in tracked_or_walked(repo):
        full = os.path.join(repo, rel)
        if os.path.islink(full):
            continue
        if os.path.getsize(full) > sanitize.MAX_SCAN_BYTES:
            findings.append({"path": rel, "source": "-", "hits": 0, "kind": "unscanned"})
            continue
        with open(full, "rb") as fh:
            data = fh.read()
        scanned += 1
        digests = set()
        for text in _views(rel, data):
            digests |= window_digests(text, salt, window)
        if not digests:
            continue
        for label, fps in sorted(sources.items()):
            hits = len(digests & fps)
            if hits >= min_hits:
                if rel in allowed:
                    skipped.append(rel)
                    break
                findings.append({"path": rel, "source": label, "hits": hits, "kind": "protected_text"})
    return findings, scanned, sorted(set(skipped))


def require_clean(findings):
    if not findings:
        return
    lines = []
    for f in findings[:40]:
        if f["kind"] == "unscanned":
            lines.append("%s: larger than the scan limit, so it was NOT scanned" % f["path"])
        else:
            lines.append("%s: %d windows of protected source %s" % (f["path"], f["hits"], f["source"]))
    if len(findings) > 40:
        lines.append("... and %d more" % (len(findings) - 40))
    lines.append("remove the text. If a file is meant to be public, a founder adds it to "
                 "release/public_methods.json with a reason; nothing else exempts it")
    raise Refusal(EXIT_SANITIZE, "protected text found in the public tree", lines)
