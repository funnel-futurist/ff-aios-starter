"""Starter 3.1: adopting a release into an instance that already exists (G81), and founder-lane
reviewers declared separately from founder status (G98).

Phoenix, 2026-10-14 (ai-os #532): "safe Starter adoption into FF's existing AIOS with NO OVERWRITE.
... Implement approved components/explicit overrides with rehearsal and rollback; do not infer
existing adoption works already." Phoenix, 2026-10-15 (G98): "no-overwrite 18-file adoption with
business founder role separate from CODEOWNER permission."
"""

import json
import os
import shutil
import subprocess
import sys
import unittest

import harness
from harness import Sandbox, run_git, write

sys.path.insert(0, harness.AIOS_DIR)
from aioslib import governance, install as install_mod, util  # noqa: E402
from aioslib.util import Refusal  # noqa: E402

from test_layout_3_0 import CORE_LINE, MAP_LINE, V3_SPEC, Layout3, bump_to_v3, diff, snapshot  # noqa: E402

FF_ROLES = json.loads(json.dumps(harness.ROLES))
FF_ROLES["roles"]["operator"]["paths_denied"] = [".github/**", "CLAUDE.md"]

# The fixture release ships 12 paths. The instance keeps its own CLAUDE.md, README.md, .gitignore,
# settings and role policy; adopts the runtime-ish files it doesn't have; excludes the rest.
PLAN = {
    "schema": "ff-aios-starter/adoption@1",
    "adopt": ["scripts/team/**", "START_HERE.md", ".aios/.gitignore", ".claude/skills/**"],
    "instance_owned": [".claude/settings.json", ".aios/roles.json", "CLAUDE.md", "README.md", ".gitignore"],
    "exclude": ["templates/**", "01_Foundations/**", "06_Communication/**"],
}
ADOPTED = [".aios/.gitignore", ".claude/skills/start-my-day/SKILL.md", "START_HERE.md",
           "scripts/team/git-safety-check.sh"]


class Existing(Sandbox):
    """A company's own repository that was never a Starter copy, then an adoption into it."""

    def setUp(self):
        super(Existing, self).setUp()
        self.v = harness.approve(harness.build_manifest(self.source, self.rev, "3.0.0"))
        # The source's own record of the release, as a real approved release has: undoing a finished
        # adoption checks it names the pin (3.1 round 24). releases/ isn't shipped, so the pin holds.
        write(self.source, "releases/%s.json" % self.v["release_id"], json.dumps(self.v, indent=2))
        run_git(self.source, "add", "-A")
        run_git(self.source, "commit", "-qm", "the release record")
        t = self.target
        write(t, "CLAUDE.md", "# OUR OWN brain\nOur rules, not the Starter's.\n")
        write(t, "README.md", "# our company repo\n")
        write(t, ".gitignore", "node_modules/\n.env\n")
        write(t, ".claude/settings.json", json.dumps({"permissions": {"deny": ["Read(secrets/**)"]}}))
        write(t, ".aios/roles.json", json.dumps(FF_ROLES, indent=2))
        write(t, "01_Foundations/our_own.md", "# a folder of ours with a 2.x name\n")
        write(t, "06_Clients/acme/notes.md", "# client work\n")
        os.makedirs(os.path.join(t, "empty_of_ours"))
        self.write_plan(PLAN)
        self.commit("our repo, before any Starter")

    def write_plan(self, plan):
        write(self.target, ".aios/adoption.json", json.dumps(plan, indent=2))

    def commit(self, msg):
        t = self.target
        if not os.path.isdir(os.path.join(t, ".git")):
            run_git(t, "init", "-q", "-b", "main")
            run_git(t, "config", "user.email", "ff@example.com")
            run_git(t, "config", "user.name", "ff")
        run_git(t, "add", "-A")
        run_git(t, "commit", "-qm", msg)

    def forget_state(self):
        """As a machine without this workspace's local note would be (a fresh clone has none)."""
        note = os.path.join(self.target, ".aios", "backups", "state", "head.json")
        if os.path.isfile(note):
            os.remove(note)

    def adopt(self, manifest=None, **kw):
        return install_mod.adopt_existing(self.target, manifest or self.v, self.source,
                                          kw.pop("config", None) or harness.config(), **kw)

    def refuses_unchanged(self, fn, *args, **kw):
        before = snapshot(self.target)
        with self.assertRaises(Refusal) as ctx:
            fn(*args, **kw)
        self.assertEqual(diff(before, snapshot(self.target)), [], "a refusal changed the instance")
        return ctx.exception


class Adoption(Existing):

    def test_it_creates_only_what_it_adopts_and_writes_nothing_of_the_instances(self):
        before = snapshot(self.target)
        record = self.adopt()
        after = snapshot(self.target)
        changed = [k for k in before if before[k] != after.get(k)]
        self.assertEqual([k for k in changed if k != "<git status>"], [], changed)
        new_files = sorted(k for k in after if k not in before and os.path.isfile(os.path.join(self.target, k)))
        self.assertEqual(new_files, sorted(ADOPTED + [".aios/config.json", ".aios/install.json"]))
        self.assertEqual(sorted(e["path"] for e in record["adoption"]["created"]),
                         sorted(ADOPTED + [".aios/config.json"]))
        self.assertEqual(install_mod.verify(self.target)[0], [])
        self.assertEqual(install_mod.verify(self.target, source_repo=self.source)[0], [])

    def test_an_adopted_executable_keeps_its_bit(self):
        os.chmod(os.path.join(self.source, "scripts/team/git-safety-check.sh"), 0o755)
        rev = harness.bump_source(self.source, {}, "an executable")
        self.adopt(harness.approve(harness.build_manifest(self.source, rev, "3.0.0")))
        self.assertTrue(os.stat(os.path.join(self.target, "scripts/team/git-safety-check.sh")).st_mode & 0o100)


class RefusesWithNothingChanged(Existing):

    def plan_without(self, cls, item):
        plan = json.loads(json.dumps(PLAN))
        plan[cls] = [x for x in plan[cls] if x != item]
        return plan

    def test_a_path_the_plan_doesnt_classify(self):
        self.write_plan(self.plan_without("exclude", "templates/**"))
        self.commit("forgot one")
        exc = self.refuses_unchanged(self.adopt)
        self.assertIn("templates/governance/CODEOWNERS.template: not in the plan", "\n".join(exc.details))

    def test_a_path_in_two_lists(self):
        plan = json.loads(json.dumps(PLAN))
        plan["exclude"].append("START_HERE.md")
        self.write_plan(plan)
        self.commit("twice")
        exc = self.refuses_unchanged(self.adopt)
        self.assertIn("START_HERE.md: in more than one list (adopt, exclude)", exc.details)

    def test_a_catch_all_can_never_silently_classify_the_rest(self):
        plan = json.loads(json.dumps(PLAN))
        plan["exclude"] = ["**"]
        self.write_plan(plan)
        self.commit("catch-all")
        exc = self.refuses_unchanged(self.adopt)
        self.assertIn("every path at once", "\n".join(exc.details))

    def test_an_adopted_path_that_already_exists(self):
        write(self.target, "START_HERE.md", "# ours already\n")
        self.commit("ours")
        exc = self.refuses_unchanged(self.adopt)
        self.assertIn("adoption never overwrites", exc.message)

    def test_a_path_declared_the_instances_that_isnt_there(self):
        os.remove(os.path.join(self.target, "README.md"))
        self.commit("no readme")
        exc = self.refuses_unchanged(self.adopt)
        self.assertIn("don't exist", exc.message)

    def test_uncommitted_work(self):
        write(self.target, "06_Clients/acme/draft.md", "unsaved\n")
        exc = self.refuses_unchanged(self.adopt)
        self.assertIn("uncommitted", exc.message)

    def test_no_role_policy_of_its_own(self):
        os.remove(os.path.join(self.target, ".aios/roles.json"))
        plan = self.plan_without("instance_owned", ".aios/roles.json")
        plan["exclude"].append(".aios/roles.json")
        self.write_plan(plan)
        self.commit("no policy")
        exc = self.refuses_unchanged(self.adopt)
        self.assertIn("role policy", exc.message)

    def test_no_plan_and_a_plan_outside_the_instance(self):
        os.remove(os.path.join(self.target, ".aios/adoption.json"))
        self.commit("no plan")
        self.refuses_unchanged(self.adopt)
        self.refuses_unchanged(self.adopt, plan_rel="../elsewhere.json")

    def test_a_linked_folder_on_the_way(self):
        outside = os.path.join(self.tmp, "outside")
        os.makedirs(outside)
        os.symlink(outside, os.path.join(self.target, "scripts"))
        self.commit("scripts is a link")
        self.refuses_unchanged(self.adopt)
        self.assertEqual(os.listdir(outside), [])

    def test_a_different_org_config(self):
        write(self.target, ".aios/config.json", json.dumps(dict(harness.config(), org_id="someone-else")))
        self.commit("their config")
        exc = self.refuses_unchanged(self.adopt)
        self.assertIn("different organization config", exc.message)

    def test_an_already_pinned_workspace(self):
        self.adopt()
        self.commit("adopted")
        exc = self.refuses_unchanged(self.adopt)
        self.assertIn("use upgrade", exc.message)

    def test_an_unapproved_release(self):
        draft = harness.build_manifest(self.source, self.rev, "3.0.0")
        self.refuses_unchanged(self.adopt, draft)


class NeverMovesOrAddsALine(Existing):
    """3.0's folder move would relocate the instance's own 01_Foundations; its seed line would edit
    the instance's own CLAUDE.md. Neither ever happens to an existing instance."""

    def v3_plan(self):
        return {"schema": "ff-aios-starter/adoption@1",
                "adopt": ["scripts/team/**", "START_HERE.md", ".aios/.gitignore", ".claude/skills/**"],
                "instance_owned": [".claude/settings.json", ".aios/roles.json", "CLAUDE.md", "README.md",
                                   ".gitignore"],
                "exclude": ["templates/**", "00_AIOS/**", "02_Team_Ops/**", "04_Attention/**",
                            "release/**"]}

    def test_adopting_and_upgrading_a_release_with_a_folder_move(self):
        rev3 = bump_to_v3(self.source)
        v3 = harness.approve(harness.build_manifest(self.source, rev3, "3.0.0"))
        self.assertTrue(v3.get("layout") and v3.get("seed_lines"))
        # the source's own record of this release, as a real one has (an upgrade checks the pin against it)
        write(self.source, "releases/starter-3.0.0.json", json.dumps(v3, indent=2))
        run_git(self.source, "add", "-A")
        run_git(self.source, "commit", "-qm", "the 3.0 release record")
        self.write_plan(self.v3_plan())
        self.commit("plan for 3.0")
        ours = snapshot(self.target)
        self.adopt(v3)
        self.commit("adopted 3.0")
        rev31 = harness.bump_source(self.source, {"scripts/team/new_tool.sh": "#!/bin/sh\necho new\n",
                                                  "START_HERE.md": "# start here\n3.1.\n"}, "3.1")
        v31 = harness.approve(harness.build_manifest(self.source, rev31, "3.1.0"))
        install_mod.upgrade(self.target, v31, self.source)
        after = snapshot(self.target)
        for rel in ("01_Foundations/our_own.md", "CLAUDE.md", "06_Clients/acme/notes.md"):
            self.assertEqual(ours[rel], after[rel], rel)
        with open(os.path.join(self.target, "CLAUDE.md")) as fh:
            self.assertNotIn(MAP_LINE, fh.read())
        self.assertFalse(os.path.exists(os.path.join(self.target, "00_AIOS")))
        self.assertTrue(os.path.isfile(os.path.join(self.target, "scripts/team/new_tool.sh")))
        record = install_mod.load_record(self.target)
        self.assertNotIn("layout", record)
        self.assertEqual(install_mod.verify(self.target, source_repo=self.source)[0], [])


class Upgrades(Existing):

    def adopted(self):
        self.adopt()
        self.commit("adopted")

    def test_a_new_path_the_plan_doesnt_classify_refuses(self):
        self.adopted()
        rev = harness.bump_source(self.source, {"docs/new_guide.md": "# new\n"}, "3.1")
        v31 = harness.approve(harness.build_manifest(self.source, rev, "3.1.0"))
        exc = self.refuses_unchanged(install_mod.upgrade, self.target, v31, self.source)
        self.assertIn("docs/new_guide.md: not in the plan", "\n".join(exc.details))

    def test_only_adopted_paths_are_written(self):
        self.adopted()
        rev = harness.bump_source(self.source, {".claude/settings.json": "{}\n", "README.md": "# theirs\n",
                                                "START_HERE.md": "# start here\nnew.\n"}, "3.1")
        v31 = harness.approve(harness.build_manifest(self.source, rev, "3.1.0"))
        install_mod.upgrade(self.target, v31, self.source)
        with open(os.path.join(self.target, ".claude/settings.json")) as fh:
            self.assertIn("secrets", fh.read())  # the instance's, untouched
        with open(os.path.join(self.target, "README.md")) as fh:
            self.assertEqual(fh.read(), "# our company repo\n")
        with open(os.path.join(self.target, "START_HERE.md")) as fh:
            self.assertEqual(fh.read(), "# start here\nnew.\n")  # adopted, so upgraded

    def test_a_file_the_instance_stops_adopting_stays_as_its_own(self):
        self.adopted()
        plan = json.loads(json.dumps(PLAN))
        plan["adopt"].remove("START_HERE.md")
        plan["instance_owned"].append("START_HERE.md")
        self.write_plan(plan)
        self.commit("START_HERE.md is ours now")
        rev = harness.bump_source(self.source, {"START_HERE.md": "# start here\nnew.\n"}, "3.1")
        v31 = harness.approve(harness.build_manifest(self.source, rev, "3.1.0"))
        record = install_mod.upgrade(self.target, v31, self.source)
        with open(os.path.join(self.target, "START_HERE.md")) as fh:
            self.assertEqual(fh.read(), "# start here\nthe two commands.\n")  # kept, not deleted or updated
        self.assertNotIn("START_HERE.md", [e["path"] for e in record["managed"]])

    def test_an_upgrade_then_rollback_returns_the_adopted_instance(self):
        self.adopted()
        before = snapshot(self.target)
        rev = harness.bump_source(self.source, {"START_HERE.md": "# start here\nnew.\n"}, "3.1")
        install_mod.upgrade(self.target, harness.approve(harness.build_manifest(self.source, rev, "3.1.0")),
                            self.source)
        install_mod.rollback(self.target, self.source)
        backups = set(os.listdir(os.path.join(self.target, ".aios", "backups")))
        self.assertEqual(diff(before, snapshot(self.target, backups=())), [])
        self.assertTrue(backups)


class Rollback(Existing):

    def test_rollback_undoes_a_finished_adoption_exactly(self):
        before = snapshot(self.target)
        self.adopt()
        _r, summary, how = install_mod.rollback(self.target, self.source)
        self.assertIsNone(summary["release_id"])
        self.assertIn("adoption was undone", how)
        self.assertEqual(diff(before, snapshot(self.target)), [])

    def test_rollback_leaves_an_adopted_file_the_instance_has_changed(self):
        self.adopt()
        write(self.target, "START_HERE.md", "# start here, edited by us\n")
        _r, _s, how = install_mod.rollback(self.target, self.source)
        self.assertIn("START_HERE.md changed", how)
        with open(os.path.join(self.target, "START_HERE.md")) as fh:
            self.assertIn("edited by us", fh.read())

    def test_a_killed_adoption_is_undone_by_the_next_rollback(self):
        self.be("acme-founder")
        cfg = self.write_json("org.json", harness.config())
        rel = self.write_json("release.json", self.v)
        for point in ("adopt.after_journal", "adopt.mid_write", "adopt.before_record"):
            with self.subTest(point=point):
                before = snapshot(self.target)
                code, _o, _e = self.cli("adopt", "--existing", "--release", rel, "--target", self.target,
                                        "--config", cfg, "--repo", self.source,
                                        env={"AIOS_FAULT": "crash:" + point})
                self.assertEqual(code, 137)
                self.assertTrue(os.path.isfile(install_mod.journal_path(self.target)))
                code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
                self.assertEqual(code, 0, out + err)
                self.assertIn("interrupted adoption was undone", out)
                self.assertEqual(diff(before, snapshot(self.target)), [])

    def test_the_cli_adopts_and_says_what_it_did(self):
        self.be("acme-founder")
        cfg = self.write_json("org.json", harness.config())
        rel = self.write_json("release.json", self.v)
        code, out, err = self.cli("adopt", "--existing", "--release", rel, "--target", self.target,
                                  "--config", cfg, "--repo", self.source)
        self.assertEqual(code, 0, out + err)
        self.assertIn("created:  4 file(s)", out)
        self.assertIn("no folder move, no seed line", out)
        code, _o, err = self.cli("adopt", "--release", rel, "--target", self.target, "--config", cfg,
                                 "--repo", self.source, "--plan", ".aios/adoption.json")
        self.assertNotEqual(code, 0)


class VerifyAgainstTheRelease(Existing):

    def test_an_adopted_file_dropped_from_record_and_disk_is_caught(self):
        record = self.adopt()
        record["managed"] = [e for e in record["managed"] if e["path"] != "START_HERE.md"]
        util.write_json(install_mod.install_record_path(self.target), record)
        os.remove(os.path.join(self.target, "START_HERE.md"))
        problems, _ = install_mod.verify(self.target, source_repo=self.source)
        self.assertTrue(any("START_HERE.md" in p for p in problems), problems)

    def test_the_instances_own_files_arent_expected(self):
        self.adopt()
        problems, _ = install_mod.verify(self.target, source_repo=self.source)
        self.assertEqual(problems, [])  # .claude/settings.json etc. are managed by the release, not here


CODEOWNERS = ("# aios-codeowners-for: acme/acme-aios\n"
              "/.github/   @acme-founder @acme-va @acme-lead\n"
              "/CLAUDE.md  @acme-founder @acme-va @acme-lead\n")


class LaneReviewers(Sandbox):
    """G98: who may approve the founder lane is declared apart from who is a founder."""

    def setUp(self):
        super(LaneReviewers, self).setUp()
        write(self.target, ".github/CODEOWNERS", CODEOWNERS)
        self.config = harness.config(people=[
            {"github": "acme-founder", "role": "founder", "display_name": "F"},
            {"github": "acme-va", "role": "operator", "display_name": "V"},
            {"github": "acme-lead", "role": "operator", "display_name": "L"}])
        self.policy = json.loads(json.dumps(FF_ROLES))

    def check(self):
        return governance.founder_review_local(self.target, self.policy, self.config)

    def test_without_a_declaration_founder_status_decides_and_operators_fail_it(self):
        results = self.check()
        self.assertTrue(all(st == "FAIL" for st, _d in results), results)
        self.assertIn("not only founders", results[0][1])

    def test_declared_reviewers_pass_without_becoming_founders(self):
        self.policy["founder_lane_reviewers"] = ["@acme-founder", "@acme-va", "@acme-lead"]
        results = self.check()
        self.assertEqual([st for st, _d in results if st != "INFO"], ["PASS", "PASS"], results)
        info = [d for st, d in results if st == "INFO"][0]
        self.assertIn("not founder status", info)
        self.assertFalse(any(" founders" in d or "a founder" in d for _s, d in results), results)
        self.assertEqual(governance.founders_of(self.config), ["@acme-founder"])  # status unchanged

    def test_declared_but_missing_one_owner_fails_with_the_reviewer_wording(self):
        self.policy["founder_lane_reviewers"] = ["@acme-founder", "@acme-va"]
        results = self.check()
        self.assertTrue(any("not only approved founder-lane reviewers" in d for _s, d in results), results)

    def test_a_reviewer_outside_the_people_map_or_a_team_is_refused(self):
        for bad in (["@someone-else"], ["@acme/leads"], [], "acme-founder"):
            with self.subTest(bad=bad):
                self.policy["founder_lane_reviewers"] = bad
                results = self.check()
                self.assertTrue(results and all(st == "FAIL" for st, _d in results), results)


if __name__ == "__main__":
    unittest.main()


class ReviewRoundOne(Existing):
    """Gemini and Codex, 3.1 round 1."""

    def test_g1_a_file_the_plan_keeps_is_never_deleted_when_the_release_drops_it(self):
        self.adopt()
        self.commit("adopted")
        plan = json.loads(json.dumps(PLAN))
        plan["adopt"].remove("START_HERE.md")
        plan["instance_owned"].append("START_HERE.md")
        self.write_plan(plan)
        self.commit("START_HERE.md is ours now")
        run_git(self.source, "rm", "-q", "START_HERE.md")  # and the next release stops shipping it
        v31 = harness.approve(harness.build_manifest(self.source, harness.bump_source(self.source, {}, "3.1"),
                                                     "3.1.0"))
        self.assertNotIn("START_HERE.md", install_mod.upgrade_plan(self.target, v31, self.source)["removed"])
        install_mod.upgrade(self.target, v31, self.source)
        self.assertTrue(os.path.isfile(os.path.join(self.target, "START_HERE.md")))

    def test_g1_a_file_the_plan_still_adopts_goes_when_the_release_drops_it(self):
        self.adopt()
        self.commit("adopted")
        run_git(self.source, "rm", "-q", "START_HERE.md")
        v31 = harness.approve(harness.build_manifest(self.source, harness.bump_source(self.source, {}, "3.1"),
                                                     "3.1.0"))
        self.assertIn("START_HERE.md", install_mod.upgrade_plan(self.target, v31, self.source)["removed"])
        install_mod.upgrade(self.target, v31, self.source)
        self.assertFalse(os.path.exists(os.path.join(self.target, "START_HERE.md")))

    def test_c1_a_guard_file_of_the_repositorys_own_is_never_touched(self):
        write(self.target, ".aios/backups/guard", "ours\n")
        self.commit("a file of ours at the guard's path")
        exc = self.refuses_unchanged(self.adopt)
        self.assertIn("own paths", exc.message)
        with open(os.path.join(self.target, ".aios/backups/guard")) as fh:
            self.assertEqual(fh.read(), "ours\n")

    def test_c2_json_is_never_written_through_a_planted_temporary_name(self):
        outside = os.path.join(self.tmp, "outside.json")
        with open(outside, "w") as fh:
            fh.write("untouched\n")
        path = os.path.join(self.tmp, "state", "record.json")
        os.makedirs(os.path.dirname(path))
        os.symlink(outside, path + ".tmp")
        util.write_json(path, {"a": 1})
        with open(outside) as fh:
            self.assertEqual(fh.read(), "untouched\n")
        self.assertTrue(os.path.islink(path + ".tmp"))
        self.assertEqual(util.read_json(path), {"a": 1})

    def test_c3_a_file_that_appears_while_adopting_is_never_replaced(self):
        real_fault = install_mod.util.fault

        def plant(point):
            if point == "adopt.mid_write":
                write(self.target, "scripts/team/git-safety-check.sh", "someone else's, just now\n")
            real_fault(point)
        install_mod.util.fault = plant
        try:
            with self.assertRaises(Refusal) as ctx:
                self.adopt()
        finally:
            install_mod.util.fault = real_fault
        self.assertIn("appeared while this ran", ctx.exception.message)
        with open(os.path.join(self.target, "scripts/team/git-safety-check.sh")) as fh:
            self.assertEqual(fh.read(), "someone else's, just now\n")
        self.assertFalse(os.path.exists(os.path.join(self.target, ".aios/.gitignore")))  # the rest undone
        self.assertIsNone(install_mod.load_journal(self.target))

    def kill(self, point, *args):
        self.be("acme-founder")
        cfg = self.write_json("org.json", harness.config())
        rel = self.write_json("release.json", self.v)
        return self.cli(*(args or ("adopt", "--existing", "--release", rel, "--target", self.target,
                                   "--config", cfg, "--repo", self.source)),
                        env={"AIOS_FAULT": "crash:" + point})

    def test_c4_rollback_never_deletes_a_matching_file_it_didnt_write(self):
        code, _o, _e = self.kill("adopt.mid_write")
        self.assertEqual(code, 137)
        # The script isn't written yet; someone puts the release's exact bytes there by hand.
        with open(os.path.join(self.source, "scripts/team/git-safety-check.sh"), "rb") as fh:
            write(self.target, "scripts/team/git-safety-check.sh", fh.read())
        code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
        self.assertEqual(code, 0, out + err)
        self.assertTrue(os.path.isfile(os.path.join(self.target, "scripts/team/git-safety-check.sh")))
        self.assertFalse(os.path.exists(os.path.join(self.target, ".aios/install.json")))

    def test_c5_a_killed_undo_is_finished_by_the_next_rollback(self):
        before = snapshot(self.target)
        self.adopt()
        for point in ("adopt.undo_before", "adopt.undo_mid"):
            with self.subTest(point=point):
                if not os.path.isfile(install_mod.install_record_path(self.target)):
                    self.adopt()
                code, _o, _e = self.kill(point, "rollback", "--target", self.target, "--repo", self.source)
                self.assertEqual(code, 137)
                code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
                self.assertEqual(code, 0, out + err)
                self.assertEqual(diff(before, snapshot(self.target)), [])

    def test_c5_a_dead_lock_from_before_the_journal_clears_without_a_people_map(self):
        write(self.target, ".aios/lock", "adopt pid=999999 at then\n")
        code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
        self.assertEqual(code, 0, out + err)
        self.assertIn("nothing to roll back", out)
        self.assertFalse(os.path.lexists(os.path.join(self.target, ".aios/lock")))

    def test_c6_c8_rollback_compares_the_mode_the_disk_reported(self):
        record = self.adopt()
        for c in record["adoption"]["created"]:
            self.assertEqual(c["mode"], os.lstat(os.path.join(self.target, c["path"])).st_mode & 0o7777)
        os.chmod(os.path.join(self.target, ".aios/config.json"), 0o600)
        _r, _s, how = install_mod.rollback(self.target, self.source)
        self.assertIn(".aios/config.json changed permissions", how)
        self.assertTrue(os.path.isfile(os.path.join(self.target, ".aios/config.json")))

    def test_c7_a_release_may_never_ship_the_installers_own_paths(self):
        man = json.loads(json.dumps(self.v))
        man["files"].append({"path": ".aios/txn.json", "class": "managed", "mode": "100644", "sha256": "0" * 64})
        self.assertTrue(any("installer's own state" in p for p in __import__("aioslib.release").release.check_shape(man)))
        write(self.source, ".aios/txn.json", "{}\n")
        run_git(self.source, "add", "-f", ".aios/txn.json")  # the source's own ignore rules would skip it
        rev = harness.bump_source(self.source, {}, "ships a journal")
        with self.assertRaises(Refusal) as ctx:
            harness.build_manifest(self.source, rev, "3.0.1")
        self.assertIn("installer's own state", ctx.exception.message)

    def test_c9_not_a_git_repository_and_an_uncommitted_plan(self):
        plain = os.path.join(self.tmp, "plain")
        shutil.copytree(self.target, plain, ignore=shutil.ignore_patterns(".git"))
        with self.assertRaises(Refusal) as ctx:
            install_mod.adopt_existing(plain, self.v, self.source, harness.config())
        self.assertIn("isn't a git repository", ctx.exception.message)
        write(self.target, ".gitignore", "node_modules/\n.env\n.aios/adoption.json\n")
        run_git(self.target, "rm", "-q", "--cached", ".aios/adoption.json")
        self.commit("the plan is only ignored, not committed")
        exc = self.refuses_unchanged(self.adopt)
        self.assertIn("must be committed", exc.message)

    def test_c11_a_catch_all_or_a_plan_that_adopts_nothing(self):
        self.write_plan({"schema": "ff-aios-starter/adoption@1", "adopt": [], "instance_owned": [], "exclude": ["**"]})
        self.commit("catch-all only")
        exc = self.refuses_unchanged(self.adopt)
        self.assertIn("every path at once", "\n".join(exc.details))
        everything = [e["path"] for e in self.v["files"]]
        owned = [p for p in everything if os.path.lexists(os.path.join(self.target, p))]
        self.write_plan({"schema": "ff-aios-starter/adoption@1", "adopt": [], "instance_owned": owned,
                         "exclude": [p for p in everything if p not in owned]})
        self.commit("adopts nothing")
        exc = self.refuses_unchanged(self.adopt)
        self.assertIn("adopts no path", exc.message)


class BoundaryHonoursDeclaredReviewers(Sandbox):
    """Codex round 1, finding 10: G98 at the pull request too."""

    def setUp(self):
        super(BoundaryHonoursDeclaredReviewers, self).setUp()
        self.repo = os.path.join(self.tmp, "client")
        os.makedirs(self.repo)
        run_git(self.repo, "init", "-q", "-b", "main")
        run_git(self.repo, "config", "user.email", "t@example.com")
        run_git(self.repo, "config", "user.name", "t")
        policy = json.loads(json.dumps(FF_ROLES))
        policy["founder_lane_reviewers"] = ["@acme-founder", "@acme-lead"]
        write(self.repo, ".aios/roles.json", json.dumps(policy, indent=2))
        write(self.repo, ".aios/config.json", json.dumps(harness.config(people=[
            {"github": "acme-founder", "role": "founder", "display_name": "F"},
            {"github": "acme-lead", "role": "operator", "display_name": "L"},
            {"github": "acme-va", "role": "operator", "display_name": "V"}]), indent=2))
        write(self.repo, "CLAUDE.md", "# rules\n")
        run_git(self.repo, "add", "-A")
        run_git(self.repo, "commit", "-qm", "base")
        self.base = util.git(self.repo, ["rev-parse", "HEAD"])
        run_git(self.repo, "checkout", "-q", "-b", "pr")
        write(self.repo, "CLAUDE.md", "# rules, changed\n")
        run_git(self.repo, "commit", "-qam", "change")
        self.head = util.git(self.repo, ["rev-parse", "HEAD"])

    def check(self, author, approvers):
        from aioslib import boundary
        return boundary.check_pr(self.repo, self.base, self.head, author, approvers)

    def test_a_declared_reviewer_who_isnt_a_founder_satisfies_it(self):
        code, lines = self.check("acme-va", ["acme-lead"])
        self.assertEqual(code, 0, lines)

    def test_an_undeclared_operator_does_not_and_the_message_names_who_may(self):
        code, lines = self.check("acme-lead", ["acme-va"])
        self.assertNotEqual(code, 0)
        self.assertIn("approved founder-lane reviewer", "\n".join(lines))

    def test_nobody_approves_their_own_change(self):
        code, _lines = self.check("acme-lead", ["acme-lead"])
        self.assertNotEqual(code, 0)


class ReviewRoundTwo(Existing):
    """Codex, 3.1 round 2."""

    def test_r2_2_a_tracked_guard_in_a_linked_worktree_is_never_touched(self):
        write(self.target, ".aios/backups/guard", "")  # empty, but the repository's own
        run_git(self.target, "add", "-f", ".aios/backups/guard")
        self.commit("an empty file of ours at the guard's path")
        linked = os.path.join(self.tmp, "linked")
        run_git(self.target, "worktree", "add", "-q", "--detach", linked, "HEAD")
        self.assertTrue(os.path.isfile(os.path.join(linked, ".git")))  # a file, not a folder
        before = snapshot(linked)
        with self.assertRaises(Refusal) as ctx:
            install_mod.adopt_existing(linked, self.v, self.source, harness.config())
        self.assertIn("own paths", ctx.exception.message)
        self.assertEqual(diff(before, snapshot(linked)), [])

    def test_r2_4_a_kill_between_link_and_cleanup_leaves_no_temporary_copy(self):
        before = snapshot(self.target)
        backups = os.path.join(self.target, ".aios", "backups")
        self.be("acme-founder")
        cfg = self.write_json("org.json", harness.config())
        rel = self.write_json("release.json", self.v)
        code, _o, _e = self.cli("adopt", "--existing", "--release", rel, "--target", self.target,
                                "--config", cfg, "--repo", self.source, env={"AIOS_FAULT": "crash:adopt.after_link"})
        self.assertEqual(code, 137)
        code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(diff(before, snapshot(self.target)), [])
        self.assertEqual([n for n in os.listdir(backups) if n.startswith(".write-")] if os.path.isdir(backups) else [], [])

    def test_r2_5_catch_alls_are_judged_by_what_they_match(self):
        for items in (["***"], ["?*"], ["*", "*/**"], ["*", "**/*"], ["*"]):
            with self.subTest(items=items):
                plan = json.loads(json.dumps(PLAN))
                plan["exclude"] = items
                self.write_plan(plan)
                self.commit("catch-all %r" % items)
                exc = self.refuses_unchanged(self.adopt)
                self.assertIn("every path at once", "\n".join(exc.details))

    def test_r2_1_the_rehearsal_never_deletes_a_root_it_didnt_make(self):
        import subprocess
        keep = os.path.join(self.tmp, "keep")
        write(keep, "precious.txt", "mine\n")
        for name, extra in (("rehearse_310_aios.py", ["--aios", self.target]), ("rehearse_310.py", [])):
            script = os.path.join(harness.REPO_ROOT, "evidence/dispatch/p22-starter/release-3.1.0", name)
            proc = subprocess.run([sys.executable, script, keep] + extra,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertNotEqual(proc.returncode, 0, name)
            with open(os.path.join(keep, "precious.txt")) as fh:
                self.assertEqual(fh.read(), "mine\n", name)


class BoundaryDeclaredListIsTheWholePermission(BoundaryHonoursDeclaredReviewers):
    """Codex, 3.1 round 2: a declared list replaces founder status at the pull request too."""

    def test_a_founder_left_off_the_list_does_not_count(self):
        policy = json.loads(json.dumps(FF_ROLES))
        policy["founder_lane_reviewers"] = ["@acme-lead"]
        write(self.repo, ".aios/roles.json", json.dumps(policy, indent=2))
        run_git(self.repo, "checkout", "-q", "main")
        run_git(self.repo, "commit", "-qam", "only acme-lead reviews")
        self.base = util.git(self.repo, ["rev-parse", "HEAD"])
        run_git(self.repo, "checkout", "-q", "-b", "pr2")
        write(self.repo, "CLAUDE.md", "# rules, changed again\n")
        run_git(self.repo, "commit", "-qam", "change")
        self.head = util.git(self.repo, ["rev-parse", "HEAD"])
        code, _lines = self.check("acme-va", ["acme-founder"])
        self.assertNotEqual(code, 0)
        code, _lines = self.check("acme-va", ["acme-lead"])
        self.assertEqual(code, 0)

    def test_an_unusable_declaration_counts_nobody(self):
        policy = json.loads(json.dumps(FF_ROLES))
        policy["founder_lane_reviewers"] = ["@acme/leads"]  # a team: can't be checked
        write(self.repo, ".aios/roles.json", json.dumps(policy, indent=2))
        run_git(self.repo, "checkout", "-q", "main")
        run_git(self.repo, "commit", "-qam", "a team")
        self.base = util.git(self.repo, ["rev-parse", "HEAD"])
        run_git(self.repo, "checkout", "-q", "-b", "pr3")
        write(self.repo, "CLAUDE.md", "# rules, changed once more\n")
        run_git(self.repo, "commit", "-qam", "change")
        self.head = util.git(self.repo, ["rev-parse", "HEAD"])
        code, _lines = self.check("acme-va", ["acme-founder", "acme-lead"])
        self.assertNotEqual(code, 0)


class ReviewRoundThree(Existing):
    """Codex, 3.1 round 3."""

    def adopted(self):
        self.adopt()
        self.commit("adopted")

    def test_r3_1_reserved_paths_are_compared_as_a_mac_or_windows_disk_would(self):
        for path in (".AIOS/txn.json", ".aios\\install.json", ".Aios/Backups/x", "/.aios/lock"):
            self.assertTrue(util.is_reserved(path), path)
        self.assertFalse(util.is_reserved("scripts/aios/install.py"))
        man = json.loads(json.dumps(self.v))
        man["files"].append({"path": ".AIOS/txn.json", "class": "managed", "mode": "100644", "sha256": "0" * 64})
        from aioslib import release
        self.assertTrue(any("installer's own state" in p for p in release.check_shape(man)))

    def test_r3_2_a_null_reviewer_declaration_counts_nobody(self):
        write(self.target, ".github/CODEOWNERS", "# aios-codeowners-for: acme/acme-aios\n/CLAUDE.md @acme-founder\n")
        policy = json.loads(json.dumps(FF_ROLES))
        policy["founder_lane_reviewers"] = None
        results = governance.founder_review_local(self.target, policy, harness.config())
        self.assertTrue(results and all(st == "FAIL" for st, _d in results), results)
        self.assertEqual(governance.lane_reviewers(policy, harness.config()), (set(), True))

    def test_r3_3_an_upgrade_refuses_a_path_the_plan_calls_the_instances_that_isnt_there(self):
        self.adopted()
        plan = json.loads(json.dumps(PLAN))
        plan["instance_owned"].append("docs/**")
        self.write_plan(plan)
        self.commit("docs are ours")
        rev = harness.bump_source(self.source, {"docs/new_guide.md": "# new\n"}, "3.1")
        v31 = harness.approve(harness.build_manifest(self.source, rev, "3.1.0"))
        exc = self.refuses_unchanged(install_mod.upgrade, self.target, v31, self.source)
        self.assertIn("docs/new_guide.md: the plan says it's the instance's, but it doesn't exist",
                      "\n".join(exc.details))

    def test_r3_4_an_upgrade_refuses_a_plan_that_is_no_longer_committed(self):
        self.adopted()
        with open(os.path.join(self.target, ".gitignore"), "a") as fh:
            fh.write(".aios/adoption.json\n")
        run_git(self.target, "rm", "-q", "--cached", ".aios/adoption.json")
        self.commit("the plan is only ignored now")
        rev = harness.bump_source(self.source, {"START_HERE.md": "# start here\nnew.\n"}, "3.1")
        v31 = harness.approve(harness.build_manifest(self.source, rev, "3.1.0"))
        exc = self.refuses_unchanged(install_mod.upgrade, self.target, v31, self.source)
        self.assertIn("isn't committed", exc.message)

    def test_r3_5_a_seed_can_never_be_adopted(self):
        plan = json.loads(json.dumps(PLAN))
        plan["exclude"].remove("01_Foundations/**")
        plan["adopt"].append("01_Foundations/market_analysis/_workspace.md")
        self.write_plan(plan)
        self.commit("adopting a seed")
        exc = self.refuses_unchanged(self.adopt)
        self.assertIn("seed", exc.message)


class BoundaryNullDeclaration(BoundaryHonoursDeclaredReviewers):

    def test_null_counts_nobody_at_the_pull_request(self):
        policy = json.loads(json.dumps(FF_ROLES))
        policy["founder_lane_reviewers"] = None
        write(self.repo, ".aios/roles.json", json.dumps(policy, indent=2))
        run_git(self.repo, "checkout", "-q", "main")
        run_git(self.repo, "commit", "-qam", "null")
        self.base = util.git(self.repo, ["rev-parse", "HEAD"])
        run_git(self.repo, "checkout", "-q", "-b", "pr4")
        write(self.repo, "CLAUDE.md", "# rules, changed after null\n")
        run_git(self.repo, "commit", "-qam", "change")
        self.head = util.git(self.repo, ["rev-parse", "HEAD"])
        code, _lines = self.check("acme-va", ["acme-founder"])
        self.assertNotEqual(code, 0)


class ReviewRoundFive(Existing):
    """Codex, 3.1 round 5: the guard deletes only a file it made itself."""

    def test_rollback_with_nothing_to_undo_never_deletes_a_file_at_the_guards_path(self):
        write(self.target, ".aios/backups/guard", "a file of ours\n")
        run_git(self.target, "add", "-f", ".aios/backups/guard")
        self.commit("ours, at the guard's path")
        write(self.target, ".aios/lock", "adopt pid=999999 at then\n")  # a dead holder's lock
        code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
        self.assertEqual(code, 0, out + err)
        with open(os.path.join(self.target, ".aios/backups/guard")) as fh:
            self.assertEqual(fh.read(), "a file of ours\n")

    def test_the_guard_never_deletes_a_file_that_was_already_there(self):
        guard = install_mod._RecoveryGuard(self.target).path
        with open(guard, "w") as fh:
            fh.write("")
        with install_mod._RecoveryGuard(self.target):
            pass
        self.assertTrue(os.path.isfile(guard))
        os.remove(guard)
        with install_mod._RecoveryGuard(self.target):
            self.assertTrue(os.path.isfile(guard))
        self.assertFalse(os.path.exists(guard))  # made, so taken back


class ReviewRoundSix(Existing):
    """Codex, 3.1 round 6."""

    @unittest.skipIf(os.name == "nt", "Windows can't remove an open file, so nothing can replace it")
    def test_the_guard_never_deletes_a_file_that_replaced_its_own(self):
        guard = install_mod._RecoveryGuard(self.target).path
        with install_mod._RecoveryGuard(self.target):
            os.remove(guard)  # someone takes the name while this run holds the lock
            with open(guard, "w") as fh:
                fh.write("theirs\n")
        with open(guard) as fh:
            self.assertEqual(fh.read(), "theirs\n")

    def test_the_rehearsal_reads_every_checkable_rule_exact_files_included(self):
        import importlib.util
        path = os.path.join(harness.REPO_ROOT, "evidence/dispatch/p22-starter/release-3.1.0/rehearse_310_aios.py")
        spec = importlib.util.spec_from_file_location("rehearse_310_aios", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        lane, reviewers = mod.lane_from_codeowners(
            "/.github/  @a @b\n/CLAUDE.md  @a @b\n.gitignore @a\n**/*.sql @a\n.env* @a\n/docs/*/x @b\n",
            governance.parse)
        self.assertEqual(lane, [".github/**", "CLAUDE.md", ".gitignore"])
        self.assertEqual(reviewers, ["@a", "@b"])


class ReviewRoundSeven(Existing):
    """Codex and Gemini, 3.1 round 7."""

    def test_in_a_git_repository_the_guard_never_shows_as_a_change(self):
        guard = install_mod._RecoveryGuard(self.target).path
        self.assertNotIn(os.path.realpath(self.target) + os.sep + ".aios", os.path.realpath(guard))
        with open(guard, "w") as fh:  # what Windows leaves behind: it can't delete an open file
            fh.write("")
        self.assertEqual(util.git(self.target, ["status", "--porcelain", "--ignored", "--untracked-files=all"]), "")
        before = snapshot(self.target)
        self.adopt()
        install_mod.rollback(self.target, self.source)
        self.assertEqual(diff(before, snapshot(self.target)), [])

    def test_an_adopted_path_the_repository_ignores_is_refused(self):
        write(self.target, ".gitignore", "node_modules/\n.env\nscripts/\n")
        self.commit("we ignore scripts/")
        exc = self.refuses_unchanged(self.adopt)
        self.assertIn("ignored by this repository's git rules", exc.message)
        self.assertIn("scripts/team/git-safety-check.sh", exc.details)

    def test_the_installers_backups_folder_must_be_empty(self):
        write(self.target, ".aios/backups/notes.txt", "ours\n")
        self.commit("a file of ours in .aios/backups")
        exc = self.refuses_unchanged(self.adopt)
        self.assertIn("own paths", exc.message)
        self.assertTrue(any("already holds files" in d for d in exc.details), exc.details)


class ReviewRoundEight(Existing):
    """Codex, 3.1 round 8."""

    def test_an_ignored_people_map_already_here_is_refused(self):
        write(self.target, ".aios/config.json", json.dumps(harness.config()))
        with open(os.path.join(self.target, ".gitignore"), "a") as fh:
            fh.write(".aios/config.json\n")
        self.commit("our config, ignored")
        exc = self.refuses_unchanged(self.adopt)
        self.assertIn("isn't committed", exc.message)

    def test_a_dead_lock_before_the_journal_is_cleared_when_a_people_map_exists(self):
        write(self.target, ".aios/config.json", json.dumps(harness.config()))
        self.commit("our config, committed")
        write(self.target, ".aios/lock", "adopt pid=999999 at then\n")
        self.be("acme-founder")
        code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
        self.assertEqual(code, 0, out + err)
        self.assertIn("nothing to roll back", out)
        self.assertIn("release:  none (nothing was changed)", out)
        self.assertFalse(os.path.lexists(os.path.join(self.target, ".aios/lock")))


class ReviewRoundNine(Existing):
    """Codex, 3.1 round 9."""

    def test_an_upgrade_refuses_when_what_the_instance_runs_on_is_no_longer_committed(self):
        self.adopt()
        self.commit("adopted")
        with open(os.path.join(self.target, ".gitignore"), "a") as fh:
            fh.write(".aios/config.json\n")
        run_git(self.target, "rm", "-q", "--cached", ".aios/config.json")
        self.commit("the people map is only local now")
        rev = harness.bump_source(self.source, {"START_HERE.md": "# start here\nnew.\n"}, "3.1")
        v31 = harness.approve(harness.build_manifest(self.source, rev, "3.1.0"))
        exc = self.refuses_unchanged(install_mod.upgrade, self.target, v31, self.source)
        self.assertIn(".aios/config.json", exc.details)

    def test_a_policy_nobody_can_upgrade_and_roll_back_with_is_refused(self):
        policy = json.loads(json.dumps(FF_ROLES))
        policy["roles"]["founder"]["lifecycle"] = ["install", "adopt", "upgrade", "governance"]  # no rollback
        write(self.target, ".aios/roles.json", json.dumps(policy, indent=2))
        self.commit("a policy without rollback")
        exc = self.refuses_unchanged(self.adopt)
        self.assertIn("upgrade and roll back", exc.message)


class ReviewRoundTen(Existing):
    """Codex, 3.1 round 10."""

    def killed_after_link(self):
        """An adoption killed after its first file is linked, before the temporary copy goes."""
        self.be("acme-founder")
        cfg = self.write_json("org.json", harness.config())
        rel = self.write_json("release.json", self.v)
        code, _o, _e = self.cli("adopt", "--existing", "--release", rel, "--target", self.target,
                                "--config", cfg, "--repo", self.source, env={"AIOS_FAULT": "crash:adopt.after_link"})
        self.assertEqual(code, 137)
        pending = install_mod.load_journal(self.target)["pending"]
        self.assertTrue(os.path.samestat(os.lstat(os.path.join(self.target, pending["path"])),
                                         os.lstat(os.path.join(self.target, pending["temp"]))))
        return pending

    def rolls_back_keeping(self, pending):
        code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
        self.assertEqual(code, 0, out + err)
        self.assertTrue(os.path.isfile(os.path.join(self.target, pending["path"])), "an edited file was removed")
        self.assertFalse(os.path.lexists(os.path.join(self.target, pending["temp"])))
        self.assertIn("left for you", out)
        return out

    def test_an_edit_after_a_kill_between_link_and_cleanup_is_kept(self):
        pending = self.killed_after_link()
        dest = os.path.join(self.target, pending["path"])
        with open(dest, "a") as fh:  # in place: the inode it shares with the temporary copy
            fh.write("\n")
        with open(dest, "rb") as fh:
            edited = fh.read()
        self.rolls_back_keeping(pending)
        with open(dest, "rb") as fh:
            self.assertEqual(fh.read(), edited)

    def test_a_mode_change_after_a_kill_between_link_and_cleanup_is_kept(self):
        pending = self.killed_after_link()
        os.chmod(os.path.join(self.target, pending["path"]), 0o600)
        self.rolls_back_keeping(pending)

    def no_rollback_policy(self):
        policy = json.loads(json.dumps(FF_ROLES))
        for role in policy["roles"].values():
            role["lifecycle"] = [a for a in role.get("lifecycle") or [] if a != "rollback"]
        write(self.target, ".aios/roles.json", json.dumps(policy, indent=2))

    def test_a_dead_lock_before_the_journal_is_cleared_whatever_the_policy_says(self):
        write(self.target, ".aios/config.json", json.dumps(harness.config()))
        self.no_rollback_policy()
        self.commit("our config, and a policy nobody may roll back with")
        write(self.target, ".aios/lock", "adopt pid=999999 at then\n")
        self.be("acme-founder")
        code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
        self.assertEqual(code, 0, out + err)
        self.assertIn("cleared a dead operation's lock", out)
        self.assertFalse(os.path.lexists(os.path.join(self.target, ".aios/lock")))

    def test_a_live_lock_is_still_never_taken_without_a_role(self):
        write(self.target, ".aios/config.json", json.dumps(harness.config()))
        self.no_rollback_policy()
        self.commit("our config, and a policy nobody may roll back with")
        write(self.target, ".aios/lock", "adopt pid=%d at now\n" % os.getpid())
        self.be("acme-founder")
        code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
        self.assertNotEqual(code, 0, out + err)
        self.assertTrue(os.path.lexists(os.path.join(self.target, ".aios/lock")))

    def test_an_upgrade_refuses_once_the_policy_lets_nobody_roll_back(self):
        self.adopt()
        self.commit("adopted")
        self.no_rollback_policy()
        self.commit("rollback dropped from every role")
        rev = harness.bump_source(self.source, {"START_HERE.md": "# start here\nnew.\n"}, "3.1")
        v31 = harness.approve(harness.build_manifest(self.source, rev, "3.1.0"))
        exc = self.refuses_unchanged(install_mod.upgrade, self.target, v31, self.source)
        self.assertIn("upgrade and roll back", exc.message)


class ReviewRoundEleven(Existing):
    """Codex, 3.1 round 11."""

    def adopted(self):
        self.adopt()
        self.commit("adopted")

    def test_an_install_record_edited_after_a_kill_at_its_link_is_kept(self):
        self.be("acme-founder")
        cfg = self.write_json("org.json", harness.config())
        rel = self.write_json("release.json", self.v)
        code, _o, _e = self.cli("adopt", "--existing", "--release", rel, "--target", self.target,
                                "--config", cfg, "--repo", self.source,
                                env={"AIOS_FAULT": "crash:adopt.record_after_link"})
        self.assertEqual(code, 137)
        pending = install_mod.load_journal(self.target)["pending"]
        self.assertEqual(pending["path"], ".aios/install.json")
        record = os.path.join(self.target, ".aios/install.json")
        with open(record, "a") as fh:  # in place; the plan hash inside is unchanged
            fh.write("\n")
        with open(record, "rb") as fh:
            edited = fh.read()
        code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
        self.assertEqual(code, 0, out + err)
        self.assertIn(".aios/install.json isn't exactly what an interrupted adoption made", out)
        with open(record, "rb") as fh:
            self.assertEqual(fh.read(), edited)
        for path in ADOPTED:  # everything else it made, unchanged, is gone
            self.assertFalse(os.path.lexists(os.path.join(self.target, path)), path)

    def test_verify_repo_takes_the_adopted_files_from_the_committed_plan(self):
        self.adopted()
        self.assertEqual(install_mod.verify(self.target, source_repo=self.source)[0], [])
        path = install_mod.install_record_path(self.target)
        record = util.read_json(path)
        dropped = record["managed"][0]["path"]
        record["managed"] = record["managed"][1:]
        record["adoption"]["exclude"].append(dropped)  # the record's own copy of the plan, edited
        util.write_json(path, record)
        os.remove(os.path.join(self.target, dropped))
        problems = install_mod.verify(self.target, source_repo=self.source)[0]
        self.assertTrue(any(dropped in p and "doesn't list it" in p for p in problems), problems)
        self.assertTrue(any("record's copy of the adoption plan" in p for p in problems), problems)

    def test_verify_repo_reports_a_plan_changed_since_the_last_upgrade_until_one_applies_it(self):
        self.adopted()
        plan = json.loads(json.dumps(PLAN))
        plan["adopt"].remove("START_HERE.md")
        plan["instance_owned"].append("START_HERE.md")
        self.write_plan(plan)
        self.commit("START_HERE.md is ours now")
        problems = install_mod.verify(self.target, source_repo=self.source)[0]
        self.assertTrue(any("isn't the one this instance was adopted" in p for p in problems), problems)
        rev = harness.bump_source(self.source, {"scripts/team/git-safety-check.sh": "#!/bin/sh\necho v31\n"}, "3.1")
        v31 = harness.approve(harness.build_manifest(self.source, rev, "3.1.0"))
        install_mod.upgrade(self.target, v31, self.source)
        self.assertEqual(install_mod.verify(self.target, source_repo=self.source)[0], [])

    def test_a_lock_that_names_no_process_is_cleared_by_rollback(self):
        for words in ("", "adopt pid="):
            with self.subTest(words=words):
                write(self.target, ".aios/lock", words)
                self.be("acme-founder")
                code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
                self.assertEqual(code, 0, out + err)
                self.assertIn("cleared a dead operation's lock", out)
                self.assertFalse(os.path.lexists(os.path.join(self.target, ".aios/lock")))

    def test_windows_aliases_of_the_installers_paths_are_reserved(self):
        for path in (".aios/lock.", ".aios/config.json ", ".aios/txn.json::$DATA", ".aios/install.json:x",
                     ".aios./lock", ".aios /lock", ".aios/backups./x", ".AIOS/Backups /x",
                     "AIOS~1/lock", ".aios/INSTAL~1.JSO", ".aios/CONFIG~1.JSO"):
            self.assertTrue(util.is_reserved(path), path)
        for path in (".aios/roles.json", ".aios/.gitignore", ".aios/operator_core/OPERATOR_CORE.md",
                     "notes~1.md", "docs/v1.0/guide.md", "scripts/aios/install.py"):
            self.assertFalse(util.is_reserved(path), path)
        from aioslib import release
        for alias in (".aios/lock.", ".aios/config.json "):
            man = json.loads(json.dumps(self.v))
            man["files"].append({"path": alias, "class": "managed", "mode": "100644", "sha256": "0" * 64})
            self.assertTrue(any("installer's own state" in p for p in release.check_shape(man)), alias)


class ReviewRoundTwelve(Existing):
    """Gemini, 3.1 round 12: a finished adoption's record, edited since, is kept like any file it made."""

    def adopted(self):
        self.adopt()
        self.commit("adopted")
        self.be("acme-founder")
        return os.path.join(self.target, ".aios/install.json")

    def rolls_back_keeping_the_record(self, record):
        with open(record, "rb") as fh:
            edited = fh.read()
        code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
        self.assertEqual(code, 0, out + err)
        self.assertIn(".aios/install.json changed since the adoption wrote it", out)
        self.assertIn(".aios/install.json was left because it changed", out)
        self.assertNotIn("no longer pinned", out)
        with open(record, "rb") as fh:
            self.assertEqual(fh.read(), edited)
        for path in ADOPTED:
            self.assertFalse(os.path.lexists(os.path.join(self.target, path)), path)

    def test_an_edited_record_with_the_same_plan_hash_is_kept(self):
        # Since round 22 an edited record isn't trusted to say which files the adoption made: rollback
        # refuses and changes nothing until it's restored from git.
        record = self.adopted()
        data = util.read_json(record)
        data["installed_at"] = "edited by hand"
        util.write_json(record, data)  # canonical bytes, same plan hash: only the seal tells
        with open(record, "rb") as fh:
            edited = fh.read()
        code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
        self.assertNotEqual(code, 0, out + err)
        self.assertTrue(any(m in out + err for m in ("can't trust which files the adoption made",
                                                       "isn't the one this workspace's last operation wrote")),
                        out + err)
        with open(record, "rb") as fh:
            self.assertEqual(fh.read(), edited)
        for path in ADOPTED:
            self.assertTrue(os.path.lexists(os.path.join(self.target, path)), path)
        run_git(self.target, "checkout", "--", ".aios/install.json")  # restored, it rolls back
        code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
        self.assertEqual(code, 0, out + err)
        self.assertFalse(os.path.lexists(record))

    def test_a_record_whose_permissions_changed_is_kept(self):
        record = self.adopted()
        os.chmod(record, 0o600)
        self.rolls_back_keeping_the_record(record)

    def test_an_unedited_record_goes_and_the_workspace_is_unpinned(self):
        record = self.adopted()
        code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
        self.assertEqual(code, 0, out + err)
        self.assertIn("no longer pinned", out)
        self.assertFalse(os.path.lexists(record))

    def test_the_seal_survives_an_upgrade_and_its_rollback(self):
        record = self.adopted()
        with open(record, "rb") as fh:
            adopted_bytes = fh.read()
        rev = harness.bump_source(self.source, {"START_HERE.md": "# start here\nnew.\n"}, "3.1")
        v31 = harness.approve(harness.build_manifest(self.source, rev, "3.1.0"))
        install_mod.upgrade(self.target, v31, self.source)
        self.assertNotIn(install_mod.RECORD_SEAL, util.read_json(record))  # a new record
        self.commit("upgraded")
        install_mod.rollback(self.target, self.source)  # back to the adoption's own record, byte for byte
        with open(record, "rb") as fh:
            self.assertEqual(fh.read(), adopted_bytes)
        self.commit("rolled back to the adoption")
        install_mod.rollback(self.target, self.source)  # and the adoption itself
        self.assertFalse(os.path.lexists(record))
        for path in ADOPTED:
            self.assertFalse(os.path.lexists(os.path.join(self.target, path)), path)


class ReviewRoundTwelveCodex(Existing):
    """Codex, 3.1 round 12."""

    def killed_at(self, point):
        self.be("acme-founder")
        cfg = self.write_json("org.json", harness.config())
        rel = self.write_json("release.json", self.v)
        code, _o, _e = self.cli("adopt", "--existing", "--release", rel, "--target", self.target,
                                "--config", cfg, "--repo", self.source, env={"AIOS_FAULT": "crash:" + point})
        self.assertEqual(code, 137)
        return os.path.join(self.target, ".aios/install.json")

    def rollback(self):
        code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
        self.assertEqual(code, 0, out + err)
        for path in ADOPTED:
            self.assertFalse(os.path.lexists(os.path.join(self.target, path)), path)
        return out

    def test_a_record_replaced_after_a_kill_at_its_link_is_kept_even_with_the_same_bytes(self):
        record = self.killed_at("adopt.record_after_link")
        with open(record, "rb") as fh:
            same = fh.read()
        fresh = record + ".new"
        with open(fresh, "wb") as fh:
            fh.write(same)
        os.chmod(fresh, 0o644)
        os.replace(fresh, record)  # identical bytes and mode, but another file
        out = self.rollback()
        self.assertIn(".aios/install.json isn't exactly what an interrupted adoption made", out)
        with open(record, "rb") as fh:
            self.assertEqual(fh.read(), same)

    def test_after_its_temporary_copy_went_a_record_is_judged_by_what_was_written(self):
        record = self.killed_at("adopt.record_after_temp")
        self.assertEqual(install_mod.load_journal(self.target)["pending"]["path"], ".aios/install.json")
        with open(record, "a") as fh:
            fh.write("\n")
        self.rollback()
        self.assertTrue(os.path.isfile(record), "an edited record was removed")

    def test_after_its_temporary_copy_went_an_unchanged_record_goes(self):
        record = self.killed_at("adopt.record_after_temp")
        out = self.rollback()
        self.assertFalse(os.path.lexists(record), out)
        self.assertEqual(os.listdir(os.path.join(self.target, ".aios", "backups"))
                         if os.path.isdir(os.path.join(self.target, ".aios", "backups")) else [], [])

    def test_a_file_that_appeared_identical_when_the_link_failed_is_kept(self):
        with open(os.path.join(self.source, "START_HERE.md"), "rb") as fh:
            release_bytes = fh.read()
        real = util.create_new

        def appears_first(target, rel, data, mode, before_link=None):
            if rel == "START_HERE.md":
                with open(os.path.join(target, rel), "wb") as fh:  # someone else's, the same bytes
                    fh.write(release_bytes)
                os.chmod(os.path.join(target, rel), 0o644)
            return real(target, rel, data, mode, before_link)

        util.create_new = appears_first
        try:
            with self.assertRaises(Refusal) as ctx:
                self.adopt()
        finally:
            util.create_new = real
        self.assertIn("appeared while this ran", ctx.exception.message)
        with open(os.path.join(self.target, "START_HERE.md"), "rb") as fh:
            self.assertEqual(fh.read(), release_bytes)
        self.assertFalse(os.path.lexists(install_mod.journal_path(self.target)))

    def test_verify_repo_refuses_a_managed_file_the_plan_doesnt_adopt(self):
        self.adopt()
        self.commit("adopted")
        entries = {e["path"]: e for e in self.v["files"]}
        classes, _ = install_mod.classify_adoption(PLAN, entries)
        extra = sorted(p for p, e in entries.items() if e["class"] == "managed" and classes.get(p) == "exclude")[0]
        with open(os.path.join(self.source, extra), "rb") as fh:
            write(self.target, extra, fh.read().decode("utf-8"))
        path = install_mod.install_record_path(self.target)
        record = util.read_json(path)
        record["managed"].append({"path": extra, "sha256": entries[extra]["sha256"],
                                  "exec": entries[extra].get("mode") == "100755"})
        util.write_json(path, record)
        problems = install_mod.verify(self.target, source_repo=self.source)[0]
        self.assertTrue(any(extra in p and "doesn't adopt it" in p for p in problems), problems)

    def test_paths_under_a_state_file_are_reserved(self):
        from aioslib import release
        for path in (".aios/config.json/child", ".aios/install.json/x/y", ".aios/txn.json/a", ".aios/lock/b",
                     ".aios/config.json./child", ".AIOS/Install.json /x"):
            self.assertTrue(util.is_reserved(path), path)
            man = json.loads(json.dumps(self.v))
            man["files"].append({"path": path, "class": "managed", "mode": "100644", "sha256": "0" * 64})
            self.assertTrue(any("installer's own state" in p for p in release.check_shape(man)), path)
        self.assertFalse(util.is_reserved(".aios/config.jsonx/child"))


class ReviewRoundThirteen(Existing):
    """Gemini, 3.1 round 13: a temporary copy create_new couldn't remove is still cleaned up."""

    def test_a_failed_link_whose_temporary_copy_remains_is_cleaned_up_and_keeps_the_other_file(self):
        real = util.create_new

        def link_fails_and_copy_stays(target, rel, data, mode, before_link=None):
            if rel != "START_HERE.md":
                return real(target, rel, data, mode, before_link)
            tmp = util.private_temp(target)
            with open(tmp, "wb") as fh:
                fh.write(data)
            os.chmod(tmp, 0o644)
            before_link(tmp)
            write(target, rel, "# someone else's, appeared meanwhile\n")
            raise Refusal(util.EXIT_STATE, "%s appeared while this ran; it was not overwritten" % rel)

        util.create_new = link_fails_and_copy_stays
        try:
            with self.assertRaises(Refusal):
                self.adopt()
        finally:
            util.create_new = real
        backups = os.path.join(self.target, ".aios", "backups")
        self.assertEqual([n for n in os.listdir(backups) if n.startswith(".write-")]
                         if os.path.isdir(backups) else [], [], "a temporary copy was left behind")
        with open(os.path.join(self.target, "START_HERE.md")) as fh:
            self.assertEqual(fh.read(), "# someone else's, appeared meanwhile\n")
        self.assertFalse(os.path.lexists(install_mod.journal_path(self.target)))


class ReviewRoundThirteenCodex(Existing):
    """Codex, 3.1 round 13."""

    def test_a_kill_after_a_failed_link_never_takes_the_file_that_appeared(self):
        import subprocess
        with open(os.path.join(self.source, "START_HERE.md"), "rb") as fh:
            release_bytes = fh.read()
        rel = self.write_json("release.json", self.v)
        cfg = self.write_json("org.json", harness.config())
        script = (
            "import json, os, sys\n"
            "sys.path.insert(0, %r)\n"
            "from aioslib import install, util\n"
            "real = util.create_new\n"
            "def appears_first(target, rel, data, mode, before_link=None):\n"
            "    if rel == 'START_HERE.md':\n"
            "        with open(os.path.join(target, rel), 'wb') as fh:\n"
            "            fh.write(%r)\n"
            "        os.chmod(os.path.join(target, rel), 0o644)\n"
            "    return real(target, rel, data, mode, before_link)\n"
            "util.create_new = appears_first\n"
            "install.adopt_existing(%r, json.load(open(%r)), %r, json.load(open(%r)))\n"
        ) % (harness.AIOS_DIR, release_bytes, self.target, rel, self.source, cfg)
        env = dict(os.environ, AIOS_FAULT="crash:create.link_refused")
        proc = subprocess.run([sys.executable, "-c", script], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(proc.returncode, 137, proc.stderr)
        self.be("acme-founder")
        code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
        self.assertEqual(code, 0, out + err)
        with open(os.path.join(self.target, "START_HERE.md"), "rb") as fh:
            self.assertEqual(fh.read(), release_bytes)  # someone else's, identical, kept
        backups = os.path.join(self.target, ".aios", "backups")
        self.assertEqual([n for n in os.listdir(backups) if n.startswith(".write-")]
                         if os.path.isdir(backups) else [], [])
        for path in ADOPTED:
            if path != "START_HERE.md":
                self.assertFalse(os.path.lexists(os.path.join(self.target, path)), path)

    def test_on_windows_an_unchanged_record_is_judged_by_its_read_only_flag(self):
        self.adopt()
        self.commit("adopted")
        record = install_mod.install_record_path(self.target)
        saved = install_mod._EXEC_BITS
        install_mod._EXEC_BITS = False  # as on Windows: no POSIX bits, only read-only
        try:
            os.chmod(record, 0o666)  # what Windows reports for an ordinary writable file
            self.assertTrue(install_mod._record_unchanged(record))
            os.chmod(record, 0o444)  # read-only: changed
            self.assertFalse(install_mod._record_unchanged(record))
            os.chmod(record, 0o666)
            install_mod.rollback(self.target, self.source)
        finally:
            install_mod._EXEC_BITS = saved
        self.assertFalse(os.path.lexists(record))

    def test_a_linked_aios_folder_refuses_before_the_lock(self):
        outside = os.path.join(self.tmp, "outside")
        shutil.move(os.path.join(self.target, ".aios"), outside)
        os.symlink(outside, os.path.join(self.target, ".aios"))
        self.commit("our .aios is a link")
        before = sorted(os.listdir(outside))
        exc = self.refuses_unchanged(self.adopt)
        self.assertIn("own paths", exc.message)
        self.assertTrue(any(".aios is a link" in d for d in exc.details), exc.details)
        self.assertEqual(sorted(os.listdir(outside)), before)


def _tree(root):
    """Every folder and file under `root` (git's own folder aside), with each file's bytes."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not (dirpath == root and d == ".git")]
        rel = os.path.relpath(dirpath, root)
        out[rel + "/"] = "<folder>"  # a value, so a folder only one side has is a difference
        for f in filenames:
            with open(os.path.join(dirpath, f), "rb") as fh:
                out[os.path.join(rel, f)] = fh.read()
    return out


class ReviewRoundFourteen(Existing):
    """Codex, 3.1 round 14."""

    def test_a_failed_journal_write_leaves_no_temporary_copy_and_adoption_can_run_again(self):
        real = util.write_json
        journal = install_mod.journal_path(self.target)
        failed = []

        def disk_full_once(path, obj):
            if path == journal and isinstance(obj, dict) and obj.get("pending") and not failed:
                failed.append(path)
                raise OSError(28, "No space left on device")
            return real(path, obj)

        util.write_json = disk_full_once
        try:
            with self.assertRaises(OSError):
                self.adopt()
        finally:
            util.write_json = real
        self.assertTrue(failed)
        backups = os.path.join(self.target, ".aios", "backups")
        self.assertEqual([n for n in os.listdir(backups) if n.startswith(".write-")]
                         if os.path.isdir(backups) else [], [], "a temporary copy no journal names was left")
        self.be("acme-founder")
        code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
        self.assertEqual(code, 0, out + err)
        self.adopt()  # and it runs again
        self.assertEqual(install_mod.verify(self.target, source_repo=self.source)[0], [])

    def test_outside_git_a_refusal_changes_no_folder(self):
        shutil.rmtree(os.path.join(self.target, ".git"))
        before = _tree(self.target)
        with self.assertRaises(Refusal) as ctx:
            self.adopt()
        self.assertIn("isn't a git repository", ctx.exception.message)
        self.assertEqual(_tree(self.target), before)

    def test_without_an_aios_folder_a_refusal_changes_no_folder(self):
        shutil.rmtree(os.path.join(self.target, ".aios"))
        self.commit("no .aios at all")
        before = _tree(self.target)
        with self.assertRaises(Refusal) as ctx:
            self.adopt()
        self.assertIn("no role policy of its own", ctx.exception.message)
        self.assertEqual(_tree(self.target), before)


class ReviewRoundFifteen(Existing):
    """Codex, 3.1 round 15."""

    def test_rollback_in_an_ordinary_folder_creates_nothing(self):
        plain = os.path.join(self.tmp, "plain")
        write(plain, "notes.md", "# just a folder\n")
        before = _tree(plain)
        code, out, err = self.cli("rollback", "--target", plain)
        self.assertEqual(code, 0, out + err)
        self.assertIn("nothing to roll back", out)
        self.assertEqual(_tree(plain), before)

    def with_config_committed(self):
        write(self.target, ".aios/config.json", json.dumps(harness.config()))
        self.commit("our people map, committed")  # so the first create is an adopted file
        return _tree(self.target)

    def test_a_refused_link_leaves_no_folder_it_made(self):
        before = self.with_config_committed()
        real = os.link

        def no_links_into_new_folders(src, dst, *a, **kw):
            if ".claude/skills" in dst.replace(os.sep, "/"):
                raise PermissionError(1, "Operation not permitted")
            return real(src, dst, *a, **kw)

        os.link = no_links_into_new_folders
        try:
            with self.assertRaises(Refusal) as ctx:
                self.adopt()
        finally:
            os.link = real
        self.assertIn("without risking a replace", ctx.exception.message)
        self.assertEqual(diff(before, _tree(self.target)), [])

    def test_a_create_that_fails_before_its_journal_entry_has_its_folders_pruned_by_rollback(self):
        before = self.with_config_committed()
        real = util.create_new

        def fails_after_making_folders(target, rel, data, mode, before_link=None):
            if rel.startswith(".claude/skills/"):
                util.ensure_parent(os.path.join(target, rel))
                raise OSError(5, "Input/output error")
            return real(target, rel, data, mode, before_link)

        util.create_new = fails_after_making_folders
        try:
            with self.assertRaises(OSError):
                self.adopt()
        finally:
            util.create_new = real
        self.be("acme-founder")
        code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(diff(before, _tree(self.target)), [])

    def test_a_finished_adoption_rolled_back_leaves_every_folder_as_it_was(self):
        before = self.with_config_committed()
        self.adopt()
        self.commit("adopted")
        self.be("acme-founder")
        code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
        self.assertEqual(code, 0, out + err)
        after = _tree(self.target)
        self.assertEqual(diff(before, after), [])

    def test_an_empty_backups_folder_that_was_there_stays(self):
        os.makedirs(os.path.join(self.target, ".aios", "backups"))
        before = self.with_config_committed()
        self.assertIn(".aios/backups/", before)
        self.adopt()
        self.commit("adopted")
        self.be("acme-founder")
        code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(diff(before, _tree(self.target)), [])


class ReviewRoundSixteen(Existing):
    """Codex, 3.1 round 16."""

    def cli_adopt(self, config=None):
        cfg = self.write_json("org.json", config or harness.config())
        rel = self.write_json("release.json", self.v)
        return self.cli("adopt", "--existing", "--release", rel, "--target", self.target,
                        "--config", cfg, "--repo", self.source)

    def test_the_instances_own_policy_decides_who_may_adopt_into_it(self):
        policy = json.loads(json.dumps(FF_ROLES))
        policy["roles"]["founder"]["lifecycle"] = ["install", "upgrade", "rollback", "governance"]  # no adopt
        write(self.target, ".aios/roles.json", json.dumps(policy, indent=2))
        self.commit("in our instance, nobody adopts")
        before = _tree(self.target)
        self.be("acme-founder")  # the release's own policy lets a founder adopt
        code, out, err = self.cli_adopt()
        self.assertEqual(code, util.EXIT_ROLE, out + err)
        self.assertEqual(diff(before, _tree(self.target)), [])

    def test_a_role_only_the_instances_policy_lets_adopt_may(self):
        policy = json.loads(json.dumps(FF_ROLES))
        policy["roles"]["operator"]["lifecycle"] = ["adopt"]  # the release's policy doesn't allow it
        write(self.target, ".aios/roles.json", json.dumps(policy, indent=2))
        self.commit("in our instance, an operator may adopt")
        self.be("acme-va")
        code, out, err = self.cli_adopt()
        self.assertEqual(code, 0, out + err)
        self.assertIn("by:       acme-va (operator)", out)

    def test_verify_repo_refuses_a_plan_that_isnt_committed(self):
        self.adopt()
        self.commit("adopted")
        path = install_mod.install_record_path(self.target)
        record = util.read_json(path)
        dropped = record["managed"][0]["path"]
        alt = json.loads(json.dumps(PLAN))
        alt["exclude"].append(dropped)
        alt["adopt"] = [p for p in alt["adopt"] if not util.match_any([p], dropped)] + \
            [e["path"] for e in record["managed"][1:]]
        write(self.target, ".aios/local_plan.json", json.dumps(alt, indent=2))  # never committed
        record["managed"] = record["managed"][1:]
        record["adoption"]["plan"] = ".aios/local_plan.json"
        record["adoption"]["plan_sha256"] = install_mod.load_adoption_plan(self.target, ".aios/local_plan.json")[1]
        for cls in ("adopt", "instance_owned", "exclude"):
            record["adoption"][cls] = alt[cls]
        util.write_json(path, record)
        os.remove(os.path.join(self.target, dropped))
        problems = install_mod.verify(self.target, source_repo=self.source)[0]
        self.assertTrue(any("isn't committed" in p for p in problems), problems)

    def test_verify_repo_refuses_a_plan_edited_since_its_commit(self):
        self.adopt()
        self.commit("adopted")
        plan_path = os.path.join(self.target, ".aios/adoption.json")
        with open(plan_path, "a") as fh:
            fh.write("\n")
        path = install_mod.install_record_path(self.target)
        record = util.read_json(path)
        record["adoption"]["plan_sha256"] = install_mod.load_adoption_plan(self.target)[1]  # hides the edit
        util.write_json(path, record)
        problems = install_mod.verify(self.target, source_repo=self.source)[0]
        self.assertTrue(any("aren't committed" in p for p in problems), problems)

    def test_a_folder_the_adoption_made_but_since_replaced_stays(self):
        self.adopt()
        self.commit("adopted")
        skills = os.path.join(self.target, ".claude", "skills")
        old = os.path.join(self.target, ".claude", "skills_old")
        os.rename(skills, old)  # the old folders keep their inodes while the new ones are made
        os.makedirs(os.path.join(skills, "start-my-day"))
        shutil.rmtree(old)
        install_mod.rollback(self.target, self.source)
        self.assertTrue(os.path.isdir(os.path.join(skills, "start-my-day")), "a folder it didn't make was removed")


class ReviewRoundSeventeen(Existing):
    """Codex, 3.1 round 17."""

    def test_a_kill_inside_any_early_state_write_rolls_back_to_the_exact_tree(self):
        before = _tree(self.target)
        self.be("acme-founder")
        cfg = self.write_json("org.json", harness.config())
        rel = self.write_json("release.json", self.v)
        for n in range(1, 7):
            with self.subTest(write=n):
                code, _o, _e = self.cli("adopt", "--existing", "--release", rel, "--target", self.target,
                                        "--config", cfg, "--repo", self.source,
                                        env={"AIOS_FAULT": "crash:write_json.before_replace@%d" % n})
                self.assertEqual(code, 137)
                code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
                self.assertEqual(code, 0, out + err)
                self.assertEqual(diff(before, _tree(self.target)), [])
                self.assertEqual(util.git(self.target, ["status", "--porcelain", "--untracked-files=all"]), "")
        self.adopt()  # and it runs again
        self.assertEqual(install_mod.verify(self.target, source_repo=self.source)[0], [])

    def declared_reviewers(self):
        policy = json.loads(json.dumps(FF_ROLES))
        policy["founder_lane_reviewers"] = ["@acme-lead"]  # not a founder
        write(self.target, ".aios/roles.json", json.dumps(policy, indent=2))
        self.commit("only acme-lead reviews the founder lane")

    def test_the_edit_hold_names_the_declared_reviewers(self):
        self.declared_reviewers()
        self.adopt()
        from aioslib import boundary
        ok, reason = boundary.check_edit(self.target, "Edit", {"file_path": os.path.join(self.target, "CLAUDE.md")},
                                         identify=lambda root: "acme-va")
        self.assertFalse(ok)
        self.assertIn("for an approved founder-lane reviewer", reason)
        self.assertNotIn("or to review a pull request", reason)

    def test_start_names_the_declared_reviewers(self):
        self.declared_reviewers()
        self.adopt()
        self.commit("adopted")
        self.be("acme-va")
        code, out, err = self.cli("start", "--target", self.target)
        self.assertEqual(code, 0, out + err)
        self.assertIn("until an approved founder-lane reviewer", out)


class ReviewRoundEighteen(Existing):
    """Codex, 3.1 round 18: a name is not proof."""

    NAME = ".aios/.txn.json.aaaaaaaa.tmp"

    def test_adoption_refuses_over_a_file_with_an_installer_temporary_name(self):
        write(self.target, self.NAME, "ours\n")
        self.commit("a file of ours with that name")
        exc = self.refuses_unchanged(self.adopt)
        self.assertTrue(any("temporary files" in d for d in exc.details), exc.details)

    def test_rollback_never_sweeps_a_tracked_file(self):
        self.adopt()
        self.commit("adopted")
        write(self.target, self.NAME, "ours\n")
        self.commit("a file of ours with that name, after the adoption")
        install_mod.rollback(self.target, self.source)
        with open(os.path.join(self.target, self.NAME)) as fh:
            self.assertEqual(fh.read(), "ours\n")

    def test_releases_may_not_ship_those_names(self):
        from aioslib import release
        for path in (self.NAME, ".aios/.install.json.abc12345.tmp", ".AIOS/.config.json.zz_00000.tmp"):
            self.assertTrue(util.is_reserved(path), path)
            man = json.loads(json.dumps(self.v))
            man["files"].append({"path": path, "class": "managed", "mode": "100644", "sha256": "0" * 64})
            self.assertTrue(any("installer's own state" in p for p in release.check_shape(man)), path)
        self.assertFalse(util.is_reserved(".aios/txn.json.notes.md"))


def _folds_case(folder):
    probe = os.path.join(folder, "CaseProbe")
    write(folder, "CaseProbe", "x")
    try:
        return os.path.exists(probe.lower())
    finally:
        os.remove(probe)


class ReviewRoundNineteen(Existing):
    """Codex, 3.1 round 19: whether git tracks a path, asked literally and as the disk sees it."""

    def test_a_plan_named_like_a_pattern_isnt_mistaken_for_the_committed_one(self):
        with open(os.path.join(self.target, ".gitignore"), "a") as fh:
            fh.write(".aios/adopt*.json\n")
        self.commit("we ignore our scratch plans")
        write(self.target, ".aios/adopt*.json", json.dumps(PLAN, indent=2))  # ignored, never committed
        self.assertFalse(util.is_tracked(self.target, ".aios/adopt*.json"))
        self.assertFalse(util.is_tracked(self.target, ".aios/adopt[i]on.json"))
        exc = self.refuses_unchanged(self.adopt, plan_rel=".aios/adopt*.json")
        self.assertIn("must be committed", exc.message)

    def test_rollback_never_sweeps_a_file_tracked_under_another_case(self):
        if not _folds_case(self.tmp):
            self.skipTest("this disk keeps case, so the two spellings are two files")
        self.adopt()
        self.commit("adopted")
        name = ".txn.json.aaaaaaaa.tmp"
        write(self.target, ".aios/" + name, "ours\n")
        blob = util.git(self.target, ["hash-object", "-w", ".aios/" + name])
        run_git(self.target, "update-index", "--add", "--cacheinfo", "100644,%s,.AIOS/%s" % (blob, name))
        run_git(self.target, "commit", "-qm", "tracked as .AIOS")
        self.assertTrue(util.is_tracked(self.target, ".aios/" + name))
        install_mod.rollback(self.target, self.source)
        with open(os.path.join(self.target, ".aios", name)) as fh:
            self.assertEqual(fh.read(), "ours\n")


class ReviewRoundTwenty(Existing):
    """Codex, 3.1 round 20."""

    def test_rollback_never_follows_a_link_out_of_the_repository(self):
        self.adopt()
        self.commit("adopted")
        outside = os.path.join(self.tmp, "outside")
        with open(os.path.join(self.target, ".claude/skills/start-my-day/SKILL.md"), "rb") as fh:
            release_bytes = fh.read()
        write(outside, "start-my-day/SKILL.md", release_bytes.decode("utf-8"))  # identical bytes, outside
        os.chmod(os.path.join(outside, "start-my-day/SKILL.md"), 0o644)
        shutil.rmtree(os.path.join(self.target, ".claude", "skills"))
        os.symlink(outside, os.path.join(self.target, ".claude", "skills"))
        self.be("acme-founder")
        code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
        self.assertEqual(code, 0, out + err)
        self.assertIn("reached through a link now", out)
        with open(os.path.join(outside, "start-my-day/SKILL.md"), "rb") as fh:
            self.assertEqual(fh.read(), release_bytes)

    def test_rollback_never_acts_on_a_journal_path_outside_the_workspace(self):
        outside = os.path.join(self.tmp, "outside.txt")
        write(self.tmp, "outside.txt", "not the workspace's\n")
        self.be("acme-founder")
        cfg = self.write_json("org.json", harness.config())
        rel = self.write_json("release.json", self.v)
        code, _o, _e = self.cli("adopt", "--existing", "--release", rel, "--target", self.target,
                                "--config", cfg, "--repo", self.source, env={"AIOS_FAULT": "crash:adopt.mid_write"})
        self.assertEqual(code, 137)
        journal = install_mod.load_journal(self.target)
        journal["adoption"]["created"].append({"path": "../outside.txt", "mode": 0o644,
                                               "sha256": util.sha256_file(outside)})
        util.write_json(install_mod.journal_path(self.target), journal)
        code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
        self.assertEqual(code, 0, out + err)
        self.assertTrue(os.path.isfile(outside), "a file outside the workspace was removed")

    def test_a_tracked_lock_is_the_repositorys_file(self):
        write(self.target, ".aios/lock", "adopt pid=999999 at then\n")
        run_git(self.target, "add", "-f", ".aios/lock")
        self.commit("a file of ours at that path")
        exc = self.refuses_unchanged(self.adopt)
        self.assertTrue(any("this repository tracks" in d for d in exc.details), exc.details)
        self.be("acme-founder")
        code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
        self.assertNotEqual(code, 0, out + err)
        self.assertIn("not the installer's lock", out + err)
        self.assertTrue(os.path.isfile(os.path.join(self.target, ".aios/lock")))


class ReviewRoundTwentyOne(Existing):
    """Codex, 3.1 round 21: in a git workspace too, .aios and its backups folder must be real folders."""

    def adopted(self):
        self.adopt()
        self.commit("adopted")
        outside = os.path.join(self.tmp, "outside")
        os.makedirs(outside)
        return outside

    def test_an_upgrade_never_backs_up_through_a_linked_backups_folder(self):
        outside = self.adopted()
        with open(os.path.join(self.target, ".gitignore"), "a") as fh:
            fh.write("/.aios/backups\n")  # so the link itself is ignored and the worktree stays clean
        self.commit("ignore the backups path, link or not")
        backups = os.path.join(self.target, ".aios", "backups")
        if os.path.isdir(backups):
            shutil.rmtree(backups)
        os.symlink(outside, backups)
        self.assertEqual(util.git(self.target, ["status", "--porcelain"]), "")
        rev = harness.bump_source(self.source, {"START_HERE.md": "# start here\nnew.\n"}, "3.1")
        v31 = harness.approve(harness.build_manifest(self.source, rev, "3.1.0"))
        with self.assertRaises(Refusal) as ctx:
            install_mod.upgrade(self.target, v31, self.source)
        self.assertIn("is a link or a file, not a folder", ctx.exception.message)
        self.assertEqual(os.listdir(outside), [])

    def test_rollback_never_writes_through_a_linked_aios_folder(self):
        outside = self.adopted()
        os.rmdir(outside)
        shutil.move(os.path.join(self.target, ".aios"), outside)
        os.symlink(outside, os.path.join(self.target, ".aios"))
        before = _tree(outside)
        with self.assertRaises(Refusal) as ctx:
            install_mod.rollback(self.target, self.source)
        self.assertIn("is a link or a file, not a folder", ctx.exception.message)
        self.assertEqual(diff(before, _tree(outside)), [])


class ReviewRoundTwentyTwo(Existing):
    """Codex and Gemini, 3.1 round 22."""

    def test_a_finished_adoptions_record_naming_another_file_is_refused(self):
        self.adopt()
        self.commit("adopted")
        path = install_mod.install_record_path(self.target)
        record = util.read_json(path)
        record["adoption"]["created"].append({"path": "README.md", "sha256": None})  # the instance's own
        util.write_json(path, record)
        self.be("acme-founder")
        code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
        self.assertNotEqual(code, 0, out + err)
        with open(os.path.join(self.target, "README.md")) as fh:
            self.assertEqual(fh.read(), "# our company repo\n")
        for p in ADOPTED:
            self.assertTrue(os.path.lexists(os.path.join(self.target, p)), p)

    def test_an_interrupted_adoptions_entry_without_provenance_is_left(self):
        self.be("acme-founder")
        cfg = self.write_json("org.json", harness.config())
        rel = self.write_json("release.json", self.v)
        code, _o, _e = self.cli("adopt", "--existing", "--release", rel, "--target", self.target,
                                "--config", cfg, "--repo", self.source, env={"AIOS_FAULT": "crash:adopt.mid_write"})
        self.assertEqual(code, 137)
        journal = install_mod.load_journal(self.target)
        journal["adoption"]["created"].append({"path": "README.md", "sha256": None})
        util.write_json(install_mod.journal_path(self.target), journal)
        code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
        self.assertEqual(code, 0, out + err)
        self.assertIn("without a usable hash and mode", out)
        with open(os.path.join(self.target, "README.md")) as fh:
            self.assertEqual(fh.read(), "# our company repo\n")

    def test_a_file_where_aios_should_be_is_a_refusal_not_a_crash(self):
        for make in ("file", "link to a file"):
            with self.subTest(make=make):
                aios = os.path.join(self.tmp, "ws-" + make.replace(" ", "-"))
                os.makedirs(aios)
                if make == "file":
                    write(aios, ".aios", "not a folder\n")
                else:
                    write(self.tmp, "a-file", "x\n")
                    os.symlink(os.path.join(self.tmp, "a-file"), os.path.join(aios, ".aios"))
                with self.assertRaises(Refusal) as ctx:
                    with install_mod._Lock(aios, "upgrade"):
                        pass
                self.assertIn("is a link or a file, not a folder", ctx.exception.message)

    def test_the_backup_step_refuses_a_linked_backups_folder(self):
        self.adopt()
        self.commit("adopted")
        outside = os.path.join(self.tmp, "outside")
        os.makedirs(outside)
        backups = os.path.join(self.target, ".aios", "backups")
        if os.path.isdir(backups):
            shutil.rmtree(backups)
        os.symlink(outside, backups)
        with self.assertRaises(Refusal):
            install_mod._backup(self.target, install_mod.load_record(self.target), "txn-test")
        self.assertEqual(os.listdir(outside), [])


class ReviewRoundTwentyThree(Existing):
    """Gemini, 3.1 round 23."""

    def readme_entry(self):
        full = os.path.join(self.target, "README.md")
        return {"path": "README.md", "sha256": util.sha256_file(full),
                "mode": stat_mode(full)}

    def test_a_forged_and_resealed_record_cant_make_an_instance_file_removable(self):
        self.adopt()
        self.commit("adopted")
        path = install_mod.install_record_path(self.target)
        record = util.read_json(path)
        record["adoption"]["created"].append(self.readme_entry())
        record = install_mod._sealed(record)  # a seal anyone can recompute
        with open(path, "wb") as fh:
            fh.write(install_mod._record_bytes(record))
        os.chmod(path, 0o644)
        self.be("acme-founder")
        code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
        self.assertNotEqual(code, 0, out + err)  # since round 26: it differs from the committed record
        self.assertTrue(any(m in out + err for m in ("differs from the one committed with the adoption",
                                                       "isn't the one this workspace's last operation wrote")),
                        out + err)
        with open(os.path.join(self.target, "README.md")) as fh:
            self.assertEqual(fh.read(), "# our company repo\n")

    def test_a_forged_journal_entry_cant_either(self):
        self.be("acme-founder")
        cfg = self.write_json("org.json", harness.config())
        rel = self.write_json("release.json", self.v)
        code, _o, _e = self.cli("adopt", "--existing", "--release", rel, "--target", self.target,
                                "--config", cfg, "--repo", self.source, env={"AIOS_FAULT": "crash:adopt.mid_write"})
        self.assertEqual(code, 137)
        journal = install_mod.load_journal(self.target)
        journal["adoption"]["created"].append(self.readme_entry())
        util.write_json(install_mod.journal_path(self.target), journal)
        code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
        self.assertEqual(code, 0, out + err)
        with open(os.path.join(self.target, "README.md")) as fh:
            self.assertEqual(fh.read(), "# our company repo\n")

    def test_the_backup_snapshot_folder_is_always_new(self):
        self.adopt()
        self.commit("adopted")
        txn = "20261015T000000Z-3.0.0-to-3.1.0"
        root = os.path.join(self.target, ".aios", "backups", txn)
        os.makedirs(root)
        os.symlink(self.target, os.path.join(root, "files"))  # would send the copies into the workspace
        before = _tree(self.target)
        with self.assertRaises(Refusal) as ctx:
            install_mod._backup(self.target, install_mod.load_record(self.target), txn)
        self.assertIn("already exists", ctx.exception.message)
        self.assertEqual(diff(before, _tree(self.target)), [])


def stat_mode(full):
    import stat as _stat
    return _stat.S_IMODE(os.lstat(full).st_mode)


class ReviewRoundTwentyThreeCodex(Existing):
    """Codex, 3.1 round 23: the journal's pending temporary copy is only ever an installer temporary."""

    def test_a_tampered_pending_temp_never_removes_a_repository_file(self):
        self.be("acme-founder")
        cfg = self.write_json("org.json", harness.config())
        rel = self.write_json("release.json", self.v)
        code, _o, _e = self.cli("adopt", "--existing", "--release", rel, "--target", self.target,
                                "--config", cfg, "--repo", self.source, env={"AIOS_FAULT": "crash:adopt.mid_write"})
        self.assertEqual(code, 137)
        journal = install_mod.load_journal(self.target)
        for temp in ("README.md", ".aios/backups/README.md", ".aios/backups/.write-abc"):
            with self.subTest(temp=temp):
                if temp.startswith(".aios/backups/"):
                    write(self.target, temp, "ours\n")
                journal["pending"] = {"path": "docs/absent.md", "temp": temp,
                                      "sha256": "0" * 64, "mode": 0o644}
                util.write_json(install_mod.journal_path(self.target), journal)
                notes = install_mod._undo_adoption(self.target, journal["adoption"], journal["pending"])
                self.assertIn("an interrupted adoption's journal entry wasn't usable, so it was left alone", notes)
                self.assertTrue(os.path.isfile(os.path.join(self.target, temp)), temp)


class ReviewRoundTwentyFour(Existing):
    """Codex, 3.1 round 24: a finished adoption's undo trusts only the release, and git, not the record."""

    def forge(self, mutate):
        path = install_mod.install_record_path(self.target)
        record = util.read_json(path)
        mutate(record)
        record = install_mod._sealed(record)  # a seal anyone can recompute
        with open(path, "wb") as fh:
            fh.write(install_mod._record_bytes(record))
        os.chmod(path, 0o644)
        self.commit("a forged record, as a pull request could bring")
        self.forget_state()  # so the git anchor itself is what's tested

    def entry(self, rel):
        full = os.path.join(self.target, rel)
        return {"path": rel, "sha256": util.sha256_file(full), "mode": stat_mode(full)}

    def rollback_ok(self):
        self.be("acme-founder")
        code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
        self.assertEqual(code, 0, out + err)
        for p in ADOPTED:
            self.assertFalse(os.path.lexists(os.path.join(self.target, p)), p)
        return out

    def rollback_refused(self):
        """Since round 26 a record changed after the adoption commit is refused outright, nothing changed."""
        before = _tree(self.target)
        self.be("acme-founder")
        code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
        self.assertNotEqual(code, 0, out + err)
        self.assertIn("differs from the one committed with the adoption", out + err)
        self.assertEqual(diff(before, _tree(self.target)), [])

    def test_an_instance_file_under_an_adopted_pattern_stays(self):
        write(self.target, "scripts/team/local.sh", "#!/bin/sh\necho ours\n")
        self.commit("our own script beside the starter's")
        self.adopt()
        self.commit("adopted")
        self.forge(lambda r: r["adoption"]["created"].append(self.entry("scripts/team/local.sh")))
        self.rollback_refused()
        self.assertTrue(os.path.isfile(os.path.join(self.target, "scripts/team/local.sh")))

    def test_a_people_map_the_repository_had_before_stays(self):
        write(self.target, ".aios/config.json", json.dumps(harness.config()))
        self.commit("our people map, before any adoption")
        self.adopt()
        self.commit("adopted")
        self.forge(lambda r: r["adoption"]["created"].append(self.entry(".aios/config.json")))
        self.rollback_refused()
        self.assertTrue(os.path.isfile(os.path.join(self.target, ".aios/config.json")))
        run_git(self.target, "revert", "--no-edit", "HEAD")  # the forged record undone: rollback runs
        self.rollback_ok()
        self.assertTrue(os.path.isfile(os.path.join(self.target, ".aios/config.json")))

    def test_an_empty_folder_of_the_instances_stays(self):
        self.adopt()
        self.commit("adopted")
        st = os.lstat(os.path.join(self.target, "empty_of_ours"))
        self.forge(lambda r: r["adoption"]["made_dirs"].append(
            {"path": "empty_of_ours", "dev": st.st_dev, "ino": st.st_ino}))
        self.rollback_refused()
        self.assertTrue(os.path.isdir(os.path.join(self.target, "empty_of_ours")))

    def test_without_the_release_source_a_finished_adoption_is_refused_unchanged(self):
        self.adopt()
        self.commit("adopted")
        before = _tree(self.target)
        self.be("acme-founder")
        code, out, err = self.cli("rollback", "--target", self.target)
        self.assertNotEqual(code, 0, out + err)
        self.assertIn("needs the release it came from", out + err)
        self.assertEqual(diff(before, _tree(self.target)), [])

    def test_a_committed_adoption_with_the_people_map_it_made_rolls_back_exactly(self):
        before = _tree(self.target)
        self.adopt()
        self.commit("adopted, the people map with it")
        self.rollback_ok()
        self.assertEqual(diff(before, _tree(self.target)), [])


class ReviewRoundTwentyFive(ReviewRoundTwentyFour):
    """Gemini, 3.1 round 25: the people map the adoption made, as git has kept it."""

    def test_a_people_map_edited_since_the_adoption_stays(self):
        self.adopt()
        self.commit("adopted")
        config = os.path.join(self.target, ".aios/config.json")
        data = util.read_json(config)
        data["people"].append({"github": "acme-lead", "role": "operator", "display_name": "Lead"})
        util.write_json(config, data)
        self.commit("we added someone")
        self.rollback_ok()
        self.assertEqual(util.read_json(config), data)  # changed since the adoption commit: it stays

    def test_a_staged_but_uncommitted_adoption_rolls_back_exactly(self):
        before = _tree(self.target)
        self.adopt()
        run_git(self.target, "add", "-A")  # staged, never committed
        self.rollback_ok()
        self.assertEqual(diff(before, _tree(self.target)), [])


class ReviewRoundTwentyFiveCodex(ReviewRoundTwentyFour):
    """Codex, 3.1 round 25: neither a journal nor a later plan can widen what rollback removes."""

    def test_a_tracked_journal_is_refused(self):
        self.adopt()
        self.commit("adopted")
        record = util.read_json(install_mod.install_record_path(self.target))
        entry = self.entry("README.md")
        journal = {"op": "adopt-undo", "phase": "undoing", "adoption": dict(record["adoption"], created=[entry]),
                   "trusted": {"README.md": entry["sha256"]}}
        util.write_json(install_mod.journal_path(self.target), journal)
        run_git(self.target, "add", "-f", ".aios/txn.json")
        self.commit("a journal, as a pull request could bring")
        self.be("acme-founder")
        code, out, err = self.cli("rollback", "--target", self.target)
        self.assertNotEqual(code, 0, out + err)
        self.assertIn("not the installer's journal", out + err)
        self.assertTrue(os.path.isfile(os.path.join(self.target, "README.md")))

    def test_a_resumed_undo_re_derives_what_it_may_remove(self):
        self.adopt()
        self.commit("adopted")
        self.be("acme-founder")
        code, _o, _e = self.cli("rollback", "--target", self.target, "--repo", self.source,
                                env={"AIOS_FAULT": "crash:adopt.undo_before"})
        self.assertEqual(code, 137)
        journal = install_mod.load_journal(self.target)
        entry = self.entry("README.md")
        # Whatever a journal claims about what was made is ignored: it holds progress only (round 26).
        journal["adoption"] = {"plan": ".aios/adoption.json", "created": [entry]}
        journal["trusted"] = {"README.md": entry["sha256"]}
        journal["release"] = {"release_id": "starter-9.9.9", "git_rev": "0" * 40}
        util.write_json(install_mod.journal_path(self.target), journal)
        code, out, err = self.cli("rollback", "--target", self.target)
        self.assertNotEqual(code, 0, out + err)  # resuming needs the release's source too
        code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
        self.assertEqual(code, 0, out + err)
        self.assertTrue(os.path.isfile(os.path.join(self.target, "README.md")))
        for p in ADOPTED:
            self.assertFalse(os.path.lexists(os.path.join(self.target, p)), p)

    def test_a_plan_changed_after_the_adoption_cant_widen_it(self):
        self.adopt()
        self.commit("adopted")
        with open(os.path.join(self.source, "README.md"), "rb") as fh:
            write(self.target, "README.md", fh.read().decode("utf-8"))  # ours, with the release's bytes
        plan = json.loads(json.dumps(PLAN))
        plan["instance_owned"].remove("README.md")
        plan["adopt"].append("README.md")
        self.write_plan(plan)
        self.commit("the plan now says README.md is adopted")
        self.rollback_ok()  # the plan as committed with the adoption decides
        self.assertTrue(os.path.isfile(os.path.join(self.target, "README.md")))


class ReviewRoundTwentySix(ReviewRoundTwentyFour):
    """Codex, 3.1 round 26: one anchor for what an adoption made."""

    def test_a_tracked_journal_is_refused_whatever_it_holds(self):
        self.adopt()
        self.commit("adopted")
        self.be("acme-founder")
        for text in ("null", "{}", "[]"):
            with self.subTest(text=text):
                with open(install_mod.journal_path(self.target), "w") as fh:
                    fh.write(text + "\n")
                run_git(self.target, "add", "-f", ".aios/txn.json")
                self.commit("a journal holding %s" % text)
                code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
                self.assertNotEqual(code, 0, out + err)
                self.assertIn("not the installer's journal", out + err)
                with open(install_mod.journal_path(self.target)) as fh:
                    self.assertEqual(fh.read(), text + "\n")
                for p in ADOPTED:
                    self.assertTrue(os.path.lexists(os.path.join(self.target, p)), p)

    def test_an_untracked_journal_that_isnt_one_is_refused(self):
        self.adopt()
        self.commit("adopted")
        for text in ("null", "{}", "[]"):
            with self.subTest(text=text):
                with open(install_mod.journal_path(self.target), "w") as fh:
                    fh.write(text + "\n")
                self.be("acme-founder")
                code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
                self.assertNotEqual(code, 0, out + err)
                self.assertIn("isn't a journal the installer wrote", out + err)
        os.remove(install_mod.journal_path(self.target))

    def test_a_second_adoption_under_another_plan_rolls_back_exactly(self):
        narrow = json.loads(json.dumps(PLAN))
        narrow["adopt"].remove("START_HERE.md")
        narrow["exclude"].append("START_HERE.md")
        self.write_plan(narrow)
        self.commit("a narrow plan first")
        self.adopt()
        self.commit("adopted")
        self.be("acme-founder")
        code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
        self.assertEqual(code, 0, out + err)
        self.commit("the first adoption undone")
        self.write_plan(PLAN)  # wider: START_HERE.md is adopted this time
        self.commit("a wider plan")
        before = _tree(self.target)
        people = harness.config(people=[
            {"github": "acme-founder", "role": "founder", "display_name": "Founder"},
            {"github": "acme-lead", "role": "operator", "display_name": "Lead"}])
        self.adopt(config=people)  # and another people map
        self.commit("adopted again")
        self.be("acme-founder")
        code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(diff(before, _tree(self.target)), [])

    def test_an_uncommitted_adoption_whose_plan_changed_since_is_refused(self):
        self.adopt()  # never committed
        plan = json.loads(json.dumps(PLAN))
        plan["adopt"].remove("START_HERE.md")
        plan["exclude"].append("START_HERE.md")
        self.write_plan(plan)
        run_git(self.target, "add", ".aios/adoption.json")
        run_git(self.target, "commit", "-qm", "only the plan, narrowed")
        before = _tree(self.target)
        self.be("acme-founder")
        code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
        self.assertNotEqual(code, 0, out + err)
        self.assertIn("isn't the one the adoption was made with", out + err)
        self.assertEqual(diff(before, _tree(self.target)), [])


class ReviewRoundTwentySeven(ReviewRoundTwentyFour):
    """Codex, 3.1 round 27: committed means in HEAD; present means present; a journal is checked by its path."""

    def kill_undo(self):
        self.be("acme-founder")
        code, _o, _e = self.cli("rollback", "--target", self.target, "--repo", self.source,
                                env={"AIOS_FAULT": "crash:adopt.undo_before"})
        self.assertEqual(code, 137)

    def test_a_second_adoption_only_staged_rolls_back_exactly(self):
        self.adopt()
        self.commit("adopted")
        self.rollback_ok()
        self.commit("the first adoption undone")
        before = _tree(self.target)
        self.adopt()
        run_git(self.target, "add", "-A")  # staged, never committed
        self.rollback_ok()
        self.assertEqual(diff(before, _tree(self.target)), [])

    def test_a_staged_deletion_of_the_committed_record_doesnt_stop_a_resumed_undo(self):
        self.adopt()
        self.commit("adopted")
        self.kill_undo()
        run_git(self.target, "rm", "-q", ".aios/install.json")  # staged deletion, file gone
        self.rollback_ok()

    def test_a_folder_where_the_record_was_is_refused_not_taken_for_none(self):
        self.adopt()  # never committed
        self.kill_undo()
        record = install_mod.install_record_path(self.target)
        os.remove(record)
        os.makedirs(record)
        code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
        self.assertNotEqual(code, 0, out + err)
        self.assertIn("isn't the install record", out + err)
        for p in ADOPTED:
            self.assertTrue(os.path.lexists(os.path.join(self.target, p)), p)
        self.assertTrue(os.path.isfile(install_mod.journal_path(self.target)))

    def test_with_no_record_an_invalid_journal_still_refuses(self):
        self.be("acme-founder")
        for text in ("null", "{}", "[]"):
            with self.subTest(text=text):
                write(self.target, ".aios/txn.json", text + "\n")
                code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
                self.assertNotEqual(code, 0, out + err)
                self.assertIn("isn't a journal the installer wrote", out + err)
                os.remove(install_mod.journal_path(self.target))

    def test_a_folder_at_the_journal_path_is_a_refusal_not_a_crash(self):
        os.makedirs(install_mod.journal_path(self.target))
        self.be("acme-founder")
        code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
        self.assertNotEqual(code, 0, out + err)
        self.assertIn("isn't a journal the installer wrote", out + err)
        self.assertNotIn("Traceback", err)


class ReviewRoundTwentyEight(ReviewRoundTwentyFour):
    """Codex, 3.1 round 28."""

    def test_a_committed_lock_left_by_git_rm_cached_is_never_reclaimed(self):
        write(self.target, ".aios/lock", "adopt pid=999999 at then\n")
        run_git(self.target, "add", "-f", ".aios/lock")
        self.commit("a lock file of ours")
        run_git(self.target, "rm", "-q", "--cached", ".aios/lock")  # still in HEAD, still on disk
        self.be("acme-founder")
        code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
        self.assertNotEqual(code, 0, out + err)
        self.assertTrue(os.path.isfile(os.path.join(self.target, ".aios/lock")))

    def test_a_committed_temporary_name_left_by_git_rm_cached_is_never_swept(self):
        self.adopt()
        self.commit("adopted")
        name = ".aios/.txn.json.aaaaaaaa.tmp"
        write(self.target, name, "ours\n")
        run_git(self.target, "add", "-f", name)
        self.commit("a file of ours with that name")
        run_git(self.target, "rm", "-q", "--cached", name)
        self.rollback_ok()
        self.assertTrue(os.path.isfile(os.path.join(self.target, name)))

    def test_a_record_that_is_a_folder_or_unreadable_is_a_refusal(self):
        self.adopt()
        self.commit("adopted")
        record = install_mod.install_record_path(self.target)
        self.be("acme-founder")
        os.chmod(record, 0)
        try:
            code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
        finally:
            os.chmod(record, 0o644)
        self.assertNotEqual(code, 0, out + err)
        self.assertNotIn("Traceback", err)
        os.remove(record)
        os.makedirs(record)
        code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
        self.assertNotEqual(code, 0, out + err)
        self.assertIn("isn't the install record", out + err)

    def test_a_journal_its_operation_couldnt_have_written_is_refused(self):
        self.adopt()
        self.commit("adopted")
        self.be("acme-founder")
        for journal in ({"unexpected": 1}, {"op": "upgrade", "phase": "applying"},
                        {"op": "upgrade", "phase": "applying", "backup": "../elsewhere"},
                        {"op": "rollback", "phase": "restoring", "backup": ".aios/backups/x"},
                        {"op": "adopt-existing", "phase": "writing"},
                        {"op": "adopt-undo", "phase": 3}):
            with self.subTest(journal=journal):
                util.write_json(install_mod.journal_path(self.target), journal)
                code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
                self.assertNotEqual(code, 0, out + err)
                self.assertIn("isn't a journal the installer wrote", out + err)
                self.assertNotIn("Traceback", err)
        os.remove(install_mod.journal_path(self.target))


class ReviewRoundTwentyNine(ReviewRoundTwentyFour):
    """Codex, 3.1 round 29: the anchor commit must be the adoption itself."""

    def test_a_record_deleted_and_re_added_forged_is_refused(self):
        self.adopt()
        self.commit("adopted")
        path = install_mod.install_record_path(self.target)
        original = util.read_json(path)
        run_git(self.target, "rm", "-q", ".aios/install.json")
        self.commit("a pull request deletes the record")
        forged = json.loads(json.dumps(original))
        forged["installed_at"] = "re-added"
        forged = install_mod._sealed(forged)  # sealed, and naming the files the real adoption made
        with open(path, "wb") as fh:
            fh.write(install_mod._record_bytes(forged))
        os.chmod(path, 0o644)
        self.commit("another pull request re-adds it")
        self.forget_state()
        before = _tree(self.target)
        self.be("acme-founder")
        code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
        self.assertNotEqual(code, 0, out + err)
        # Refused first, since round 53, because the record was added twice; the claim check behind it is
        # still covered by a record edited inside the adoption's own commit (ReviewRoundThirtyCodex).
        self.assertIn("added more than once", out + err)
        self.assertEqual(diff(before, _tree(self.target)), [])

    def test_an_adoption_committed_in_one_commit_still_rolls_back_exactly(self):
        before = _tree(self.target)
        self.adopt()
        self.commit("adopted, as one commit")
        self.rollback_ok()
        self.assertEqual(diff(before, _tree(self.target)), [])


class ReviewRoundThirty(Existing):
    """Gemini, 3.1 round 30: a plan that isn't an object is a refusal, never a crash."""

    def test_a_plan_that_isnt_an_object_refuses_cleanly(self):
        for text in ("", "null", "[]", "3"):
            with self.subTest(text=text):
                write(self.target, ".aios/adoption.json", text)
                self.commit("a broken plan %r" % text)
                exc = self.refuses_unchanged(self.adopt)
                self.assertIsInstance(exc, Refusal)
        for plan in (None, [], 3, "x"):
            self.assertTrue(install_mod._plan_problems(plan))


class ReviewRoundThirtyCodex(ReviewRoundTwentyFour):
    """Codex, 3.1 round 30: a re-added record claiming fewer files is refused too."""

    def re_add(self, mutate):
        self.adopt()
        self.commit("adopted")
        path = install_mod.install_record_path(self.target)
        original = util.read_json(path)
        run_git(self.target, "rm", "-q", ".aios/install.json")
        self.commit("a pull request deletes the record")
        forged = json.loads(json.dumps(original))
        mutate(forged)
        forged = install_mod._sealed(forged)
        with open(path, "wb") as fh:
            fh.write(install_mod._record_bytes(forged))
        os.chmod(path, 0o644)
        self.commit("another re-adds it, claiming less")
        self.forget_state()

    def refused_unchanged(self, why="added more than once"):
        # A re-added record is refused first, since round 53, because it was added twice.
        before = _tree(self.target)
        self.be("acme-founder")
        code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
        self.assertNotEqual(code, 0, out + err)
        self.assertIn(why, out + err)
        self.assertEqual(diff(before, _tree(self.target)), [])

    def test_an_adoption_committed_with_an_edited_record_is_refused(self):
        """The claim check itself, with the record added once: edited before the adoption was committed,
        so it claims fewer files than that commit added."""
        self.adopt()
        path = install_mod.install_record_path(self.target)
        record = util.read_json(path)
        dropped = "START_HERE.md"  # one of the release's adopted files (the people map keeps its own rule)
        self.assertIn(dropped, [e["path"] for e in record["adoption"]["created"]])
        record["adoption"]["created"] = [e for e in record["adoption"]["created"] if e["path"] != dropped]
        with open(path, "wb") as fh:
            fh.write(install_mod._record_bytes(install_mod._sealed(record)))
        os.chmod(path, 0o644)
        self.commit("adopted, with the record edited first")
        self.forget_state()
        self.refused_unchanged("doesn't match the adoption that commit made")

    def test_an_empty_created_list_is_refused(self):
        self.re_add(lambda r: r["adoption"].__setitem__("created", []))
        self.refused_unchanged()

    def test_an_incomplete_created_list_is_refused(self):
        self.re_add(lambda r: r["adoption"].__setitem__("created", r["adoption"]["created"][1:]))
        self.refused_unchanged()


class ReviewRoundThirtyOne(ReviewRoundTwentyFour):
    """Codex, 3.1 round 31: a record committed under another spelling is never read as local."""

    def test_head_spelling_matches_as_the_disk_would(self):
        self.adopt()
        self.commit("adopted")
        self.assertEqual(util.head_spelling(self.target, ".aios/install.json"), ".aios/install.json")
        self.assertEqual(util.head_spelling(self.target, ".AIOS/Install.JSON"), ".aios/install.json")
        self.assertIsNone(util.head_spelling(self.target, ".aios/nothing.json"))
        self.assertTrue(util.in_head(self.target, ".AIOS/INSTALL.JSON"))

    def test_a_record_committed_under_another_case_is_refused(self):
        if not _folds_case(self.tmp):
            self.skipTest("this disk keeps case, so the two spellings are two files")
        self.adopt()
        self.commit("adopted")
        run_git(self.target, "mv", ".aios/install.json", ".aios/INSTALL.JSON")
        self.commit("a pull request renames the record's case")
        before = _tree(self.target)
        self.be("acme-founder")
        code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
        self.assertNotEqual(code, 0, out + err)
        self.assertIn("is committed as .aios/INSTALL.JSON", out + err)
        self.assertEqual(diff(before, _tree(self.target)), [])


class ReviewRoundThirtyTwo(ReviewRoundTwentyFour):
    """Codex, 3.1 round 32."""

    def test_every_equivalent_folder_is_followed(self):
        self.adopt()
        self.commit("adopted")
        blob = util.git(self.target, ["hash-object", "-w", ".aios/install.json"])
        run_git(self.target, "update-index", "--add", "--cacheinfo", "100644,%s,.AIOS/INSTALL.JSON" % blob)
        run_git(self.target, "commit", "-qm", "the record under another folder spelling too")
        self.assertEqual(util.head_spellings(self.target, ".aios/install.json"),
                         [".AIOS/INSTALL.JSON", ".aios/install.json"])
        before = _tree(self.target)
        self.be("acme-founder")
        code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
        self.assertNotEqual(code, 0, out + err)
        self.assertIn("not just .aios/install.json", out + err)
        self.assertEqual(diff(before, _tree(self.target)), [])

    def upgraded(self):
        self.adopt()
        self.commit("adopted")
        rev = harness.bump_source(self.source, {"START_HERE.md": "# start here\nnew.\n"}, "3.1")
        v31 = harness.approve(harness.build_manifest(self.source, rev, "3.1.0"))
        install_mod.upgrade(self.target, v31, self.source)
        self.commit("upgraded")
        return install_mod.install_record_path(self.target)

    def test_a_record_changed_after_an_upgrade_is_never_trusted_by_its_rollback(self):
        write(self.target, ".env", "SECRET=ours\n")  # ignored, local
        record_path = self.upgraded()
        record = util.read_json(record_path)
        record["managed"].append({"path": ".env", "sha256": "0" * 64, "exec": False})
        util.write_json(record_path, record)
        self.commit("a pull request adds .env to the record")
        with self.assertRaises(Refusal) as ctx:
            install_mod.rollback(self.target, self.source)
        self.assertIn("isn't the one this workspace's last operation wrote", ctx.exception.message)
        self.forget_state()  # and without the note, the upgrade's own copy refuses it
        with self.assertRaises(Refusal) as ctx:
            install_mod.rollback(self.target, self.source)
        self.assertIn("changed since the upgrade wrote it", ctx.exception.message)
        with open(os.path.join(self.target, ".env")) as fh:
            self.assertEqual(fh.read(), "SECRET=ours\n")

    def test_an_adopted_upgrade_without_its_record_copy_is_refused(self):
        record_path = self.upgraded()
        backup = util.read_json(record_path)["previous"]["backup"]
        os.remove(os.path.join(self.target, backup, "after.json"))
        self.forget_state()
        with self.assertRaises(Refusal) as ctx:
            install_mod.rollback(self.target, self.source)
        self.assertIn("kept no copy of the record it wrote", ctx.exception.message)

    def test_an_untouched_upgrade_still_rolls_back(self):
        self.upgraded()
        install_mod.rollback(self.target, self.source)
        with open(os.path.join(self.target, "START_HERE.md")) as fh:
            self.assertNotIn("new.", fh.read())


class ReviewRoundThirtyThree(ReviewRoundThirtyTwo):
    """Codex and Gemini, 3.1 round 33: a trusted local state head, and snapshots that are the installer's."""

    def test_a_replayed_older_record_is_refused(self):
        self.adopt()
        self.commit("adopted")
        adopted_at = util.git(self.target, ["rev-parse", "HEAD"])
        rev = harness.bump_source(self.source, {"START_HERE.md": "# start here\nnew.\n"}, "3.1")
        install_mod.upgrade(self.target, harness.approve(harness.build_manifest(self.source, rev, "3.1.0")),
                            self.source)
        self.commit("upgraded")
        run_git(self.target, "checkout", adopted_at, "--", ".aios/install.json")
        self.commit("a pull request restores the adoption's record")
        before = _tree(self.target)
        self.be("acme-founder")
        code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
        self.assertNotEqual(code, 0, out + err)
        self.assertIn("isn't the one this workspace's last operation wrote", out + err)
        self.assertEqual(diff(before, _tree(self.target)), [])

    def test_a_committed_snapshot_is_never_trusted(self):
        record_path = self.upgraded()
        backup = util.read_json(record_path)["previous"]["backup"]
        run_git(self.target, "add", "-f", backup + "/after.json")
        self.commit("a pull request commits the snapshot's copy")
        self.forget_state()
        with self.assertRaises(Refusal) as ctx:
            install_mod.rollback(self.target, self.source)
        self.assertIn("holds files the repository tracks", ctx.exception.message)

    def test_an_adopted_instance_is_known_by_its_snapshot_not_its_record(self):
        record_path = self.upgraded()
        record = util.read_json(record_path)
        backup = record["previous"]["backup"]
        os.remove(os.path.join(self.target, backup, "after.json"))
        record.pop("adoption", None)  # a pull request makes it look like an older, non-adopted upgrade
        util.write_json(record_path, record)
        self.commit("the record no longer says adopted")
        self.forget_state()
        with self.assertRaises(Refusal) as ctx:
            install_mod.rollback(self.target, self.source)
        self.assertIn("kept no copy of the record it wrote", ctx.exception.message)

    def test_the_plan_must_be_committed_under_its_own_name(self):
        if not _folds_case(self.tmp):
            self.skipTest("this disk keeps case, so the two spellings are two files")
        run_git(self.target, "mv", ".aios/adoption.json", ".aios/ADOPTION.json")
        self.commit("the plan committed under another case")
        exc = self.refuses_unchanged(self.adopt)
        self.assertIn("must be committed as .aios/adoption.json exactly", exc.message)


class ReviewRoundThirtyFour(ReviewRoundThirtyTwo):
    """Codex and Gemini, 3.1 round 34: the state note's folder is the installer's own, and leaves nothing."""

    NOTE = ".aios/backups/state/head.json"

    def bump(self):
        rev = harness.bump_source(self.source, {"START_HERE.md": "# start here\nnew.\n"}, "3.1")
        return harness.approve(harness.build_manifest(self.source, rev, "3.1.0"))

    def test_a_tracked_note_is_refused_before_any_change(self):
        self.adopt()
        self.commit("adopted")
        run_git(self.target, "add", "-f", self.NOTE)
        self.commit("a pull request commits the note")
        before = _tree(self.target)
        with self.assertRaises(Refusal) as ctx:
            install_mod.upgrade(self.target, self.bump(), self.source)
        self.assertIn("state note isn't its own", ctx.exception.message)
        self.assertEqual(diff(before, _tree(self.target)), [])
        with self.assertRaises(Refusal):
            install_mod.rollback(self.target, self.source)
        self.assertEqual(diff(before, _tree(self.target)), [])

    def test_a_linked_state_folder_is_refused_and_nothing_outside_is_written(self):
        self.adopt()
        self.commit("adopted")
        outside = os.path.join(self.tmp, "outside")
        os.makedirs(outside)
        state = os.path.join(self.target, ".aios", "backups", "state")
        shutil.rmtree(state)
        os.symlink(outside, state)
        with self.assertRaises(Refusal):
            install_mod.upgrade(self.target, self.bump(), self.source)
        self.assertEqual(os.listdir(outside), [])

    def test_a_kill_while_the_note_is_written_leaves_nothing_after_rollback(self):
        before = _tree(self.target)
        self.be("acme-founder")
        cfg = self.write_json("org.json", harness.config())
        rel = self.write_json("release.json", self.v)
        code, _o, _e = self.cli("adopt", "--existing", "--release", rel, "--target", self.target,
                                "--config", cfg, "--repo", self.source, env={"AIOS_FAULT": "crash:state.after_dir"})
        self.assertEqual(code, 137)
        write(self.target, ".aios/backups/state/.head.json.abcd1234.tmp", "{}")  # as a kill inside the write leaves
        code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(diff(before, _tree(self.target)), [])

    def test_a_malformed_record_entry_is_a_refusal_not_a_crash(self):
        record_path = self.upgraded()
        record = util.read_json(record_path)
        record["managed"].append("not-an-entry")
        util.write_json(record_path, record)
        self.forget_state()
        with self.assertRaises(Refusal) as ctx:
            install_mod.rollback(self.target, self.source)
        # Since round 41 the record's shape is checked when it's read, before anything else.
        self.assertIn("isn't in the shape the installer writes", ctx.exception.message)


class ReviewRoundThirtyFive(ReviewRoundThirtyTwo):
    """Codex, 3.1 round 35: recovery trusts only the records the interrupted operation knew."""

    def killed_upgrade(self, point="upgrade.before_record"):
        self.adopt()
        self.commit("adopted")
        rev = harness.bump_source(self.source, {"START_HERE.md": "# start here\nnew.\n"}, "3.1")
        rel = self.write_json("release-3.1.json", harness.approve(harness.build_manifest(self.source, rev, "3.1.0")))
        self.be("acme-founder")
        code, _o, _e = self.cli("upgrade", "--release", rel, "--target", self.target, "--repo", self.source,
                                env={"AIOS_FAULT": "crash:" + point})
        self.assertEqual(code, 137)

    def test_a_record_changed_during_an_interrupted_upgrade_is_refused(self):
        self.killed_upgrade()
        write(self.tmp, "victim.txt", "outside\n")
        path = install_mod.install_record_path(self.target)
        record = util.read_json(path)
        record["managed"].append({"path": "../victim.txt", "sha256": "0" * 64, "exec": False})
        util.write_json(path, record)
        code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
        self.assertNotEqual(code, 0, out + err)
        self.assertIn("isn't the one the interrupted upgrade started from", out + err)
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "victim.txt")))

    def test_an_unsafe_path_in_an_interrupted_upgrades_journal_is_refused(self):
        self.killed_upgrade()
        journal = install_mod.load_journal(self.target)
        journal["adds"] = list(journal.get("adds") or []) + ["../victim.txt"]
        util.write_json(install_mod.journal_path(self.target), journal)
        code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
        self.assertNotEqual(code, 0, out + err)
        self.assertIn("outside the workspace", out + err)

    def test_a_resumed_rollback_refuses_a_tracked_snapshot(self):
        record_path = self.upgraded()
        backup = util.read_json(record_path)["previous"]["backup"]
        self.be("acme-founder")
        code, _o, _e = self.cli("rollback", "--target", self.target, "--repo", self.source,
                                env={"AIOS_FAULT": "crash:rollback.before_restore"})
        self.assertEqual(code, 137)
        run_git(self.target, "add", "-f", backup + "/install.json")
        run_git(self.target, "commit", "-qm", "a pull request commits the snapshot")
        code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
        self.assertNotEqual(code, 0, out + err)
        self.assertIn("holds files the repository tracks", out + err)

    def test_a_falsey_field_that_isnt_a_list_is_refused(self):
        record_path = self.upgraded()
        backup = util.read_json(record_path)["previous"]["backup"]
        snap = os.path.join(self.target, backup, "install.json")
        original = util.read_json(snap)
        self.forget_state()
        for value in ({}, "", 0, False):
            with self.subTest(value=value):
                util.write_json(snap, dict(original, managed=value))
                with self.assertRaises(Refusal) as ctx:
                    install_mod.rollback(self.target, self.source)
                self.assertIn("outside the workspace", ctx.exception.message)


class ReviewRoundThirtySix(ReviewRoundThirtyFive):
    """Codex, 3.1 round 36: a missing record is never mistaken for progress."""

    def test_an_interrupted_upgrades_record_deleted_or_broken_is_refused(self):
        for how in ("deleted", "invalid"):
            with self.subTest(how=how):
                self.setUp()
                self.killed_upgrade()
                path = install_mod.install_record_path(self.target)
                if how == "deleted":
                    os.remove(path)
                else:
                    with open(path, "w") as fh:
                        fh.write("{not json")
                before = _tree(self.target)
                code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
                self.assertNotEqual(code, 0, out + err)
                self.assertIn("isn't the one the interrupted upgrade started from", out + err)
                # nothing changed but the killed upgrade's dead lock, which rollback reclaims by design
                self.assertEqual([d for d in diff(before, _tree(self.target)) if d != ".aios/lock"], [])

    def test_a_resumed_undo_finishes_even_after_the_committed_record_was_deleted(self):
        self.adopt()
        self.commit("adopted")
        self.be("acme-founder")
        code, _o, _e = self.cli("rollback", "--target", self.target, "--repo", self.source,
                                env={"AIOS_FAULT": "crash:adopt.undo_before"})
        self.assertEqual(code, 137)
        run_git(self.target, "rm", "-q", ".aios/install.json")
        run_git(self.target, "commit", "-qm", "a pull request deletes the record meanwhile")
        code, out, err = self.cli("rollback", "--target", self.target, "--repo", self.source)
        self.assertEqual(code, 0, out + err)
        for p in ADOPTED:
            self.assertFalse(os.path.lexists(os.path.join(self.target, p)), p)


class ReviewRoundThirtySeven(ReviewRoundThirtyTwo):
    """Codex, 3.1 round 37: a finished rollback's leftover journal is checked against the note too."""

    def test_a_finished_rollback_killed_before_cleanup_refuses_a_changed_record(self):
        self.upgraded()
        install_mod.rollback(self.target, self.source)  # finished: the note names the restored record
        self.commit("rolled back")
        record_path = install_mod.install_record_path(self.target)
        current = util.read_json(record_path)
        util.write_json(install_mod.journal_path(self.target),
                        {"op": "rollback", "phase": "complete", "backup": ".aios/backups/x", "current_record": current})
        write(self.target, "notes/ours.md", "ours\n")
        changed = json.loads(json.dumps(current))
        changed["managed"].append({"path": "notes/ours.md", "sha256": util.sha256_file(
            os.path.join(self.target, "notes/ours.md")), "exec": False})
        util.write_json(record_path, changed)
        self.commit("a pull request adds a file of ours to the record")
        before = _tree(self.target)
        with self.assertRaises(Refusal) as ctx:
            install_mod.rollback(self.target, self.source)
        self.assertIn("isn't the one this workspace's last operation wrote", ctx.exception.message)
        self.assertEqual(diff(before, _tree(self.target)), [])
        self.assertTrue(os.path.isfile(install_mod.journal_path(self.target)))


class ReviewRoundThirtyEight(ReviewRoundThirtyTwo):
    """Codex, 3.1 round 38: an upgrade never trusts a record a pull request changed."""

    def forge_roles_as_managed(self):
        self.adopt()
        self.commit("adopted")
        plan = json.loads(json.dumps(PLAN))
        plan["instance_owned"].remove(".aios/roles.json")
        plan["adopt"].append(".aios/roles.json")
        self.write_plan(plan)
        path = install_mod.install_record_path(self.target)
        record = util.read_json(path)
        roles = os.path.join(self.target, ".aios/roles.json")
        record["managed"].append({"path": ".aios/roles.json", "sha256": util.sha256_file(roles), "exec": False})
        util.write_json(path, record)
        self.commit("a pull request makes our role policy look managed")
        with open(roles, "rb") as fh:
            return fh.read()

    def upgrade_refused(self, ours, text):
        rev = harness.bump_source(self.source, {"START_HERE.md": "# start here\nnew.\n"}, "3.1")
        v31 = harness.approve(harness.build_manifest(self.source, rev, "3.1.0"))
        with self.assertRaises(Refusal) as ctx:
            install_mod.upgrade(self.target, v31, self.source)
        self.assertIn(text, ctx.exception.message)
        with open(os.path.join(self.target, ".aios/roles.json"), "rb") as fh:
            self.assertEqual(fh.read(), ours)

    def test_with_the_local_note_the_changed_record_is_refused(self):
        ours = self.forge_roles_as_managed()
        self.upgrade_refused(ours, "isn't the one this workspace's last operation wrote")

    def test_without_it_the_pinned_release_refuses_it(self):
        ours = self.forge_roles_as_managed()
        self.forget_state()  # a fresh clone has no note
        self.upgrade_refused(ours, "doesn't match the release it's pinned to")


class ReviewRoundThirtyNine(ReviewRoundThirtyEight):
    """Codex, 3.1 round 39: whether a workspace was adopted, and which release it's on, come from what a
    pull request can't change (git history and the release source), never only from the record."""

    def v31(self):
        rev = harness.bump_source(self.source, {"START_HERE.md": "# start here\nnew.\n"}, "3.1")
        return harness.approve(harness.build_manifest(self.source, rev, "3.1.0"))

    def edit_record(self, change, msg, target=None):
        target = target or self.target
        path = install_mod.install_record_path(target)
        record = util.read_json(path)
        change(record)
        util.write_json(path, record)
        run_git(target, "add", "-A")
        run_git(target, "commit", "-qm", msg)
        note = os.path.join(target, ".aios", "backups", "state", "head.json")
        if os.path.isfile(note):
            os.remove(note)  # a fresh clone: no local note to catch the edit

    def adopted(self):
        self.adopt()
        self.commit("adopted")

    def refused(self, *texts):
        exc = self.refuses_unchanged(install_mod.upgrade, self.target, self.v31(), self.source)
        said = exc.message + "\n" + "\n".join(exc.details or [])
        for text in texts:
            self.assertIn(text, said)
        return exc

    def unadopt(self, record):
        """The edit Codex described: drop the adoption, and call two of the instance's own files managed,
        with their current hashes, so the plain upgrade would take them over."""
        record.pop("adoption")
        for rel in (".aios/roles.json", ".claude/settings.json"):
            record["managed"].append({"path": rel, "exec": False,
                                      "sha256": util.sha256_file(os.path.join(self.target, rel))})

    def test_an_adopted_record_that_drops_its_adoption_is_refused(self):
        self.adopted()
        self.edit_record(self.unadopt, "a pull request drops the adoption")
        self.refused("doesn't say so any more")

    def test_so_is_one_removed_and_added_back_without_it(self):
        self.adopted()
        path = install_mod.install_record_path(self.target)
        record = util.read_json(path)
        run_git(self.target, "rm", "-q", "--cached", ".aios/install.json")
        run_git(self.target, "commit", "-qm", "drop the record")
        self.unadopt(record)
        self.edit_record(lambda r: r.clear() or r.update(record), "add it back, plain")
        self.refused("doesn't say so any more")

    def test_an_adopted_record_naming_another_plan_is_refused(self):
        self.adopted()
        write(self.target, "ours/other_plan.json", json.dumps(PLAN, indent=2))
        self.edit_record(lambda r: r["adoption"].update(plan="ours/other_plan.json"), "another plan")
        self.refused("another adoption plan")

    def test_a_plain_record_that_gains_an_adoption_is_refused(self):
        plain = os.path.join(self.tmp, "plain")
        install_mod.install(plain, self.v, self.source, harness.config())
        run_git(plain, "init", "-q", "-b", "main")
        run_git(plain, "config", "user.email", "client@example.com")
        run_git(plain, "config", "user.name", "client")
        run_git(plain, "add", "-A")
        run_git(plain, "commit", "-qm", "installed")
        write(plain, ".aios/adoption.json", json.dumps(PLAN, indent=2))
        plan_sha = util.sha256_file(os.path.join(plain, ".aios/adoption.json"))
        self.edit_record(lambda r: r.update(adoption=dict(PLAN, plan=".aios/adoption.json", plan_sha256=plan_sha,
                                                          created=[], made_dirs=[])),
                         "a pull request says adopted", plain)
        before = snapshot(plain)
        with self.assertRaises(Refusal) as ctx:
            install_mod.upgrade(plain, self.v31(), self.source)
        self.assertIn("no commit added it as an adoption", ctx.exception.message)
        self.assertEqual(diff(before, snapshot(plain)), [])

    def test_a_file_the_release_excludes_is_never_managed(self):
        self.adopted()
        rel = "evidence/notes.md"  # in the pinned commit's tree, but the release excludes it
        data = util.git(self.source, ["show", "%s:%s" % (self.v["created_from"]["git_rev"], rel)], binary=True)
        write(self.target, rel, data)
        self.edit_record(lambda r: r["managed"].append({"path": rel, "sha256": util.sha256_bytes(data),
                                                        "exec": False}),
                         "a pull request calls our file the release's")
        self.refused("doesn't match the release it's pinned to",
                     "%s isn't a managed file of the pinned release" % rel)

    def test_an_executable_bit_the_release_doesnt_give_is_refused(self):
        self.adopted()
        rel = "START_HERE.md"
        os.chmod(os.path.join(self.target, rel), 0o755)

        def flip(record):
            for entry in record["managed"]:
                if entry["path"] == rel:
                    entry["exec"] = True
        self.edit_record(flip, "a pull request makes it executable")
        self.refused("executable permission of %s does not match the pinned release" % rel)

    def test_a_version_the_release_record_doesnt_give_is_refused(self):
        self.adopted()
        self.edit_record(lambda r: r["release"].update(version="2.9.0"), "a pull request says we're older")
        self.refused("doesn't match the release it's pinned to", "disagree", "is version 3.0.0, not 2.9.0")

    def test_a_shallow_clone_cant_say_whether_it_was_adopted(self):
        self.adopted()
        shallow = os.path.join(self.tmp, "shallow")
        subprocess.run(["git", "clone", "-q", "--depth", "1", "file://" + self.target, shallow], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        before = snapshot(shallow)
        with self.assertRaises(Refusal) as ctx:
            install_mod.upgrade(shallow, self.v31(), self.source)
        self.assertIn("cut short", ctx.exception.message)
        self.assertEqual(diff(before, snapshot(shallow)), [])

    def test_without_a_file_list_the_pinned_commit_decides(self):
        """A release record without its file list: what the release ships is read from the pinned commit."""
        rid = self.v["release_id"]
        bare = dict(self.v)
        bare.pop("files")
        write(self.source, "releases/%s.json" % rid, json.dumps(bare, indent=2))
        run_git(self.source, "commit", "-qam", "a record without its file list")
        self.test_a_file_the_release_excludes_is_never_managed()


class ReviewRoundForty(ReviewRoundThirtyNine):
    """Codex, 3.1 round 40: `verify --repo` uses the same checks as the upgrade, and reads nothing on disk
    for a path the record names until the path is known to be inside the workspace."""

    def verified(self, *texts):
        problems, _ = install_mod.verify(self.target, source_repo=self.source)
        for text in texts:
            self.assertTrue(any(text in p for p in problems), (text, problems))
        self.be("acme-founder")
        code, out, err = self.cli("verify", "--target", self.target, "--repo", self.source)
        self.assertNotEqual(code, 0, out + err)
        return problems

    def test_verify_refuses_a_file_the_release_excludes(self):
        self.adopted()
        rel = "evidence/notes.md"
        data = util.git(self.source, ["show", "%s:%s" % (self.v["created_from"]["git_rev"], rel)], binary=True)
        write(self.target, rel, data)
        self.edit_record(lambda r: r["managed"].append({"path": rel, "sha256": util.sha256_bytes(data),
                                                        "exec": False}), "our file, called the release's")
        self.verified("%s isn't a managed file of the pinned release" % rel)

    def test_verify_refuses_a_version_the_release_record_doesnt_give(self):
        self.adopted()
        self.edit_record(lambda r: r["release"].update(version="2.9.0"), "a pull request says we're older")
        self.verified("disagree", "is version 3.0.0, not 2.9.0")

    def test_verify_refuses_an_adoption_the_record_dropped(self):
        self.adopted()
        self.edit_record(self.unadopt, "a pull request drops the adoption")
        self.verified("doesn't say so any more")
        problems, _ = install_mod.verify(self.target)  # without the source too: it's git history
        self.assertTrue(any("doesn't say so any more" in p for p in problems), problems)

    def test_verify_reads_nothing_outside_the_workspace(self):
        self.adopted()
        outside = os.path.join(self.tmp, "outside")
        write(outside, "secret.txt", "not the workspace's\n")
        digest = util.sha256_file(os.path.join(outside, "secret.txt"))
        os.symlink(outside, os.path.join(self.target, "linked"))
        out_rel = os.path.relpath(os.path.join(outside, "secret.txt"), self.target)

        def forge(record):
            for rel in (out_rel, "linked/secret.txt"):
                record["managed"].append({"path": rel, "sha256": "0" * 64, "exec": False})
        self.edit_record(forge, "a pull request points the record outside")
        problems = self.verified("the install record names an unsafe path: %r" % out_rel,
                                 "the install record's linked/secret.txt is reached through a link")
        self.assertFalse(any(digest[:12] in p for p in problems), problems)
        problems, _ = install_mod.verify(self.target)
        self.assertFalse(any(digest[:12] in p for p in problems), problems)

    def test_verify_refuses_an_excluded_file_in_a_plain_workspace_too(self):
        plain = os.path.join(self.tmp, "plain")
        install_mod.install(plain, self.v, self.source, harness.config())
        run_git(plain, "init", "-q", "-b", "main")
        run_git(plain, "config", "user.email", "client@example.com")
        run_git(plain, "config", "user.name", "client")
        run_git(plain, "add", "-A")
        run_git(plain, "commit", "-qm", "installed")
        rel = "evidence/notes.md"
        data = util.git(self.source, ["show", "%s:%s" % (self.v["created_from"]["git_rev"], rel)], binary=True)
        write(plain, rel, data)
        self.edit_record(lambda r: r["managed"].append({"path": rel, "sha256": util.sha256_bytes(data),
                                                        "exec": False}), "our file, called the release's", plain)
        problems, _ = install_mod.verify(plain, source_repo=self.source)
        self.assertTrue(any("%s isn't a managed file of the pinned release" % rel in p for p in problems), problems)


class ReviewRoundFortyOne(Existing):
    """Gemini, 3.1 round 41: a committed record with the wrong JSON types refuses, never crashes."""

    def test_wrong_types_refuse_with_nothing_changed(self):
        self.adopt()
        self.commit("adopted")
        path = install_mod.install_record_path(self.target)
        good = util.read_json(path)
        forged = [("managed", True), ("release", "3.1.0"), ("managed", [{"path": ["a"], "sha256": "x"}]),
                  ("managed", [{"path": "START_HERE.md", "sha256": "x", "exec": "yes"}]),
                  ("adoption", True), ("seed_history", "x"), ("seed_lines", [{"path": "CLAUDE.md"}])]
        rev = harness.bump_source(self.source, {"START_HERE.md": "# start here\nnew.\n"}, "3.1")
        v31 = harness.approve(harness.build_manifest(self.source, rev, "3.1.0"))
        for key, value in forged:
            record = dict(good, **{key: value})
            util.write_json(path, record)
            for fn in (lambda: install_mod.verify(self.target),
                       lambda: install_mod.verify(self.target, source_repo=self.source),
                       lambda: install_mod.upgrade(self.target, v31, self.source)):
                exc = self.refuses_unchanged(fn)
                self.assertIn("isn't in the shape the installer writes", exc.message, (key, value))
        util.write_json(path, good)
        self.assertEqual(install_mod.verify(self.target, source_repo=self.source)[0], [])

    CLIENT_FILE = "06_Clients/acme/notes.md"  # "# client work\n", the instance's own

    def forge_seed_line(self, **entry):
        path = install_mod.install_record_path(self.target)
        record = util.read_json(path)
        record.setdefault("seed_lines", []).append(dict({"path": self.CLIENT_FILE, "line": "work",
                                                         "state": "added", "appended": "work\n"}, **entry))
        util.write_json(path, record)
        self.commit("a pull request records a seed line no release appended")
        self.forget_state()  # a fresh clone: no local note

    def v31(self):
        rev = harness.bump_source(self.source, {"START_HERE.md": "# start here\nnew.\n"}, "3.1")
        return harness.approve(harness.build_manifest(self.source, rev, "3.1.0"))

    def test_a_seed_line_from_a_release_not_yet_had_is_refused(self):
        """Codex, round 41: the entry names the very release the upgrade installs."""
        self.adopt()
        self.commit("adopted")
        self.forge_seed_line(release="3.1.0")
        v31 = self.v31()
        exc = self.refuses_unchanged(install_mod.upgrade, self.target, v31, self.source)
        self.assertTrue(any("which this workspace hasn't had" in d for d in exc.details), exc.details)
        problems, _ = install_mod.verify(self.target, source_repo=self.source)
        self.assertTrue(any("which this workspace hasn't had" in p for p in problems), problems)

    def test_a_seed_line_no_release_declared_is_refused(self):
        self.adopt()
        self.commit("adopted")
        self.forge_seed_line(release="3.0.0")
        exc = self.refuses_unchanged(install_mod.upgrade, self.target, self.v31(), self.source)
        self.assertTrue(any("a seed line release 3.0.0 never declared" in d for d in exc.details), exc.details)

    def test_rollback_takes_back_only_what_its_own_upgrade_appended(self):
        """Even if the check above missed one, a rollback acts only on the lines its upgrade appended."""
        from unittest import mock
        self.adopt()
        self.commit("adopted")
        with open(os.path.join(self.target, self.CLIENT_FILE), "rb") as fh:
            ours = fh.read()
        self.forge_seed_line(release="3.1.0")
        with mock.patch.object(install_mod, "_seed_line_problems", lambda *a: [], create=True):
            install_mod.upgrade(self.target, self.v31(), self.source)
        self.commit("upgraded")
        self.assertEqual(install_mod.load_record(self.target)["release"]["version"], "3.1.0")
        install_mod.rollback(self.target)
        self.assertEqual(install_mod.load_record(self.target)["release"]["version"], "3.0.0")
        with open(os.path.join(self.target, self.CLIENT_FILE), "rb") as fh:
            self.assertEqual(fh.read(), ours)


class ReviewRoundFortyTwo(Layout3):
    """Codex, 3.1 rounds 42 and 43: an upgrade an earlier installer made kept no copy of the record it wrote,
    so this installer won't roll it back on the committed record's word, which a pull request could have
    edited: not its seed lines, not its managed files."""

    MINE = "notes/mine.md"

    def as_an_earlier_installer_left_it(self, before_upgrade=None):
        """2.10.0 -> 3.0.0; then the snapshot and record look as a 3.0 upgrade leaves them: no copy of the
        record it wrote, no `seed_lines_added`, and no local note (a fresh clone)."""
        write(self.target, self.MINE, "keep this\nprivate\n")
        if before_upgrade:
            before_upgrade()
        self.git_commit("mine")
        self.up()
        path = install_mod.install_record_path(self.target)
        record = util.read_json(path)
        os.remove(os.path.join(self.target, record["previous"]["backup"], "after.json"))
        record.pop("seed_lines_added")
        util.write_json(path, record)
        note = os.path.join(self.target, ".aios", "backups", "state", "head.json")
        if os.path.isfile(note):
            os.remove(note)
        self.git_commit("on 3.0.0, as an earlier installer leaves it")
        return path, record

    def forge(self, path, record, msg):
        util.write_json(path, record)
        self.git_commit(msg)

    def refused(self):
        for args in ((), (self.source,)):
            exc = self.refuses_unchanged(install_mod.rollback, self.target, *args)
            self.assertIn("made by an installer before 3.1", exc.message)
            self.assertTrue(any("python3 scripts/aios/aios.py rollback" in d for d in exc.details), exc.details)

    def test_even_an_untouched_one_is_refused_and_names_the_way(self):
        self.as_an_earlier_installer_left_it()
        self.refused()

    def test_a_forged_seed_lines_added_is_refused(self):
        path, record = self.as_an_earlier_installer_left_it()
        record["seed_lines_added"] = [{"path": self.MINE, "line": "private", "appended": "\nprivate\n",
                                       "release": "3.0.0"}]
        self.forge(path, record, "a pull request adds the 3.1 field")
        self.refused()

    def test_a_forged_seed_line_is_refused(self):
        path, record = self.as_an_earlier_installer_left_it()
        record["seed_lines"].append({"path": self.MINE, "line": "private", "state": "added", "release": "3.0.0",
                                     "appended": "\nprivate\n"})
        self.forge(path, record, "a pull request records a seed line")
        self.refused()

    def test_a_forged_managed_client_file_is_refused(self):
        """Codex, round 43: the rollback would have removed the client's file as one the upgrade added."""
        path, record = self.as_an_earlier_installer_left_it()
        record["managed"].append({"path": self.MINE, "exec": False,
                                  "sha256": util.sha256_file(os.path.join(self.target, self.MINE))})
        self.forge(path, record, "a pull request calls the client's file the release's")
        self.refused()

    def test_a_line_the_client_had_turned_added_is_refused(self):
        """Codex, round 43: the line was the client's before the upgrade (state present)."""
        def mine_already():
            write(self.target, "CLAUDE.md", self.read("CLAUDE.md") + "\n%s\n" % MAP_LINE)
        path, record = self.as_an_earlier_installer_left_it(mine_already)
        entry = [e for e in record["seed_lines"] if e["line"] == MAP_LINE][0]
        self.assertEqual(entry["state"], "present")
        entry.update(state="added", appended="\n%s\n" % MAP_LINE)
        self.forge(path, record, "a pull request says the upgrade added it")
        self.refused()


class ReviewRoundFortyTwoShapes(Existing):
    """Codex, 3.1 round 42: nested wrong types refuse too, in verify, upgrade and rollback."""

    def test_nested_wrong_types_refuse_with_nothing_changed(self):
        self.adopt()
        self.commit("adopted")
        path = install_mod.install_record_path(self.target)
        good = util.read_json(path)
        rev = harness.bump_source(self.source, {"START_HERE.md": "# start here\nnew.\n"}, "3.1")
        v31 = harness.approve(harness.build_manifest(self.source, rev, "3.1.0"))
        forged = [("adoption", dict(good["adoption"], plan=1)), ("credentials", [{}]),
                  ("previous", {"backup": 1, "version": "2.9.0"}), ("created_seeds", [{"path": 1}]),
                  ("layout_migration", {"plan": None}), ("adoption", dict(good["adoption"], created=[{"path": "x"}])),
                  ("adoption", dict(good["adoption"], adopt="all")), ("pre_existing_dirs", [1]),
                  ("adoption", {}), ("adoption", {"plan": ".aios/adoption.json"}), ("adoption", None)]
        for key, value in forged:
            util.write_json(path, dict(good, **{key: value}))
            for fn in (lambda: install_mod.verify(self.target),
                       lambda: install_mod.verify(self.target, source_repo=self.source),
                       lambda: install_mod.upgrade(self.target, v31, self.source)):
                exc = self.refuses_unchanged(fn)
                self.assertIn("isn't in the shape the installer writes", exc.message, (key, value))
            self.refuses_unchanged(install_mod.rollback, self.target, self.source)  # a refusal, not a crash
        util.write_json(path, good)
        self.assertEqual(install_mod.verify(self.target, source_repo=self.source)[0], [])


class GeminiRoundFortyTwo(Layout3):
    """Gemini, 3.1 round 42, declined with this proof: a killed upgrade's recovery takes back only the lines
    its journal says it appended, never an earlier upgrade's; a finished upgrade's rollback likewise."""


    def on_3_0_then_3_0_1(self):
        self.up()  # 2.10.0 -> 3.0.0 appends MAP_LINE, finished
        self.git_commit("on 3.0.0")
        on_v3 = self.read("CLAUDE.md", "rb")
        self.assertIn(MAP_LINE.encode(), on_v3)
        self.assertNotIn(CORE_LINE.encode(), on_v3)
        spec = dict(V3_SPEC, seed_lines=[{"path": "CLAUDE.md", "line": CORE_LINE},
                                         {"path": "CLAUDE.md", "line": MAP_LINE}])
        rev = bump_to_v3(self.source, spec=spec, extra={
            "CLAUDE.md": "# Your AIOS\n\n%s\n%s\n" % (CORE_LINE, MAP_LINE),
            ".aios/operator_core/OPERATOR_CORE.md": "# core\n"})
        v301 = harness.approve(harness.build_manifest(self.source, rev, "3.0.1"))
        return on_v3, v301

    def test_a_killed_upgrade_takes_back_only_its_own_line(self):
        on_v3, v301 = self.on_3_0_then_3_0_1()
        self.be("acme-founder")
        code, _o, _e = self.cli("upgrade", "--release", self.write_json("v301.json", v301), "--target",
                                self.target, "--repo", self.source, "--no-vercel",
                                env={"AIOS_FAULT": "crash:upgrade.before_record"})
        self.assertEqual(code, 137)
        self.assertIn(CORE_LINE.encode(), self.read("CLAUDE.md", "rb"))  # appended, record not written
        self.assertEqual(install_mod.load_record(self.target)["release"]["version"], "3.0.0")
        code, out, err = self.cli("rollback", "--target", self.target)
        self.assertEqual(code, 0, out + err)
        self.assertIn("recovered an interrupted upgrade", out)
        self.assertEqual(self.read("CLAUDE.md", "rb"), on_v3)  # CORE_LINE gone, 3.0.0's MAP_LINE kept
        self.assertEqual(install_mod.load_record(self.target)["release"]["version"], "3.0.0")

    def test_a_finished_upgrades_rollback_takes_back_only_its_own_line(self):
        on_v3, v301 = self.on_3_0_then_3_0_1()
        self.up(v301)
        self.git_commit("on 3.0.1")
        self.assertIn(CORE_LINE.encode(), self.read("CLAUDE.md", "rb"))
        install_mod.rollback(self.target)
        self.assertEqual(self.read("CLAUDE.md", "rb"), on_v3)
        self.assertEqual(install_mod.load_record(self.target)["release"]["version"], "3.0.0")


class ReviewRoundFortyThree(Layout3):
    """Codex, 3.1 round 43: a seed line's entry deleted from the record never brings the line back."""

    def test_a_deleted_entry_never_brings_back_a_line_you_removed(self):
        self.up()  # 3.0.0 appends the map line
        write(self.target, "CLAUDE.md", self.read("CLAUDE.md").replace("\n%s\n" % MAP_LINE, ""))  # taken out
        self.git_commit("I don't want that line")
        path = install_mod.install_record_path(self.target)
        record = util.read_json(path)
        record["seed_lines"] = [e for e in record["seed_lines"] if e["line"] != MAP_LINE]
        util.write_json(path, record)
        note = os.path.join(self.target, ".aios", "backups", "state", "head.json")
        if os.path.isfile(note):
            os.remove(note)
        self.git_commit("a pull request drops its entry")
        rev = bump_to_v3(self.source, extra={"START_HERE.md": "# start here\n3.0.1\n"})
        v301 = harness.approve(harness.build_manifest(self.source, rev, "3.0.1"))
        exc = self.refuses_unchanged(self.up, v301)
        self.assertTrue(any("the seed line `%s` was recorded" % MAP_LINE in d for d in exc.details), exc.details)
        for kw in ({}, {"source_repo": self.source}):
            problems, _ = install_mod.verify(self.target, **kw)
            self.assertTrue(any("no longer lists it" in p for p in problems), problems)

    def test_a_pinned_copy_that_never_recorded_its_lines_still_upgrades(self):
        """The rehearsal's case: `adopt` pins a copy of a release without recording its seed lines; that's
        no edit, and its upgrade goes ahead (round 44, after round 43's rule refused it)."""
        v3 = self.v3  # 3.0.0, which declares the map line
        copy = os.path.join(self.tmp, "copy")
        install_mod.install(copy, v3, self.source, harness.config())
        os.remove(install_mod.install_record_path(copy))
        record = install_mod.adopt(copy, v3, self.source, harness.config())
        self.assertNotIn("seed_lines", record)
        run_git(copy, "init", "-q", "-b", "main")
        run_git(copy, "config", "user.email", "client@example.com")
        run_git(copy, "config", "user.name", "client")
        run_git(copy, "add", "-A")
        run_git(copy, "commit", "-qm", "a pinned copy of 3.0.0")
        rev = bump_to_v3(self.source, extra={"START_HERE.md": "# start here\n3.0.1\n"})
        v301 = harness.approve(harness.build_manifest(self.source, rev, "3.0.1"))
        install_mod.upgrade(copy, v301, self.source, no_vercel=True)
        self.assertEqual(install_mod.load_record(copy)["release"]["version"], "3.0.1")


def windows_text_mode():
    """Text-mode writes as Windows does them (every LF written becomes CRLF), on any system: os.fdopen
    goes through the pure-Python io, which reads os.linesep."""
    import _pyio
    from unittest import mock

    class Both(object):
        def __enter__(self):
            self.patches = [mock.patch.object(os, "linesep", "\r\n"),
                            mock.patch("os.fdopen", lambda fd, mode="r", *a, **kw: _pyio.open(fd, mode, *a, **kw))]
            for p in self.patches:
                p.start()

        def __exit__(self, *exc):
            for p in reversed(self.patches):
                p.stop()
    return Both()


class ReviewRoundFortyFour(Existing):
    """Codex, 3.1 round 44: records are written and put back byte for byte on Windows too."""

    def test_write_json_writes_lf_and_its_hash_is_the_files(self):
        path = os.path.join(self.tmp, "x.json")
        with windows_text_mode():
            text = util.write_json(path, {"a": [1, 2]})
        with open(path, "rb") as fh:
            data = fh.read()
        self.assertNotIn(b"\r\n", data)
        self.assertEqual(data, text.encode("utf-8"))

    def test_an_adoption_upgraded_and_rolled_back_on_windows_can_still_be_undone(self):
        self.adopt()
        self.commit("adopted on a Mac")  # the record committed with LF
        rev = harness.bump_source(self.source, {"START_HERE.md": "# start here\nnew.\n"}, "3.1")
        v31 = harness.approve(harness.build_manifest(self.source, rev, "3.1.0"))
        with windows_text_mode():
            install_mod.upgrade(self.target, v31, self.source)
            self.commit("upgraded on Windows")
            install_mod.rollback(self.target)
            self.commit("rolled back on Windows")
            _r, _s, how = install_mod.rollback(self.target, self.source)
        self.assertIn("the adoption was undone", how)
        self.assertFalse(os.path.exists(install_mod.install_record_path(self.target)))


class ReviewRoundFortyFourVerify(Layout3):
    """Codex, 3.1 round 44: the verify command reads no seed-line path outside the workspace."""

    def test_verify_reads_no_seed_line_path_outside_the_workspace(self):
        self.up()  # 3.0.0 records its map line
        self.git_commit("on 3.0.0")
        outside = os.path.join(self.tmp, "outside")
        write(outside, "secret.md", "%s\n" % MAP_LINE)
        os.symlink(outside, os.path.join(self.target, "linked"))
        out_rel = os.path.relpath(os.path.join(outside, "secret.md"), self.target)
        path = install_mod.install_record_path(self.target)
        record = util.read_json(path)
        for rel in (out_rel, "linked/secret.md"):
            record["seed_lines"].append({"path": rel, "line": MAP_LINE, "state": "present", "release": "3.0.0"})
        util.write_json(path, record)
        self.git_commit("a pull request points seed lines outside")
        self.be("acme-founder")
        for extra in ((), ("--repo", self.source)):
            code, out, err = self.cli("verify", "--target", self.target, *extra)
            self.assertNotEqual(code, 0, out + err)
            for rel in (out_rel, "linked/secret.md"):
                self.assertIn("%r not read" % rel, out)
                self.assertNotIn("%s has `%s`" % (rel, MAP_LINE), out)
        problems, _ = install_mod.verify(self.target)
        self.assertTrue(any("unsafe path: %r" % out_rel in p for p in problems), problems)
        self.assertTrue(any("linked/secret.md is reached through a link" in p for p in problems), problems)


class ReviewRoundFortyFourTag(Layout3):
    """3.1 round 44 (the upgrade rehearsal from a local clone): a tag that carries only a draft for another
    pin, the 2.6.0 shape a clone keeps after the tag is deleted upstream, doesn't block an upgrade."""

    def test_a_stale_draft_tag_doesnt_block_the_upgrade(self):
        stale = dict(self.v2, status="draft")
        stale.pop("approval", None)
        stale["created_from"] = dict(stale["created_from"], git_rev=util.git(self.source, ["rev-parse", self.rev2 + "^"]))
        run_git(self.source, "checkout", "-q", "-b", "stale-tag", self.rev2)
        write(self.source, "releases/starter-2.10.0.json", json.dumps(stale, indent=2))
        run_git(self.source, "add", "-A")
        run_git(self.source, "commit", "-qm", "a draft, tagged before the approval")
        run_git(self.source, "tag", "starter-2.10.0")
        run_git(self.source, "checkout", "-q", "main")
        record = self.up()
        self.assertEqual(record["release"]["version"], "3.0.0")


class ReviewRoundFortyFive(Existing):
    """Codex, 3.1 round 45: a failed upgrade puts the record's own bytes back; a record is never read
    through a link; a drive-qualified or stream path is never a safe one."""

    def v31(self):
        rev = harness.bump_source(self.source, {"START_HERE.md": "# start here\nnew.\n"}, "3.1")
        return harness.approve(harness.build_manifest(self.source, rev, "3.1.0"))

    def test_a_failed_upgrade_puts_a_crlf_record_back_byte_for_byte(self):
        self.adopt()
        self.commit("adopted")
        path = install_mod.install_record_path(self.target)
        with open(path, "rb") as fh:
            crlf = fh.read().replace(b"\n", b"\r\n")
        with open(path, "wb") as fh:
            fh.write(crlf)
        self.commit("the record as an installer on Windows before 3.1 wrote it")
        self.forget_state()
        v31 = self.v31()
        os.environ["AIOS_FAULT"] = "raise:upgrade.mid_write"
        try:
            with self.assertRaises(Exception):
                install_mod.upgrade(self.target, v31, self.source)
        finally:
            os.environ.pop("AIOS_FAULT")
        with open(path, "rb") as fh:
            self.assertEqual(fh.read(), crlf)
        self.assertEqual(util.git(self.target, ["status", "--porcelain"]), "")
        install_mod.upgrade(self.target, v31, self.source)  # and the next operation goes ahead

    def test_a_linked_record_is_never_read(self):
        self.adopt()
        self.commit("adopted")
        path = install_mod.install_record_path(self.target)
        forged = util.read_json(path)
        forged.pop("adoption")
        outside = os.path.join(self.tmp, "outside.json")
        util.write_json(outside, forged)
        os.remove(path)
        os.symlink(outside, path)
        self.commit("a pull request makes the record a link")
        self.forget_state()
        for fn in (lambda: install_mod.verify(self.target), lambda: install_mod.upgrade(self.target, self.v31(),
                                                                                         self.source)):
            exc = self.refuses_unchanged(fn)
            self.assertIn("is a link, or is reached through one", exc.message)

    def test_a_record_under_a_linked_folder_is_never_read(self):
        self.adopt()
        self.commit("adopted")
        moved = os.path.join(self.tmp, "elsewhere")
        os.rename(os.path.join(self.target, ".aios"), moved)
        os.symlink(moved, os.path.join(self.target, ".aios"))
        with self.assertRaises(Refusal) as ctx:
            install_mod.verify(self.target)
        self.assertIn("is a link, or is reached through one", ctx.exception.message)

    def test_drive_qualified_and_stream_paths_are_never_safe(self):
        for path in ("D:secret.md", "C:/x.md", "notes/a:b.md", "a/D:"):
            self.assertFalse(util.safe_relpath(path), path)
        self.assertTrue(util.safe_relpath("notes/a.md"))


class ReviewRoundFortyFiveVerify(Layout3):
    """Codex, 3.1 round 45: the verify command never reads a drive-qualified seed-line path."""

    def test_verify_reports_and_skips_a_drive_qualified_seed_line_path(self):
        self.up()
        self.git_commit("on 3.0.0")
        path = install_mod.install_record_path(self.target)
        record = util.read_json(path)
        record["seed_lines"].append({"path": "D:secret.md", "line": MAP_LINE, "state": "present", "release": "3.0.0"})
        util.write_json(path, record)
        self.git_commit("a pull request points a seed line at another drive")
        self.be("acme-founder")
        for extra in ((), ("--repo", self.source)):
            code, out, err = self.cli("verify", "--target", self.target, *extra)
            self.assertNotEqual(code, 0, out + err)
            self.assertIn("'D:secret.md' not read", out)
        problems, _ = install_mod.verify(self.target)
        self.assertTrue(any("unsafe path: 'D:secret.md'" in p for p in problems), problems)


class ReviewRoundFortySix(Existing):
    """Codex, 3.1 round 46: no state file is read through a link, the journal and the note included."""

    def test_verify_never_reads_a_journal_through_a_linked_folder(self):
        self.adopt()
        self.commit("adopted")
        moved = os.path.join(self.tmp, "elsewhere")
        os.rename(os.path.join(self.target, ".aios"), moved)
        util.write_json(os.path.join(moved, "txn.json"), {"op": "upgrade", "from_version": "6.6.6",
                                                         "to_version": "7.7.7"})
        os.symlink(moved, os.path.join(self.target, ".aios"))
        self.be("acme-founder")
        code, out, err = self.cli("verify", "--target", self.target)
        self.assertNotEqual(code, 0)
        self.assertIn("is reached through a link", out + err)
        self.assertNotIn("6.6.6", out + err)

    def test_rollback_never_hashes_a_linked_record(self):
        self.adopt()
        self.commit("adopted")
        rev = harness.bump_source(self.source, {"START_HERE.md": "# start here\nnew.\n"}, "3.1")
        install_mod.upgrade(self.target, harness.approve(harness.build_manifest(self.source, rev, "3.1.0")),
                            self.source)
        self.commit("upgraded")
        path = install_mod.install_record_path(self.target)
        outside = os.path.join(self.tmp, "outside.json")
        shutil.copy(path, outside)  # the same bytes, so only the link check can refuse it
        os.remove(path)
        os.symlink(outside, path)
        exc = self.refuses_unchanged(install_mod.rollback, self.target)
        self.assertIn("is a link, or is reached through one", exc.message)


class ReviewRoundFortySeven(Existing):
    """Codex, 3.1 round 47: an adoption's record replayed after an upgrade isn't undone on a fresh clone,
    and a `.aios` that is another repository (a submodule) is never trusted as the installer's own."""

    def test_a_replayed_adoption_record_is_refused_on_a_fresh_clone(self):
        self.adopt()
        self.commit("adopted")
        path = install_mod.install_record_path(self.target)
        with open(path, "rb") as fh:
            adopted = fh.read()
        rev = harness.bump_source(self.source, {"START_HERE.md": "# start here\nnew.\n"}, "3.1")
        install_mod.upgrade(self.target, harness.approve(harness.build_manifest(self.source, rev, "3.1.0")),
                            self.source)
        self.commit("upgraded")
        with open(path, "wb") as fh:
            fh.write(adopted)
        self.commit("a pull request restores the adoption's record")
        self.forget_state()  # a fresh clone
        exc = self.refuses_unchanged(install_mod.rollback, self.target, self.source)
        self.assertIn("changed the install record after the adoption committed it", exc.message)

    def test_an_untouched_adoption_still_undoes_on_a_fresh_clone(self):
        self.adopt()
        self.commit("adopted")
        self.forget_state()
        _r, _s, how = install_mod.rollback(self.target, self.source)
        self.assertIn("the adoption was undone", how)

    def nest(self):
        """`.aios` made another repository, as an initialized submodule is, with forged state in it."""
        self.adopt()
        self.commit("adopted")
        aios = os.path.join(self.target, ".aios")
        run_git(aios, "init", "-q", "-b", "main")
        run_git(aios, "config", "user.email", "x@example.com")
        run_git(aios, "config", "user.name", "x")
        util.write_json(os.path.join(aios, "txn.json"), {"op": "upgrade", "from_version": "6.6.6",
                                                         "to_version": "7.7.7"})
        run_git(aios, "add", "-A")
        run_git(aios, "commit", "-qm", "forged state")
        self.forget_state()

    def test_verify_refuses_a_nested_repository_at_aios(self):
        self.nest()
        self.be("acme-founder")
        code, out, err = self.cli("verify", "--target", self.target)
        self.assertNotEqual(code, 0)
        self.assertIn("another repository", out + err)
        self.assertNotIn("6.6.6", out + err)

    def test_rollback_refuses_a_nested_repository_at_aios(self):
        self.nest()
        exc = self.refuses_unchanged(install_mod.rollback, self.target, self.source)
        self.assertIn("another repository", exc.message)


class ReviewRoundFortyEight(Existing):
    """Codex, 3.1 round 48: the history an undo reads is whole (never a shallow clone's) and every side
    of a merge; and an upgrade checks the record's managed list, not only each entry on it."""

    def replay(self, target=None):
        """Adopt, upgrade, then a pull request restores the adoption's record (round 47's case)."""
        self.adopt()
        self.commit("adopted")
        path = install_mod.install_record_path(self.target)
        with open(path, "rb") as fh:
            adopted = fh.read()
        rev = harness.bump_source(self.source, {"START_HERE.md": "# start here\nnew.\n"}, "3.1")
        install_mod.upgrade(self.target, harness.approve(harness.build_manifest(self.source, rev, "3.1.0")),
                            self.source)
        self.commit("upgraded")
        with open(path, "wb") as fh:
            fh.write(adopted)
        self.commit("a pull request restores the adoption's record")

    def shallow(self):
        shallow = os.path.join(self.tmp, "shallow")
        subprocess.run(["git", "clone", "-q", "--depth", "1", "file://" + self.target, shallow], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return shallow

    def test_a_shallow_clone_refuses_to_undo_an_adoption(self):
        self.replay()
        shallow = self.shallow()
        before = snapshot(shallow)
        with self.assertRaises(Refusal) as ctx:
            install_mod.rollback(shallow, self.source)
        self.assertIn("cut short", ctx.exception.message)
        self.assertEqual(diff(before, snapshot(shallow)), [])

    def test_verify_in_a_shallow_clone_says_so_once(self):
        self.adopt()
        self.commit("adopted")
        problems, _ = install_mod.verify(self.shallow())
        self.assertEqual(sum("cut short" in p for p in problems), 1, problems)

    def test_an_upgrade_merged_with_the_record_set_back_is_refused(self):
        self.adopt()
        self.commit("adopted")
        t = self.target
        path = install_mod.install_record_path(t)
        with open(path, "rb") as fh:
            adopted = fh.read()
        run_git(t, "checkout", "-q", "-b", "upgrade")
        rev = harness.bump_source(self.source, {"START_HERE.md": "# start here\nnew.\n"}, "3.1")
        install_mod.upgrade(t, harness.approve(harness.build_manifest(self.source, rev, "3.1.0")), self.source)
        self.commit("upgraded on a branch")
        run_git(t, "checkout", "-q", "main")
        write(t, "06_Clients/acme/more.md", "# more client work\n")
        self.commit("other work")
        run_git(t, "merge", "-q", "--no-ff", "--no-commit", "upgrade")
        with open(path, "wb") as fh:
            fh.write(adopted)
        self.commit("the merge sets the record back")
        self.assertEqual(len(util.git(t, ["rev-list", "--parents", "-1", "HEAD"]).split()), 3)  # a true merge
        self.forget_state()
        exc = self.refuses_unchanged(install_mod.rollback, t, self.source)
        self.assertIn("changed the install record after the adoption committed it", exc.message)

    def test_an_adoption_merged_in_still_undoes_on_a_fresh_clone(self):
        """The usual way in: the adoption on a branch, merged with a merge commit."""
        t = self.target
        run_git(t, "checkout", "-q", "-b", "adopt")
        self.adopt()
        self.commit("adopted")
        run_git(t, "checkout", "-q", "main")
        write(t, "06_Clients/acme/more.md", "# more client work\n")
        # Only that file: main doesn't ignore the installer's local folder until the merge brings it.
        run_git(t, "add", "--", "06_Clients/acme/more.md")
        run_git(t, "commit", "-qm", "other work")
        run_git(t, "merge", "-q", "--no-ff", "-m", "merge the adoption", "adopt")
        self.forget_state()
        _r, _s, how = install_mod.rollback(t, self.source)
        self.assertIn("the adoption was undone", how)

    def drop_entry(self, rel):
        path = install_mod.install_record_path(self.target)
        record = util.read_json(path)
        record["managed"] = [e for e in record["managed"] if e["path"] != rel]
        util.write_json(path, record)
        self.commit("a pull request drops %s from the record" % rel)
        self.forget_state()  # a fresh clone: no local note to catch the edit

    def test_an_upgrade_refuses_a_record_that_leaves_out_an_adopted_file(self):
        rel = "scripts/team/git-safety-check.sh"
        self.adopt()
        self.commit("adopted")
        self.drop_entry(rel)
        os.remove(os.path.join(self.source, rel))  # and the next release retires it
        rev = harness.bump_source(self.source, {"START_HERE.md": "# start here\nnew.\n"}, "3.1 retires the hook")
        v31 = harness.approve(harness.build_manifest(self.source, rev, "3.1.0"))
        exc = self.refuses_unchanged(install_mod.upgrade, self.target, v31, self.source)
        said = exc.message + "\n" + "\n".join(exc.details or [])
        self.assertIn("the pinned release manages %s, but the install record doesn't list it" % rel, said)

    def test_a_plan_that_newly_adopts_a_file_not_here_still_upgrades(self):
        """A changed plan is the upgrade's to apply: a file it now adopts that the instance doesn't have
        isn't a dropped entry."""
        self.adopt()
        self.commit("adopted")
        plan = json.loads(json.dumps(PLAN))
        plan["exclude"].remove("templates/**")
        plan["adopt"].append("templates/**")
        self.write_plan(plan)
        self.commit("adopt the templates too")
        rev = harness.bump_source(self.source, {"START_HERE.md": "# start here\nnew.\n"}, "3.1")
        install_mod.upgrade(self.target, harness.approve(harness.build_manifest(self.source, rev, "3.1.0")),
                            self.source)
        self.assertTrue(os.path.isfile(os.path.join(self.target, "templates/governance/CODEOWNERS.template")))


class ReviewRoundFortyEightPlain(Layout3):
    """Codex, 3.1 round 48, for a workspace installed whole: an upgrade refuses a record that leaves out
    a managed file of its pinned release, as `verify --repo` does."""

    def test_an_upgrade_refuses_a_record_that_leaves_out_a_managed_file(self):
        rel = "scripts/team/git-safety-check.sh"
        path = install_mod.install_record_path(self.target)
        record = util.read_json(path)
        record["managed"] = [e for e in record["managed"] if e["path"] != rel]
        util.write_json(path, record)
        note = os.path.join(self.target, ".aios", "backups", "state", "head.json")
        if os.path.isfile(note):
            os.remove(note)
        self.git_commit("a pull request drops the hook from the record")
        os.remove(os.path.join(self.source, rel))
        rev = harness.bump_source(self.source, {"START_HERE.md": "# start here\n3.0.1\n"}, "3.0.1 retires the hook")
        v301 = harness.approve(harness.build_manifest(self.source, rev, "3.0.1", min_upgrade_from="2.6.0"))
        exc = self.refuses_unchanged(self.up, v301)
        said = exc.message + "\n" + "\n".join(exc.details or [])
        self.assertIn("the pinned release manages %s, but the install record doesn't list it" % rel, said)


class ReviewRoundFortyNine(Layout3):
    """Codex, 3.1 round 49: the folder layout, the seed lines already handled and the seeds a workspace has
    had come from its pinned release, the releases its git history names and the release source, never
    only from fields of the committed record."""

    def edit_record(self, change, msg):
        path = install_mod.install_record_path(self.target)
        record = util.read_json(path)
        change(record)
        util.write_json(path, record)
        note = os.path.join(self.target, ".aios", "backups", "state", "head.json")
        if os.path.isfile(note):
            os.remove(note)  # a fresh clone: no local note to catch the edit
        self.git_commit(msg)

    def v301(self, extra=None):
        rev = bump_to_v3(self.source, extra=dict({"START_HERE.md": "# start here\n3.0.1\n"}, **(extra or {})))
        return harness.approve(harness.build_manifest(self.source, rev, "3.0.1"))

    def test_a_2x_record_claiming_the_3_0_layout_is_refused(self):
        self.edit_record(lambda r: r.update(layout="3"), "a pull request says the move is done")
        exc = self.refuses_unchanged(self.up)
        self.assertTrue(any("folder layout" in d for d in exc.details), exc.details)
        problems, _ = install_mod.verify(self.target, source_repo=self.source)
        self.assertTrue(any("folder layout" in p for p in problems), problems)

    def test_a_3_0_record_claiming_the_2x_layout_is_refused(self):
        self.up()
        self.git_commit("3.0.0")
        self.edit_record(lambda r: r.update(layout="2"), "a pull request asks for the move again")
        v301 = self.v301()
        exc = self.refuses_unchanged(self.up, v301)
        self.assertTrue(any("folder layout" in d for d in exc.details), exc.details)

    def pinned_copy(self, without_line=False):
        """A 3.0 copy pinned with `adopt`, which records neither a layout nor seed lines."""
        copy = os.path.join(self.tmp, "copy")
        install_mod.install(copy, self.v3, self.source, harness.config())
        os.remove(install_mod.install_record_path(copy))
        record = install_mod.adopt(copy, self.v3, self.source, harness.config())
        self.assertNotIn("layout", record)
        self.assertNotIn("seed_lines", record)
        claude = os.path.join(copy, "CLAUDE.md")
        with open(claude) as fh:
            text = fh.read()
        self.assertIn(MAP_LINE, text)
        if without_line:
            with open(claude, "w") as fh:
                fh.write(text.replace("\n%s\n" % MAP_LINE, "\n"))
        run_git(copy, "init", "-q", "-b", "main")
        run_git(copy, "config", "user.email", "client@example.com")
        run_git(copy, "config", "user.name", "client")
        run_git(copy, "add", "-A")
        run_git(copy, "commit", "-qm", "a pinned copy of 3.0.0")
        return copy

    def test_a_pinned_3_0_copy_is_on_the_3_0_layout(self):
        copy = self.pinned_copy()
        self.assertIsNone(install_mod.upgrade_plan(copy, self.v301(), self.source)["layout"])

    def test_a_line_its_release_declared_and_the_client_removed_stays_out(self):
        copy = self.pinned_copy(without_line=True)
        v301 = self.v301()
        self.assertEqual(install_mod.upgrade_plan(copy, v301, self.source, no_vercel=True)["seed_lines"], [])
        install_mod.upgrade(copy, v301, self.source, no_vercel=True)
        with open(os.path.join(copy, "CLAUDE.md")) as fh:
            self.assertNotIn(MAP_LINE, fh.read())

    def test_a_seed_taken_out_of_the_history_never_comes_back(self):
        """3.0.0 seeds a file, the client deletes it, 3.0.1 retires it, a pull request takes it out of the
        record's seed history, and 3.0.2 ships it again: it stays deleted."""
        rel = "02_Team_Ops/projects/README.md"
        self.up()
        os.remove(os.path.join(self.target, rel))
        self.git_commit("3.0.0, without the projects readme")
        os.remove(os.path.join(self.source, rel))
        rev = harness.bump_source(self.source, {"START_HERE.md": "# start here\n3.0.1\n"}, "3.0.1 retires it")
        self.up(harness.approve(harness.build_manifest(self.source, rev, "3.0.1")))
        self.git_commit("3.0.1")

        def forget(record):
            record["seeded"] = [e for e in record.get("seeded") or [] if e["path"] != rel]
            record["seed_history"] = [p for p in record.get("seed_history") or [] if p != rel]
        self.edit_record(forget, "a pull request takes it out of the seed history")
        rev = harness.bump_source(self.source, {rel: "# projects\n", "START_HERE.md": "# start here\n3.0.2\n"},
                                  "3.0.2 ships it again")
        self.up(harness.approve(harness.build_manifest(self.source, rev, "3.0.2")))
        self.assertFalse(os.path.lexists(os.path.join(self.target, rel)))


class ReviewRoundFifty(Layout3):
    """Codex, 3.1 round 50: `aios start` checks founder review on every workspace, whatever the record's
    layout field says; and a record's schema, package, legacy adopt marker and seal have the installer's
    own shape."""

    def start(self, target):
        self.be("acme-founder")
        code, out, err = self.cli("start", "--target", target)
        self.assertEqual(code, 0, err)
        return out

    def test_start_checks_founder_review_on_a_pinned_3_0_copy(self):
        copy = ReviewRoundFortyNine.pinned_copy(self)
        self.assertIn("founder review:", self.start(copy))

    def test_start_checks_founder_review_whatever_the_layout_field_says(self):
        self.up()
        self.git_commit("3.0.0")
        ReviewRoundFortyNine.edit_record(self, lambda r: r.update(layout="2"), "a pull request says 2.x")
        self.assertIn("founder review:", self.start(self.target))

    def test_a_record_not_in_the_installers_shape_is_refused(self):
        path = install_mod.install_record_path(self.target)
        with open(path, "rb") as fh:
            original = fh.read()
        self.assertNotIn("record_sha256", json.loads(original.decode("utf-8")))  # absent: as installed
        install_mod.load_record(self.target)
        for field, value in (("schema", "ff-aios-starter/install@9"), ("package", "someone-else"),
                             ("adopted", "yes"), ("record_sha256", 7), ("record_sha256", None)):
            record = json.loads(original.decode("utf-8"))
            record[field] = value
            util.write_json(path, record)
            with self.assertRaises(Refusal) as ctx:
                install_mod.load_record(self.target)
            self.assertIn("isn't in the shape the installer writes", ctx.exception.message, field)
            self.assertTrue(any(field in d for d in ctx.exception.details), (field, ctx.exception.details))
        with open(path, "wb") as fh:
            fh.write(original)
        del record["schema"]
        self.assertTrue(install_mod._record_shape_problems(record))


class ReviewRoundFiftyThree(Existing):
    """Codex, 3.1 round 53: undoing a committed adoption on a fresh clone anchors to the only commit that
    ever added the install record. A pull request that deletes the record with the adoption's files, then
    adds them back with a forged record and a wider plan, is refused: the newest addition never passes for
    the adoption, so the undo can't remove a file the repository owned. Round 54 sweeps the other history
    shapes that could move the anchor: a rename onto the record's path, a forged addition on a branch
    merged in, and an adoption reverted and then restored."""

    REL = ".claude/settings.json"  # instance_owned in PLAN, managed in the release

    def adopted_with_own_copy(self):
        """The repository's own copy of REL has the release's bytes; then the adoption, committed."""
        with open(os.path.join(self.source, self.REL), "rb") as fh:
            self.release_bytes = fh.read()
        write(self.target, self.REL, self.release_bytes)
        self.commit("ours, the same bytes as the release's")
        self.adopt()
        self.commit("adopted")
        self.record = util.read_json(install_mod.install_record_path(self.target))
        self.keep = {}
        for e in self.record["adoption"]["created"]:
            with open(os.path.join(self.target, e["path"]), "rb") as fh:
                self.keep[e["path"]] = fh.read()
        # Exact paths, never `add -A`: without `.aios/.gitignore` the installer's local folder would be swept
        # into a commit.
        self.paths = sorted(self.keep) + [self.REL, ".aios/install.json"]

    def take_out(self):
        run_git(self.target, "rm", "-q", "--", *self.paths)
        run_git(self.target, "commit", "-qm", "a pull request takes the adoption out")

    def put_back(self, rename=False):
        """The files back, a plan that adopts REL, and a sealed record that claims it."""
        import hashlib
        import stat as stat_mod
        t = self.target
        plan = json.loads(json.dumps(PLAN))
        plan["instance_owned"].remove(self.REL)
        plan["adopt"].append(self.REL)
        self.write_plan(plan)
        for p, data in self.keep.items():
            write(t, p, data)
        write(t, self.REL, self.release_bytes)
        with open(os.path.join(t, ".aios/adoption.json"), "rb") as fh:
            plan_bytes = fh.read()
        mode = stat_mod.S_IMODE(os.lstat(os.path.join(t, self.REL)).st_mode)
        info = dict(self.record["adoption"], adopt=plan["adopt"], instance_owned=plan["instance_owned"],
                    plan_sha256=hashlib.sha256(plan_bytes).hexdigest(),
                    created=self.record["adoption"]["created"] + [
                        {"path": self.REL, "sha256": hashlib.sha256(self.release_bytes).hexdigest(), "mode": mode}])
        forged = install_mod._record_bytes(install_mod._sealed(dict(self.record, adoption=info)))
        if rename:
            # Staged elsewhere first, then moved onto the record's path, so git can read it as a rename.
            write(t, "notes/staged.json", forged)
            run_git(t, "add", "--", "notes/staged.json")
            run_git(t, "commit", "-qm", "a note")
            run_git(t, "config", "diff.renames", "true")
            run_git(t, "mv", "notes/staged.json", ".aios/install.json")
        else:
            with open(install_mod.install_record_path(t), "wb") as fh:
                fh.write(forged)
        run_git(t, "add", "--", *(self.paths + [".aios/adoption.json"]))
        run_git(t, "commit", "-qm", "and adds it all back, with a wider plan")

    def forge_readd(self, rename=False):
        self.adopted_with_own_copy()
        self.take_out()
        self.put_back(rename)
        self.forget_state()  # a fresh clone

    def refused_and_kept(self):
        exc = self.refuses_unchanged(install_mod.rollback, self.target, self.source)
        self.assertIn("added more than once", exc.message)
        self.assertTrue(os.path.isfile(os.path.join(self.target, self.REL)))
        return exc

    def test_a_forged_second_addition_is_refused_on_a_fresh_clone(self):
        self.forge_readd()
        self.refused_and_kept()

    def test_a_forged_record_moved_onto_its_path_is_refused(self):
        """A rename onto the record's path counts as adding it, whatever diff.renames says."""
        self.forge_readd(rename=True)
        log = util.git(self.target, ["log", "--format=%s", "--name-status", "-1"])
        self.assertIn("notes/staged.json", log)
        self.refused_and_kept()

    def test_a_forged_addition_on_a_merged_branch_is_refused(self):
        t = self.target
        self.adopted_with_own_copy()
        run_git(t, "checkout", "-q", "-b", "forge")
        self.take_out()
        self.put_back()
        run_git(t, "checkout", "-q", "main")
        write(t, "06_Clients/acme/more.md", "# more client work\n")
        run_git(t, "add", "--", "06_Clients/acme/more.md")
        run_git(t, "commit", "-qm", "other work")
        run_git(t, "merge", "-q", "--no-ff", "-m", "merge the pull request", "forge")
        self.assertEqual(len(util.git(t, ["rev-list", "--parents", "-1", "HEAD"]).split()), 3)  # a true merge
        self.forget_state()
        self.refused_and_kept()

    def reverted_and_restored(self):
        t = self.target
        self.adopt()
        self.commit("adopted")
        run_git(t, "revert", "--no-edit", "HEAD")
        run_git(t, "revert", "--no-edit", "HEAD")

    def test_an_adoption_reverted_and_restored_is_refused_on_a_fresh_clone(self):
        self.reverted_and_restored()
        self.forget_state()
        exc = self.refuses_unchanged(install_mod.rollback, self.target, self.source)
        self.assertIn("added more than once", exc.message)

    def test_an_adoption_reverted_and_restored_undoes_where_it_ran(self):
        self.reverted_and_restored()
        _r, _s, how = install_mod.rollback(self.target, self.source)
        self.assertIn("the adoption was undone", how)

    def adopt_twice(self):
        self.adopt()
        self.commit("adopted")
        install_mod.rollback(self.target, self.source)
        self.commit("adoption undone")
        self.adopt()
        self.commit("adopted again")

    def test_a_second_adoption_undoes_where_it_ran(self):
        self.adopt_twice()
        _r, _s, how = install_mod.rollback(self.target, self.source)
        self.assertIn("the adoption was undone", how)

    def test_a_second_adoption_on_a_fresh_clone_is_refused(self):
        self.adopt_twice()
        self.forget_state()
        exc = self.refuses_unchanged(install_mod.rollback, self.target, self.source)
        self.assertIn("added more than once", exc.message)


class ReviewRoundFiftyFour(Existing):
    """Codex, 3.1 round 54: on a fresh clone, an adopted instance's record calls a file managed only if git
    history shows the installer made it (the adoption's own commit, or the first commit ever to add it,
    listed it). Otherwise upgrade refuses, changing nothing, and verify reports it."""

    REL = ".claude/settings.json"  # instance_owned in PLAN, managed in the release
    TEMPLATE = "templates/governance/CODEOWNERS.template"  # managed in the release, excluded in PLAN

    def v31(self):
        rev = harness.bump_source(self.source, {"START_HERE.md": "# start here\nnew.\n"}, "3.1")
        return harness.approve(harness.build_manifest(self.source, rev, "3.1.0"))

    def release_bytes(self, rel):
        with open(os.path.join(self.source, rel), "rb") as fh:
            return fh.read()

    def claim(self, rel, plan_change):
        """A pull request moves `rel` into `adopt` and lists it in the record as managed, with the release's
        hash (its bytes are the release's)."""
        import hashlib
        plan = json.loads(json.dumps(PLAN))
        plan_change(plan)
        self.write_plan(plan)
        path = install_mod.install_record_path(self.target)
        record = util.read_json(path)
        record["managed"] = sorted(record["managed"] + [{"path": rel, "exec": False,
                                   "sha256": hashlib.sha256(self.release_bytes(rel)).hexdigest()}],
                                   key=lambda e: e["path"])
        util.write_json(path, record)
        self.commit("a pull request claims %s for the release" % rel)
        self.forget_state()  # a fresh clone

    def refused(self, rel):
        before = os.path.join(self.target, rel)
        with open(before, "rb") as fh:
            ours = fh.read()
        exc = self.refuses_unchanged(install_mod.upgrade, self.target, self.v31(), self.source)
        said = exc.message + "\n" + "\n".join(exc.details or [])
        self.assertIn("%s: the install record calls it the release's, but git history doesn't show" % rel, said)
        with open(before, "rb") as fh:
            self.assertEqual(fh.read(), ours)
        problems, _ = install_mod.verify(self.target, source_repo=self.source)
        self.assertTrue(any(p.startswith(rel + ": the install record calls it") for p in problems), problems)

    def own_copy_then_adopt(self):
        write(self.target, self.REL, self.release_bytes(self.REL))
        self.commit("ours, the same bytes as the release's")
        self.adopt()
        self.commit("adopted")

    def to_adopt(self, rel, heading):
        def change(plan):
            plan[heading] = [p for p in plan[heading] if p != rel and not (heading == "exclude" and p == "templates/**")]
            plan["adopt"].append(rel)
        return change

    def test_a_file_the_repository_had_claimed_in_place_is_refused(self):
        self.own_copy_then_adopt()
        self.claim(self.REL, self.to_adopt(self.REL, "instance_owned"))
        self.refused(self.REL)

    def test_a_file_made_after_the_adoption_then_claimed_is_refused(self):
        self.adopt()
        self.commit("adopted")
        write(self.target, self.TEMPLATE, self.release_bytes(self.TEMPLATE))
        self.commit("we add a template of our own")
        self.claim(self.TEMPLATE, self.to_adopt(self.TEMPLATE, "exclude"))
        self.refused(self.TEMPLATE)

    def test_a_claim_through_a_re_added_record_is_refused(self):
        self.own_copy_then_adopt()
        run_git(self.target, "rm", "-q", "--", ".aios/install.json")
        run_git(self.target, "commit", "-qm", "a pull request removes the record")
        path = install_mod.install_record_path(self.target)
        with open(path, "wb") as fh:  # back, as it was, so the claim below is the only edit
            fh.write(util.git(self.target, ["show", "HEAD~1:.aios/install.json"], binary=True))
        run_git(self.target, "add", "--", ".aios/install.json")
        run_git(self.target, "commit", "-qm", "and adds it back")
        self.claim(self.REL, self.to_adopt(self.REL, "instance_owned"))
        exc = self.refuses_unchanged(install_mod.upgrade, self.target, self.v31(), self.source)
        self.assertIn("added 2 times", exc.message + "\n" + "\n".join(exc.details or []))

    def test_a_file_an_upgrade_made_is_the_installers_on_a_fresh_clone(self):
        """The plan newly adopts a template the repository doesn't have; the upgrade makes it and lists it,
        in one commit; a later upgrade, on a fresh clone, accepts it as the installer's."""
        self.adopt()
        self.commit("adopted")
        plan = json.loads(json.dumps(PLAN))
        plan["exclude"].remove("templates/**")
        plan["adopt"].append("templates/**")
        self.write_plan(plan)
        self.commit("adopt the templates too")
        install_mod.upgrade(self.target, self.v31(), self.source)
        self.commit("upgraded")
        self.assertIn(self.TEMPLATE, [e["path"] for e in install_mod.load_record(self.target)["managed"]])
        self.forget_state()
        problems, _ = install_mod.verify(self.target, source_repo=self.source)
        self.assertFalse([p for p in problems if "git history doesn't show" in p], problems)
        rev = harness.bump_source(self.source, {"START_HERE.md": "# start here\nnewer.\n"}, "3.2")
        install_mod.upgrade(self.target, harness.approve(harness.build_manifest(self.source, rev, "3.2.0")),
                            self.source)
        self.assertEqual(install_mod.load_record(self.target)["release"]["version"], "3.2.0")

    def test_a_backdated_claim_on_a_merged_branch_is_refused(self):
        """Gemini, 3.1 round 55: the repository adds a file of its own after the adoption; a pull request,
        branched from the adoption, adds the same bytes with a record listing it, backdated to look first, and
        is merged. Every commit that added the file must have listed it, so the repository's own one refuses."""
        t = self.target
        self.adopt()
        self.commit("adopted")
        adopted_at = util.git(t, ["rev-parse", "HEAD"])
        write(t, self.TEMPLATE, self.release_bytes(self.TEMPLATE))
        run_git(t, "add", "--", self.TEMPLATE)
        run_git(t, "commit", "-qm", "we add a template of our own")
        run_git(t, "checkout", "-q", "-b", "claim", adopted_at)
        write(t, self.TEMPLATE, self.release_bytes(self.TEMPLATE))
        import hashlib
        plan = json.loads(json.dumps(PLAN))
        self.to_adopt(self.TEMPLATE, "exclude")(plan)
        self.write_plan(plan)
        path = install_mod.install_record_path(t)
        record = util.read_json(path)
        record["managed"] = sorted(record["managed"] + [{"path": self.TEMPLATE, "exec": False, "sha256":
                                   hashlib.sha256(self.release_bytes(self.TEMPLATE)).hexdigest()}],
                                   key=lambda e: e["path"])
        util.write_json(path, record)
        run_git(t, "add", "--", self.TEMPLATE, ".aios/adoption.json", ".aios/install.json")
        env = dict(os.environ, GIT_AUTHOR_DATE="2001-01-01T00:00:00", GIT_COMMITTER_DATE="2001-01-01T00:00:00")
        subprocess.run(["git", "-C", t, "commit", "-qm", "claim it, backdated"], check=True, env=env,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        run_git(t, "checkout", "-q", "main")
        run_git(t, "merge", "-q", "--no-ff", "-m", "merge the pull request", "claim")
        self.assertEqual(len(install_mod._additions(t, self.TEMPLATE)), 2)
        self.forget_state()
        self.refused(self.TEMPLATE)


class ReviewRoundFiftyFive(Existing):
    """Codex, 3.1 round 55: an adoption committed inside a merge commit is anchored too (never read as local
    state); the tools' local caches never overwrite a file the repository tracks, and adoption refuses one;
    and `verify --repo` answers the same on every machine."""

    REL = ".claude/settings.json"  # instance_owned in PLAN, managed in the release
    TEMPLATE = "templates/governance/CODEOWNERS.template"  # managed in the release, excluded in PLAN
    CACHES = (".aios/release_notice.json", ".aios/usage/identity.json")  # the tools' local caches

    def release_bytes(self, rel):
        with open(os.path.join(self.source, rel), "rb") as fh:
            return fh.read()

    def test_an_adoption_committed_inside_a_merge_is_anchored(self):
        import hashlib
        import stat as stat_mod
        t = self.target
        write(t, self.REL, self.release_bytes(self.REL))
        self.commit("ours, the same bytes as the release's")
        before = util.git(t, ["rev-parse", "HEAD"])
        run_git(t, "checkout", "-q", "-b", "side")
        write(t, "06_Clients/acme/side.md", "# side\n")
        run_git(t, "add", "--", "06_Clients/acme/side.md")
        run_git(t, "commit", "-qm", "side work")
        side = util.git(t, ["rev-parse", "HEAD"])
        run_git(t, "checkout", "-q", "main")
        self.adopt()
        run_git(t, "add", "-A")
        tree = util.git(t, ["write-tree"])
        merge = util.git(t, ["commit-tree", tree, "-p", before, "-p", side, "-m", "a merge that brings the adoption"])
        run_git(t, "update-ref", "refs/heads/main", merge)
        self.assertEqual(install_mod._additions(t, ".aios/install.json"), [merge])
        # A pull request widens the plan and reseals the record so it claims the repository's own file.
        plan = json.loads(json.dumps(PLAN))
        plan["instance_owned"].remove(self.REL)
        plan["adopt"].append(self.REL)
        self.write_plan(plan)
        path = install_mod.install_record_path(t)
        record = util.read_json(path)
        with open(os.path.join(t, ".aios/adoption.json"), "rb") as fh:
            plan_bytes = fh.read()
        mode = stat_mod.S_IMODE(os.lstat(os.path.join(t, self.REL)).st_mode)
        record["adoption"] = dict(record["adoption"], adopt=plan["adopt"], instance_owned=plan["instance_owned"],
                                  plan_sha256=hashlib.sha256(plan_bytes).hexdigest(),
                                  created=record["adoption"]["created"] + [
                                      {"path": self.REL, "mode": mode,
                                       "sha256": hashlib.sha256(self.release_bytes(self.REL)).hexdigest()}])
        with open(path, "wb") as fh:
            fh.write(install_mod._record_bytes(install_mod._sealed(record)))
        run_git(t, "add", "--", ".aios/adoption.json", ".aios/install.json")
        run_git(t, "commit", "-qm", "a pull request claims our file for the adoption")
        self.forget_state()
        self.refuses_unchanged(install_mod.rollback, t, self.source)
        self.assertTrue(os.path.isfile(os.path.join(t, self.REL)))

    def test_adoption_refuses_a_tracked_tool_cache(self):
        for rel in self.CACHES:
            write(self.target, rel, '{"ours": true}\n')
        run_git(self.target, "add", "-f", "--", *self.CACHES)
        run_git(self.target, "commit", "-qm", "files of ours at the tools' local paths")
        exc = self.refuses_unchanged(self.adopt)
        said = exc.message + "\n" + "\n".join(exc.details or [])
        for rel in self.CACHES:
            self.assertIn("%s is a file this repository tracks" % rel, said)

    def test_the_tools_never_write_over_a_tracked_cache(self):
        from aioslib import boundary, notice
        # The sandbox turns the notice off, and check() then returns before it reaches the cache (3.1 round 56).
        os.environ.pop("AIOS_NO_RELEASE_NOTICE", None)
        self.addCleanup(os.environ.__setitem__, "AIOS_NO_RELEASE_NOTICE", "1")
        self.adopt()
        self.commit("adopted")
        for rel in self.CACHES:
            write(self.target, rel, '{"ours": true}\n')
        run_git(self.target, "add", "-f", "--", *self.CACHES)
        run_git(self.target, "commit", "-qm", "a pull request commits files at the tools' local paths")
        notice.check(self.target, now=1e9, tags_fn=lambda: [], fetch_fn=lambda ref, v: None)
        self.be("acme-founder")
        boundary._cached_identity(self.target)
        for rel in self.CACHES:
            with open(os.path.join(self.target, rel)) as fh:
                self.assertEqual(fh.read(), '{"ours": true}\n', rel)
        self.assertEqual(util.git(self.target, ["status", "--porcelain"]), "")

    def test_verify_repo_answers_the_same_with_the_note(self):
        """The documented boundary: a path the repository once had and a later upgrade created. Upgrade trusts
        it where the last operation ran; verify --repo reports it on every machine."""
        t = self.target
        write(t, self.TEMPLATE, "# our own template, long ago\n")
        self.commit("a template of ours")
        os.remove(os.path.join(t, self.TEMPLATE))
        self.commit("removed")
        self.adopt()
        self.commit("adopted")
        plan = json.loads(json.dumps(PLAN))
        plan["exclude"].remove("templates/**")
        plan["adopt"].append("templates/**")
        self.write_plan(plan)
        self.commit("adopt the templates too")
        rev = harness.bump_source(self.source, {"START_HERE.md": "# start here\nnew.\n"}, "3.1")
        install_mod.upgrade(t, harness.approve(harness.build_manifest(self.source, rev, "3.1.0")), self.source)
        self.commit("upgraded")
        self.assertTrue(install_mod._vouched_by_note(t))
        problems, _ = install_mod.verify(t, source_repo=self.source)
        self.assertTrue(any(p.startswith(self.TEMPLATE + ": the install record calls it") for p in problems), problems)
        self.assertEqual(install_mod._adopted_ownership_problems(t, install_mod.load_record(t)), [])  # upgrade's view


class ReviewRoundFiftySix(Existing):
    """Codex and the second reviewer, 3.1 round 56: an untouched adoption committed inside a merge commit rolls
    back from a fresh clone; and the tools never read a local cache the repository tracks or reaches through
    a committed link, nor break on one that isn't an object."""

    CACHES = (".aios/release_notice.json", ".aios/usage/identity.json")  # the tools' local caches

    def notice_on(self):
        # The sandbox turns the notice off, and check() then returns before it reaches the cache.
        os.environ.pop("AIOS_NO_RELEASE_NOTICE", None)
        self.addCleanup(os.environ.__setitem__, "AIOS_NO_RELEASE_NOTICE", "1")

    def adopted_inside_a_merge(self):
        t = self.target
        before = util.git(t, ["rev-parse", "HEAD"])
        run_git(t, "checkout", "-q", "-b", "side")
        write(t, "06_Clients/acme/side.md", "# side\n")
        run_git(t, "add", "--", "06_Clients/acme/side.md")
        run_git(t, "commit", "-qm", "side work")
        side = util.git(t, ["rev-parse", "HEAD"])
        run_git(t, "checkout", "-q", "main")
        self.adopt()
        run_git(t, "checkout", "side", "--", "06_Clients/acme/side.md")  # the merge brings the side's work too
        run_git(t, "add", "-A")
        tree = util.git(t, ["write-tree"])
        merge = util.git(t, ["commit-tree", tree, "-p", before, "-p", side, "-m", "a merge that brings the adoption"])
        run_git(t, "update-ref", "refs/heads/main", merge)
        self.assertEqual(util.git(t, ["status", "--porcelain"]), "")
        return merge, side

    def test_an_untouched_adoption_committed_inside_a_merge_rolls_back(self):
        t = self.target
        merge, _ = self.adopted_inside_a_merge()
        added = install_mod._added_in(t, merge)
        self.assertTrue(set(ADOPTED + [".aios/install.json"]) <= added, sorted(added))
        self.assertNotIn("06_Clients/acme/side.md", added)  # the side already had it
        self.forget_state()  # as a fresh clone would be
        self.be("acme-founder")
        code, out, err = self.cli("rollback", "--target", t, "--repo", self.source)
        self.assertEqual(code, 0, out + err)
        for p in ADOPTED:
            self.assertFalse(os.path.lexists(os.path.join(t, p)), p)
        with open(os.path.join(t, "CLAUDE.md")) as fh:
            self.assertIn("OUR OWN brain", fh.read())
        self.assertTrue(os.path.isfile(os.path.join(t, "06_Clients/acme/side.md")))

    def test_a_merge_adds_only_what_no_parent_had(self):
        t = self.target
        merge, side = self.adopted_inside_a_merge()
        self.assertEqual(install_mod._added_in(t, side), {"06_Clients/acme/side.md"})  # one parent: what it added
        self.assertNotIn("06_Clients/acme/side.md", install_mod._added_in(t, merge))  # a parent had it
        self.assertIn(".aios/install.json", install_mod._added_in(t, merge))  # no parent had it
        root = util.git(t, ["rev-list", "--max-parents=0", "HEAD"]).split()[0]
        self.assertIn("CLAUDE.md", install_mod._added_in(t, root))  # a root commit adds every path

    def commit_link_to(self, link_rel, folder_rel, name, content):
        t = self.target
        write(t, os.path.join(folder_rel, name), content)
        os.makedirs(os.path.dirname(os.path.join(t, link_rel)), exist_ok=True)
        os.symlink(os.path.relpath(os.path.join(t, folder_rel), os.path.dirname(os.path.join(t, link_rel))),
                   os.path.join(t, link_rel))
        run_git(t, "add", "-f", "--", folder_rel, link_rel)
        run_git(t, "commit", "-qm", "a pull request links the cache folder to a folder of its own")

    def test_a_committed_link_to_a_malformed_identity_cache_never_lets_an_edit_through(self):
        from aioslib import boundary
        self.adopt()
        self.commit("adopted")
        self.commit_link_to(".aios/usage", "planted", "identity.json", "[1]\n")
        self.be("acme-va")
        allowed, reason = boundary.check_edit(self.target, "Edit", {"file_path": os.path.join(self.target, "CLAUDE.md")})
        self.assertFalse(allowed, reason)
        self.assertIn("acme-va (operator)", reason)
        code, out = boundary.hook_pre_edit(json.dumps({"tool_name": "Edit", "tool_input": {
            "file_path": os.path.join(self.target, "CLAUDE.md")}}), root=self.target)
        self.assertIn('"permissionDecision": "deny"', out or "")
        with open(os.path.join(self.target, "planted/identity.json")) as fh:
            self.assertEqual(fh.read(), "[1]\n")  # and nothing was written through the link

    def test_a_committed_link_to_an_identity_cache_is_never_read(self):
        import time
        from aioslib import boundary
        self.adopt()
        self.commit("adopted")
        self.be("acme-va")
        planted = json.dumps({"login": "acme-founder", "at": time.time(), "gh": boundary._gh_fingerprint()})
        self.commit_link_to(".aios/usage", "planted", "identity.json", planted)
        self.assertEqual(boundary._cached_identity(self.target), "acme-va")
        allowed, reason = boundary.check_edit(self.target, "Edit", {"file_path": os.path.join(self.target, "CLAUDE.md")})
        self.assertFalse(allowed, reason)

    def test_a_tracked_release_notice_cache_is_never_read(self):
        from aioslib import notice
        self.notice_on()
        self.adopt()
        self.commit("adopted")
        installed = install_mod.load_record(self.target)["release"]["version"]
        write(self.target, ".aios/release_notice.json", json.dumps(
            {"installed": installed, "checked_at": 2e9, "complete": True, "line": "a line a pull request wrote"}))
        run_git(self.target, "add", "-f", "--", ".aios/release_notice.json")
        run_git(self.target, "commit", "-qm", "a pull request commits the notice cache")
        self.assertIsNone(notice.check(self.target, now=1e9, tags_fn=lambda: [], fetch_fn=lambda ref, v: None))

    def test_a_cache_that_isnt_an_object_breaks_nothing(self):
        from aioslib import boundary, notice
        self.notice_on()
        self.adopt()
        self.commit("adopted")
        for rel in self.CACHES:
            write(self.target, rel, "[1]\n")  # untracked: this machine's own, but not an object
        self.assertIsNone(notice.check(self.target, now=1e9, tags_fn=lambda: [], fetch_fn=lambda ref, v: None))
        self.be("acme-va")
        self.assertEqual(boundary._cached_identity(self.target), "acme-va")
        allowed, _ = boundary.check_edit(self.target, "Edit", {"file_path": os.path.join(self.target, "CLAUDE.md")})
        self.assertFalse(allowed)
        for rel in self.CACHES:
            self.assertIsInstance(util.read_local_cache(self.target, rel), dict, rel)  # rewritten, as its own


class ReviewRoundFiftySeven(Existing):
    """Codex, 3.1 round 57: a folder this repository records as a submodule (a gitlink) is another repository
    wherever it is, initialized or not. Adoption and upgrade never create a file under one (the parent could
    never commit it), and no tool cache is read from or written into one."""

    def gitlink(self, rel):
        """Record `rel` as a submodule, uninitialized: a gitlink in the index and in HEAD, an empty folder."""
        t = self.target
        sha = util.git(t, ["rev-parse", "HEAD"])
        run_git(t, "update-index", "--add", "--cacheinfo", "160000,%s,%s" % (sha, rel))
        os.makedirs(os.path.join(t, rel), exist_ok=True)
        run_git(t, "commit", "-qm", "%s is a submodule here" % rel)
        self.assertTrue(util.git(t, ["ls-tree", "HEAD", "--", rel]).startswith("160000"))
        self.assertEqual(util.git(t, ["status", "--porcelain"]), "")

    def test_adoption_refuses_a_path_under_an_uninitialized_submodule(self):
        self.gitlink("scripts")  # the plan adopts scripts/team/**
        exc = self.refuses_unchanged(self.adopt)
        self.assertIn("adoption would write through a link, a file in a folder's place, or another repository",
                      exc.message)
        self.assertEqual(exc.details, ["scripts"])
        self.assertFalse(os.path.lexists(os.path.join(self.target, "scripts/team")))

    def test_adoption_refuses_a_submodule_recorded_under_another_case(self):
        self.gitlink("SCRIPTS")  # one folder on a Mac or Windows disk
        exc = self.refuses_unchanged(self.adopt)
        self.assertEqual(exc.details, ["scripts"])

    def test_an_upgrade_refuses_a_path_under_an_uninitialized_submodule(self):
        t = self.target
        self.adopt()
        self.commit("adopted")
        rev = harness.bump_source(self.source, {".claude/skills/new-skill/SKILL.md": "# a new skill\n"}, "3.1")
        manifest = harness.approve(harness.build_manifest(self.source, rev, "3.1.0"))
        self.gitlink(".claude/skills/new-skill")
        # Byte for byte, everything outside .git (backups, lock and state folders included), and git's own view.
        tree, git_view = _tree(t), self.git_view()
        exc = self.refuses_unchanged(install_mod.upgrade, t, manifest, self.source)
        self.assertIn("would write under a link, a file in a folder's place, or another repository", exc.message)
        self.assertEqual(exc.details[0], ".claude/skills/new-skill")
        self.assertEqual(diff(tree, _tree(t)), [])
        self.assertEqual(git_view, self.git_view())
        self.assertFalse(os.path.lexists(os.path.join(t, ".claude/skills/new-skill/SKILL.md")))

    def git_view(self):
        t = self.target
        return (util.git(t, ["rev-parse", "HEAD"]), util.git(t, ["ls-files", "-s"]),
                util.git(t, ["status", "--porcelain", "--ignored", "--untracked-files=all"]))

    def test_an_initialized_submodule_never_supplies_the_identity_cache(self):
        import time
        from aioslib import boundary
        t = self.target
        self.adopt()
        self.commit("adopted")
        self.be("acme-va")
        sub = os.path.join(t, ".aios/usage")
        os.makedirs(sub)
        run_git(sub, "init", "-q", "-b", "main")
        run_git(sub, "config", "user.email", "pr@example.com")
        run_git(sub, "config", "user.name", "pr")
        planted = json.dumps({"login": "acme-founder", "at": time.time(), "gh": boundary._gh_fingerprint()})
        write(sub, "identity.json", planted)
        run_git(sub, "add", "-A")
        run_git(sub, "commit", "-qm", "a planted identity")
        run_git(t, "add", "-f", "--", ".aios/usage")
        run_git(t, "commit", "-qm", "a pull request makes the cache folder a submodule")
        self.assertTrue(util.git(t, ["ls-files", "-s", "--", ".aios/usage"]).startswith("160000"))
        self.assertEqual(boundary._cached_identity(t), "acme-va")
        with open(os.path.join(sub, "identity.json")) as fh:
            self.assertEqual(fh.read(), planted)  # and never written over

    def test_no_tool_cache_is_written_into_an_uninitialized_submodule(self):
        from aioslib import boundary, notice
        t = self.target
        os.environ.pop("AIOS_NO_RELEASE_NOTICE", None)
        self.addCleanup(os.environ.__setitem__, "AIOS_NO_RELEASE_NOTICE", "1")
        self.adopt()
        self.commit("adopted")
        self.gitlink(".aios/usage")
        self.be("acme-va")
        self.assertEqual(boundary._cached_identity(t), "acme-va")
        self.assertFalse(os.path.lexists(os.path.join(t, ".aios/usage/identity.json")))
        notice.check(t, now=1e9, tags_fn=lambda: [], fetch_fn=lambda ref, v: None)
        self.assertTrue(os.path.isfile(os.path.join(t, ".aios/release_notice.json")))  # its own folder: written


def _gitlink(test, root, rel, msg=None):
    """Record `rel` as an uninitialized submodule: a gitlink in the index and HEAD, an empty folder."""
    sha = util.git(root, ["rev-parse", "HEAD"])
    run_git(root, "update-index", "--add", "--cacheinfo", "160000,%s,%s" % (sha, rel))
    os.makedirs(os.path.join(root, rel), exist_ok=True)
    run_git(root, "commit", "-qm", msg or "%s is a submodule here" % rel)
    test.assertTrue(util.git(root, ["ls-tree", "HEAD", "--", rel]).startswith("160000"))


def _git_view(root):
    return (util.git(root, ["rev-parse", "HEAD"]), util.git(root, ["ls-files", "-s"]),
            util.git(root, ["status", "--porcelain", "--ignored", "--untracked-files=all"]))


class ReviewRoundFiftyEightMoves(Layout3):
    """Codex, 3.1 round 58: the 2.x to 3.0 folder move is checked before the first write too, so it never
    moves a file into, or out of, a submodule."""

    def refused_unchanged(self, fn, *args):
        tree, view = _tree(self.target), _git_view(self.target)
        with self.assertRaises(Refusal) as ctx:
            fn(*args)
        self.assertEqual(diff(tree, _tree(self.target)), [])
        self.assertEqual(view, _git_view(self.target))
        return ctx.exception

    def test_a_move_into_an_uninitialized_submodule_is_refused(self):
        write(self.target, "02_Deliverables/private/note.md", "# mine\n")
        self.git_commit("a note of mine")
        _gitlink(self, self.target, "01_Creation/outputs/private")
        exc = self.refused_unchanged(self.up)
        self.assertIn("the folder move would go through a link, a file in a folder's place, or another repository",
                      exc.message)
        self.assertIn("01_Creation/outputs/private", exc.details)

    def test_a_move_out_of_an_uninitialized_submodule_is_refused(self):
        _gitlink(self, self.target, "02_Deliverables/vendor")
        exc = self.refused_unchanged(self.up)
        self.assertIn("02_Deliverables/vendor", exc.details)


class ReviewRoundFiftyEight(Existing):
    """Codex and the second reviewer, 3.1 round 58: no operation writes into another repository, and each
    refuses before its first write: adopt --existing with a submodule at the installer's backups folder,
    plain adopt into an initialized .aios submodule, and a seed line into a file inside one."""

    def test_adopt_existing_refuses_a_backups_submodule_before_anything_changes(self):
        _gitlink(self, self.target, ".aios/backups")
        tree, view = _tree(self.target), _git_view(self.target)
        exc = self.refuses_unchanged(self.adopt)
        self.assertIn(".aios/backups is another repository (a submodule), a link or a file", "\n".join(exc.details))
        self.assertEqual(diff(tree, _tree(self.target)), [])
        self.assertEqual(view, _git_view(self.target))

    def test_a_state_note_that_cant_be_written_takes_the_adoption_back(self):
        from unittest import mock
        before = _tree(self.target)
        with mock.patch.object(install_mod, "_write_state",
                               side_effect=Refusal(util.EXIT_STATE, "the state note can't be written")):
            with self.assertRaises(Refusal):
                self.adopt()
        for p in ADOPTED + [".aios/install.json", ".aios/config.json", ".aios/txn.json"]:
            self.assertFalse(os.path.lexists(os.path.join(self.target, p)), p)
        self.assertEqual(diff(before, _tree(self.target)), [])  # byte for byte, the backups folder included
        self.assertEqual(util.git(self.target, ["status", "--porcelain", "--untracked-files=all"]), "")

    def test_plain_adopt_refuses_an_initialized_aios_submodule_before_writing(self):
        copy = os.path.join(self.tmp, "copy")
        install_mod.install(copy, self.v, self.source, harness.config())
        os.remove(install_mod.install_record_path(copy))
        os.remove(os.path.join(copy, ".aios/config.json"))
        run_git(os.path.join(copy, ".aios"), "init", "-q")  # .aios is another repository now
        tree = _tree(copy)
        with self.assertRaises(Refusal) as ctx:
            install_mod.adopt(copy, self.v, self.source, harness.config())
        self.assertIn("adopt would pin or write files under a link, a file in a folder's place, or another "
                      "repository", ctx.exception.message)
        self.assertEqual(diff(tree, _tree(copy)), [])

    def test_no_seed_line_goes_into_a_file_inside_a_submodule(self):
        t = self.target
        sub = os.path.join(t, "vendor")
        os.makedirs(sub)
        run_git(sub, "init", "-q")
        write(sub, "notes.md", "# theirs\n")
        write(t, "ours.md", "# ours\n")
        self.assertIsNone(install_mod._seed_line_target(t, "vendor/notes.md"))
        self.assertEqual(install_mod._seed_line_target(t, "ours.md"), os.path.join(t, "ours.md"))


# ─── the standing check: nothing written into another repository (3.1 rounds 58 and 59) ──────────────────────


def _make_submodule(root, folder):
    """Make `folder` an uninitialized submodule of the repository at `root`, as a pull request could: its
    tracked files untracked (left on disk), a gitlink in their place, committed."""
    if util.git(root, ["ls-files", "--", folder]):
        run_git(root, "rm", "-r", "-q", "--cached", "--", folder)
    os.makedirs(os.path.join(root, folder), exist_ok=True)
    sha = util.git(root, ["rev-parse", "HEAD"])
    run_git(root, "update-index", "--add", "--cacheinfo", "160000,%s,%s" % (sha, folder))
    run_git(root, "commit", "-qm", "%s is a submodule now" % folder)


def _make_nested_repository(root, folder):
    """Make `folder` a repository inside this one, as a vendored checkout is: a `.git` of its own, and, when this
    repository tracks nothing there, hidden from its status by .git/info/exclude."""
    full = os.path.join(root, folder)
    os.makedirs(full, exist_ok=True)
    run_git(full, "init", "-q")
    if not util.git(root, ["ls-files", "--", folder]):
        with open(os.path.join(root, ".git", "info", "exclude"), "a") as fh:
            fh.write("/%s/\n" % folder)


_REPOSITORY_KINDS = (("a submodule", _make_submodule), ("a nested repository", _make_nested_repository))


class _Writes(object):
    """Every write the code run inside this context makes under `root`, as Python's audit hooks report it
    (audit_writes.py): what actually ran, whatever form its source takes, so a temporary file, a rewrite of the
    same bytes, a mode change, a write through a folder handle and an open reached by getattr all count; and
    each git run whose subcommand writes, by the folder it runs in (independent review, 3.1 rounds 59 and 63)."""

    def __init__(self, root):
        self.root = root
        self.files, self.dirs = set(), set()

    def __enter__(self):
        import audit_writes
        self._recording = audit_writes.Recording().__enter__()
        return self

    def __exit__(self, *exc):
        from test_write_sites import git_kind
        self._recording.__exit__(*exc)
        for rel, is_folder in self._recording.under(self.root):
            (self.dirs if is_folder else self.files).add(rel)
        real_root = os.path.realpath(self.root)
        for argv, where in self._recording.git_dirs():
            real = os.path.realpath(where)
            if git_kind(argv[1:]) and real.startswith(real_root + os.sep):
                self.dirs.add(os.path.relpath(real, real_root).replace(os.sep, "/"))
        return False

    def folders(self):
        """The folder of every path written, and every folder made or removed. Under the installer's backups
        folder, whose snapshot and probe names are new each run, the backups folder and its state folder stand
        for them."""
        out = set()
        for rel, is_dir in [(f, False) for f in self.files] + [(d, True) for d in self.dirs]:
            if rel == ".git" or rel.startswith(".git/"):
                continue
            if rel.startswith(".aios/backups/") or rel == ".aios/backups":
                out.add(".aios/backups/state" if rel.startswith(".aios/backups/state") else ".aios/backups")
                continue
            for folder in ([rel] if is_dir else []) + [os.path.dirname(rel)]:
                if folder and folder != ".":
                    out.add(folder)
        return sorted(out)


def _sweep(test, base, run):
    """Run the operation once on a copy of `base`, recording every folder it writes, creates or removes in; then,
    for each folder and each kind of other repository, on a fresh copy with that folder made one, the operation
    must refuse, name the folder, and leave every file, folder and git's view as they were."""
    probe = os.path.join(test.tmp, "sweep-probe")
    shutil.copytree(base, probe, symlinks=True)
    with _Writes(probe) as writes:
        run(probe)
    folders = writes.folders()
    shutil.rmtree(probe)
    test.assertTrue(folders, "the operation wrote nothing")
    n = 0
    for folder in folders:
        for kind, make in _REPOSITORY_KINDS:
            n += 1
            copy = os.path.join(test.tmp, "sweep-%d" % n)
            shutil.copytree(base, copy, symlinks=True)
            make(copy, folder)
            with test.subTest(folder=folder, kind=kind):
                _check_injected(test, copy, folder, kind, run)
            shutil.rmtree(copy)
    return folders


def _check_injected(test, copy, folder, kind, run):
    """With `folder` already made another repository in `copy`: the operation refuses and names it; the runtime
    audit sees no write inside it, not even one made and taken back before the refusal (a kill at that moment would
    leave it there; independent review, 3.1 rounds 60 and 63); and every file, folder and git's view stay as they
    were, but for a killed run's dead lock, which recovery reclaims by design."""
    tree, view = _tree(copy), _git_view(copy)
    with _Writes(copy) as attempted:
        try:
            run(copy)
        except Refusal as exc:
            said = exc.message + "\n" + "\n".join(str(d) for d in exc.details or [])
            test.assertIn(folder, said, "the refusal doesn't name the folder")
        else:
            test.fail("%s made %s: the operation went ahead" % (folder, kind))
    inside = sorted(p for p in attempted.files | attempted.dirs if p == folder or p.startswith(folder + "/"))
    test.assertEqual(inside, [], "a write was attempted inside the other repository")
    after, now = _tree(copy), _git_view(copy)
    changed = diff(tree, after)
    if ".aios/lock" in changed and ".aios/lock" in tree and ".aios/lock" not in after:
        changed.remove(".aios/lock")
        view, now = _without_lock(view), _without_lock(now)
    test.assertEqual(changed, [], "a refusal changed the workspace")
    test.assertEqual(view, now, "a refusal changed what git sees")


def _without_lock(view):
    head, index, status = view
    return head, index, "\n".join(l for l in status.split("\n") if l[3:] != ".aios/lock")


def _crashed(test, base, name, args, point):
    """A copy of `base` with the real CLI killed at `point` (`@T@` in `args` stands for the copy)."""
    crashed = os.path.join(test.tmp, name)
    shutil.copytree(base, crashed, symlinks=True)
    test.be("acme-founder")
    code, out, err = test.cli(*[crashed if a == "@T@" else a for a in args], env={"AIOS_FAULT": "crash:" + point})
    test.assertEqual(code, 137, out + err)
    return crashed


class SubmoduleSweep(Existing):
    """Chat Zero, 3.1 round 58, and Codex, round 59: by operation, not by path. Each operation that writes runs
    once, recorded, to learn every folder it writes in; then each of those folders, made a submodule and then a
    nested repository in fresh copies, must make it refuse with nothing changed. Each operation with a journal
    is also killed partway and its recovery swept the same way. A new public function in install fails the
    first test until it is swept here (or in SubmoduleSweepMoves) or listed as one that only reads."""

    READ_ONLY = {"install_record_path", "load_record", "journal_path", "load_journal", "verify", "require_verified",
                 "state_fingerprint", "founder_review_notice", "drift_recipe", "load_adoption_plan",
                 "classify_adoption", "adopted_view", "ownership_paths", "ownership_review_notice"}
    SWEPT = {"install", "adopt", "adopt_existing", "upgrade", "upgrade_plan", "rollback", "clear_dead_lock"}

    def test_every_public_operation_is_swept_or_only_reads(self):
        import inspect
        public = {name for name, fn in inspect.getmembers(install_mod, inspect.isfunction)
                  if not name.startswith("_") and fn.__module__ == install_mod.__name__}
        self.assertEqual(public - self.READ_ONLY, self.SWEPT)
        self.assertEqual(public & self.READ_ONLY, self.READ_ONLY)

    def repo(self, name):
        root = os.path.join(self.tmp, name)
        os.makedirs(root)
        run_git(root, "init", "-q", "-b", "main")
        run_git(root, "config", "user.email", "ff@example.com")
        run_git(root, "config", "user.name", "ff")
        write(root, "notes_of_ours.md", "# ours\n")
        run_git(root, "add", "-A")
        run_git(root, "commit", "-qm", "ours")
        return root

    def adopted_base(self, name="adopted-base"):
        base = os.path.join(self.tmp, name)
        shutil.copytree(self.target, base, symlinks=True)
        install_mod.adopt_existing(base, self.v, self.source, harness.config())
        run_git(base, "add", "-A")
        run_git(base, "commit", "-qm", "adopted")
        return base

    def release31(self, extra=None):
        files = {"START_HERE.md": "# start here\nnew.\n"}
        files.update(extra or {})
        rev = harness.bump_source(self.source, files, "3.1")
        return harness.approve(harness.build_manifest(self.source, rev, "3.1.0"))

    def upgraded_base(self):
        base = self.adopted_base("upgraded-base")
        install_mod.upgrade(base, self.release31(), self.source)
        run_git(base, "add", "-A")
        run_git(base, "commit", "-qm", "upgraded")
        return base

    def test_install(self):
        _sweep(self, self.repo("install-base"), lambda r: install_mod.install(r, self.v, self.source, harness.config()))

    def test_plain_adopt(self):
        base = self.repo("adopt-base")
        install_mod.install(base, self.v, self.source, harness.config())
        os.remove(install_mod.install_record_path(base))
        os.remove(os.path.join(base, ".aios/config.json"))
        run_git(base, "add", "-A")
        run_git(base, "commit", "-qm", "a copy of the release, unpinned")
        _sweep(self, base, lambda r: install_mod.adopt(r, self.v, self.source, harness.config()))

    def test_adopt_existing(self):
        _sweep(self, self.target, lambda r: install_mod.adopt_existing(r, self.v, self.source, harness.config()))

    def test_upgrade_of_an_adoption_and_its_dry_run(self):
        base = self.adopted_base()
        v31 = self.release31({".claude/skills/new-skill/SKILL.md": "# a new skill\n"})
        _sweep(self, base, lambda r: install_mod.upgrade(r, v31, self.source))
        with _Writes(base) as writes:  # its dry run writes nothing at all (it has no folder move to probe for)
            install_mod.upgrade_plan(base, v31, self.source)
        self.assertEqual((writes.files, writes.dirs), (set(), set()))

    def test_rollback_undoing_an_adoption(self):
        _sweep(self, self.adopted_base(), lambda r: install_mod.rollback(r, self.source))

    def test_rollback_of_an_upgrade(self):
        _sweep(self, self.upgraded_base(), lambda r: install_mod.rollback(r, self.source))

    def test_clearing_a_dead_lock(self):
        base = self.repo("lock-base")
        write(base, ".aios/lock", "op=install pid=999999\n")  # its holder is gone
        write(base, ".aios/.gitignore", "lock\nbackups/\n")
        run_git(base, "add", "--", ".aios/.gitignore")
        run_git(base, "commit", "-qm", "a dead install's lock, ignored")

        def clear(r):
            self.assertTrue(install_mod.clear_dead_lock(r))
        _sweep(self, base, clear)

    # Recovery: each operation with a journal, killed partway, then its recovery (rollback) swept.

    def recovery(self, crashed):
        _sweep(self, crashed, lambda r: install_mod.rollback(r, self.source))

    def test_recovering_a_killed_adoption(self):
        cfg, rel = self.write_json("org.json", harness.config()), self.write_json("release.json", self.v)
        self.recovery(_crashed(self, self.target, "killed-adoption", ["adopt", "--existing", "--release", rel,
                                                                       "--target", "@T@", "--config", cfg,
                                                                       "--repo", self.source], "adopt.mid_write"))

    def test_recovering_a_killed_upgrade(self):
        base = self.adopted_base()
        rel = self.write_json("release-3.1.json", self.release31({".claude/skills/new-skill/SKILL.md": "# new\n"}))
        self.recovery(_crashed(self, base, "killed-upgrade", ["upgrade", "--release", rel, "--target", "@T@",
                                                              "--repo", self.source], "upgrade.mid_write"))

    def test_finishing_a_killed_rollback_of_an_upgrade(self):
        self.recovery(_crashed(self, self.upgraded_base(), "killed-rollback",
                               ["rollback", "--target", "@T@", "--repo", self.source], "rollback.before_restore"))

    def test_control_a_write_the_scanner_cant_see_is_caught_at_runtime(self):
        """Chat Zero, 3.1 round 63: the runtime audit is the backstop to the static inventory. A write the scanner
        can't read (open and remove reached through getattr), made inside the other repository and taken back before
        the refusal, so the tree ends unchanged, is still caught."""
        import ast as ast_mod
        import builtins
        import inspect
        import textwrap
        from unittest import mock
        import test_write_sites
        copy = os.path.join(self.tmp, "control")
        shutil.copytree(self.upgraded_base(), copy, symlinks=True)
        _make_submodule(copy, "scripts/team")
        real = install_mod._require_state_folder

        def planted(target):
            hidden = os.path.join(target, "scripts", "team", ".planted")
            getattr(builtins, "op" + "en")(hidden, "w").close()
            getattr(os, "re" + "move")(hidden)
            return real(target)
        calls = [n for n in ast_mod.walk(ast_mod.parse(textwrap.dedent(inspect.getsource(planted))))
                 if isinstance(n, ast_mod.Call)]
        self.assertEqual([k for k in (test_write_sites.write_kind(n, {}, "install") for n in calls) if k], [])
        with mock.patch.object(install_mod, "_require_state_folder", planted):
            with self.assertRaises(AssertionError) as ctx:
                _check_injected(self, copy, "scripts/team", "a submodule", lambda r: install_mod.rollback(r, self.source))
        self.assertIn("a write was attempted inside the other repository", str(ctx.exception))
        _check_injected(self, copy, "scripts/team", "a submodule", lambda r: install_mod.rollback(r, self.source))

    def test_finishing_a_killed_undo_of_an_adoption(self):
        self.recovery(_crashed(self, self.adopted_base(), "killed-undo",
                               ["rollback", "--target", "@T@", "--repo", self.source], "adopt.undo_mid"))


class SubmoduleSweepMoves(Layout3):
    """The same sweep for an upgrade with the 2.x to 3.0 folder move, its dry run, its rollback, and each killed
    partway: every folder it moves from or to."""

    def test_upgrade_with_the_folder_move_and_its_dry_run(self):
        folders = _sweep(self, self.target, lambda r: install_mod.upgrade(r, self.v3, self.source, no_vercel=True))
        self.assertIn("01_Creation/outputs", folders)
        _sweep(self, self.target, lambda r: install_mod.upgrade_plan(r, self.v3, self.source, no_vercel=True))

    def moved_base(self):
        base = os.path.join(self.tmp, "moved-base")
        shutil.copytree(self.target, base, symlinks=True)
        install_mod.upgrade(base, self.v3, self.source, no_vercel=True)
        run_git(base, "add", "-A")
        run_git(base, "commit", "-qm", "on 3.0")
        return base

    def test_rollback_of_the_folder_move(self):
        _sweep(self, self.moved_base(), lambda r: install_mod.rollback(r))

    def test_recovering_a_killed_folder_move_and_a_killed_rollback_of_one(self):
        rel = self.write_json("v3.json", self.v3)
        crashed = _crashed(self, self.target, "killed-move", ["upgrade", "--release", rel, "--target", "@T@",
                                                              "--repo", self.source, "--no-vercel"], "layout.mid_moves")
        _sweep(self, crashed, lambda r: install_mod.rollback(r))
        crashed = _crashed(self, self.moved_base(), "killed-move-rollback", ["rollback", "--target", "@T@"],
                           "rollback.before_restore")
        _sweep(self, crashed, lambda r: install_mod.rollback(r))


class ReviewRoundSixtyThree(Existing):
    """Codex, 3.1 round 63: a release pin that is a git option never reaches git. `aios install` and `aios adopt`
    read the release's files before checking the release, so a manifest pinned to `--output=<path>` made
    `git archive` write that file before anything refused."""

    def test_an_option_shaped_pin_never_reaches_git(self):
        outside = os.path.join(self.tmp, "elsewhere", "written-by-git")
        os.makedirs(os.path.dirname(outside))
        manifest = json.loads(json.dumps(self.v))
        manifest["created_from"]["git_rev"] = "--output=" + outside
        rel = self.write_json("release-option.json", manifest)
        cfg = self.write_json("org.json", harness.config())
        self.be("acme-founder")
        for args in (("install", "--release", rel, "--target", os.path.join(self.tmp, "fresh"), "--config", cfg,
                      "--repo", self.source),
                     ("adopt", "--release", rel, "--target", self.target, "--config", cfg, "--repo", self.source)):
            with self.subTest(command=args[0]):
                code, out, err = self.cli(*args)
                self.assertNotEqual(code, 0, out + err)
                self.assertFalse(os.path.lexists(outside), "git wrote %s before the refusal" % outside)
        with self.assertRaises(Refusal):
            list(util.read_tree(self.source, "--output=" + outside))
        self.assertFalse(util.rev_exists(self.source, "--output=" + outside))
        self.assertFalse(os.path.lexists(outside))


OWNERSHIP = [".aios/install.json", ".aios/adoption.json"]


class OwnerDecisionC3(Existing):
    """Owner decision C3 (2026-10-17, #81 6234002893, with A): the ownership list, the install record and an
    adoption's plan, is in the founder lane. An upgrade or the undo trusts that list to say which files are the
    installer's own, so a pull request that changes it needs founder-lane approval, by the same rule as the
    Starter's other sensitive files; and `instance check` fails while a workspace's own policy leaves it open."""

    def shipped_policy(self):
        return util.read_json(os.path.join(harness.REPO_ROOT, ".aios/roles.json"))

    def test_the_shipped_policy_and_code_owner_template_hold_the_ownership_list(self):
        policy = self.shipped_policy()
        self.assertEqual([st for st, _d in governance.ownership_lane_check(policy, OWNERSHIP)], ["PASS", "PASS"])
        with open(os.path.join(harness.REPO_ROOT, "templates/governance/CODEOWNERS.template")) as fh:
            rendered = governance.render(fh.read(), "acme/acme-aios", {
                "REPO_OWNER": ["@acme-founder"], "PRIMARY_REVIEWER": ["@acme-partner"],
                "TECHNICAL_REVIEWER": ["@acme-founder"]})
        results = dict((d.split(" (", 1)[0], st) for st, d in governance.founder_rules_check(
            governance.parse(rendered), policy, {"@acme-founder", "@acme-partner"}, "CODEOWNERS"))
        for path in OWNERSHIP:
            self.assertEqual(results.get("founder lane " + path), "PASS", results)

    def pr_repo(self):
        repo = os.path.join(self.tmp, "pr-repo")
        os.makedirs(repo)
        run_git(repo, "init", "-q", "-b", "main")
        run_git(repo, "config", "user.email", "t@example.com")
        run_git(repo, "config", "user.name", "t")
        write(repo, ".aios/roles.json", json.dumps(self.shipped_policy(), indent=2))
        write(repo, ".aios/config.json", json.dumps(harness.config(), indent=2))
        write(repo, ".aios/install.json", json.dumps({"managed": [{"path": "START_HERE.md"}]}, indent=2))
        write(repo, ".aios/adoption.json", json.dumps(PLAN, indent=2))
        run_git(repo, "add", "-A")
        run_git(repo, "commit", "-qm", "base")
        return repo, util.git(repo, ["rev-parse", "HEAD"])

    def test_a_pull_request_that_edits_the_ownership_list_fails_until_a_founder_approves(self):
        from aioslib import boundary
        repo, base = self.pr_repo()
        for path, claim in ((".aios/install.json", {"managed": [{"path": "START_HERE.md"}, {"path": "CLAUDE.md"}]}),
                            (".aios/adoption.json", dict(PLAN, adopt=PLAN["adopt"] + ["CLAUDE.md"]))):
            run_git(repo, "checkout", "-q", "-B", "pr-" + path.split("/")[-1], base)
            write(repo, path, json.dumps(claim, indent=2))  # claims one of the repository's own files
            run_git(repo, "commit", "-qam", "claim CLAUDE.md for the installer")
            head = util.git(repo, ["rev-parse", "HEAD"])
            for author in ("acme-va", "ff-agents-bot"):  # an operator, and an author the people map doesn't name
                with self.subTest(path=path, author=author):
                    code, lines = boundary.check_pr(repo, base, head, author, [])
                    self.assertEqual(code, util.EXIT_ROLE, lines)
                    self.assertIn("  - " + path, lines)
                    code, lines = boundary.check_pr(repo, base, head, author, ["acme-founder"])
                    self.assertEqual(code, util.EXIT_OK, lines)

    def test_claude_will_not_edit_the_ownership_list_for_an_operator(self):
        from aioslib import boundary
        repo, _base = self.pr_repo()
        for path in OWNERSHIP:
            allowed, reason = boundary.check_edit(repo, "Write", {"file_path": os.path.join(repo, path)},
                                                  identify=lambda _r: "acme-va")
            self.assertFalse(allowed, path)
            self.assertIn("founder lane", reason)
            allowed, _reason = boundary.check_edit(repo, "Write", {"file_path": os.path.join(repo, path)},
                                                   identify=lambda _r: "acme-founder")
            self.assertTrue(allowed, path)

    def instance_check(self):
        return self.cli("instance", "check", "--offline", "--target", self.target, "--repo-slug", "acme/acme-aios")

    def test_instance_check_fails_while_the_instances_own_policy_leaves_the_list_open(self):
        write(self.target, ".github/CODEOWNERS", "# aios-codeowners-for: acme/acme-aios\n"
                                                 "/.github/   @acme-founder\n/CLAUDE.md  @acme-founder\n")
        self.commit("our CODEOWNERS")
        self.adopt()
        code, out, err = self.instance_check()
        for path in OWNERSHIP:
            self.assertIn("FAIL  founder   ownership list %s: the role policy lets operator change it" % path,
                          out, out + err)
        self.assertIn("FOUNDER REVIEW IS NOT IN FORCE", out)
        self.assertNotEqual(code, 0)
        # The instance puts the list in its own lane, with a code owner for each: both lines pass.
        policy = json.loads(json.dumps(FF_ROLES))
        policy["roles"]["operator"]["paths_denied"] += OWNERSHIP
        write(self.target, ".aios/roles.json", json.dumps(policy, indent=2))
        with open(os.path.join(self.target, ".github/CODEOWNERS"), "a") as fh:
            fh.write("/.aios/install.json  @acme-founder\n/.aios/adoption.json  @acme-founder\n")
        code, out, err = self.instance_check()
        for path in OWNERSHIP:
            self.assertIn("PASS  founder   ownership list %s" % path, out, out + err)
            self.assertIn("PASS  founder   founder lane %s (.github/CODEOWNERS)" % path, out, out + err)
        self.assertNotIn("ownership list .aios/install.json: the role policy lets", out)

    def test_an_adoption_with_its_own_plan_path_needs_that_path_in_the_lane(self):
        write(self.target, "ops/our_plan.json", json.dumps(PLAN, indent=2))
        os.remove(os.path.join(self.target, ".aios/adoption.json"))
        policy = json.loads(json.dumps(FF_ROLES))
        policy["roles"]["operator"]["paths_denied"] += OWNERSHIP
        write(self.target, ".aios/roles.json", json.dumps(policy, indent=2))
        self.commit("our plan lives elsewhere")
        record = self.adopt(plan_rel="ops/our_plan.json")
        self.assertEqual(install_mod.ownership_paths(record), [".aios/install.json", "ops/our_plan.json"])
        failed = [d for st, d in governance.founder_review_local(
            self.target, policy, harness.config(), (), install_mod.ownership_paths(record)) if st == "FAIL"]
        self.assertTrue(any(d.startswith("ownership list ops/our_plan.json:") for d in failed), failed)
        self.assertFalse(any(d.startswith("ownership list .aios/install.json:") for d in failed), failed)

    def test_a_plain_install_lists_only_its_record(self):
        self.assertEqual(install_mod.ownership_paths({"managed": []}), [".aios/install.json"])

    def commit_in_git_only(self, repo, path, text):
        """A commit adding `path` to git without touching the disk: on a Mac a case variant of a file that's there
        would otherwise just rewrite that file."""
        blob = subprocess.run(["git", "-C", repo, "hash-object", "-w", "--stdin"], input=text.encode(),
                              stdout=subprocess.PIPE, check=True).stdout.decode().strip()
        run_git(repo, "update-index", "--add", "--cacheinfo", "100644,%s,%s" % (blob, path))
        run_git(repo, "commit", "-qm", "add %s" % path)
        return util.git(repo, ["rev-parse", "HEAD"])

    def test_a_case_or_windows_spelling_of_a_lane_path_is_that_path(self):
        from aioslib import boundary
        repo, base = self.pr_repo()
        claim = json.dumps({"managed": [{"path": "CLAUDE.md"}]})
        for path in (".AIOS/Install.json", ".aios/install.json.", ".aios/install.json :x", ".aios/INSTAL~1.JSO",
                     "ſcripts/aios/aios.py", ".Claude/settings.json"):
            with self.subTest(path=path):
                run_git(repo, "checkout", "-q", "-f", "-B", "variant", base)
                head = self.commit_in_git_only(repo, path, claim)
                code, lines = boundary.check_pr(repo, base, head, "acme-va", [])
                self.assertEqual(code, util.EXIT_ROLE, lines)
                self.assertIn("  - " + path, lines)
                allowed, _reason = boundary.check_edit(repo, "Write", {"file_path": os.path.join(repo, path)},
                                                       identify=lambda _r: "acme-va")
                self.assertFalse(allowed, path)

    def test_the_folded_match_stays_exact_about_other_names(self):
        lane = OWNERSHIP + ["scripts/aios/**"]
        for path in (".aios/install.json.bak", ".aios/installs.json", ".aios/x/install.json", "docs/aios/x.md",
                     "scripts/aiosx/y.py"):
            self.assertFalse(util.lane_match(lane, path), path)
        for path in (".AIOS/INSTALL.JSON", ".aios\\install.json", "/.aios/install.json", "Scripts/AIOS/x.py",
                     "scripts/aios.", "scripts/PROGRA~1/x"):
            self.assertTrue(util.lane_match(lane, path), path)
        self.assertFalse(util.lane_match([], ".aios/INSTAL~1.JSO"))

    def cli_upgrade(self, version):
        rev = harness.bump_source(self.source, {"START_HERE.md": "# start here\n%s.\n" % version}, version)
        rel = self.write_json("release-%s.json" % version, harness.approve(
            harness.build_manifest(self.source, rev, version)))
        self.be("acme-founder")
        return self.cli("upgrade", "--release", rel, "--target", self.target, "--repo", self.source)

    def test_the_upgrade_says_when_the_ownership_list_still_needs_founder_review(self):
        write(self.target, ".github/CODEOWNERS", "# aios-codeowners-for: acme/acme-aios\n/.github/   @acme-founder\n")
        self.commit("our CODEOWNERS")
        self.adopt()
        self.commit("adopted")
        code, out, err = self.cli_upgrade("3.1.0")
        self.assertEqual(code, 0, out + err)
        self.assertIn("NEXT:     founder review: the ownership list (.aios/install.json, .aios/adoption.json)", out)
        # Once the instance holds the list (its policy and a CODEOWNERS rule for each), the upgrade says nothing.
        install_mod.rollback(self.target, self.source)
        policy = json.loads(json.dumps(FF_ROLES))
        policy["roles"]["operator"]["paths_denied"] += OWNERSHIP
        write(self.target, ".aios/roles.json", json.dumps(policy, indent=2))
        with open(os.path.join(self.target, ".github/CODEOWNERS"), "a") as fh:
            fh.write("/.aios/install.json  @acme-founder\n/.aios/adoption.json  @acme-founder\n")
        self.commit("the ownership list in our lane")
        self.assertEqual(install_mod.ownership_review_notice(self.target, install_mod.load_record(self.target)), [])
        code, out, err = self.cli_upgrade("3.1.1")
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("ownership list", out)


class ReviewRoundSixtySix(Existing):
    """Codex, 3.1 round 66: the upgrade's NEXT notice judged the ownership list by the founder-review lines that
    name one of its paths, so a workspace with no CODEOWNERS file at all, whose one failure names no path, got no
    notice after upgrading."""

    def held_policy(self):
        policy = json.loads(json.dumps(FF_ROLES))
        policy["roles"]["operator"]["paths_denied"] += OWNERSHIP
        write(self.target, ".aios/roles.json", json.dumps(policy, indent=2))
        return policy

    def test_no_codeowners_file_still_gets_the_notice(self):
        self.held_policy()
        self.commit("the list in our lane, but no CODEOWNERS file")
        self.assertFalse(os.path.lexists(os.path.join(self.target, ".github/CODEOWNERS")))
        record = self.adopt()
        self.assertTrue(install_mod.ownership_review_notice(self.target, record))
        self.commit("adopted")
        rev = harness.bump_source(self.source, {"START_HERE.md": "# start here\n3.1.0.\n"}, "3.1.0")
        rel = self.write_json("release-3.1.0.json", harness.approve(harness.build_manifest(self.source, rev, "3.1.0")))
        self.be("acme-founder")
        code, out, err = self.cli("upgrade", "--release", rel, "--target", self.target, "--repo", self.source)
        self.assertEqual(code, 0, out + err)
        self.assertIn("NEXT:     founder review: the ownership list (.aios/install.json, .aios/adoption.json)", out)

    def test_held_means_a_founder_rule_for_every_path(self):
        policy = self.held_policy()
        config = harness.config()
        paths = install_mod.ownership_paths({"adoption": {"plan": ".aios/adoption.json"}})
        for codeowners, held in (
                (None, False),
                ("/.aios/install.json @acme-founder\n", False),                      # the plan has no rule
                ("/.aios/install.json @acme-founder\n/.aios/adoption.json @acme-va\n", False),  # not a founder
                ("/.aios/ @acme-founder\n", True),                                     # one folder rule covers both
                ("/.aios/ @acme-founder\n/.aios/*.json @acme-va\n", False),             # a later rule takes them
                ("/.aios/install.json @acme-founder\n/.aios/adoption.json @acme-founder\n", True)):
            with self.subTest(codeowners=codeowners):
                path = os.path.join(self.target, ".github/CODEOWNERS")
                if codeowners is None:
                    if os.path.lexists(path):
                        os.remove(path)
                else:
                    write(self.target, ".github/CODEOWNERS", "# aios-codeowners-for: acme/acme-aios\n" + codeowners)
                self.assertEqual(governance.ownership_held(self.target, policy, config, paths), held)
        open_policy = json.loads(json.dumps(FF_ROLES))  # the rules are there, the policy leaves the list open
        self.assertFalse(governance.ownership_held(self.target, open_policy, config, paths))
        no_founder = harness.config(people=[{"github": "acme-va", "role": "operator", "display_name": "V"}])
        self.assertFalse(governance.ownership_held(self.target, policy, no_founder, paths))


class ReviewRoundSixtySeven(Sandbox):
    """Codex, 3.1 round 67: on a plain install the record names no plan, so the upgrade's NEXT notice looked at the
    record alone, while the upgraded policy keeps the default plan path in the founder lane and `instance check`
    wants a founder rule for it. CODEOWNERS covering only the record got no notice and a failing instance check."""

    def setUp(self):
        super(ReviewRoundSixtySeven, self).setUp()
        policy = json.loads(json.dumps(harness.ROLES))
        policy["roles"]["operator"]["paths_denied"] += OWNERSHIP  # as the Starter's own policy has it from 3.1
        rev = harness.bump_source(self.source, {".aios/roles.json": json.dumps(policy, indent=2)}, "the list in the lane")
        install_mod.install(self.target, harness.approve(harness.build_manifest(self.source, rev, "3.0.0")),
                            self.source, harness.config())
        run_git(self.target, "init", "-q", "-b", "main")
        run_git(self.target, "config", "user.email", "client@example.com")
        run_git(self.target, "config", "user.name", "client")
        self.codeowners("/.github/ @acme-founder\n/.aios/install.json @acme-founder\n")  # the record only

    def codeowners(self, rules):
        write(self.target, ".github/CODEOWNERS", "# aios-codeowners-for: acme/acme-aios\n" + rules)
        run_git(self.target, "add", "-A")
        run_git(self.target, "commit", "-qm", "our CODEOWNERS")

    def upgrade(self, version):
        rev = harness.bump_source(self.source, {"START_HERE.md": "# start here\n%s.\n" % version}, version)
        rel = self.write_json("release-%s.json" % version, harness.approve(harness.build_manifest(self.source, rev, version)))
        self.be("acme-founder")
        return self.cli("upgrade", "--release", rel, "--target", self.target, "--repo", self.source)

    def test_a_plain_install_hears_about_the_plan_path_its_lane_holds(self):
        self.assertEqual(install_mod.ownership_paths(install_mod.load_record(self.target)), [".aios/install.json"])
        code, out, err = self.upgrade("3.1.0")
        self.assertEqual(code, 0, out + err)
        self.assertIn("NEXT:     founder review: the ownership list (.aios/install.json, .aios/adoption.json)", out)
        code, out, _err = self.cli("instance", "check", "--offline", "--target", self.target, "--repo-slug", "acme/acme-aios")
        self.assertIn("FAIL  founder   founder lane .aios/adoption.json (.github/CODEOWNERS): no rule covers it", out)
        # With a rule for the plan path too, the notice and instance check agree: nothing about the list.
        run_git(self.target, "add", "-A")
        run_git(self.target, "commit", "-qm", "upgraded")
        self.codeowners("/.github/ @acme-founder\n/.aios/install.json @acme-founder\n/.aios/adoption.json @acme-founder\n")
        self.assertEqual(install_mod.ownership_review_notice(self.target, install_mod.load_record(self.target)), [])
        code, out, _err = self.cli("instance", "check", "--offline", "--target", self.target, "--repo-slug", "acme/acme-aios")
        self.assertFalse([l for l in out.splitlines() if "FAIL" in l and ".aios/" in l and "founder" in l], out)

    def test_a_lane_path_needs_only_its_code_owner_as_instance_check_judges_it(self):
        # A further role that may change the plan path: instance check doesn't require it of a plain install, and
        # neither does the notice once CODEOWNERS covers both paths.
        policy = util.read_json(os.path.join(self.target, ".aios/roles.json"))
        policy["roles"]["reviewer"] = {"entries": ["operator"], "lifecycle": [], "paths_denied": [".aios/install.json"]}
        self.codeowners("/.github/ @acme-founder\n/.aios/install.json @acme-founder\n/.aios/adoption.json @acme-founder\n")
        config = harness.config()
        record = install_mod.load_record(self.target)
        self.assertTrue(governance.ownership_held(self.target, policy, config, [".aios/install.json"],
                                                 [".aios/adoption.json"]))
        self.assertFalse(governance.ownership_held(self.target, policy, config, [".aios/install.json",
                                                                                 ".aios/adoption.json"]))
        self.assertEqual(install_mod.ownership_paths(record), [".aios/install.json"])

    def test_the_notice_and_instance_check_agree_in_both_directions(self):
        record = install_mod.load_record(self.target)
        base = util.read_json(os.path.join(self.target, ".aios/roles.json"))
        literal = json.loads(json.dumps(base))
        folder = json.loads(json.dumps(base))
        folder["roles"]["operator"]["paths_denied"] = [p for p in base["roles"]["operator"]["paths_denied"]
                                                       if p not in OWNERSHIP] + [".aios/**"]
        bare = json.loads(json.dumps(harness.ROLES))  # the list left out of the lane altogether
        for name, policy in (("literal", literal), ("folder", folder), ("bare", bare)):
            for rules in ("/.github/ @acme-founder\n",
                          "/.github/ @acme-founder\n/.aios/install.json @acme-founder\n",
                          "/.github/ @acme-founder\n/.aios/install.json @acme-founder\n/.aios/adoption.json @acme-founder\n",
                          "/.github/ @acme-founder\n/.aios/ @acme-founder\n",
                          "/.github/ @acme-founder\n/.aios/ @acme-founder\n/.aios/*.json @acme-va\n"):
                with self.subTest(policy=name, rules=rules):
                    write(self.target, ".aios/roles.json", json.dumps(policy, indent=2))
                    write(self.target, ".github/CODEOWNERS", "# aios-codeowners-for: acme/acme-aios\n" + rules)
                    lines = governance.founder_review_local(self.target, policy, harness.config(), (),
                                                            install_mod.ownership_paths(record))
                    entries = [g for g in governance.founder_lane_paths(policy)
                               if any(util.lane_match([g], p) for p in OWNERSHIP)]
                    failing = [d for st, d in lines if st == "FAIL" and (
                        d.startswith("ownership list ") or any(d.startswith("founder lane %s (" % g) for g in entries))]
                    notice = install_mod.ownership_review_notice(self.target, record)
                    self.assertEqual(bool(notice), bool(failing), (notice, failing))


class NoBytecodeBesideThePackage(Sandbox):
    """GitHub's runs of 3.1 rounds 62 to 68: on a Python that writes bytecode beside the source (a Linux runner's), the
    CLI left scripts/aios/aioslib/__pycache__ in the repository it ran from, a Starter clone included, which the
    runtime audit rightly counts as a write into another repository. macOS's own python3 keeps its cache elsewhere
    (under ~/Library/Caches), so no run on a Mac showed it. Judged by where this interpreter would cache each module,
    so the check means the same on both."""

    def copy(self, name):
        pkg = os.path.join(self.tmp, name, "scripts", "aios")
        shutil.copytree(harness.AIOS_DIR, pkg, ignore=shutil.ignore_patterns("__pycache__"))
        return pkg

    def caches(self, pkg):
        import importlib.util
        sources = [os.path.join(pkg, "aios.py")] + [os.path.join(pkg, "aioslib", f)
                                                     for f in os.listdir(os.path.join(pkg, "aioslib"))
                                                     if f.endswith(".py")]
        found = [importlib.util.cache_from_source(src) for src in sources]
        for path in found:  # a cache this test makes outside its folder is removed with it
            self.addCleanup(lambda p=path: os.path.isfile(p) and os.remove(p))
        return [p for p in found if os.path.isfile(p)]

    def run_py(self, code, *args):
        env = {k: v for k, v in os.environ.items() if k != "PYTHONDONTWRITEBYTECODE"}
        return subprocess.run([sys.executable, "-c", code] + list(args), stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, env=env, cwd=self.tmp)

    def test_the_cli_writes_no_bytecode_cache_where_python_would(self):
        # The control: this interpreter, told to write bytecode, caches a plain import of the package.
        control = self.copy("control")
        self.caches(control)
        proc = self.run_py("import sys; sys.dont_write_bytecode = False; sys.path.insert(0, sys.argv[1]); "
                           "import aioslib.install", control)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(self.caches(control), "the control cached nothing, so the test below would prove nothing")
        # The CLI under the same setting, every module of the package imported: no cache for any of them.
        pkg = self.copy("starter")
        self.caches(pkg)
        proc = self.run_py("import runpy, sys; sys.dont_write_bytecode = False; path = sys.argv[1]; "
                           "sys.argv = [path, 'instance', 'check', '--help']; runpy.run_path(path, run_name='__main__')",
                           os.path.join(pkg, "aios.py"))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(b"instance", proc.stdout)
        self.assertEqual(self.caches(pkg), [])
        self.assertEqual([d for d, _s, _f in os.walk(os.path.join(self.tmp, "starter")) if "__pycache__" in d], [])
