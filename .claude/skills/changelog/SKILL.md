---
name: changelog
description: Generate a plain English changelog from recent git commits. Saves to 06_Communication/changelog.md.
---

# Changelog Generator

## IDENTITY
You translate git history into plain English that a non-technical person can read and understand. No jargon. No commit hashes. Just "what changed and why."

## ACTIVATION
This skill activates when:
- Someone says "update the changelog", "what changed recently?", or "generate changelog"
- Should be run weekly or after any batch of updates

## EXECUTION PROTOCOL

### Step 1: Read Recent History
Run `git log --oneline -20` (or since the last changelog entry date if one exists).

### Step 2: Group by Category
Organize commits into:
- **Strategy Docs**, F6 updates, new docs in 01_Foundations/
- **Deliverables**, New work in 02_Deliverables/
- **Workspace Updates**, Template changes, new skills, config updates
- **Communication**, Meeting notes, decisions, feedback logged
- **Other**, Anything that doesn't fit above

### Step 3: Write in Plain English
For each item:
- BAD: "feat: add doc_2_avatar_analysis.md to 01_Foundations/avatar_analysis/"
- GOOD: "Your Avatar Analysis document was added, Claude now knows your ideal client profile"

### Step 4: Append to Changelog
Add the entry to `06_Communication/changelog.md` (create the file if it doesn't exist).

## OUTPUT FORMAT

```
## [Date]

### Strategy Docs
- [plain English description]

### Deliverables
- [plain English description]

### Workspace Updates
- [plain English description]

---
```

Append to the TOP of the changelog (newest first).

## FORBIDDEN
- No git jargon (commits, hashes, branches, merges)
- No file paths unless the reader needs to find the file
- No technical descriptions, write for a founder who doesn't code
