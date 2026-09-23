"""The install contract: the positive path, and every refusal that must hold.

Run: python3 -m unittest discover -s tests/aios -v

Numbering follows the P22 package: A1-A7 are the acceptance criteria, N1-N7 the negative
tests. Every negative asserts the *specific* exit code, not merely "it failed": a refusal
that returns the wrong reason sends the operator down the wrong path.
"""

import json
import os
import subprocess
import sys

import harness
from harness import Sandbox

sys.path.insert(0, harness.AIOS_DIR)

from aioslib import install as install_mod, orgconfig, release as release_mod, roles, util  # noqa: E402
from aioslib.util import Refusal  # noqa: E402


class InstallPath(Sandbox):
    """A1 - a pinned, approved release installs into a clean environment, readback-verified."""

    def test_a1_install_is_verified_by_reading_state_back(self):
        man = harness.approve(harness.build_manifest(self.source, self.rev, "1.0.0"))
        cfg = harness.config()
        record, _creds = install_mod.install(self.target, man, self.source, cfg)

        self.assertEqual(record["release"]["version"], "1.0.0")
        self.assertTrue(record["managed"], "a release with no managed files proves nothing")
        # Readback, not the installer's own say-so: re-hash every managed file from disk.
        for entry in record["managed"]:
            disk = util.sha256_file(os.path.join(self.target, entry["path"]))
            self.assertEqual(disk, entry["sha256"], entry["path"])
        problems, summary = install_mod.verify(self.target)
        self.assertEqual(problems, [])
        self.assertEqual(summary["managed_checked"], len(record["managed"]))

    def test_a1b_readback_actually_catches_a_changed_byte(self):
        """A verifier that cannot fail is not a verifier."""
        man = harness.approve(harness.build_manifest(self.source, self.rev, "1.0.0"))
        install_mod.install(self.target, man, self.source, harness.config())
        with open(os.path.join(self.target, "START_HERE.md"), "a") as fh:
            fh.write("\nedited by hand\n")
        problems, _ = install_mod.verify(self.target)
        self.assertTrue(any("START_HERE.md" in p for p in problems), problems)

    def test_a1c_install_refuses_a_target_that_is_not_clean(self):
        man = harness.approve(harness.build_manifest(self.source, self.rev, "1.0.0"))
        harness.write(self.target, "START_HERE.md", "mine already\n")
        with self.assertRaises(Refusal) as ctx:
            install_mod.install(self.target, man, self.source, harness.config())
        self.assertEqual(ctx.exception.code, util.EXIT_STATE)

    def test_a7_counts_carry_provenance(self):
        man = harness.build_manifest(self.source, self.rev, "1.0.0")
        counted = len(man["files"])
        self.assertEqual(man["counts"]["files"], counted)
        self.assertEqual(man["counts"]["managed"] + man["counts"]["seed"], counted)
        self.assertEqual(man["counts"]["skills"], len(man["skills"]))
        # every count is derived from the pinned tree, never typed in
        self.assertEqual(
            counted,
            len(release_mod.select_files(self.source, self.rev, harness.PACKAGE_SPEC)))


class PackageGate(Sandbox):
    """N1 - an unpinned or unapproved package is refused."""

    def test_n1a_draft_release_is_refused(self):
        man = harness.build_manifest(self.source, self.rev, "1.0.0")  # status: draft
        with self.assertRaises(Refusal) as ctx:
            install_mod.install(self.target, man, self.source, harness.config())
        self.assertEqual(ctx.exception.code, util.EXIT_PACKAGE)
        self.assertTrue(any("draft" in d for d in ctx.exception.details), ctx.exception.details)
        self.assertFalse(os.path.exists(os.path.join(self.target, "START_HERE.md")),
                         "a refused install must write nothing")

    def test_n1b_approved_status_without_a_signer_is_refused(self):
        man = harness.build_manifest(self.source, self.rev, "1.0.0")
        man["status"] = "approved"  # but approval.approved_by stays null
        with self.assertRaises(Refusal) as ctx:
            install_mod.install(self.target, man, self.source, harness.config())
        self.assertEqual(ctx.exception.code, util.EXIT_PACKAGE)
        self.assertTrue(any("approved_by" in d for d in ctx.exception.details))

    def test_n1c_a_branch_name_is_not_a_pin(self):
        with self.assertRaises(Refusal) as ctx:
            harness.build_manifest(self.source, "main", "1.0.0")
        self.assertEqual(ctx.exception.code, util.EXIT_PACKAGE)

    def test_n1d_short_sha_is_not_a_pin(self):
        man = harness.approve(harness.build_manifest(self.source, self.rev, "1.0.0"))
        man["created_from"]["git_rev"] = self.rev[:12]
        problems = release_mod.consumable(man, self.source)
        self.assertTrue(any("40-character" in p for p in problems), problems)

    def test_n1e_tampered_content_at_the_pin_is_refused(self):
        man = harness.approve(harness.build_manifest(self.source, self.rev, "1.0.0"))
        for entry in man["files"]:
            if entry["path"] == "START_HERE.md":
                entry["sha256"] = "0" * 64
        with self.assertRaises(Refusal) as ctx:
            install_mod.install(self.target, man, self.source, harness.config())
        self.assertEqual(ctx.exception.code, util.EXIT_PACKAGE)
        self.assertTrue(any("drift" in d for d in ctx.exception.details), ctx.exception.details)

    def test_n1f_a_manifest_that_omits_a_shipped_file_is_refused(self):
        """An omission means a file nobody verifies - as dangerous as a mutation."""
        man = harness.approve(harness.build_manifest(self.source, self.rev, "1.0.0"))
        man["files"] = [e for e in man["files"] if e["path"] != "START_HERE.md"]
        problems = release_mod.consumable(man, self.source)
        self.assertTrue(any("does not list" in p for p in problems), problems)

    def test_n1g_consuming_an_unapproved_aios_release_is_refused(self):
        """Founder ruling D3 reaches through to P01's catalogue."""
        man = harness.approve(
            harness.build_manifest(self.source, self.rev, "1.0.0", aios_release="aios-0.1.0"))
        catalogue = os.path.join(self.tmp, "aios_releases")
        util.write_json(os.path.join(catalogue, "aios-0.1.0.json"),
                        {"release_id": "aios-0.1.0", "status": "draft"})

        def lookup(rid):
            path = os.path.join(catalogue, "%s.json" % rid)
            return util.read_json(path) if os.path.isfile(path) else None

        with self.assertRaises(Refusal) as ctx:
            install_mod.install(self.target, man, self.source, harness.config(), lookup)
        self.assertEqual(ctx.exception.code, util.EXIT_PACKAGE)
        self.assertTrue(any("aios-0.1.0" in d for d in ctx.exception.details))

    def test_n1h_the_builder_cannot_approve_its_own_release(self):
        man = harness.build_manifest(self.source, self.rev, "9.9.9")
        self.assertEqual(man["status"], "draft")
        self.assertIsNone(man["approval"]["approved_by"])
        # The same belt-and-braces P01 uses: no approval literal may appear in the builder.
        src = open(os.path.join(harness.AIOS_DIR, "aioslib", "release.py")).read()
        body = src.split("def build(", 1)[1].split("\ndef ", 1)[0]
        self.assertNotIn('"approved"', body,
                         "build() must not be able to emit an approved release")

    def test_n1i_a_link_inside_the_package_is_refused_but_one_outside_it_is_not(self):
        """PR #11's bug, generalised: refuse links that ship, ignore links that do not."""
        os.symlink("README.md", os.path.join(self.source, "evidence", "link.md"))
        harness.run_git(self.source, "add", "-A")
        harness.run_git(self.source, "commit", "-qm", "excluded link")
        rev = util.git(self.source, ["rev-parse", "HEAD"])
        man = harness.build_manifest(self.source, rev, "1.0.1")  # must not raise
        self.assertTrue(man["files"])

        os.symlink("README.md", os.path.join(self.source, "shipped_link.md"))
        harness.run_git(self.source, "add", "-A")
        harness.run_git(self.source, "commit", "-qm", "shipped link")
        rev2 = util.git(self.source, ["rev-parse", "HEAD"])
        with self.assertRaises(Refusal) as ctx:
            harness.build_manifest(self.source, rev2, "1.0.2")
        self.assertEqual(ctx.exception.code, util.EXIT_PACKAGE)


class Credentials(Sandbox):
    """A3 / N2 - references resolve, values are refused, a missing one fails loudly."""

    def _release_needing(self, name, required=True):
        return harness.approve(harness.build_manifest(
            self.source, self.rev, "1.0.0",
            credentials=[{"name": name, "required": required, "purpose": "test"}]))

    def test_a3_reference_resolves_from_the_environment(self):
        man = self._release_needing("ACME_API_KEY")
        cfg = harness.config(credentials={"ACME_API_KEY": "env:ACME_API_KEY"})
        os.environ["ACME_API_KEY"] = "not-a-real-value"
        self.addCleanup(os.environ.pop, "ACME_API_KEY", None)
        record, creds = install_mod.install(self.target, man, self.source, cfg)
        self.assertTrue(creds[0]["resolved"])
        # The record stores the reference and nothing else.
        blob = json.dumps(record)
        self.assertIn("env:ACME_API_KEY", blob)
        self.assertNotIn("not-a-real-value", blob)

    def test_a3b_dotenv_reference_resolves_by_name_only(self):
        man = self._release_needing("ACME_API_KEY")
        cfg = harness.config(credentials={"ACME_API_KEY": "dotenv:ACME_API_KEY"})
        os.makedirs(self.target, exist_ok=True)
        harness.write(self.target, ".env", "ACME_API_KEY=also-not-real\n")
        record, creds = install_mod.install(self.target, man, self.source, cfg)
        self.assertTrue(creds[0]["resolved"])
        self.assertNotIn("also-not-real", json.dumps(record))

    def test_n2_missing_required_credential_fails_loudly_and_writes_nothing(self):
        man = self._release_needing("ACME_API_KEY")
        cfg = harness.config(credentials={"ACME_API_KEY": "env:ACME_API_KEY"})
        os.environ.pop("ACME_API_KEY", None)
        with self.assertRaises(Refusal) as ctx:
            install_mod.install(self.target, man, self.source, cfg)
        self.assertEqual(ctx.exception.code, util.EXIT_CREDENTIAL)
        self.assertFalse(os.path.exists(os.path.join(self.target, "START_HERE.md")),
                         "a degraded install that looks fine is the failure mode we are avoiding")

    def test_n2b_missing_optional_credential_installs_but_says_so(self):
        man = self._release_needing("ACME_OPTIONAL", required=False)
        cfg = harness.config(credentials={})
        record, creds = install_mod.install(self.target, man, self.source, cfg)
        self.assertFalse(creds[0]["resolved"])
        self.assertEqual(creds[0]["reason"], "no reference in organization config")
        self.assertEqual(record["credentials"][0]["resolved"], False)

    def test_n2c_a_literal_value_in_config_is_refused_and_never_echoed(self):
        cfg = harness.config(credentials={"ACME_API_KEY": "sk-" + "ant-" + "a" * 40})
        problems = orgconfig.validate(cfg)
        self.assertTrue(problems)
        joined = " ".join(problems)
        self.assertIn("must be a reference", joined)
        self.assertNotIn("a" * 40, joined, "the error must not become the second leak")


class RoleScoping(Sandbox):
    """A2 / N3 - proven with the reduced role, through the real identity path."""

    def setUp(self):
        Sandbox.setUp(self)
        man = harness.approve(harness.build_manifest(self.source, self.rev, "1.0.0"))
        self.man = man
        install_mod.install(self.target, man, self.source, harness.config())
        self.policy = roles.load_policy(self.target)
        self.cfg = orgconfig.load(self.target)

    def test_a2_operator_enters_the_operator_workspace(self):
        self.be("acme-va")
        login, source = roles.identity()
        self.assertEqual(login, "acme-va")
        self.assertEqual(roles.role_for(self.cfg, login), "operator")
        self.assertEqual(roles.resolve_entry(self.policy, "operator", None), "operator")

    def test_n3_operator_cannot_reach_the_founder_entry(self):
        self.be("acme-va")
        with self.assertRaises(Refusal) as ctx:
            roles.resolve_entry(self.policy, "operator", "founder")
        self.assertEqual(ctx.exception.code, util.EXIT_ROLE)

    def test_n3b_operator_cannot_upgrade_or_roll_back(self):
        self.be("acme-va")
        for action in ("upgrade", "rollback", "install"):
            with self.assertRaises(Refusal) as ctx:
                roles.require_lifecycle(self.policy, self.cfg, action)
            self.assertEqual(ctx.exception.code, util.EXIT_ROLE, action)

    def test_n3c_an_unknown_identity_gets_no_role(self):
        self.be("some-stranger")
        with self.assertRaises(Refusal) as ctx:
            roles.require_lifecycle(self.policy, self.cfg, "upgrade")
        self.assertEqual(ctx.exception.code, util.EXIT_ROLE)

    def test_n3d_an_unidentifiable_operator_gets_no_role(self):
        self.nobody()
        with self.assertRaises(Refusal) as ctx:
            roles.require_lifecycle(self.policy, self.cfg, "upgrade")
        self.assertEqual(ctx.exception.code, util.EXIT_ROLE)

    def test_a2b_founder_may_do_both(self):
        self.be("acme-founder")
        login, role = roles.require_lifecycle(self.policy, self.cfg, "upgrade")
        self.assertEqual((login, role), ("acme-founder", "founder"))
        self.assertEqual(roles.resolve_entry(self.policy, "founder", "founder"), "founder")

    def test_n3e_the_cli_refuses_end_to_end_with_exit_3(self):
        """Through the real CLI, as an operator: the shipped path, not a library call."""
        self.be("acme-va")
        code, out, err = self.cli("start", "--target", self.target, "--entry", "founder")
        self.assertEqual(code, util.EXIT_ROLE, out + err)
        self.assertIn("may not enter", err)

    def test_a2c_the_cli_admits_an_unpinned_workspace(self):
        """A "Use this template" workspace must not look installed."""
        self.be("acme-va")
        os.remove(os.path.join(self.target, ".aios", "install.json"))
        code, out, _err = self.cli("start", "--target", self.target)
        self.assertEqual(code, 0)
        self.assertIn("UNPINNED", out)


class UpgradeAndRollback(Sandbox):
    """A4 / N4 / N5 - state survives both directions, and a kill is recoverable."""

    def setUp(self):
        Sandbox.setUp(self)
        self.v1 = harness.approve(harness.build_manifest(self.source, self.rev, "1.0.0"))
        install_mod.install(self.target, self.v1, self.source, harness.config())
        # the operator does real work: edits a seed, adds their own files
        harness.write(self.target, "CLAUDE.md", "# Your AIOS\nMY OWN CONSTITUTION\n")
        harness.write(self.target, "01_Foundations/market_analysis/_workspace.md", "MY MARKET\n")
        harness.write(self.target, "02_Deliverables/copy/my_ad.md", "my work\n")
        harness.write(self.target, ".claude/skills/my_skill/SKILL.md", "# mine\n")
        self.state_before = install_mod.state_fingerprint(self.target)

        rev2 = harness.bump_source(self.source, {
            "START_HERE.md": "# start here\nthe two commands, now clearer.\n",
            ".claude/skills/new_skill/SKILL.md": "# shipped later\n",
        })
        self.v2 = harness.approve(harness.build_manifest(self.source, rev2, "1.1.0"))

    def test_a4_upgrade_preserves_state_and_is_readback_verified(self):
        record = install_mod.upgrade(self.target, self.v2, self.source)
        self.assertEqual(record["release"]["version"], "1.1.0")
        self.assertEqual(install_mod.verify(self.target)[0], [])
        # the managed file really did change
        self.assertIn("now clearer",
                      open(os.path.join(self.target, "START_HERE.md")).read())
        self.assertTrue(os.path.isfile(
            os.path.join(self.target, ".claude", "skills", "new_skill", "SKILL.md")))
        # and nothing of the operator's did
        self.assertEqual(install_mod.state_fingerprint(self.target), self.state_before)
        self.assertIn("MY OWN CONSTITUTION", open(os.path.join(self.target, "CLAUDE.md")).read())

    def test_a4b_rollback_restores_and_is_readback_verified(self):
        install_mod.upgrade(self.target, self.v2, self.source)
        record, summary, _how = install_mod.rollback(self.target)
        self.assertEqual(summary["version"], "1.0.0")
        self.assertEqual(install_mod.verify(self.target)[0], [])
        self.assertNotIn("now clearer",
                         open(os.path.join(self.target, "START_HERE.md")).read())
        # a file the newer release introduced is gone again
        self.assertFalse(os.path.exists(
            os.path.join(self.target, ".claude", "skills", "new_skill", "SKILL.md")))
        # state survived the round trip
        self.assertEqual(install_mod.state_fingerprint(self.target), self.state_before)

    def test_n4_upgrade_over_a_dirty_workspace_is_refused(self):
        with open(os.path.join(self.target, "START_HERE.md"), "a") as fh:
            fh.write("hand-edited\n")
        with self.assertRaises(Refusal) as ctx:
            install_mod.upgrade(self.target, self.v2, self.source)
        self.assertEqual(ctx.exception.code, util.EXIT_VERIFY)
        self.assertNotIn("now clearer",
                         open(os.path.join(self.target, "START_HERE.md")).read(),
                         "a refused upgrade must not have written anything")

    def test_n4b_upgrade_over_a_partial_install_is_refused(self):
        util.write_json(os.path.join(self.target, ".aios", "txn.json"),
                        {"op": "upgrade", "phase": "applying", "backup": "x"})
        with self.assertRaises(Refusal) as ctx:
            install_mod.upgrade(self.target, self.v2, self.source)
        self.assertEqual(ctx.exception.code, util.EXIT_STATE)

    def test_n4c_a_downgrade_dressed_as_an_upgrade_is_refused(self):
        install_mod.upgrade(self.target, self.v2, self.source)
        with self.assertRaises(Refusal) as ctx:
            install_mod.upgrade(self.target, self.v1, self.source)
        self.assertEqual(ctx.exception.code, util.EXIT_PACKAGE)

    def test_n4d_min_upgrade_from_is_enforced(self):
        rev3 = harness.bump_source(self.source, {"START_HERE.md": "# v3\n"})
        v3 = harness.approve(harness.build_manifest(self.source, rev3, "2.0.0",
                                                    min_upgrade_from="1.5.0"))
        with self.assertRaises(Refusal) as ctx:
            install_mod.upgrade(self.target, v3, self.source)
        self.assertEqual(ctx.exception.code, util.EXIT_PACKAGE)

    def test_n4e_a_collision_with_the_operators_own_file_is_refused(self):
        """A newly shipped path that already exists as your work is never eaten."""
        harness.write(self.target, ".claude/skills/new_skill/SKILL.md", "MINE FIRST\n")
        with self.assertRaises(Refusal) as ctx:
            install_mod.upgrade(self.target, self.v2, self.source)
        self.assertEqual(ctx.exception.code, util.EXIT_STATE)
        self.assertEqual("MINE FIRST\n",
                         open(os.path.join(self.target, ".claude", "skills", "new_skill",
                                           "SKILL.md")).read())

    def test_n5_a_failed_upgrade_rolls_itself_back(self):
        os.environ["AIOS_FAULT"] = "raise:upgrade.mid_write"
        with self.assertRaises(Refusal) as ctx:
            install_mod.upgrade(self.target, self.v2, self.source)
        self.assertIn(ctx.exception.code, (util.EXIT_VERIFY, util.EXIT_PACKAGE))
        os.environ.pop("AIOS_FAULT")
        problems, summary = install_mod.verify(self.target)
        self.assertEqual(problems, [])
        self.assertEqual(summary["version"], "1.0.0")
        self.assertEqual(install_mod.state_fingerprint(self.target), self.state_before)

    def test_n5b_rollback_recovers_a_hard_killed_upgrade(self):
        """kill -9 in the middle: no cleanup runs, only the journal survives."""
        code = subprocess.call(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0, %r);"
             "from aioslib import install as i, util;"
             "man=util.read_json(%r);"
             "i.upgrade(%r, man, %r)" % (harness.AIOS_DIR,
                                         self.write_json("v2.json", self.v2),
                                         self.target, self.source)],
            env=dict(os.environ, AIOS_FAULT="crash:upgrade.mid_write"),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.assertEqual(code, 137, "the fixture must actually die mid-write")

        journal = install_mod.load_journal(self.target)
        self.assertIsNotNone(journal, "a killed upgrade must leave a journal behind")
        # the workspace is genuinely broken at this point
        self.assertNotEqual(install_mod.verify(self.target)[0], [])

        record, summary, how = install_mod.rollback(self.target)
        self.assertEqual(summary["version"], "1.0.0")
        self.assertEqual(install_mod.verify(self.target)[0], [])
        self.assertIn("recovered", how)
        self.assertEqual(install_mod.state_fingerprint(self.target), self.state_before)
        self.assertIsNone(install_mod.load_journal(self.target))


class Adoption(Sandbox):
    """The "Use this template" path back onto the contract."""

    def test_adopt_pins_a_matching_workspace(self):
        man = harness.approve(harness.build_manifest(self.source, self.rev, "1.0.0"))
        subprocess.run(["git", "clone", "-q", self.source, self.target], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        record = install_mod.adopt(self.target, man, self.source, harness.config())
        self.assertEqual(record["release"]["version"], "1.0.0")
        self.assertTrue(record["adopted"])
        self.assertEqual(install_mod.verify(self.target)[0], [])

    def test_adopt_refuses_a_workspace_that_does_not_match(self):
        man = harness.approve(harness.build_manifest(self.source, self.rev, "1.0.0"))
        subprocess.run(["git", "clone", "-q", self.source, self.target], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        harness.write(self.target, "START_HERE.md", "drifted\n")
        with self.assertRaises(Refusal) as ctx:
            install_mod.adopt(self.target, man, self.source, harness.config())
        self.assertEqual(ctx.exception.code, util.EXIT_VERIFY)


if __name__ == "__main__":
    import unittest

    unittest.main()


class Concurrency(Sandbox):
    """Two mutations at once. The journal makes a crash recoverable; the lock stops a race."""

    def setUp(self):
        Sandbox.setUp(self)
        self.v1 = harness.approve(harness.build_manifest(self.source, self.rev, "1.0.0"))
        install_mod.install(self.target, self.v1, self.source, harness.config())
        rev2 = harness.bump_source(self.source, {"START_HERE.md": "# v2\n"})
        self.v2 = harness.approve(harness.build_manifest(self.source, rev2, "1.1.0"))

    def test_a_second_upgrade_is_refused_while_one_holds_the_lock(self):
        lock = install_mod._Lock(self.target, "upgrade")
        lock.__enter__()
        try:
            with self.assertRaises(Refusal) as ctx:
                install_mod.upgrade(self.target, self.v2, self.source)
            self.assertEqual(ctx.exception.code, util.EXIT_STATE)
            self.assertIn("already running", ctx.exception.message)
        finally:
            lock.__exit__(None, None, None)
        # released: the upgrade now succeeds
        record = install_mod.upgrade(self.target, self.v2, self.source)
        self.assertEqual(record["release"]["version"], "1.1.0")

    def test_rollback_clears_a_lock_left_by_a_killed_holder(self):
        install_mod.upgrade(self.target, self.v2, self.source)
        harness.write(self.target, install_mod.LOCK_PATH, "upgrade pid=99999 (killed)\n")
        record, summary, _how = install_mod.rollback(self.target)
        self.assertEqual(summary["version"], "1.0.0")
        self.assertFalse(os.path.exists(os.path.join(self.target, install_mod.LOCK_PATH)))

    def test_the_lock_is_released_on_success_and_on_refusal(self):
        install_mod.upgrade(self.target, self.v2, self.source)
        self.assertFalse(os.path.exists(os.path.join(self.target, install_mod.LOCK_PATH)))
        with self.assertRaises(Refusal):
            install_mod.upgrade(self.target, self.v1, self.source)  # downgrade, refused
        self.assertFalse(os.path.exists(os.path.join(self.target, install_mod.LOCK_PATH)),
                         "a refusal must not leave the workspace locked")


class TwoFamilyReviewRegressions(Sandbox):
    """Seven defects found by a Gemini + DeepSeek review of this change, each reproduced
    before being fixed. Two of them - the symlink write and the missing `adopt` role check -
    were found by BOTH families independently, which is the strongest signal the routing
    produced."""

    def _installed(self, version="1.0.0"):
        man = harness.approve(harness.build_manifest(self.source, self.rev, version))
        install_mod.install(self.target, man, self.source, harness.config())
        return man

    def test_rollback_refuses_to_overwrite_work_in_a_path_the_release_freed(self):
        rev1 = harness.bump_source(self.source, {"dropped.txt": "managed in v1\n"})
        v1 = harness.approve(harness.build_manifest(self.source, rev1, "1.0.0"))
        install_mod.install(self.target, v1, self.source, harness.config())
        harness.run_git(self.source, "rm", "-q", "dropped.txt")
        harness.run_git(self.source, "commit", "-qm", "drop it")
        v2 = harness.approve(harness.build_manifest(
            self.source, util.git(self.source, ["rev-parse", "HEAD"]), "2.0.0"))
        install_mod.upgrade(self.target, v2, self.source)
        # the path is free; the operator puts their own work there
        harness.write(self.target, "dropped.txt", "operator's precious work\n")
        with self.assertRaises(Refusal) as ctx:
            install_mod.rollback(self.target)
        self.assertEqual(ctx.exception.code, util.EXIT_STATE)
        self.assertEqual("operator's precious work\n",
                         open(os.path.join(self.target, "dropped.txt")).read())

    def test_verify_against_the_pin_catches_a_tampered_install_record(self):
        self._installed()
        target_file = os.path.join(self.target, "START_HERE.md")
        with open(target_file, "w") as fh:
            fh.write("tampered\n")
        record_path = os.path.join(self.target, ".aios", "install.json")
        record = util.read_json(record_path)
        for entry in record["managed"]:
            if entry["path"] == "START_HERE.md":
                entry["sha256"] = util.sha256_file(target_file)
        util.write_json(record_path, record)
        # circular check agrees with itself...
        self.assertEqual(install_mod.verify(self.target)[0], [])
        # ...the cross-check against the pinned release does not
        problems, _ = install_mod.verify(self.target, None, self.source)
        self.assertTrue(any("does not match the pinned release" in p for p in problems),
                        problems)

    def test_upgrade_refuses_to_write_through_a_symlink(self):
        """Found by both families. The write escaped the workspace entirely."""
        self._installed()
        escaped = os.path.join(self.tmp, "escaped.txt")
        newp = os.path.join(self.target, ".claude", "skills", "new_skill", "SKILL.md")
        os.makedirs(os.path.dirname(newp), exist_ok=True)
        os.symlink(escaped, newp)
        rev2 = harness.bump_source(self.source,
                                   {".claude/skills/new_skill/SKILL.md": "# shipped later\n"})
        v2 = harness.approve(harness.build_manifest(self.source, rev2, "1.1.0"))
        with self.assertRaises(Refusal) as ctx:
            install_mod.upgrade(self.target, v2, self.source)
        self.assertEqual(ctx.exception.code, util.EXIT_STATE)
        self.assertFalse(os.path.exists(escaped), "a release file was written outside the workspace")

    def test_a_corrupt_install_record_refuses_instead_of_crashing_recovery(self):
        self._installed()
        with open(os.path.join(self.target, ".aios", "install.json"), "w") as fh:
            fh.write("{partial_json")
        with self.assertRaises(Refusal) as ctx:
            install_mod.rollback(self.target)
        self.assertEqual(ctx.exception.code, util.EXIT_STATE)
        self.assertIn("corrupt", ctx.exception.message)

    def test_records_are_written_atomically(self):
        """A truncating write is what let a kill leave unparseable JSON behind."""
        self._installed()
        record_path = os.path.join(self.target, ".aios", "install.json")
        util.write_json(record_path, {"schema": "x"})
        self.assertFalse(os.path.exists(record_path + ".tmp"))
        self.assertEqual(util.read_json(record_path)["schema"], "x")

    def test_upgrade_does_not_resurrect_a_seed_the_operator_deleted(self):
        self._installed()
        seed = os.path.join(self.target, "CLAUDE.md")
        os.remove(seed)
        rev2 = harness.bump_source(self.source, {"START_HERE.md": "# v2\n"})
        v2 = harness.approve(harness.build_manifest(self.source, rev2, "1.1.0"))
        install_mod.upgrade(self.target, v2, self.source)
        self.assertFalse(os.path.exists(seed),
                         "'written once, never touched again' includes not undoing a delete")

    def test_a_failed_upgrade_removes_seeds_it_created(self):
        self._installed()
        before = install_mod.state_fingerprint(self.target)
        rev2 = harness.bump_source(self.source, {"START_HERE.md": "# v2\n",
                                                 "06_Communication/new_seed.md": "new\n"})
        v2 = harness.approve(harness.build_manifest(self.source, rev2, "1.1.0"))
        os.environ["AIOS_FAULT"] = "raise:upgrade.before_record"
        try:
            with self.assertRaises(Refusal):
                install_mod.upgrade(self.target, v2, self.source)
        finally:
            os.environ.pop("AIOS_FAULT", None)
        self.assertFalse(os.path.exists(
            os.path.join(self.target, "06_Communication", "new_seed.md")))
        self.assertEqual(install_mod.state_fingerprint(self.target), before,
                         "a rollback that leaves new files behind did not restore state")

    def test_adopt_is_founder_only_through_the_cli(self):
        """Found by both families: the policy said founder, the CLI never checked."""
        man = harness.approve(harness.build_manifest(self.source, self.rev, "1.0.0"))
        subprocess.run(["git", "clone", "-q", self.source, self.target], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.be("acme-va")
        code, _out, err = self.cli("adopt", "--repo", self.source,
                                   "--release", self.write_json("man.json", man),
                                   "--target", self.target,
                                   "--config", self.write_json("cfg.json", harness.config()))
        self.assertEqual(code, util.EXIT_ROLE, err)
        self.be("acme-founder")
        code, _out, err = self.cli("adopt", "--repo", self.source,
                                   "--release", self.write_json("man.json", man),
                                   "--target", self.target,
                                   "--config", self.write_json("cfg.json", harness.config()))
        self.assertEqual(code, 0, err)
