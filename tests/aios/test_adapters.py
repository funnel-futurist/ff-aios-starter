"""R3-i-1: the adapter manifest is honest, and a new tool-specific file cannot arrive undeclared.

The Starter's behaviour is built on Claude Code. These tests do not add a second tool. They
hold the claim steady: what is Claude-specific is declared file by file, nothing else is
claimed to work, and "verified" has to point at a real test.
"""

import json
import os
import sys

import harness
from harness import Sandbox

sys.path.insert(0, harness.AIOS_DIR)

from aioslib import adapters, protected, util  # noqa: E402

REPO = harness.REPO_ROOT


def _manifest(tools=None, neutral=None, mixed=None):
    base = {"schema": adapters.SCHEMA,
            "tools": tools or {
                "claude-code": {"status": "verified", "evidence": ["tests/t.py::T::test_a"],
                                "signatures": [".claude/**", "CLAUDE.md"],
                                "files": [".claude/settings.json", "CLAUDE.md"]},
                "codex": {"status": "not verified", "signatures": ["AGENTS.md", ".codex/**"], "files": []}},
            "tool_neutral": neutral if neutral is not None else ["scripts/*.py"],
            "mixed": mixed or []}
    return base


class FixtureTree(Sandbox):

    def setUp(self):
        super().setUp()
        self.repo = os.path.join(self.tmp, "r")
        harness.write(self.repo, ".claude/settings.json", "{}")
        harness.write(self.repo, "CLAUDE.md", "# mine\n")
        harness.write(self.repo, "scripts/tool.py", "print('x')\n")
        harness.write(self.repo, "tests/t.py", "class T:\n    def test_a(self):\n        pass\n")
        self.put(_manifest())

    def put(self, manifest):
        harness.write(self.repo, adapters.MANIFEST_PATH, json.dumps(manifest))

    def problems(self, extra=()):
        files = protected.tracked_or_walked(self.repo) + list(extra)
        return adapters.problems(self.repo, files)

    def test_a_consistent_manifest_has_no_problems(self):
        self.assertEqual(self.problems(), [])

    def test_an_undeclared_claude_file_fails(self):
        harness.write(self.repo, ".claude/hooks/new-hook.js", "// new\n")
        found = self.problems()
        self.assertEqual(len(found), 1, found)
        self.assertIn(".claude/hooks/new-hook.js", found[0])
        self.assertIn("not declared", found[0])

    def test_an_undeclared_file_for_another_tool_fails_too(self):
        harness.write(self.repo, "AGENTS.md", "# agents\n")
        harness.write(self.repo, ".codex/hooks/x.js", "//\n")
        found = " | ".join(self.problems())
        self.assertIn("AGENTS.md", found)
        self.assertIn(".codex/hooks/x.js", found)

    def test_declaring_a_file_for_a_tool_makes_it_pass_but_never_makes_the_tool_verified(self):
        harness.write(self.repo, "AGENTS.md", "# agents\n")
        m = _manifest()
        m["tools"]["codex"]["files"] = ["AGENTS.md"]
        self.put(m)
        self.assertEqual(self.problems(), [])
        self.assertEqual(m["tools"]["codex"]["status"], "not verified")

    def test_a_declared_file_that_disappeared_is_a_problem(self):
        os.remove(os.path.join(self.repo, ".claude", "settings.json"))
        self.assertTrue(any("does not exist" in p for p in self.problems()))

    def test_verified_with_no_evidence_fails(self):
        m = _manifest()
        m["tools"]["claude-code"]["evidence"] = []
        self.put(m)
        self.assertTrue(any("names no test that proves it" in p for p in self.problems()))

    def test_verified_with_evidence_that_names_no_real_test_fails(self):
        for ref in ("tests/missing.py::T::test_a", "tests/t.py::Nope::test_a", "tests/t.py::T::test_nope"):
            m = _manifest()
            m["tools"]["claude-code"]["evidence"] = [ref]
            self.put(m)
            self.assertTrue(any("evidence" in p for p in self.problems()), ref)

    def test_a_tool_that_is_not_verified_cannot_carry_evidence(self):
        m = _manifest()
        m["tools"]["codex"]["evidence"] = ["tests/t.py::T::test_a"]
        self.put(m)
        self.assertTrue(any("either it is verified or it is not" in p for p in self.problems()))

    def test_an_unknown_status_is_refused(self):
        m = _manifest()
        m["tools"]["codex"]["status"] = "works"
        self.put(m)
        self.assertTrue(any("status must be one of" in p for p in self.problems()))

    def test_a_file_cannot_be_both_tool_specific_and_neutral(self):
        m = _manifest(neutral=["CLAUDE.md"])
        self.put(m)
        self.assertTrue(any("tool-specific" in p and "tool-neutral" in p for p in self.problems()))

    def test_a_neutral_pattern_that_matches_nothing_is_stale(self):
        self.put(_manifest(neutral=["nothing/**"]))
        self.assertTrue(any("matches no file" in p for p in self.problems()))

    def test_the_cli_exits_non_zero_on_an_undeclared_file(self):
        harness.write(self.repo, ".claude/skills/x/SKILL.md", "# x\n")
        code, out, err = self.cli("adapters", "check", "--repo", self.repo)
        self.assertEqual(code, util.EXIT_PACKAGE, out + err)
        self.assertIn(".claude/skills/x/SKILL.md", err)


class TheRealManifest(Sandbox):

    def files(self):
        return protected.tracked_or_walked(REPO)

    def manifest(self):
        return adapters.load(REPO)

    def test_the_real_tree_and_the_manifest_agree(self):
        self.assertEqual(adapters.problems(REPO, self.files()), [])

    def test_a_new_claude_file_in_the_real_tree_would_fail(self):
        found = adapters.problems(REPO, self.files() + [".claude/hooks/undeclared.js"])
        self.assertEqual(len(found), 1, found)
        self.assertIn(".claude/hooks/undeclared.js", found[0])

    def test_claude_code_is_the_only_tool_with_anything_shipped_or_verified(self):
        tools = self.manifest()["tools"]
        self.assertEqual(tools["claude-code"]["status"], "verified")
        for name, tool in tools.items():
            if name != "claude-code":
                self.assertEqual(tool["status"], "not verified", name)
                self.assertEqual(tool["files"], [], "%s ships files nobody has verified" % name)
                self.assertFalse(tool.get("evidence"), name)

    def test_every_claude_file_in_the_tree_is_declared_one_by_one_not_by_pattern(self):
        declared = set(self.manifest()["tools"]["claude-code"]["files"])
        for path in self.files():
            if path.startswith(".claude/") or path in ("CLAUDE.md", ".github/workflows/pr-review.yml"):
                self.assertIn(path, declared)
        self.assertFalse([d for d in declared if "*" in d], "a glob here would let a new file in silently")

    def test_mixed_files_say_which_part_is_which(self):
        for entry in self.manifest()["mixed"]:
            self.assertTrue(entry["tool_specific_part"] and entry["neutral_part"])

    def test_the_release_that_ships_never_carries_the_manifest(self):
        spec = util.read_json(os.path.join(REPO, "release", "package_spec.json"))
        self.assertTrue(util.match_any(spec["exclude"], adapters.MANIFEST_PATH))
