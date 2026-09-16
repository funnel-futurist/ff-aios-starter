# Skill validation verification

Candidate: b5a7309. Base: c4387053c956e45a3a190c78d3331214a3b09fff.

A clean local clone installed the hook, ran the validator report, and passed all 40 tests. The tests use disposable local bare Git remotes and prove good pushes succeed while invalid outgoing commits fail, including non-current branches, dirty-working-tree mismatch, invalid intermediate history, missing validators, reference deletion across directories/skills, malformed skill roots and templated traversal. Existing pre-push hooks are preserved; the existing skill-root README remains permitted.

An independent review reproduced four bypasses in an earlier candidate. Each was corrected and covered by regression tests before this candidate was committed. The final review and clean-clone test run passed. An actual initial push correctly stopped on a compatibility regression in reference-impact selection; the final candidate preserves existing unrelated skill debt while rejecting newly broken references. Its actual branch push passed.

Existing `.claude/skills` content is unchanged. No skill port or server-side protection change is included. Local hooks require installation and are bypassable; public-safety and code-owner review remain required.

Reproduce:

```sh
bash .githooks/install.sh
python3 scripts/verify_skills.py
python3 tests/test_verify_skills.py
```

Rollback: revert the validation commits and remove only the installed matching pre-push hook; preserve any unrelated hooks or custom integration.
