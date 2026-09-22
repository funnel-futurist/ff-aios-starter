"""Test harness: a miniature but realistic source repo, plus a stub `gh`.

Two rules this harness exists to keep honest:

* **Approval is never faked as a human act.** Fixture releases are approved by the literal
  string `fixture-approval (test only)`. Nothing here ever writes a real person's name into
  an approval field, so no test output can be mistaken for a sign-off.
* **Identity is exercised, not bypassed.** There is no environment override in the shipped
  code. A test that wants to be somebody puts a stub `gh` on PATH, so the code path under
  test is the one that runs on a real machine.
"""

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
AIOS_DIR = os.path.join(REPO_ROOT, "scripts", "aios")
sys.path.insert(0, AIOS_DIR)

from aioslib import release as release_mod, util  # noqa: E402

FIXTURE_APPROVER = "fixture-approval (test only)"

PACKAGE_SPEC = {
    "schema": "ff-aios-starter/package-spec@1",
    "exclude": ["evidence/**", "releases/**", "release/**", "tests/**", ".github/CODEOWNERS"],
    "seed": ["CLAUDE.md", "README.md", ".gitignore", "01_Foundations/**", "06_Communication/**"],
}

ROLES = {
    "schema": "ff-aios-starter/roles@1",
    "roles": {
        "founder": {"entries": ["founder", "operator"],
                    "lifecycle": ["install", "adopt", "upgrade", "rollback", "governance"],
                    "paths_denied": []},
        "operator": {"entries": ["operator"], "lifecycle": [],
                     "paths_denied": ["01_Foundations/offer_economics/**", ".github/**"]},
    },
    "entries": {
        "operator": {"summary": "run the day", "skills": ["start-my-day", "wrap-up"]},
        "founder": {"summary": "own the gates", "skills": ["dashboard"],
                    "actions": ["aios upgrade"]},
    },
}

CODEOWNERS_TEMPLATE = """# CODEOWNERS
# [REPO_OWNER] = the founder
/.github/                   [REPO_OWNER] [PRIMARY_REVIEWER]
/.claude/skills/            [REPO_OWNER]
"""


def run_git(repo, *args):
    subprocess.run(["git", "-C", repo] + list(args), check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def write(root, rel, content):
    path = os.path.join(root, rel)
    util.ensure_parent(path)
    mode = "wb" if isinstance(content, bytes) else "w"
    with open(path, mode) as fh:
        fh.write(content)
    return path


def make_source_repo(root, extra_files=None, spec=None):
    """A small git repo shaped like the real starter."""
    os.makedirs(root, exist_ok=True)
    run_git(root, "init", "-q", "-b", "main")
    run_git(root, "config", "user.email", "harness@example.com")
    run_git(root, "config", "user.name", "harness")

    write(root, "release/package_spec.json", json.dumps(spec or PACKAGE_SPEC, indent=2))
    write(root, ".aios/roles.json", json.dumps(ROLES, indent=2))
    write(root, ".aios/.gitignore", "backups/\ntxn.json\n")
    write(root, "templates/governance/CODEOWNERS.template", CODEOWNERS_TEMPLATE)
    write(root, ".claude/skills/start-my-day/SKILL.md", "# start-my-day\nsync, branch, brain.\n")
    write(root, ".claude/settings.json", json.dumps({"permissions": {"deny": ["Read(.env*)"]}}))
    write(root, "scripts/team/git-safety-check.sh", "#!/usr/bin/env bash\necho BRANCH=main\n")
    write(root, "START_HERE.md", "# start here\nthe two commands.\n")
    # seed files - these become the operator's the moment they land
    write(root, "CLAUDE.md", "# Your AIOS\nyours to shape.\n")
    write(root, "README.md", "# readme\n")
    write(root, ".gitignore", ".env\n")
    write(root, "01_Foundations/market_analysis/_workspace.md", "# market\n")
    write(root, "06_Communication/decisions_log.md", "# decisions\n")
    # excluded
    write(root, "evidence/notes.md", "not shipped\n")
    write(root, ".github/CODEOWNERS", "* [REPO_OWNER]\n")

    for rel, content in (extra_files or {}).items():
        write(root, rel, content)

    run_git(root, "add", "-A")
    run_git(root, "commit", "-qm", "package")
    return util.git(root, ["rev-parse", "HEAD"])


def bump_source(root, changes, message="next version"):
    for rel, content in changes.items():
        write(root, rel, content)
    run_git(root, "add", "-A")
    run_git(root, "commit", "-qm", message)
    return util.git(root, ["rev-parse", "HEAD"])


def build_manifest(repo, rev, version, credentials=None, min_upgrade_from=None,
                   aios_release=None):
    return release_mod.build(repo, rev, version, branch="main", credentials=credentials,
                             min_upgrade_from=min_upgrade_from, aios_release=aios_release)


def approve(manifest, by=FIXTURE_APPROVER):
    """Mark a fixture release approved. Never used with a real person's name."""
    out = json.loads(json.dumps(manifest))
    out["status"] = "approved"
    out["approval"] = {"approved_by": by, "approved_at": "2026-09-22T00:00:00Z"}
    return out


def config(repository="acme/acme-aios", people=None, credentials=None, code_owners=None):
    return {
        "schema": "ff-aios-starter/org-config@1",
        "org_id": "acme",
        "repository": repository,
        "people": people or [
            {"github": "acme-founder", "role": "founder", "display_name": "Founder"},
            {"github": "acme-va", "role": "operator", "display_name": "Operator"},
        ],
        "credentials": credentials if credentials is not None else {},
        "code_owners": code_owners or {},
    }


def stub_gh(bin_dir, login):
    """A fake `gh` that answers `gh api user --jq .login`, so role code runs for real."""
    os.makedirs(bin_dir, exist_ok=True)
    path = os.path.join(bin_dir, "gh")
    with open(path, "w") as fh:
        fh.write("#!/bin/sh\nif [ \"$1\" = \"api\" ] && [ \"$2\" = \"user\" ]; then\n"
                 "  echo %s\n  exit 0\nfi\nexit 1\n" % login)
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return path


class Sandbox(unittest.TestCase):
    """Base class: temp dirs, a source repo, and PATH control for identity."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="aios-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.source = os.path.join(self.tmp, "source")
        self.target = os.path.join(self.tmp, "workspace")
        self.bin = os.path.join(self.tmp, "bin")
        self.rev = make_source_repo(self.source)
        self._old_path = os.environ.get("PATH", "")
        self._old_fault = os.environ.get("AIOS_FAULT")
        self.addCleanup(self._restore_env)

    def _restore_env(self):
        os.environ["PATH"] = self._old_path
        if self._old_fault is None:
            os.environ.pop("AIOS_FAULT", None)
        else:
            os.environ["AIOS_FAULT"] = self._old_fault

    def be(self, login):
        stub_gh(self.bin, login)
        os.environ["PATH"] = self.bin + os.pathsep + self._old_path

    def nobody(self):
        """No `gh` at all: an unidentifiable operator."""
        os.makedirs(self.bin, exist_ok=True)
        os.environ["PATH"] = self.bin

    def cli(self, *args, **kwargs):
        """Run the real CLI in a subprocess and return (code, stdout, stderr)."""
        env = dict(os.environ)
        env.update(kwargs.get("env") or {})
        proc = subprocess.run(
            [sys.executable, os.path.join(AIOS_DIR, "aios.py")] + [str(a) for a in args],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
            cwd=kwargs.get("cwd") or self.tmp)
        return (proc.returncode, proc.stdout.decode("utf-8", "replace"),
                proc.stderr.decode("utf-8", "replace"))

    def write_json(self, rel, obj):
        path = os.path.join(self.tmp, rel)
        util.write_json(path, obj)
        return path
