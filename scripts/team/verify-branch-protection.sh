#!/usr/bin/env bash
# ============================================================================
# verify-branch-protection.sh — assert the safety claims are actually configured.
#
# The whole workflow promises "you can't push to main" / "owned paths need a review".
# Those depend on GitHub branch protection + CODEOWNERS being ON — settings that live
# OUTSIDE this repo. This script checks they're real, so the promise can't silently be false.
#
# Run by an admin (reading protection needs admin) or in CI with an admin token.
# Usage:  bash scripts/team/verify-branch-protection.sh [owner/repo]
# Exit: 0 = all good (or can't-determine), 1 = a protection is MISSING (claims would be false).
# ============================================================================
set +e
REPO="${1:-$(gh repo view --json nameWithOwner --jq .nameWithOwner 2>/dev/null)}"
[ -z "$REPO" ] && { echo "FAIL: can't determine repo (pass owner/repo, or run inside the repo with gh auth)"; exit 1; }
echo "Verifying protection for: $REPO"
echo "─────────────────────────────────────────────"

# The `protected` flag on the branch itself is readable WITHOUT admin, unlike the protection
# detail below. Without this, a non-admin run reported INCONCLUSIVE on a repo that had no
# protection at all — the detector stayed quiet about the loudest possible finding.
# Initialised here, before the first check. It used to be set further down, AFTER the
# unprotected-branch check had already incremented it, so the increment was wiped and the
# script printed "direct pushes are allowed" and "all protections in place" in the same run -
# a detector reporting green over the finding it had just printed.
fails=0

PROTECTED=$(gh api "repos/$REPO/branches/main" --jq .protected 2>/dev/null)
if [ "$PROTECTED" = "false" ]; then
  echo "  ✗ FAIL: main is NOT protected (confirmed without admin: branches/main .protected = false)"
  echo "         direct pushes, force-pushes and deletions of main are all allowed"
  fails=$((fails+1))
fi

PROT=$(gh api "repos/$REPO/branches/main/protection" 2>/tmp/_prot_err)
CODE=$?
ERR=$(cat /tmp/_prot_err 2>/dev/null); rm -f /tmp/_prot_err
if [ $CODE -ne 0 ]; then
  if echo "$ERR" | grep -qi "Not Found"; then
    if [ "$PROTECTED" != "false" ]; then
      echo "  ✗ FAIL: main has NO branch protection (direct pushes to main are NOT blocked)"
      fails=$((fails+1))
    fi
  elif echo "$ERR" | grep -qiE "403|admin"; then
    echo "  ⚠ NOTE: can't read protection (needs an admin token). Re-run as an admin to verify."
    echo "─────────────────────────────────────────────"; echo "INCONCLUSIVE (no admin access) — not a failure."; exit 0
  else
    echo "  ⚠ NOTE: couldn't read protection ($(echo "$ERR" | head -1 | cut -c1-80))"; exit 0
  fi
else
  echo "$PROT" | python3 -c "
import sys,json
d=json.load(sys.stdin); f=0
pr = d.get('required_pull_request_reviews')
print('  '+('✓' if pr else '✗ FAIL')+' PR required before merge'); f+= 0 if pr else 1
print('  '+('✓' if (pr or {}).get('require_code_owner_reviews') else '✗ FAIL')+' code-owner review required'); f+= 0 if (pr or {}).get('require_code_owner_reviews') else 1
ctx=[c for c in (d.get('required_status_checks') or {}).get('contexts',[])]
print('  '+('✓' if ctx else 'ℹ')+f' required status checks: {ctx or \"none (optional — only if you add CI/an AI reviewer)\"}')  # informational, not a fail
fp = not (d.get('allow_force_pushes') or {}).get('enabled', True)
print('  '+('✓' if fp else '✗ FAIL')+' force-pushes to main blocked'); f+= 0 if fp else 1
de = not (d.get('allow_deletions') or {}).get('enabled', True)
print('  '+('✓' if de else '✗ FAIL')+' main deletion blocked'); f+= 0 if de else 1
sys.exit(f)
"
  fails=$((fails+$?))
  # In an installed workspace (it has a people map), the founder-lane boundary only BLOCKS a
  # merge when it is a required check. Otherwise it is a red X anyone with merge rights can
  # click past, and /start's "held at the pull request" would overstate it.
  ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
  if [ -f "$ROOT_DIR/.aios/config.json" ]; then
    if echo "$PROT" | python3 -c "
import sys,json
c=(json.load(sys.stdin).get('required_status_checks') or {})
names=set(c.get('contexts') or [])|{x.get('context') for x in (c.get('checks') or [])}
sys.exit(0 if 'boundary' in names else 1)"; then
      echo "  ✓ the founder-lane boundary check is required before merge"
    else
      echo "  ✗ FAIL: the 'boundary' check is not a required status check - a founder-lane change can be merged past it"
      fails=$((fails+1))
    fi
  fi
fi

# CODEOWNERS present AND actually naming somebody.
#
# This used to check only that the file EXISTS. A file full of [REPO_OWNER] placeholders
# exists, so this reported a green tick over a rule that matched nobody and enforced nothing
# — exactly the drift this script was written to catch. Presence is not enforcement.
if gh api "repos/$REPO/contents/.github/CODEOWNERS" --jq .name >/dev/null 2>&1; then
  echo "  ✓ .github/CODEOWNERS present"
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  if python3 "$SCRIPT_DIR/../aios/aios.py" governance check --root "$SCRIPT_DIR/../.." \
       --repo-slug "$REPO" >/tmp/_co_out 2>&1; then
    echo "  ✓ .github/CODEOWNERS names real owners, bound to this repository"
  else
    echo "  ✗ FAIL: .github/CODEOWNERS does not enforce anything:"
    sed 's/^/      /' /tmp/_co_out
    fails=$((fails+1))
  fi
  rm -f /tmp/_co_out
else
  echo "  ✗ FAIL: no .github/CODEOWNERS (owned-path reviews can't route)"; fails=$((fails+1))
fi

echo "─────────────────────────────────────────────"
if [ "$fails" -gt 0 ]; then
  echo "RESULT: $fails check(s) FAILED — the workflow's safety promises are NOT fully enforced. Fix in repo Settings → Branches."
  exit 1
fi
echo "RESULT: all protections in place ✓ — the safety claims hold."
exit 0
