#!/usr/bin/env node
/*
 * SessionStart hook — git staleness nudge.
 * Read-only from the user's perspective: does a bounded `git fetch` (updates remote-tracking
 * refs = git metadata only, NEVER touches working files), then prints a one-line nudge IF the
 * operator is on `main` or behind `origin/main`. On a clean, synced task branch it stays quiet.
 *
 * FAIL-OPEN: any error / offline / nothing-to-say → no output, exit 0. Never blocks a session.
 */
const { execSync } = require('child_process');
function sh(cmd, ms) {
  try {
    return execSync(cmd, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'], timeout: ms || 4000 }).trim();
  } catch (_) { return ''; }
}
try {
  const root = process.env.CLAUDE_PROJECT_DIR || process.cwd();
  if (sh(`git -C "${root}" rev-parse --is-inside-work-tree`, 3000) !== 'true') process.exit(0);

  const branch = sh(`git -C "${root}" rev-parse --abbrev-ref HEAD`, 3000);
  sh(`git -C "${root}" fetch --quiet origin main`, 8000); // bounded; ignore failure (offline)

  const onMain = branch === 'main';
  const nBehind = parseInt(sh(`git -C "${root}" rev-list --count HEAD..origin/main`, 3000) || '0', 10) || 0;
  const dirtyOut = sh(`git -C "${root}" status --porcelain`, 3000);
  const nDirty = dirtyOut ? dirtyOut.split('\n').filter(Boolean).length : 0;

  let who = '';
  try {
    const fs = require('fs');
    const p = root + '/.aios/local-operator.json';
    if (fs.existsSync(p)) {
      const j = JSON.parse(fs.readFileSync(p, 'utf8'));
      who = j.display_name || j.operator || '';
    }
  } catch (_) { /* ignore */ }
  const hi = who ? `${who} — ` : '';

  const lines = [];
  if (onMain) {
    lines.push(`⚠️  ${hi}you're on **main** (the official timeline). Don't work here — run \`/start-my-day\` to start safely on your own branch.`);
  } else if (nBehind > 0) {
    lines.push(`👋 ${hi}branch \`${branch}\` is **${nBehind} commit${nBehind === 1 ? '' : 's'} behind main**. Run \`/start-my-day\` to sync before you work.`);
  }
  if (nDirty > 0 && !onMain) {
    lines.push(`   You have ${nDirty} uncommitted change${nDirty === 1 ? '' : 's'} — \`/wrap-up\` will commit + push them cleanly so they're not stranded.`);
  }
  if (lines.length) process.stdout.write(`[git status check]\n${lines.join('\n')}\n`);
} catch (_) { /* fail-open */ }
process.exit(0);
