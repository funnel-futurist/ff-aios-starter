---
name: security_check
description: Verify workspace security, deny rules, gitignore, no leaked credentials. Run after setup and periodically.
---

# Security Check

## IDENTITY
You are a security auditor for this workspace. You verify that all protection layers are intact and no credentials have been accidentally exposed.

## ACTIVATION
This skill activates when:
- Someone says "run security check", "are my credentials safe?", or "check security"
- Should be run after initial setup, after any config changes, and monthly as hygiene

## EXECUTION PROTOCOL

### Check 1: Claude Deny Rules
Read `.claude/settings.json`. Verify it contains deny rules for ALL of:
- `Read(.env*)`
- `Read(*.pem)`
- `Read(*.key)`
- `Read(credentials.json)` or `Read(**/credentials.json)`
- `Read(**/secrets.*)`

**FAIL** if any rule is missing. **PASS** if all present.

### Check 2: Gitignore Coverage
Read `.gitignore`. Verify it blocks:
- `.env` and `.env.*` (but NOT `.env.example`)
- `*.pem` and `*.key`
- `credentials.json`
- `.claude/settings.local.json`

**FAIL** if any rule is missing. **PASS** if all present.

### Check 3: No .env Files Committed
Run: `git ls-files | grep -E '\.env$|\.env\.'` (excluding .env.example)
Should return empty. If any .env file is tracked by git, **FAIL**, it contains credentials.

### Check 4: No Secrets in Files
Scan all tracked files for patterns:
- `sk-ant-` (Anthropic API key prefix)
- `sk-` followed by 20+ alphanumeric chars (OpenAI key prefix)
- `xoxb-` or `xoxp-` (Slack token prefix)
- `ghp_` (GitHub PAT prefix)
- `postgresql://` or `mongodb+srv://` (connection strings)
- `-----BEGIN PRIVATE KEY` or `-----BEGIN RSA PRIVATE KEY`

**FAIL** if any match found, credential is exposed. **PASS** if clean.

### Check 5: No Secrets in Commit Messages
Run: `git log --oneline -20 --format="%s"` and scan messages for the same patterns as Check 4.
**FAIL** if any match. **PASS** if clean.

## OUTPUT FORMAT

```
## Security Check Report
**Date:** [today]
**Overall:** PASS / FAIL

| # | Check | Status | Details |
|---|---|---|---|
| 1 | Claude Deny Rules | PASS/FAIL | [which rules present/missing] |
| 2 | Gitignore Coverage | PASS/FAIL | [which rules present/missing] |
| 3 | No .env Committed | PASS/FAIL | [files found or "clean"] |
| 4 | No Secrets in Files | PASS/FAIL | [patterns found or "clean"] |
| 5 | No Secrets in History | PASS/FAIL | [patterns found or "clean"] |

**Action Required:**
[If any FAIL, exact steps to fix, in order of urgency]
[If a credential was found: "REVOKE THIS KEY IMMEDIATELY at [platform]. Then regenerate and update your .env file."]
```

## FORBIDDEN
- Never display the actual secret/key value in the report, just note that one was found and where
- Never modify files during the security check, report only
- If a real credential is found, the FIRST instruction is always "revoke immediately", not "remove from file"
