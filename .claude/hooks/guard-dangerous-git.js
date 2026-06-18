#!/usr/bin/env node
/*
 * PreToolUse(Bash) guard v2 — stop-and-ask before DESTRUCTIVE LOCAL commands that can permanently
 * delete work that hasn't been pushed (so GitHub can't recover it).
 *
 * v2 hardening (from independent cross-model review): split the command into segments on shell
 * separators, then STRIP leading prefixes (env assignments like `FOO=bar`, plus `sudo`/`xargs`/
 * `time`/`nohup`/`command`) before matching — so `FOO=bar git reset --hard`, `sudo rm -rf`,
 * `cat x | xargs rm -rf`, and `cd y && git reset --hard` are all caught. Coverage now includes
 * git restore/checkout-of-a-file, branch -D, push --force/--delete/:refspec, stash drop/clear,
 * and rm with recursive+force flags in any arrangement (-rf / -fr / -r -f / --recursive --force).
 *
 * Returns permissionDecision "ask" (Claude Code stops and asks the operator to confirm).
 * FAIL-OPEN: any parse error / non-Bash payload / no match → allow. Mentions inside echoes/strings
 * are NOT matched (the dangerous token must be the actual command at a segment start).
 */

const PREFIX = /^(?:[A-Za-z_][A-Za-z0-9_]*=\S*|sudo|xargs|time|nohup|command|exec|builtin|env)\s+/;

function stripPrefixes(seg) {
  let c = seg.trim();
  let prev;
  do { prev = c; c = c.replace(PREFIX, '').trim(); } while (c !== prev);
  return c;
}

function rmHasRecursiveAndForce(c) {
  if (!/^rm\b/.test(c)) return false;
  let rec = false, force = false;
  for (const a of c.split(/\s+/).slice(1)) {
    if (a === '--recursive') rec = true;
    if (a === '--force') force = true;
    if (/^-[A-Za-z]+$/.test(a)) { if (/[rR]/.test(a)) rec = true; if (/f/.test(a)) force = true; }
  }
  return rec && force;
}

// Each rule: (cleanedSegment) -> reason string | false
const RULES = [
  c => /^git\s+reset\s+(--hard|--keep)\b/.test(c) && 'git reset --hard/--keep throws away ALL uncommitted changes in tracked files',
  c => /^git\s+clean\b/.test(c) && /(-\w*f|--force)/.test(c) && 'git clean -f permanently deletes untracked files — including new work you have not committed yet',
  c => /^git\s+checkout\b/.test(c) && (/\s--(\s|$)/.test(c) || /\s-f\b|--force\b/.test(c) || /\s\.(\s|$)/.test(c) || /\s[^\s-]\S*\.\w+(\s|$)/.test(c)) && 'git checkout of a file (-- / a path / -f) overwrites your local changes with no undo',
  c => /^git\s+restore\b/.test(c) && !(/--staged/.test(c) && !/--worktree/.test(c)) && 'git restore discards your local file changes with no undo',
  c => /^git\s+branch\b/.test(c) && (/\s-D\b/.test(c) || (/(--delete|\s-d)\b/.test(c) && /(--force|\s-f)\b/.test(c))) && 'git branch -D force-deletes a branch even if it has commits that were never merged',
  c => /^git\s+push\b/.test(c) && (/--force(-with-lease)?\b/.test(c) || /\s-f\b/.test(c) || /--delete\b/.test(c) || /\s:\S/.test(c)) && 'git push --force / --delete can overwrite or delete history others may rely on',
  c => /^git\s+stash\s+(drop|clear)\b/.test(c) && 'git stash drop/clear permanently deletes stashed (parked) work',
  c => rmHasRecursiveAndForce(c) && 'rm -rf permanently deletes files/folders — there is no recycle bin',
];

function analyze(cmd) {
  if (!cmd || typeof cmd !== 'string') return null;
  const segments = cmd.split(/\s*(?:&&|\|\||[;&|\n()])\s*/).filter(Boolean);
  for (const seg of segments) {
    const c = stripPrefixes(seg);
    for (const rule of RULES) {
      const why = rule(c);
      if (why) return why;
    }
  }
  return null;
}

module.exports = { analyze, stripPrefixes, rmHasRecursiveAndForce };

if (require.main === module) {
  let s = '';
  process.stdin.on('data', d => { s += d; });
  process.stdin.on('end', () => {
    try {
      const why = analyze(((JSON.parse(s || '{}').tool_input) || {}).command || '');
      if (why) {
        process.stdout.write(JSON.stringify({
          hookSpecificOutput: {
            hookEventName: 'PreToolUse',
            permissionDecision: 'ask',
            permissionDecisionReason:
              `SAFETY CHECK: this can permanently delete work that isn't pushed (so it can't be recovered). ${why}. ` +
              `Confirm the operator truly intends this BEFORE running it. If they're unsure, stop — \`/start-my-day\`, \`/wrap-up\`, and \`/resolve-conflict\` protect their work instead.`,
          },
        }));
      }
    } catch (_) { /* fail-open */ }
    process.exit(0);
  });
}
