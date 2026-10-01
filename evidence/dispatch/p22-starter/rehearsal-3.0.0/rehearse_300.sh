#!/bin/bash
# Starter 3.0.0 (DRAFT) learner/P03 rehearsal from a fresh GitHub clone. The real records stay
# draft; rehearsal COPIES carry a rehearsal-only approval string so the installer runs, and it
# still re-hashes every file against the pinned commit.
set -u
R=<scratch>/r300
rm -rf "$R"; mkdir -p "$R"; cd "$R"
say(){ printf '\n### %s\n' "$*"; }
LOGIN=$(gh api user --jq .login)
git clone -q --branch exec/p22-starter-3.0-20261001 https://github.com/funnel-futurist/ff-aios-starter.git starter
cp ../starter-3.0.0.local.json starter/releases/starter-3.0.0.json   # the draft record cut locally, not yet pushed
python3 - <<EOF
import json
for v,src in (("3.0.0","starter/releases/starter-3.0.0.json"),("2.7.0","starter/releases/starter-2.7.0.json")):
    m=json.load(open(src)); m["status"]="approved"
    m["approval"]={"approved_by":"REHEARSAL-ONLY-NOT-AN-APPROVAL","approved_at":"2026-10-01T00:00:00Z"}
    json.dump(m,open("rehearsal-%s.json"%v,"w"),indent=2)
print("3.0.0 pin:", json.load(open("starter/releases/starter-3.0.0.json"))["created_from"]["git_rev"])
EOF
cat > org.json <<EOF
{"schema":"ff-aios-starter/org-config@1","org_id":"rehearsal-co","repository":"rehearsal/rehearsal-co-os",
 "people":[{"github":"$LOGIN","role":"founder","display_name":"Rehearsal installer"},
           {"github":"rehearsal-operator","role":"operator","display_name":"Invented operator"}],
 "credentials":{},"code_owners":{"REPO_OWNER":["@$LOGIN"],"PRIMARY_REVIEWER":["@$LOGIN"]}}
EOF
A="python3 starter/scripts/aios/aios.py"

say "R1 the real 3.0.0 draft record is refused"
$A install --release starter/releases/starter-3.0.0.json --target d1 --config org.json 2>&1 | head -2; rm -rf d1

say "R2 fresh 3.0 install into an empty repository (the ff-00-instance route)"
git init -q --bare fresh.git; git clone -q fresh.git fresh 2>/dev/null
$A install --release rehearsal-3.0.0.json --target fresh --config org.json | head -4
cd fresh
sed -i '' 's/^repo: ""/repo: "rehearsal-co-os"/' estate.yaml
git add -A; git -c user.email=r@example.invalid -c user.name=R commit -qm "Install AIOS 3.0"; git push -q origin HEAD:main
python3 scripts/aios/aios.py start | sed -n 1,6p
python3 scripts/aios/aios.py verify --target . --repo ../starter | grep verdict
python3 scripts/aios/aios.py instance check --target . | grep -E "FAIL|FLAG|verdict"
echo "top level: $(ls -d */ | tr '\n' ' ')"
cd ..

say "R3 a 2.7.0 workspace with real work, upgraded to 3.0"
git init -q --bare up.git; git clone -q up.git up 2>/dev/null
$A install --release rehearsal-2.7.0.json --target up --config org.json | head -2
cd up
printf '# Ours\nOur F6 lives in 01_Foundations/.\n' > CLAUDE.md
printf 'OUR MARKET\n' > 01_Foundations/market_analysis/_workspace.md
printf 'launch email\n' > 02_Deliverables/emails/launch.md
printf 'note to self\n' > 07_Setup/my_note.md
mkdir -p 11_Projects/main-website; printf '{"name":"site"}\n' > 11_Projects/main-website/package.json
printf '| 2026-10-01 | moved to 3.0 |\n' >> 06_Communication/decisions_log.md
git add -A; git -c user.email=r@example.invalid -c user.name=R commit -qm "2.7.0 + our work"
python3 ../starter/scripts/aios/aios.py upgrade --release ../rehearsal-3.0.0.json --target . --repo ../starter; echo "upgrade exit=$?"
echo "2.x folders left: $(ls -d 0[1-9]_*/ 11_*/ 2>/dev/null | grep -vE '^0[0-5]_(AIOS|Creation|Team_Ops|RevOps|Attention|Jobs)/' | wc -l | tr -d ' ')"
for f in 00_AIOS/company/market_analysis/_workspace.md 04_Attention/campaigns/emails/launch.md 99_Archive/07_Setup/my_note.md 02_Team_Ops/projects/main-website/package.json; do printf '%s: %s\n' "$f" "$(cat $f 2>/dev/null | head -1)"; done
tail -1 00_AIOS/decisions_log.md
python3 scripts/aios/aios.py verify --target . --repo ../starter | grep verdict
python3 scripts/aios/aios.py instance check --target . | grep -E "FAIL|verdict"
git add -A; echo "git sees: $(git diff --cached -M --name-status | grep -c '^R') renames, $(git diff --cached -M --name-status | grep -c '^D') deletions, $(git diff --cached -M --name-status | grep -c '^A') additions"
git -c user.email=r@example.invalid -c user.name=R commit -qm "Upgrade to 3.0"
cd ..

say "R4 the founder lane at its 3.0 path, in the upgraded workspace"
mkdir -p bin-op; printf '#!/bin/sh\n[ "$1" = api ] && [ "$2" = user ] && { echo rehearsal-operator; exit 0; }; exit 1\n' > bin-op/gh; chmod +x bin-op/gh
ln -sf "$(command -v python3)" bin-op/python3; ln -sf "$(command -v git)" bin-op/git
rm -f up/.aios/.identity* 2>/dev/null
echo "{\"tool_name\":\"Edit\",\"tool_input\":{\"file_path\":\"$R/up/00_AIOS/company/offer_economics/_workspace.md\"}}" | env PATH="$R/bin-op:/usr/bin:/bin" CLAUDE_PROJECT_DIR="$R/up" python3 up/scripts/aios/aios.py hook pre-edit | python3 -c 'import json,sys;print("operator editing offer_economics:", json.load(sys.stdin)["hookSpecificOutput"]["permissionDecision"])'

say "R5 rollback 3.0 -> 2.7.0 puts every file back"
cd up
python3 scripts/aios/aios.py rollback --target . | head -3
for f in 01_Foundations/market_analysis/_workspace.md 02_Deliverables/emails/launch.md 07_Setup/my_note.md 11_Projects/main-website/package.json; do printf '%s: %s\n' "$f" "$([ -f $f ] && echo back || echo MISSING)"; done
echo "3.0 folders left after rollback: $(ls -d 00_AIOS 01_Creation/outputs 05_Jobs 2>/dev/null | wc -l | tr -d ' ')"
python3 scripts/aios/aios.py verify --target . | grep verdict
git status --porcelain | wc -l | tr -d ' ' | sed 's/^/files differing from the committed 3.0 state: /'
cd ..

say "R6 Workspace Kit over the fresh 3.0 instance"
cat > vault.json <<EOF
{"schema":"ff-aios-starter/workspace@1","workspace_name":"Rehearsal Co Operating System","company":"Rehearsal Co (invented)",
 "repos":{"aios":{"domain":"aios","title":"AIOS instance (starter-3.0.0 candidate)","url":"$R/fresh.git","branch":"main","path":"aios","state":"active","start_page":"START_HERE.md"}}}
EOF
$A workspace init --manifest vault.json --parent "$R/vault" | head -3
grep -c "aios/START_HERE.md" "$R/vault/START-HERE.md"
echo; echo "rehearsal done"
