"""Governance and sanitization.

N7 is the canonicalized form of the defect found in this repository on 2026-09-21: a
`CODEOWNERS` file whose owners were literal `[REPO_OWNER]` placeholders, so the rule matched
nobody while looking like a gate. The repo's own drift detector only checked the file
*existed*, which a placeholder file does.

N6 covers the other claim worth attacking: "no secrets and no client names in the package".
"""

import os
import re
import sys

import harness
from harness import Sandbox

sys.path.insert(0, harness.AIOS_DIR)

from aioslib import governance, sanitize, util  # noqa: E402
from aioslib.util import Refusal  # noqa: E402

REAL_ROOT = harness.REPO_ROOT


class CodeownersCheck(Sandbox):

    def _write(self, text, rel=".github/CODEOWNERS"):
        harness.write(self.target, rel, text)
        return self.target

    def test_n7_a_placeholder_owner_fails_the_check(self):
        root = self._write("# aios-codeowners-for: acme/acme-aios\n"
                           "/.github/    [REPO_OWNER] [PRIMARY_REVIEWER]\n")
        problems = governance.check(root, expected_slug="acme/acme-aios")
        self.assertTrue(problems)
        self.assertTrue(any("placeholder" in p for p in problems), problems)
        self.assertTrue(any("enforces nothing" in p for p in problems), problems)

    def test_n7b_the_real_repository_file_is_the_case_that_fails(self):
        """The actual file on this branch, checked as-is. It must fail until a human fills it."""
        problems = governance.check(REAL_ROOT, expected_slug="funnel-futurist/ff-aios-starter")
        self.assertTrue(problems, "if this ever passes with placeholders, the check is broken")

    def test_a5_a_filled_file_passes(self):
        root = self._write("# aios-codeowners-for: acme/acme-aios\n"
                           "/.github/    @acme-founder @acme-reviewer\n")
        self.assertEqual(governance.check(root, expected_slug="acme/acme-aios"), [])

    def test_binding_stops_a_generated_repo_inheriting_foreign_owners(self):
        """The template-inheritance trap: valid handles, wrong repository."""
        root = self._write("# aios-codeowners-for: funnel-futurist/ff-aios-starter\n"
                           "/.github/    @somebody-at-the-publisher\n")
        problems = governance.check(root, expected_slug="acme/acme-aios")
        self.assertTrue(any("match nobody" in p for p in problems), problems)

    def test_a_file_with_no_binding_line_fails(self):
        root = self._write("/.github/    @acme-founder\n")
        problems = governance.check(root, expected_slug="acme/acme-aios")
        self.assertTrue(any("aios-codeowners-for" in p for p in problems), problems)

    def test_a_missing_file_fails(self):
        os.makedirs(self.target, exist_ok=True)
        self.assertTrue(governance.check(self.target, expected_slug="acme/acme-aios"))

    def test_a_malformed_owner_fails(self):
        root = self._write("# aios-codeowners-for: acme/acme-aios\n"
                           "/.github/    acme-founder\n")  # missing @
        problems = governance.check(root, expected_slug="acme/acme-aios")
        self.assertTrue(any("not @user" in p for p in problems), problems)

    def test_an_owner_outside_the_people_map_fails(self):
        root = self._write("# aios-codeowners-for: acme/acme-aios\n"
                           "/.github/    @not-on-this-team\n")
        problems = governance.check(root, expected_slug="acme/acme-aios", config=harness.config())
        self.assertTrue(any("people map" in p for p in problems), problems)

    def test_render_refuses_to_emit_an_unfilled_owner(self):
        with self.assertRaises(Refusal) as ctx:
            governance.render("/.github/  [REPO_OWNER]\n", "acme/acme-aios", {})
        self.assertEqual(ctx.exception.code, util.EXIT_GOVERNANCE)

    def test_render_output_passes_the_check(self):
        with open(os.path.join(REAL_ROOT, "templates", "governance",
                               "CODEOWNERS.template")) as fh:
            template = fh.read()
        text = governance.render(template, "acme/acme-aios",
                                 {"REPO_OWNER": ["@acme-founder"],
                                  "PRIMARY_REVIEWER": ["@acme-reviewer"]})
        root = self._write(text)
        self.assertEqual(governance.check(root, expected_slug="acme/acme-aios"), [])
        self.assertNotIn("[", text.replace("[", "", 0) if False else
                         "\n".join(l for l in text.splitlines()
                                   if not l.strip().startswith("#")))


class Sanitization(Sandbox):

    def _scan(self, files, denylist_terms=None):
        deny_re = None
        if denylist_terms is not None:
            path = os.path.join(self.tmp, "deny.txt")
            with open(path, "w") as fh:
                fh.write("\n".join(denylist_terms) + "\n")
            deny_re = sanitize._denylist_re(sanitize.load_denylist(path))
        return sanitize.scan_files([(p, c.encode() if isinstance(c, str) else c)
                                    for p, c in files], deny_re)

    def test_n6_a_literal_secret_fails(self):
        key = "sk-ant-" + "api03-" + "A" * 40
        findings = self._scan([("config.py", 'KEY = "%s"' % key)])
        self.assertTrue(findings)
        self.assertEqual(findings[0]["kind"], "secret")
        # the finding names the file, never the value
        self.assertNotIn(key, str(findings))

    def test_n6b_a_client_name_fails(self):
        findings = self._scan([("notes.md", "call with Acme Fixture tomorrow")],
                              denylist_terms=["acme_fixture"])
        self.assertTrue(findings)
        self.assertEqual(findings[0]["kind"], "client_name")

    def test_n6c_word_boundaries_stop_the_false_positives_that_kill_a_scanner(self):
        """A substring scan of this very repo flagged `Reporter` and `compounds`."""
        findings = self._scan([("a.md", "the Reporter said it compounds monthly")],
                              denylist_terms=["porter", "pounds"])
        self.assertEqual(findings, [])

    def test_n6d_internal_hosts_fail(self):
        findings = self._scan([("doc.md", "see https://odysseus-production-1234.up.railway.app")])
        self.assertTrue(findings)
        self.assertEqual(findings[0]["kind"], "internal")

    def test_placeholders_and_env_reads_are_not_secrets(self):
        self.assertEqual(self._scan([(".env.example", "ANTHROPIC_API_KEY=your-key-here")]), [])
        self.assertEqual(self._scan([("a.js", "const k = process.env.ANTHROPIC_API_KEY")]), [])

    def test_binaries_are_scanned_not_skipped(self):
        blob = b"\x00\x01\x02" + ("xoxb" + "-1234567890-abcdefghijklmnop").encode() + b"\xff"
        findings = sanitize.scan_files([("asset.bin", blob)])
        self.assertTrue(findings, "a secret inside a binary is still a secret")

    def test_release_mode_refuses_to_run_without_a_denylist(self):
        """You cannot claim "no client names" without the list of names."""
        with self.assertRaises(Refusal) as ctx:
            sanitize.scan_release(self.source, self.rev, ["README.md"], None, "release")
        self.assertEqual(ctx.exception.code, util.EXIT_SANITIZE)

    def test_secret_patterns_stay_in_parity_with_the_pr_floor(self):
        """static_checks.mjs is the repo's single source of truth for secret shapes.

        Parity is asserted on BEHAVIOUR, not on regex text: anything the floor would call a
        secret, this scanner must also catch. Comparing pattern source would break on JS
        escaping and would forbid this scanner from being deliberately stricter.

        Samples are assembled from fragments so this test file contains no contiguous
        matchable literal - otherwise it would trip the very floor it checks.
        """
        js = os.path.join(REAL_ROOT, "scripts", "pr_review", "static_checks.mjs")
        floor_fragments = [f.replace("\\\\", "\\") for f in sanitize.js_floor_fragments(js)]
        self.assertTrue(floor_fragments, "could not parse SECRET_FRAGMENTS out of the floor")
        floor_re = re.compile("(" + "|".join(floor_fragments) + ")", re.I)

        j = lambda *p: "".join(p)  # noqa: E731
        samples = [
            j("sk-", "ant-", "api03-", "A" * 40),
            j("sk-", "a1b2c3d4e5f6g7h8i9j0k1l2"),
            j("xoxb", "-1234567890-abcdefghijklmnop"),
            j("xoxp", "-1234567890-abcdefghijklmnop"),
            j("AKIA", "ABCDEFGHIJKLMNOP"),
            j("ghp_", "a" * 36),
            j("postgresql:", "//user:pass@db.internal:5432/app"),
            j("mongodb", "+srv://user:pass@cluster.example/db"),
            j("-----BEGIN RSA PRIVATE", " KEY-----"),
        ]
        uncovered = [f for f in floor_fragments
                     if not any(re.search(f, s, re.I) for s in samples)]
        self.assertEqual(uncovered, [],
                         "the floor learned a pattern with no sample here; add one: %s"
                         % uncovered)
        for sample in samples:
            self.assertTrue(floor_re.search(sample), "bad sample, floor misses it")
            self.assertTrue(sanitize.SECRET_RE.search(sample),
                            "sanitizer is behind the PR floor for this shape")


class TemplateVersion(Sandbox):
    """Counts carry provenance: the declared skill list must match the tree."""

    def test_template_version_matches_the_actual_skills(self):
        declared = util.read_json(os.path.join(REAL_ROOT, ".template_version.json"))
        actual = sorted(
            d for d in os.listdir(os.path.join(REAL_ROOT, ".claude", "skills"))
            if os.path.isfile(os.path.join(REAL_ROOT, ".claude", "skills", d, "SKILL.md")))
        self.assertEqual(sorted(declared.get("skills") or []), actual,
                         "declared skills drifted from the tree")
        self.assertEqual(declared.get("skill_count"), len(actual))


if __name__ == "__main__":
    import unittest

    unittest.main()
