"""Starter 3.0: the 2.x to 3.0 folder move, its refusals, its recovery and its rollback.

Founder rulings this pins (2026-10-14): one repository with phase folders; preserve every
client-owned file; prove migration and rollback; refuse a website move until Vercel is corrected
and verified (R-A); one declared map line in CLAUDE.md, shown in the dry run, never duplicated,
taken back exactly (R-B); `instance check` fails visibly until founder review is restored at the
new paths (R-C). And the proof bar: existing destinations, case-insensitive collisions,
interrupted moves, and exact rollback against the actual pre-upgrade snapshot.

Every "nothing changed" claim below is checked against a full snapshot of the workspace: every
file's bytes, size and mode, every folder (empty ones included), and git's own status with
ignored files. Not against a committed state, and not against the installer's own fingerprint.

Run: python3 -m unittest discover -s tests/aios -v
"""

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import threading
import unicodedata
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import harness
from harness import Sandbox, run_git, write

sys.path.insert(0, harness.AIOS_DIR)

from aioslib import governance, install as install_mod, layout as layout_mod, release, util  # noqa: E402
from aioslib.util import EXIT_STATE, Refusal  # noqa: E402

REAL_SPEC = util.read_json(os.path.join(harness.REPO_ROOT, "release", "package_spec.json"))
LAYOUT = REAL_SPEC["layout"]
MAP_LINE = "@00_AIOS/routing.md"
CORE_LINE = "@.aios/operator_core/OPERATOR_CORE.md"

V3_SPEC = {
    "schema": "ff-aios-starter/package-spec@1",
    "exclude": ["evidence/**", "releases/**", "release/**", "tests/**", ".github/CODEOWNERS"],
    "seed": ["CLAUDE.md", "README.md", ".gitignore", "00_AIOS/**", "01_Creation/**", "02_Team_Ops/**",
             "03_RevOps/**", "04_Attention/**", "05_Jobs/**", "99_Archive/**"],
    "client_owned": [".claude/settings.local.json"],
    "seed_lines": [{"path": "CLAUDE.md", "line": MAP_LINE}],
    "layout": LAYOUT,
}


def snapshot(root, backups=None):
    """Everything a person could notice: files (bytes, size, mode), folders, links, git status
    with ignored files.

    One thing is set aside, and only one: the installer's own git-ignored record of an upgrade
    attempt, `.aios/backups/<attempt>/`, which rollback keeps on purpose (it holds the plan and the
    proof). `backups` names the attempts that existed before; those stay in the snapshot, so a
    change to an older backup is still caught.
    """
    keep = set(backups or ())
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root).replace(os.sep, "/")
        dirnames[:] = sorted(d for d in dirnames if not (rel_dir == "." and d == ".git")
                             and not (rel_dir == ".aios/backups" and d not in keep))
        for d in dirnames:
            rel = d if rel_dir == "." else rel_dir + "/" + d
            if rel == ".aios/backups":
                continue  # the container of the set-aside record; its kept children are listed
            out[rel + "/"] = ("dir",)
        for name in filenames:
            rel = name if rel_dir == "." else rel_dir + "/" + name
            if rel in (".aios/lock",):
                continue
            full = os.path.join(root, rel)
            st = os.lstat(full)
            if stat.S_ISLNK(st.st_mode):
                out[rel] = ("link", os.readlink(full))
                continue
            with open(full, "rb") as fh:
                digest = hashlib.sha256(fh.read()).hexdigest()
            out[rel] = ("file", digest, st.st_size, stat.S_IMODE(st.st_mode))
    if os.path.isdir(os.path.join(root, ".git")):
        status = subprocess.run(["git", "-C", root, "status", "--porcelain", "--ignored",
                                 "--untracked-files=all"], stdout=subprocess.PIPE).stdout
        out["<git status>"] = "\n".join(
            line for line in status.decode("utf-8", "replace").splitlines()
            if not (line.startswith("!! .aios/backups/")
                    and line[len("!! .aios/backups/"):].split("/", 1)[0] not in keep))
        out["<git HEAD>"] = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"],
                                           stdout=subprocess.PIPE).stdout.decode().strip()
    return out


def diff(a, b):
    keys = sorted(set(a) | set(b))
    return [k for k in keys if a.get(k) != b.get(k)]


def bump_to_v3(source, spec=None, roles_path="00_AIOS/company/offer_economics/**", extra=None):
    """The fixture's 3.0: the starter's own seeds at their 3.0 paths, a new seed or two, the
    folder map in the spec, and the founder lane at its new path, with the ownership list in it, as the
    Starter's role policy has it from 3.1 (owner decision C3)."""
    run_git(source, "rm", "-q", "-r", "--ignore-unmatch", "01_Foundations", "06_Communication", "07_Setup")
    roles = json.loads(json.dumps(harness.ROLES))
    roles["roles"]["operator"]["paths_denied"] = [roles_path, ".github/**", ".aios/install.json", ".aios/adoption.json"]
    files = {
        "00_AIOS/company/market_analysis/_workspace.md": "# market\n",
        "00_AIOS/decisions_log.md": "# decisions\n",
        "00_AIOS/routing.md": "# routing\nthe new map.\n",
        "02_Team_Ops/projects/README.md": "# projects\n",
        "04_Attention/content/.gitkeep": "",
        "CLAUDE.md": "# Your AIOS\nyours to shape.\n\n%s\n" % MAP_LINE,
        ".aios/roles.json": json.dumps(roles, indent=2),
        "release/package_spec.json": json.dumps(spec or V3_SPEC, indent=2),
        "START_HERE.md": "# start here\nthe 3.0 folders.\n",
    }
    files.update(extra or {})
    return harness.bump_source(source, files, "3.0")


class Layout3(Sandbox):
    """A 2.x workspace with a realistic spread of the client's own content, then 3.0."""

    def setUp(self):
        super(Layout3, self).setUp()
        # 2.x ships one managed file inside an old folder, like 07_Setup's walkthroughs.
        self.rev2 = harness.bump_source(self.source, {"07_Setup/walkthrough.md": "# setup\n"})
        self.v2 = harness.approve(harness.build_manifest(self.source, self.rev2, "2.10.0"))
        self.rev2_recorded = util.git(self.source, ["rev-parse", "HEAD"])  # the pin plus its record
        install_mod.install(self.target, self.v2, self.source, harness.config())
        self.client_content()
        self.git_commit("2.10.0 and my work")
        rev3 = bump_to_v3(self.source)
        self.v3 = harness.approve(harness.build_manifest(self.source, rev3, "3.0.0",
                                                         min_upgrade_from="2.6.0"))

    def client_content(self):
        t = self.target
        write(t, "01_Foundations/market_analysis/_workspace.md", "MY MARKET, edited\n")  # edited seed
        write(t, "01_Foundations/offer_economics/pricing.md", "# price\n$1\n")
        write(t, "02_Deliverables/copy/my_ad.md", "my ad\n")
        write(t, "02_Deliverables/report.md", "my report\n")
        write(t, "02_Deliverables/café menu.md", "unicode name\n")
        write(t, "05_Assets/logo.bin", bytes(range(256)) * 8)
        os.chmod(os.path.join(t, "05_Assets/logo.bin"), 0o755)
        write(t, "11_Projects/notes/plan.md", "# my plan\n")
        write(t, "11_Projects/notes/.env", "SECRET_THING=not-a-real-value\n")  # git-ignored
        write(t, ".gitignore", ".env\n")
        os.makedirs(os.path.join(t, "02_Deliverables/empty_drafts"))
        os.makedirs(os.path.join(t, "my_empty_folder"))  # outside every old folder
        write(t, "01_Foundations/.DS_Store", b"\x00\x01junk")
        write(t, "CLAUDE.md", "# Your AIOS\nMY HOUSE RULE: invoices on Fridays.\n")
        # The client deleted one starter seed: it must not come back under its 3.0 name.
        os.remove(os.path.join(t, "06_Communication/decisions_log.md"))

    def git_commit(self, msg):
        t = self.target
        if not os.path.isdir(os.path.join(t, ".git")):
            run_git(t, "init", "-q", "-b", "main")
            run_git(t, "config", "user.email", "client@example.com")
            run_git(t, "config", "user.name", "client")
            run_git(t, "remote", "add", "origin", "https://github.com/acme/acme-aios.git")
        run_git(t, "add", "-A")
        run_git(t, "commit", "-qm", msg)

    NO_VERCEL = True  # a repository not deployed by Vercel, unless a test says otherwise

    def up(self, manifest=None, no_vercel=None):
        return install_mod.upgrade(self.target, manifest or self.v3, self.source,
                                   no_vercel=self.NO_VERCEL if no_vercel is None else no_vercel)

    def read(self, rel, mode="r"):
        with open(os.path.join(self.target, rel), mode) as fh:
            return fh.read()

    def refuses_unchanged(self, fn, *args):
        before = snapshot(self.target)
        with self.assertRaises(Refusal) as ctx:
            fn(*args)
        self.assertEqual(diff(before, snapshot(self.target)), [], "a refusal changed the workspace")
        return ctx.exception


class Migration(Layout3):

    def test_every_client_file_lands_at_its_new_path_with_its_bytes(self):
        before = snapshot(self.target)
        record = self.up()
        after = snapshot(self.target)
        expect = {
            "01_Foundations/market_analysis/_workspace.md": "00_AIOS/company/market_analysis/_workspace.md",
            "01_Foundations/offer_economics/pricing.md": "00_AIOS/company/offer_economics/pricing.md",
            "02_Deliverables/copy/my_ad.md": "01_Creation/outputs/copy/my_ad.md",
            "02_Deliverables/report.md": "01_Creation/outputs/report.md",
            "02_Deliverables/café menu.md": "01_Creation/outputs/café menu.md",
            "05_Assets/logo.bin": "01_Creation/asset_library/logo.bin",
            "11_Projects/notes/plan.md": "02_Team_Ops/projects/notes/plan.md",
            "11_Projects/notes/.env": "02_Team_Ops/projects/notes/.env",
        }
        for old, new in expect.items():
            self.assertNotIn(old, after, old)
            self.assertEqual(before[old], after[new], "%s changed bytes, size or mode" % old)
        self.assertEqual(after["02_Team_Ops/projects/notes/.env"], before["11_Projects/notes/.env"])
        self.assertEqual(self.read("00_AIOS/company/market_analysis/_workspace.md"), "MY MARKET, edited\n")
        self.assertEqual(record["layout"], "3")
        self.assertEqual(record["layout_migration"]["moved"], len(record_moves(self.target, record)))
        for d in layout_mod.OLD_FOLDERS:
            self.assertFalse(os.path.lexists(os.path.join(self.target, d)), d)

    def test_no_starter_file_is_refreshed_and_a_deleted_one_stays_deleted(self):
        self.up()
        # the release's 3.0 copy is "# market\n"; the client's edited copy wins
        self.assertEqual(self.read("00_AIOS/company/market_analysis/_workspace.md"), "MY MARKET, edited\n")
        self.assertFalse(os.path.exists(os.path.join(self.target, "00_AIOS/decisions_log.md")))
        # brand-new 3.0 starter files do arrive
        self.assertEqual(self.read("02_Team_Ops/projects/README.md"), "# projects\n")
        self.assertEqual(self.read("00_AIOS/routing.md"), "# routing\nthe new map.\n")

    def test_empty_folders_move_and_unrelated_empty_folders_survive(self):
        self.up()
        self.assertTrue(os.path.isdir(os.path.join(self.target, "01_Creation/outputs/empty_drafts")))
        self.assertTrue(os.path.isdir(os.path.join(self.target, "my_empty_folder")))

    def test_junk_is_set_aside_not_moved(self):
        record = self.up()
        backup = record["previous"]["backup"]
        self.assertFalse(os.path.lexists(os.path.join(self.target, "00_AIOS/company/.DS_Store")))
        kept = os.path.join(self.target, backup, "quarantine", "01_Foundations", ".DS_Store")
        self.assertEqual(open(kept, "rb").read(), b"\x00\x01junk")

    def test_the_proof_file_lists_every_move_with_its_hash(self):
        record = self.up()
        proof = util.read_json(os.path.join(self.target, record["layout_migration"]["proof"]))
        for m in proof["moved"]:
            with open(os.path.join(self.target, m["to"]), "rb") as fh:
                self.assertEqual(hashlib.sha256(fh.read()).hexdigest(), m["sha256"], m["to"])
        self.assertIn({"from": "02_Deliverables/report.md", "to": "01_Creation/outputs/report.md",
                       "sha256": hashlib.sha256(b"my report\n").hexdigest(), "size": 10}, proof["moved"])

    def test_the_old_managed_file_in_an_old_folder_is_retired_not_moved(self):
        self.up()
        self.assertFalse(os.path.exists(os.path.join(self.target, "99_Archive/07_Setup/walkthrough.md")))

    def test_the_workspace_verifies_and_git_sees_renames(self):
        self.up()
        problems, _ = install_mod.verify(self.target)
        self.assertEqual(problems, [])
        run_git(self.target, "add", "-A")
        out = subprocess.run(["git", "-C", self.target, "diff", "--cached", "-M", "--name-status"],
                             stdout=subprocess.PIPE).stdout.decode()
        self.assertIn("01_Foundations/offer_economics/pricing.md\t00_AIOS/company/offer_economics/pricing.md",
                      out)

    def test_stale_references_are_reported_never_rewritten(self):
        write(self.target, "02_Deliverables/links.md", "see 01_Foundations/offer_economics\n")
        self.git_commit("a note naming an old folder")
        record = self.up()
        self.assertIn("01_Creation/outputs/links.md", record["layout_migration"]["stale_references"])
        self.assertEqual(self.read("01_Creation/outputs/links.md"), "see 01_Foundations/offer_economics\n")


def record_moves(target, record):
    return util.read_json(os.path.join(target, record["layout_migration"]["plan"]))["moves"]


class MapLine(Layout3):
    """R-B: shown in the dry run, added once, every other byte kept, taken back exactly."""

    def test_the_dry_run_shows_the_exact_line_and_writes_nothing(self):
        before = snapshot(self.target)
        plan = install_mod.upgrade_plan(self.target, self.v3, self.source)
        self.assertEqual(plan["seed_lines"], [{"path": "CLAUDE.md", "line": MAP_LINE}])
        self.assertIn(("02_Deliverables/report.md", "01_Creation/outputs/report.md"), plan["layout"]["moves"])
        self.assertEqual(diff(before, snapshot(self.target)), [])

    def test_the_cli_dry_run_prints_the_line(self):
        self.be("acme-founder")
        code, out, err = self.cli("upgrade", "--release", self.write_json("v3.json", self.v3),
                                  "--target", self.target, "--repo", self.source, "--dry-run",
                                  "--no-vercel")
        self.assertEqual(code, 0, err)
        self.assertIn("one line:  CLAUDE.md gains `%s`" % MAP_LINE, out)
        self.assertIn("move:      02_Deliverables/report.md -> 01_Creation/outputs/report.md", out)

    def test_added_once_with_every_other_byte_kept(self):
        original = self.read("CLAUDE.md", "rb")
        self.up()
        now = self.read("CLAUDE.md", "rb")
        self.assertTrue(now.startswith(original))
        self.assertEqual(now[len(original):], ("\n%s\n" % MAP_LINE).encode())

    def test_never_duplicated(self):
        write(self.target, "CLAUDE.md", "# Mine\n%s\nmore of mine\n" % MAP_LINE)
        self.git_commit("I added it myself")
        original = self.read("CLAUDE.md", "rb")
        self.up()
        self.assertEqual(self.read("CLAUDE.md", "rb"), original)

    def test_rollback_restores_the_original_file_exactly(self):
        write(self.target, "CLAUDE.md", "# Mine, no newline at the end")
        self.git_commit("no trailing newline")
        original = self.read("CLAUDE.md", "rb")
        self.up()
        self.assertIn(MAP_LINE, self.read("CLAUDE.md"))
        install_mod.rollback(self.target)
        self.assertEqual(self.read("CLAUDE.md", "rb"), original)

    def test_two_lines_from_one_upgrade_come_off_byte_for_byte(self):
        spec = dict(V3_SPEC, seed_lines=[{"path": "CLAUDE.md", "line": CORE_LINE},
                                         {"path": "CLAUDE.md", "line": MAP_LINE}])
        harness.run_git(self.source, "reset", "-q", "--hard", self.rev2_recorded)
        rev3 = bump_to_v3(self.source, spec=spec, extra={
            "CLAUDE.md": "# Your AIOS\n\n%s\n%s\n" % (CORE_LINE, MAP_LINE),
            ".aios/operator_core/OPERATOR_CORE.md": "# core\n"})
        v3 = harness.approve(harness.build_manifest(self.source, rev3, "3.0.0"))
        original = self.read("CLAUDE.md", "rb")
        self.up(v3)
        text = self.read("CLAUDE.md")
        self.assertEqual((text.count(CORE_LINE), text.count(MAP_LINE)), (1, 1))
        install_mod.rollback(self.target)
        self.assertEqual(self.read("CLAUDE.md", "rb"), original)


class Refusals(Layout3):
    """Each refusal names the problem and leaves the workspace exactly as it was."""

    def test_an_existing_destination(self):
        write(self.target, "01_Creation/outputs/report.md", "already here\n")
        self.git_commit("a 3.0 path already in use")
        exc = self.refuses_unchanged(self.up)
        self.assertEqual(exc.code, EXIT_STATE)
        self.assertTrue(any("01_Creation/outputs/report.md, which already exists" in d for d in exc.details))

    def test_a_destination_differing_only_by_case(self):
        write(self.target, "01_Creation/outputs/REPORT.md", "mine, capital letters\n")
        self.git_commit("case twin")
        exc = self.refuses_unchanged(self.up)
        self.assertTrue(any("REPORT.md" in d for d in exc.details), exc.details)

    def test_two_files_that_would_become_one_name_on_a_case_insensitive_disk(self):
        write(self.target, "03_Quality_Control/Notes.md", "QC notes\n")
        write(self.target, "02_Deliverables/_review_queue/notes.md", "queue notes\n")
        self.git_commit("two notes")
        exc = self.refuses_unchanged(self.up)
        self.assertTrue(any("would both become" in d for d in exc.details), exc.details)

    def test_a_unicode_twin(self):
        write(self.target, "01_Creation/outputs/café menu.md", "decomposed accent\n")
        self.git_commit("NFD twin of a file that moves")
        self.refuses_unchanged(self.up)

    def test_a_symlink_in_an_old_folder(self):
        os.symlink("../CLAUDE.md", os.path.join(self.target, "02_Deliverables", "link.md"))
        self.git_commit("a link")
        exc = self.refuses_unchanged(self.up)
        self.assertTrue(any("symbolic link" in d for d in exc.details))

    def test_a_nested_repository(self):
        nested = os.path.join(self.target, "11_Projects", "site")
        os.makedirs(nested)
        run_git(nested, "init", "-q")
        write(self.target, ".gitignore", ".env\n11_Projects/site/\n")  # how people keep one
        self.git_commit("ignore the nested repository")
        exc = self.refuses_unchanged(self.up)
        self.assertTrue(any("nested repository" in d for d in exc.details))

    def test_a_submodule(self):
        sub = os.path.join(self.tmp, "site-repo")
        os.makedirs(sub)
        run_git(sub, "init", "-q", "-b", "main")
        write(sub, "index.html", "<h1>site</h1>\n")
        run_git(sub, "add", "-A")
        run_git(sub, "-c", "user.email=s@example.com", "-c", "user.name=s", "commit", "-qm", "site")
        run_git(self.target, "-c", "protocol.file.allow=always", "submodule", "add", "-q", sub,
                "11_Projects/site")
        self.git_commit("a submodule in an old folder")
        exc = self.refuses_unchanged(self.up)
        self.assertTrue(any("nested repository" in d for d in exc.details))

    def test_uncommitted_work(self):
        write(self.target, "02_Deliverables/unsaved.md", "not committed\n")
        self.refuses_unchanged(self.up)

    def test_a_move_onto_a_file_the_release_manages(self):
        rev = harness.bump_source(self.source, {"01_Creation/outputs/report.md": "release's own\n",
                                                "release/package_spec.json": json.dumps(dict(
                                                    V3_SPEC, seed=[s for s in V3_SPEC["seed"]
                                                                   if s != "01_Creation/**"]), indent=2)})
        v3 = harness.approve(harness.build_manifest(self.source, rev, "3.0.0"))
        exc = self.refuses_unchanged(self.up, v3)
        self.assertTrue(any("ships its own file" in d for d in exc.details), exc.details)


class Interrupted(Layout3):
    """A hard kill (os._exit, as kill -9) at every stage of the move; rollback restores the
    pre-upgrade snapshot exactly; a fresh upgrade then succeeds."""

    POINTS = ("layout.before_moves", "layout.linked_not_unlinked", "layout.after_first_move",
              "layout.mid_moves", "layout.after_moves", "upgrade.mid_write", "upgrade.before_record")

    def kill_at(self, point):
        path = self.write_json("v3.json", self.v3)
        self.be("acme-founder")
        code, _out, _err = self.cli("upgrade", "--release", path, "--target", self.target,
                                    "--repo", self.source, "--no-vercel", env={"AIOS_FAULT": "crash:" + point})
        return code, path

    def test_every_kill_point_recovers_exactly(self):
        for point in self.POINTS:
            with self.subTest(point=point):
                before = snapshot(self.target)
                code, path = self.kill_at(point)
                self.assertEqual(code, 137, point)
                self.assertTrue(os.path.isfile(os.path.join(self.target, ".aios", "txn.json")), point)
                code, out, err = self.cli("rollback", "--target", self.target)
                self.assertEqual(code, 0, err)
                self.assertIn("recovered an interrupted upgrade", out)
                self.assertEqual(diff(before, snapshot(self.target)), [], point)

    def test_a_kill_before_the_journal_rolls_nothing_back(self):
        """An upgraded workspace whose 3.0 upgrade dies while planning: rollback must not undo the
        earlier upgrade. Simulated exactly as a kill leaves it: the lock, no journal."""
        harness.run_git(self.source, "reset", "-q", "--hard", self.rev2_recorded)
        rev = harness.bump_source(self.source, {"START_HERE.md": "# start here\n2.10.1\n"})
        v2b = harness.approve(harness.build_manifest(self.source, rev, "2.10.1"))
        install_mod.upgrade(self.target, v2b, self.source)
        self.git_commit("on 2.10.1, upgraded from 2.10.0")
        before = snapshot(self.target)
        write(self.target, ".aios/lock", "upgrade pid=99999 at 2026-10-14T00:00:00Z\n")
        record, _summary, how = install_mod.rollback(self.target)
        self.assertIn("rolled nothing back", how)
        self.assertEqual(record["release"]["version"], "2.10.1")
        self.assertEqual(diff(before, snapshot(self.target)), [])
        self.up()

    def test_after_recovery_the_upgrade_runs_cleanly(self):
        self.kill_at("layout.mid_moves")
        self.cli("rollback", "--target", self.target)
        record = self.up()
        self.assertEqual(record["release"]["version"], "3.0.0")

    def test_a_raised_failure_rolls_back_by_itself(self):
        before = snapshot(self.target)
        os.environ["AIOS_FAULT"] = "raise:layout.mid_moves"
        with self.assertRaises(Refusal):
            self.up()
        os.environ.pop("AIOS_FAULT")
        self.assertEqual(diff(before, snapshot(self.target)), [])


class Rollback(Layout3):

    def test_right_after_the_upgrade_the_workspace_is_exactly_as_before(self):
        before = snapshot(self.target)
        self.up()
        install_mod.rollback(self.target)
        self.assertEqual(diff(before, snapshot(self.target)), [])

    def test_edits_made_after_the_upgrade_go_back_to_the_old_paths(self):
        self.up()
        write(self.target, "01_Creation/outputs/report.md", "edited after the upgrade\n")
        os.remove(os.path.join(self.target, "01_Creation/outputs/copy/my_ad.md"))
        write(self.target, "02_Team_Ops/new_since.md", "made in 3.0\n")
        install_mod.rollback(self.target)
        self.assertEqual(self.read("02_Deliverables/report.md"), "edited after the upgrade\n")
        self.assertFalse(os.path.exists(os.path.join(self.target, "02_Deliverables/copy/my_ad.md")))
        self.assertEqual(self.read("02_Team_Ops/new_since.md"), "made in 3.0\n")

    def test_an_untouched_new_starter_file_is_removed_and_an_edited_one_kept(self):
        self.up()
        write(self.target, "02_Team_Ops/projects/README.md", "# my projects\n")
        install_mod.rollback(self.target)
        self.assertFalse(os.path.exists(os.path.join(self.target, "04_Attention/content/.gitkeep")))
        self.assertEqual(self.read("02_Team_Ops/projects/README.md"), "# my projects\n")

    def test_a_file_where_an_empty_folder_was_refuses_before_changing_anything(self):
        self.up()
        write(self.target, "02_Deliverables/empty_drafts", "a file where the empty folder was\n")
        before = snapshot(self.target)
        with self.assertRaises(Refusal) as ctx:
            install_mod.rollback(self.target)
        self.assertIn("02_Deliverables/empty_drafts", ctx.exception.details)
        self.assertEqual(diff(before, snapshot(self.target)), [])

    def test_a_file_where_an_old_folder_was_refuses_before_changing_anything(self):
        self.up()
        write(self.target, "05_Assets", "a file named like the old folder\n")
        before = snapshot(self.target)
        with self.assertRaises(Refusal) as ctx:
            install_mod.rollback(self.target)
        self.assertIn("05_Assets", ctx.exception.details)
        self.assertEqual(diff(before, snapshot(self.target)), [])

    def test_an_occupied_old_path_refuses_before_changing_anything(self):
        self.up()
        write(self.target, "02_Deliverables/report.md", "something new at the old path\n")
        before = snapshot(self.target)
        with self.assertRaises(Refusal):
            install_mod.rollback(self.target)
        self.assertEqual(diff(before, snapshot(self.target)), [])


class FakeVercel(object):
    """Enough of Vercel's REST API for the R-A check: teams, projects by repo URL, one project."""

    def __init__(self, projects):
        self.projects = projects  # [{id, name, rootDirectory, scope, repo}]
        self.fail = False
        self.refuse = ()  # paths or scopes this token is denied, as a team-scoped token would be
        self.page_size = 100
        self.redirect_to = None
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                if self.headers.get("Authorization") != "Bearer test-token":
                    return self.reply(403, {"error": {"code": "forbidden"}})
                if fake.fail:
                    return self.reply(500, {"error": {"code": "internal"}})
                url = urlparse(self.path)
                q = {k: v[0] for k, v in parse_qs(url.query).items()}
                if fake.redirect_to:
                    self.send_response(302)
                    self.send_header("Location", fake.redirect_to)
                    self.end_headers()
                    return
                if url.path in fake.refuse:
                    return self.reply(403, {"error": {"code": "forbidden"}})
                if url.path == "/v2/teams":
                    return self.reply(200, {"teams": [{"id": "team_acme"}]})
                if url.path == "/v10/projects":
                    scope = q.get("teamId")
                    if (scope or "personal") in fake.refuse:
                        return self.reply(403, {"error": {"code": "forbidden"}})
                    found = [p for p in fake.projects if p["scope"] == scope
                             and "https://github.com/%s" % p["repo"] == q.get("repoUrl")]
                    start = int(q.get("from") or 0)
                    page = found[start:start + fake.page_size]
                    nxt = str(start + fake.page_size) if start + fake.page_size < len(found) else None
                    return self.reply(200, {"projects": page, "pagination": {"count": len(page), "next": nxt}})
                if url.path.startswith("/v9/projects/"):
                    pid = url.path.rsplit("/", 1)[-1]
                    for p in fake.projects:
                        if p["id"] == pid:
                            return self.reply(200, p)
                    return self.reply(404, {"error": {"code": "not_found"}})
                return self.reply(404, {})

            def reply(self, code, body):
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = "http://127.0.0.1:%d" % self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class Websites(Layout3):
    """R-A: a website folder moves only after Vercel builds its new path (or no project builds it)."""

    NO_VERCEL = False

    def setUp(self):
        super(Websites, self).setUp()
        write(self.target, "11_Projects/main-website/package.json", '{"scripts": {"build": "next build"}}\n')
        write(self.target, "11_Projects/main-website/app/page.js", "export default () => 'hi'\n")
        self.git_commit("my site")
        self.vercel = FakeVercel([{"id": "prj_site", "name": "acme-site", "scope": "team_acme",
                                   "repo": "acme/acme-aios", "rootDirectory": "11_Projects/main-website"}])
        self.addCleanup(self.vercel.close)
        os.environ["AIOS_VERCEL_API"] = self.vercel.url
        self.addCleanup(os.environ.pop, "AIOS_VERCEL_API", None)
        self.addCleanup(os.environ.pop, "VERCEL_TOKEN", None)

    def test_no_token_refuses_with_nothing_changed(self):
        os.environ.pop("VERCEL_TOKEN", None)
        exc = self.refuses_unchanged(self.up)
        self.assertTrue(any("11_Projects/main-website" in d and "website" in d for d in exc.details))

    def test_a_project_still_on_the_old_folder_refuses_and_names_the_new_path(self):
        os.environ["VERCEL_TOKEN"] = "test-token"
        exc = self.refuses_unchanged(self.up)
        self.assertTrue(any("acme-site" in d and "set it to 02_Team_Ops/projects/main-website" in d
                            for d in exc.details), exc.details)

    def test_corrected_and_verified_then_it_moves(self):
        os.environ["VERCEL_TOKEN"] = "test-token"
        self.vercel.projects[0]["rootDirectory"] = "02_Team_Ops/projects/main-website"
        record = self.up()
        rows = record["layout_migration"]["sites"]
        self.assertTrue(any("verified" in r and "acme-site" in r for r in rows), rows)
        self.assertTrue(os.path.isfile(os.path.join(self.target, "02_Team_Ops/projects/main-website/package.json")))

    def test_no_project_builds_it_so_nothing_is_affected(self):
        os.environ["VERCEL_TOKEN"] = "test-token"
        self.vercel.projects[:] = []
        record = self.up()
        self.assertTrue(any("No Vercel project" in r for r in record["layout_migration"]["sites"]))

    def test_vercel_unreachable_refuses(self):
        os.environ["VERCEL_TOKEN"] = "test-token"
        self.vercel.fail = True
        exc = self.refuses_unchanged(self.up)
        self.assertTrue(any("nothing was verified" in d for d in exc.details), exc.details)

    def test_a_linked_project_json_is_checked_too(self):
        os.environ["VERCEL_TOKEN"] = "test-token"
        self.vercel.projects[0].update(repo="someone/else")  # not found by repo URL
        write(self.target, "11_Projects/main-website/.vercel/project.json",
              '{"projectId": "prj_site", "orgId": "team_acme"}\n')
        write(self.target, ".gitignore", ".env\n.vercel\n")  # what `vercel link` adds
        self.git_commit("linked with the Vercel CLI")
        exc = self.refuses_unchanged(self.up)
        self.assertTrue(any("project.json" in d for d in exc.details), exc.details)

    def test_a_team_scoped_token_refused_the_team_list_still_verifies(self):
        os.environ["VERCEL_TOKEN"] = "test-token"
        os.environ["VERCEL_TEAM_ID"] = "team_acme"
        self.addCleanup(os.environ.pop, "VERCEL_TEAM_ID", None)
        self.vercel.refuse = ("/v2/teams", "personal")
        exc = self.refuses_unchanged(self.up)
        self.assertTrue(any("acme-site" in d for d in exc.details), exc.details)
        self.vercel.projects[0]["rootDirectory"] = "02_Team_Ops/projects/main-website"
        record = self.up()
        self.assertTrue(any("verified" in r for r in record["layout_migration"]["sites"]))

    def test_a_token_that_can_read_nothing_is_unverified_not_empty(self):
        os.environ["VERCEL_TOKEN"] = "test-token"
        self.vercel.projects[:] = []
        self.vercel.refuse = ("/v2/teams", "personal", "team_acme")
        exc = self.refuses_unchanged(self.up)
        self.assertTrue(any("can't list your Vercel teams and no team was named" in d for d in exc.details),
                        exc.details)

    def test_a_project_on_page_two_is_found(self):
        os.environ["VERCEL_TOKEN"] = "test-token"
        self.vercel.page_size = 2
        others = [{"id": "prj_%d" % i, "name": "other-%d" % i, "scope": "team_acme", "repo": "acme/acme-aios",
                   "rootDirectory": "03_RevOps/site"} for i in range(4)]
        self.vercel.projects[:0] = others  # the site's own project is now on the third page
        exc = self.refuses_unchanged(self.up)
        self.assertTrue(any("acme-site" in d for d in exc.details), exc.details)

    def test_4_an_unreadable_team_is_unverified_not_skipped(self):
        os.environ["VERCEL_TOKEN"] = "test-token"
        self.vercel.projects[:] = []
        self.vercel.refuse = ("team_acme",)
        exc = self.refuses_unchanged(self.up)
        self.assertTrue(any("nothing was verified" in d for d in exc.details), exc.details)

    def test_5_a_redirect_is_never_followed_with_the_token(self):
        seen = []

        class Catcher(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                seen.append(self.headers.get("Authorization"))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"{}")

        catcher = HTTPServer(("127.0.0.1", 0), Catcher)
        threading.Thread(target=catcher.serve_forever, daemon=True).start()
        self.addCleanup(catcher.server_close)
        self.addCleanup(catcher.shutdown)
        self.vercel.redirect_to = "http://127.0.0.1:%d/steal" % catcher.server_address[1]
        os.environ["VERCEL_TOKEN"] = "test-token"
        exc = self.refuses_unchanged(self.up)
        self.assertEqual(seen, [])
        self.assertTrue(any("redirect" in d for d in exc.details), exc.details)

    def test_the_dry_run_lists_the_blocker_and_exits_nonzero(self):
        self.be("acme-founder")
        code, out, _err = self.cli("upgrade", "--release", self.write_json("v3.json", self.v3),
                                   "--target", self.target, "--repo", self.source, "--dry-run",
                                   env={"VERCEL_TOKEN": "test-token"})
        self.assertEqual(code, EXIT_STATE)
        self.assertIn("BLOCKED", out)
        self.assertIn("02_Team_Ops/projects/main-website", out)

    def test_the_token_is_never_written_or_printed(self):
        os.environ["VERCEL_TOKEN"] = "test-token"
        self.vercel.projects[0]["rootDirectory"] = "02_Team_Ops/projects/main-website"
        self.up()
        for dirpath, _d, files in os.walk(self.target):
            if ".git" in dirpath.split(os.sep):
                continue
            for name in files:
                with open(os.path.join(dirpath, name), "rb") as fh:
                    self.assertNotIn(b"test-token", fh.read(), name)


def stub_gh_github(bin_dir, login, slug, protection, permission="admin", remote_codeowners=None):
    """A fake `gh`: who you are, the repository, its rules or branch protection, the founder's
    permission on it, and the CODEOWNERS on its default branch (the one GitHub enforces)."""
    os.makedirs(bin_dir, exist_ok=True)
    remote_file = os.path.join(bin_dir, "remote_codeowners.txt")
    with open(remote_file, "w") as fh:
        fh.write(remote_codeowners or "")
    remote = json.dumps({"type": "file", "size": len((remote_codeowners or "").encode())})
    os.makedirs(bin_dir, exist_ok=True)
    rules = "[]"
    prot = '{"message": "Branch not protected"}'
    prot_code = 1
    if protection == "ruleset":
        rules = '[{"type": "pull_request", "parameters": {"require_code_owner_review": true}}]'
    elif protection == "classic":
        prot = '{"required_pull_request_reviews": {"require_code_owner_reviews": true}}'
        prot_code = 0
    script = """#!/bin/sh
case "$2" in
  user) echo %(login)s; exit 0;;
  repos/%(slug)s) echo '{"default_branch": "main"}'; exit 0;;
  repos/%(slug)s/rules/branches/main) echo '%(rules)s'; exit 0;;
  repos/%(slug)s/branches/main/protection) echo '%(prot)s'; exit %(code)d;;
  repos/%(slug)s/collaborators/*/permission) echo '{"permission": "%(perm)s"}'; exit 0;;
  "repos/%(slug)s/contents/.github/CODEOWNERS?ref=main") %(remote_cmd)s;;
  "repos/%(slug)s/codeowners/errors?ref=main") echo '{"errors": []}'; exit 0;;
esac
exit 1
""" % {"login": login, "slug": slug, "rules": rules, "prot": prot, "code": prot_code, "perm": permission,
       "remote_cmd": ('if [ "$4" = "Accept: application/vnd.github.raw" ]; then cat "%s"; '
                      'else echo \'%s\'; fi; exit 0' % (remote_file, remote))
                     if remote_codeowners is not None else "echo '{\"message\": \"Not Found\"}'; exit 1"}
    path = os.path.join(bin_dir, "gh")
    with open(path, "w") as fh:
        fh.write(script)
    os.chmod(path, 0o755)


class FounderReview(Layout3):
    """R-C: instance check fails visibly until CODEOWNERS covers the new founder lane AND GitHub
    enforces code-owner review."""

    OLD = "# aios-codeowners-for: acme/acme-aios\n/01_Foundations/offer_economics/ @acme-founder\n/.github/ @acme-founder\n"
    NEW = ("# aios-codeowners-for: acme/acme-aios\n/00_AIOS/company/offer_economics/ @acme-founder\n/.github/ @acme-founder\n"
           "/.aios/install.json @acme-founder\n/.aios/adoption.json @acme-founder\n")

    def setUp(self):
        super(FounderReview, self).setUp()
        write(self.target, ".github/CODEOWNERS", self.OLD)
        self.git_commit("owners at the 2.x path")
        self.up()

    def check(self, protection, permission="admin", remote=None):
        """`remote`: the CODEOWNERS on GitHub's default branch; by default, the local file as is
        (as if it were merged)."""
        if remote is None:
            with open(os.path.join(self.target, ".github", "CODEOWNERS")) as fh:
                remote = fh.read()
        stub_gh_github(self.bin, "acme-founder", "acme/acme-aios", protection, permission, remote)
        os.environ["PATH"] = self.bin + os.pathsep + self._old_path
        return self.cli("instance", "check", "--target", self.target)

    def test_fails_visibly_while_codeowners_names_the_old_path(self):
        code, out, _err = self.check("ruleset")
        self.assertNotEqual(code, 0)
        self.assertIn("FOUNDER REVIEW IS NOT IN FORCE", out)
        self.assertIn("founder lane 00_AIOS/company/offer_economics/** (.github/CODEOWNERS): no rule covers "
                      "the whole folder", out)
        self.assertIn("/01_Foundations/offer_economics/, a folder that no longer exists", out)

    def test_fails_while_github_does_not_enforce_it(self):
        write(self.target, ".github/CODEOWNERS", self.NEW)
        code, out, _err = self.check("none")
        self.assertNotEqual(code, 0)
        self.assertIn("not protected", out)

    def test_passes_founder_review_once_restored_and_enforced(self):
        write(self.target, ".github/CODEOWNERS", self.NEW)
        for protection in ("ruleset", "classic"):
            code, out, _err = self.check(protection)
            founder = [l for l in out.splitlines() if " founder " in l]
            self.assertTrue(founder, out)
            self.assertFalse([l for l in founder if "FAIL" in l], out)

    def test_start_says_it_is_not_restored(self):
        self.be("acme-founder")
        code, out, err = self.cli("start", "--target", self.target)
        self.assertEqual(code, 0, err)
        self.assertIn("founder review: NOT RESTORED", out)

    def test_the_upgrade_says_what_to_do_next(self):
        lines = install_mod.founder_review_notice(self.target, LAYOUT["retired_roots"])
        self.assertTrue(lines and "restore_founder_review.md" in lines[0], lines)

    def test_the_founder_lane_hook_holds_the_new_path(self):
        from aioslib import boundary, roles
        policy = roles.load_policy(self.target)
        self.assertTrue(any(util.match_pattern(p, "00_AIOS/company/offer_economics/pricing.md")
                            for p in roles.denied_paths(policy, "operator")))
        self.assertIsNotNone(boundary)


class FreshAndContract(Sandbox):
    """A fresh 3.0 install, and the instance contract on a complete workspace."""

    def setUp(self):
        super(FreshAndContract, self).setUp()
        extra = {"README.md": "# readme\n", "estate.yaml": 'kind_target: "instance"\nrepo: "acme-aios"\n',
                 "SETUP.md": "# setup\n", "REPO_CONTEXT.md": "# context\n",
                 "docs/decisions/0001-layout.md": "# 0001\n"}
        for d in layout_mod.DOMAIN_FOLDERS:
            extra.setdefault("%s/README.md" % d, "# %s\n" % d)
        self.v3 = harness.approve(harness.build_manifest(self.source, bump_to_v3(self.source, extra=extra),
                                                         "3.0.0"))
        install_mod.install(self.target, self.v3, self.source, harness.config())
        write(self.target, ".github/CODEOWNERS", FounderReview.NEW)
        run_git(self.target, "init", "-q", "-b", "main")
        run_git(self.target, "remote", "add", "origin", "https://github.com/acme/acme-aios.git")

    def check(self, protection="ruleset"):
        with open(os.path.join(self.target, ".github", "CODEOWNERS")) as fh:
            remote = fh.read()
        stub_gh_github(self.bin, "acme-founder", "acme/acme-aios", protection, remote_codeowners=remote)
        os.environ["PATH"] = self.bin + os.pathsep + self._old_path
        return self.cli("instance", "check", "--target", self.target)

    def test_a_fresh_3_0_install_has_only_the_new_layout(self):
        record = install_mod.load_record(self.target)
        self.assertEqual(record["layout"], "3")
        for d in layout_mod.OLD_FOLDERS:
            self.assertFalse(os.path.exists(os.path.join(self.target, d)), d)
        with open(os.path.join(self.target, "CLAUDE.md")) as fh:
            self.assertEqual(fh.read().splitlines().count(MAP_LINE), 1)

    def test_a_complete_instance_passes(self):
        code, out, err = self.check()
        self.assertEqual(code, 0, out + err)
        self.assertIn("meets the instance contract's checks", out)

    def test_a_leftover_2x_folder_fails(self):
        write(self.target, "02_Deliverables/stray.md", "left behind\n")
        code, out, _err = self.check()
        self.assertNotEqual(code, 0)
        self.assertIn("02_Deliverables still there", out)

    def test_a_placeholder_codeowners_fails(self):
        write(self.target, ".github/CODEOWNERS",
              "# aios-codeowners-for: acme/acme-aios\n/00_AIOS/company/offer_economics/ [REPO_OWNER]\n")
        code, out, _err = self.check()
        self.assertNotEqual(code, 0)
        self.assertIn("unresolved placeholder", out)


class IndependentReviewRegressions(Layout3):
    """Each defect the Codex review (gpt-5.6-sol, 2026-10-14) found, reproduced, then fixed."""

    def test_1_a_dry_run_and_a_refusal_leave_nothing_behind(self):
        backups = os.path.join(self.target, ".aios", "backups")
        before = sorted(os.listdir(backups)) if os.path.isdir(backups) else None
        install_mod.upgrade_plan(self.target, self.v3, self.source, no_vercel=True)
        self.assertEqual(sorted(os.listdir(backups)) if os.path.isdir(backups) else None, before)
        with self.assertRaises(Refusal):
            self.up(no_vercel=False)  # no token, no statement: refused
        if os.name != "nt":  # Windows can't delete the open guard file, so it stays there
            self.assertEqual(sorted(os.listdir(backups)) if os.path.isdir(backups) else None, before)
        self.assertFalse(os.path.lexists(os.path.join(self.target, ".aios", "lock")))

    def test_2_a_linked_destination_folder_is_refused(self):
        outside = os.path.join(self.tmp, "outside")
        os.makedirs(outside)
        os.symlink(outside, os.path.join(self.target, "01_Creation"))
        self.git_commit("01_Creation is a link")
        exc = self.refuses_unchanged(self.up)
        self.assertTrue(any("symbolic link or a file" in d for d in exc.details), exc.details)
        self.assertEqual(os.listdir(outside), [])

    def test_3_every_move_needs_a_vercel_read_or_the_founders_statement(self):
        exc = self.refuses_unchanged(self.up, None, False)
        self.assertTrue(any("--no-vercel" in d for d in exc.details), exc.details)
        record = self.up(no_vercel=True)
        self.assertIn("isn't deployed by Vercel", record["layout_migration"]["vercel"])

    def test_3_the_statement_is_refused_when_vercel_files_are_moving(self):
        write(self.target, "05_Assets/landing/vercel.json", "{}\n")
        self.git_commit("a vercel.json in an old folder")
        exc = self.refuses_unchanged(self.up)
        self.assertTrue(any("deployed by Vercel" in d for d in exc.details), exc.details)

    def test_6_a_live_lock_is_never_taken(self):
        self.up()
        write(self.target, ".aios/lock", "upgrade pid=%d at now\n" % os.getpid())
        before = snapshot(self.target)
        with self.assertRaises(Refusal) as ctx:
            install_mod.rollback(self.target)
        self.assertIn("still running", ctx.exception.message)
        self.assertEqual(diff(before, snapshot(self.target)), [])

    def test_7_a_rollback_killed_partway_is_finished_by_the_next_one(self):
        self.be("acme-founder")
        for point in ("rollback.before_restore", "rollback.after_restore", "rollback.after_reverse"):
            with self.subTest(point=point):
                pre = snapshot(self.target)
                self.up()
                code, _o, _e = self.cli("rollback", "--target", self.target, env={"AIOS_FAULT": "crash:" + point})
                self.assertEqual(code, 137)
                code, out, err = self.cli("rollback", "--target", self.target)
                self.assertEqual(code, 0, err)
                self.assertIn("finished an interrupted rollback", out)
                self.assertEqual(diff(pre, snapshot(self.target)), [], point)

    def test_8_an_empty_folder_the_client_had_survives_rollback(self):
        os.makedirs(os.path.join(self.target, "04_Attention", "content"))  # 3.0 ships a file in it
        pre = snapshot(self.target)
        self.up()
        self.assertTrue(os.path.isfile(os.path.join(self.target, "04_Attention/content/.gitkeep")))
        install_mod.rollback(self.target)
        self.assertEqual(diff(pre, snapshot(self.target)), [])

    def test_9_a_claude_md_with_non_utf8_bytes_comes_back_exactly(self):
        write(self.target, "CLAUDE.md", b"# Mine\n\xff\xfe not utf-8\nend")
        self.git_commit("odd bytes")
        original = self.read("CLAUDE.md", "rb")
        self.up()
        self.assertTrue(self.read("CLAUDE.md", "rb").startswith(original))
        install_mod.rollback(self.target)
        self.assertEqual(self.read("CLAUDE.md", "rb"), original)

    def test_10_a_linked_claude_md_is_never_written_through(self):
        outside = os.path.join(self.tmp, "elsewhere.md")
        with open(outside, "w") as fh:
            fh.write("# not in the workspace\n")
        os.remove(os.path.join(self.target, "CLAUDE.md"))
        os.symlink(outside, os.path.join(self.target, "CLAUDE.md"))
        self.git_commit("CLAUDE.md is a link")
        record = self.up()
        with open(outside) as fh:
            self.assertEqual(fh.read(), "# not in the workspace\n")
        self.assertIn({"path": "CLAUDE.md", "line": MAP_LINE, "release": "3.0.0", "state": "link"},
                      record["seed_lines"])

    def test_11_codeowners_matching_follows_githubs_documented_examples(self):
        cases = [("docs/*", "docs/getting-started.md", True),
                 ("docs/*", "docs/build-app/troubleshooting.md", False),
                 ("*.js", "src/a/b.js", True), ("apps/", "x/apps/y.md", True),
                 ("/docs/", "docs/a/b.md", True), ("/docs/", "x/docs/a.md", False),
                 ("**/logs", "a/logs/x.txt", True), ("/build/logs/", "build/logs/a/b", True),
                 ("/scripts/aios", "scripts/aios/x.py", True), (".env*", "x/.env.local", True)]
        for pattern, path, want in cases:
            self.assertEqual(bool(governance._pattern_regex(pattern).match(path)), want, (pattern, path))


class SeedLineOnAMovedFile(Layout3):
    """Gemini round 3: a declared line whose file the move also relocates comes off exactly."""

    def test_rollback_and_recovery_take_it_back_exactly(self):
        target_file = "00_AIOS/company/market_analysis/_workspace.md"
        spec = dict(V3_SPEC, seed_lines=[{"path": "CLAUDE.md", "line": MAP_LINE},
                                         {"path": target_file, "line": "@00_AIOS/routing.md"}])
        harness.run_git(self.source, "reset", "-q", "--hard", self.rev2_recorded)
        rev3 = bump_to_v3(self.source, spec=spec, extra={
            target_file: "# market\n\n@00_AIOS/routing.md\n"})
        v3 = harness.approve(harness.build_manifest(self.source, rev3, "3.0.0"))
        pre = snapshot(self.target)
        record = self.up(v3)
        self.assertIn("@00_AIOS/routing.md", self.read(target_file))
        self.assertTrue(any(e["path"] == target_file and e["state"] == "added" for e in record["seed_lines"]))
        install_mod.rollback(self.target)
        self.assertEqual(diff(pre, snapshot(self.target)), [])
        os.environ["AIOS_FAULT"] = "raise:upgrade.before_record"
        with self.assertRaises(Refusal):
            self.up(v3)
        os.environ.pop("AIOS_FAULT")
        self.assertEqual(diff(pre, snapshot(self.target)), [])


class FounderCoverage(FounderReview):
    """R-C, past one sample path: a later rule that takes over part of the founder lane fails."""

    def test_12_a_later_rule_over_a_subfolder_fails(self):
        write(self.target, ".github/CODEOWNERS", self.NEW + "/00_AIOS/company/offer_economics/drafts/ @acme-va\n")
        code, out, _err = self.check("ruleset")
        self.assertNotEqual(code, 0)
        self.assertIn("drafts", out)

    def test_12_a_later_file_type_rule_fails(self):
        write(self.target, ".github/CODEOWNERS", self.NEW + "*.md @acme-va\n")
        code, out, _err = self.check("ruleset")
        self.assertNotEqual(code, 0)
        self.assertIn("*.md", out)

    def test_13_no_founder_in_the_people_map_fails(self):
        write(self.target, ".github/CODEOWNERS", self.NEW)
        cfg = util.read_json(os.path.join(self.target, ".aios", "config.json"))
        for person in cfg["people"]:
            person["role"] = "operator"
        util.write_json(os.path.join(self.target, ".aios", "config.json"), cfg)
        problems = governance.founder_review_local(self.target, util.read_json(
            os.path.join(self.target, ".aios", "roles.json")), cfg)
        self.assertEqual(problems[0][0], "FAIL")
        self.assertIn("no founder", problems[0][1])

    def test_13_a_founder_without_write_access_fails(self):
        write(self.target, ".github/CODEOWNERS", self.NEW)
        code, out, _err = self.check("ruleset", permission="read")
        self.assertNotEqual(code, 0)
        self.assertIn("GitHub ignores a code owner without write access", out)


class SecondReviewRegressions(Layout3):
    """Each defect the Codex review's second round found, reproduced, then fixed."""

    def test_r2_1_a_link_where_an_old_folder_was_refuses_rollback_before_any_change(self):
        self.up()
        outside = os.path.join(self.tmp, "outside")
        os.makedirs(outside)
        os.symlink(outside, os.path.join(self.target, "07_Setup"))  # where a 2.x release file goes back
        before = snapshot(self.target)
        with self.assertRaises(Refusal):
            install_mod.rollback(self.target)
        self.assertEqual(os.listdir(outside), [])
        self.assertEqual(diff(before, snapshot(self.target)), [])

    def test_r2_2_a_lock_its_holder_is_still_writing_is_never_reclaimed(self):
        # Round 2 refused every lock that named no process, since its holder might be writing it.
        # Since round 10 a holder creates and writes its lock under the workspace guard, so a recovery
        # waits until the name is there; a lock still unnamed after that lost its holder, and is
        # cleared (3.1 round 11). Here a live holder is still writing its lock when rollback starts.
        self.up()
        holder = (
            "import os, sys, time\n"
            "sys.path.insert(0, %r)\n"
            "from aioslib import install\n"
            "with install._RecoveryGuard(%r):\n"
            "    fd = os.open(%r, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)\n"
            "    print('unnamed', flush=True)\n"
            "    time.sleep(1.0)\n"
            "    os.write(fd, ('upgrade pid=%%d at now\\n' %% os.getpid()).encode())\n"
            "time.sleep(3.0)\n"
        ) % (harness.AIOS_DIR, self.target, os.path.join(self.target, ".aios", "lock"))
        proc = subprocess.Popen([sys.executable, "-c", holder], stdout=subprocess.PIPE)
        try:
            self.assertEqual(proc.stdout.readline().strip(), b"unnamed")
            with open(os.path.join(self.target, ".aios/lock")) as fh:
                self.assertEqual(fh.read(), "")  # unnamed as rollback starts
            with self.assertRaises(Refusal) as ctx:
                install_mod.rollback(self.target)
            self.assertIn("still running", ctx.exception.message)
            self.assertTrue(os.path.lexists(os.path.join(self.target, ".aios/lock")))
        finally:
            proc.wait()
            proc.stdout.close()

    def test_r2_2_a_lock_removes_only_itself(self):
        lock = install_mod._Lock(self.target, "upgrade")
        lock.__enter__()
        os.remove(lock.path)
        write(self.target, ".aios/lock", "rollback pid=1 at now\n")  # someone else's now
        lock.__exit__(None, None, None)
        self.assertTrue(os.path.exists(os.path.join(self.target, ".aios/lock")))

    def test_r2_3_a_finished_rollback_killed_before_unlocking_isnt_repeated(self):
        harness.run_git(self.source, "reset", "-q", "--hard", self.rev2_recorded)
        rev = harness.bump_source(self.source, {"START_HERE.md": "# start here\n2.10.1\n"})
        install_mod.upgrade(self.target, harness.approve(harness.build_manifest(self.source, rev, "2.10.1")),
                            self.source)
        self.git_commit("2.10.1")
        self.up()
        install_mod.rollback(self.target)  # back to 2.10.1
        # what a kill right after the rollback finished, before it unlocked, leaves behind:
        current = install_mod.load_record(self.target)
        util.write_json(os.path.join(self.target, ".aios", "txn.json"),
                        {"op": "rollback", "phase": "complete", "backup": "x", "current_record": current})
        write(self.target, ".aios/lock", "rollback pid=999999 at now\n")
        record, _s, how = install_mod.rollback(self.target)
        self.assertEqual(record["release"]["version"], "2.10.1")
        self.assertIn("had finished", how)
        self.assertFalse(os.path.exists(os.path.join(self.target, ".aios", "txn.json")))

    def test_r2_4_recovery_leaves_a_client_file_at_a_path_the_upgrade_meant_to_write(self):
        self.be("acme-founder")
        code, _o, _e = self.cli("upgrade", "--release", self.write_json("v3.json", self.v3), "--target",
                                self.target, "--repo", self.source, "--no-vercel",
                                env={"AIOS_FAULT": "crash:layout.mid_moves"})
        self.assertEqual(code, 137)
        write(self.target, "02_Team_Ops/projects/README.md", "MINE, written after the crash\n")
        install_mod.rollback(self.target)
        self.assertEqual(self.read("02_Team_Ops/projects/README.md"), "MINE, written after the crash\n")

    def test_r2_4_a_created_starter_file_with_new_permissions_is_theirs(self):
        self.up()
        os.chmod(os.path.join(self.target, "02_Team_Ops/projects/README.md"), 0o600)
        _r, _s, how = install_mod.rollback(self.target)
        self.assertTrue(os.path.isfile(os.path.join(self.target, "02_Team_Ops/projects/README.md")))
        self.assertIn("changed permissions", how)

    def test_r2_7_ci_repository_isnt_trusted_for_another_workspace(self):
        os.environ["GITHUB_REPOSITORY"] = "someone/else"
        os.environ["GITHUB_WORKSPACE"] = self.tmp
        self.addCleanup(os.environ.pop, "GITHUB_REPOSITORY", None)
        self.addCleanup(os.environ.pop, "GITHUB_WORKSPACE", None)
        self.assertEqual(governance.target_repo_slug(self.target), "acme/acme-aios")
        os.environ["GITHUB_WORKSPACE"] = self.target
        self.assertEqual(governance.target_repo_slug(self.target), "someone/else")


class FourthGeminiRegressions(Layout3):
    """Gemini round 4: rollback never removes, or moves back, through a link, and never copies a
    file into a folder that took its place."""

    def test_a_link_in_place_of_a_new_folder_stops_rollback_before_it_deletes_outside(self):
        self.up()
        outside = os.path.join(self.tmp, "outside")
        os.makedirs(outside)
        write(outside, "README.md", "# projects\n")  # same name and bytes as the starter file
        shutil.rmtree(os.path.join(self.target, "02_Team_Ops", "projects"))
        os.symlink(outside, os.path.join(self.target, "02_Team_Ops", "projects"))
        with self.assertRaises(Refusal):
            install_mod.rollback(self.target)
        self.assertEqual(os.listdir(outside), ["README.md"])

    def test_a_folder_where_a_release_file_goes_back_refuses_before_any_change(self):
        self.up()
        os.makedirs(os.path.join(self.target, "07_Setup", "walkthrough.md"))
        before = snapshot(self.target)
        with self.assertRaises(Refusal) as ctx:
            install_mod.rollback(self.target)
        self.assertIn("07_Setup/walkthrough.md", ctx.exception.details)
        self.assertEqual(diff(before, snapshot(self.target)), [])


class ThirdCodexRegressions(Layout3):
    """Codex round 3, each reproduced then fixed."""

    def test_r3_2_a_link_at_the_old_path_pointing_at_the_new_file_is_refused(self):
        self.up()
        os.makedirs(os.path.join(self.target, "02_Deliverables"))
        os.symlink(os.path.join(self.target, "01_Creation/outputs/report.md"),
                   os.path.join(self.target, "02_Deliverables/report.md"))
        with self.assertRaises(Refusal):
            install_mod.rollback(self.target)
        self.assertEqual(self.read("01_Creation/outputs/report.md"), "my report\n")

    def test_r3_3_a_stale_lock_is_cleared_only_if_it_is_still_the_one_judged(self):
        path = os.path.join(self.target, ".aios", "lock")
        write(self.target, ".aios/lock", "upgrade pid=999999 at then\n")
        real_alive = install_mod._holder_alive

        def judged_then_replaced(text):  # someone takes the lock between our verdict and our removal
            dead = real_alive(text)
            os.remove(path)
            with open(path, "w") as fh:
                fh.write("rollback pid=%d at now\n" % os.getpid())
            return dead
        install_mod._holder_alive = judged_then_replaced
        try:
            self.assertFalse(install_mod._reclaim_stale_lock(path))
        finally:
            install_mod._holder_alive = real_alive
        with open(path) as fh:
            self.assertIn("rollback pid=%d" % os.getpid(), fh.read())

    def test_r3_3_and_when_the_new_lock_reuses_the_old_inode(self):
        # Linux gives a freed inode number to the next new file at once (CI caught it); rewriting
        # the file in place makes the same inode certain on every system.
        path = os.path.join(self.target, ".aios", "lock")
        write(self.target, ".aios/lock", "upgrade pid=999999 at then\n")
        real_alive = install_mod._holder_alive
        inode = os.stat(path).st_ino

        def judged_then_reused(text):
            dead = real_alive(text)
            with open(path, "w") as fh:  # same inode, another holder's words
                fh.write("rollback pid=%d at now\n" % os.getpid())
            return dead
        install_mod._holder_alive = judged_then_reused
        try:
            self.assertFalse(install_mod._reclaim_stale_lock(path))
        finally:
            install_mod._holder_alive = real_alive
        self.assertEqual(os.stat(path).st_ino, inode)
        with open(path) as fh:
            self.assertIn("rollback pid=%d" % os.getpid(), fh.read())

    def test_r3_3_a_lock_never_removes_a_successor_on_its_reused_inode(self):
        lock = install_mod._Lock(self.target, "upgrade")
        lock.__enter__()
        with open(lock.path, "w") as fh:  # ours was taken over in place: same inode, other words
            fh.write("rollback pid=1 at now\n")
        lock.__exit__(None, None, None)
        self.assertTrue(os.path.exists(lock.path))

    def test_r3_3_an_untouched_dead_lock_is_still_cleared(self):
        path = os.path.join(self.target, ".aios", "lock")
        write(self.target, ".aios/lock", "upgrade pid=999999 at then\n")
        self.assertTrue(install_mod._reclaim_stale_lock(path))
        self.assertFalse(os.path.lexists(path))

    @unittest.skipUnless(hasattr(os, "fork"), "the guard is flock, which this system lacks")
    def test_r10_no_new_holder_can_land_between_dead_and_removed(self):
        # A recovery judged the lock dead. In that instant someone deletes it and a real second
        # process starts an upgrade. Its lock must survive the recovery's removal.
        path = os.path.join(self.target, ".aios", "lock")
        write(self.target, ".aios/lock", "upgrade pid=999999 at then\n")
        child_src = ("import sys, time\nsys.path.insert(0, %r)\nfrom aioslib import install\n"
                     "print('trying', flush=True)\n"
                     "with install._Lock(%r, 'upgrade'):\n    print('got', flush=True)\n    time.sleep(3)\n"
                     % (harness.AIOS_DIR, self.target))
        child = []
        real_still = install_mod._still_this_lock

        def window(p, ident):
            same = real_still(p, ident)
            if p == path and same and not child:
                os.remove(path)  # someone clears it by hand...
                proc = subprocess.Popen([sys.executable, "-c", child_src], stdout=subprocess.PIPE)
                child.append(proc)
                self.assertEqual(proc.stdout.readline().strip(), b"trying")  # ...and an upgrade starts
                import select
                ready, _, _ = select.select([proc.stdout], [], [], 1.5)
                if ready:
                    child.append(proc.stdout.readline().strip())  # it got in during the window
            return same
        install_mod._still_this_lock = window
        try:
            with install_mod._RecoveryGuard(self.target):
                install_mod._reclaim_stale_lock(path)
        finally:
            install_mod._still_this_lock = real_still
        proc = child[0]
        try:
            self.assertEqual(len(child), 1, "the second process took the lock inside the window")
            self.assertEqual(proc.stdout.readline().strip(), b"got")  # once the guard is free
            with open(path) as fh:
                self.assertIn("pid=%d" % proc.pid, fh.read())  # its lock survived
        finally:
            proc.wait(10)
            proc.stdout.close()
        self.assertFalse(os.path.lexists(path))  # and it removed only its own, on finishing

    def test_r3_7_a_setuid_bit_counts_as_a_change(self):
        self.up()
        os.chmod(os.path.join(self.target, "02_Team_Ops/projects/README.md"), 0o4644)
        _r, _s, how = install_mod.rollback(self.target)
        self.assertTrue(os.path.isfile(os.path.join(self.target, "02_Team_Ops/projects/README.md")))
        self.assertIn("changed permissions", how)

    def test_r3_8_a_finished_rollback_with_drift_since_is_not_reported_as_fine(self):
        self.up()
        install_mod.rollback(self.target)
        current = install_mod.load_record(self.target)
        util.write_json(os.path.join(self.target, ".aios", "txn.json"),
                        {"op": "rollback", "phase": "complete", "backup": "x", "current_record": current})
        with open(os.path.join(self.target, "START_HERE.md"), "a") as fh:
            fh.write("drift\n")
        with self.assertRaises(Refusal) as ctx:
            install_mod.rollback(self.target)
        self.assertEqual(ctx.exception.code, util.EXIT_VERIFY)


class ThirdCodexFounder(FounderReview):

    def test_r3_4_a_founder_sharing_a_rule_with_a_non_founder_isnt_founder_review(self):
        write(self.target, ".github/CODEOWNERS",
              "# aios-codeowners-for: acme/acme-aios\n/00_AIOS/company/offer_economics/ @acme-founder @acme-va\n"
              "/.github/ @acme-founder\n")
        code, out, _err = self.check("ruleset")
        self.assertNotEqual(code, 0)
        self.assertIn("not only founders", out)

    def test_r3_5_an_error_reading_githubs_file_is_unverified_not_a_fallthrough(self):
        write(self.target, ".github/CODEOWNERS", self.NEW)
        stub_gh_github(self.bin, "acme-founder", "acme/acme-aios", "ruleset", remote_codeowners=self.NEW)
        gh = os.path.join(self.bin, "gh")
        with open(gh) as fh:
            script = fh.read()
        script = script.replace('"repos/acme/acme-aios/contents/.github/CODEOWNERS?ref=main")',
                                '"repos/acme/acme-aios/contents/.github/CODEOWNERS?ref=main") '
                                'echo \'{"message": "Server Error"}\'; exit 1;;\n  "unused")')
        with open(gh, "w") as fh:
            fh.write(script)
        os.environ["PATH"] = self.bin + os.pathsep + self._old_path
        code, out, _err = self.cli("instance", "check", "--target", self.target)
        self.assertNotEqual(code, 0)
        self.assertIn("couldn't read .github/CODEOWNERS on main", out)

    def test_r3_6_the_binding_check_uses_the_workspaces_own_repository(self):
        write(self.target, ".github/CODEOWNERS", self.NEW)
        os.environ["GITHUB_REPOSITORY"] = "controller/repo"
        os.environ["GITHUB_WORKSPACE"] = self.tmp
        self.addCleanup(os.environ.pop, "GITHUB_REPOSITORY", None)
        self.addCleanup(os.environ.pop, "GITHUB_WORKSPACE", None)
        self.assertEqual(governance.check(self.target), [])  # bound to acme/acme-aios, its own origin


class FourthCodexRegressions(Layout3):
    """Codex round 4: the installer paths under the move, hardened."""

    def test_r4_1_a_release_may_never_take_over_a_seed(self):
        spec = dict(V3_SPEC, seed=[x for x in V3_SPEC["seed"] if x != "00_AIOS/**"])
        # 2.10.0's record moves to a tag, off the branch: the release build's own seed check reads the
        # branch, and this test is about the installer's check when the build's misses.
        harness.run_git(self.source, "reset", "-q", "--hard", self.rev2)
        harness.build_manifest(self.source, self.rev2, "2.10.0", record="tag")
        rev3 = bump_to_v3(self.source, spec=spec)  # 00_AIOS/company/... is now managed
        v3 = harness.approve(harness.build_manifest(self.source, rev3, "3.0.0"))
        exc = self.refuses_unchanged(self.up, v3)
        self.assertIn("would take over", exc.message)

    def test_r4_2_a_planted_link_in_the_backups_folder_redirects_nothing(self):
        outside = os.path.join(self.tmp, "outside.txt")
        with open(outside, "w") as fh:
            fh.write("untouched\n")
        os.makedirs(os.path.join(self.target, ".aios", "backups"), exist_ok=True)
        for name in (".write.tmp", ".seed-line.tmp"):
            os.symlink(outside, os.path.join(self.target, ".aios", "backups", name))
        self.up()
        with open(outside) as fh:
            self.assertEqual(fh.read(), "untouched\n")

    def test_r4_4_a_link_with_the_same_bytes_isnt_identical(self):
        src = os.path.join(self.tmp, "a.md")
        with open(src, "w") as fh:
            fh.write("same\n")
        link = os.path.join(self.tmp, "b.md")
        os.symlink(src, link)
        self.assertFalse(install_mod._identical_regular(src, link))

    def test_r4_5_verify_catches_a_link_and_special_bits(self):
        self.up()
        rel = "START_HERE.md"
        full = os.path.join(self.target, rel)
        os.chmod(full, 0o4644)
        problems, _ = install_mod.verify(self.target)
        self.assertTrue(any("setuid" in p for p in problems), problems)
        os.chmod(full, 0o644)
        copy = os.path.join(self.tmp, "copy.md")
        shutil.copy2(full, copy)
        os.remove(full)
        os.symlink(copy, full)
        problems, _ = install_mod.verify(self.target)
        self.assertTrue(any("replaced by a link" in p for p in problems), problems)


class InstallRefusesBeforeWriting(Sandbox):
    """Codex round 4: CODEOWNERS is rendered before the first file is written."""

    def test_an_incomplete_owners_map_leaves_the_target_empty(self):
        v = harness.approve(harness.build_manifest(self.source, self.rev, "2.10.0"))
        cfg = harness.config(code_owners={"PRIMARY_REVIEWER": ["@acme-founder"]})  # REPO_OWNER missing
        os.makedirs(self.target)
        with self.assertRaises(Refusal):
            install_mod.install(self.target, v, self.source, cfg)
        self.assertEqual(os.listdir(self.target), [])


class InstallerReview(Sandbox):
    """Helpers for the installer findings of the later review rounds."""

    OWNERS = {"REPO_OWNER": ["@acme-founder"], "PRIMARY_REVIEWER": ["@acme-va"]}

    def v(self, rev, version, **kw):
        return harness.approve(harness.build_manifest(self.source, rev, version, **kw))

    def commit_target(self, msg):
        if not os.path.isdir(os.path.join(self.target, ".git")):
            run_git(self.target, "init", "-q", "-b", "main")
            run_git(self.target, "config", "user.email", "client@example.com")
            run_git(self.target, "config", "user.name", "client")
        run_git(self.target, "add", "-A")
        run_git(self.target, "commit", "-qm", msg)

    def refuses_leaving(self, cfg, before):
        with self.assertRaises(Refusal) as ctx:
            install_mod.install(self.target, self.v(self.rev, "2.10.0"), self.source, cfg)
        self.assertEqual(diff(before, snapshot(self.target)), [], "a refused install changed the target")
        return ctx.exception


class FifthCodexRegressions(InstallerReview):
    """Codex round 5: install writes nothing of the client's, owner tokens GitHub would ignore are
    refused, a seed stays the client's across releases, and adopt pins the executable bit."""

    def test_r5_1_the_clients_codeowners_is_never_replaced_or_shadowed(self):
        for rel in (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS"):
            shutil.rmtree(self.target, True)
            write(self.target, rel, "* @someone-of-theirs\n")
            exc = self.refuses_leaving(harness.config(code_owners=self.OWNERS), snapshot(self.target))
            self.assertIn("already has a CODEOWNERS", exc.message)

    def test_r5_1_a_different_org_config_is_refused_and_the_same_one_is_fine(self):
        cfg = harness.config(code_owners=self.OWNERS)
        write(self.target, ".aios/config.json", json.dumps(dict(cfg, org_id="someone-else")))
        exc = self.refuses_leaving(cfg, snapshot(self.target))
        self.assertIn("different organization config", exc.message)
        write(self.target, ".aios/config.json", json.dumps(cfg))
        install_mod.install(self.target, self.v(self.rev, "2.10.0"), self.source, cfg)

    def test_r5_1_install_never_writes_through_a_linked_folder(self):
        outside = os.path.join(self.tmp, "outside")
        os.makedirs(outside)
        os.makedirs(self.target)
        os.symlink(outside, os.path.join(self.target, ".claude"))
        exc = self.refuses_leaving(harness.config(), snapshot(self.target))
        self.assertIn("through a link", exc.message)
        self.assertEqual(os.listdir(outside), [])

    def test_r5_1_a_seed_the_client_already_had_is_theirs_and_the_next_upgrade_keeps_it(self):
        write(self.target, "README.md", "# my own readme\n")
        record, _creds = install_mod.install(self.target, self.v(self.rev, "2.10.0"), self.source,
                                             harness.config())
        self.assertIn("README.md", [e["path"] for e in record["seeded"]])
        self.commit_target("2.10.0")
        rev2 = harness.bump_source(self.source, {"START_HERE.md": "# start here\nnext.\n"})
        install_mod.upgrade(self.target, self.v(rev2, "2.10.1"), self.source)  # once: a "collision"
        with open(os.path.join(self.target, "README.md")) as fh:
            self.assertEqual(fh.read(), "# my own readme\n")

    def test_r5_2_an_owner_github_would_ignore_is_refused_before_any_write(self):
        bad = dict(self.OWNERS, REPO_OWNER=["not-a-handle"])
        self.assertTrue(any("not-a-handle" in p for p in
                            __import__("aioslib.orgconfig").orgconfig.validate(harness.config(code_owners=bad))))
        exc = self.refuses_leaving(harness.config(code_owners=bad), snapshot(self.target))
        self.assertIn("not usable", exc.message)
        # Well-formed, but nobody in this workspace: the rendered file is checked as instance check
        # would check it, before the first write.
        stranger = dict(self.OWNERS, REPO_OWNER=["@a-stranger"])
        exc = self.refuses_leaving(harness.config(code_owners=stranger), snapshot(self.target))
        self.assertIn("would not enforce", exc.message)
        self.assertTrue(any("a-stranger" in d for d in exc.details), exc.details)

    def _seed_dropped_then_deleted(self):
        spec = dict(harness.PACKAGE_SPEC, seed=harness.PACKAGE_SPEC["seed"] + ["notes/x.md"])
        rev1 = harness.bump_source(self.source, {"notes/x.md": "a seed\n",
                                                 "release/package_spec.json": json.dumps(spec)})
        # 2.10.0's record goes on a tag, off the branch: the release build's own seed check reads the
        # branch, and this test is about the installer's check when the build's misses.
        install_mod.install(self.target, self.v(rev1, "2.10.0", record="tag"), self.source, harness.config())
        self.commit_target("2.10.0")
        run_git(self.source, "rm", "-q", "notes/x.md")  # 2.10.1 stops shipping it
        rev2 = harness.bump_source(self.source, {}, "2.10.1")
        record = install_mod.upgrade(self.target, self.v(rev2, "2.10.1"), self.source)
        self.assertNotIn("notes/x.md", [e["path"] for e in record["seeded"]])
        self.assertIn("notes/x.md", record["seed_history"])
        os.remove(os.path.join(self.target, "notes/x.md"))  # and the client deletes it
        self.commit_target("I deleted it")
        # 2.10.2 ships the same path as its own.
        return harness.bump_source(self.source, {"notes/x.md": "the release's now\n",
                                                 "release/package_spec.json": json.dumps(harness.PACKAGE_SPEC)})

    def test_r5_3_a_seed_dropped_and_deleted_is_never_taken_over(self):
        rev3 = self._seed_dropped_then_deleted()
        before = snapshot(self.target)
        with self.assertRaises(Refusal) as ctx:
            install_mod.upgrade(self.target, self.v(rev3, "2.10.2"), self.source)
        self.assertIn("would take over", ctx.exception.message)
        self.assertIn("notes/x.md", ctx.exception.details)
        self.assertEqual(diff(before, snapshot(self.target)), [])

    def test_r5_3_release_build_refuses_a_managed_file_any_earlier_release_seeded(self):
        rev3 = self._seed_dropped_then_deleted()
        old = harness.build_manifest(self.source, self.rev, "2.10.0")
        old["files"].append({"path": "notes/x.md", "class": "seed", "mode": "100644", "sha256": "0" * 64})
        rev4 = harness.bump_source(self.source, {"releases/starter-2.10.0.json": json.dumps(old)})
        with self.assertRaises(Refusal) as ctx:
            harness.build_manifest(self.source, rev4, "2.10.2")
        self.assertIn("earlier seed", ctx.exception.message)
        self.assertIn("notes/x.md", ctx.exception.details)
        self.assertTrue(rev3)
        # Under its new name too, when the release moves folders.
        moved = release.seeds_ever_released(self.source, rev4, LAYOUT)
        self.assertIn("00_AIOS/company/market_analysis/_workspace.md", moved)

    def _exec_release(self):
        write(self.source, "scripts/hook.sh", "#!/bin/sh\necho hook\n")
        os.chmod(os.path.join(self.source, "scripts/hook.sh"), 0o755)
        rev = harness.bump_source(self.source, {}, "a hook")
        return self.v(rev, "2.10.0")

    def test_r5_4_adopt_refuses_a_hook_without_its_executable_bit(self):
        v = self._exec_release()
        install_mod.install(self.target, v, self.source, harness.config())
        os.remove(install_mod.install_record_path(self.target))
        os.chmod(os.path.join(self.target, "scripts/hook.sh"), 0o644)
        with self.assertRaises(Refusal) as ctx:
            install_mod.adopt(self.target, v, self.source, harness.config())
        self.assertIn("permissions differ: scripts/hook.sh", ctx.exception.details)

    def test_r5_4_adopt_pins_the_bit_and_verify_against_the_release_catches_an_edited_record(self):
        v = self._exec_release()
        install_mod.install(self.target, v, self.source, harness.config())
        os.remove(install_mod.install_record_path(self.target))
        record = install_mod.adopt(self.target, v, self.source, harness.config())
        self.assertTrue([e for e in record["managed"] if e["path"] == "scripts/hook.sh"][0]["exec"])
        os.chmod(os.path.join(self.target, "scripts/hook.sh"), 0o644)
        problems, _ = install_mod.verify(self.target)
        self.assertTrue(any("executable permission" in p for p in problems), problems)
        # The record is the operator's to edit; the pinned release is not.
        for e in record["managed"]:
            if e["path"] == "scripts/hook.sh":
                e["exec"] = False
        util.write_json(install_mod.install_record_path(self.target), record)
        self.assertEqual(install_mod.verify(self.target)[0], [])
        problems, _ = install_mod.verify(self.target, source_repo=self.source)
        self.assertTrue(any("does not match the pinned release" in p for p in problems), problems)


class SixthCodexRegressions(InstallerReview):
    """Codex round 6: verify --repo takes the release's own file list and pin, adopt keeps every
    seed, and seed ownership is compared as a case-insensitive disk sees names."""

    def installed(self):
        install_mod.install(self.target, self.v(self.rev, "2.10.0"), self.source, harness.config())
        return install_mod.load_record(self.target)

    def test_r6_1_a_file_dropped_from_the_record_and_the_disk_is_caught(self):
        record = self.installed()
        record["managed"] = [e for e in record["managed"] if e["path"] != "START_HERE.md"]
        os.remove(os.path.join(self.target, "START_HERE.md"))
        util.write_json(install_mod.install_record_path(self.target), record)
        self.assertEqual(install_mod.verify(self.target)[0], [])  # the record agrees with itself
        problems, _ = install_mod.verify(self.target, source_repo=self.source)
        self.assertTrue(any("START_HERE.md" in p and "doesn't list it" in p for p in problems), problems)

    def test_r6_1_the_pin_is_checked_against_the_sources_release_record(self):
        record = self.installed()
        man = harness.build_manifest(self.source, self.rev, "2.10.0")
        harness.bump_source(self.source, {"releases/starter-2.10.0.json": json.dumps(man)})
        problems, summary = install_mod.verify(self.target, source_repo=self.source)
        self.assertEqual(problems, [])
        self.assertEqual(summary["pin_confirmed_by"], "HEAD:releases/starter-2.10.0.json")
        other = harness.bump_source(self.source, {"notes.txt": "x\n"})  # same files, another commit
        record["release"]["git_rev"] = other
        util.write_json(install_mod.install_record_path(self.target), record)
        problems, _ = install_mod.verify(self.target, source_repo=self.source)
        self.assertTrue(any("but HEAD:releases/starter-2.10.0.json pins" in p for p in problems), problems)

    def test_r6_2_adopt_keeps_a_seed_the_client_deleted_and_no_upgrade_brings_it_back(self):
        v = self.v(self.rev, "2.10.0")
        install_mod.install(self.target, v, self.source, harness.config())
        os.remove(install_mod.install_record_path(self.target))
        os.remove(os.path.join(self.target, "06_Communication/decisions_log.md"))
        record = install_mod.adopt(self.target, v, self.source, harness.config())
        self.assertIn({"path": "06_Communication/decisions_log.md", "sha256": ""}, record["seeded"])
        self.commit_target("adopted")
        rev2 = harness.bump_source(self.source, {"START_HERE.md": "# start here\nnext.\n"})
        install_mod.upgrade(self.target, self.v(rev2, "2.10.1"), self.source)
        self.assertFalse(os.path.lexists(os.path.join(self.target, "06_Communication/decisions_log.md")))

    def _seed_then_managed_in_other_case(self):
        spec = dict(harness.PACKAGE_SPEC, seed=harness.PACKAGE_SPEC["seed"] + ["Notes/Plan.md"])
        rev1 = harness.bump_source(self.source, {"Notes/Plan.md": "a seed\n",
                                                 "release/package_spec.json": json.dumps(spec)})
        install_mod.install(self.target, self.v(rev1, "2.10.0", record="tag"), self.source, harness.config())
        os.remove(os.path.join(self.target, "Notes/Plan.md"))
        os.rmdir(os.path.join(self.target, "Notes"))
        self.commit_target("2.10.0, and I deleted the seed")
        run_git(self.source, "rm", "-q", "-r", "Notes")
        return harness.bump_source(self.source, {"notes/plan.md": "the release's now\n",
                                                 "release/package_spec.json": json.dumps(harness.PACKAGE_SPEC)})

    def test_r6_3_a_seed_returning_in_other_case_is_never_taken_over(self):
        rev2 = self._seed_then_managed_in_other_case()
        before = snapshot(self.target)
        with self.assertRaises(Refusal) as ctx:
            install_mod.upgrade(self.target, self.v(rev2, "2.10.1"), self.source)
        self.assertIn("would take over", ctx.exception.message)
        self.assertIn("notes/plan.md", ctx.exception.details)
        self.assertEqual(diff(before, snapshot(self.target)), [])

    def test_r6_3_release_build_folds_case_too(self):
        rev2 = self._seed_then_managed_in_other_case()
        old = harness.build_manifest(self.source, self.rev, "2.10.0")
        old["files"].append({"path": "Notes/Plan.md", "class": "seed", "mode": "100644", "sha256": "0" * 64})
        rev3 = harness.bump_source(self.source, {"releases/starter-2.10.0.json": json.dumps(old)})
        with self.assertRaises(Refusal) as ctx:
            harness.build_manifest(self.source, rev3, "2.10.1")
        self.assertIn("notes/plan.md", ctx.exception.details)
        self.assertTrue(rev2)


class SeventhCodexRegressions(InstallerReview):
    """Codex round 7: a seed the client deleted never comes back, whichever release last shipped it
    and however the new release spells it."""

    def _seed_dropped_deleted_then_shipped_again(self, again="notes/x.md"):
        spec = dict(harness.PACKAGE_SPEC, seed=harness.PACKAGE_SPEC["seed"] + ["notes/x.md", "Notes/**"])
        rev1 = harness.bump_source(self.source, {"notes/x.md": "a seed\n",
                                                 "release/package_spec.json": json.dumps(spec)})
        install_mod.install(self.target, self.v(rev1, "2.10.0"), self.source, harness.config())
        self.commit_target("2.10.0")
        run_git(self.source, "rm", "-q", "notes/x.md")  # 2.10.1 stops shipping it
        install_mod.upgrade(self.target, self.v(harness.bump_source(self.source, {}, "2.10.1"), "2.10.1"),
                            self.source)
        os.remove(os.path.join(self.target, "notes/x.md"))  # and the client deletes it
        os.rmdir(os.path.join(self.target, "notes"))
        self.commit_target("I deleted it")
        return harness.bump_source(self.source, {again: "a seed again\n"})  # 2.10.2 seeds it again

    def assert_not_back(self, rev, name):
        plan = install_mod.upgrade_plan(self.target, self.v(rev, "2.10.2"), self.source)
        self.assertNotIn(name, plan["new_seeds"])
        record = install_mod.upgrade(self.target, self.v(rev, "2.10.2"), self.source)
        self.assertFalse(os.path.lexists(os.path.join(self.target, name)))
        self.assertIn({"path": name, "sha256": ""}, record["seeded"])

    def test_r7_a_seed_shipped_again_after_the_client_deleted_it_stays_deleted(self):
        self.assert_not_back(self._seed_dropped_deleted_then_shipped_again(), "notes/x.md")

    def test_r7_in_another_case_too(self):
        self.assert_not_back(self._seed_dropped_deleted_then_shipped_again("Notes/X.md"), "Notes/X.md")

    def test_r7_in_another_unicode_form_too(self):
        nfd = unicodedata.normalize("NFD", "notes/café.md")
        keys = install_mod._seed_keys({"seeded": [{"path": nfd, "sha256": ""}]}, {})
        self.assertIn(layout_mod.key(unicodedata.normalize("NFC", "notes/café.md")), keys)
        self.assertIn(layout_mod.key("NOTES/CAFÉ.md"), keys)


class EighthCodexRegressions(Layout3):
    """Codex round 8: a record written by a 2.x installer can leave a seed out (one the client already
    had at install, one absent at adopt). The installed release's own seed list fills the gap."""

    def legacy_record_without(self, rel):
        record = install_mod.load_record(self.target)
        record["seeded"] = [e for e in record["seeded"] if e["path"] != rel]
        record.pop("seed_history", None)
        util.write_json(install_mod.install_record_path(self.target), record)
        self.git_commit("a 2.x-style record")

    def test_r8_a_deleted_seed_the_record_never_listed_stays_deleted_under_its_new_name(self):
        self.legacy_record_without("06_Communication/decisions_log.md")  # and the client deleted it
        plan = install_mod.upgrade_plan(self.target, self.v3, self.source, no_vercel=True)
        self.assertNotIn("00_AIOS/decisions_log.md", plan["new_seeds"])
        record = self.up()
        self.assertFalse(os.path.lexists(os.path.join(self.target, "00_AIOS/decisions_log.md")))
        self.assertIn("06_Communication/decisions_log.md", record["seed_history"])

    def test_r8_without_the_old_pin_in_the_source_nothing_is_backfilled(self):
        record = {"release": {"git_rev": "0" * 40}, "seeded": []}
        self.assertEqual(install_mod._seed_history(record, self.v3, self.source), set())


class WorkspaceGuard(Sandbox):
    """Codex round 11: the guard around the workspace lock, on every system, leaving nothing."""

    class FakeMsvcrt(object):
        LK_NBLCK, LK_UNLCK = 2, 0

        def __init__(self, busy=1):
            self.calls, self.busy = [], busy

        def locking(self, fd, mode, nbytes):
            self.calls.append((mode, os.lseek(fd, 0, os.SEEK_CUR), nbytes))
            if mode == self.LK_NBLCK and self.busy:
                self.busy -= 1
                raise OSError("locked by another process")

    def setUp(self):
        super(WorkspaceGuard, self).setUp()
        os.makedirs(os.path.join(self.target, ".aios"))
        self.guard = os.path.join(self.target, ".aios", "backups", "guard")
        self.addCleanup(setattr, install_mod, "_fcntl", install_mod._fcntl)
        self.addCleanup(setattr, install_mod, "_msvcrt", install_mod._msvcrt)

    @unittest.skipIf(os.name == "nt", "Windows can't delete the open guard file")
    def test_it_leaves_no_file_behind_and_nothing_of_the_clients_is_touched(self):
        write(self.target, ".aios/guard", "a file of the client's, at the 3.0 rc's first guard path\n")
        with install_mod._RecoveryGuard(self.target):
            self.assertTrue(os.path.isfile(self.guard))
        self.assertEqual(os.listdir(os.path.join(self.target, ".aios", "backups")), [])
        with open(os.path.join(self.target, ".aios", "guard")) as fh:
            self.assertIn("client's", fh.read())

    @unittest.skipIf(os.name == "nt", "Windows can't delete the open guard file")
    def test_a_waiter_whose_file_was_deleted_locks_the_one_there_now(self):
        real_lock, rounds = install_mod._os_lock, []

        def lock(fd):  # the holder before us finishes and deletes the file as we get its lock
            real_lock(fd)
            rounds.append(os.fstat(fd).st_ino)
            if len(rounds) == 1:
                os.remove(self.guard)
        install_mod._os_lock = lock
        try:
            with install_mod._RecoveryGuard(self.target) as g:
                self.assertEqual(os.fstat(g.fd).st_ino, os.lstat(self.guard).st_ino)
        finally:
            install_mod._os_lock = real_lock
        self.assertEqual(len(rounds), 2)

    def test_windows_locks_the_first_byte_waits_while_busy_and_unlocks(self):
        fake = self.FakeMsvcrt(busy=1)
        install_mod._fcntl, install_mod._msvcrt = None, fake
        with install_mod._RecoveryGuard(self.target):
            pass
        self.assertEqual(fake.calls, [(fake.LK_NBLCK, 0, 1), (fake.LK_NBLCK, 0, 1), (fake.LK_UNLCK, 0, 1)])

    def test_a_system_with_no_file_lock_is_refused_with_nothing_changed(self):
        install_mod._fcntl = install_mod._msvcrt = None
        with self.assertRaises(Refusal):
            with install_mod._RecoveryGuard(self.target):
                self.fail("ran unguarded")
        self.assertEqual(os.listdir(os.path.join(self.target, ".aios")), [])  # not even the folder

    def test_a_linked_aios_folder_is_refused(self):
        outside = os.path.join(self.tmp, "outside")
        os.makedirs(outside)
        shutil.rmtree(os.path.join(self.target, ".aios"))
        os.symlink(outside, os.path.join(self.target, ".aios"))
        with self.assertRaises(Refusal):
            install_mod._RecoveryGuard(self.target).__enter__()
        self.assertEqual(os.listdir(outside), [])


class SecondReviewFounder(FounderReview):

    def test_r2_5_github_enforces_the_default_branchs_file_not_the_local_one(self):
        write(self.target, ".github/CODEOWNERS", self.NEW)  # fixed locally, not merged
        code, out, _err = self.check("ruleset", remote=self.OLD)
        self.assertNotEqual(code, 0)
        self.assertIn("as GitHub enforces it", out)
        self.assertIn("differs from main's", out)

    def test_r2_6_rules_that_beat_sampling_are_caught(self):
        rules = governance.parse("/00_AIOS/company/offer_economics/ @acme-founder\n*.md @acme-va\n"
                                 "a.md @acme-founder\naios-probe.md @acme-founder\n")
        ok, detail = governance.lane_coverage(rules, "00_AIOS/company/offer_economics", {"@acme-founder"})
        self.assertFalse(ok)
        self.assertIn("*.md", detail)


class ReleaseRecord(unittest.TestCase):

    def test_the_real_map_is_total_and_safe(self):
        self.assertEqual(release.check_layout(LAYOUT), [])

    def test_a_map_without_a_catch_all_or_landing_in_an_old_folder_is_refused(self):
        bad = json.loads(json.dumps(LAYOUT))
        bad["moves"] = [m for m in bad["moves"] if m["from"] != "05_Assets/"]
        bad["moves"].append({"from": "09_Archive/x/", "to": "01_Foundations/x/"})
        problems = release.check_layout(bad)
        self.assertTrue(any("05_Assets has no catch-all" in p for p in problems), problems)
        self.assertTrue(any("lands in a retired folder" in p for p in problems), problems)

    def test_every_2x_starter_file_maps_to_its_3_0_home(self):
        """A fresh 3.0 install and an upgraded 2.x workspace hold the starter's files at the same
        paths: every 2.10.0 seed under an old folder maps to a path the 3.0 tree ships (or is a
        file the 3.0 tree retires on purpose)."""
        root = harness.REPO_ROOT
        old_seeds = util.git(root, ["ls-tree", "-r", "--name-only", "starter-2.10.0"]).splitlines() \
            if util.rev_exists(root, "starter-2.10.0") else []
        if not old_seeds:
            self.skipTest("tag starter-2.10.0 isn't in this clone")
        retired_on_purpose = {"11_Projects/README.md", "11_Projects/main-website/main-website.md"}
        missing = []
        for p in old_seeds:
            if p.split("/", 1)[0] not in LAYOUT["retired_roots"] or p.startswith("07_Setup/"):
                continue
            if p in retired_on_purpose:
                continue
            new = layout_mod.destination(p, LAYOUT["moves"])
            if not os.path.isfile(os.path.join(root, new)):
                missing.append("%s -> %s" % (p, new))
        self.assertEqual(missing, [])

    def test_routing_md_lists_every_old_folder(self):
        with open(os.path.join(harness.REPO_ROOT, "00_AIOS", "routing.md"), encoding="utf-8") as fh:
            text = fh.read()
        for root in LAYOUT["retired_roots"]:
            self.assertIn("`%s/`" % root, text, root)

    def test_the_map_line_is_declared_and_in_the_template_once(self):
        spec_file = os.path.join(harness.REPO_ROOT, "release", "package_spec.json")
        spec = util.read_json(spec_file)
        self.assertIn({"path": "CLAUDE.md", "line": MAP_LINE}, spec["seed_lines"])
        with open(os.path.join(harness.REPO_ROOT, "CLAUDE.md"), encoding="utf-8") as fh:
            self.assertEqual(fh.read().splitlines().count(MAP_LINE), 1)


class PlannerUnits(unittest.TestCase):

    def test_destination_longest_rule_wins(self):
        self.assertEqual(layout_mod.destination("02_Deliverables/copy/a.md", LAYOUT["moves"]),
                         "01_Creation/outputs/copy/a.md")
        self.assertEqual(layout_mod.destination("02_Deliverables/a.md", LAYOUT["moves"]),
                         "01_Creation/outputs/a.md")
        self.assertEqual(layout_mod.destination("06_Communication/decisions_log.md", LAYOUT["moves"]),
                         "00_AIOS/decisions_log.md")
        self.assertEqual(layout_mod.destination("11_Projects/site", LAYOUT["moves"]),
                         "02_Team_Ops/projects/site")

    def test_key_folds_case_and_unicode_form(self):
        self.assertEqual(layout_mod.key("Café.md"), layout_mod.key("café.MD"))

    def test_codeowners_last_match_wins(self):
        rules = governance.parse("/00_AIOS/ @a\n/00_AIOS/company/offer_economics/ @f\n")
        self.assertEqual(governance.owners_for(rules, "00_AIOS/company/offer_economics/p.md")[1], ["@f"])
        rules = governance.parse("/00_AIOS/company/offer_economics/ @f\n/00_AIOS/ @a\n")
        self.assertEqual(governance.owners_for(rules, "00_AIOS/company/offer_economics/p.md")[1], ["@a"])


if __name__ == "__main__":
    unittest.main()
