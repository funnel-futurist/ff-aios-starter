"""LW-22 part 1: an installed workspace hears, at most once a day, that a newer approved release exists.

Read-only and silent on failure. A release is named only when the record on `main` and the record
inside its tag both say approved, pinned to the same commit, so a superseded, withdrawn or draft
release is never advertised. No test here touches the network: the tag list and the record
fetches are injected.
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

from aioslib import notice  # noqa: E402

DAY = 24 * 3600
PIN = "a" * 40
# What every installer writes at the top of an install record (3.1 round 50 checks both).
RECORD_HEAD = {"schema": "ff-aios-starter/install@1", "package": "ff-aios-starter"}


def record(status, pin=PIN):
    return {"status": status, "created_from": {"git_rev": pin}}


def tags(*versions):
    return lambda: [tuple(int(x) for x in v.split(".")) for v in versions]


class Fetch(object):
    """Fake record fetches: {(ref, version): record or None}. Counts calls."""

    def __init__(self, table):
        self.table, self.calls = table, []

    def __call__(self, ref, version):
        self.calls.append((ref, version))
        return self.table.get((ref, version))


class Notice(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.old_optout = os.environ.pop("AIOS_NO_RELEASE_NOTICE", None)
        self.addCleanup(self._restore)
        self.install("2.8.0")

    def _restore(self):
        if self.old_optout is not None:
            os.environ["AIOS_NO_RELEASE_NOTICE"] = self.old_optout

    def install(self, version):
        os.makedirs(os.path.join(self.tmp, ".aios"), exist_ok=True)
        with open(os.path.join(self.tmp, ".aios", "install.json"), "w") as fh:
            json.dump(dict(RECORD_HEAD, release={"version": version, "release_id": "starter-" + version}), fh)

    def approved_290(self):
        return Fetch({("main", "2.9.0"): record("approved"), ("starter-2.9.0", "2.9.0"): record("approved")})

    def test_a_newer_approved_release_is_named(self):
        line = notice.check(self.tmp, now=1000, tags_fn=tags("2.7.2", "2.8.0", "2.9.0"), fetch_fn=self.approved_290())
        self.assertIn("Starter 2.9.0 is approved; this workspace has 2.8.0", line)
        self.assertIn("check-tag", line)

    def test_nothing_when_the_workspace_is_current(self):
        self.install("2.9.0")
        f = self.approved_290()
        self.assertIsNone(notice.check(self.tmp, now=1000, tags_fn=tags("2.8.0", "2.9.0"), fetch_fn=f))
        self.assertEqual(f.calls, [], "no record is read when no tag is newer")

    def test_superseded_withdrawn_or_draft_on_main_is_never_advertised(self):
        for status in ("superseded", "withdrawn", "draft"):
            os.path.exists(os.path.join(self.tmp, notice.CACHE)) and os.remove(os.path.join(self.tmp, notice.CACHE))
            f = Fetch({("main", "2.9.0"): record(status), ("starter-2.9.0", "2.9.0"): record("approved")})
            self.assertIsNone(notice.check(self.tmp, now=1000, tags_fn=tags("2.9.0"), fetch_fn=f), status)

    def test_the_tag_must_carry_the_approval_pinned_to_the_same_commit(self):
        for at_tag in (record("draft"), record("approved", pin="b" * 40)):
            os.path.exists(os.path.join(self.tmp, notice.CACHE)) and os.remove(os.path.join(self.tmp, notice.CACHE))
            f = Fetch({("main", "2.9.0"): record("approved"), ("starter-2.9.0", "2.9.0"): at_tag})
            self.assertIsNone(notice.check(self.tmp, now=1000, tags_fn=tags("2.9.0"), fetch_fn=f))

    def test_the_newest_good_release_wins_and_a_bad_newer_one_is_skipped(self):
        f = Fetch({("main", "2.10.0"): record("withdrawn"),
                   ("main", "2.9.0"): record("approved"), ("starter-2.9.0", "2.9.0"): record("approved")})
        line = notice.check(self.tmp, now=1000, tags_fn=tags("2.9.0", "2.10.0"), fetch_fn=f)
        self.assertIn("Starter 2.9.0 is approved", line)

    def test_at_most_one_network_check_a_day(self):
        notice.check(self.tmp, now=1000, tags_fn=tags("2.9.0"), fetch_fn=self.approved_290())

        def no_network():
            raise AssertionError("network called within the day")
        self.assertIn("2.9.0", notice.check(self.tmp, now=1000 + DAY - 1, tags_fn=no_network))
        f = self.approved_290()
        notice.check(self.tmp, now=1000 + DAY + 1, tags_fn=tags("2.9.0"), fetch_fn=f)
        self.assertTrue(f.calls, "a day later it checks again")

    def test_an_upgrade_ignores_the_old_cache(self):
        notice.check(self.tmp, now=1000, tags_fn=tags("2.9.0"), fetch_fn=self.approved_290())
        self.install("2.9.0")
        self.assertIsNone(notice.check(self.tmp, now=1001, tags_fn=tags("2.9.0"), fetch_fn=self.approved_290()))

    def no_network(self):
        raise AssertionError("network called inside the back-off window")

    def test_offline_is_silent_and_backs_off_for_an_hour_not_a_day(self):
        self.assertIsNone(notice.check(self.tmp, now=1000, tags_fn=lambda: [], fetch_fn=self.approved_290()))
        # Offline costs one delay an hour, not one per session start.
        self.assertIsNone(notice.check(self.tmp, now=1000 + notice.RETRY - 1, tags_fn=self.no_network))
        line = notice.check(self.tmp, now=1000 + notice.RETRY + 1, tags_fn=tags("2.9.0"), fetch_fn=self.approved_290())
        self.assertIn("2.9.0", line)

    def test_an_unreadable_record_is_unknown_and_retried_after_an_hour(self):
        f = Fetch({})          # every fetch fails
        self.assertIsNone(notice.check(self.tmp, now=1000, tags_fn=tags("2.9.0"), fetch_fn=f))
        self.assertIsNone(notice.check(self.tmp, now=1001, tags_fn=self.no_network))
        self.assertIn("2.9.0", notice.check(self.tmp, now=1000 + notice.RETRY + 1, tags_fn=tags("2.9.0"),
                                            fetch_fn=self.approved_290()))

    def test_the_whole_check_stays_inside_its_time_budget(self):
        ticks = iter([0, notice.BUDGET + 1, notice.BUDGET + 2, notice.BUDGET + 3])  # deadline, then spent
        f = self.approved_290()
        line = notice.check(self.tmp, now=1000, tags_fn=tags("2.9.0"), fetch_fn=f, clock=lambda: next(ticks))
        self.assertIsNone(line)
        self.assertEqual(f.calls, [], "no call starts once the budget is spent")
        # Out of budget is "unknown": retried after the short window, not a day later.
        self.assertIn("2.9.0", notice.check(self.tmp, now=1000 + notice.RETRY + 1, tags_fn=tags("2.9.0"),
                                            fetch_fn=self.approved_290()))

    def test_only_the_newest_few_candidates_are_read(self):
        f = Fetch({})
        notice.check(self.tmp, now=1000, tags_fn=tags("2.9.0", "2.10.0", "2.11.0", "2.12.0", "2.13.0"), fetch_fn=f)
        self.assertEqual(len({v for _ref, v in f.calls}), notice.CANDIDATES)

    def test_not_an_installed_workspace_says_nothing(self):
        os.remove(os.path.join(self.tmp, ".aios", "install.json"))
        self.assertIsNone(notice.check(self.tmp, now=1000, tags_fn=tags("9.9.9"), fetch_fn=self.approved_290()))

    def test_the_opt_out_makes_no_check_at_all(self):
        os.environ["AIOS_NO_RELEASE_NOTICE"] = "1"
        self.addCleanup(os.environ.pop, "AIOS_NO_RELEASE_NOTICE", None)

        def no_network():
            raise AssertionError("network called despite the opt-out")
        self.assertIsNone(notice.check(self.tmp, now=1000, tags_fn=no_network))


class RealHook(unittest.TestCase):
    """The SessionStart hook prints the notice, from the real hook script and the real CLI."""

    def setUp(self):
        if not shutil.which("node"):
            self.skipTest("node is not installed")
        self.ws = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.ws)
        shutil.copytree(os.path.join(harness.REPO_ROOT, "scripts"), os.path.join(self.ws, "scripts"))
        os.makedirs(os.path.join(self.ws, ".aios"))
        with open(os.path.join(self.ws, ".aios", "install.json"), "w") as fh:
            json.dump(dict(RECORD_HEAD, release={"version": "2.8.0"}), fh)
        subprocess.run(["git", "init", "-q", self.ws], check=True)

    def run_hook(self):
        env = {"PATH": os.environ.get("PATH", ""), "HOME": self.ws, "CLAUDE_PROJECT_DIR": self.ws}
        hook = os.path.join(harness.REPO_ROOT, ".claude", "hooks", "git-staleness-check.js")
        return subprocess.run(["node", hook], capture_output=True, text=True, env=env, cwd=self.ws, timeout=60)

    def test_the_hook_shows_a_fresh_cached_notice_without_any_network(self):
        import time
        line = notice.line_for("2.8.0", "2.9.0")
        with open(os.path.join(self.ws, notice.CACHE), "w") as fh:
            json.dump({"checked_at": time.time(), "installed": "2.8.0", "line": line}, fh)
        out = self.run_hook()
        self.assertEqual(out.returncode, 0)
        self.assertIn(line, out.stdout)

    def test_the_hook_stays_quiet_when_there_is_nothing_to_say(self):
        import time
        with open(os.path.join(self.ws, notice.CACHE), "w") as fh:
            json.dump({"checked_at": time.time(), "installed": "2.8.0", "line": None}, fh)
        out = self.run_hook()
        self.assertEqual(out.returncode, 0)
        self.assertNotIn("is approved", out.stdout)


if __name__ == "__main__":
    unittest.main()
