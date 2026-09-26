#!/bin/sh
# Install without disabling any existing pre-commit scanner or replacing hooks.
set -eu
root=$(git rev-parse --show-toplevel)
cd "$root"
if [ -n "$(git config --get core.hooksPath || true)" ]; then
  echo "Existing core.hooksPath requires manual hook integration; no changes made." >&2
  exit 1
fi
hooks=$(git rev-parse --git-path hooks)
mkdir -p "$hooks"
target="$hooks/pre-push"
if [ -e "$target" ] && ! cmp -s .githooks/pre-push "$target"; then
  echo "Existing pre-push hook requires manual integration; no changes made." >&2
  exit 1
fi
cp .githooks/pre-push "$target"
chmod +x "$target"
echo "Installed skill-validation pre-push hook. Other hooks unchanged."
