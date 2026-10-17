#!/usr/bin/env python3
"""Exact-candidate rehearsal for starter-3.1.0 (DRAFT): every supported start upgrading to it.

The 3.0 rehearsal (release-3.0.0/rehearse_300.py), retargeted at 3.1.0: each 2.x start still makes
the folder move on its way to 3.1.0, with every check it had; and a 3.0.0 workspace, installed by
3.0.0's own installer, upgrades as an ordinary upgrade (from_300 below). Adopting into an existing
repository is rehearsed separately (rehearse_310_aios.py).

What follows is the 3.0 rehearsal's own description:

usage: python3 rehearse_300.py <empty scratch dir> [--source URL-or-path] [--branch BRANCH] [--quick]

What it proves, from a fresh clone of the candidate branch:

* Every starting version the release accepts (min_upgrade_from 2.6.0, so all eight release records) is
  installed by ITS OWN installer, given the client's own work in every old folder, and upgraded
  straight to 3.0 by the candidate. Upgrade chains (2.6.0 -> 2.8.0 -> 2.10.0 -> 3.0 and
  2.7.0 -> 2.9.0 -> 3.0), each step run by that release's own tool, and an adopted workspace, too.
* For every one: an independent proof (this script's own folder map, not the installer's) that
  each client file is at its new path with identical bytes, size and mode and nothing else of the
  client's changed; `verify`; git sees renames; then rollback compared field by field with a full
  snapshot taken before the upgrade (every file, every folder, git status with ignored files).
* For every one, on a copy: an existing destination and a case twin are refused with nothing
  changed; a hard kill (os._exit, as kill -9) at each of seven points is recovered exactly, and a
  fresh upgrade then succeeds.
* A heavy workspace: a 120 MB file, thousands of git-ignored dependency files, and real SIGKILLs
  at random moments. A case-sensitive disk image: twins that can only exist there are refused.

The real record stays draft. COPIES with a rehearsal-only approval string let the installers run;
they still re-hash every installed file against the pinned commit. 2.6.1 and 2.7.1 were never
approved, so no real workspace carries their install record: their trees are installed here with
the same rehearsal-only copy so the move is still exercised on their layouts. Identity comes from
a stub `gh`. Nothing here pushes, tags or calls Vercel; the live Vercel check is separate.
"""

import argparse
import hashlib
import json
import os
import random
import shutil
import signal
import stat
import subprocess
import sys
import time
import unicodedata

OLD = ["01_Foundations", "02_Deliverables", "03_Quality_Control", "04_Customer_Journey", "05_Assets",
       "06_Communication", "07_Setup", "08_Automations", "09_Archive", "10_Departments", "11_Projects"]
VERSIONS = ["2.6.0", "2.6.1", "2.7.0", "2.7.1", "2.7.2", "2.8.0", "2.9.0", "2.10.0"]
NEVER_APPROVED = ("2.6.1", "2.7.1")
TARGET = "3.1.0"  # the candidate; 3.0.0 is a starting version here
KILL_POINTS = ["layout.before_moves", "layout.linked_not_unlinked", "layout.after_first_move",
               "layout.mid_moves", "layout.after_moves", "upgrade.mid_write", "upgrade.before_record"]
ROLLBACK_KILL_POINTS = ["rollback.before_restore", "rollback.after_restore", "rollback.after_reverse"]
JUNK = (".ds_store", "thumbs.db", "desktop.ini")
MAP_LINE = "@00_AIOS/routing.md"
RESULTS = []


def say(msg=""):
    print(msg, flush=True)


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    say("  %s  %s%s" % ("PASS" if ok else "FAIL", name, (": " + detail) if detail else ""))
    return ok


def sh(cmd, cwd=None, env=None, timeout=900):
    e = dict(os.environ)
    e.update(env or {})
    p = subprocess.run(cmd, cwd=cwd, env=e, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       timeout=timeout)
    return p.returncode, p.stdout.decode("utf-8", "replace")


def git(ws, *args):
    return sh(["git", "-c", "user.email=r@example.invalid", "-c", "user.name=Rehearsal", "-C", ws]
              + list(args))


def write(root, rel, data, mode=None):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb" if isinstance(data, bytes) else "w") as fh:
        fh.write(data)
    if mode:
        os.chmod(path, mode)


# ─── the independent yardsticks ─────────────────────────────────────────────

def snapshot(root, backups=()):
    """Every file (sha256, size, mode), folder and link, plus git status with ignored files and
    HEAD. Set aside only: new upgrade attempts under .aios/backups/ (kept on purpose)."""
    keep = set(backups)
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root).replace(os.sep, "/")
        dirnames[:] = sorted(d for d in dirnames if not (rel_dir == "." and d == ".git")
                             and not (rel_dir == ".aios/backups" and d not in keep))
        for d in dirnames:
            rel = d if rel_dir == "." else rel_dir + "/" + d
            if rel != ".aios/backups":
                out[rel + "/"] = ("dir",)
        for name in filenames:
            rel = name if rel_dir == "." else rel_dir + "/" + name
            if rel == ".aios/lock":
                continue
            full = os.path.join(root, rel)
            st = os.lstat(full)
            if stat.S_ISLNK(st.st_mode):
                out[rel] = ("link", os.readlink(full))
                continue
            h = hashlib.sha256()
            with open(full, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
            out[rel] = ("file", h.hexdigest(), st.st_size, stat.S_IMODE(st.st_mode))
    if os.path.isdir(os.path.join(root, ".git")):
        _c, status = sh(["git", "-C", root, "status", "--porcelain", "--ignored", "--untracked-files=all"])
        out["<git status>"] = "\n".join(
            l for l in status.splitlines()
            if not (l.startswith("!! .aios/backups/") and l[17:].split("/", 1)[0] not in keep))
        out["<git HEAD>"] = sh(["git", "-C", root, "rev-parse", "HEAD"])[1].strip()
    return out


def backups_of(ws):
    d = os.path.join(ws, ".aios", "backups")
    return sorted(os.listdir(d)) if os.path.isdir(d) else []


def differences(a, b):
    return [k for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)]


def destination(rel, moves):
    """This script's own reading of the approved map (longest rule wins), not the installer's."""
    best = None
    for m in moves:
        src = m["from"]
        if (src.endswith("/") and (rel + "/").startswith(src)) or rel == src:
            if best is None or len(src) > len(best["from"]):
                best = m
    if best is None:
        return None
    if not best["from"].endswith("/"):
        return best["to"]
    return (best["to"] + (rel + "/")[len(best["from"]):]).rstrip("/")


def nfc_fold(p):
    return unicodedata.normalize("NFC", p).casefold()


def independent_proof(ws, pre, post, pre_claude, layout, old_record, new_record):
    """Every client file at its mapped path with identical bytes; nothing else of the client's
    changed; the only CLAUDE.md change is appended declared lines. Returns problems."""
    problems = []
    moves = layout["moves"]
    old_managed = {e["path"] for e in old_record.get("managed") or []}
    new_managed = {e["path"] for e in new_record.get("managed") or []}
    created = {e["path"] for e in new_record.get("created_seeds") or []}
    backup = new_record["previous"]["backup"]
    explained = set(new_managed) | created | {".aios/install.json"}
    for p, v in pre.items():
        if p.startswith("<"):
            continue
        top = p.split("/", 1)[0]
        if top in OLD:
            if v[0] == "dir":
                q = destination(p.rstrip("/"), moves)
                if p.rstrip("/") != top and not any(k.startswith(p) for k in pre if k != p):
                    if (q + "/") not in post:
                        problems.append("empty folder %s missing at %s" % (p, q))
                    explained.add(q + "/")
                continue
            if p in old_managed:
                continue  # release-owned; 3.0 retires it
            if p.rsplit("/", 1)[-1].casefold() in JUNK:
                kept = os.path.join(ws, backup, "quarantine", p)
                if not os.path.isfile(kept) or hashlib.sha256(open(kept, "rb").read()).hexdigest() != v[1]:
                    problems.append("junk %s not kept byte for byte in the backup" % p)
                continue
            q = destination(p, moves)
            if post.get(q) != v:
                problems.append("%s -> %s: %s" % (p, q, "missing" if q not in post else "bytes/size/mode differ"))
            if p in post:
                problems.append("%s still at its old path" % p)
            explained.add(q)
            continue
        if p in old_managed or p in new_managed or p == ".aios/install.json":
            continue
        if p == "CLAUDE.md":
            now = open(os.path.join(ws, "CLAUDE.md"), "rb").read()
            tail = now[len(pre_claude):].decode("utf-8")
            if not now.startswith(pre_claude) or any(
                    l.strip() and l.strip() not in (MAP_LINE, "@.aios/operator_core/OPERATOR_CORE.md")
                    for l in tail.splitlines()):
                problems.append("CLAUDE.md changed beyond appended declared lines")
            continue
        if v[0] == "dir":
            continue
        if post.get(p) != v:
            problems.append("%s changed and isn't the release's" % p)
    for p in post:
        if p.startswith("<") or p in pre or p in explained:
            continue
        if p.endswith("/") and any(k.startswith(p) for k in explained | set(post) if k != p):
            continue
        if p.startswith(".aios/"):
            continue  # the installer's own records
        problems.append("unexplained new path %s" % p)
    return problems


# ─── the client's own work ──────────────────────────────────────────────────

def client_content(ws):
    """Realistic work in every old folder, plus things that must never move or change."""
    w = lambda rel, data, mode=None: write(ws, rel, data, mode)
    if os.path.isfile(os.path.join(ws, "01_Foundations/avatar_analysis/_workspace.md")):
        with open(os.path.join(ws, "01_Foundations/avatar_analysis/_workspace.md"), "a") as fh:
            fh.write("\n## Our real avatar\nOwners of two-location clinics.\n")  # an edited starter file
    w("01_Foundations/offer_economics/pricing.md", "# Pricing\nCore offer: 4,000 a month.\n")
    w("02_Deliverables/copy/spring_email.md", "Subject: spring\n")
    w("02_Deliverables/report.md", "# Q3 report\n")
    w("02_Deliverables/funnels/webinar_funnel.md", "# webinar funnel\n")
    w("02_Deliverables/ads/fb_ad_v2.md", "ad copy\n")
    w(unicodedata.normalize("NFD", "02_Deliverables/résumé_notes.md"), "decomposed accent in the name\n")
    os.makedirs(os.path.join(ws, "02_Deliverables/empty_drafts"), exist_ok=True)
    if os.path.isfile(os.path.join(ws, "03_Quality_Control/qc_preferences.md")):
        with open(os.path.join(ws, "03_Quality_Control/qc_preferences.md"), "a") as fh:
            fh.write("\nNever say 'leverage'.\n")
    w("04_Customer_Journey/my_onboarding.md", "# onboarding\n")
    w("05_Assets/brand_guide/logo.png", bytes(range(256)) * 64)
    w("05_Assets/photos/team photo.jpg", os.urandom(2 * 1024 * 1024))
    w("06_Communication/meeting_notes/2026-10-01.md", "# standup\n")
    w("07_Setup/my_setup_notes.md", "my own notes about our setup\n")
    w("08_Automations/run_report.sh", "#!/bin/sh\necho report\n", 0o755)
    w("09_Archive/2025/old_offer.md", "# old offer\n")
    w("10_Departments/sales/README.md", "# sales department\n")
    w("11_Projects/q4_launch/PLAN.md", "# Q4 launch\n")
    w("11_Projects/q4_launch/.env.local", "Q4_KEY=placeholder-not-a-secret\n")  # git-ignored
    w("01_Foundations/.DS_Store", b"\x00\x00\x00\x01Bud1")
    w("05_Assets/Thumbs.db", b"thumbs")
    w(".claude/skills/my_skill/SKILL.md", "---\nname: my_skill\ndescription: mine\n---\nmine\n")
    w(".claude/settings.local.json", '{"permissions": {"deny": ["Bash(rm -rf *)"]}}\n')
    with open(os.path.join(ws, "CLAUDE.md"), "a") as fh:
        fh.write("\n## My own rule\nAlways answer in British English.\n")
    with open(os.path.join(ws, ".gitignore"), "a") as fh:
        fh.write("\n.env.local\nnode_modules/\n")
    os.makedirs(os.path.join(ws, "scratch_empty"), exist_ok=True)  # an empty folder outside the old ones


def commit_all(ws, msg):
    git(ws, "add", "-A")
    git(ws, "add", "-f", ".claude/settings.local.json")
    return git(ws, "commit", "-qm", msg)


# ─── the run ─────────────────────────────────────────────────────────────────

class Rehearsal(object):

    def __init__(self, root, source, branch, quick):
        self.R = os.path.abspath(root)
        self.source, self.branch, self.quick = source, branch, quick
        self.trees = {}

    def setup(self):
        say("### R0 tools")
        say(sh([sys.executable, "--version"])[1].strip() + " | " + sh(["git", "--version"])[1].strip())
        os.makedirs(os.path.join(self.R, "bin"))
        write(self.R, "bin/gh", '#!/bin/sh\n[ "$1" = api ] && [ "$2" = user ] && { echo rehearsal-founder; exit 0; }; exit 1\n', 0o755)
        os.environ["PATH"] = os.path.join(self.R, "bin") + os.pathsep + os.environ["PATH"]
        os.environ["AIOS_NO_RELEASE_NOTICE"] = "1"
        write(self.R, "org.json", json.dumps({
            "schema": "ff-aios-starter/org-config@1", "org_id": "rehearsal-co",
            "repository": "rehearsal/rehearsal-aios",
            "people": [{"github": "rehearsal-founder", "role": "founder", "display_name": "Founder"},
                       {"github": "rehearsal-operator", "role": "operator", "display_name": "Operator"}],
            "credentials": {}, "code_owners": {"REPO_OWNER": ["@rehearsal-founder"],
                                               "PRIMARY_REVIEWER": ["@rehearsal-founder"]}}))
        say("\n### R1 fresh clone of the candidate")
        self.starter = os.path.join(self.R, "starter")
        code, out = sh(["git", "clone", "-q", "--branch", self.branch, self.source, self.starter])
        if code:
            say(out)
            sys.exit(1)
        say(sh(["git", "-C", self.starter, "log", "--oneline", "-1"])[1].strip())
        record = os.path.join(self.starter, "releases/starter-%s.json" % TARGET)
        if not os.path.isfile(record):
            # The bare code pin, before its record commit: build the draft the same way the release
            # does, so the rehearsal runs on any commit of the branch (independent review).
            pin = sh(["git", "-C", self.starter, "rev-parse", "HEAD"])[1].strip()
            record = os.path.join(self.R, "draft-%s.json" % TARGET)
            code, out = sh([sys.executable, os.path.join(self.starter, "scripts/aios/aios.py"), "release", "build",
                            "--repo", self.starter, "--version", TARGET, "--rev", pin, "--branch", self.branch,
                            "--credentials", os.path.join(self.starter, "release/credential_refs.json"),
                            "--min-upgrade-from", "2.6.0", "--out", record])
            if code:
                say(out)
                sys.exit(1)
        m = json.load(open(record))
        say("record: %s, pin %s, %s" % (m["status"], m["created_from"]["git_rev"], m["counts"]))
        self.layout = m["layout"]
        self.candidate = self.approval_copy(m, TARGET)
        for v in VERSIONS + ["3.0.0"]:
            self.approval_copy(json.load(open(os.path.join(self.starter, "releases/starter-%s.json" % v))), v)

    def approval_copy(self, m, v):
        m = json.loads(json.dumps(m))
        m["status"] = "approved"
        m["approval"] = {"approved_by": "REHEARSAL-ONLY-NOT-AN-APPROVAL", "approved_at": "2026-10-14T00:00:00Z"}
        path = os.path.join(self.R, "rehearsal-%s.json" % v)
        json.dump(m, open(path, "w"), indent=2)
        return path

    def tool(self, v):
        """The aios.py of release v, from a worktree at its own pin."""
        if v == TARGET:
            return os.path.join(self.starter, "scripts/aios/aios.py")
        if v not in self.trees:
            pin = json.load(open(os.path.join(self.R, "rehearsal-%s.json" % v)))["created_from"]["git_rev"]
            tree = os.path.join(self.R, "trees", v)
            sh(["git", "-C", self.starter, "worktree", "add", "-q", "--detach", tree, pin])
            self.trees[v] = tree
        return os.path.join(self.trees[v], "scripts/aios/aios.py")

    def aios(self, v, *args, **kw):
        return sh([sys.executable, self.tool(v)] + list(args), env=kw.get("env"))

    def new_ws(self, name):
        ws = os.path.join(self.R, "ws", name)
        bare = ws + ".git"
        sh(["git", "init", "-q", "--bare", bare])
        sh(["git", "clone", "-q", bare, ws])
        git(ws, "checkout", "-q", "-b", "main")
        git(ws, "remote", "set-url", "origin", "https://github.com/rehearsal/rehearsal-aios.git")
        return ws

    def install(self, v, ws):
        code, out = self.aios(v, "install", "--release", os.path.join(self.R, "rehearsal-%s.json" % v),
                              "--target", ws, "--config", os.path.join(self.R, "org.json"),
                              "--repo", self.starter)
        commit_all(ws, "install %s" % v)
        return code, out

    def upgrade(self, v, ws, dry=False, env=None, vercel_statement=True):
        """The 3.0 move needs a Vercel read or the founder's --no-vercel statement (R-A); these
        workspaces aren't on Vercel. The live Vercel run is vercel_live_300.py."""
        args = ["upgrade", "--release", os.path.join(self.R, "rehearsal-%s.json" % v), "--target", ws,
                "--repo", self.starter] + (["--dry-run"] if dry else [])
        if v == TARGET and vercel_statement:
            args.append("--no-vercel")
        return self.aios(v, *args, env=env)

    def adopt(self, v, ws):
        """A "Use this template" copy of release v's tree, then `adopt` by v's own tool."""
        pin = json.load(open(os.path.join(self.R, "rehearsal-%s.json" % v)))["created_from"]["git_rev"]
        p1 = subprocess.Popen(["git", "-C", self.starter, "archive", pin], stdout=subprocess.PIPE)
        subprocess.run(["tar", "-x", "-C", ws], stdin=p1.stdout)
        p1.wait()
        for rel in ("evidence", "releases", "release", "tests", ".github/CODEOWNERS"):
            full = os.path.join(ws, rel)
            if os.path.isdir(full):
                shutil.rmtree(full)
            elif os.path.isfile(full):
                os.remove(full)
        commit_all(ws, "template copy of %s" % v)
        code, out = self.aios(v, "adopt", "--release", os.path.join(self.R, "rehearsal-%s.json" % v),
                              "--target", ws, "--config", os.path.join(self.R, "org.json"),
                              "--repo", self.starter)
        commit_all(ws, "adopt %s" % v)
        return code, out

    # ── one history, every check ──

    def history(self, name, steps, adopt=False):
        say("\n### H %s: %s" % (name, " -> ".join(steps + [TARGET])))
        ws = self.new_ws(name)
        if adopt:
            code, out = self.adopt(steps[0], ws)
            check("%s: adopt %s" % (name, steps[0]), code == 0, out.strip().splitlines()[0] if code == 0 else out[-400:])
        else:
            code, out = self.install(steps[0], ws)
            check("%s: install %s with its own installer" % (name, steps[0]), code == 0,
                  "" if code == 0 else out[-400:])
        for v in steps[1:]:
            code, out = self.upgrade(v, ws)
            commit_all(ws, "upgrade to %s" % v)
            check("%s: upgrade to %s with %s's own tool" % (name, v, v), code == 0, "" if code == 0 else out[-400:])
        client_content(ws)
        commit_all(ws, "my own work")
        self.full_cycle(name, ws)
        if not self.quick:
            self.failure_cases(name, ws)
        return ws

    def full_cycle(self, name, ws):
        old_record = json.load(open(os.path.join(ws, ".aios/install.json")))
        keep = backups_of(ws)
        pre = snapshot(ws, keep)
        pre_claude = open(os.path.join(ws, "CLAUDE.md"), "rb").read()
        code, out = self.upgrade(TARGET, ws, dry=True, vercel_statement=False)
        check("%s: without a Vercel token or --no-vercel the dry run is BLOCKED, writing nothing" % name,
              code == 5 and "BLOCKED" in out and "--no-vercel" in out and not differences(pre, snapshot(ws, keep)))
        code, out = self.upgrade(TARGET, ws, dry=True)
        moves = sum(1 for l in out.splitlines() if l.startswith("  move:"))
        line_shown = ("one line:  CLAUDE.md gains `%s`" % MAP_LINE) in out
        check("%s: dry run lists %d move(s) and shows the exact map line, writing nothing" % (name, moves),
              code == 0 and line_shown and moves > 0 and not differences(pre, snapshot(ws, keep)),
              "" if code == 0 else out[-400:])
        t0 = time.time()
        code, out = self.upgrade(TARGET, ws)
        took = time.time() - t0
        if not check("%s: upgrade to %s (%.1fs)" % (name, TARGET, took), code == 0, "" if code == 0 else out[-600:]):
            return
        new_record = json.load(open(os.path.join(ws, ".aios/install.json")))
        post = snapshot(ws, keep)
        problems = independent_proof(ws, pre, post, pre_claude, self.layout, old_record, new_record)
        check("%s: independent proof: every client file at its mapped path, same bytes/size/mode; "
              "nothing else of theirs changed (%d moved)" % (name, new_record["layout_migration"]["moved"]),
              not problems, "; ".join(problems[:6]))
        claude_now = open(os.path.join(ws, "CLAUDE.md")).read()
        check("%s: CLAUDE.md gained the map line exactly once" % name, claude_now.count(MAP_LINE) == 1)
        check("%s: no old folder left" % name, not [d for d in OLD if os.path.lexists(os.path.join(ws, d))])
        code, out = self.aios(TARGET, "verify", "--target", ws, "--repo", self.starter)
        check("%s: verify against the pin" % name, code == 0 and "matches the installed release" in out)
        git(ws, "add", "-A")
        _c, ns = git(ws, "diff", "--cached", "-M", "--name-status", "HEAD")
        kinds = {}
        for l in ns.splitlines():
            kinds[l[:1]] = kinds.get(l[:1], 0) + 1
        git(ws, "reset", "-q")
        check("%s: git sees the moves as renames (%s)" % (name, ", ".join("%s %d" % kv for kv in sorted(kinds.items()))),
              kinds.get("R", 0) >= 1)
        proof = json.load(open(os.path.join(ws, new_record["layout_migration"]["proof"])))
        check("%s: layout_proof.json lists every move with its hash" % name,
              len(proof["moved"]) == new_record["layout_migration"]["moved"])
        code, out = self.aios(TARGET, "rollback", "--target", ws)
        diff = differences(pre, snapshot(ws, keep))
        check("%s: rollback = the pre-upgrade snapshot, field for field" % name, code == 0 and not diff,
              "; ".join(diff[:6]) if diff else "")
        # after rollback, upgrade again and leave it upgraded for later checks
        code, out = self.upgrade(TARGET, ws)
        check("%s: upgrade again after the rollback" % name, code == 0, "" if code == 0 else out[-300:])
        self.aios(TARGET, "rollback", "--target", ws)

    def copy_ws(self, ws, suffix):
        dst = ws + "-" + suffix
        if os.path.exists(dst):
            shutil.rmtree(dst)
        shutil.copytree(ws, dst, symlinks=True)
        return dst

    def failure_cases(self, name, ws):
        # F1 an existing destination
        c = self.copy_ws(ws, "f1")
        write(c, "01_Creation/outputs/report.md", "already mine\n")
        commit_all(c, "a 3.0 path already in use")
        keep = backups_of(c)
        pre = snapshot(c, keep)
        code, out = self.upgrade(TARGET, c)
        check("%s: existing destination refused, nothing changed" % name,
              code == 5 and "already exists" in out and not differences(pre, snapshot(c, keep)),
              out.strip().splitlines()[0] if out.strip() else "")
        shutil.rmtree(c)
        # F2 a case twin (two spellings on a case-insensitive disk)
        c = self.copy_ws(ws, "f2")
        write(c, "01_Creation/outputs/REPORT.md", "mine, in capitals\n")
        commit_all(c, "a case twin")
        keep = backups_of(c)
        pre = snapshot(c, keep)
        code, out = self.upgrade(TARGET, c)
        check("%s: case twin refused, nothing changed" % name,
              code == 5 and "REPORT.md" in out and not differences(pre, snapshot(c, keep)))
        shutil.rmtree(c)
        # F3 a hard kill at every point, then exact recovery and a clean upgrade
        c = self.copy_ws(ws, "f3")
        keep = backups_of(c)
        pre = snapshot(c, keep)
        bad = []
        for point in KILL_POINTS:
            code, out = self.upgrade(TARGET, c, env={"AIOS_FAULT": "crash:" + point})
            if code != 137:
                bad.append("%s: exit %s" % (point, code))
                continue
            code, out = self.aios(TARGET, "rollback", "--target", c)
            d = differences(pre, snapshot(c, keep))
            if code != 0 or "recovered an interrupted upgrade" not in out or d:
                bad.append("%s: %s" % (point, d[:3] or out[-200:]))
        check("%s: hard kill at %d points, each recovered to the exact snapshot" % (name, len(KILL_POINTS)),
              not bad, "; ".join(bad))
        code, out = self.upgrade(TARGET, c)
        check("%s: after the kills, a fresh upgrade succeeds" % name, code == 0, "" if code == 0 else out[-300:])
        # F4 a hard kill during the ROLLBACK itself; the next rollback finishes it exactly
        bad = []
        for point in ROLLBACK_KILL_POINTS:
            code, out = self.aios(TARGET, "rollback", "--target", c, env={"AIOS_FAULT": "crash:" + point})
            if code != 137:
                bad.append("%s: exit %s" % (point, code))
                continue
            code, out = self.aios(TARGET, "rollback", "--target", c)
            d = differences(pre, snapshot(c, keep))
            if code != 0 or "finished an interrupted rollback" not in out or d:
                bad.append("%s: %s" % (point, d[:3] or out[-200:]))
            self.upgrade(TARGET, c)
        check("%s: hard kill during rollback at %d points, each finished to the exact snapshot"
              % (name, len(ROLLBACK_KILL_POINTS)), not bad, "; ".join(bad))
        shutil.rmtree(c)

    # ── the heavy workspace: big files, many ignored files, real SIGKILLs ──

    def heavy(self):
        say("\n### HEAVY workspace (2.9.0 upgraded to 2.10.0): a 120 MB file, 6,000 ignored dependency "
            "files, real SIGKILLs")
        ws = self.new_ws("heavy")
        self.install("2.9.0", ws)
        self.upgrade("2.10.0", ws)
        commit_all(ws, "upgrade to 2.10.0")
        client_content(ws)
        os.makedirs(os.path.join(ws, "05_Assets/video"), exist_ok=True)
        with open(os.path.join(ws, "05_Assets/video/launch_cut.mov"), "wb") as fh:
            fh.write(os.urandom(1 << 20) * 120)
        nm = os.path.join(ws, "11_Projects/q4_launch/node_modules")
        for i in range(6000):
            write(nm, "pkg%03d/file%02d.js" % (i // 60, i % 60), "module.exports = %d;\n" % i)
        commit_all(ws, "heavy")
        keep = backups_of(ws)
        pre = snapshot(ws, keep)
        say("  pre-upgrade snapshot: %d entries" % len(pre))
        for delay in (0.05, 0.3, 0.8, 1.5, 3.0):
            p = subprocess.Popen([sys.executable, self.tool(TARGET), "upgrade", "--release", self.candidate,
                                  "--target", ws, "--repo", self.starter, "--no-vercel"],
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            time.sleep(delay)
            if p.poll() is None:
                os.kill(p.pid, signal.SIGKILL)
                p.wait()
                state = "killed"
            else:
                state = "finished first (exit %s)" % p.returncode
            journal = os.path.exists(os.path.join(ws, ".aios/txn.json"))
            lock = os.path.exists(os.path.join(ws, ".aios/lock"))
            if not journal and not lock and not state.startswith("finished"):
                # Killed before it even took the lock: there is nothing to recover, and the
                # documented next step is simply to run the upgrade again. Prove nothing changed.
                d = differences(pre, snapshot(ws, keep))
                check("heavy: SIGKILL after %.2fs (before the lock was taken): nothing changed" % delay,
                      not d, "; ".join(d[:4]))
                continue
            code, out = self.aios(TARGET, "rollback", "--target", ws)
            d = differences(pre, snapshot(ws, keep))
            version = json.load(open(os.path.join(ws, ".aios/install.json")))["release"]["version"]
            # No journal: the kill came while planning, so nothing changed and rollback must not undo
            # the earlier 2.9.0 -> 2.10.0 upgrade. With a journal: recovered to the exact snapshot.
            expect = "rolled nothing back" if not journal else "recovered an interrupted upgrade"
            if state.startswith("finished"):
                expect = "rolled back to 2.10.0"  # the upgrade beat the kill: a normal rollback
            check("heavy: SIGKILL after %.2fs (%s, journal %s): rollback %s, still 2.10.0, exact snapshot" % (
                delay, state, "on disk" if journal else "not yet written",
                "touches nothing" if not journal else "recovers"),
                code == 0 and expect in out and version == "2.10.0" and not d,
                "; ".join(d[:4]) or (out.strip().splitlines()[-1] if out.strip() else ""))
        t0 = time.time()
        code, out = self.upgrade(TARGET, ws)
        took = time.time() - t0
        check("heavy: full upgrade (%.1fs)" % took, code == 0, "" if code == 0 else out[-300:])
        rec = json.load(open(os.path.join(ws, ".aios/install.json")))
        post = snapshot(ws, keep)
        big = post.get("01_Creation/asset_library/video/launch_cut.mov")
        check("heavy: the 120 MB file kept its bytes at its new path",
              big is not None and big == pre.get("05_Assets/video/launch_cut.mov"))
        moved_nm = sum(1 for k in post if k.startswith("02_Team_Ops/projects/q4_launch/node_modules/") and not k.endswith("/"))
        check("heavy: all 6,000 ignored dependency files moved (%d)" % moved_nm, moved_nm == 6000)
        code, out = self.aios(TARGET, "rollback", "--target", ws)
        d = differences(pre, snapshot(ws, keep))
        check("heavy: rollback exact", code == 0 and not d, "; ".join(d[:4]))

    # ── a case-sensitive disk: twins that can only exist there ──

    def case_sensitive(self):
        say("\n### CASE-SENSITIVE disk image (APFS, case-sensitive)")
        img = os.path.join(self.R, "cs.dmg")
        mnt = os.path.join(self.R, "cs")
        code, out = sh(["hdiutil", "create", "-size", "200m", "-fs", "Case-sensitive APFS", "-volname",
                        "aios-cs", "-type", "UDIF", img])
        if code:
            check("case-sensitive image created", False, out[-200:])
            return
        os.makedirs(mnt)
        code, out = sh(["hdiutil", "attach", "-nobrowse", "-mountpoint", mnt, img])
        try:
            if not check("case-sensitive image mounted", code == 0, out[-200:] if code else ""):
                return
            ws = os.path.join(mnt, "ws")
            sh(["git", "init", "-q", "--bare", ws + ".git"])
            sh(["git", "clone", "-q", ws + ".git", ws])
            git(ws, "checkout", "-q", "-b", "main")
            self.install("2.10.0", ws)
            client_content(ws)
            write(ws, "02_Deliverables/Plan.md", "capital P\n")
            write(ws, "02_Deliverables/plan.md", "lower-case p\n")
            both = os.path.isfile(os.path.join(ws, "02_Deliverables/Plan.md")) and \
                open(os.path.join(ws, "02_Deliverables/plan.md")).read() == "lower-case p\n" and \
                open(os.path.join(ws, "02_Deliverables/Plan.md")).read() == "capital P\n"
            check("case-sensitive: Plan.md and plan.md exist side by side", both)
            nfc, nfd = unicodedata.normalize("NFC", "café.md"), unicodedata.normalize("NFD", "café.md")
            write(ws, "02_Deliverables/" + nfc, "composed\n")
            write(ws, "02_Deliverables/" + nfd, "decomposed\n")
            names = [n for n in os.listdir(os.path.join(ws, "02_Deliverables")) if nfc_fold(n) == nfc_fold(nfc)]
            say("  this disk keeps %d of the two Unicode spellings of café.md as separate files" % len(names))
            commit_all(ws, "twins")
            keep = backups_of(ws)
            pre = snapshot(ws, keep)
            code, out = self.upgrade(TARGET, ws)
            check("case-sensitive: twins refused (they'd be one file on a Mac or Windows disk), nothing changed",
                  code == 5 and "would both become" in out and not differences(pre, snapshot(ws, keep)),
                  out.strip().splitlines()[0] if out.strip() else "")
            os.remove(os.path.join(ws, "02_Deliverables/plan.md"))
            for n in names[1:]:
                os.remove(os.path.join(ws, "02_Deliverables", n))
            commit_all(ws, "renamed the twins away")
            keep = backups_of(ws)
            pre = snapshot(ws, keep)
            code, out = self.upgrade(TARGET, ws)
            check("case-sensitive: upgrade once the twins are gone", code == 0, "" if code == 0 else out[-300:])
            code, out = self.aios(TARGET, "rollback", "--target", ws)
            d = differences(pre, snapshot(ws, keep))
            check("case-sensitive: rollback exact", code == 0 and not d, "; ".join(d[:4]))
        finally:
            sh(["hdiutil", "detach", mnt, "-force"])

    # ── refusals that need no copy ──

    def edited_managed(self):
        say("\n### EDITED MANAGED FILE (2.10.0): refused, never overwritten")
        ws = self.new_ws("edited-managed")
        self.install("2.10.0", ws)
        client_content(ws)
        with open(os.path.join(ws, "START_HERE.md"), "a") as fh:
            fh.write("\nmy edit to a release file\n")
        commit_all(ws, "edited a managed file")
        keep = backups_of(ws)
        pre = snapshot(ws, keep)
        code, out = self.upgrade(TARGET, ws)
        check("edited managed file: refused (exit 6), the edit kept, nothing changed",
              code == 6 and not differences(pre, snapshot(ws, keep)))

    def founder_lane(self, ws):
        say("\n### FOUNDER LANE after the move")
        self.upgrade(TARGET, ws)
        bin2 = os.path.join(self.R, "bin-operator")
        write(bin2, "gh", '#!/bin/sh\n[ "$1" = api ] && [ "$2" = user ] && { echo rehearsal-operator; exit 0; }; exit 1\n', 0o755)
        payload = json.dumps({"tool_name": "Edit", "cwd": ws,
                              "tool_input": {"file_path": os.path.join(ws, "00_AIOS/company/offer_economics/pricing.md")}})
        p = subprocess.run([sys.executable, os.path.join(ws, "scripts/aios/aios.py"), "hook", "pre-edit"],
                           input=payload.encode(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=ws,
                           env=dict(os.environ, PATH=bin2 + os.pathsep + os.environ["PATH"]))
        out = p.stdout.decode()
        check("founder lane: an operator's edit at the new offer_economics path is held",
              '"deny"' in out or "founder" in out.lower(), out.strip()[:200])
        code, out = sh([sys.executable, os.path.join(ws, "scripts/aios/aios.py"), "instance", "check",
                        "--target", ws, "--offline"])
        check("founder review: instance check fails visibly while CODEOWNERS names the old path",
              code != 0 and "FOUNDER REVIEW IS NOT IN FORCE" in out)
        code, out = sh([sys.executable, os.path.join(ws, "scripts/aios/aios.py"), "start", "--target", ws])
        check("founder review: start says NOT RESTORED", "founder review: NOT RESTORED" in out)

    def from_300(self):
        """A 3.0.0 workspace: no folder is left to move, so 3.1.0 is an ordinary upgrade."""
        v, name = "3.0.0", "from-3.0.0"
        say("\n### P %s: 3.0.0 -> %s (an ordinary upgrade: nothing left to move)" % (name, TARGET))
        ws = self.new_ws(name)
        code, out = self.install(v, ws)
        check("%s: install 3.0.0 with its own installer" % name, code == 0, out[-300:] if code else "")
        write(ws, "00_AIOS/company/offer_economics/pricing.md", "# my price\n$9\n")
        write(ws, "01_Creation/outputs/my_ad.md", "my ad\n")
        with open(os.path.join(ws, "CLAUDE.md"), "a") as fh:
            fh.write("\nMY HOUSE RULE: invoices on Fridays.\n")
        commit_all(ws, "my work in the 3.0 folders")
        keep = backups_of(ws)
        before = snapshot(ws, keep)
        code, out = self.upgrade(TARGET, ws, dry=True)
        check("%s: the dry run changes nothing (exit %d)" % (name, code), code == 0 and snapshot(ws, keep) == before)
        code, out = self.upgrade(TARGET, ws)
        check("%s: upgrade to %s" % (name, TARGET), code == 0, "" if code == 0 else out[-600:])
        code, out = self.aios(TARGET, "verify", "--target", ws, "--repo", self.starter)
        check("%s: verify against the pin" % name, code == 0, "" if code == 0 else out[-300:])
        after = snapshot(ws, keep)
        mine = ["00_AIOS/company/offer_economics/pricing.md", "01_Creation/outputs/my_ad.md", "CLAUDE.md"]
        check("%s: the client's files and CLAUDE.md keep their bytes" % name,
              all(before.get(p) == after.get(p) for p in mine))
        check("%s: the map line is there once" % name,
              open(os.path.join(ws, "CLAUDE.md")).read().count("\n" + MAP_LINE + "\n") == 1)
        code, out = self.aios(TARGET, "rollback", "--target", ws)
        check("%s: rollback = the pre-upgrade snapshot, field for field" % name,
              code == 0 and snapshot(ws, keep) == before, "" if code == 0 else out[-300:])
        for point in ("upgrade.before_write", "upgrade.mid_write", "upgrade.before_record"):
            code, _out = self.upgrade(TARGET, ws, env={"AIOS_FAULT": "crash:" + point})
            code2, out2 = self.aios(TARGET, "rollback", "--target", ws)
            check("%s: hard kill at %s, then rollback = the snapshot" % (name, point),
                  code == 137 and code2 == 0 and snapshot(ws, keep) == before, "" if code2 == 0 else out2[-300:])
        code, out = self.upgrade(TARGET, ws)
        check("%s: upgrade again after the kills" % name, code == 0, "" if code == 0 else out[-300:])

    def run(self):
        t0 = time.time()
        self.setup()
        self.from_300()
        for v in VERSIONS:
            self.history("from-" + v, [v])
        self.history("chain-2.6.0-2.8.0-2.10.0", ["2.6.0", "2.8.0", "2.10.0"])
        self.history("chain-2.7.0-2.9.0", ["2.7.0", "2.9.0"])
        last = self.history("adopted-2.7.2", ["2.7.2"], adopt=True)
        self.edited_managed()
        self.founder_lane(last)
        if not self.quick:
            self.heavy()
            self.case_sensitive()
        passed = sum(1 for _n, ok in RESULTS if ok)
        say("\n" + "-" * 60)
        say("RESULT: %d passed, %d failed (%.0fs)" % (passed, len(RESULTS) - passed, time.time() - t0))
        return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--source", default="https://github.com/funnel-futurist/ff-aios-starter.git")
    ap.add_argument("--branch", default="exec/lane01-starter-3.1.0-20261015")
    ap.add_argument("--quick", action="store_true", help="skip the failure copies, the heavy run and the disk image")
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    # Never deletes anything it didn't make: the root must be new or empty (independent review).
    if os.path.lexists(root) and (not os.path.isdir(root) or os.path.islink(root) or os.listdir(root)):
        sys.exit("refusing: %s exists and isn't an empty folder; name a new scratch folder" % root)
    os.makedirs(root, exist_ok=True)
    sys.exit(Rehearsal(a.root, a.source, a.branch, a.quick).run())
