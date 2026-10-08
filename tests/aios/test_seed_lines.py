"""Seed lines: one declared line a release adds once to a seed file that predates it.

The operator core (2.7.2) is the first: `.aios/operator_core/OPERATOR_CORE.md` ships as a managed
file, and `CLAUDE.md`, which is the client's, needs one import line for it. A fresh install gets
the line from the release's own `CLAUDE.md`. An existing workspace gets it from the upgrade, once,
and keeps every edit of its own. This is the only time an upgrade writes into a client's file, so
every way it could go wrong is pinned here.

Run: python3 -m unittest discover -s tests/aios -v
"""

import json
import os
import subprocess
import sys

import harness
from harness import Sandbox

sys.path.insert(0, harness.AIOS_DIR)

from aioslib import install as install_mod, util  # noqa: E402
from aioslib.util import Refusal  # noqa: E402

IMPORT = "@.aios/operator_core/OPERATOR_CORE.md"
CORE = "<!-- aios-operator-core v1.0.0 -->\n# AIOS Operator Core v1.0.0\nhow work is explained.\n"
SPEC = dict(harness.PACKAGE_SPEC, seed_lines=[{"path": "CLAUDE.md", "line": IMPORT}])
CLIENT_CLAUDE = "# Your AIOS\nyours to shape.\nMY HOUSE RULE: invoices go out on Fridays.\n"


class SeedLines(Sandbox):

    def setUp(self):
        super(SeedLines, self).setUp()
        self.v1 = harness.approve(harness.build_manifest(self.source, self.rev, "1.0.0"))
        install_mod.install(self.target, self.v1, self.source, harness.config())
        # the client's own work, before the core exists
        harness.write(self.target, "CLAUDE.md", CLIENT_CLAUDE)
        harness.write(self.target, "02_Deliverables/copy/my_ad.md", "my work\n")
        self.state_before = self._state_without_claude_md()

        # 1.1.0 ships the core and declares the one line; its own CLAUDE.md carries the line
        rev2 = harness.bump_source(self.source, {
            ".aios/operator_core/OPERATOR_CORE.md": CORE,
            "CLAUDE.md": "# Your AIOS\nyours to shape.\n\n%s\n" % IMPORT,
            "release/package_spec.json": json.dumps(SPEC, indent=2),
        })
        self.v2 = harness.approve(harness.build_manifest(self.source, rev2, "1.1.0"))
        rev3 = harness.bump_source(self.source, {"START_HERE.md": "# start here\nversion three.\n"})
        self.v3 = harness.approve(harness.build_manifest(self.source, rev3, "1.2.0"))

    def _state_without_claude_md(self):
        state = install_mod.state_fingerprint(self.target)
        state.pop("CLAUDE.md", None)
        return state

    def _claude_md(self):
        with open(os.path.join(self.target, "CLAUDE.md")) as fh:
            return fh.read()

    # ─── the release carries the line, and refuses a line it can't honour ────────

    def test_the_release_declares_its_seed_line_and_an_older_one_has_none(self):
        self.assertEqual(self.v2["seed_lines"], [{"path": "CLAUDE.md", "line": IMPORT}])
        self.assertNotIn("seed_lines", self.v1)

    def test_a_seed_line_its_own_seed_file_lacks_is_refused_at_build(self):
        rev = harness.bump_source(self.source, {"CLAUDE.md": "# Your AIOS\nno import here.\n"})
        with self.assertRaises(Refusal) as ctx:
            harness.build_manifest(self.source, rev, "9.0.0")
        self.assertEqual(ctx.exception.code, util.EXIT_PACKAGE)
        self.assertIn("a fresh install would lack it", "\n".join(ctx.exception.details))

    def test_a_seed_line_on_a_managed_file_is_refused_at_build(self):
        spec = dict(harness.PACKAGE_SPEC, seed_lines=[{"path": "START_HERE.md", "line": IMPORT}])
        rev = harness.bump_source(self.source, {"release/package_spec.json": json.dumps(spec)})
        with self.assertRaises(Refusal) as ctx:
            harness.build_manifest(self.source, rev, "9.0.0")
        self.assertIn("is not a seed file", "\n".join(ctx.exception.details))

    def test_a_seed_line_must_be_one_plain_line(self):
        spec = dict(harness.PACKAGE_SPEC, seed_lines=[{"path": "CLAUDE.md", "line": IMPORT + "\nrm -rf /"}])
        rev = harness.bump_source(self.source, {"release/package_spec.json": json.dumps(spec)})
        with self.assertRaises(Refusal):
            harness.build_manifest(self.source, rev, "9.0.0")

    # ─── the upgrade: the core arrives, the line is added once, nothing else moves ──

    def test_an_existing_client_gets_the_core_and_keeps_every_edit(self):
        record = install_mod.upgrade(self.target, self.v2, self.source)
        with open(os.path.join(self.target, ".aios", "operator_core", "OPERATOR_CORE.md")) as fh:
            self.assertEqual(fh.read(), CORE)
        # their CLAUDE.md, byte for byte, plus exactly one blank line and the import
        self.assertEqual(self._claude_md(), CLIENT_CLAUDE + "\n" + IMPORT + "\n")
        self.assertEqual(self._state_without_claude_md(), self.state_before)
        self.assertEqual([(e["path"], e["state"], e["release"]) for e in record["seed_lines"]],
                         [("CLAUDE.md", "added", "1.1.0")])
        self.assertEqual(install_mod.verify(self.target)[0], [])

    def test_the_line_is_never_added_twice(self):
        install_mod.upgrade(self.target, self.v2, self.source)
        after_first = self._claude_md()
        record = install_mod.upgrade(self.target, self.v3, self.source)
        self.assertEqual(self._claude_md(), after_first)
        self.assertEqual(self._claude_md().count(IMPORT), 1)
        self.assertEqual(len(record["seed_lines"]), 1)

    def test_a_client_who_removes_the_line_keeps_it_removed(self):
        install_mod.upgrade(self.target, self.v2, self.source)
        harness.write(self.target, "CLAUDE.md", CLIENT_CLAUDE)
        install_mod.upgrade(self.target, self.v3, self.source)
        self.assertEqual(self._claude_md(), CLIENT_CLAUDE)

    def test_a_deleted_claude_md_is_not_recreated(self):
        os.remove(os.path.join(self.target, "CLAUDE.md"))
        record = install_mod.upgrade(self.target, self.v2, self.source)
        self.assertFalse(os.path.exists(os.path.join(self.target, "CLAUDE.md")))
        self.assertEqual(record["seed_lines"][0]["state"], "absent")

    def test_a_line_the_client_already_has_is_left_alone(self):
        harness.write(self.target, "CLAUDE.md", CLIENT_CLAUDE + IMPORT + "\n")
        record = install_mod.upgrade(self.target, self.v2, self.source)
        self.assertEqual(self._claude_md(), CLIENT_CLAUDE + IMPORT + "\n")
        self.assertEqual(record["seed_lines"][0]["state"], "present")

    def test_a_claude_md_without_a_final_newline_gets_a_clean_line(self):
        harness.write(self.target, "CLAUDE.md", "# Your AIOS\nno newline at the end")
        install_mod.upgrade(self.target, self.v2, self.source)
        self.assertEqual(self._claude_md(), "# Your AIOS\nno newline at the end\n\n%s\n" % IMPORT)

    def test_the_dry_run_shows_the_line_and_writes_nothing(self):
        plan = install_mod.upgrade_plan(self.target, self.v2, self.source)
        self.assertEqual(plan["seed_lines"], [{"path": "CLAUDE.md", "line": IMPORT}])
        self.assertIn(".aios/operator_core/OPERATOR_CORE.md", plan["added"])
        self.assertEqual(self._claude_md(), CLIENT_CLAUDE)

    # ─── every way back takes exactly the line back ─────────────────────────────

    def test_rollback_takes_the_line_back(self):
        install_mod.upgrade(self.target, self.v2, self.source)
        install_mod.rollback(self.target)
        self.assertEqual(self._claude_md(), CLIENT_CLAUDE)
        self.assertFalse(os.path.exists(os.path.join(self.target, ".aios", "operator_core", "OPERATOR_CORE.md")))
        self.assertEqual(self._state_without_claude_md(), self.state_before)
        self.assertEqual(install_mod.verify(self.target)[0], [])

    def test_rollback_after_the_client_wrote_more_removes_only_the_line(self):
        install_mod.upgrade(self.target, self.v2, self.source)
        with open(os.path.join(self.target, "CLAUDE.md"), "a") as fh:
            fh.write("A LATER RULE.\n")
        install_mod.rollback(self.target)
        text = self._claude_md()
        self.assertNotIn(IMPORT, text)
        self.assertIn("MY HOUSE RULE", text)
        self.assertIn("A LATER RULE.", text)

    def test_a_failed_upgrade_takes_the_line_back(self):
        os.environ["AIOS_FAULT"] = "raise:upgrade.before_record"  # after the line was appended
        with self.assertRaises(Refusal):
            install_mod.upgrade(self.target, self.v2, self.source)
        os.environ.pop("AIOS_FAULT")
        self.assertEqual(self._claude_md(), CLIENT_CLAUDE)
        self.assertEqual(install_mod.verify(self.target)[0], [])
        self.assertEqual(self._state_without_claude_md(), self.state_before)

    def test_recovery_after_a_hard_kill_takes_the_line_back(self):
        code = subprocess.call(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0, %r);"
             "from aioslib import install as i, util;"
             "man=util.read_json(%r);"
             "i.upgrade(%r, man, %r)" % (harness.AIOS_DIR, self.write_json("v2.json", self.v2),
                                         self.target, self.source)],
            env=dict(os.environ, AIOS_FAULT="crash:upgrade.before_record"),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.assertEqual(code, 137, "the fixture must die after appending the line")
        self.assertIn(IMPORT, self._claude_md())  # the kill left it there
        _record, summary, how = install_mod.rollback(self.target)
        self.assertIn("recovered", how)
        self.assertEqual(summary["version"], "1.0.0")
        self.assertEqual(self._claude_md(), CLIENT_CLAUDE)

    # ─── a fresh install: the line comes with the release, and is never doubled ───

    def test_a_fresh_install_has_the_line_once_and_an_upgrade_leaves_it(self):
        fresh = os.path.join(self.tmp, "fresh")
        install_mod.install(fresh, self.v2, self.source, harness.config())
        with open(os.path.join(fresh, "CLAUDE.md")) as fh:
            self.assertEqual(fh.read().count(IMPORT), 1)
        self.assertEqual(install_mod.load_record(fresh)["seed_lines"][0]["state"], "present")
        install_mod.upgrade(fresh, self.v3, self.source)
        with open(os.path.join(fresh, "CLAUDE.md")) as fh:
            self.assertEqual(fh.read().count(IMPORT), 1)

    def test_the_cli_says_what_it_wrote_outside_the_managed_files(self):
        self.be("acme-founder")
        release = self.write_json("v2.json", self.v2)
        code, out, err = self.cli("upgrade", "--release", release, "--target", self.target,
                                  "--repo", self.source, "--dry-run")
        self.assertEqual(code, 0, err)
        self.assertIn("one line:  CLAUDE.md gains `%s`" % IMPORT, out)
        code, out, err = self.cli("upgrade", "--release", release, "--target", self.target,
                                  "--repo", self.source)
        self.assertEqual(code, 0, err)
        self.assertIn("untouched, except one declared line: CLAUDE.md gained `%s`" % IMPORT, out)
        code, out, _err = self.cli("verify", "--target", self.target)
        self.assertIn("line:    CLAUDE.md has `%s`" % IMPORT, out)
