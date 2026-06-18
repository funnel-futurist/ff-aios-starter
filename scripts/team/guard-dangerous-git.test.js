#!/usr/bin/env node
/* Test suite for the destructive-git guard. Run: node scripts/team/guard-dangerous-git.test.js
 * Covers the bypasses found in the cross-model review (env-prefix, sudo, xargs, separated flags,
 * restore/checkout-of-file, stash drop, push --delete/:refspec) AND the safe commands that must
 * NOT trigger (branch switch, branch with a slash, --staged restore, single-file rm, mentions). */
const { analyze } = require('../../.claude/hooks/guard-dangerous-git.js');

const ASK = [
  'git reset --hard HEAD', 'git reset --keep', 'FOO=bar git reset --hard', 'sudo git reset --hard',
  'cd /x && git reset --hard', 'git clean -fd', 'git clean -f', 'git clean --force',
  'rm -rf build', 'rm -fr build', 'rm -r -f build', 'rm -f -r build', 'rm --recursive --force build',
  'sudo rm -rf /tmp/x', 'cat list | xargs rm -rf', 'A=1 B=2 rm -rf x',
  'git branch -D feature', 'git branch --delete --force feature',
  'git push --force origin x', 'git push -f origin mine', 'git push --force-with-lease',
  'git push origin --delete oldbranch', 'git push origin :oldbranch',
  'git stash drop', 'git stash clear',
  'git checkout -- .', 'git checkout -- file.txt', 'git checkout -f', 'git checkout .',
  'git checkout config.json',
  'git restore .', 'git restore file.txt', 'git restore --worktree --staged file',
];
const ALLOW = [
  'git status', 'git checkout main', 'git checkout -b new-feature',
  'git checkout alex/welcome-2026-06-18', "git commit -m 'fix: thing'",
  'git push -u origin HEAD', 'git pull --ff-only origin main', 'git restore --staged file.txt',
  'git stash', 'git branch -d merged-feature', 'rm file.txt', 'rm -f file.txt',
  "echo 'do not run rm -rf ever'", 'git add -A', 'npm run build', 'git merge origin/main',
];

let pass = 0, fail = 0;
for (const c of ASK) {
  const got = analyze(c) ? 'ASK' : 'ALLOW';
  if (got === 'ASK') pass++; else { fail++; console.log(`  FAIL (want ASK, got ALLOW): ${c}`); }
}
for (const c of ALLOW) {
  const got = analyze(c) ? 'ASK' : 'ALLOW';
  if (got === 'ALLOW') pass++; else { fail++; console.log(`  FAIL (want ALLOW, got ASK): ${c}`); }
}
console.log(`\nguard tests: ${pass} passed, ${fail} failed  (${ASK.length} ask-cases, ${ALLOW.length} allow-cases)`);
process.exit(fail ? 1 : 0);
