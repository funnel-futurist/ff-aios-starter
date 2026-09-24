"""2.6.1: the founder lane is held, not just listed, and the inventory tells the truth.

Every test here fails on 2.6.0 (`0c0cf170840295c4fd3fa2a6c9de5dd30bbd63d3`):

* there was no `boundary` module, no pre-edit hook and no PR check, so `/start`'s
  "not yours in this workspace" was a list on screen and nothing held it;
* CLAUDE.md named 18 of the 24 skills and the skills catalog 19;
* 186 of the 282 shipped files were a copy of Anthropic's document skills.
"""

import json
import os
import shutil
import subprocess
import sys

import harness
from harness import Sandbox

sys.path.insert(0, harness.AIOS_DIR)

from aioslib import boundary, util  # noqa: E402
from aioslib.util import EXIT_OK, EXIT_ROLE  # noqa: E402

REAL_ROOT = harness.REPO_ROOT

OPERATOR_DENIED = [
    "01_Foundations/offer_economics/**", ".github/**", ".aios/config.json",
    ".aios/roles.json", ".claude/settings.json", ".claude/hooks/**", "scripts/aios/**",
]


def _policy():
    policy = json.loads(json.dumps(harness.ROLES))
    policy["roles"]["operator"]["paths_denied"] = list(OPERATOR_DENIED)
    policy["roles"]["co_founder"] = {"entries": ["founder", "operator"], "lifecycle": [],
                                     "paths_denied": []}
    return policy


def _people():
    return [
        {"github": "acme-founder", "role": "founder", "display_name": "Founder"},
        {"github": "acme-partner", "role": "co_founder", "display_name": "Partner"},
        {"github": "acme-va", "role": "operator", "display_name": "Operator"},
    ]


class _Workspace(Sandbox):
    def setUp(self):
        super().setUp()
        self.ws = os.path.join(self.tmp, "ws")
        harness.write(self.ws, ".aios/roles.json", json.dumps(_policy()))
        harness.write(self.ws, ".aios/config.json", json.dumps(harness.config(people=_people())))
        harness.write(self.ws, ".aios/.gitignore", "usage/\n")
        harness.write(self.ws, "01_Foundations/offer_economics/pricing.md", "# price\n")
        harness.write(self.ws, "02_Deliverables/draft.md", "# draft\n")

    def edit(self, rel, login="acme-va", tool="Edit"):
        return boundary.check_edit(self.ws, tool, {"file_path": os.path.join(self.ws, rel)},
                                   identify=lambda _root: login)


class SessionHook(_Workspace):
    """Claude will not edit a founder-lane path for someone whose role may not change it."""

    def test_an_operator_is_refused_on_every_founder_lane_path(self):
        for rel in (".aios/config.json", ".aios/roles.json", ".claude/settings.json",
                    ".claude/hooks/guard.js", ".github/workflows/ci.yml",
                    "01_Foundations/offer_economics/pricing.md", "scripts/aios/aios.py"):
            allowed, reason = self.edit(rel)
            self.assertFalse(allowed, rel)
            self.assertIn("founder lane", reason)

    def test_founders_and_co_founders_may_edit_them(self):
        for login in ("acme-founder", "acme-partner"):
            allowed, _ = self.edit(".aios/config.json", login=login)
            self.assertTrue(allowed, login)

    def test_an_unidentified_person_gets_the_operator_limits_not_none(self):
        allowed, reason = self.edit(".claude/settings.json", login=None)
        self.assertFalse(allowed)
        self.assertIn("unidentified", reason)
        allowed, reason = self.edit(".claude/settings.json", login="a-stranger")
        self.assertFalse(allowed)
        self.assertIn("not in the people map", reason)

    def test_ordinary_work_is_untouched_and_needs_no_identity_lookup(self):
        def explode(_root):
            raise AssertionError("an ordinary edit must not pay for an identity lookup")
        allowed, _ = boundary.check_edit(
            self.ws, "Write", {"file_path": os.path.join(self.ws, "02_Deliverables/draft.md")},
            identify=explode)
        self.assertTrue(allowed)

    def test_every_edit_tool_is_covered_and_reads_are_not(self):
        for tool in ("Edit", "Write", "MultiEdit"):
            self.assertFalse(self.edit(".aios/config.json", tool=tool)[0], tool)
        allowed, _ = boundary.check_edit(
            self.ws, "NotebookEdit",
            {"notebook_path": os.path.join(self.ws, "scripts/aios/n.ipynb")},
            identify=lambda _r: "acme-va")
        self.assertFalse(allowed)
        self.assertTrue(self.edit(".aios/config.json", tool="Read")[0])

    def test_a_symlink_cannot_smuggle_an_edit_into_the_founder_lane(self):
        link = os.path.join(self.ws, "02_Deliverables", "innocent.md")
        os.symlink(os.path.join(self.ws, ".aios", "config.json"), link)
        allowed, _ = self.edit("02_Deliverables/innocent.md")
        self.assertFalse(allowed)

    def test_relative_paths_are_resolved_against_the_workspace(self):
        allowed, _ = boundary.check_edit(self.ws, "Edit", {"file_path": ".aios/config.json"},
                                         identify=lambda _r: "acme-va")
        self.assertFalse(allowed)

    def test_a_workspace_with_no_people_map_holds_nobody(self):
        os.remove(os.path.join(self.ws, ".aios", "config.json"))
        self.assertTrue(self.edit(".aios/roles.json")[0])

    def test_the_real_hook_command_prints_a_deny_decision_for_an_operator(self):
        self.be("acme-va")
        event = {"tool_name": "Edit", "cwd": self.ws,
                 "tool_input": {"file_path": os.path.join(self.ws, ".aios/config.json")}}
        proc = subprocess.run(
            [sys.executable, os.path.join(harness.AIOS_DIR, "aios.py"), "hook", "pre-edit"],
            input=json.dumps(event).encode(), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=dict(os.environ, CLAUDE_PROJECT_DIR=self.ws))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout.decode())["hookSpecificOutput"]
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertEqual(out["hookEventName"], "PreToolUse")
        cache = util.read_json(os.path.join(self.ws, ".aios", "usage", "identity.json"))
        self.assertEqual(cache["login"], "acme-va")

    def test_the_real_hook_command_is_silent_for_a_founder(self):
        self.be("acme-founder")
        event = {"tool_name": "Write", "cwd": self.ws,
                 "tool_input": {"file_path": os.path.join(self.ws, ".aios/config.json")}}
        proc = subprocess.run(
            [sys.executable, os.path.join(harness.AIOS_DIR, "aios.py"), "hook", "pre-edit"],
            input=json.dumps(event).encode(), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=dict(os.environ, CLAUDE_PROJECT_DIR=self.ws))
        self.assertEqual((proc.returncode, proc.stdout), (0, b""))

    def test_switching_github_accounts_does_not_keep_the_old_role(self):
        """The login is cached for speed. A different account must not inherit it."""
        self.be("acme-founder")
        rel = {"file_path": os.path.join(self.ws, ".aios/config.json")}
        self.assertTrue(boundary.check_edit(self.ws, "Edit", rel)[0])
        # Same second, different person: the stub is rewritten, as `gh auth switch` would.
        os.remove(os.path.join(self.bin, "gh"))
        self.be("acme-va")
        self.assertFalse(boundary.check_edit(self.ws, "Edit", rel)[0],
                         "the cached founder login outlived the account switch")

    def test_malformed_hook_input_does_not_wedge_the_session(self):
        code, out = boundary.hook_pre_edit("not json", root=self.ws)
        self.assertEqual((code, out), (EXIT_OK, None))


class PullRequestCheck(Sandbox):
    """A founder-lane change by a non-founder fails until a founder approves that commit."""

    def setUp(self):
        super().setUp()
        self.repo = os.path.join(self.tmp, "client")
        os.makedirs(self.repo)
        harness.run_git(self.repo, "init", "-q", "-b", "main")
        harness.run_git(self.repo, "config", "user.email", "t@example.com")
        harness.run_git(self.repo, "config", "user.name", "t")
        harness.write(self.repo, ".aios/roles.json", json.dumps(_policy(), indent=2))
        harness.write(self.repo, ".aios/config.json",
                      json.dumps(harness.config(people=_people()), indent=2))
        harness.write(self.repo, "02_Deliverables/draft.md", "# draft\n")
        harness.write(self.repo, "01_Foundations/offer_economics/pricing.md", "# price\n")
        harness.run_git(self.repo, "add", "-A")
        harness.run_git(self.repo, "commit", "-qm", "base")
        self.base = util.git(self.repo, ["rev-parse", "HEAD"])
        harness.run_git(self.repo, "checkout", "-q", "-b", "pr")

    def change(self, files, removals=()):
        for rel, content in files.items():
            harness.write(self.repo, rel, content)
        for rel in removals:
            harness.run_git(self.repo, "rm", "-q", rel)
        harness.run_git(self.repo, "add", "-A")
        harness.run_git(self.repo, "commit", "-qm", "change")
        return util.git(self.repo, ["rev-parse", "HEAD"])

    def check(self, head, author="acme-va", approvers=()):
        return boundary.check_pr(self.repo, self.base, head, author, list(approvers))

    def test_an_operator_changing_the_people_map_fails(self):
        head = self.change({".aios/config.json": '{"people": []}\n'})
        code, lines = self.check(head)
        self.assertEqual(code, EXIT_ROLE)
        self.assertIn(".aios/config.json", "\n".join(lines))

    def test_a_founders_approval_of_that_commit_passes_it(self):
        head = self.change({"01_Foundations/offer_economics/pricing.md": "# new price\n"})
        for founder in ("acme-founder", "acme-partner"):
            code, _ = self.check(head, approvers=[founder])
            self.assertEqual(code, EXIT_OK, founder)

    def test_an_operators_approval_does_not_count(self):
        head = self.change({".claude/settings.json": "{}\n"})
        code, _ = self.check(head, approvers=["acme-va", "a-stranger"])
        self.assertEqual(code, EXIT_ROLE)

    def test_a_founder_author_needs_nobody(self):
        head = self.change({".aios/config.json": '{"people": []}\n'})
        self.assertEqual(self.check(head, author="acme-founder")[0], EXIT_OK)

    def test_ordinary_work_by_an_operator_passes(self):
        head = self.change({"02_Deliverables/draft.md": "# better draft\n"})
        self.assertEqual(self.check(head)[0], EXIT_OK)

    def test_a_pr_cannot_loosen_the_rule_it_is_checked_against(self):
        """The operator deletes their own restrictions AND makes themselves a founder."""
        policy = _policy()
        policy["roles"]["operator"]["paths_denied"] = []
        people = [dict(p, role="founder") for p in _people()]
        head = self.change({".aios/roles.json": json.dumps(policy),
                            ".aios/config.json": json.dumps(harness.config(people=people))})
        code, _ = self.check(head)
        self.assertEqual(code, EXIT_ROLE, "the rule must be read from the base commit")

    def test_deleting_or_moving_a_protected_file_counts(self):
        head = self.change({}, removals=["01_Foundations/offer_economics/pricing.md"])
        self.assertEqual(self.check(head)[0], EXIT_ROLE)

    def test_a_stranger_is_held_to_the_operator_limits(self):
        head = self.change({".github/workflows/x.yml": "on: push\n"})
        self.assertEqual(self.check(head, author="a-stranger")[0], EXIT_ROLE)

    def test_no_people_map_on_the_base_holds_nobody(self):
        harness.run_git(self.repo, "checkout", "-q", "main")
        harness.run_git(self.repo, "rm", "-q", ".aios/config.json")
        harness.run_git(self.repo, "commit", "-qm", "template, not installed")
        self.base = util.git(self.repo, ["rev-parse", "HEAD"])
        harness.run_git(self.repo, "checkout", "-q", "-b", "pr2")
        head = self.change({".aios/roles.json": "{}\n"})
        self.assertEqual(self.check(head)[0], EXIT_OK)

    def test_the_real_cli_exits_with_the_role_code(self):
        head = self.change({".aios/roles.json": "{}\n"})
        code, out, _err = self.cli("boundary", "check-pr", "--repo", self.repo, "--base",
                                   self.base, "--head", head, "--author", "acme-va",
                                   "--approved-by", "acme-va")
        self.assertEqual(code, EXIT_ROLE, out)
        code, _out, _err = self.cli("boundary", "check-pr", "--repo", self.repo, "--base",
                                    self.base, "--head", head, "--author", "acme-va",
                                    "--approved-by", "acme-va,acme-founder")
        self.assertEqual(code, EXIT_OK)


class ProtectionVerifierKnowsTheBoundary(Sandbox):
    """In an installed workspace, "held at the pull request" needs the check to be required."""

    def _run(self, contexts):
        root = os.path.join(self.tmp, "installed")
        shutil.copytree(os.path.join(REAL_ROOT, "scripts"), os.path.join(root, "scripts"))
        harness.write(root, ".aios/config.json", json.dumps(harness.config()))
        protection = {
            "required_pull_request_reviews": {"require_code_owner_reviews": True},
            "required_status_checks": {"contexts": contexts},
            "allow_force_pushes": {"enabled": False}, "allow_deletions": {"enabled": False},
        }
        gh = os.path.join(self.bin, "gh")
        os.makedirs(self.bin, exist_ok=True)
        with open(gh, "w") as fh:
            fh.write("#!/bin/sh\ncase \"$*\" in\n"
                     "  *'branches/main/protection'*) echo '%s';;\n"
                     "  *'branches/main'*) echo true;;\n"
                     "  *) echo ''; ;;\nesac\n" % json.dumps(protection))
        os.chmod(gh, 0o755)
        env = dict(os.environ, PATH=self.bin + os.pathsep + os.environ["PATH"])
        proc = subprocess.run(
            ["bash", os.path.join(root, "scripts", "team", "verify-branch-protection.sh"),
             "acme/acme-aios"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
        return proc.stdout.decode()

    def test_a_missing_boundary_requirement_is_a_failure(self):
        out = self._run([])
        self.assertIn("'boundary' check is not a required status check", out)

    def test_a_required_boundary_check_is_reported(self):
        out = self._run(["boundary", "governance"])
        self.assertIn("founder-lane boundary check is required", out)


class WhatTheRepoShips(Sandbox):
    """The shipped policy, settings and code-owner template agree with each other."""

    def load(self, rel):
        return util.read_json(os.path.join(REAL_ROOT, rel))

    def test_the_session_hook_is_wired_for_every_edit_tool(self):
        hooks = self.load(".claude/settings.json")["hooks"]["PreToolUse"]
        wired = [h for h in hooks if "hook pre-edit" in json.dumps(h)]
        self.assertEqual(len(wired), 1)
        self.assertEqual(set(wired[0]["matcher"].split("|")),
                         {"Edit", "Write", "MultiEdit", "NotebookEdit"})

    def test_every_founder_lane_path_has_a_code_owner(self):
        template = open(os.path.join(REAL_ROOT, "templates", "governance",
                                     "CODEOWNERS.template")).read()
        rules = [line.split()[0].strip("/") for line in template.splitlines()
                 if line.strip() and not line.startswith("#")]
        denied = self.load(".aios/roles.json")["roles"]["operator"]["paths_denied"]
        for pattern in denied:
            prefix = pattern[:-3] if pattern.endswith("/**") else pattern
            self.assertTrue(any(prefix == r or prefix.startswith(r + "/") for r in rules),
                            "%s is founder-lane but no code owner is asked to review it"
                            % pattern)

    def test_the_boundary_check_runs_on_pull_requests_and_reviews(self):
        wf = open(os.path.join(REAL_ROOT, ".github", "workflows",
                               "install-contract.yml")).read()
        self.assertIn("pull_request_review:", wf)
        self.assertIn("boundary check-pr", wf)
        self.assertIn('"$RUNNER_TEMP/base"', wf, "the checker must run from the BASE commit")
        self.assertIn("commit_id == env.HEAD_SHA", wf, "only approvals of this commit count")


class Inventory(Sandbox):
    """What we say is in the Starter is what is in the Starter."""

    def skills(self):
        root = os.path.join(REAL_ROOT, ".claude", "skills")
        return sorted(d for d in os.listdir(root)
                      if os.path.isfile(os.path.join(root, d, "SKILL.md")))

    def test_claude_md_names_every_skill(self):
        text = open(os.path.join(REAL_ROOT, "CLAUDE.md")).read()
        missing = [s for s in self.skills() if s not in text]
        self.assertEqual(missing, [], "CLAUDE.md is the map Claude reads on every message")

    def test_the_skills_catalog_names_every_skill(self):
        text = open(os.path.join(REAL_ROOT, ".claude", "skills", "README.md")).read()
        self.assertEqual([s for s in self.skills() if "**%s**" % s not in text], [])

    def test_no_copy_of_anthropics_document_skills_ships(self):
        for name in ("docx", "pdf", "pptx", "xlsx"):
            self.assertFalse(os.path.exists(os.path.join(REAL_ROOT, ".claude", "skills", name)),
                             name)
        tracked = util.git(REAL_ROOT, ["ls-files"]).splitlines()
        # Assembled, so this file does not match itself once it is tracked.
        marker = "Anthropic, PBC. " + "All rights " + "reserved"
        carrying = [p for p in tracked if os.path.isfile(os.path.join(REAL_ROOT, p))
                    and marker in open(os.path.join(REAL_ROOT, p), "rb").read()
                    .decode("utf-8", "replace")]
        self.assertEqual(carrying, [])

    def test_the_document_skills_are_installed_from_anthropic_and_credited(self):
        settings = self.load_settings()
        self.assertEqual(settings["extraKnownMarketplaces"]["anthropic-agent-skills"]["source"],
                         {"source": "github", "repo": "anthropics/skills"})
        self.assertTrue(settings["enabledPlugins"]["document-skills@anthropic-agent-skills"])
        declared = util.read_json(os.path.join(REAL_ROOT, ".template_version.json"))
        self.assertEqual([p["id"] for p in declared["plugins"]],
                         ["document-skills@anthropic-agent-skills"])
        notice = open(os.path.join(REAL_ROOT, "THIRD_PARTY_NOTICES.md")).read()
        self.assertIn("Anthropic", notice)
        self.assertIn("document-skills@anthropic-agent-skills", notice)
        wizard = open(os.path.join(REAL_ROOT, ".claude", "skills", "onboard_wizard",
                                   "SKILL.md")).read()
        self.assertIn("/plugin install document-skills@anthropic-agent-skills", wizard)
        self.assertIn("THIRD_PARTY_NOTICES.md", open(os.path.join(REAL_ROOT, "LICENSE")).read())

    def load_settings(self):
        return util.read_json(os.path.join(REAL_ROOT, ".claude", "settings.json"))
