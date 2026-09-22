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
    """(slug, source). GITHUB_REPOSITORY in CI, else the origin remote."""
    env = os.environ.get("GITHUB_REPOSITORY")
    if env:
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
    problems = []
    rel, path = find_file(root)
    if not path:
        return ["no CODEOWNERS file (looked in %s)" % ", ".join(LOCATIONS)]

    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        text = fh.read()

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
