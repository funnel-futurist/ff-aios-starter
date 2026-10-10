"""R3-h-1: a client-owned settings override that an upgrade never touches.

Found by Chat Zero's upgrade rehearsal: a client who appends one deny rule to the managed
`.claude/settings.json` cannot upgrade until they revert it. The fix is not to make the
installer tolerate edits to managed files (that would make "verify" mean nothing); it is to
give the client a file the release does not manage, which Claude Code merges natively.
"""

import json
import os
import sys

import harness
from harness import Sandbox

sys.path.insert(0, harness.AIOS_DIR)

from aioslib import install as install_mod, release as release_mod, util  # noqa: E402
from aioslib.util import Refusal  # noqa: E402

OVERRIDE = ".claude/settings.local.json"
MINE = json.dumps({"permissions": {"deny": ["Read(./clients-private/**)"]},
                   "_note": "acme's own rule, written by hand é\n"}, indent=1) + "\n"
GIT = ("-c", "user.email=t@example.com", "-c", "user.name=t")


class OverrideSurvives(Sandbox):

    def setUp(self):
        Sandbox.setUp(self)
        self.v1 = harness.approve(harness.build_manifest(self.source, self.rev, "1.0.0"))
        install_mod.install(self.target, self.v1, self.source, harness.config())
        harness.write(self.target, OVERRIDE, MINE)
        self.bytes_before = self.read()
        # The release changes the managed settings file, so the upgrade really does rewrite
        # a neighbour of the override.
        rev2 = harness.bump_source(self.source, {
            ".claude/settings.json": json.dumps({"permissions": {"deny": ["Read(.env*)", "Bash(sudo:*)"]}}),
            "START_HERE.md": "# start here\nthe two commands, now clearer.\n"})
        self.v2 = harness.approve(harness.build_manifest(self.source, rev2, "1.1.0"))

    def read(self):
        with open(os.path.join(self.target, OVERRIDE), "rb") as fh:
            return fh.read()

    def commit(self, msg):
        harness.run_git(self.target, *GIT, "add", "-A")
        harness.run_git(self.target, *GIT, "commit", "-qm", msg)

    def test_the_override_is_byte_identical_after_upgrade_and_after_rollback(self):
        install_mod.upgrade(self.target, self.v2, self.source)
        self.assertEqual(self.read(), self.bytes_before, "the upgrade touched the client's override")
        with open(os.path.join(self.target, ".claude/settings.json")) as fh:
            self.assertIn("Bash(sudo:*)", fh.read(), "the managed neighbour should have been upgraded")
        self.assertEqual(install_mod.verify(self.target)[0], [], "verify must ignore the override")
        install_mod.rollback(self.target)
        self.assertEqual(self.read(), self.bytes_before, "rollback touched the client's override")
        self.assertEqual(install_mod.verify(self.target)[0], [])

    def test_the_override_is_not_in_the_install_record(self):
        record = install_mod.load_record(self.target)
        self.assertNotIn(OVERRIDE, [e["path"] for e in record["managed"]])
        self.assertTrue(os.path.isfile(os.path.join(self.target, OVERRIDE)))

    def test_it_survives_in_a_git_workspace_whether_or_not_it_is_committed(self):
        harness.run_git(self.target, "init", "-q", "-b", "main")
        harness.write(self.target, ".gitignore", ".claude/settings.local.json\n.aios/lock\n")
        self.commit("installed")  # ignored: personal, per machine, like the real Starter
        self.assertNotIn(OVERRIDE, util.git(self.target, ["ls-files"]).split())
        install_mod.upgrade(self.target, self.v2, self.source)
        self.assertEqual(self.read(), self.bytes_before)
        install_mod.rollback(self.target)
        self.assertEqual(self.read(), self.bytes_before)

    def test_a_committed_override_is_equally_safe_and_does_not_block_the_upgrade(self):
        harness.run_git(self.target, "init", "-q", "-b", "main")
        self.commit("installed, override committed on purpose")
        self.assertIn(OVERRIDE, util.git(self.target, ["ls-files"]).split())
        install_mod.upgrade(self.target, self.v2, self.source)  # clean tree, so no refusal
        self.assertEqual(self.read(), self.bytes_before)
        self.commit("upgraded")
        install_mod.rollback(self.target)
        self.assertEqual(self.read(), self.bytes_before)

    def test_it_survives_a_hard_killed_upgrade_and_its_recovery(self):
        import subprocess
        code = ("import sys; sys.path.insert(0, %r); from aioslib import install as i, util; "
                "man = util.read_json(%r); i.upgrade(%r, man, %r)"
                % (harness.AIOS_DIR, self._write_manifest(), self.target, self.source))
        proc = subprocess.run([sys.executable, "-c", code], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, env=dict(os.environ, AIOS_FAULT="crash:upgrade.mid_write"))
        self.assertNotEqual(proc.returncode, 0)
        install_mod.rollback(self.target)
        self.assertEqual(self.read(), self.bytes_before)

    def _write_manifest(self):
        path = os.path.join(self.tmp, "v2.json")
        util.write_json(path, self.v2)
        return path

    def test_editing_the_managed_file_is_still_refused_and_the_message_points_to_the_override(self):
        with open(os.path.join(self.target, ".claude/settings.json"), "a") as fh:
            fh.write("\n")
        with self.assertRaises(Refusal) as ctx:
            install_mod.upgrade(self.target, self.v2, self.source)
        self.assertEqual(ctx.exception.code, util.EXIT_VERIFY)
        details = "\n".join(ctx.exception.details)
        self.assertIn("modified managed file: .claude/settings.json", details)
        self.assertIn(".claude/settings.local.json", details)
        self.assertEqual(self.read(), self.bytes_before)

    def test_the_way_forward_the_message_gives_actually_works(self):
        # Edit the managed file, get refused, move the change to the override, revert, upgrade.
        managed = os.path.join(self.target, ".claude/settings.json")
        with open(managed) as fh:
            original = fh.read()
        with open(managed, "a") as fh:
            fh.write("\n")
        with self.assertRaises(Refusal):
            install_mod.upgrade(self.target, self.v2, self.source)
        with open(managed, "w") as fh:
            fh.write(original)
        install_mod.upgrade(self.target, self.v2, self.source)
        self.assertEqual(self.read(), self.bytes_before)
        self.assertEqual(install_mod.verify(self.target)[0], [])

    def test_a_release_that_somehow_shipped_the_override_path_is_refused_at_upgrade(self):
        # Belt and braces: even a hand-built manifest naming the path cannot overwrite it,
        # because the upgrade's collision rule treats the client's file as theirs.
        rev3 = harness.bump_source(self.source, {OVERRIDE: "{}\n"})
        spec = dict(harness.PACKAGE_SPEC)
        spec["client_owned"] = []  # simulate a spec that forgot the rule
        v3 = release_mod.build(self.source, rev3, "1.2.0", spec=spec, branch="main")
        v3 = harness.approve(v3)
        with self.assertRaises(Refusal):
            install_mod.upgrade(self.target, v3, self.source)
        self.assertEqual(self.read(), self.bytes_before)


class ReleaseNeverCarriesIt(Sandbox):

    def test_a_package_built_from_a_clean_source_has_no_override(self):
        man = harness.build_manifest(self.source, self.rev, "1.0.0")
        self.assertNotIn(OVERRIDE, [f["path"] for f in man["files"]])

    def test_a_source_that_tracks_one_cannot_build_a_release(self):
        rev = harness.bump_source(self.source, {OVERRIDE: "{}\n"})
        with self.assertRaises(Refusal) as ctx:
            harness.build_manifest(self.source, rev, "1.1.0")
        self.assertEqual(ctx.exception.code, util.EXIT_PACKAGE)
        self.assertIn("client-owned", ctx.exception.message)
        self.assertIn(OVERRIDE, ctx.exception.message)

    def test_classify_treats_it_as_nobodys_but_the_clients(self):
        self.assertIsNone(release_mod.classify(harness.PACKAGE_SPEC, OVERRIDE))
        self.assertEqual(release_mod.classify(harness.PACKAGE_SPEC, ".claude/settings.json"), "managed")


class TheRealStarter(Sandbox):
    REPO = harness.REPO_ROOT

    def spec(self):
        return util.read_json(os.path.join(self.REPO, "release", "package_spec.json"))

    def test_the_real_spec_declares_the_override_client_owned(self):
        self.assertEqual(self.spec()["client_owned"], [OVERRIDE])
        self.assertIsNone(release_mod.classify(self.spec(), OVERRIDE))
        self.assertEqual(release_mod.classify(self.spec(), ".claude/settings.json"), "managed")

    def test_the_real_tree_does_not_track_it_and_the_gitignore_keeps_it_personal(self):
        tracked = util.git(self.REPO, ["ls-files"]).split("\n")
        self.assertNotIn(OVERRIDE, tracked)
        with open(os.path.join(self.REPO, ".gitignore")) as fh:
            self.assertIn(OVERRIDE, fh.read().split("\n"))

    def test_the_real_release_file_set_cannot_contain_it(self):
        files = release_mod.select_files(self.REPO, "HEAD", self.spec())
        self.assertNotIn(OVERRIDE, [f[0] for f in files])

    def test_the_upgrade_docs_point_clients_to_it(self):
        with open(os.path.join(self.REPO, "docs", "INSTALL_AND_UPGRADE.md"), encoding="utf-8") as fh:
            doc = fh.read()
        self.assertIn("## Your own settings", doc)
        self.assertIn(OVERRIDE, doc)
        self.assertIn("never write, replace, verify or remove", doc)
        # and the place a client lands when refused says so, too
        self.assertIn('see "Your own settings"', doc)
