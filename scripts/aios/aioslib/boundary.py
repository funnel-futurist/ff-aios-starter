"""Founder-lane boundaries that are enforced, not just displayed.

`/start` tells an operator which paths are "not yours". Until 2.6.1 that was all it did: a
list on screen, and nothing stopped the edit. A product that claims a boundary has to hold
it, so this module enforces `paths_denied` at the two places an edit actually happens:

1. **In the session.** A Claude Code hook (`aios hook pre-edit`) refuses an Edit / Write /
   MultiEdit / NotebookEdit on a founder-lane path when the person working is not a founder.
   Somebody who cannot be identified gets the most restricted role, never the least.
2. **At the pull request.** `aios boundary check-pr` fails a PR whose author is not a founder
   when it touches a founder-lane path, until a founder approves that exact head commit. It
   reads the policy, the people map AND the checker itself from the BASE commit, so a PR
   cannot loosen the rule it is being checked against.

What this still does not stop, stated so nobody has to discover it:

* A person typing in their own terminal. The hook governs Claude, not the keyboard. The PR
  check catches the result, provided the change goes through a PR.
* A direct push to `main`. Only branch protection stops that, and only a repository admin can
  turn it on. `scripts/team/verify-branch-protection.sh` reports whether it is on.
* Shell commands Claude runs. Parsing a shell line reliably is not possible, so the hook does
  not pretend to. The PR check is the backstop.
"""

import json
import os
import shutil
import subprocess
import time

from . import governance, roles, util
from .util import EXIT_OK, EXIT_ROLE, Refusal

# The role an unidentified person is held to. The most restricted lane, never the least.
UNIDENTIFIED_ROLE = "operator"
# Roles whose approval satisfies the PR check for a founder-lane change.
APPROVER_ROLES = ("founder", "co_founder")

IDENTITY_CACHE = os.path.join(".aios", "usage", "identity.json")
IDENTITY_TTL_SECONDS = 15 * 60

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


def denied_for(policy, role):
    """Paths this role may not change. An unknown role gets the unidentified role's limits."""
    known = policy.get("roles") or {}
    if role not in known:
        role = UNIDENTIFIED_ROLE
    return roles.denied_paths(policy, role)


def violations(policy, role, paths):
    denied = denied_for(policy, role)
    # As the disk resolves each name, so a case or Windows spelling of a lane path is that path (C3).
    return sorted({p for p in paths if util.lane_match(denied, p)})


def _any_role_denies(policy, path):
    return any(util.lane_match(spec.get("paths_denied") or [], path)
               for spec in (policy.get("roles") or {}).values())


# ---------------------------------------------------------------------------------------------
# 1. The session hook
# ---------------------------------------------------------------------------------------------

def _gh_fingerprint():
    """What would change if somebody switched GitHub accounts.

    `gh auth login` / `gh auth switch` rewrite gh's hosts file, so its mtime is part of the
    fingerprint; so is the gh binary itself. Any change and the cached login is thrown away,
    so a switched account never keeps the previous person's role for the cache's lifetime.
    """
    parts = []
    gh = shutil.which("gh")
    for candidate in (gh, _gh_hosts_file()):
        try:
            parts.append("%s@%d" % (candidate, os.stat(candidate).st_mtime_ns) if candidate
                         else "-")
        except OSError:
            parts.append("%s@missing" % candidate)
    return "|".join(parts)


def _gh_hosts_file():
    base = os.environ.get("GH_CONFIG_DIR")
    if not base:
        xdg = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
        base = os.path.join(xdg, "gh")
    return os.path.join(base, "hosts.yml")


def _cached_identity(root):
    """gh costs about a second, and an edit should not. Cache the login briefly, gitignored."""
    # A copy the repository tracks, or one reached through a committed link, is the repository's file,
    # never this machine's cache; and nothing in it can raise here, since a hook that raises lets the
    # edit through (independent review, 3.1 rounds 55 and 56).
    cached = util.read_local_cache(root, IDENTITY_CACHE)
    fingerprint = _gh_fingerprint()
    try:
        fresh = time.time() - float(cached.get("at") or 0) < IDENTITY_TTL_SECONDS if cached else False
    except (TypeError, ValueError):
        fresh = False
    if fresh and isinstance(cached.get("login"), str) and cached["login"] and cached.get("gh") == fingerprint:
        return cached["login"]
    login, _source = roles.identity(timeout=5)
    if login:
        # Never over a file of the repository's; a read-only disk must not turn into a refusal either.
        util.write_local_cache(root, IDENTITY_CACHE, {"login": login, "at": time.time(), "gh": fingerprint})
    return login


def _relative_to_root(root, file_path):
    """The path relative to the workspace, or None if it points somewhere else entirely.

    realpath on both sides, so a symlink cannot smuggle an edit into a protected path.
    """
    if not file_path:
        return None
    full = file_path if os.path.isabs(file_path) else os.path.join(root, file_path)
    real_root = os.path.realpath(root)
    real = os.path.realpath(full)
    if real != real_root and not real.startswith(real_root + os.sep):
        return None
    return os.path.relpath(real, real_root).replace(os.sep, "/")


def check_edit(root, tool_name, tool_input, identify=None):
    """(allowed, reason). Pure enough to test without a Claude session."""
    if tool_name not in EDIT_TOOLS:
        return True, "not an edit tool"
    config_path = os.path.join(root, ".aios", "config.json")
    policy_path = os.path.join(root, roles.POLICY_PATH)
    if not os.path.isfile(config_path) or not os.path.isfile(policy_path):
        # Not an installed workspace (the template repository itself, for example). There is
        # no people map, so there are no roles to hold anybody to.
        return True, "no people map"
    policy = util.read_json(policy_path)
    rel = _relative_to_root(root, (tool_input or {}).get("file_path")
                            or (tool_input or {}).get("notebook_path"))
    if rel is None:
        return True, "outside this workspace"
    # Fast path: most edits touch nothing any role protects, and need no identity lookup.
    if not _any_role_denies(policy, rel):
        return True, "not a founder-lane path"
    config = util.read_json(config_path)
    login = (identify or _cached_identity)(root)
    role = roles.role_for(config, login)
    if not violations(policy, role, [rel]):
        return True, "role %s may change %s" % (role, rel)
    who = ("%s (%s)" % (login, role)) if role else (
        "%s (not in the people map)" % login if login else "an unidentified person")
    return False, (
        "%s belongs to the founder lane, and %s may not change it. Ask a founder to make "
        "this change, or open a pull request for %s to approve. If you are a founder and "
        "see this, run `gh auth login` so the workspace can tell who you are.%s" % (
            rel, who, lane_approver(policy), "" if login else " " + roles.WEB_NOTE + "."))


def lane_approver(policy):
    """Who approves a founder-lane pull request, as the role policy says: its declared
    founder_lane_reviewers when it declares them (the whole permission), else a founder (3.1 round 17)."""
    return ("an approved founder-lane reviewer (the role policy's founder_lane_reviewers)"
            if "founder_lane_reviewers" in (policy or {}) else "a founder or co-founder")


def hook_pre_edit(stdin_text, root=None):
    """Claude Code PreToolUse hook. Prints a deny decision, or nothing to allow."""
    try:
        event = json.loads(stdin_text or "{}")
    except ValueError:
        return EXIT_OK, None
    root = root or os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or os.getcwd()
    allowed, reason = check_edit(root, event.get("tool_name"), event.get("tool_input"))
    if allowed:
        return EXIT_OK, None
    return EXIT_OK, json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }})


# ---------------------------------------------------------------------------------------------
# 2. The pull-request check
# ---------------------------------------------------------------------------------------------

def _show_json(repo, rev, path):
    proc = subprocess.run(["git", "-C", repo, "show", "%s:%s" % (rev, path)],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout.decode("utf-8"))
    except ValueError:
        raise Refusal(EXIT_ROLE, "%s at %s is not valid JSON" % (path, rev[:12]))


def changed_paths(repo, base, head):
    """Every path the PR adds, edits, deletes or renames (both sides of a rename), as git stores it: NUL
    separated, so a name git would print quoted (a non-ASCII one) reaches the lane check unchanged (C3)."""
    out = util.git(repo, ["diff", "--name-only", "-z", "--no-renames", "%s...%s" % (base, head)], binary=True)
    return [p.decode("utf-8", "surrogateescape") for p in out.split(b"\0") if p]


def check_pr(repo, base, head, author, approvers):
    """(code, lines). Policy and people map come from BASE: the PR cannot rewrite its own rule."""
    policy = _show_json(repo, base, ".aios/roles.json")
    config = _show_json(repo, base, ".aios/config.json")
    if policy is None or config is None:
        return EXIT_OK, ["no people map on the base branch, so there are no roles to hold "
                         "this pull request to"]
    role = roles.role_for(config, author)
    hits = violations(policy, role, changed_paths(repo, base, head))
    who = "%s (%s)" % (author, role or "not in the people map")
    if not hits:
        return EXIT_OK, ["%s changed no founder-lane path" % who]
    # Who may approve the founder lane: founders and co-founders, or, when the base policy declares
    # them, its founder_lane_reviewers - review permission, not founder status (G98). Never the author.
    # When the base policy declares the reviewers, that list is the whole permission: a founder left
    # off it doesn't count either, and a declaration that can't be used counts nobody (fails closed;
    # independent review, 3.1 round 2).
    declared = "founder_lane_reviewers" in policy
    if declared:
        usable = governance.lane_reviewer_problems(policy, config) == []
        reviewers = governance.lane_reviewers(policy, config)[0] if usable else set()
        eligible = lambda a: ("@" + a.lower()) in reviewers  # noqa: E731
    else:
        eligible = lambda a: roles.role_for(config, a) in APPROVER_ROLES  # noqa: E731
    founder_approvals = sorted(a for a in approvers
                               if eligible(a) and a.lower() != (author or "").lower())
    if founder_approvals:
        return EXIT_OK, ["%s changed %d founder-lane path(s), approved at this commit by %s"
                         % (who, len(hits), ", ".join(founder_approvals))]
    whom = ("an approved founder-lane reviewer (the role policy's founder_lane_reviewers)" if declared
            else "a founder or co-founder")
    return EXIT_ROLE, (
        ["%s changed %d founder-lane path(s) without an approval of this commit from %s:"
         % (who, len(hits), whom)]
        + ["  - %s" % p for p in hits[:20]]
        + ["%s approves the pull request, then this check re-runs and passes. A new push needs a "
           "new approval." % (whom[0].upper() + whom[1:])])
