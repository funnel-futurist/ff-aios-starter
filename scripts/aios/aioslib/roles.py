"""Identity, role and role-scoped entry.

**Be honest about what this is.** A local checkout cannot authenticate anybody. The repo
already says so about `.aios/local-operator.json`: *"it is NOT a login or a security
boundary"*. This module keeps that promise instead of quietly pretending otherwise.

So role is resolved from two things, in this order:

1. **Identity** from the authenticated GitHub CLI (`gh api user`), not from a file the
   operator writes about themselves.
2. **Role** from `.aios/config.json`, the organization's committed people map, which sits on
   a CODEOWNERS-protected path so changing it needs a code owner's review.

That makes the guardrail real *at the repository boundary* - where merges happen - and
advisory on the local disk, where anyone can edit any file. The security boundary is GitHub
permissions and branch protection. This is the thing that stops an honest operator walking
into the founder's lane by accident, and it is not a thing that stops an attacker who
already has your laptop.

Which is exactly why the CODEOWNERS defect matters: with no code-owner rule and no branch
protection, the people map is editable by anyone with write access and nobody reviews it.
Role scoping inherits the strength of that gate.
"""

import os
import subprocess

from . import util
from .util import EXIT_ROLE, Refusal

SCHEMA = "ff-aios-starter/roles@1"
POLICY_PATH = os.path.join(".aios", "roles.json")


def load_policy(root):
    path = os.path.join(root, POLICY_PATH)
    if not os.path.isfile(path):
        raise Refusal(EXIT_ROLE, "no role policy at %s" % path)
    policy = util.read_json(path)
    if policy.get("schema") != SCHEMA:
        raise Refusal(EXIT_ROLE, "role policy schema is %r, expected %r"
                      % (policy.get("schema"), SCHEMA))
    return policy


def identity(timeout=10):
    """(login, source). Never invents one: unknown identity gets no role."""
    # Deliberately no environment override. A test harness proves role scoping by putting a
    # stub `gh` on PATH and exercising this exact code path; an override would mean the
    # thing shipped is not the thing tested, and it would be a bypass on every real machine.
    try:
        proc = subprocess.run(
            ["gh", "api", "user", "--jq", ".login"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return None, "gh unavailable"
    if proc.returncode != 0:
        return None, "gh not authenticated"
    login = proc.stdout.decode("utf-8", "replace").strip()
    return (login or None), "gh api user"


def role_for(config, login):
    if not login:
        return None
    for person in config.get("people") or []:
        if (person.get("github") or "").lower() == login.lower():
            return person.get("role")
    return None


def require_role(config, allowed, action):
    """Resolve identity -> role and refuse unless the role is allowed for this action."""
    login, source = identity()
    if not login:
        raise Refusal(
            EXIT_ROLE,
            "cannot establish who is running this (%s)" % source,
            ["run `gh auth login` so the workspace can tell who you are",
             "least privilege: an unidentified operator gets no role, so nothing runs"],
        )
    role = role_for(config, login)
    if role is None:
        raise Refusal(
            EXIT_ROLE,
            "%s is not in this workspace's people map, so has no role" % login,
            ["a founder must add them to .aios/config.json (a code-owner-reviewed path)"],
        )
    if role not in allowed:
        raise Refusal(
            EXIT_ROLE,
            "role %r may not run %s" % (role, action),
            ["%s requires one of: %s" % (action, ", ".join(sorted(allowed))),
             "identity %s resolved from %s" % (login, source)],
        )
    return login, role


def lifecycle_roles(policy, action):
    return {name for name, spec in (policy.get("roles") or {}).items()
            if action in (spec.get("lifecycle") or [])}


def require_lifecycle(policy, config, action):
    allowed = lifecycle_roles(policy, action)
    if not allowed:
        raise Refusal(EXIT_ROLE, "no role in the policy may run %s" % action)
    return require_role(config, allowed, action)


def entries_for(policy, role):
    return ((policy.get("roles") or {}).get(role) or {}).get("entries") or []


def resolve_entry(policy, role, requested):
    """The founder-scoped path is unreachable for a role that does not carry it."""
    allowed = entries_for(policy, role)
    if not allowed:
        raise Refusal(EXIT_ROLE, "role %r has no entry point" % role)
    if requested is None:
        return allowed[0]
    if requested not in allowed:
        raise Refusal(
            EXIT_ROLE,
            "role %r may not enter the %r workspace" % (role, requested),
            ["%r may enter: %s" % (role, ", ".join(allowed)),
             "ask a founder if you believe your role is wrong; do not edit the people map yourself"],
        )
    return requested


def denied_paths(policy, role):
    return ((policy.get("roles") or {}).get(role) or {}).get("paths_denied") or []


def path_allowed(policy, role, path):
    return not util.match_any(denied_paths(policy, role), path)
