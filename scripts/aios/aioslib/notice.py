"""Release notice: tell an installed workspace, at most once a day, that a newer approved release exists.

LW-22 part 1. An upgrade only helps a client who knows it exists, and nothing told them. This is
read-only: it lists the template's public release tags and reads two public release records. It
writes nothing but its own one-line cache in `.aios/`, never upgrades anything, and says nothing
when offline or on any error.

A release is named only when both records agree it is approved: the one on `main` (so a release
later marked `superseded` or `withdrawn` is never advertised) and the one inside its tag, pinned to
the same commit (the record `check-tag` reads). The full byte-for-byte check stays with
`aios release check-tag`, which the upgrade route in docs/INSTALL_AND_UPGRADE.md runs first.

Python 3.9+, standard library only.
"""

import json
import os
import re
import subprocess
import time
import urllib.request

from . import install as install_mod
from . import util
from .util import Refusal

UPSTREAM = "https://github.com/funnel-futurist/ff-aios-starter"
RAW = "https://raw.githubusercontent.com/funnel-futurist/ff-aios-starter"
CACHE = os.path.join(".aios", "release_notice.json")
EVERY = 24 * 3600
RETRY = 3600         # after a failed or partial check, wait an hour, so offline costs one delay an hour
TIMEOUT = 5          # per network call
BUDGET = 8           # the whole check, all calls together
CANDIDATES = 3       # the newest few tags above the installed one; a release far behind still shows
TAG_RE = re.compile(r"refs/tags/starter-(\d+)\.(\d+)\.(\d+)$")


def _version(text):
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)$", text or "")
    return tuple(int(x) for x in m.groups()) if m else None


def list_tags(timeout=TIMEOUT):
    """[(major, minor, patch)] of the template's starter-X.Y.Z tags. [] on any failure."""
    try:
        out = subprocess.run(["git", "ls-remote", "--tags", UPSTREAM, "refs/tags/starter-*"],
                             capture_output=True, text=True, timeout=timeout, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    found = set()
    for line in out.splitlines():
        m = TAG_RE.search(line.strip())
        if m:
            found.add(tuple(int(x) for x in m.groups()))
    return sorted(found)


def fetch_record(ref, version, timeout=TIMEOUT):
    """The release record for `version` at `ref` (a branch or tag), or None on any failure."""
    url = "%s/%s/releases/starter-%s.json" % (RAW, ref, version)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (OSError, ValueError):
        return None


def newest_approved(installed, tags, fetch, limit=CANDIDATES):
    """(version, complete): the newest version above `installed` that main and its tag both record
    as approved, and whether every record needed to decide was actually read. An unread record is
    "unknown", not "not approved", so the caller doesn't cache a day of silence after a blip."""
    complete = True
    for ver in sorted((t for t in tags if t > installed), reverse=True)[:limit]:
        text = "%d.%d.%d" % ver
        on_main = fetch("main", text)
        if on_main is None:
            complete = False
            continue
        if on_main.get("status") != "approved":
            continue
        at_tag = fetch("starter-" + text, text)
        if at_tag is None:
            complete = False
            continue
        if at_tag.get("status") != "approved":
            continue
        pin = (on_main.get("created_from") or {}).get("git_rev")
        if not pin or (at_tag.get("created_from") or {}).get("git_rev") != pin:
            continue
        return text, complete
    return None, complete


def line_for(installed_text, newest_text):
    return ("Starter %s is approved; this workspace has %s. How to upgrade: "
            "docs/INSTALL_AND_UPGRADE.md (run `aios release check-tag` first)." % (newest_text, installed_text))


def check(target, now=None, tags_fn=None, fetch_fn=None, clock=time.monotonic):
    """One line to show, or None. At most one network check per day per workspace (an hour after a
    failed one), and never more than BUDGET seconds of network time."""
    if os.environ.get("AIOS_NO_RELEASE_NOTICE") == "1":
        return None                       # opt-out: no network check at all
    now = time.time() if now is None else now
    try:
        record = install_mod.load_record(target)
    except Refusal:
        return None                       # not an installed workspace (the template itself, say)
    installed_text = (record.get("release") or {}).get("version")
    installed = _version(installed_text)
    if installed is None:
        return None
    # Never a cache the repository tracks or reaches through a committed link: a pull request could make
    # every start print its own line, or break the start (independent review, 3.1 round 56).
    cached = util.read_local_cache(target, CACHE)
    try:
        if cached:
            window = EVERY if cached.get("complete", True) else RETRY
            line = cached.get("line")
            if cached.get("installed") == installed_text and now - float(cached.get("checked_at", 0)) < window \
                    and (line is None or isinstance(line, str)):
                return line
    except (TypeError, ValueError):
        pass

    deadline = clock() + BUDGET

    def remaining():
        return deadline - clock()

    def fetch(ref, version):
        if remaining() <= 0.5:
            return None                   # out of budget: unknown, not "not approved"
        if fetch_fn:
            return fetch_fn(ref, version)
        return fetch_record(ref, version, timeout=min(TIMEOUT, remaining()))

    tags = tags_fn() if tags_fn else list_tags(timeout=min(TIMEOUT, remaining()))
    if not tags:
        newest, complete = None, False    # offline or GitHub unreachable: say nothing
    else:
        newest, complete = newest_approved(installed, tags, fetch)
    line = line_for(installed_text, newest) if newest else None
    # Never over a file of the repository's (independent review, 3.1 round 55).
    util.write_local_cache(target, CACHE, {"checked_at": now, "installed": installed_text, "line": line,
                                           "complete": bool(newest or complete)})
    return line
