"""Organization config and credential *references*.

The rule this module exists to enforce: **a package and its config carry credential
references, never credential values.** `env:ANTHROPIC_API_KEY` is a reference. An actual key
is a leak, and a leak in a config file is a leak in git history five minutes later.

A missing required reference fails the install loudly and early. The failure mode this
prevents is the expensive one: a workspace that installs "successfully", looks fine, and
silently does half its job because a key was never wired up.
"""

import os
import re

from . import util
from .util import EXIT_CREDENTIAL, Refusal

SCHEMA = "ff-aios-starter/org-config@1"
GITHUB_HANDLE_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$")
REPO_SLUG_RE = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")
ORG_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,38}$")
CRED_REF_RE = re.compile(r"^(env|dotenv):([A-Z][A-Z0-9_]*)$")

# Values that mean "nobody filled this in". A config carrying one of these is not configured,
# however complete it looks.
PLACEHOLDER_RE = re.compile(
    r"(\[[A-Z_]+\]|your-?github-?username|yourname|your\.name|changeme|xxx+|<[a-z_ ]+>)", re.I)


def validate(config):
    """Return a list of problems. Never echoes a credential value."""
    problems = []
    if config.get("schema") != SCHEMA:
        problems.append("schema is %r, expected %r" % (config.get("schema"), SCHEMA))
    if not ORG_ID_RE.match(config.get("org_id", "") or ""):
        problems.append("org_id %r is not a slug" % config.get("org_id"))
    repo = config.get("repository", "") or ""
    if not REPO_SLUG_RE.match(repo):
        problems.append("repository %r is not owner/repo" % repo)
    if PLACEHOLDER_RE.search(repo):
        problems.append("repository %r is still a placeholder" % repo)

    people = config.get("people") or []
    if not people:
        problems.append("config lists no people")
    founders = 0
    for person in people:
        handle = person.get("github", "") or ""
        if not GITHUB_HANDLE_RE.match(handle):
            problems.append("person github %r is not a GitHub handle" % handle)
        if PLACEHOLDER_RE.search(handle):
            problems.append("person github %r is still a placeholder" % handle)
        role = person.get("role")
        if role not in ("founder", "co_founder", "operator"):
            problems.append("person %s has unknown role %r" % (handle or "?", role))
        if role in ("founder", "co_founder"):
            founders += 1
    if people and not founders:
        problems.append("config names no founder; somebody must own upgrades and governance")

    creds = config.get("credentials") or {}
    if not isinstance(creds, dict):
        problems.append("credentials must be a map of NAME -> reference")
        creds = {}
    for name, ref in sorted(creds.items()):
        if not isinstance(ref, str) or not CRED_REF_RE.match(ref):
            # Deliberately does not print `ref`: if somebody pasted a live key here, the
            # error message must not become the second place it leaks.
            problems.append(
                "credential %s must be a reference like env:%s or dotenv:%s, not a value"
                % (name, name, name))
    return problems


def require_valid(config):
    problems = validate(config)
    if problems:
        raise Refusal(EXIT_CREDENTIAL, "organization config is not usable", problems)


def _dotenv_names(path):
    """Names defined in a .env file. Reads names only; values are never returned."""
    names = {}
    if not os.path.isfile(path):
        return names
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            names[key.strip()] = bool(value.strip().strip("'\""))
    return names


def resolve(declared, config, target_root):
    """Resolve each credential the release declares. Returns rows, never values.

    row: {name, required, ref, resolved, reason}
    """
    creds = config.get("credentials") or {}
    dotenv_cache = None
    rows = []
    for entry in declared or []:
        name = entry.get("name")
        required = bool(entry.get("required"))
        ref = creds.get(name)
        if not ref:
            rows.append({
                "name": name, "required": required, "ref": None, "resolved": False,
                "reason": "no reference in organization config",
            })
            continue
        m = CRED_REF_RE.match(ref)
        if not m:
            rows.append({
                "name": name, "required": required, "ref": "<invalid>", "resolved": False,
                "reason": "reference is not env:NAME or dotenv:NAME",
            })
            continue
        scheme, var = m.group(1), m.group(2)
        if scheme == "env":
            ok = bool((os.environ.get(var) or "").strip())
            reason = "" if ok else "environment variable %s is unset or empty" % var
        else:
            if dotenv_cache is None:
                dotenv_cache = _dotenv_names(os.path.join(target_root, ".env"))
            ok = dotenv_cache.get(var, False)
            reason = "" if ok else ".env does not define a non-empty %s" % var
        rows.append({
            "name": name, "required": required, "ref": ref, "resolved": ok, "reason": reason,
        })
    return rows


def require_resolved(rows):
    """Fail loudly on a missing *required* credential.

    Optional credentials that are absent are reported explicitly by the caller. Silence is
    the thing we are avoiding: an unconfigured optional integration must be visible, not
    inferred from something not working later.
    """
    missing = [r for r in rows if r["required"] and not r["resolved"]]
    if missing:
        raise Refusal(
            EXIT_CREDENTIAL,
            "required credential reference did not resolve",
            ["%s: %s" % (r["name"], r["reason"]) for r in missing],
        )


def default_config_path(target_root):
    return os.path.join(target_root, ".aios", "config.json")


def load(target_root):
    path = default_config_path(target_root)
    if not os.path.isfile(path):
        raise Refusal(EXIT_CREDENTIAL, "no organization config at %s" % path)
    return util.read_json(path)
