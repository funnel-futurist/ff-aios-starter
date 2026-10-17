#!/usr/bin/env python3
"""Rehearsal: Starter 3.1's `adopt --existing` against a throwaway copy of FF's real ai-os (G81, G98).

usage: rehearse_310_aios.py <empty scratch dir> --aios <local ai-os clone> [--branch <starter branch>]

Nothing touches the real ai-os. Steps:
  1. a shared clone of ai-os at origin/main (detached), and a fresh GitHub clone of the Starter branch;
  2. a draft record for the candidate, with a REHEARSAL-ONLY approval copy;
  3. in the ai-os copy only: the two CODEOWNERS rules FF's adoption PR adds for the ownership list
     (the install record and the plan; owner decision C3), with the owners the copy's own /.github/
     rule names; FF's own role policy (G81 decision 2 draft: the founder lane and its reviewer
     accounts read from the copy's CODEOWNERS, as founder_lane_reviewers per G98) and the adoption
     plan, then a commit;
  4. the real `aios adopt --existing`, run by a stub founder identity;
  5. checks: exactly the 18 adopted files plus the config and record are new; no tracked file
     changed (ai-os's own 01_Foundations included); verify --repo; instance check; start;
  6. `aios rollback --repo <the starter>`, back to exactly the committed state.
The people map here is REHEARSAL-ONLY: who holds which business role in FF is FF's to state.
"""

import argparse
import json
import os
import subprocess
import sys

RESULTS = []
ADOPT = ["scripts/aios/**", ".aios/.gitignore", ".template_version.json"]


def lane_from_codeowners(text, parse):
    """FF's founder lane and its reviewers, read from the copy's own CODEOWNERS at run time (G81
    decision 2: the lane is exactly what ai-os's CODEOWNERS already owner-gates, where the Starter's
    check can verify it). Nothing of ai-os's is written into this public file."""
    lane, reviewers = [], set()
    for _lineno, pattern, owners in parse(text):
        p = pattern.lstrip("/")
        glob = p[:-1] + "/**" if p.endswith("/") else p
        base = glob[:-3] if glob.endswith("/**") else glob
        if any(c in base for c in "*?["):
            continue  # a wildcard rule: GitHub enforces it at review; the check can't prove it
        lane.append(glob)
        reviewers.update(o for o in owners if o.startswith("@") and "/" not in o)
    return lane, sorted(reviewers)


def check(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print("  %s  %s%s" % ("PASS" if ok else "FAIL", name, (": " + detail) if detail else ""), flush=True)


def sh(cmd, cwd=None, env=None):
    e = dict(os.environ)
    e.update(env or {})
    p = subprocess.run(cmd, cwd=cwd, env=e, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return p.returncode, p.stdout.decode("utf-8", "replace")


def git(repo, *args):
    return sh(["git", "-C", repo] + list(args))[1].strip()


def state(ws):
    """What a person could notice: every tracked file's index entry and working-tree diff, and the
    full untracked and ignored listing."""
    return {"index": git(ws, "ls-files", "-s"), "diff": git(ws, "diff", "--stat"),
            "status": git(ws, "status", "--porcelain", "--ignored", "--untracked-files=all")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--aios", required=True)
    ap.add_argument("--branch", default="exec/lane01-starter-3.1.0-20261015")
    a = ap.parse_args()
    R = os.path.abspath(a.root)
    # Never deletes anything it didn't make: the root must be new or empty (independent review).
    if os.path.lexists(R) and (not os.path.isdir(R) or os.path.islink(R) or os.listdir(R)):
        sys.exit("refusing: %s exists and isn't an empty folder; name a new scratch folder" % R)
    os.makedirs(os.path.join(R, "bin"))
    with open(os.path.join(R, "bin", "gh"), "w") as fh:
        fh.write('#!/bin/sh\n[ "$1" = api ] && [ "$2" = user ] && { echo phoenix-ship-it; exit 0; }; exit 1\n')
    os.chmod(os.path.join(R, "bin", "gh"), 0o755)
    env = {"PATH": os.path.join(R, "bin") + os.pathsep + os.environ["PATH"], "AIOS_NO_RELEASE_NOTICE": "1"}

    print("### S1 the copies")
    st = os.path.join(R, "starter")
    sh(["git", "clone", "-q", "--branch", a.branch, "https://github.com/funnel-futurist/ff-aios-starter.git", st])
    print("starter: " + git(st, "log", "--oneline", "-1"))
    ws = os.path.join(R, "ai-os")
    sh(["git", "clone", "-q", "--shared", "--no-checkout", a.aios, ws])
    main_rev = git(a.aios, "rev-parse", "origin/main")
    sh(["git", "-C", ws, "checkout", "-q", "--detach", main_rev])
    print("ai-os copy: main at " + git(ws, "rev-parse", "--short", "HEAD"))
    aios = [sys.executable, os.path.join(st, "scripts/aios/aios.py")]

    print("\n### S2 the candidate record (draft), and a REHEARSAL-ONLY approval copy")
    committed = os.path.join(st, "releases/starter-3.1.0.json")
    if os.path.isfile(committed):
        # The branch's own draft record, so `verify --repo` confirms the very pin it names.
        code, man = 0, json.load(open(committed))
        pin = man["created_from"]["git_rev"]
    else:  # the bare code commit, before its record: build the draft the way the release does
        pin = git(st, "rev-parse", "HEAD")
        code, out = sh(aios + ["release", "build", "--repo", st, "--version", "3.1.0", "--rev", pin, "--branch",
                               a.branch, "--credentials", os.path.join(st, "release/credential_refs.json"),
                               "--min-upgrade-from", "2.6.0", "--out", os.path.join(R, "draft-3.1.0.json")])
        man = json.load(open(os.path.join(R, "draft-3.1.0.json")))
    man["status"] = "approved"
    man["approval"] = {"approved_by": "REHEARSAL-ONLY-NOT-AN-APPROVAL", "approved_at": "2026-10-15T00:00:00Z"}
    rel = os.path.join(R, "rehearsal-3.1.0.json")
    json.dump(man, open(rel, "w"), indent=2)
    check("record built at %s (%d files)" % (pin[:7], len(man["files"])), code == 0)

    print("\n### S3 FF's own role policy and adoption plan, committed in the copy")
    sys.path.insert(0, os.path.join(st, "scripts/aios"))
    from aioslib import governance  # noqa: E402
    # C3: the ownership list joins the lane the way FF's adoption PR adds it, with the owners ai-os's own
    # /.github/ rule already names (read here, never written into this public file).
    codeowners = os.path.join(ws, ".github/CODEOWNERS")
    with open(codeowners) as fh:
        text = fh.read()
    gate = [o for _l, pattern, o in governance.parse(text) if pattern.rstrip("/") == "/.github"]
    check("the copy's CODEOWNERS has a /.github/ rule to take the owners from", bool(gate and gate[-1]))
    with open(codeowners, "a") as fh:
        fh.write("".join("%s %s\n" % (p, " ".join(gate[-1])) for p in ("/.aios/install.json", "/.aios/adoption.json")))
    with open(codeowners) as fh:
        LANE, REVIEWERS = lane_from_codeowners(fh.read(), governance.parse)
    check("FF's founder lane holds the ownership list (C3)",
          ".aios/install.json" in LANE and ".aios/adoption.json" in LANE)
    print("founder lane: %d path(s) from the copy's CODEOWNERS; %d reviewer account(s) declared"
          % (len(LANE), len(REVIEWERS)))
    policy = json.loads(git(st, "show", "HEAD:.aios/roles.json"))
    policy["_comment"] = ("FF's own role policy for ai-os (instance-owned; G81 decision 2 draft). The founder "
                          "lane is ai-os's own CODEOWNERS-gated paths. founder_lane_reviewers is permission to "
                          "approve them (G98), not founder status, which is each person's role in the people map.")
    policy["roles"]["operator"]["paths_denied"] = LANE
    policy["founder_lane_reviewers"] = REVIEWERS
    policy["entries"]["operator"]["skills"] = ["start-my-day", "review-queue", "resolve-conflict", "wrap-up"]
    policy["entries"]["founder"]["skills"] = ["start-my-day", "project_management", "review-queue", "wrap-up"]
    os.makedirs(os.path.join(ws, ".aios"), exist_ok=True)
    json.dump(policy, open(os.path.join(ws, ".aios/roles.json"), "w"), indent=2)
    paths = [e["path"] for e in man["files"]]
    adopt_hits = [p for p in paths if p.startswith("scripts/aios/") or p in (".aios/.gitignore", ".template_version.json")]
    owned = sorted(p for p in paths if p not in adopt_hits and os.path.lexists(os.path.join(ws, p)))
    exclude = sorted(p for p in paths if p not in adopt_hits and p not in owned)
    plan = {"schema": "ff-aios-starter/adoption@1", "adopt": ADOPT, "instance_owned": owned, "exclude": exclude}
    json.dump(plan, open(os.path.join(ws, ".aios/adoption.json"), "w"), indent=2)
    G = ["git", "-C", ws, "-c", "user.name=rehearsal", "-c", "user.email=rehearsal@example.invalid"]
    sh(G + ["add", ".aios/roles.json", ".aios/adoption.json", ".github/CODEOWNERS"])
    sh(G + ["commit", "-qm", "FF's role policy, adoption plan and ownership-list code owners (rehearsal copy)"])
    check("plan: %d adopt, %d instance-owned (FF's roles.json among them), %d excluded, %d in all"
          % (len(adopt_hits), len(owned), len(exclude), len(paths)),
          len(adopt_hits) == 18 and ".aios/roles.json" in owned and len(adopt_hits) + len(owned) + len(exclude) == len(paths))
    # A REHEARSAL-ONLY people map: the operator the stub identity names is the founder; every other
    # reviewer account is an operator (review permission is not founder status, G98).
    me = "phoenix-ship-it"
    people = [{"github": me, "role": "founder", "display_name": "REHEARSAL"}] + [
        {"github": r.lstrip("@"), "role": "operator", "display_name": "REHEARSAL"}
        for r in REVIEWERS if r.lstrip("@").lower() != me]
    json.dump({"schema": "ff-aios-starter/org-config@1", "org_id": "funnel-futurist", "repository": "funnel-futurist/ai-os",
               "people": people, "credentials": {}, "code_owners": {}}, open(os.path.join(R, "org.json"), "w"))

    print("\n### S4 adopt --existing (the real CLI)")
    before = state(ws)
    owned_bytes = {p: git(ws, "hash-object", p) for p in owned}
    code, out = sh(aios + ["adopt", "--existing", "--release", rel, "--target", ws, "--config",
                           os.path.join(R, "org.json"), "--repo", st], env=env)
    print("\n".join("    " + l for l in out.strip().splitlines()[:8]))
    check("adopted (exit %d)" % code, code == 0)

    print("\n### S5 what changed")
    after = state(ws)
    check("no tracked file changed (index identical, no diff): ai-os's own 01_Foundations and CLAUDE.md included",
          after["index"] == before["index"] and after["diff"] == "")
    new = sorted(set(after["status"].splitlines()) - set(before["status"].splitlines()))
    created = sorted(l[3:] for l in new if l.startswith("?? "))
    want = sorted(adopt_hits + [".aios/config.json", ".aios/install.json"])
    check("exactly the 18 adopted files plus the config and record are new (%d)" % len(created), created == want,
          "" if created == want else "extra %s missing %s" % (sorted(set(created) - set(want))[:5], sorted(set(want) - set(created))[:5]))
    check("every instance-owned file keeps its bytes (%d)" % len(owned),
          all(git(ws, "hash-object", p) == h for p, h in owned_bytes.items()))
    code, out = sh(aios + ["verify", "--target", ws, "--repo", st])
    check("verify --repo: %s" % next((l.strip() for l in out.splitlines() if l.startswith("verdict")), "?"), code == 0,
          "" if code == 0 else " | ".join(l.strip() for l in out.splitlines() if l.strip().startswith("-"))[:600])
    code, out = sh(aios + ["instance", "check", "--offline", "--repo-slug", "funnel-futurist/ai-os"], cwd=ws, env=env)
    lane = [l for l in out.splitlines() if any(" founder lane %s (" % g in l for g in LANE)]
    check("instance check: all %d founder-lane paths PASS with the declared reviewers" % len(LANE),
          len(lane) == len(LANE) and all(l.strip().startswith("PASS") for l in lane))
    owns = [l.strip() for l in out.splitlines() if " ownership list " in l]
    check("instance check: the ownership list (record and plan) is in the lane, PASS (C3)",
          len(owns) == 2 and all(l.startswith("PASS") for l in owns), " | ".join(owns)[:400])
    check("instance check says reviewers are not founder status",
          any("not founder status" in l for l in out.splitlines()))
    check("instance check fails closed offline (enforcement unverified), exit %d" % code,
          code != 0 and "GitHub enforcement not checked" in out)
    code, out = sh(aios + ["start", "--target", ws], env=env)
    check("start runs and names the release and the founder role (exit %d)" % code,
          code == 0 and "3.1.0" in out and "founder" in out)

    print("\n### S6 rollback")
    code, out = sh(aios + ["rollback", "--target", ws, "--repo", st], env=env)  # a finished adoption: the release's source
    print("    " + out.strip().splitlines()[0])
    check("rollback (exit %d) returns the copy to exactly its committed state" % code,
          code == 0 and state(ws) == before)
    print("\nRESULT: %d passed, %d failed" % (sum(RESULTS), len(RESULTS) - sum(RESULTS)))
    return 0 if all(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
