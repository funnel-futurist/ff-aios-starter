"""CODEOWNERS: the check that makes an unfilled template loud instead of silent.

The defect this exists for: `.github/CODEOWNERS` shipped with literal `[REPO_OWNER]`
placeholders. GitHub treats an unparseable owner as *no owner*, so the rule matches nobody
and enforces nothing - while the file's presence makes every reader believe it does. The
repo's own drift detector checked only that the file **exists**, which a placeholder file
does, so the detector reported green over a dead gate.

Three checks, because there are three distinct ways this file lies:

* **placeholder** - `[ANYTHING]` in an owner position. Nobody filled it in.
* **binding** - the file declares which repository it was written for. A repo generated from
  this template inherits the template's owners, who have no access there, so the rule again
  matches nobody. The binding line turns that inheritance into an error instead of a silent
  downgrade.
* **syntax** - an owner must be `@user`, `@org/team` or an email, or GitHub ignores it.

None of this makes ownership *enforced*. Enforcement is branch protection with "require
review from Code Owners", which lives in repository settings and needs an admin. This check
proves the file is real; a human still has to turn the gate on.
"""

import json
import os
import re

from . import util
from .util import EXIT_GOVERNANCE, Refusal

PLACEHOLDER_RE = re.compile(r"\[[A-Za-z0-9_ -]+\]")
OWNER_RE = re.compile(r"^(@[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:/[A-Za-z0-9._-]+)?"
                      r"|[^@\s]+@[^@\s]+\.[A-Za-z]{2,})$")
BINDING_RE = re.compile(r"^#\s*aios-codeowners-for:\s*([A-Za-z0-9._-]+/[A-Za-z0-9._-]+)\s*$",
                        re.M)
LOCATIONS = (os.path.join(".github", "CODEOWNERS"), "CODEOWNERS", os.path.join("docs", "CODEOWNERS"))


def find_file(root):
    for rel in LOCATIONS:
        path = os.path.join(root, rel)
        if os.path.isfile(path):
            return rel, path
    return None, None


def current_repo_slug(root):
    """(slug, source). GITHUB_REPOSITORY in CI when `root` is CI's own checkout, else the origin
    remote. A CI job working on another workspace must not lend it the CI repository's name
    (independent review)."""
    env, ws = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_WORKSPACE")
    if env and (not ws or os.path.realpath(ws) == os.path.realpath(root)):
        return env.strip(), "GITHUB_REPOSITORY"
    if util.is_git_repo(root):
        try:
            url = util.git(root, ["remote", "get-url", "origin"])
        except Refusal:
            return None, "no origin remote"
        m = re.search(r"[:/]([A-Za-z0-9._-]+/[A-Za-z0-9._-]+?)(?:\.git)?/?$", url or "")
        if m:
            return m.group(1), "origin remote"
    return None, "could not determine repository"


def parse(text):
    """[(lineno, pattern, [owners])] for each rule line."""
    rules = []
    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        rules.append((lineno, parts[0], parts[1:]))
    return rules


def check(root, expected_slug=None, config=None):
    """Return a list of problems. Empty means the file names real, in-scope owners."""
    rel, path = find_file(root)
    if not path:
        return ["no CODEOWNERS file (looked in %s)" % ", ".join(LOCATIONS)]

    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    return check_text(text, rel, root, expected_slug, config)


def check_text(text, rel, root, expected_slug=None, config=None):
    """`check` on CODEOWNERS text, so install can check what it rendered before it writes."""
    problems = []
    rules = parse(text)
    if not rules:
        problems.append("%s defines no rules, so it protects nothing" % rel)

    for lineno, pattern, owners in rules:
        if not owners:
            problems.append("%s:%d rule %s has no owner" % (rel, lineno, pattern))
        for owner in owners:
            if PLACEHOLDER_RE.search(owner):
                problems.append(
                    "%s:%d owner %s is an unresolved placeholder - GitHub matches nobody, so this "
                    "rule enforces nothing" % (rel, lineno, owner))
            elif not OWNER_RE.match(owner):
                problems.append("%s:%d owner %r is not @user, @org/team or an email"
                                % (rel, lineno, owner))

    # Any placeholder anywhere else in the file (including comments) is still an unfinished
    # template, but only owner-position ones break enforcement, so report them separately.
    for lineno, line in enumerate(text.splitlines(), 1):
        if line.strip().startswith("#") and PLACEHOLDER_RE.search(line):
            problems.append("%s:%d placeholder left in a comment: %s"
                            % (rel, lineno, PLACEHOLDER_RE.search(line).group(0)))

    m = BINDING_RE.search(text)
    if not m:
        problems.append(
            "%s has no `# aios-codeowners-for: <owner>/<repo>` line, so there is nothing to stop a "
            "repo generated from this template inheriting owners who have no access to it" % rel)
    else:
        bound = m.group(1)
        slug = expected_slug
        source = "argument"
        if not slug:
            slug, source = current_repo_slug(root)
        if slug and bound.lower() != slug.lower():
            problems.append(
                "%s was written for %s but this repository is %s (%s) - those owners have no "
                "access here, so the rules match nobody" % (rel, bound, slug, source))

    if config:
        known = {(p.get("github") or "").lower() for p in config.get("people") or []}
        for lineno, _pattern, owners in rules:
            for owner in owners:
                if owner.startswith("@") and "/" not in owner:
                    if known and owner[1:].lower() not in known:
                        problems.append(
                            "%s:%d owner %s is not in this workspace's people map"
                            % (rel, lineno, owner))
    return problems


def require_ok(root, expected_slug=None, config=None):
    problems = check(root, expected_slug, config)
    if problems:
        raise Refusal(EXIT_GOVERNANCE, "CODEOWNERS does not enforce anything", problems)


def render(template_text, repo_slug, owners):
    """Fill a CODEOWNERS template. Refuses to emit a file that is still a template.

    `owners` maps placeholder name -> list of owner tokens, e.g.
    {"REPO_OWNER": ["@alice"], "PRIMARY_REVIEWER": ["@bob"]}.
    """
    out_lines = []
    for line in template_text.splitlines():
        stripped = line.strip()
        if not stripped:
            out_lines.append(line)
            continue
        if stripped.startswith("#"):
            # Instruction comments explain the placeholders. Once rendered they are
            # misleading ("@alice = the founder"), so a comment naming a placeholder is
            # template scaffolding and does not belong in the output.
            if PLACEHOLDER_RE.search(line):
                continue
            out_lines.append(line)
            continue

        parts = line.split()
        pattern, tokens = parts[0], parts[1:]
        resolved = []
        for token in tokens:
            m = PLACEHOLDER_RE.fullmatch(token)
            if not m:
                resolved.append(token)
                continue
            handles = owners.get(token[1:-1]) or []
            # An optional role nobody filled is dropped, never emitted: a placeholder left in
            # an owner position is precisely the defect this whole module exists for.
            resolved.extend(handles)
        if not resolved:
            # Every owner on this rule was unfilled. Dropping the rule would quietly leave a
            # catastrophic path with NO owner, which is the same silent weakening as the
            # placeholder itself. Make the human decide.
            raise Refusal(
                EXIT_GOVERNANCE,
                "no owner supplied for the rule %s" % pattern,
                ["supply a handle for %s, or delete the rule from the template on purpose"
                 % ", ".join(sorted(set(PLACEHOLDER_RE.findall(line))))],
            )
        out_lines.append("%-27s %s" % (pattern, " ".join(resolved)))
    text = "\n".join(out_lines).rstrip("\n") + "\n"

    binding = "# aios-codeowners-for: %s\n" % repo_slug
    if not BINDING_RE.search(text):
        lines = text.splitlines(True)
        text = (lines[0] if lines else "") + binding + "".join(lines[1:])
    else:
        text = BINDING_RE.sub(binding.rstrip("\n"), text)

    leftover = PLACEHOLDER_RE.findall(text)
    if leftover:
        raise Refusal(
            EXIT_GOVERNANCE,
            "rendered CODEOWNERS still contains placeholders: %s" % ", ".join(sorted(set(leftover))),
            ["supply a handle for each, or remove the rule from the template"],
        )
    return text


# ─── founder review at the paths the founder lane actually uses ─────────────────────────────
#
# Founder requirement (2026-10-14, Starter 3.0): "Verify founder-review protection at the new
# paths. instance check must fail visibly until it is restored." CODEOWNERS is rendered once per
# workspace and never rewritten by an upgrade, so after the 3.0 folder move it can still name the
# old founder-only folder, and GitHub then silently stops asking a founder. Two things have to be
# true, and both are checked: CODEOWNERS sends every founder-lane path to a founder, and GitHub
# enforces code-owner review on the default branch.

FOUNDER_ROLES = ("founder", "co_founder")


def _pattern_regex(pattern):
    """GitHub's CODEOWNERS pattern rules, as a regex over a repository path.

    gitignore-style, with GitHub's own reading of a trailing wildcard: `docs/*` matches
    `docs/a.md` but not `docs/sub/a.md` (GitHub's docs say so in as many words). A pattern
    whose last part is a plain name (`/scripts/aios`, `apps/`, `**/logs`) also covers everything
    inside that folder. A leading `/` or a `/` in the middle anchors it to the root.
    """
    anchored = pattern.startswith("/") or "/" in pattern.rstrip("/")
    body = pattern.lstrip("/")
    dir_only = body.endswith("/")
    body = body.rstrip("/")
    last = body.rsplit("/", 1)[-1]
    out, i = "", 0
    while i < len(body):
        if body.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif body.startswith("/**", i) and i + 3 == len(body):
            out += "/.*"
            i += 3
        elif body.startswith("**", i):
            out += ".*"
            i += 2
        elif body[i] == "*":
            out += "[^/]*"
            i += 1
        elif body[i] == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(body[i])
            i += 1
    if dir_only:
        tail = "/.*"
    elif body.endswith("/**") or any(c in last for c in "*?"):
        tail = ""
    else:
        tail = "(?:/.*)?"
    return re.compile(("^" if anchored else "^(?:.*/)?") + out + tail + "$")


def owners_for(rules, path):
    """(pattern, owners) of the rule GitHub applies to `path`: the LAST matching one."""
    hit = (None, [])
    for _lineno, pattern, owners in rules:
        if _pattern_regex(pattern).match(path):
            hit = (pattern, owners)
    return hit


def _component_regex(part):
    out = ""
    for ch in part:
        out += "[^/]*" if ch == "*" else "[^/]" if ch == "?" else re.escape(ch)
    return re.compile("^" + out + "$")


def _anchored(pattern):
    return pattern.startswith("/") or "/" in pattern.rstrip("/")


def _covers(pattern, base):
    """Does this rule match EVERY path inside the folder `base`? Exact for GitHub's syntax."""
    if not _anchored(pattern):
        body = pattern.rstrip("/")
        # `*` (or `**`) matches every file at any depth; a plain folder name matches that folder
        # wherever it is, so it covers `base` if `base` ends in it, or in any folder above it.
        if body in ("*", "**"):
            return True
        if not any(c in body for c in "*?"):
            return body in base.split("/")
        return False
    parts = pattern.strip("/").split("/")
    bparts = base.split("/")
    for i, part in enumerate(parts):
        if part == "**":
            return i == len(parts) - 1  # `x/**` covers; `x/**/y` doesn't cover everything
        if i >= len(bparts):
            return False  # the rule only reaches inside base, not all of it
        if not _component_regex(part).match(bparts[i]):
            return False
    last = parts[-1]
    # the rule names base or a folder above it; its last part must be a plain name (or end in /)
    return not any(c in last for c in "*?") or pattern.endswith("/")


def _overlaps(pattern, base):
    """Could this rule match ANY path inside the folder `base`? Errs towards yes."""
    if not _anchored(pattern):
        return True  # it can match at any depth, so inside base too
    parts = pattern.strip("/").split("/")
    bparts = base.split("/")
    for i, part in enumerate(parts):
        if part == "**":
            return True
        if i >= len(bparts):
            return True  # the rule continues inside base
        if not _component_regex(part).match(bparts[i]):
            return False
    # every part of the rule matched a folder at or above base
    last = parts[-1]
    if pattern.endswith("/") or not any(c in last for c in "*?"):
        return True  # names a folder at or above base, so everything inside
    return False  # a wildcard last part matches only files at that level, not inside base


def founders_only(owners, founders):
    """Every owner on the rule is a founder. GitHub accepts ANY listed owner's approval, so one
    non-founder on the rule means founder review isn't required (independent review, round 3).
    A team can't be checked from here, so it doesn't count as a founder."""
    named = {o.lower() for o in owners}
    return bool(named) and named <= set(founders)


def lane_coverage(rules, base, founders, noun="founders"):
    """(ok, detail) for every path inside `base`, proven, not sampled: the last rule that covers the
    whole folder names a founder, and so does every later rule that could match anything in it.
    (GitHub applies the last matching rule, so those are the only rules that can decide a path.)"""
    last_cover = None
    for idx, (_lineno, pattern, owners) in enumerate(rules):
        if _covers(pattern, base):
            last_cover = idx
    if last_cover is None:
        return False, "no rule covers the whole folder, so some files in it reach no founder"
    _l, pattern, owners = rules[last_cover]
    if not founders_only(owners, founders):
        return False, "the last rule covering the whole folder (%s) names %s: not only %s, and " \
                      "GitHub accepts any one of them" % (pattern, " ".join(owners) or "nobody", noun)
    for _lineno, later, later_owners in rules[last_cover + 1:]:
        if _overlaps(later, base) and not founders_only(later_owners, founders):
            return False, "a later rule (%s, owned by %s) takes over files in it, and not only %s " \
                          "own it" % (later, " ".join(later_owners) or "nobody", noun)
    return True, "%s sends it to %s, and no later rule takes any of it away" % (pattern, " ".join(owners))


def founder_lane_paths(policy):
    out = []
    for role in (policy.get("roles") or {}).values():
        for p in role.get("paths_denied") or []:
            if p not in out:
                out.append(p)
    return out


def _probe(glob):
    """A concrete path inside a founder-lane glob, or None if the glob is too loose to sample."""
    if glob.endswith("/**"):
        base = glob[:-3]
        return None if any(c in base for c in "*?[") else base + "/aios-probe.md"
    return None if any(c in glob for c in "*?[") else glob


def founder_rules_check(rules, policy, founders, where, noun="founders"):
    """[(status, detail)] for each founder-lane path against one CODEOWNERS file's rules. `founders`
    is whoever may approve the founder lane: see lane_reviewers."""
    out = []
    for glob in founder_lane_paths(policy):
        if glob.endswith("/**") and not any(c in glob[:-3] for c in "*?["):
            ok, detail = lane_coverage(rules, glob[:-3], founders, noun)
        elif not any(c in glob for c in "*?["):
            pattern, owners = owners_for(rules, glob)
            ok = bool(pattern) and founders_only(owners, founders)
            detail = ("%s sends it to %s" % (pattern, " ".join(owners)) if ok else
                      "no rule covers it" if not pattern else
                      "the rule that applies (%s) names %s: not only %s, and GitHub accepts any "
                      "one of them" % (pattern, " ".join(owners) or "nobody", noun))
        else:
            ok, detail = False, "too broad to check, so it can't be shown to reach a founder"
        out.append(("PASS" if ok else "FAIL", "founder lane %s (%s): %s" % (glob, where, detail)))
    return out


REVIEWER_RE = re.compile(r"^@?[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$")
REVIEWERS_NOUN = "approved founder-lane reviewers"


def lane_reviewers(policy, config):
    """(accounts, declared): whose CODEOWNERS approval counts as founder-lane review.

    By default the founders and co-founders in the people map, as before. An instance can declare
    the accounts separately in its role policy, `founder_lane_reviewers`: that is review permission
    on the founder lane, never business founder status, which stays the people map's `role`
    (Phoenix, 2026-10-15, G98: "business founder role separate from CODEOWNER permission")."""
    # Declared by the key being there at all: `null` is a declaration nobody can use, never "absent"
    # (which would let founders count again; independent review, 3.1 round 3).
    if "founder_lane_reviewers" not in (policy or {}):
        return set(founders_of(config)), False
    declared = policy["founder_lane_reviewers"]
    if not isinstance(declared, list):
        return set(), True
    return {"@" + h.strip().lstrip("@").lower() for h in declared
            if isinstance(h, str) and REVIEWER_RE.match(h.strip())}, True


def lane_reviewer_problems(policy, config):
    """Why the declared founder-lane reviewers can't be used, if they're declared at all."""
    if "founder_lane_reviewers" not in (policy or {}):
        return []
    declared = policy["founder_lane_reviewers"]
    if not isinstance(declared, list) or not declared:
        return ["the role policy's founder_lane_reviewers must be a non-empty list of GitHub accounts"]
    known = {(p.get("github") or "").lower() for p in (config or {}).get("people") or []}
    out = []
    for h in declared:
        if not isinstance(h, str) or not REVIEWER_RE.match(h.strip()):
            out.append("founder_lane_reviewers: %r is not one GitHub account (a team can't be checked "
                       "from here)" % (h,))
        elif h.strip().lstrip("@").lower() not in known:
            out.append("founder_lane_reviewers: %s is not in this workspace's people map" % h.strip())
    return out


def founders_of(config):
    return sorted({("@" + (p.get("github") or "")).lower() for p in (config or {}).get("people") or []
                   if p.get("role") in FOUNDER_ROLES and p.get("github")})


def ownership_lane_check(policy, paths):
    """[(status, detail)] for the files that say which files are the installer's own (the install
    record, and an adoption's plan). An upgrade or the undo trusts that list, so a pull request that
    changes it needs a founder's approval, by the same founder-lane rule as every other sensitive
    path: each one is denied to every role that isn't a founder, and to the role an unidentified
    author is held to. A policy that leaves one open fails (3.1, owner decision C3)."""
    from . import boundary  # boundary imports this module

    defined = policy.get("roles") or {}
    held = sorted({r for r in defined if r not in FOUNDER_ROLES} | {boundary.UNIDENTIFIED_ROLE})
    out = []
    for path in paths:
        open_to = [r for r in held if not util.lane_match(
            (defined.get(r) or {}).get("paths_denied") or [], path)]
        if open_to:
            out.append(("FAIL", "ownership list %s: the role policy lets %s change it without founder-lane "
                                "approval, so a pull request could change which files the installer treats "
                                "as its own; add it to paths_denied for %s in .aios/roles.json, and give it "
                                "a CODEOWNERS rule" % (path, ", ".join(open_to), "them" if len(open_to) > 1
                                                       else "that role")))
        else:
            out.append(("PASS", "ownership list %s: in the founder lane, so a pull request from anyone who "
                                "isn't a founder needs founder-lane approval to change it" % path))
    return out


def ownership_held(root, policy, config, paths, also_reviewed=()):
    """Whether this workspace holds every path in `paths` to founder review: the role policy keeps each in the
    founder lane (ownership_lane_check), and CODEOWNERS sends it to founder-lane reviewers. `also_reviewed` are
    paths the policy's founder lane already names, which need only the CODEOWNERS half. That half is judged as
    `instance check` judges it, entry by entry: every founder-lane entry that covers one of the paths (the file
    itself, or a folder holding it) must pass founder_rules_check. No CODEOWNERS file, an unusable reviewer
    declaration or no founder at all means it isn't held (3.1, C3)."""
    if any(st == "FAIL" for st, _d in ownership_lane_check(policy, paths)):
        return False
    rel, path = find_file(root)
    if not path or lane_reviewer_problems(policy, config):
        return False
    founders, declared = lane_reviewers(policy, config)
    if not founders:
        return False
    with open(path, encoding="utf-8", errors="replace") as fh:
        rules = parse(fh.read())
    targets = list(paths) + list(also_reviewed)
    entries = [g for g in founder_lane_paths(policy) if any(util.lane_match([g], p) for p in targets)]
    if not entries:
        return not targets
    return all(st == "PASS" for st, _d in founder_rules_check(
        rules, {"roles": {"lane": {"paths_denied": entries}}}, founders, rel,
        REVIEWERS_NOUN if declared else "founders"))


def founder_review_local(root, policy, config, retired_folders=(), ownership=()):
    """[(status, detail)] from the files alone: does CODEOWNERS send every path in the founder
    lane to a founder? Also flags rules that still guard a folder the 3.0 move retired, and, given
    the workspace's ownership list (see ownership_lane_check), any of it left outside the lane."""
    out = list(ownership_lane_check(policy, ownership))
    rel, path = find_file(root)
    if not path:
        return out + [("FAIL", "no CODEOWNERS file, so GitHub asks no founder about the founder lane")]
    with open(path, encoding="utf-8", errors="replace") as fh:
        rules = parse(fh.read())
    founders, declared = lane_reviewers(policy, config)
    problems = lane_reviewer_problems(policy, config)
    if problems:
        return out + [("FAIL", p) for p in problems]
    if not founders:
        return out + [("FAIL", "no founder in this workspace's people map (.aios/config.json), so no rule "
                         "can send the founder lane to one")]
    if declared:
        out.append(("INFO", "founder-lane review is the role policy's founder_lane_reviewers (%s): "
                            "permission to approve those paths, not founder status, which is each "
                            "person's role in the people map" % " ".join(sorted(founders))))
    out.extend(founder_rules_check(rules, policy, founders, rel, REVIEWERS_NOUN if declared else "founders"))
    for _lineno, pattern, _owners in rules:
        first = pattern.lstrip("/").split("/", 1)[0]
        if first in retired_folders and not os.path.exists(os.path.join(root, first)):
            out.append(("FAIL", "%s still guards %s, a folder that no longer exists after the 3.0 "
                                "move: that rule now protects nothing" % (rel, pattern)))
    return out


def _gh_raw(args):
    """(text, error) for a raw `gh api` read."""
    import subprocess

    try:
        proc = subprocess.run(["gh", "api"] + args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, "gh could not run (%s)" % exc
    if proc.returncode != 0:
        return None, proc.stderr.decode("utf-8", "replace").strip() or "gh api failed"
    return proc.stdout.decode("utf-8", "replace"), None


def _gh_json(args):
    import subprocess

    try:
        proc = subprocess.run(["gh", "api"] + args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, "gh could not run (%s)" % exc
    text = proc.stdout.decode("utf-8", "replace")
    try:
        data = json.loads(text) if text.strip() else None
    except ValueError:
        data = None
    if proc.returncode != 0:
        msg = (data or {}).get("message") if isinstance(data, dict) else None
        return None, msg or proc.stderr.decode("utf-8", "replace").strip() or "gh api failed"
    return data, None


def target_repo_slug(target):
    """The GitHub repository the workspace at `target` belongs to (see current_repo_slug)."""
    return current_repo_slug(target)[0]


MAX_CODEOWNERS_BYTES = 3 * 1024 * 1024  # GitHub ignores a larger file


def remote_codeowners(slug):
    """(branch, location, text, problems): the CODEOWNERS GitHub actually enforces, which is the
    one on the default branch (the base of every pull request), not the local copy."""
    repo, err = _gh_json(["repos/%s" % slug])
    if err:
        return None, None, None, ["couldn't read %s from GitHub (%s)" % (slug, err)]
    branch = repo.get("default_branch") or "main"
    for loc in (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS"):
        path = "repos/%s/contents/%s?ref=%s" % (slug, loc, branch)
        # The object media type: the default one refuses files over 1 MB (GitHub's contents docs),
        # which would make a large but valid file look unreadable (independent review, round 5).
        data, err = _gh_json([path, "-H", "Accept: application/vnd.github.object"])
        if err:
            # GitHub uses the FIRST location that exists, so only a confirmed absence moves on.
            # Any other failure is unverified, never a reason to judge a different file.
            if "not found" in err.lower():
                continue
            return branch, loc, None, ["couldn't read %s on %s (%s)" % (loc, branch, err)]
        if not isinstance(data, dict) or data.get("type") not in (None, "file"):
            return branch, loc, None, ["%s on %s isn't a file" % (loc, branch)]
        problems = []
        if (data.get("size") or 0) >= MAX_CODEOWNERS_BYTES:
            problems.append("%s on %s is 3 MB or more, so GitHub ignores it" % (loc, branch))
        # The raw bytes: the contents API leaves `content` empty for files over 1 MB.
        text, err = _gh_raw([path, "-H", "Accept: application/vnd.github.raw"])
        if err:
            return branch, loc, None, ["couldn't read %s on %s (%s)" % (loc, branch, err)]
        errors, err = _gh_json(["repos/%s/codeowners/errors?ref=%s" % (slug, branch)])
        if err:
            problems.append("couldn't read GitHub's CODEOWNERS errors (%s)" % err)
        elif (errors or {}).get("errors"):
            problems.append("GitHub reports %d error(s) in %s on %s; it skips those lines"
                            % (len(errors["errors"]), loc, branch))
        return branch, loc, text, problems
    return branch, None, None, ["%s has no CODEOWNERS on %s, so GitHub asks nobody" % (slug, branch)]


def founder_review_remote(slug, policy, founders, local_text=None, noun="founders"):
    """[(status, detail)] for the CODEOWNERS GitHub enforces on the default branch."""
    if not slug:
        return [("FAIL", "can't tell which GitHub repository this is (no origin remote), so the "
                         "CODEOWNERS GitHub enforces is unverified")]
    branch, loc, text, problems = remote_codeowners(slug)
    out = [("FAIL", p) for p in problems]
    if text is None:
        return out or [("FAIL", "no CODEOWNERS on GitHub's default branch")]
    out.extend(founder_rules_check(parse(text), policy, set(founders), "%s on %s, as GitHub enforces it"
                                   % (loc, branch), noun))
    if local_text is not None and local_text != text:
        out.append(("INFO", "the local CODEOWNERS differs from %s's; GitHub enforces %s's until "
                            "the change is merged" % (branch, branch)))
    return out


def founder_review_enforced(slug, founders=(), noun="founder"):
    """[(status, detail)]: does GitHub require code-owner review on the default branch, and can
    each founder actually be a code owner (GitHub ignores an owner without write access)?"""
    out = [_enforced(slug)]
    for handle in founders:
        login = handle.lstrip("@")
        data, err = _gh_json(["repos/%s/collaborators/%s/permission" % (slug, login)]) if slug else (None, "no repository")
        level = (data or {}).get("permission")
        if err:
            out.append(("FAIL", "couldn't confirm %s can review in %s (%s)" % (handle, slug, err)))
        elif level in ("admin", "maintain", "write"):
            out.append(("PASS", "%s has %s access, so GitHub can ask them as a code owner" % (handle, level)))
        else:
            out.append(("FAIL", "%s has %s access to %s; GitHub ignores a code owner without write "
                                "access, so %s review can't be required of them"
                        % (handle, level or "no", slug, noun)))
    return out


def _enforced(slug):
    """(status, detail): does GitHub require code-owner review on the default branch?"""
    if not slug:
        return ("FAIL", "can't tell which GitHub repository this is (no origin remote), so code-owner "
                        "enforcement is unverified")
    repo, err = _gh_json(["repos/%s" % slug])
    if err:
        return ("FAIL", "couldn't read %s from GitHub (%s), so code-owner enforcement is unverified"
                % (slug, err))
    branch = repo.get("default_branch") or "main"
    rules, err = _gh_json(["repos/%s/rules/branches/%s" % (slug, branch)])
    if not err:
        for r in rules or []:
            if r.get("type") == "pull_request" and \
                    (r.get("parameters") or {}).get("require_code_owner_review"):
                return ("PASS", "GitHub requires code-owner review on %s (ruleset)" % branch)
    prot, err = _gh_json(["repos/%s/branches/%s/protection" % (slug, branch)])
    if err:
        if "not protected" in err.lower():
            return ("FAIL", "%s is not protected, so GitHub enforces no code-owner review" % branch)
        return ("FAIL", "couldn't read %s's protection (%s); a repository admin can run this check"
                % (branch, err))
    reviews = (prot or {}).get("required_pull_request_reviews") or {}
    if reviews.get("require_code_owner_reviews"):
        return ("PASS", "GitHub requires code-owner review on %s (branch protection)" % branch)
    return ("FAIL", "%s's protection doesn't require review from code owners, so CODEOWNERS asks "
                    "but can't hold a merge" % branch)
