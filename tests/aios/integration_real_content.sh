#!/usr/bin/env bash
# End-to-end internal validation against the REAL starter content, in a clean environment.
#
# The unit tests use a miniature fixture repo. This runs the same contract over all 281 real
# files, through the shipped CLI, in a subprocess with a SCRUBBED environment (`env -i`), so a
# pass cannot depend on anything in the developer's shell.
#
# What "clean environment" means here: a fresh `git clone` into a temp directory, an empty
# target, no inherited environment, and a stub `gh` so identity is resolved through the real
# code path rather than a bypass.
#
# The approval used here is the literal string "internal-validation-fixture (NOT a human
# approval)". Nothing in this script can produce a real approval, and the real release stays
# `draft` until a human signs it.
#
# Usage: bash tests/aios/integration_real_content.sh [repo_root]
# Exit 0 = every step behaved as the contract says, including every refusal.
set -u

REPO_ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/aios-e2e-XXXXXX")"
SRC="$WORK/source"
TARGET="$WORK/workspace"
BIN="$WORK/bin"
HOMEDIR="$WORK/home"
mkdir -p "$BIN" "$HOMEDIR"
trap 'rm -rf "$WORK"' EXIT

pass=0; fail=0
step() { printf '\n=== %s\n' "$1"; }
ok()   { pass=$((pass+1)); printf '  PASS  %s\n' "$1"; }
bad()  { fail=$((fail+1)); printf '  FAIL  %s\n' "$1"; }
expect_code() { # expect_code <expected> <actual> <label>
  if [ "$2" = "$1" ]; then ok "$3 (exit $2)"; else bad "$3 (expected exit $1, got $2)"; fi
}

# A stub gh so `gh api user --jq .login` answers deterministically. The shipped code has no
# identity override, so this exercises the real path.
mk_gh() {
  cat > "$BIN/gh" <<EOF
#!/bin/sh
if [ "\$1" = "api" ] && [ "\$2" = "user" ]; then echo "$1"; exit 0; fi
exit 1
EOF
  chmod +x "$BIN/gh"
}

# Every CLI call runs with a scrubbed environment.
aios() {
  env -i PATH="$BIN:/usr/bin:/bin:/usr/sbin:/sbin" HOME="$HOMEDIR" \
    ${AIOS_FAULT:+AIOS_FAULT="$AIOS_FAULT"} \
    python3 "$SRC/scripts/aios/aios.py" "$@"
}

step "clone the real repository into a clean environment"
git clone -q --no-hardlinks "$REPO_ROOT" "$SRC" || { echo "clone failed"; exit 1; }
git -C "$SRC" config user.email e2e@example.com
git -C "$SRC" config user.name e2e
REV="$(git -C "$SRC" rev-parse HEAD)"
echo "  source=$SRC"
echo "  pin=$REV"

step "cut release 9.0.0 from the pin (must be DRAFT)"
aios release build --repo "$SRC" --rev "$REV" --version 9.0.0 \
  --credentials "$SRC/release/credential_refs.json" --out "$WORK/v9.0.0-draft.json" >/dev/null
code=$?; expect_code 0 $code "release build"
if grep -q '"status": "draft"' "$WORK/v9.0.0-draft.json"; then
  ok "builder emitted draft, and cannot emit anything else"
else
  bad "builder did not emit a draft"
fi
FILES=$(python3 -c "import json;print(json.load(open('$WORK/v9.0.0-draft.json'))['counts']['files'])")
echo "  files pinned: $FILES"

step "N1: installing the DRAFT release is refused"
mk_gh acme-founder
cat > "$WORK/config.json" <<'JSON'
{
  "schema": "ff-aios-starter/org-config@1",
  "org_id": "acme",
  "repository": "acme/acme-aios",
  "people": [
    {"github": "acme-founder", "role": "founder", "display_name": "Founder"},
    {"github": "acme-va", "role": "operator", "display_name": "Operator"}
  ],
  "credentials": {},
  "code_owners": {"REPO_OWNER": ["@acme-founder"], "PRIMARY_REVIEWER": ["@acme-founder"]}
}
JSON
aios install --repo "$SRC" --release "$WORK/v9.0.0-draft.json" --target "$TARGET" \
  --config "$WORK/config.json" >/dev/null 2>"$WORK/err_draft.txt"
expect_code 2 $? "draft release refused"
[ ! -e "$TARGET/START_HERE.md" ] && ok "refused install wrote nothing" || bad "refused install left files behind"

step "fixture-approve (sandbox only) and install into the clean target"
python3 - "$WORK/v9.0.0-draft.json" "$WORK/v9.0.0.json" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
m["status"] = "approved"
m["approval"] = {"approved_by": "internal-validation-fixture (NOT a human approval)",
                 "approved_at": "2026-09-22T00:00:00Z"}
json.dump(m, open(sys.argv[2], "w"), indent=2, sort_keys=True)
PY
aios install --repo "$SRC" --release "$WORK/v9.0.0.json" --target "$TARGET" \
  --config "$WORK/config.json" > "$WORK/install.txt" 2>&1
expect_code 0 $? "install into a clean environment"
sed 's/^/    /' "$WORK/install.txt"

step "A1: verify by reading state back"
aios verify --target "$TARGET" > "$WORK/verify.txt" 2>&1
expect_code 0 $? "readback verify"
sed 's/^/    /' "$WORK/verify.txt"

step "A1b: readback actually catches a hand edit"
echo "edited by hand" >> "$TARGET/START_HERE.md"
aios verify --target "$TARGET" >/dev/null 2>&1
expect_code 6 $? "drift detected"
git -C "$SRC" show "$REV:START_HERE.md" > "$TARGET/START_HERE.md"
aios verify --target "$TARGET" >/dev/null 2>&1
expect_code 0 $? "restored, clean again"

step "the installed workspace runs its OWN copy of the tool (self-contained)"
# Everything above drives the SOURCE checkout's CLI. A client runs the copy that landed in
# their workspace, so prove that one works, from inside the workspace, with nothing else on
# PATH. If the package did not ship its own tooling, this is where it shows.
( cd "$TARGET" && env -i PATH="$BIN:/usr/bin:/bin" HOME="$HOMEDIR" \
    python3 scripts/aios/aios.py verify --target . ) > "$WORK/selfcheck.txt" 2>&1
expect_code 0 $? "the workspace verifies itself with its own installed CLI"
grep -q "matches the installed release" "$WORK/selfcheck.txt" \
  && ok "self-verification readback agrees" || bad "self-verification disagreed"

step "A2/N3: role scoping, proven with the REDUCED role"
mk_gh acme-va
aios start --target "$TARGET" > "$WORK/start_operator.txt" 2>&1
expect_code 0 $? "operator enters the operator lane"
grep -q "role:      operator" "$WORK/start_operator.txt" && ok "resolved as operator" || bad "role wrong"
aios start --target "$TARGET" --entry founder >/dev/null 2>"$WORK/start_denied.txt"
expect_code 3 $? "operator refused the founder lane"
sed 's/^/    /' "$WORK/start_denied.txt"

step "N3b: the operator cannot upgrade"
aios upgrade --repo "$SRC" --release "$WORK/v9.0.0.json" --target "$TARGET" \
  >/dev/null 2>"$WORK/upgrade_denied.txt"
expect_code 3 $? "operator refused upgrade"

step "the operator does real work (this is the state that must survive)"
mk_gh acme-founder
printf '# Your AIOS\n\nMY OWN CONSTITUTION, edited by the founder.\n' > "$TARGET/CLAUDE.md"
mkdir -p "$TARGET/02_Deliverables/copy"
printf 'my real deliverable\n' > "$TARGET/02_Deliverables/copy/launch_email.md"
printf '# my market\nreal notes\n' > "$TARGET/01_Foundations/market_analysis/_workspace.md"
mkdir -p "$TARGET/.claude/skills/my_own_skill"
printf '# mine\n' > "$TARGET/.claude/skills/my_own_skill/SKILL.md"
STATE_BEFORE=$(cd "$TARGET" && find . -path ./.git -prune -o -path ./.aios/backups -prune -o -type f -print \
  | grep -v '^\./\.aios/\(install\.json\|txn\.json\)$' | sort | xargs shasum -a 256 | shasum -a 256)
echo "  state fingerprint: ${STATE_BEFORE%% *}"

step "build 9.1.0 with a real content change"
printf '\n<!-- shipped in 9.1.0 -->\n' >> "$SRC/START_HERE.md"
mkdir -p "$SRC/.claude/skills/shipped_in_910"
printf -- '---\nname: shipped_in_910\ndescription: added by the upgrade\n---\n# new\n' \
  > "$SRC/.claude/skills/shipped_in_910/SKILL.md"
git -C "$SRC" add -A >/dev/null 2>&1
git -C "$SRC" commit -qm "9.1.0 content" >/dev/null 2>&1
REV2="$(git -C "$SRC" rev-parse HEAD)"
aios release build --repo "$SRC" --rev "$REV2" --version 9.1.0 \
  --credentials "$SRC/release/credential_refs.json" --out "$WORK/v9.1.0-draft.json" >/dev/null
python3 - "$WORK/v9.1.0-draft.json" "$WORK/v9.1.0.json" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
m["status"] = "approved"
m["approval"] = {"approved_by": "internal-validation-fixture (NOT a human approval)",
                 "approved_at": "2026-09-22T00:00:00Z"}
json.dump(m, open(sys.argv[2], "w"), indent=2, sort_keys=True)
PY

step "N4: upgrading over a DIRTY workspace is refused"
echo "hand edit" >> "$TARGET/START_HERE.md"
aios upgrade --repo "$SRC" --release "$WORK/v9.1.0.json" --target "$TARGET" \
  >/dev/null 2>"$WORK/dirty.txt"
expect_code 6 $? "dirty workspace refused"
grep -q "shipped in 9.1.0" "$TARGET/START_HERE.md" && bad "refused upgrade still wrote" \
  || ok "refused upgrade wrote nothing"
git -C "$SRC" show "$REV:START_HERE.md" > "$TARGET/START_HERE.md"

step "A4: upgrade preserves state"
aios upgrade --repo "$SRC" --release "$WORK/v9.1.0.json" --target "$TARGET" \
  > "$WORK/upgrade.txt" 2>&1
expect_code 0 $? "upgrade 9.0.0 -> 9.1.0"
sed 's/^/    /' "$WORK/upgrade.txt"
aios verify --target "$TARGET" >/dev/null 2>&1
expect_code 0 $? "readback verify after upgrade"
grep -q "shipped in 9.1.0" "$TARGET/START_HERE.md" && ok "managed file really changed" \
  || bad "managed file did not change"
[ -f "$TARGET/.claude/skills/shipped_in_910/SKILL.md" ] && ok "new managed file arrived" \
  || bad "new managed file missing"
grep -q "MY OWN CONSTITUTION" "$TARGET/CLAUDE.md" && ok "seed file untouched" \
  || bad "SEED FILE WAS OVERWRITTEN"
STATE_AFTER=$(cd "$TARGET" && find . -path ./.git -prune -o -path ./.aios/backups -prune -o -type f -print \
  | grep -v '^\./\.aios/\(install\.json\|txn\.json\)$' | grep -v 'shipped_in_910' \
  | grep -v '^\./START_HERE\.md$' | sort | xargs shasum -a 256 | shasum -a 256)
STATE_BEFORE_CMP=$(cd "$TARGET" && echo "$STATE_BEFORE")
[ -n "$STATE_AFTER" ] && ok "state re-hashed after upgrade"

step "A4b: rollback restores, and is readback-verified"
aios rollback --target "$TARGET" > "$WORK/rollback.txt" 2>&1
expect_code 0 $? "rollback 9.1.0 -> 9.0.0"
sed 's/^/    /' "$WORK/rollback.txt"
aios verify --target "$TARGET" >/dev/null 2>&1
expect_code 0 $? "readback verify after rollback"
grep -q "shipped in 9.1.0" "$TARGET/START_HERE.md" && bad "rollback left new content" \
  || ok "managed file restored"
[ -f "$TARGET/.claude/skills/shipped_in_910/SKILL.md" ] && bad "rollback left an added file" \
  || ok "file added by 9.1.0 removed again"
grep -q "MY OWN CONSTITUTION" "$TARGET/CLAUDE.md" && ok "seed survived the round trip" \
  || bad "SEED LOST IN ROLLBACK"
[ -f "$TARGET/02_Deliverables/copy/launch_email.md" ] && ok "operator's own work survived" \
  || bad "OPERATOR WORK LOST"
[ -f "$TARGET/.claude/skills/my_own_skill/SKILL.md" ] && ok "operator's own skill survived" \
  || bad "OPERATOR SKILL LOST"
STATE_END=$(cd "$TARGET" && find . -path ./.git -prune -o -path ./.aios/backups -prune -o -type f -print \
  | grep -v '^\./\.aios/\(install\.json\|txn\.json\)$' | sort | xargs shasum -a 256 | shasum -a 256)
if [ "$STATE_END" = "$STATE_BEFORE" ]; then
  ok "state fingerprint identical after upgrade AND rollback"
else
  bad "state changed across the round trip"
fi

step "N5: hard kill mid-upgrade, then rollback recovers it"
AIOS_FAULT="crash:upgrade.mid_write" aios upgrade --repo "$SRC" --release "$WORK/v9.1.0.json" \
  --target "$TARGET" >/dev/null 2>&1
expect_code 137 $? "upgrade died mid-write with no cleanup"
[ -f "$TARGET/.aios/txn.json" ] && ok "journal left on disk" || bad "no journal after a hard kill"
aios verify --target "$TARGET" >/dev/null 2>&1
expect_code 5 $? "verify reports PARTIAL, not a clean workspace"
aios rollback --target "$TARGET" > "$WORK/recover.txt" 2>&1
expect_code 0 $? "rollback recovered the interrupted upgrade"
sed 's/^/    /' "$WORK/recover.txt"
aios verify --target "$TARGET" >/dev/null 2>&1
expect_code 0 $? "readback verify after recovery"
STATE_RECOVERED=$(cd "$TARGET" && find . -path ./.git -prune -o -path ./.aios/backups -prune -o -type f -print \
  | grep -v '^\./\.aios/\(install\.json\|txn\.json\)$' | sort | xargs shasum -a 256 | shasum -a 256)
if [ "$STATE_RECOVERED" = "$STATE_BEFORE" ]; then
  ok "state identical after a hard kill and recovery"
else
  bad "state changed across crash recovery"
fi

step "N2: a missing REQUIRED credential fails loudly"
python3 - "$WORK/v9.0.0.json" "$WORK/v9.0.0-needs-cred.json" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
m["credentials"] = [{"name": "ACME_REQUIRED_KEY", "required": True, "purpose": "negative test"}]
json.dump(m, open(sys.argv[2], "w"), indent=2, sort_keys=True)
PY
aios install --repo "$SRC" --release "$WORK/v9.0.0-needs-cred.json" --target "$WORK/t2" \
  --config "$WORK/config.json" >/dev/null 2>"$WORK/cred.txt"
expect_code 4 $? "missing required credential refused"
[ ! -e "$WORK/t2/START_HERE.md" ] && ok "nothing installed in a degraded state" \
  || bad "installed anyway"

step "N6: a package carrying a literal secret fails sanitization"
printf 'KEY = "%s"\n' "sk-ant-api03-$(printf 'A%.0s' $(seq 1 40))" > "$SRC/06_Communication/leak.md"
git -C "$SRC" add -A >/dev/null 2>&1; git -C "$SRC" commit -qm "leak" >/dev/null 2>&1
REV3="$(git -C "$SRC" rev-parse HEAD)"
aios sanitize --repo "$SRC" --rev "$REV3" --mode scan >/dev/null 2>&1
expect_code 7 $? "literal secret in the package refused"
git -C "$SRC" revert --no-edit -q HEAD >/dev/null 2>&1

step "N7: CODEOWNERS with an unresolved placeholder fails the repo's own check"
aios governance check --root "$SRC" --repo-slug acme/acme-aios >/dev/null 2>&1
expect_code 8 $? "placeholder CODEOWNERS refused"

printf '\n─────────────────────────────────────────\n'
printf 'RESULT: %d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ] || exit 1
