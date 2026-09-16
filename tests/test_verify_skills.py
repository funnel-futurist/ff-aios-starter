#!/usr/bin/env python3
"""Tests for scripts/verify_skills.py — fixture-based contract enforcement.

Runs known-good and known-bad skill fixtures through the verifier and confirms
the expected pass/fail outcomes. Also tests the pre-push hook via a local
bare-remote push scenario.

Usage:
    python3 tests/test_verify_skills.py          # run all tests
    python3 tests/test_verify_skills.py -v       # verbose
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

# Ensure the repo root is importable
REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

# Import the verifier module
import verify_skills


class TestFixtureGood(unittest.TestCase):
    """The known-good fixture must pass every contract check."""

    def setUp(self):
        self.skill_dir = REPO / "tests/fixtures/skill_good"

    def test_check_passes(self):
        r = verify_skills.check(self.skill_dir)
        failing = [k for k, v in r["checks"].items() if not v]
        self.assertEqual(failing, [], f"Expected all checks to pass, but these failed: {failing}")

    def test_score_is_max(self):
        r = verify_skills.check(self.skill_dir)
        self.assertEqual(r["score"], r["max"])

    def test_no_dead_refs(self):
        r = verify_skills.check(self.skill_dir)
        self.assertEqual(r["refs_dead"], [])

    def test_checklist_items_paired(self):
        r = verify_skills.check(self.skill_dir)
        self.assertTrue(r["items_have_examples"])
        self.assertGreaterEqual(r["checklist_paired"], 3)
        self.assertEqual(r["checklist_paired"], r["checklist_items"])

    def test_has_gather_block(self):
        r = verify_skills.check(self.skill_dir)
        self.assertTrue(r["has_gather_block"])

    def test_resource_links_live(self):
        r = verify_skills.check(self.skill_dir)
        self.assertEqual(r["resources_dead"], [])

    def test_name_matches_folder(self):
        r = verify_skills.check(self.skill_dir)
        self.assertTrue(r["checks"]["name_matches_folder"])

    def test_description_has_not_clause(self):
        r = verify_skills.check(self.skill_dir)
        self.assertTrue(r["checks"]["desc_has_not_clause"])


class TestFixtureBad(unittest.TestCase):
    """The known-bad fixture must fail specific contract checks."""

    def setUp(self):
        self.skill_dir = REPO / "tests/fixtures/skill_bad"

    def test_check_fails(self):
        r = verify_skills.check(self.skill_dir)
        self.assertLess(r["score"], r["max"], "Expected some checks to fail")

    def test_missing_not_clause(self):
        r = verify_skills.check(self.skill_dir)
        self.assertFalse(r["checks"]["desc_has_not_clause"])

    def test_dead_resource_detected(self):
        r = verify_skills.check(self.skill_dir)
        self.assertTrue(len(r["resources_dead"]) > 0, "Expected dead Resource: links")

    def test_items_lack_examples(self):
        r = verify_skills.check(self.skill_dir)
        self.assertFalse(r["items_have_examples"],
                         "Expected items_have_examples to be False")

    def test_no_gather_block(self):
        r = verify_skills.check(self.skill_dir)
        self.assertFalse(r["has_gather_block"])


class TestChecklist(unittest.TestCase):
    """Checklist audit edge cases."""

    def test_empty_pair_not_counted(self):
        """An item with bare markers (no content) must not count as paired."""
        body = """---
name: test_empty
description: test
---
## Definition of done
- [ ] **D-1 - Check something.** ✅ ❌
- [ ] **D-2 - Check another.** ✅ ❌
- [ ] **D-3 - Check third.** ✅ ❌
"""
        a = verify_skills.checklist_audit(body)
        self.assertEqual(a["paired"], 0, "Bare markers with no content must not count as paired")

    def test_labelled_pair_counted(self):
        """An item with labelled Example:/Counter-example: and content must count."""
        body = """---
name: test_labelled
description: test
---
## Definition of done
- [ ] **D-1 - Title is bounded.**
  - **Example:** "Week of 2026-09-08" with explicit dates.
  - **Counter-example:** "Recent updates" with no date range.
- [ ] **D-2 - Evidence is cited.**
  - **Example:** "Shipped (commit a1b2c3)" with a hash.
  - **Counter-example:** "Worked on stuff" with no reference.
- [ ] **D-3 - Blockers name someone.**
  - **Example:** "Blocked: waiting on @ops-lead."
  - **Counter-example:** "Some things blocked" — no name.
"""
        a = verify_skills.checklist_audit(body)
        self.assertEqual(a["paired"], 3)
        self.assertTrue(a["pass"])


class TestCLI(unittest.TestCase):
    """CLI integration: verify_skills.py runs and produces expected output."""

    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(REPO / "scripts/verify_skills.py")] + list(args),
            capture_output=True, text=True, cwd=str(REPO), timeout=30
        )

    def test_scorecard_runs(self):
        r = self._run()
        self.assertEqual(r.returncode, 0)
        self.assertIn("skill", r.stdout.lower())

    def test_json_output(self):
        r = self._run("--json")
        self.assertEqual(r.returncode, 0)
        data = json.loads(r.stdout)
        self.assertIsInstance(data, list)

    def test_checklists_mode(self):
        r = self._run("--checklists")
        self.assertEqual(r.returncode, 0)

    def test_resources_mode(self):
        r = self._run("--resources")
        self.assertEqual(r.returncode, 0)

    def test_broken_refs_mode(self):
        r = self._run("--broken-refs")
        self.assertEqual(r.returncode, 0)

    def test_nonexistent_skill(self):
        r = self._run("--skill", "nonexistent_skill_xyz")
        self.assertNotEqual(r.returncode, 0)


class TestPrePushHook(unittest.TestCase):
    """End-to-end: a local bare-remote push with the hook installed.

    Creates a temporary bare repo, clones it, installs the hook, and verifies
    that a bad skill blocks the push and a good skill allows it.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="aios_hook_test_")
        self.bare = os.path.join(self.tmpdir, "remote.git")
        self.clone = os.path.join(self.tmpdir, "clone")

        # Create bare remote
        subprocess.run(["git", "init", "--bare", self.bare], capture_output=True, check=True)

        # Clone it
        subprocess.run(["git", "clone", self.bare, self.clone], capture_output=True, check=True)

        subprocess.run(["git", "-C", self.clone, "checkout", "-b", "main"], capture_output=True, check=True)

        # Initial commit on main so we have a base
        subprocess.run(["git", "-C", self.clone, "config", "user.email", "test@test.com"],
                       capture_output=True, check=True)
        subprocess.run(["git", "-C", self.clone, "config", "user.name", "Test"],
                       capture_output=True, check=True)
        # Create the required directory structure
        os.makedirs(os.path.join(self.clone, ".claude/skills"), exist_ok=True)
        os.makedirs(os.path.join(self.clone, "scripts"), exist_ok=True)
        os.makedirs(os.path.join(self.clone, ".githooks"), exist_ok=True)

        # Copy verifier and hook into the clone
        shutil.copy2(str(REPO / "scripts/verify_skills.py"),
                     os.path.join(self.clone, "scripts/verify_skills.py"))
        shutil.copy2(str(REPO / ".githooks/pre-push"),
                     os.path.join(self.clone, ".githooks/pre-push"))
        shutil.copy2(str(REPO / ".githooks/install.sh"),
                     os.path.join(self.clone, ".githooks/install.sh"))

        shutil.copy2(str(REPO / "scripts/verify_skill_push.py"), os.path.join(self.clone, "scripts/verify_skill_push.py"))

        # Initial commit
        subprocess.run(["git", "-C", self.clone, "add", "-A"], capture_output=True, check=True)
        subprocess.run(["git", "-C", self.clone, "commit", "-m", "initial"],
                       capture_output=True, check=True)
        subprocess.run(["git", "-C", self.clone, "push", "-u", "origin", "main"],
                       capture_output=True, check=True)

        # Install the hook
        subprocess.run(["bash", ".githooks/install.sh"], cwd=self.clone,
                       capture_output=True, check=True)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _commit_skill(self, name, skill_md_content, extra_files=None):
        """Add/update a skill and commit it."""
        skill_dir = os.path.join(self.clone, ".claude/skills", name)
        os.makedirs(skill_dir, exist_ok=True)
        with open(os.path.join(skill_dir, "SKILL.md"), "w") as f:
            f.write(skill_md_content)
        if extra_files:
            for relpath, content in extra_files.items():
                fpath = os.path.join(skill_dir, relpath)
                os.makedirs(os.path.dirname(fpath), exist_ok=True)
                with open(fpath, "w") as f:
                    f.write(content)
        subprocess.run(["git", "-C", self.clone, "add", "-A"], capture_output=True, check=True)
        subprocess.run(["git", "-C", self.clone, "commit", "-m", f"update {name}"],
                       capture_output=True, check=True)

    def test_bad_skill_blocks_push(self):
        """A skill with missing examples and dead refs must block the push."""
        subprocess.run(["git", "-C", self.clone, "checkout", "-b", "test/bad-skill"],
                       capture_output=True, check=True)
        self._commit_skill("test_bad_skill", """\
---
name: test_bad_skill
description: Does stuff.
---
# Test Bad
## Definition of done
- [ ] D-1 Output exists.
- [ ] D-2 Files saved.
- [ ] D-3 Quality ok.
""")
        r = subprocess.run(["git", "-C", self.clone, "push", "origin", "test/bad-skill"],
                           capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0, "Push should have been blocked")
        self.assertIn("blocked", r.stderr.lower() + r.stdout.lower(),
                      "Hook output should mention 'blocked'")

    def test_good_skill_allows_push(self):
        """A skill meeting the full contract must allow the push."""
        subprocess.run(["git", "-C", self.clone, "checkout", "-b", "test/good-skill"],
                       capture_output=True, check=True)
        self._commit_skill("test_good_skill", """\
---
name: test_good_skill
description: Generate reports from project data. NOT for financial work — use financial_teardown instead.
---
# Test Good

## When NOT to use this skill
| Ask | Skill |
|---|---|
| Financial | `financial_teardown` |

## GATHER
### G-1 Collect data
Read recent activity.
### G-2 Collect issues
Read open items.
### G-3 Collect blockers
Ask for stalled work.

## Definition of done
- [ ] **D-1 - Covers the period.**
  - **Example:** "Week of 2026-09-08 to 2026-09-14" — bounded window.
  - **Counter-example:** "Recent updates" — no dates, reader cannot verify.
  - **Resource:** `references/guide.md`
- [ ] **D-2 - Evidence is cited.**
  - **Example:** "Shipped (commit a1b2c3)" — citable.
  - **Counter-example:** "Worked on stuff" — unfalsifiable.
- [ ] **D-3 - Blockers name someone.**
  - **Example:** "Blocked: waiting on @ops-lead (asked 09-10)."
  - **Counter-example:** "Things are blocked" — no name, no followup.
- [ ] **D-4 - Under 500 words.**
  - **Example:** 320 words, 4 themes. Scannable.
  - **Counter-example:** 1200 words repeating commit messages verbatim.

## QC gate
Route to `qc_review` for quality checks.

No approved gold standard yet.

## OUTPUT
A status report.
""", extra_files={
            "references/guide.md": "# Guide\nReference material.\n"
        })
        r = subprocess.run(["git", "-C", self.clone, "push", "origin", "test/good-skill"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0,
                         f"Push should have succeeded.\nstdout: {r.stdout}\nstderr: {r.stderr}")

    def test_no_skill_changes_passes(self):
        """A push that does not touch .claude/skills/ must pass without verification."""
        subprocess.run(["git", "-C", self.clone, "checkout", "-b", "test/no-skills"],
                       capture_output=True, check=True)
        readme = os.path.join(self.clone, "README.md")
        with open(readme, "w") as f:
            f.write("# Test\n")
        subprocess.run(["git", "-C", self.clone, "add", "README.md"],
                       capture_output=True, check=True)
        subprocess.run(["git", "-C", self.clone, "commit", "-m", "docs only"],
                       capture_output=True, check=True)
        r = subprocess.run(["git", "-C", self.clone, "push", "origin", "test/no-skills"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0,
                         f"Non-skill push should succeed.\nstdout: {r.stdout}\nstderr: {r.stderr}")



class TestOutgoingSnapshots(TestPrePushHook):
    def fixture(self, name="skill_good"):
        body = (REPO / "tests/fixtures/skill_good/SKILL.md").read_text().replace("name: skill_good", "name: " + name)
        self._commit_skill(name, body, {"references/quality_checklist.md": "# Reference\n"})
        return body

    def push(self, *refs):
        return subprocess.run(["git", "-C", self.clone, "push", "origin", *refs],
                              capture_output=True, text=True)

    def test_fixed_working_tree_cannot_hide_bad_commit(self):
        self._commit_skill("broken", "---\nname: broken\ndescription: bad\n---\n# Incomplete\n")
        path = pathlib.Path(self.clone) / ".claude/skills/broken/SKILL.md"
        path.write_text((REPO / "tests/fixtures/skill_good/SKILL.md").read_text())
        self.assertNotEqual(self.push("main").returncode, 0)

    def test_non_current_branch_is_checked(self):
        subprocess.run(["git", "-C", self.clone, "checkout", "-b", "bad"], check=True, capture_output=True)
        self._commit_skill("broken", "# Incomplete\n")
        subprocess.run(["git", "-C", self.clone, "checkout", "main"], check=True, capture_output=True)
        self.assertNotEqual(self.push("bad").returncode, 0)

    def test_bad_history_is_not_hidden_by_later_fix(self):
        self._commit_skill("skill_good", "# Incomplete\n")
        self.fixture()
        self.assertNotEqual(self.push("main").returncode, 0)

    def test_existing_pre_push_is_preserved(self):
        hook = pathlib.Path(self.clone) / ".git/hooks/pre-push"
        hook.write_text("#!/bin/sh\nexit 42\n")
        result = subprocess.run(["sh", ".githooks/install.sh"], cwd=self.clone, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(hook.read_text(), "#!/bin/sh\nexit 42\n")

    def test_deleted_cross_skill_reference_blocks_push(self):
        body = (REPO / "tests/fixtures/skill_good/SKILL.md").read_text()
        self._commit_skill("shared", body.replace("name: skill_good", "name: shared"),
                           {"references/quality_checklist.md": "# Own reference",
                            "references/guide.md": "# Shared guide"})
        self._commit_skill("skill_good", body.replace("references/quality_checklist.md",
                                                     "../shared/references/guide.md"))
        self.assertEqual(self.push("main").returncode, 0)
        (pathlib.Path(self.clone) / ".claude/skills/shared/references/guide.md").unlink()
        subprocess.run(["git", "-C", self.clone, "add", "-A"], check=True, capture_output=True)
        subprocess.run(["git", "-C", self.clone, "commit", "-m", "delete shared source"],
                       check=True, capture_output=True)
        self.assertNotEqual(self.push("main").returncode, 0)

    def test_deleted_external_reference_blocks_push(self):
        root = pathlib.Path(self.clone)
        (root / "docs").mkdir()
        (root / "docs/guide.md").write_text("# Reference\n")
        body = (REPO / "tests/fixtures/skill_good/SKILL.md").read_text().replace(
            "references/quality_checklist.md", "docs/guide.md")
        self._commit_skill("skill_good", body)
        self.assertEqual(self.push("main").returncode, 0)
        (root / "docs/guide.md").unlink()
        subprocess.run(["git", "-C", self.clone, "add", "-A"], check=True, capture_output=True)
        subprocess.run(["git", "-C", self.clone, "commit", "-m", "delete referenced source"],
                       check=True, capture_output=True)
        result = self.push("main")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no_dead_refs", result.stderr)

    def test_malformed_skill_root_file_blocks_push(self):
        (pathlib.Path(self.clone) / ".claude/skills/not-a-directory").write_text("invalid")
        subprocess.run(["git", "-C", self.clone, "add", "-A"], check=True, capture_output=True)
        subprocess.run(["git", "-C", self.clone, "commit", "-m", "malformed skill entry"],
                       check=True, capture_output=True)
        result = self.push("main")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing SKILL.md", result.stderr)

    def test_existing_skill_root_readme_remains_legal(self):
        path = pathlib.Path(self.clone) / ".claude/skills/README.md"
        for text in ("# Skill index\n", "# Updated skill index\n"):
            path.write_text(text)
            subprocess.run(["git", "-C", self.clone, "add", "-A"], check=True, capture_output=True)
            subprocess.run(["git", "-C", self.clone, "commit", "-m", "update root index"],
                           check=True, capture_output=True)
            result = self.push("main")
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_validator_fails_closed(self):
        (pathlib.Path(self.clone) / "scripts/verify_skills.py").unlink()
        self.assertNotEqual(self.push("main").returncode, 0)


class TestPortableReferences(unittest.TestCase):
    def test_absolute_existing_file_refused(self):
        self.assertEqual(verify_skills.resolve(str(REPO / "README.md")), "dead")

    def test_templated_and_wildcard_references_refused(self):
        for path in ("../../../../private/{secret}.md", "/tmp/{secret}.md",
                     "references/{name}.md", "references/*.md"):
            with self.subTest(path=path):
                self.assertEqual(verify_skills.resolve(path, REPO / ".claude/skills/skill_good"), "dead")

    def test_escape_refused(self):
        self.assertEqual(verify_skills.resolve("../../../../etc/passwd", REPO / ".claude/skills"), "dead")


if __name__ == "__main__":
    unittest.main()
