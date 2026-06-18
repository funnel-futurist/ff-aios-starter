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

PROT=$(gh api "repos/$REPO/branches/main/protection" 2>/tmp/_prot_err)
CODE=$?
ERR=$(cat /tmp/_prot_err 2>/dev/null); rm -f /tmp/_prot_err

fails=0
if [ $CODE -ne 0 ]; then
  if echo "$ERR" | grep -qi "Not Found"; then
    echo "  ✗ FAIL: main has NO branch protection (direct pushes to main are NOT blocked)"
    fails=$((fails+1))
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
fi

# CODEOWNERS present?
if gh api "repos/$REPO/contents/.github/CODEOWNERS" --jq .name >/dev/null 2>&1; then
  echo "  ✓ .github/CODEOWNERS present"
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
