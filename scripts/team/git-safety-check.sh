#!/usr/bin/env bash
# ============================================================================
# git-safety-check.sh — read-only operator/branch/sync status.
#
# Used by the /start-my-day and /wrap-up skills. Prints a human-readable STATUS
# block followed by KEY=VALUE lines the skills parse.
#
# It NEVER changes anything: no checkout, no pull, no commit, no reset.
# It ALWAYS exits 0. The ONLY optional side effect is `--fetch`, which updates
# remote-tracking refs (git metadata) — it does NOT touch your working files.
#
# Usage:  bash scripts/team/git-safety-check.sh [--fetch]
# ============================================================================
set +e

DO_FETCH=0
[ "${1:-}" = "--fetch" ] && DO_FETCH=1

ROOT=$(git rev-parse --show-toplevel 2>/dev/null)
if [ -z "$ROOT" ]; then
  echo "STATUS: not inside a git repository."
  echo "ERROR=not_a_git_repo"
  exit 0
fi
cd "$ROOT" 2>/dev/null || exit 0

# Optional, bounded metadata sync (remote-tracking refs only — no working-file changes).
FETCHED=skipped
if [ "$DO_FETCH" = "1" ]; then
  if timeout 8 git fetch --quiet origin main 2>/dev/null; then FETCHED=ok; else FETCHED=failed_or_offline; fi
fi

REPO=$(git config --get remote.origin.url 2>/dev/null | sed -E 's#.*[:/]([^/]+/[^/]+)$#\1#; s#\.git$##')
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
ON_MAIN=false; [ "$BRANCH" = "main" ] && ON_MAIN=true

DIRTY=$(git status --porcelain 2>/dev/null | grep -c .)
CLEAN=true; { [ "${DIRTY:-0}" -gt 0 ]; } 2>/dev/null && CLEAN=false

if git rev-parse --verify --quiet origin/main >/dev/null 2>&1; then
  BEHIND=$(git rev-list --count HEAD..origin/main 2>/dev/null)
  AHEAD=$(git rev-list --count origin/main..HEAD 2>/dev/null)
else
  BEHIND=unknown; AHEAD=unknown
fi

GIT_NAME=$(git config user.name 2>/dev/null)
GIT_EMAIL=$(git config user.email 2>/dev/null)
GH_USER=$(gh api user --jq .login 2>/dev/null); [ -z "$GH_USER" ] && GH_USER=unknown

OPFILE="$ROOT/.aios/local-operator.json"
if [ -f "$OPFILE" ]; then OP_FILE=present; else OP_FILE=absent; fi

# ---- human-readable summary ----
echo "STATUS ─────────────────────────────────────────────"
echo "  Repo:     ${REPO:-unknown}"
if [ "$ON_MAIN" = true ]; then
  echo "  Branch:   ${BRANCH:-unknown}   ⚠️  YOU ARE ON MAIN — do not work here"
else
  echo "  Branch:   ${BRANCH:-unknown}"
fi
if [ "$CLEAN" = true ]; then
  echo "  Worktree: clean"
else
  echo "  Worktree: ${DIRTY} uncommitted change(s)"
fi
echo "  vs main:  behind ${BEHIND}, ahead ${AHEAD}   (fetch: ${FETCHED})"
echo "  Identity: ${GIT_NAME:-?} <${GIT_EMAIL:-?}>  ·  gh: ${GH_USER}"
echo "  Operator file: ${OP_FILE}"
echo "─────────────────────────────────────────────────────"

# ---- machine-readable keys ----
echo "REPO=${REPO:-unknown}"
echo "BRANCH=${BRANCH:-unknown}"
echo "ON_MAIN=${ON_MAIN}"
echo "WORKTREE_CLEAN=${CLEAN}"
echo "DIRTY_FILES=${DIRTY:-0}"
echo "BEHIND_MAIN=${BEHIND}"
echo "AHEAD_MAIN=${AHEAD}"
echo "GIT_NAME=${GIT_NAME}"
echo "GIT_EMAIL=${GIT_EMAIL}"
echo "GH_USER=${GH_USER}"
echo "OPERATOR_FILE=${OP_FILE}"
echo "FETCH=${FETCHED}"
exit 0
