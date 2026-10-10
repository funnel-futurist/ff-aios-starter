"""R3-c-2: protected FF method text must not be able to ship in the public tree.

Everything here uses INVENTED text. The real fingerprint list lives outside this repository
and is never needed to run these tests: the public CI proves the mechanism with a fixture, and
the real scan runs where the private list lives (release/PROTECTED_TEXT_SCAN.md).
"""

import io
import json
import os
import sys
import zipfile

import harness
from harness import Sandbox

sys.path.insert(0, harness.AIOS_DIR)

from aioslib import protected, util  # noqa: E402
from aioslib.util import Refusal  # noqa: E402

# Invented. Long enough for many 12-word windows, with nothing in it that is real method.
PLANTED = (
    "The violet harbor ledger works in three quiet passes. First the clerk counts every lantern "
    "that was lit before dawn, then compares that count with the tide table pinned beside the "
    "ferry office door, and only afterwards signs the page in green ink so that nobody downstream "
    "has to guess which count was trusted. A second clerk repeats the pass from the opposite pier "
    "and the two pages are never allowed to meet until both are sealed."
)
OTHER = (
    "Orchard gates are oiled on the first Tuesday of every month by whoever holds the brass key, "
    "and the oiling is written beside the rota in pencil so the next keeper can tell at a glance "
    "whether the hinge on the north gate was skipped again during the wet weeks of early spring."
)


def _list(*pairs, **kw):
    return protected.build_list(list(pairs), **kw)


class Fingerprints(Sandbox):

    def test_the_list_holds_no_text_and_cannot_be_read_back_into_any(self):
        data = _list(("P-001", PLANTED))
        blob = json.dumps(data)
        for word in set(w for w in protected.tokens(PLANTED) if len(w) >= 5):
            self.assertNotIn(word, blob.lower(), "a word of the source is in the list: %r" % word)
        self.assertEqual(data["algorithm"], "hmac-sha256-trunc64")
        for digest in data["sources"]["P-001"]:
            self.assertEqual(len(digest), 16, "truncated to 64 bits, not a full hash of the window")

    def test_the_salt_changes_every_fingerprint(self):
        a = _list(("P-001", PLANTED), salt_hex="00" * 16)
        b = _list(("P-001", PLANTED), salt_hex="11" * 16)
        self.assertFalse(set(a["sources"]["P-001"]) & set(b["sources"]["P-001"]),
                         "an unsalted or shared-salt list can be matched across lists")

    def test_a_source_too_short_to_fingerprint_is_refused_not_ignored(self):
        with self.assertRaises(Refusal) as ctx:
            _list(("P-001", "far too short to carry one window"))
        self.assertEqual(ctx.exception.code, util.EXIT_SANITIZE)

    def test_a_source_label_must_be_opaque_and_short(self):
        with self.assertRaises(Refusal):
            _list(("the real title of a protected document", PLANTED))

    def test_windows_shorter_than_ordinary_prose_are_refused(self):
        with self.assertRaises(Refusal):
            _list(("P-001", PLANTED), window_tokens=3)


class Scan(Sandbox):

    def setUp(self):
        super().setUp()
        self.tree = os.path.join(self.tmp, "public")
        harness.write(self.tree, "README.md", "# a public readme\nnothing protected here\n")
        harness.write(self.tree, ".claude/skills/ordinary/SKILL.md",
                      "# ordinary\n\nA perfectly ordinary skill about writing standups.\n")
        self.fp = _list(("P-001", PLANTED), ("P-002", OTHER))

    def scan(self, allowlist=None):
        return protected.scan_tree(self.tree, self.fp, allowlist)

    def test_a_clean_tree_passes(self):
        findings, scanned, _allowed = self.scan()
        self.assertEqual(findings, [])
        self.assertGreaterEqual(scanned, 2)

    def test_a_planted_protected_paragraph_fails_and_names_path_and_source(self):
        harness.write(self.tree, ".claude/skills/new_skill/SKILL.md",
                      "---\nname: new_skill\n---\n# New\n\n" + PLANTED + "\n")
        findings, _n, _a = self.scan()
        self.assertEqual([(f["path"], f["source"]) for f in findings],
                         [(".claude/skills/new_skill/SKILL.md", "P-001")])
        with self.assertRaises(Refusal) as ctx:
            protected.require_clean(findings)
        self.assertEqual(ctx.exception.code, util.EXIT_SANITIZE)

    def test_the_failure_message_never_repeats_the_protected_text(self):
        harness.write(self.tree, "docs/oops.md", PLANTED)
        findings, _n, _a = self.scan()
        with self.assertRaises(Refusal) as ctx:
            protected.require_clean(findings)
        message = " ".join([ctx.exception.message] + list(ctx.exception.details)).lower()
        for word in ("violet", "lantern", "ferry", "ledger"):
            self.assertNotIn(word, message)

    def test_rewrapping_recasing_and_markdown_do_not_hide_it(self):
        wrapped = "\n> ".join(PLANTED.upper().replace(", ", ",  ").split(". "))
        harness.write(self.tree, "docs/wrapped.md", "> **" + wrapped + "**\n")
        findings, _n, _a = self.scan()
        self.assertEqual([f["path"] for f in findings], ["docs/wrapped.md"])

    def test_the_whole_public_tree_is_scanned_not_only_the_package(self):
        for rel in ("evidence/notes.md", "templates/x.md", "releases/starter-9.9.9.BRIEF.md",
                    "tests/fixtures/y.md", "release/z.md"):
            harness.write(self.tree, rel, PLANTED)
        findings, _n, _a = self.scan()
        self.assertEqual(sorted(f["path"] for f in findings),
                         ["evidence/notes.md", "release/z.md", "releases/starter-9.9.9.BRIEF.md",
                          "templates/x.md", "tests/fixtures/y.md"])

    def test_text_inside_an_office_file_is_found(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("word/document.xml", "<w:t>%s</w:t>" % PLANTED)
        harness.write(self.tree, "05_Assets/guide.docx", buf.getvalue())
        findings, _n, _a = self.scan()
        self.assertEqual([f["path"] for f in findings], ["05_Assets/guide.docx"])

    def test_a_short_shared_phrase_is_not_a_finding(self):
        harness.write(self.tree, "docs/quote.md",
                      "As the note says: " + " ".join(protected.tokens(PLANTED)[:11]) + " and no more.\n")
        findings, _n, _a = self.scan()
        self.assertEqual(findings, [], "one short quotation must not make the check cry wolf")

    def test_each_source_is_reported_separately(self):
        harness.write(self.tree, "docs/both.md", PLANTED + "\n\n" + OTHER)
        findings, _n, _a = self.scan()
        self.assertEqual(sorted(f["source"] for f in findings), ["P-001", "P-002"])

    def test_an_oversize_file_is_reported_unscanned_not_waved_through(self):
        big = os.path.join(self.tree, "docs", "huge.bin")
        os.makedirs(os.path.dirname(big), exist_ok=True)
        with open(big, "wb") as fh:
            fh.truncate(protected.sanitize.MAX_SCAN_BYTES + 1)
        findings, _n, _a = self.scan()
        self.assertEqual([(f["path"], f["kind"]) for f in findings], [("docs/huge.bin", "unscanned")])


class AllowList(Sandbox):
    """The allow-list is explicit, reasoned and pinned to the exact bytes a founder approved."""

    def setUp(self):
        super().setUp()
        self.tree = os.path.join(self.tmp, "public")
        self.method = ".claude/skills/public_method/SKILL.md"
        harness.write(self.tree, self.method, "# method\n\n" + PLANTED + "\n")
        self.fp = _list(("P-001", PLANTED))
        self.allow = {"schema": protected.ALLOWLIST_SCHEMA, "public_methods": [
            {"path": self.method, "reason": "public on purpose (test)",
             "sha256": util.sha256_file(os.path.join(self.tree, self.method))}]}

    def test_the_text_is_a_finding_without_the_entry_and_not_with_it(self):
        self.assertEqual(len(protected.scan_tree(self.tree, self.fp, None)[0]), 1)
        findings, _n, allowed = protected.scan_tree(self.tree, self.fp, self.allow)
        self.assertEqual(findings, [])
        self.assertEqual(allowed, [self.method])

    def test_the_exemption_is_for_that_file_only(self):
        harness.write(self.tree, "docs/copy.md", PLANTED)
        findings, _n, _a = protected.scan_tree(self.tree, self.fp, self.allow)
        self.assertEqual([f["path"] for f in findings], ["docs/copy.md"])

    def test_editing_an_allowed_file_turns_the_check_red_until_it_is_re_pinned(self):
        self.assertEqual(protected.check_allowlist(self.tree, self.allow), [])
        with open(os.path.join(self.tree, self.method), "a") as fh:
            fh.write("\nA new paragraph nobody approved as public.\n")
        problems = protected.check_allowlist(self.tree, self.allow)
        self.assertTrue(any("changed since a founder approved" in p for p in problems), problems)

    def test_pin_rewrites_the_hash_and_only_the_hash(self):
        path = os.path.join(self.tmp, "public_methods.json")
        util.write_json(path, self.allow)
        with open(os.path.join(self.tree, self.method), "a") as fh:
            fh.write("\nreviewed addition\n")
        protected.pin_allowlist(self.tree, path)
        again = util.read_json(path)
        self.assertEqual(protected.check_allowlist(self.tree, again), [])
        self.assertEqual(again["public_methods"][0]["reason"], "public on purpose (test)")

    def test_a_stale_entry_a_missing_reason_and_a_duplicate_are_all_problems(self):
        bad = {"schema": protected.ALLOWLIST_SCHEMA, "public_methods": [
            {"path": "docs/gone.md", "reason": "x", "sha256": "0"},
            {"path": self.method, "reason": "", "sha256": self.allow["public_methods"][0]["sha256"]},
            {"path": self.method, "reason": "again", "sha256": self.allow["public_methods"][0]["sha256"]}]}
        problems = " | ".join(protected.check_allowlist(self.tree, bad))
        self.assertIn("does not exist", problems)
        self.assertIn("has no reason", problems)
        self.assertIn("listed twice", problems)


class Cli(Sandbox):
    """The shipped commands, end to end, as a maintainer and as CI would run them."""

    def setUp(self):
        super().setUp()
        self.tree = os.path.join(self.tmp, "public")
        self.method = "docs/METHOD.md"
        harness.write(self.tree, "README.md", "# public\n")
        harness.write(self.tree, self.method, PLANTED)
        self.private = os.path.join(self.tmp, "private")
        harness.write(self.private, "source.md", PLANTED)
        self.list_path = os.path.join(self.private, "fingerprints.json")
        self.allow_path = os.path.join(self.tmp, "public_methods.json")
        util.write_json(self.allow_path, {"schema": protected.ALLOWLIST_SCHEMA, "public_methods": []})

    def make_list(self):
        return self.cli("protected", "fingerprint", "--source",
                        "P-001=" + os.path.join(self.private, "source.md"), "--out", self.list_path)

    def scan(self, *extra, **kw):
        return self.cli("protected", "scan", "--repo", self.tree, "--allowlist", self.allow_path, *extra, **kw)

    def test_fingerprint_then_scan_fails_with_the_sanitize_exit_code_and_no_text(self):
        code, out, err = self.make_list()
        self.assertEqual(code, 0, err)
        with open(self.list_path) as fh:
            self.assertNotIn("violet", fh.read().lower())
        code, out, err = self.scan("--fingerprints", self.list_path)
        self.assertEqual(code, util.EXIT_SANITIZE, out + err)
        self.assertIn("docs/METHOD.md", err)
        self.assertNotIn("violet", (out + err).lower())

    def test_the_scan_passes_once_a_founder_lists_the_file(self):
        self.make_list()
        util.write_json(self.allow_path, {"schema": protected.ALLOWLIST_SCHEMA, "public_methods": [
            {"path": self.method, "reason": "public on purpose (test)",
             "sha256": util.sha256_file(os.path.join(self.tree, self.method))}]})
        code, out, err = self.scan("--fingerprints", self.list_path)
        self.assertEqual(code, 0, out + err)
        self.assertIn("docs/METHOD.md", out)

    def test_no_list_means_no_clean_claim(self):
        code, _out, err = self.scan(env={protected.ENV_LIST: ""})
        self.assertEqual(code, util.EXIT_SANITIZE)
        self.assertIn("cannot say 'clean' without having looked", err)

    def test_the_list_can_come_from_the_environment(self):
        self.make_list()
        code, _out, _err = self.scan(env={protected.ENV_LIST: self.list_path})
        self.assertEqual(code, util.EXIT_SANITIZE)

    def test_an_allowlist_out_of_order_stops_the_scan_before_it_trusts_it(self):
        self.make_list()
        util.write_json(self.allow_path, {"schema": protected.ALLOWLIST_SCHEMA, "public_methods": [
            {"path": self.method, "reason": "ok", "sha256": "deadbeef"}]})
        code, _out, err = self.scan("--fingerprints", self.list_path)
        self.assertEqual(code, util.EXIT_SANITIZE)
        self.assertIn("changed since a founder approved", err)


class TheRealPublicTree(Sandbox):
    """The allow-list shipped in this repository, held to the same standard."""

    REPO = harness.REPO_ROOT
    SEVEN = [
        ".claude/skills/f6_completeness_check/SKILL.md",
        ".claude/skills/financial_teardown/SKILL.md",
        ".claude/skills/grill_me/SKILL.md",
        ".claude/skills/humanize/SKILL.md",
        ".claude/skills/project_management/SKILL.md",
        ".claude/skills/qc_review/SKILL.md",
        "docs/UNSTUCK_PROTOCOL.md",
    ]

    def allowlist(self):
        return protected.load_allowlist(os.path.join(self.REPO, protected.DEFAULT_ALLOWLIST))

    def test_the_allowlist_names_the_seven_public_method_files_explicitly(self):
        paths = sorted(e["path"] for e in self.allowlist()["public_methods"])
        self.assertEqual(paths, self.SEVEN)
        for entry in self.allowlist()["public_methods"]:
            self.assertTrue(entry["reason"].strip())

    def test_every_entry_exists_and_matches_its_approved_bytes(self):
        self.assertEqual(protected.check_allowlist(self.REPO, self.allowlist()), [])

    def test_the_allowlist_does_not_decide_the_founders_question(self):
        data = self.allowlist()
        self.assertIn("pending founder", data["decision"])

    def test_the_allowlist_is_what_exempts_them_and_the_real_tree_is_otherwise_clean(self):
        # Fingerprint one of the seven (its text is already public) and scan the real tree.
        # With the allow-list the tree is clean; without it the file is the one finding.
        # That proves the scan reads the real tree and that the exemption is the explicit list.
        method = self.SEVEN[1]
        with open(os.path.join(self.REPO, method), encoding="utf-8") as fh:
            fp = protected.build_list([("P-TEST", fh.read())])
        findings, _n, allowed = protected.scan_tree(self.REPO, fp, self.allowlist())
        self.assertEqual(findings, [])
        self.assertIn(method, allowed)
        without, _n2, _a2 = protected.scan_tree(self.REPO, fp, None)
        self.assertEqual([f["path"] for f in without], [method])

    def test_the_real_tree_is_scanned_whole_including_evidence_and_templates(self):
        scanned = set(protected.tracked_or_walked(self.REPO))
        self.assertIn("templates/workspace-kit/workspace.example.json", scanned)
        self.assertIn("releases/starter-2.7.2.BRIEF.md", scanned)
        self.assertIn("release/package_spec.json", scanned)

    def test_the_public_ci_runs_the_allowlist_check_and_the_private_scan_is_optional_and_loud(self):
        with open(os.path.join(self.REPO, ".github/workflows/install-contract.yml"), encoding="utf-8") as fh:
            wf = fh.read()
        self.assertIn("protected scan", wf)
        self.assertIn("protected check-allowlist", wf)
        self.assertIn("NOT RUN", wf, "a skipped real scan must say so, not pass silently")
