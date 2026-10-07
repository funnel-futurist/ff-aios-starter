#!/bin/bash
# Exact-candidate learner rehearsal for starter-2.7.0 (DRAFT, pinned aa2f46b).
# The real record stays draft. A COPY with a rehearsal-only approval string is used so the
# installer runs; it still re-hashes every installed file against the pinned commit.
set -u
R=<scratch>/r270
rm -rf "$R"; mkdir -p "$R"; cd "$R"
say(){ printf '\n### %s\n' "$*"; }
PY=$(command -v python3); GIT=$(command -v git); GH=$(command -v gh); NODE=$(command -v node)
LOGIN=$(gh api user --jq .login)

say "R0 tools on this computer"
python3 --version; git --version | head -1; node --version; gh --version | head -1

say "R1 fresh clone of the candidate branch from GitHub"
git clone -q --branch exec/p22-v4-clean-vault-20260928 https://github.com/funnel-futurist/ff-aios-starter.git starter
cd starter; git log --oneline -1; cd ..
python3 - <<EOF
import json
m=json.load(open('starter/releases/starter-2.7.0.json'))
print('record status:', m['status'], 'pin:', m['created_from']['git_rev'])
m['status']='approved'; m['approval']={'approved_by':'REHEARSAL-ONLY-NOT-AN-APPROVAL','approved_at':'2026-09-29T00:00:00Z'}
json.dump(m,open('rehearsal-2.7.0.json','w'),indent=2)
EOF
cat > org.json <<EOF
{"schema":"ff-aios-starter/org-config@1","org_id":"pilot-sandbox-co","repository":"learner/AIOS_CERT_C0_Learner_Sandbox",
 "people":[{"github":"$LOGIN","role":"founder","display_name":"Rehearsal installer"},
           {"github":"rehearsal-operator","role":"operator","display_name":"Invented operator"}],
 "credentials":{},"code_owners":{"REPO_OWNER":["@$LOGIN"],"PRIMARY_REVIEWER":["@$LOGIN"]}}
EOF

say "R2 the real draft record is refused (no approval inferred)"
python3 starter/scripts/aios/aios.py install --release starter/releases/starter-2.7.0.json --target d1 --config org.json; echo "exit=$?"; rm -rf d1

say "R3 install the exact candidate into an empty repository clone"
git init -q --bare sandbox.git; git clone -q sandbox.git sandbox 2>/dev/null
python3 starter/scripts/aios/aios.py install --release rehearsal-2.7.0.json --target sandbox --config org.json | head -4; echo "exit=${PIPESTATUS[0]}"
cd sandbox; git add -A; git -c user.email=r@example.invalid -c user.name=R commit -qm "Install AIOS"; git push -q origin HEAD:main
python3 scripts/aios/aios.py start | sed -n 1,5p
python3 scripts/aios/aios.py verify --target . --repo ../starter | grep -E "verdict|checked"
echo "not shipped: $(ls -d releases tests evidence 2>/dev/null | wc -l | tr -d ' ') of releases/tests/evidence present"
cd ..

say "R4 founder lane in the session (edit hook)"
mkdir -p bin-op bin-none; printf '#!/bin/sh\n[ "$1" = api ] && [ "$2" = user ] && { echo rehearsal-operator; exit 0; }; exit 1\n' > bin-op/gh; chmod +x bin-op/gh
ln -sf "$PY" bin-none/python3; ln -sf "$GIT" bin-none/git; ln -sf "$PY" bin-op/python3; ln -sf "$GIT" bin-op/git
edit(){ rm -f sandbox/.aios/.identity* 2>/dev/null; echo "{\"tool_name\":\"Edit\",\"tool_input\":{\"file_path\":\"$R/sandbox/$2\"}}" | env PATH="$1" CLAUDE_PROJECT_DIR="$R/sandbox" python3 sandbox/scripts/aios/aios.py hook pre-edit; }
printf 'founder, .aios/config.json: '; out=$(edit "$(dirname $GH):/usr/bin:/bin" .aios/config.json); [ -z "$out" ] && echo allowed || echo "$out"
printf 'operator, .aios/config.json: '; edit "$R/bin-op:/usr/bin:/bin" .aios/config.json | python3 -c 'import json,sys;d=json.load(sys.stdin)["hookSpecificOutput"];print(d["permissionDecision"])'
printf 'operator, 02_Deliverables/draft.md: '; out=$(edit "$R/bin-op:/usr/bin:/bin" 02_Deliverables/draft.md); [ -z "$out" ] && echo allowed || echo "$out"
printf 'no gh (web-like), .claude/settings.json: '; edit "$R/bin-none:/usr/bin:/bin" .claude/settings.json | python3 -c 'import json,sys;d=json.load(sys.stdin)["hookSpecificOutput"];print(d["permissionDecision"], "| names desktop route:", "desktop app" in d["permissionDecisionReason"])'

say "R5 founder lane at the pull request (boundary check, as CI runs it)"
cd sandbox; git switch -q -c op-change; echo '{"tampered":true}' > .aios/roles.json; git -c user.email=o@example.invalid -c user.name=O commit -qam "operator edits roles"
BASE=$(git rev-parse main); HEAD=$(git rev-parse HEAD)
python3 scripts/aios/aios.py boundary check-pr --repo . --base $BASE --head $HEAD --author rehearsal-operator --approved-by "" | tail -2; echo "operator, no approval: exit=${PIPESTATUS[0]}"
python3 scripts/aios/aios.py boundary check-pr --repo . --base $BASE --head $HEAD --author rehearsal-operator --approved-by "$LOGIN" | tail -1; echo "operator, founder approved this commit: exit=${PIPESTATUS[0]}"
git switch -q main; git branch -q -D op-change; cd ..

say "R6 safety hooks with and without their programs"
printf 'git guard WITH node, "git push --force": '; echo '{"tool_name":"Bash","tool_input":{"command":"git push --force origin main"}}' | (cd sandbox && CLAUDE_PROJECT_DIR=$PWD node .claude/hooks/guard-dangerous-git.js) | python3 -c 'import json,sys;print("decision =", json.load(sys.stdin)["hookSpecificOutput"]["permissionDecision"], "(ask = Claude Code stops and asks the person; not a block)")' 
printf 'git guard WITHOUT node: '; echo '{}' | env PATH="$R/bin-none:/usr/bin:/bin" sh -c 'node x' >/dev/null 2>&1; echo "exit=$? (127 = program missing; Claude Code treats this as non-blocking, so the command runs)"
printf 'edit hook WITHOUT python3: '; echo '{}' | env PATH="/usr/bin:/bin" /bin/sh -c 'command -v python3 >/dev/null || exit 127; python3 -c 1' >/dev/null 2>&1; echo "exit=$? (0 means /usr/bin/python3 exists on this Mac; a machine without it gets 127)"
printf 'start WITHOUT node: '; (cd sandbox && env PATH="$R/bin-op:/usr/bin:/bin" python3 scripts/aios/aios.py start 2>&1 | grep -c "node is not installed")

say "R7 upgrade: approved 2.6.0 -> 2.7.0 candidate, own work kept"
git init -q --bare up.git; git clone -q up.git up 2>/dev/null
python3 starter/scripts/aios/aios.py install --release starter/releases/starter-2.6.0.json --target up --config org.json | head -2
cd up; echo "# my own note" > 02_Deliverables/mine.md; echo "# edited by me" >> CLAUDE.md; git add -A; git -c user.email=r@example.invalid -c user.name=R commit -qm "install + my work"
python3 ../starter/scripts/aios/aios.py upgrade --release ../rehearsal-2.7.0.json --target . --repo ../starter 2>&1 | tail -3; echo "upgrade exit=${PIPESTATUS[0]}"
python3 scripts/aios/aios.py verify --target . --repo ../starter | grep verdict
grep -c "edited by me" CLAUDE.md; ls 02_Deliverables/mine.md; git status --porcelain | wc -l | tr -d ' '
cd ..

say "R8 release tag route: tag on the approval commit passes, tag on the pin fails (local clone only)"
cd starter
python3 - <<EOF
import json; m=json.load(open('releases/starter-2.7.0.json')); m['status']='approved'
m['approval']={'approved_by':'REHEARSAL-ONLY-NOT-AN-APPROVAL','approved_at':'2026-09-29T00:00:00Z'}
json.dump(m,open('releases/starter-2.7.0.json','w'),indent=2)
EOF
git -c user.email=r@example.invalid -c user.name=R commit -qam "rehearsal approval (local only)"
git tag rehearsal-approval HEAD; git tag rehearsal-pin $(python3 -c "import json;print(json.load(open('releases/starter-2.7.0.json'))['created_from']['git_rev'])")
python3 scripts/aios/aios.py release check-tag rehearsal-approval --release-id starter-2.7.0 | tail -1
python3 scripts/aios/aios.py release check-tag rehearsal-pin --release-id starter-2.7.0 | sed -n 3,4p
cd ..
echo; echo "rehearsal done"
