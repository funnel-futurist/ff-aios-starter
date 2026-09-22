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

from aioslib import governance, release as release_mod, sanitize, util  # noqa: E402
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
            deny_re, _ignored = sanitize._denylist_re(sanitize.load_denylist(path))
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

    def test_enumerable_findings_carry_no_hash_to_confirm_a_guess_against(self):
        """A hash of a client name is not safe to publish; a hash of a real key is."""
        name_hit = self._scan([("notes.md", "call with Acme Fixture")],
                              denylist_terms=["acme_fixture"])[0]
        self.assertEqual(name_hit["fingerprint"], "-")
        url_hit = self._scan([("d.md", "https://x-prod-1.up.railway.app")])[0]
        self.assertEqual(url_hit["fingerprint"], "-")
        secret_hit = self._scan([("c.py", 'K="%s"' % ("sk-ant-" + "api03-" + "A" * 40))])[0]
        self.assertNotEqual(secret_hit["fingerprint"], "-")

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

    def test_generic_denylist_words_are_reported_not_silently_dropped(self):
        """A silent drop is a false negative; a real client can be called Enable."""
        path = os.path.join(self.tmp, "deny2.txt")
        with open(path, "w") as fh:
            fh.write("template\ninternal\nacme_fixture\n")
        deny_re, ignored = sanitize._denylist_re(sanitize.load_denylist(path))
        self.assertEqual(sorted(ignored), ["internal", "template"])
        self.assertTrue(deny_re.search("Acme Fixture"))
        self.assertIsNone(deny_re.search("this is a template"))
        widened, ignored2 = sanitize._denylist_re(sanitize.load_denylist(path),
                                                  allow_generic=True)
        self.assertEqual(ignored2, [])
        self.assertTrue(widened.search("this is a template"))

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


class AdversarialRegressions(Sandbox):
    """Every gap an adversarial review (DeepSeek V4 Pro, 2026-09-22) found and I reproduced.

    Each one was MISSED by the scanner before the fix, reproduced deterministically, then
    closed. They are pinned here so they cannot come back quietly.

    The sample key deliberately avoids the string `EXAMPLE`: AWS's documentation key
    `AKIAIOSFODNN7EXAMPLE` is correctly suppressed as a placeholder, which briefly made the
    fixes look like they had not worked.
    """

    KEY = "AKIA" + "QRSTUVWX12345678"

    def scan(self, path, data, deny=None):
        deny_re = None
        if deny:
            deny_re, _ = sanitize._denylist_re(deny)
        return sanitize.scan_bytes(path, data if isinstance(data, bytes) else data.encode(),
                                   deny_re)

    def test_a_real_key_beside_an_env_read_is_not_suppressed(self):
        """The line-wide allowlist hid a hard-coded fallback key. Fallbacks live exactly there."""
        line = 'const k = process.env.STRIPE_KEY || "sk_live_%s"' % ("0" * 22)
        self.assertTrue(self.scan("config.js", line))

    def test_a_placeholder_is_still_suppressed(self):
        self.assertEqual(self.scan(".env.example", "ANTHROPIC_API_KEY=your-key-here"), [])
        self.assertEqual(self.scan("doc.md", "keys look like sk-ant- (prefix)"), [])

    def test_a_secret_beyond_the_old_line_and_size_caps_is_found(self):
        self.assertTrue(self.scan("long.txt", b"A" * 9000 + self.KEY.encode()))
        self.assertTrue(self.scan("big.txt", b"A" * (1024 * 1024) + b"\n" + self.KEY.encode()))

    def test_an_oversize_file_is_reported_unscanned_not_silently_skipped(self):
        findings = sanitize.scan_bytes("huge.bin", b"A" * (sanitize.MAX_SCAN_BYTES + 1))
        self.assertEqual(findings[0]["kind"], "unscanned")

    def test_utf16_is_decoded(self):
        self.assertTrue(self.scan("u.txt", (self.KEY + "\n").encode("utf-16")))

    def test_zip_and_office_members_are_opened(self):
        import io
        import zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("word/document.xml", self.KEY)
        findings = self.scan("report.docx", buf.getvalue())
        self.assertTrue(findings)
        self.assertIn("!word/document.xml", findings[0]["path"])

    def test_base64_encoded_secrets_are_decoded(self):
        import base64
        blob = base64.b64encode(self.KEY.encode()).decode()
        self.assertTrue(self.scan("c.json", '{"k": "%s"}' % blob))

    def test_shapes_that_were_missing_entirely(self):
        for line in ['K="sk-proj-%s"' % ("a" * 32),
                     'K="sk_test_%s"' % ("5" * 24),
                     'U="mongodb://admin:pw@host:27017"',
                     'U="mysql://root:pw@db:3306/app"']:
            self.assertTrue(self.scan("c", line), line)

    def test_a_client_name_in_the_path_is_found(self):
        findings = self.scan("02_Deliverables/Acme Fixture/readme.md", b"nothing here\n",
                             deny=["Acme Fixture"])
        self.assertTrue(findings)
        self.assertEqual(findings[0]["line"], 0)

    def test_private_and_internal_hosts_are_found(self):
        self.assertTrue(self.scan("e.py", 'U="http://10.0.0.5/admin"'))
        self.assertTrue(self.scan("e.py", 'U="https://api.corp.internal/v1"'))

    def test_a_long_line_does_not_hang_the_scanner(self):
        """Unbounded quantifiers before a literal backtracked O(n^2) and hung on 4MB."""
        import time
        start = time.time()
        sanitize.scan_bytes("x.txt", b"A" * (512 * 1024))
        self.assertLess(time.time() - start, 10.0)

    def test_release_mode_fails_closed_on_unchecked_generic_terms(self):
        path = os.path.join(self.tmp, "deny3.txt")
        with open(path, "w") as fh:
            fh.write("template\nacme_fixture\n")
        with self.assertRaises(Refusal) as ctx:
            sanitize.scan_release(self.source, self.rev, ["README.md"], path, "release")
        self.assertEqual(ctx.exception.code, util.EXIT_SANITIZE)
        # ...and says so rather than quietly narrowing the claim
        self.assertTrue(any("not checked" in d or "ordinary English" in d
                            for d in [ctx.exception.message] + list(ctx.exception.details)))
        findings, _n, ignored = sanitize.scan_release(
            self.source, self.rev, ["README.md"], path, "release", acknowledge_generic=True)
        self.assertEqual(ignored, ["template"])

    def test_the_documented_limitation_is_real_and_stays_documented(self):
        """A secret assembled across lines is NOT detected. Written down, not pretended away."""
        self.assertEqual(self.scan("c.py", 'K = "AKIA"\n    "QRSTUVWX12345678"\n'), [])
        doc = sanitize.__doc__ or ""
        self.assertIn("assembled across lines", doc)


class BytecodeNeverShips(Sandbox):
    """Running the installer generates .pyc files. They must never enter a package.

    Missed locally because macOS's system Python redirects bytecode to a central
    `pycache_prefix`; a Linux CI runner writes it next to the source, `git add -A` swept it
    into the release, and the shipped bytecode then collided with the bytecode the client's
    own workspace generates - blocking every upgrade.
    """

    def test_package_spec_excludes_bytecode(self):
        spec = util.read_json(os.path.join(REAL_ROOT, "release", "package_spec.json"))
        for path in ("scripts/aios/aioslib/__pycache__/util.cpython-312.pyc",
                     "scripts/aios/x.pyc"):
            self.assertIsNone(release_mod.classify(spec, path),
                              "%s would ship" % path)

    def test_the_repo_refuses_to_track_bytecode(self):
        import subprocess
        out = subprocess.run(["git", "-C", REAL_ROOT, "check-ignore",
                              "scripts/aios/aioslib/__pycache__/util.cpython-312.pyc"],
                             stdout=subprocess.PIPE)
        self.assertEqual(out.returncode, 0, "python bytecode is not gitignored")

    def test_a_release_built_from_a_tree_with_bytecode_excludes_it(self):
        harness.write(self.source, "scripts/aios/aioslib/__pycache__/util.cpython-312.pyc",
                      b"\x00fake bytecode")
        harness.run_git(self.source, "add", "-Af")
        harness.run_git(self.source, "commit", "-qm", "bytecode sneaks in")
        rev = util.git(self.source, ["rev-parse", "HEAD"])
        spec = dict(harness.PACKAGE_SPEC)
        spec["exclude"] = list(spec["exclude"]) + ["**/__pycache__/**", "*.pyc"]
        man = release_mod.build(self.source, rev, "1.0.0", spec=spec)
        self.assertFalse([f for f in man["files"] if "__pycache__" in f["path"]])
