---
name: resolve-conflict
description: The calm, plain-English path through a git merge conflict for a non-technical operator. Use the moment a pull/merge/sync reports a conflict, when the user sees "<<<<<<< HEAD" or "CONFLICT" or "fix conflicts and then commit", or says "I got a conflict", "merge conflict", "it won't let me", "weird symbols in my file", "everything broke when I synced". Detects the conflicted files, explains what happened simply, and walks them through resolving each one (keep mine / keep theirs / keep both) OR safely backing all the way out — never losing committed work.
---

# /resolve-conflict — calm path through a merge conflict

A conflict is **normal and fixable** — it just means two people changed the same lines, and git needs you to pick. **Nobody's work is lost.** Stay calm, go one file at a time, plain English. (The safety guard will stop a panicked `git reset --hard` — good; you don't need it. Use the safe steps below.)

## Step 1 — Confirm the situation
```bash
git status
git diff --name-only --diff-filter=U   # the conflicted files
```
Tell the operator plainly: *"You have N file(s) where your version and the latest official version both changed the same spot. We'll go through each and you pick what to keep. Nothing is deleted."*

## Step 2 — Offer the two ways out (let them choose)
- **A) Resolve and keep going** (default — keeps both people's intended work). Go to Step 3.
- **B) Back all the way out** (if they're overwhelmed or did this by accident). This is SAFE — it undoes the merge attempt, not their committed work:
  ```bash
  git merge --abort      # if it was a merge/pull
  # or: git rebase --abort   # if a rebase was in progress (git status will say)
  ```
  Then reassure: *"You're exactly back where you were before. We can try again or get help."*

## Step 3 — Resolve each conflicted file, one at a time
For each file from Step 1, open it and find the markers:
```
<<<<<<< HEAD
(your version)
=======
(the latest official version)
>>>>>>> origin/main
```
Explain: *"Everything between `<<<<<<<` and `=======` is YOUR version; between `=======` and `>>>>>>>` is the official version."* Then ask which they want, and edit the file to that — **removing all three marker lines**:
- **Keep mine** → keep the top block, delete the markers + the bottom block.
- **Keep theirs** → keep the bottom block, delete the markers + the top block.
- **Keep both** → keep both blocks in the right order, delete only the marker lines.
- **Not sure** → show both blocks side by side in plain English and recommend; if it's risky (code, claims, governance), tell them to ask the file's owner before choosing.
Do this edit FOR them when they've chosen. Re-check there are no remaining `<<<<<<<` / `=======` / `>>>>>>>` anywhere:
```bash
grep -rn '^<<<<<<<\|^=======\|^>>>>>>>' . 2>/dev/null | grep -v node_modules
```

## Step 4 — Mark resolved + finish
```bash
git add <each resolved file>
git status        # confirm "all conflicts fixed"
```
- If a merge was in progress: `git commit` (no message needed — git fills the merge message).
- If a rebase: `git rebase --continue`.
Then tell them: *"Resolved — now run `/wrap-up` to push and open your review request."*

## Always
- Never `git reset --hard` / `git checkout --` to "fix" a conflict — `git merge --abort` is the safe undo.
- One file at a time. Confirm each choice before editing.
- If the conflict is in a file they don't own or understand (code, migrations, governance, another client's work), STOP and tell them to ask the owner — don't guess.
