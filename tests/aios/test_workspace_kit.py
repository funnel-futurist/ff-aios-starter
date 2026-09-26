"""The Obsidian Workspace Kit, exercised against real Git repositories on disk.

Every scenario the founder direction names is here: a separate parent vault that is not a
Git repository, only authorized repositories cloned, a dirty checkout left alone, an
unavailable repository reported without stopping the rest, a phase unlocked later, maps
regenerated without losing somebody's edit, core plugins only, and no credential written
anywhere.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import harness

sys.path.insert(0, harness.AIOS_DIR)

from aioslib import workspace  # noqa: E402
from aioslib.util import EXIT_OK, EXIT_PACKAGE, EXIT_STATE, Refusal  # noqa: E402

AIOS = os.path.join(harness.AIOS_DIR, "aios.py")


def git(repo, *args):
    return subprocess.run(["git", "-C", repo] + list(args), check=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE).stdout.decode().strip()


def make_remote(base, name, files):
    """A bare 'GitHub' repository with one commit on main, plus the working copy that made it."""
    work = os.path.join(base, "src-" + name)
    os.makedirs(work)
    git(work, "init", "-q", "-b", "main")
    git(work, "config", "user.email", "fixture@example.invalid")
    git(work, "config", "user.name", "Fixture")
    for rel, text in files.items():
        path = os.path.join(work, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "first")
    bare = os.path.join(base, "remote-" + name + ".git")
    subprocess.run(["git", "clone", "-q", "--bare", work, bare], check=True)
    git(work, "remote", "add", "origin", bare)
    git(work, "fetch", "-q", "origin")
    return work, bare


def push_change(work, rel, text, message="change"):
    with open(os.path.join(work, rel), "w", encoding="utf-8") as fh:
        fh.write(text)
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", message)
    git(work, "push", "-q", "origin", "main")


class KitCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="aios-ws-")
        self.remotes = os.path.join(self.tmp, "remotes")
        os.makedirs(self.remotes)
        self.src = {}
        self.bare = {}
        for name, files in {
            "aios": {"START_HERE.md": "# Company context\n\nSee [the offer](01/offer.md).\n",
                     "01/offer.md": ("# Offer\n\nBroken: [missing](nowhere.md) line.\n"
                                     "Root link [home](/START_HERE.md) and [memory](~/notes/x.md).\n"
                                     "```\n[code](not-a-real-file.md)\n```\n"
                                     "Inline `[code](inline.md)` and [prose](URL).\n")},
            "creation": {"README.md": "# Creation\n\n[brand](brand/guide.md)\n",
                         "brand/guide.md": "# Offer\n\nSame title as the AIOS offer page.\n"},
            "team-ops": {"README.md": "# Team Ops\n"},
            "revops": {"README.md": "# RevOps\n"},
        }.items():
            self.src[name], self.bare[name] = make_remote(self.remotes, name, files)
        self.parent = os.path.join(self.tmp, "Company-Operating-System")
        self.manifest = {
            "schema": workspace.SCHEMA,
            "workspace_name": "Fixture Company Operating System",
            "company": "Fixture Company",
            "repos": {
                "aios": {"domain": "aios", "title": "AIOS", "url": self.bare["aios"],
                         "state": "active", "start_page": "START_HERE.md"},
                "creation": {"domain": "creation", "title": "Creation",
                             "url": self.bare["creation"], "state": "active"},
                "team-ops": {"domain": "team-ops", "title": "Team Ops",
                             "url": self.bare["team-ops"], "state": "active"},
                "revops": {"domain": "revops", "title": "RevOps", "url": self.bare["revops"],
                           "state": "inactive"},
                "command-os": {"domain": "command-os", "title": "Command OS",
                               "url": os.path.join(self.remotes, "not-created-yet.git"),
                               "state": "reference"},
            },
            "capabilities": [{"name": "Document production", "provider": "Funnel Futurist",
                              "domain": "creation", "status": "interface",
                              "description": "brief in, formatted document out"}],
        }

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def init(self, **kw):
        return workspace.init(self.manifest, self.parent, now="2026-09-26T00:00:00Z", **kw)

    def read(self, rel):
        with open(os.path.join(self.parent, rel), encoding="utf-8") as fh:
            return fh.read()


class ManifestRules(KitCase):
    def test_a_url_carrying_a_token_is_refused_without_echoing_it(self):
        self.manifest["repos"]["aios"]["url"] = "https://x-access-token:ghp_FAKEFAKE@github.com/o/r.git"
        problems = workspace.validate(self.manifest)
        self.assertTrue(any("carries a credential" in p for p in problems))
        self.assertFalse(any("ghp_FAKEFAKE" in p for p in problems))

    def test_a_credential_value_instead_of_a_reference_is_refused(self):
        self.manifest["repos"]["aios"]["credential_ref"] = "ghp_literalvalue"
        self.assertTrue(any("never a value" in p for p in workspace.validate(self.manifest)))
        self.manifest["repos"]["aios"]["credential_ref"] = "env:GITHUB_TOKEN"
        self.assertEqual(workspace.validate(self.manifest), [])

    def test_a_path_that_escapes_the_workspace_is_refused(self):
        for bad in ("../elsewhere", "a/b", ".obsidian", "00-MAPS", "/abs"):
            self.manifest["repos"]["aios"]["path"] = bad
            self.assertTrue(workspace.validate(self.manifest), bad)

    def test_the_shipped_example_manifest_is_valid(self):
        with open(os.path.join(workspace.KIT_DIR, "workspace.example.json")) as fh:
            self.assertEqual(workspace.validate(json.load(fh)), [])


class InitAndSync(KitCase):
    def test_init_builds_one_vault_over_separate_repositories(self):
        report = self.init()
        self.assertEqual(report["code"], EXIT_OK, report)
        # The parent is a vault, not a Git repository; each child keeps its own history.
        self.assertFalse(os.path.isdir(os.path.join(self.parent, ".git")))
        self.assertFalse(workspace.inside_git_repo(self.parent))
        for name in ("aios", "creation", "team-ops"):
            self.assertTrue(os.path.isdir(os.path.join(self.parent, name, ".git")), name)
            self.assertFalse(os.path.isdir(os.path.join(self.parent, name, ".obsidian")))
        # Inactive and reference phases are shown, not cloned, and not created as empty repos.
        self.assertFalse(os.path.exists(os.path.join(self.parent, "revops")))
        self.assertFalse(os.path.exists(os.path.join(self.parent, "command-os")))
        for rel in ("START-HERE.md", "WORKSPACE.json", "00-MAPS/Repository Map.md",
                    "00-MAPS/System Relationships.md", "00-MAPS/Knowledge Health.md",
                    "00-MAPS/Operating System.canvas"):
            self.assertTrue(os.path.isfile(os.path.join(self.parent, rel)), rel)
        repo_map = self.read("00-MAPS/Repository Map.md")
        self.assertIn("inactive - not part of this plan yet", repo_map)
        self.assertIn("reference - shown as an interface, not cloned", repo_map)
        self.assertIn(git(os.path.join(self.parent, "aios"), "rev-parse", "HEAD")[:12], repo_map)

    def test_only_core_plugins_publish_and_sync_off_no_community_plugins(self):
        self.init()
        obs = os.path.join(self.parent, ".obsidian")
        with open(os.path.join(obs, "core-plugins.json")) as fh:
            core = json.load(fh)
        for needed in ("file-explorer", "global-search", "backlink", "outgoing-link", "outline",
                       "graph", "canvas", "properties"):
            self.assertTrue(core[needed], needed)
        self.assertFalse(core["publish"])
        self.assertFalse(core["sync"])
        self.assertFalse(os.path.exists(os.path.join(obs, "community-plugins.json")))
        self.assertFalse(os.path.exists(os.path.join(obs, "plugins")))
        with open(os.path.join(obs, "app.json")) as fh:
            app = json.load(fh)
        self.assertFalse(app["alwaysUpdateLinks"], "no automatic cross-repository link rewrites")
        self.assertTrue(app["useMarkdownLinks"])
        # Pane/window state stays local to each person: the kit never ships it.
        self.assertFalse(os.path.exists(os.path.join(obs, "workspace.json")))

    def test_init_refuses_inside_a_git_repository(self):
        inside = os.path.join(self.src["aios"], "vault")
        with self.assertRaises(Refusal) as ctx:
            workspace.init(self.manifest, inside)
        self.assertEqual(ctx.exception.code, EXIT_STATE)
        self.assertFalse(os.path.exists(inside))

    def test_init_refuses_a_folder_that_already_has_other_files(self):
        os.makedirs(self.parent)
        with open(os.path.join(self.parent, "mine.txt"), "w") as fh:
            fh.write("keep")
        with self.assertRaises(Refusal):
            self.init()
        self.assertEqual(os.listdir(self.parent), ["mine.txt"])

    def test_existing_obsidian_settings_are_the_owners(self):
        self.init()
        path = os.path.join(self.parent, ".obsidian", "app.json")
        with open(path, "w") as fh:
            fh.write('{"mine": true}')
        workspace._copy_kit_settings(self.parent)
        with open(path) as fh:
            self.assertEqual(fh.read(), '{"mine": true}')

    def test_an_unavailable_repository_is_reported_and_the_rest_still_set_up(self):
        self.manifest["repos"]["team-ops"]["url"] = os.path.join(self.remotes, "no-access.git")
        report = self.init()
        self.assertEqual(report["code"], EXIT_STATE)
        row = [r for r in report["repos"] if r["name"] == "team-ops"][0]
        self.assertEqual(row["status"], "not connected")
        self.assertIn("gh auth login", row["next"])
        self.assertFalse(os.path.exists(os.path.join(self.parent, "team-ops")))
        self.assertTrue(os.path.isdir(os.path.join(self.parent, "aios", ".git")))
        self.assertIn("not connected", self.read("00-MAPS/Repository Map.md"))

    def test_a_dirty_checkout_is_left_exactly_as_it_is(self):
        self.init()
        local = os.path.join(self.parent, "aios")
        with open(os.path.join(local, "START_HERE.md"), "a") as fh:
            fh.write("my unsaved line\n")
        with open(os.path.join(local, "draft.md"), "w") as fh:
            fh.write("untracked draft\n")
        before = git(local, "rev-parse", "HEAD")
        push_change(self.src["aios"], "01/offer.md", "# Offer\n\nnew upstream\n")
        report = workspace.sync(self.parent, now="2026-09-26T01:00:00Z")
        row = [r for r in report["repos"] if r["name"] == "aios"][0]
        self.assertEqual(row["status"], "dirty")
        self.assertIn("Nothing was changed", row["next"])
        self.assertEqual(report["code"], EXIT_STATE)
        self.assertEqual(git(local, "rev-parse", "HEAD"), before, "no pull into dirty work")
        self.assertEqual(git(local, "stash", "list"), "", "never stashes")
        with open(os.path.join(local, "START_HERE.md")) as fh:
            self.assertIn("my unsaved line", fh.read())
        self.assertTrue(os.path.isfile(os.path.join(local, "draft.md")))

    def test_a_clean_checkout_that_is_behind_moves_forward_only(self):
        self.init()
        push_change(self.src["creation"], "README.md", "# Creation v2\n")
        report = workspace.sync(self.parent)
        row = [r for r in report["repos"] if r["name"] == "creation"][0]
        self.assertTrue(row.get("fast_forwarded"))
        self.assertEqual(row["status"], "clean")
        self.assertEqual(git(os.path.join(self.parent, "creation"), "rev-parse", "HEAD"),
                         git(self.src["creation"], "rev-parse", "HEAD"))

    def test_a_diverged_checkout_is_not_merged_or_reset(self):
        self.init()
        local = os.path.join(self.parent, "team-ops")
        git(local, "config", "user.email", "fixture@example.invalid")
        git(local, "config", "user.name", "Fixture")
        with open(os.path.join(local, "local.md"), "w") as fh:
            fh.write("# Local work\n")
        git(local, "add", "-A")
        git(local, "commit", "-q", "-m", "local work")
        mine = git(local, "rev-parse", "HEAD")
        push_change(self.src["team-ops"], "README.md", "# Team Ops upstream\n")
        report = workspace.sync(self.parent)
        row = [r for r in report["repos"] if r["name"] == "team-ops"][0]
        self.assertEqual(row["status"], "diverged")
        self.assertEqual(git(local, "rev-parse", "HEAD"), mine)

    def test_a_phase_unlock_clones_it_and_the_maps_follow(self):
        self.init()
        self.assertIn("inactive", self.read("00-MAPS/Repository Map.md"))
        path = os.path.join(self.parent, "WORKSPACE.json")
        with open(path) as fh:
            manifest = json.load(fh)
        manifest["repos"]["revops"]["state"] = "active"
        with open(path, "w") as fh:
            json.dump(manifest, fh)
        report = workspace.sync(self.parent)
        row = [r for r in report["repos"] if r["name"] == "revops"][0]
        self.assertTrue(row.get("cloned"))
        self.assertTrue(os.path.isdir(os.path.join(self.parent, "revops", ".git")))
        with open(os.path.join(self.parent, "00-MAPS", "Operating System.canvas")) as fh:
            nodes = {n["id"]: n for n in json.load(fh)["nodes"]}
        self.assertEqual(nodes["repo-revops"]["type"], "file")

    def test_regenerating_maps_keeps_an_edit_and_the_owners_own_notes(self):
        self.init()
        maps = os.path.join(self.parent, "00-MAPS")
        with open(os.path.join(maps, "Repository Map.md"), "a") as fh:
            fh.write("\nmy note on the map\n")
        with open(os.path.join(maps, "my own note.md"), "w") as fh:
            fh.write("mine\n")
        with open(os.path.join(maps, "Operating System.canvas"), "w") as fh:
            fh.write('{"nodes": [], "edges": [], "mine": true}')
        report = workspace.sync(self.parent)
        self.assertTrue(report["maps"]["Repository Map.md"]["kept_your_edit"])
        self.assertIn("my note on the map", self.read("00-MAPS/Repository Map.md"))
        self.assertTrue(os.path.isfile(os.path.join(maps, "Repository Map.new.md")))
        self.assertEqual(self.read("00-MAPS/my own note.md"), "mine\n")
        self.assertIn('"mine": true', self.read("00-MAPS/Operating System.canvas"))
        self.assertTrue(os.path.isfile(os.path.join(maps, "Operating System.new.canvas")))
        # An unedited map is simply replaced, without a .new copy.
        self.assertFalse(report["maps"]["Knowledge Health.md"]["kept_your_edit"])
        self.assertFalse(os.path.exists(os.path.join(maps, "Knowledge Health.new.md")))

    def test_a_nested_vault_in_a_child_is_flagged(self):
        self.init()
        os.makedirs(os.path.join(self.parent, "creation", ".obsidian"))
        report = workspace.sync(self.parent)
        row = [r for r in report["repos"] if r["name"] == "creation"][0]
        self.assertTrue(row.get("nested_vault"))
        self.assertIn("nested vault", self.read("00-MAPS/Knowledge Health.md"))


class Maps(KitCase):
    def test_the_canvas_labels_every_edge_and_keeps_interfaces_outside(self):
        self.init()
        with open(os.path.join(self.parent, "00-MAPS", "Operating System.canvas")) as fh:
            doc = json.load(fh)
        nodes = {n["id"]: n for n in doc["nodes"]}
        group = nodes["client-boundary"]
        self.assertEqual(group["type"], "group")
        self.assertTrue(doc["edges"])
        for edge in doc["edges"]:
            self.assertIn(edge["label"], workspace.EDGE_LABELS)
        cap = nodes["cap-0"]
        self.assertGreaterEqual(cap["x"], group["x"] + group["width"], "interface sits outside")
        self.assertIn("Interface only", cap["text"])
        self.assertIn("inactive", nodes["repo-revops"]["text"])
        self.assertEqual(nodes["repo-aios"]["type"], "file")
        self.assertEqual(nodes["repo-aios"]["file"], "aios/START_HERE.md")
        # AIOS on top, operating domains in the middle, Command OS below.
        self.assertLess(nodes["repo-aios"]["y"], nodes["repo-creation"]["y"])
        self.assertLess(nodes["repo-creation"]["y"], nodes["repo-command-os"]["y"])

    def test_knowledge_health_points_at_the_file_and_line(self):
        self.init()
        health = self.read("00-MAPS/Knowledge Health.md")
        self.assertIn("`aios/01/offer.md:3` -> `nowhere.md`", health)
        self.assertIn('"offer"', health, "same title in two repositories is a candidate")
        self.assertIn("not a defect", health)
        # A repository-root link resolves; code and prose placeholders are not file links;
        # a home-folder link is reported as pointing outside, not as broken.
        self.assertNotIn("START_HERE.md`", health.split("outside this repository")[0])
        for noise in ("not-a-real-file.md", "inline.md", "-> `URL`"):
            self.assertNotIn(noise, health)
        self.assertIn("`aios/01/offer.md:4` -> `~/notes/x.md`", health)
        self.assertIn("Links that point at a missing file: 1", health)

    def test_generated_pages_say_so_and_record_revisions(self):
        self.init()
        text = self.read("00-MAPS/Repository Map.md")
        self.assertTrue(text.startswith("---\ngenerated: true\n"))
        self.assertIn("source_revisions:", text)
        self.assertIn(git(os.path.join(self.parent, "aios"), "rev-parse", "HEAD")[:12], text)


class Cli(KitCase):
    def run_cli(self, *args, env=None):
        return subprocess.run([sys.executable, AIOS, "workspace"] + list(args),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              env=dict(os.environ, **(env or {})))

    def test_plan_changes_nothing_then_init_and_status(self):
        mpath = os.path.join(self.tmp, "manifest.json")
        with open(mpath, "w") as fh:
            json.dump(self.manifest, fh)
        out = self.run_cli("plan", "--manifest", mpath, "--parent", self.parent)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn(b"nothing was changed", out.stdout)
        self.assertFalse(os.path.exists(self.parent))
        secret = "ghp_" + "Z" * 36
        out = self.run_cli("init", "--manifest", mpath, "--parent", self.parent,
                           env={"GITHUB_TOKEN": secret})
        self.assertEqual(out.returncode, 0, out.stderr.decode())
        self.assertIn(b"START-HERE.md", out.stdout)
        out = self.run_cli("status", "--parent", self.parent)
        self.assertIn(b"not active", out.stdout)
        # No credential value lands anywhere in the workspace.
        for dirpath, dirnames, filenames in os.walk(self.parent):
            dirnames[:] = [d for d in dirnames if d != ".git"]
            for f in filenames:
                with open(os.path.join(dirpath, f), "rb") as fh:
                    self.assertNotIn(secret.encode(), fh.read(), f)

    def test_an_invalid_manifest_exits_with_the_package_code(self):
        self.manifest["repos"]["aios"]["url"] = "https://user:pw@example.invalid/r.git"
        mpath = os.path.join(self.tmp, "manifest.json")
        with open(mpath, "w") as fh:
            json.dump(self.manifest, fh)
        out = self.run_cli("init", "--manifest", mpath, "--parent", self.parent)
        self.assertEqual(out.returncode, EXIT_PACKAGE)
        self.assertNotIn(b"user:pw", out.stderr)
        self.assertFalse(os.path.exists(self.parent))


if __name__ == "__main__":
    unittest.main()
