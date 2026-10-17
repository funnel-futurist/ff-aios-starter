#!/usr/bin/env python3
"""aios - the install contract for an AIOS workspace.

    release build     cut a DRAFT release manifest from a pinned commit
    release verify    is this manifest pinned, intact and approved?
    release notice    one line when a newer approved release exists (read-only, daily)
    install           install an approved release into a clean workspace
    adopt             pin an existing workspace that already matches a release
    verify            readback: does the workspace still match its release?
    upgrade           move to a newer approved release, preserving your work
    rollback          restore the previous release (also recovers a killed upgrade)
    start             role-scoped entry point
    sanitize          what would ship: secrets, client names, internal URLs
    adapters          which shipped files work with only one AI tool (check the manifest)
    protected         protected-text scan of the whole public tree (fingerprints, never text)
    governance        CODEOWNERS check / render
    boundary          does this pull request touch the founder lane without a founder?
    hook              Claude Code hooks (pre-edit: hold the founder lane in the session)
    workspace         Obsidian Workspace Kit: one vault over separate authorized repositories
    instance          the instance contract checks, including founder review at the new paths

Exit codes are part of the contract: 0 ok, 1 error, 2 package, 3 role, 4 credential,
5 state, 6 verify, 7 sanitize, 8 governance.

Python 3.9+, standard library only.
"""

import argparse
import json
import os
import shutil
import sys

# No bytecode cache beside the package, before any of it is imported. Run from a Starter clone or a workspace, Python
# would otherwise write scripts/aios/aioslib/__pycache__ into that repository, a write the installer never makes on
# purpose. macOS's own python3 never writes one; a Linux runner's Python did (GitHub's runs of 3.1, rounds 62 to 68).
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from aioslib import governance, install as install_mod, orgconfig, release as release_mod  # noqa: E402
from aioslib import adapters, boundary, notice, protected, roles, sanitize, util, workspace  # noqa: E402
from aioslib import layout as layout_mod  # noqa: E402
from aioslib.util import (EXIT_ERROR, EXIT_GOVERNANCE, EXIT_OK, EXIT_SANITIZE, Refusal)  # noqa: E402


def _repo_root():
    return os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))


def _say(msg=""):
    sys.stdout.write(str(msg) + "\n")


def _report_refusal(exc):
    sys.stderr.write("REFUSED: %s\n" % exc.message)
    for detail in exc.details:
        sys.stderr.write("  - %s\n" % detail)
    return exc.code


def _aios_lookup_from(path):
    """Look up an AIOS release record (P01's catalogue) so `consumes` can be checked."""
    if not path:
        return None

    def lookup(release_id):
        candidate = path
        if os.path.isdir(path):
            candidate = os.path.join(path, "%s.json" % release_id)
        if not os.path.isfile(candidate):
            return None
        data = util.read_json(candidate)
        if data.get("release_id") != release_id:
            return None
        return data

    return lookup


# ─── commands ───────────────────────────────────────────────────────────────

def cmd_release_build(args):
    repo = os.path.abspath(args.repo)
    rev = util.git(repo, ["rev-parse", args.rev])
    credentials = util.read_json(args.credentials) if args.credentials else None
    manifest = release_mod.build(
        repo, rev, args.version,
        branch=args.branch or util.git(repo, ["rev-parse", "--abbrev-ref", "HEAD"]),
        credentials=credentials,
        min_upgrade_from=args.min_upgrade_from,
        aios_release=args.aios_release,
    )
    out = args.out or os.path.join(repo, "releases", "%s.json" % manifest["release_id"])
    util.write_json(out, manifest)
    _say("wrote %s" % out)
    _say("  status:   %s (a human approves it; this command cannot)" % manifest["status"])
    _say("  pinned:   %s" % manifest["created_from"]["git_rev"])
    _say("  files:    %(files)d (%(managed)d managed, %(seed)d seed), %(skills)d skills"
         % manifest["counts"])
    return EXIT_OK


def cmd_release_verify(args):
    manifest = util.read_json(args.manifest)
    repo = os.path.abspath(args.repo)
    problems = release_mod.consumable(manifest, repo, _aios_lookup_from(args.aios_releases))
    _say("release:  %s" % manifest.get("release_id"))
    _say("status:   %s" % manifest.get("status"))
    _say("pinned:   %s" % (manifest.get("created_from") or {}).get("git_rev"))
    if problems:
        _say("verdict:  NOT INSTALLABLE")
        for p in problems:
            _say("  - %s" % p)
        return util.EXIT_PACKAGE
    _say("verdict:  installable (pinned, intact, approved)")
    return EXIT_OK


def cmd_release_check_tag(args):
    repo = os.path.abspath(args.repo)
    problems = release_mod.check_tag(repo, args.tag, args.release_id)
    _say("tag:      %s" % args.tag)
    _say("release:  %s" % args.release_id)
    if problems:
        _say("verdict:  a checkout of this tag is NOT the approved release")
        for p in problems:
            _say("  - %s" % p)
        return util.EXIT_PACKAGE
    _say("verdict:  the tag carries the approval and installs the pinned files byte for byte")
    return EXIT_OK


def cmd_install(args):
    repo = os.path.abspath(args.repo)
    manifest = util.read_json(args.release)
    config = util.read_json(args.config)
    target = os.path.abspath(args.target)
    if not os.path.isdir(target):
        os.makedirs(target)

    # Role gate: installing is a founder action, and the policy that says so travels with
    # the package, so read it from the pinned tree rather than from the target (which is
    # empty) or the source working copy (which is mutable).
    policy = None
    for path, _mode, data in util.read_tree(repo, manifest["created_from"]["git_rev"]):
        if path == roles.POLICY_PATH.replace(os.sep, "/"):
            policy = json.loads(data.decode("utf-8"))
            break
    if policy is None:
        raise Refusal(util.EXIT_ROLE, "the release ships no %s, so no role can be checked"
                      % roles.POLICY_PATH)
    login, role = roles.require_lifecycle(policy, config, "install")

    record, creds = install_mod.install(target, manifest, repo, config,
                                        _aios_lookup_from(args.aios_releases))
    _say("installed %s into %s" % (record["release"]["release_id"], target))
    _say("  by:       %s (%s)" % (login, role))
    _say("  pinned:   %s" % record["release"]["git_rev"])
    _say("  managed:  %d files, verified by readback" % len(record["managed"]))
    _say("  seeded:   %d files (yours from now on)" % len(record["seeded"]))
    for c in creds:
        _say("  cred:     %s -> %s [%s]"
             % (c["name"], c["ref"] or "(no reference)",
                "resolved" if c["resolved"] else
                ("MISSING (required)" if c["required"] else "not configured (optional)")))
    return EXIT_OK


def cmd_adopt(args):
    repo = os.path.abspath(args.repo)
    manifest = util.read_json(args.release)
    config = util.read_json(args.config)
    target = os.path.abspath(args.target)

    # `adopt` is listed as a founder lifecycle action, and the CLI simply did not check -
    # both review families found it. For a plain adopt the policy travels in the release, because
    # an unpinned workspace's own copy is the thing being adopted. An existing instance keeps its
    # own policy, which must be committed before anything is written: that one decides who may
    # adopt into it (independent review, 3.1 round 16).
    policy = None
    if args.existing:
        policy = roles.load_policy(target)
    else:
        for path, _mode, data in util.read_tree(repo, manifest["created_from"]["git_rev"]):
            if path == roles.POLICY_PATH.replace(os.sep, "/"):
                policy = json.loads(data.decode("utf-8"))
                break
    if policy is None:
        raise Refusal(util.EXIT_ROLE, "the release ships no %s, so no role can be checked"
                      % roles.POLICY_PATH)
    login, role = roles.require_lifecycle(policy, config, "adopt")

    if args.plan and not args.existing:
        raise Refusal(util.EXIT_STATE, "--plan is for --existing: a plain adopt pins a workspace that "
                                       "already matches the release byte for byte")
    if args.existing:
        plan_rel = None
        if args.plan:
            plan_rel = os.path.relpath(os.path.abspath(args.plan), target)
            if plan_rel == ".." or plan_rel.startswith(".." + os.sep):
                raise Refusal(util.EXIT_STATE, "the adoption plan must be inside the instance it adopts "
                                               "into: %s" % args.plan)
        record = install_mod.adopt_existing(target, manifest, repo, config, plan_rel,
                                            _aios_lookup_from(args.aios_releases))
        info = record["adoption"]
        _say("adopted %s into the existing instance %s" % (record["release"]["release_id"], target))
        _say("  by:       %s (%s)" % (login, role))
        _say("  plan:     %s (sha256 %s)" % (info["plan"], info["plan_sha256"][:12]))
        made = [c for c in info["created"] if c["path"] != ".aios/config.json"]
        _say("  created:  %d file(s), verified by readback%s; nothing of the instance's was written"
             % (len(made), ", and the org config" if len(made) < len(info["created"]) else ""))
        _say("  kept:     every path the plan says is the instance's; no folder move, no seed line")
        _say("  next:     commit the change (git add -A, then git commit); `aios rollback` undoes it")
        return EXIT_OK
    record = install_mod.adopt(target, manifest, repo, config,
                               _aios_lookup_from(args.aios_releases))
    _say("pinned %s to %s (%d managed files matched byte for byte)"
         % (target, record["release"]["release_id"], len(record["managed"])))
    _say("  by:       %s (%s)" % (login, role))
    return EXIT_OK


def cmd_verify(args):
    target = os.path.abspath(args.target)
    journal = install_mod.load_journal(target)
    if journal:
        _say("PARTIAL: an interrupted %s from %s to %s is on disk"
             % (journal.get("op"), journal.get("from_version"), journal.get("to_version")))
        _say("run `aios rollback` to restore the previous release")
        return util.EXIT_STATE
    record = install_mod.load_record(target)
    source = os.path.abspath(args.repo) if args.repo else None
    problems, summary = install_mod.verify(target, record, source)
    _say("workspace: %s" % target)
    _say("release:   %s (%s)" % (summary["release_id"], summary["version"]))
    _say("checked:   %s" % ("workspace files AND the install record, against the pinned "
                            "release in %s" % source if source else
                            "workspace files against the install record "
                            "(pass --repo to also check the record against the pinned release)"))
    if source:
        _say("pin:       %s" % ("confirmed by " + summary["pin_confirmed_by"] if summary.get("pin_confirmed_by")
                                else "not confirmed: the source has no record of this release"))
    _say("managed:   %d/%d files re-hashed from disk"
         % (summary["managed_checked"], summary["managed_total"]))
    for e in record.get("seed_lines") or []:
        # Read only inside the workspace: the record is committed, so a pull request could point an
        # entry anywhere; verify reports such a path above (independent review, 3.1 round 44).
        # Only a regular file, reached with no link on the way, really inside the workspace (round 45).
        safe = util.safe_relpath(e["path"]) and not install_mod._linked_paths(target, [e["path"]])
        full = install_mod._seed_line_target(target, e["path"]) if safe else None
        if not safe or (full is None and os.path.lexists(os.path.join(target, e["path"]))):
            _say("  line:    %r not read: the path leaves the workspace or runs through a link" % e["path"])
            continue
        here = False
        if full:
            with open(full, encoding="utf-8", errors="replace") as fh:
                here = any(line.strip() == e["line"] for line in fh)
        _say("  line:    %s %s `%s` (yours to keep or remove)"
             % (e["path"], "has" if here else "no longer has", e["line"]))
    config = None
    try:
        config = orgconfig.load(target)
    except Refusal:
        pass
    if config:
        rows = orgconfig.resolve(
            [{"name": c["name"], "required": c["required"]} for c in record.get("credentials") or []],
            config, target)
        for r in rows:
            _say("  cred:    %s -> %s [%s]"
                 % (r["name"], r["ref"] or "(no reference)",
                    "resolved" if r["resolved"] else
                    ("MISSING (required)" if r["required"] else "not configured (optional)")))
    if problems:
        _say("verdict:   DRIFTED")
        for p in problems:
            _say("  - %s" % p)
        return util.EXIT_VERIFY
    _say("verdict:   matches the installed release")
    return EXIT_OK


def cmd_upgrade(args):
    repo = os.path.abspath(args.repo)
    manifest = util.read_json(args.release)
    target = os.path.abspath(args.target)
    config = orgconfig.load(target)
    policy = roles.load_policy(target)
    login, role = roles.require_lifecycle(policy, config, "upgrade")
    if args.dry_run:
        # The same checks and refusals as a real upgrade; nothing is written, not even a lock.
        plan = install_mod.upgrade_plan(target, manifest, repo, _aios_lookup_from(args.aios_releases),
                                        no_vercel=args.no_vercel)
        _say("dry run: %s %s -> %s, nothing written" % (target, plan["from"], plan["to"]))
        _say("  by:        %s (%s)" % (login, role))
        for label in ("changed", "added", "removed"):
            for path in plan[label]:
                _say("  %-10s %s" % (label + ":", path))
        _say("  unchanged: %d managed files" % plan["unchanged"])
        if plan["new_seeds"]:
            _say("  new seeds: %d, written once and yours afterwards: %s"
                 % (len(plan["new_seeds"]), ", ".join(plan["new_seeds"])))
        for sl in plan["seed_lines"]:
            _say("  one line:  %s gains `%s` (added once; rollback takes it back)" % (sl["path"], sl["line"]))
        lay = plan.get("layout")
        if lay:
            _say("  layout:    %s -> %s: %d file(s) move to new folders, bytes unchanged; %d empty "
                 "folder(s) recreated; %d junk file(s) set aside in the backup"
                 % (lay["from"], lay["to"], len(lay["moves"]), len(lay["empty_folders"]),
                    len(lay["set_aside"])))
            for src, dst in lay["moves"]:
                _say("  move:      %s -> %s" % (src, dst))
            for src in lay["set_aside"]:
                _say("  set aside: %s" % src)
            for row in lay["sites"]:
                _say("  website:   %s" % row)
            for line in lay["founder_review"]:
                _say("  after:     %s" % line)
            if lay["blocked"]:
                _say("  BLOCKED: the upgrade will refuse until this is done:")
                for b in lay["blocked"]:
                    _say("    - %s" % b)
                return util.EXIT_STATE
        _say("  run it again without --dry-run to upgrade")
        return EXIT_OK
    before = install_mod.load_record(target)
    record = install_mod.upgrade(target, manifest, repo, _aios_lookup_from(args.aios_releases),
                                 no_vercel=args.no_vercel)
    _say("upgraded %s: %s -> %s"
         % (target, before["release"]["version"], record["release"]["version"]))
    _say("  by:       %s (%s)" % (login, role))
    _say("  managed:  %d files, verified by readback" % len(record["managed"]))
    added = [e for e in record.get("seed_lines") or []
             if e.get("state") == "added" and e.get("release") == record["release"]["version"]]
    migration = record.get("layout_migration")
    if migration:
        _say("  layout:   %s -> %s: %d file(s) moved to new folders, every one re-hashed: bytes unchanged"
             % (migration["from"], migration["to"], migration["moved"]))
        _say("            proof: %s" % migration["proof"])
        if migration.get("set_aside"):
            _say("            %d junk file(s) (.DS_Store and the like) set aside in the backup"
                 % migration["set_aside"])
        for row in migration.get("sites") or []:
            _say("  website:  %s" % row)
        stale = migration.get("stale_references") or []
        if stale:
            _say("  check:    %d of your own file(s) still name an old folder. They were not edited; "
                 "update the paths when you're ready:" % len(stale))
            for p in stale[:15]:
                _say("              %s" % p)
    if added:
        _say("  state:    untouched, except %s: %s"
             % ("one declared line" if len(added) == 1 else "%d declared lines" % len(added),
                "; ".join("%s gained `%s`" % (e["path"], e["line"]) for e in added)))
    else:
        _say("  state:    untouched (seed and unmanaged files were not written)")
    if migration:
        for line in install_mod.founder_review_notice(target, (manifest.get("layout") or {})
                                                      .get("retired_roots") or []):
            _say("  NEXT:     %s" % line)
        _say("  next:     commit the change (git add -A, then git commit): git shows it as renames")
    for line in install_mod.ownership_review_notice(target, record):
        _say("  NEXT:     %s" % line)
    _say("  rollback: available (%s)" % record["previous"]["backup"])
    return EXIT_OK


def cmd_rollback(args):
    target = os.path.abspath(args.target)
    # By the paths, never by what a file there says: a journal that isn't one refuses below (3.1 round 27).
    nothing_changed = (not os.path.lexists(install_mod.journal_path(target))
                       and not os.path.lexists(install_mod.install_record_path(target)))
    if nothing_changed and install_mod.clear_dead_lock(target):
        # Nothing was ever changed here, only a dead holder's lock left by an adoption killed before its
        # journal. Clearing that needs no role, whatever the people map or policy say; a live holder's
        # lock is never taken (independent review, 3.1 round 10).
        _say("nothing to roll back: this workspace has no install record and no journal; "
             "cleared a dead operation's lock")
        _say("  release:  none (nothing was changed)")
        return EXIT_OK
    try:
        config = orgconfig.load(target)
    except Refusal:
        # An adoption killed before its org config landed, or an undo that already removed it: the
        # journal holds the people map, so the operator is still checked against it (3.1).
        journal = install_mod.load_journal(target) or {}
        if journal.get("op") in ("adopt-existing", "adopt-undo") and journal.get("config"):
            config = journal["config"]
        elif nothing_changed:
            _say("nothing to roll back: this workspace has no install record and no journal")
            return EXIT_OK
        else:
            raise
    policy = roles.load_policy(target)
    login, role = roles.require_lifecycle(policy, config, "rollback")
    record, summary, how = install_mod.rollback(target, os.path.abspath(args.repo) if args.repo else None)
    _say("%s" % how)
    _say("  by:       %s (%s)" % (login, role))
    if summary["release_id"] is None:
        if summary.get("record_left"):
            _say("  release:  .aios/install.json was left because it changed: check it, then delete it to "
                 "finish unpinning")
        else:
            _say("  release:  none (%s)" % ("nothing was changed" if summary.get("unchanged") else
                                            "the adoption is undone; this is the instance it was before"))
        return EXIT_OK
    _say("  release:  %s (%s)" % (summary["release_id"], summary["version"]))
    _say("  managed:  %d/%d files re-hashed from disk"
         % (summary["managed_checked"], summary["managed_total"]))
    return EXIT_OK


def cmd_start(args):
    target = os.path.abspath(args.target)
    policy = roles.load_policy(target)
    config = orgconfig.load(target)
    login, source = roles.identity()
    if not login:
        raise Refusal(util.EXIT_ROLE, "cannot establish who you are (%s)" % source,
                      roles.identity_help(source))
    role = roles.role_for(config, login)
    if role is None:
        raise Refusal(util.EXIT_ROLE,
                      "%s is not in this workspace's people map, so has no role" % login,
                      ["a founder adds you to .aios/config.json"])
    entry = roles.resolve_entry(policy, role, args.entry)
    spec = (policy.get("entries") or {}).get(entry) or {}

    _say("you:       %s (%s)" % (login, source))
    _say("role:      %s" % role)
    _say("entry:     %s - %s" % (entry, spec.get("summary", "")))
    try:
        record = install_mod.load_record(target)
        problems, summary = install_mod.verify(target, record)
        _say("release:   %s (%s)%s"
             % (summary["release_id"], summary["version"], "" if not problems else "  DRIFTED"))
        for p in problems[:5]:
            _say("  - %s" % p)
        # Every workspace, as `aios instance check` does: the record's layout field is the workspace's
        # to edit, and a 3.0 copy pinned with `adopt` has none (independent review, 3.1 round 50).
        fails = [d for st, d in governance.founder_review_local(
            target, policy, config, layout_mod.OLD_FOLDERS, install_mod.ownership_paths(record)) if st == "FAIL"]
        _say("founder review: %s" % ("CODEOWNERS covers the founder lane (run `aios instance check` "
                                     "to confirm GitHub enforces it)" if not fails else
                                     "NOT RESTORED at the founder-lane paths - `aios instance check` "
                                     "fails until it is (docs/human_steps/restore_founder_review.md)"))
        for d in fails[:5]:
            _say("  - %s" % d)
    except Refusal:
        _say("release:   UNPINNED - this workspace was not installed from an approved release")
        _say("           (a workspace made with \"Use this template\" copies mutable main;")
        _say("            run `aios adopt` to pin it, per founder ruling D3)")
    _say("")
    _say("your moves:")
    for item in spec.get("skills") or []:
        _say("  /%s" % item)
    if spec.get("actions"):
        _say("founder actions: %s" % ", ".join(spec["actions"]))
    denied = roles.denied_paths(policy, role)
    if denied:
        _say("")
        _say("founder lane (ask a founder first): %s" % ", ".join(denied))
        _say("  held two ways: Claude will not edit these for you, and a pull request that")
        _say("  changes them fails its boundary check until %s approves that commit."
             % boundary.lane_approver(policy))
        _say("  a direct push to main is stopped only if branch protection is on.")
    for warning in _hook_runtime_warnings(target):
        _say("")
        _say("warning:   %s" % warning)
    try:
        newer = notice.check(target)
    except Exception:  # noqa: BLE001 - a notice must never break a session start (3.1 round 56)
        newer = None
    if newer:
        _say("")
        _say("update:    %s" % newer)
    return EXIT_OK


def cmd_instance_check(args):
    """Read-only. Exit 0 only when every control passes, founder review included (R-C)."""
    target = os.path.abspath(args.target)
    results = list(layout_mod.instance_checks(target))
    policy, config = None, None
    try:
        policy = roles.load_policy(target)
        config = orgconfig.load(target)
    except Refusal as exc:
        results.append(("founder", "FAIL", "can't read the role policy or people map (%s)" % exc.message))
    slug = args.repo_slug or governance.target_repo_slug(target)  # one identity for every check
    for problem in governance.check(target, slug, config):
        results.append(("B4", "FAIL", problem))  # placeholders, binding, owner syntax
    if policy is not None and config is not None:
        # The ownership list is the record's (and an adoption's plan): none without a record (C3).
        try:
            ownership = install_mod.ownership_paths(install_mod.load_record(target))
        except Refusal:
            ownership = []
        for status, detail in governance.founder_review_local(target, policy, config,
                                                              layout_mod.OLD_FOLDERS, ownership):
            results.append(("founder", status, detail))
        if args.offline:
            results.append(("founder", "FAIL", "GitHub enforcement not checked (--offline), so founder "
                                               "review is unverified"))
        else:
            rel, path = governance.find_file(target)
            local_text = open(path, encoding="utf-8", errors="replace").read() if path else None
            # Whoever may approve the founder lane: the founders, or the accounts the role policy
            # declares as founder-lane reviewers (review permission, not founder status; G98).
            founders, declared = governance.lane_reviewers(policy, config)
            for status, detail in governance.founder_review_remote(
                    slug, policy, sorted(founders), local_text,
                    governance.REVIEWERS_NOUN if declared else "founders"):
                results.append(("founder", status, detail))
            for status, detail in governance.founder_review_enforced(
                    slug, sorted(founders), "founder-lane" if declared else "founder"):
                results.append(("founder", status, detail))
    for control, status, detail in results:
        _say("  %-5s %-9s %s" % (status, control, detail))
    failed = [r for r in results if r[1] == "FAIL"]
    founder_failed = [r for r in failed if r[0] == "founder"]
    if founder_failed:
        _say("")
        _say("FOUNDER REVIEW IS NOT IN FORCE at this workspace's founder-lane paths.")
        _say("  restore it: docs/human_steps/restore_founder_review.md")
    _say("verdict:  %s" % ("meets the instance contract's checks" if not failed
                          else "%d check(s) failed" % len(failed)))
    return util.EXIT_VERIFY if failed else EXIT_OK


def cmd_release_notice(args):
    """One line when a newer approved release exists, else nothing. Always exit 0: it informs, never blocks."""
    try:
        line = notice.check(os.path.abspath(args.target))
    except Exception:  # noqa: BLE001 - a notice must never break a session start
        line = None
    if line:
        _say(line)
    return EXIT_OK


def _hook_runtime_warnings(target):
    """A Claude Code hook whose program is missing fails without blocking anything, so a safety
    hook that cannot start is a silent gap. Name it where people look first."""
    settings = os.path.join(target, ".claude", "settings.json")
    try:
        hooks = util.read_json(settings).get("hooks") or {}
    except (OSError, ValueError):
        return []
    needed = set()
    for entries in hooks.values():
        for entry in entries or []:
            for hook in entry.get("hooks") or []:
                program = (hook.get("command") or "").split(" ", 1)[0]
                if program in ("node", "python3"):
                    needed.add(program)
    return ["%s is not installed, so this workspace's %s safety hooks cannot run and Claude Code "
            "skips them without saying so. Install %s, then run start again"
            % (prog, prog, "Node.js from https://nodejs.org" if prog == "node" else "Python 3")
            for prog in sorted(needed) if shutil.which(prog) is None]


def cmd_sanitize(args):
    repo = os.path.abspath(args.repo)
    if args.release:
        manifest = util.read_json(args.release)
        rev = manifest["created_from"]["git_rev"]
        paths = [e["path"] for e in manifest["files"]]
    else:
        rev = util.git(repo, ["rev-parse", args.rev])
        spec = release_mod.load_spec(repo, rev)
        paths = [p for p, _c, _m, _s in release_mod.select_files(repo, rev, spec)]
    findings, scanned, ignored = sanitize.scan_release(
        repo, rev, paths, args.denylist, args.mode, args.allow_generic, args.allowlist,
        args.acknowledge_generic)
    _say("scanned %d file(s) at %s" % (scanned, rev[:12]))
    _say("denylist: %s" % (args.denylist or "(none - mode %s)" % args.mode))
    if ignored:
        _say("ignored:  %d denylist term(s) that are ordinary English words, so the scan stays "
             "readable: %s" % (len(ignored), ", ".join(sorted(ignored)[:10])))
        _say("          (pass --allow-generic to include them; a real client's name CAN be an ordinary word)")
    if findings:
        _say("findings: %d" % len(findings))
        for f in findings[:50]:
            _say("  %s:%s  %s  %s  fp=%s"
                 % (f["path"], f["line"], f["kind"], f["detail"], f["fingerprint"]))
        return EXIT_SANITIZE
    _say("findings: 0 (no credential shapes, denylisted names or internal hosts)")
    return EXIT_OK


def _allowlist_path(args, repo):
    return args.allowlist or os.path.join(repo, protected.DEFAULT_ALLOWLIST)


def cmd_protected_fingerprint(args):
    """Private side: turn protected source files into a fingerprint list. Writes no text."""
    sources = []
    for spec in args.source:
        label, sep, path = spec.partition("=")
        if not sep or not os.path.isfile(path):
            raise Refusal(EXIT_SANITIZE, "--source wants LABEL=path to an existing file, got %r" % spec)
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            sources.append((label, fh.read()))
    data = protected.build_list(sources, args.window, args.min_hits)
    util.write_json(args.out, data)
    total = sum(len(v) for v in data["sources"].values())
    _say("wrote %s: %d source(s), %d fingerprints, window %d words, min hits %d"
         % (args.out, len(data["sources"]), total, args.window, args.min_hits))
    _say("it holds fingerprints only. Keep it OUTSIDE the public repository.")
    return EXIT_OK


def cmd_protected_scan(args):
    repo = os.path.abspath(args.repo)
    fp_list = protected.load_list(args.fingerprints or os.environ.get(protected.ENV_LIST))
    allowlist = protected.load_allowlist(_allowlist_path(args, repo))
    problems = protected.check_allowlist(repo, allowlist)
    if problems:
        raise Refusal(EXIT_SANITIZE, "the public-methods allow-list is not in order", problems)
    findings, scanned, allowed = protected.scan_tree(repo, fp_list, allowlist)
    _say("scanned %d file(s) in %s against %d protected source(s)" % (scanned, repo, len(fp_list["sources"])))
    _say("allow-listed as public on purpose (%d): %s" % (len(allowed), ", ".join(allowed) or "none matched"))
    protected.require_clean(findings)
    _say("findings: 0 (no protected text outside the allow-list)")
    return EXIT_OK


def cmd_protected_check_allowlist(args):
    repo = os.path.abspath(args.repo)
    allowlist = protected.load_allowlist(_allowlist_path(args, repo))
    problems = protected.check_allowlist(repo, allowlist)
    if problems:
        raise Refusal(EXIT_SANITIZE, "the public-methods allow-list is not in order", problems)
    _say("allow-list ok: %d public method file(s), every one exists and matches its approved bytes"
         % len(allowlist.get("public_methods", [])))
    return EXIT_OK


def cmd_protected_pin(args):
    repo = os.path.abspath(args.repo)
    data = protected.pin_allowlist(repo, _allowlist_path(args, repo))
    _say("re-pinned %d entr(ies). Review the diff: each changed sha256 is a founder-approved change."
         % len(data.get("public_methods", [])))
    return EXIT_OK


def cmd_adapters_check(args):
    repo = os.path.abspath(args.repo)
    files = protected.tracked_or_walked(repo)
    found = adapters.problems(repo, files)
    manifest = adapters.load(repo)
    for name, tool in sorted(manifest["tools"].items()):
        _say("%-12s %-12s %d file(s)" % (name, tool["status"], len(tool.get("files") or [])))
    if found:
        raise Refusal(util.EXIT_PACKAGE, "the adapter manifest and the tree disagree", found)
    _say("adapter manifest ok: every tool-specific file is declared")
    return EXIT_OK


def cmd_adapters_render(args):
    repo = os.path.abspath(args.repo)
    text = adapters.render_agents_md(repo)
    with open(os.path.join(repo, adapters.AGENTS_PATH), "w", encoding="utf-8") as fh:
        fh.write(text)
    _say("wrote %s (%d bytes) from CLAUDE.md and its imports" % (adapters.AGENTS_PATH, len(text.encode("utf-8"))))
    return EXIT_OK


def cmd_governance_check(args):
    root = os.path.abspath(args.root)
    config = None
    if args.use_config:
        try:
            config = orgconfig.load(root)
        except Refusal:
            config = None
    problems = governance.check(root, args.repo_slug, config)
    rel, _path = governance.find_file(root)
    _say("CODEOWNERS: %s" % (rel or "MISSING"))
    if problems:
        _say("verdict:    NOT ENFORCING")
        for p in problems:
            _say("  - %s" % p)
        _say("")
        _say("note: a valid file is necessary but not sufficient. Enforcement also needs branch")
        _say("      protection with \"Require review from Code Owners\", which needs an admin.")
        return EXIT_GOVERNANCE
    _say("verdict:    names real owners, bound to this repository")
    _say("note:       enforcement still depends on branch protection being on.")
    return EXIT_OK


def cmd_governance_render(args):
    with open(args.template, "r", encoding="utf-8") as fh:
        template = fh.read()
    owners = {}
    for pair in args.owner or []:
        name, _, handles = pair.partition("=")
        owners[name.strip()] = [h for h in handles.split() if h]
    text = governance.render(template, args.repo_slug, owners)
    if args.out:
        util.ensure_parent(args.out)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        _say("wrote %s" % args.out)
    else:
        sys.stdout.write(text)
    return EXIT_OK


def cmd_boundary_check_pr(args):
    approvers = [a.strip() for a in (args.approved_by or "").split(",") if a.strip()]
    code, lines = boundary.check_pr(os.path.abspath(args.repo), args.base, args.head,
                                    args.author, approvers)
    for line in lines:
        _say(line)
    return code


def cmd_hook_pre_edit(args):
    # A hook that crashes must not wedge the session: Claude Code treats a non-2 exit as a
    # non-blocking error. The refusal path is a printed decision, never an exception.
    code, out = boundary.hook_pre_edit(sys.stdin.read())
    if out:
        _say(out)
    return code


def _print_workspace_report(report):
    for r in report["repos"]:
        rev = (" @ %s" % r["revision"][:12]) if r.get("revision") else ""
        extra = " (cloned)" if r.get("cloned") else (" (moved forward)" if r.get("fast_forwarded") else "")
        if r.get("moved_to"):
            extra = " (old copy moved out of the vault to %s)" % r["moved_to"]
        _say("  %-12s %-14s %s%s%s" % (r["name"], r["domain"], r["status"], rev, extra))
        if r.get("next"):
            _say("               next: %s" % r["next"])
        for w in r.get("warnings", []):
            _say("               warning: %s" % w)
    kept = [v["file"] for v in report["maps"].values() if v["kept_your_edit"]]
    _say("maps written to %s/%s" % (report["parent"], workspace.MAPS_DIR))
    if kept:
        _say("kept your edits; fresh copies written as: %s" % ", ".join(kept))
    _say("open %s in Obsidian, then START-HERE.md" % report["parent"])


def cmd_workspace_plan(args):
    manifest = util.read_json(args.manifest)
    problems = workspace.validate(manifest)
    if problems:
        raise Refusal(util.EXIT_PACKAGE, "the workspace manifest is not valid", problems)
    for row in workspace.plan(manifest, os.path.abspath(args.parent),
                              check_remote=not args.offline):
        _say("  %-12s %-10s %-12s %s" % (row["name"], row["state"], row["local"], row["action"]))
    _say("nothing was changed")
    return EXIT_OK


def cmd_workspace_init(args):
    report = workspace.init(util.read_json(args.manifest), args.parent,
                            clone_filter=args.filter)
    if report["settings_written"]:
        _say("Obsidian settings: %s" % ", ".join(report["settings_written"]))
    _print_workspace_report(report)
    return report["code"]


def cmd_workspace_sync(args):
    report = workspace.sync(args.parent, clone_filter=args.filter,
                            move_retired_copies=args.move_retired)
    _print_workspace_report(report)
    return report["code"]


def cmd_workspace_status(args):
    for row in workspace.status(os.path.abspath(args.parent)):
        rev = (" @ %s" % row["revision"][:12]) if row.get("revision") else ""
        _say("  %-12s %s%s" % (row["name"], row["status"], rev))
    return EXIT_OK


# ─── argument parsing ───────────────────────────────────────────────────────

def build_parser():
    p = argparse.ArgumentParser(prog="aios", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command")

    rel = sub.add_parser("release", help="build or verify a release manifest")
    relsub = rel.add_subparsers(dest="subcommand")

    rb = relsub.add_parser("build", help="cut a DRAFT release manifest")
    rb.add_argument("--repo", default=_repo_root())
    rb.add_argument("--rev", default="HEAD")
    rb.add_argument("--version", required=True)
    rb.add_argument("--branch")
    rb.add_argument("--credentials", help="JSON file: the credential references this release needs")
    rb.add_argument("--min-upgrade-from", dest="min_upgrade_from")
    rb.add_argument("--aios-release", dest="aios_release",
                    help="the approved AIOS release this consumes (P01)")
    rb.add_argument("--out")
    rb.set_defaults(func=cmd_release_build)

    rv = relsub.add_parser("verify", help="is this manifest pinned, intact and approved?")
    rv.add_argument("manifest")
    rv.add_argument("--repo", default=_repo_root())
    rv.add_argument("--aios-releases", dest="aios_releases")
    rv.set_defaults(func=cmd_release_verify)

    rt = relsub.add_parser("check-tag", help="does a checkout of this tag carry the approved "
                                              "release, with the pinned files byte for byte?")
    rt.add_argument("tag")
    rt.add_argument("--release-id", dest="release_id", required=True,
                    help="e.g. starter-2.7.0 (the record releases/<id>.json is read at the tag)")
    rt.add_argument("--repo", default=_repo_root())
    rt.set_defaults(func=cmd_release_check_tag)
    rn = relsub.add_parser("notice", help="one line if a newer approved release exists (read-only, "
                                          "at most one check a day, silent offline)")
    rn.add_argument("--target", default=".")
    rn.set_defaults(func=cmd_release_notice)

    ins = sub.add_parser("install", help="install an approved release into a clean workspace")
    ins.add_argument("--release", required=True)
    ins.add_argument("--target", required=True)
    ins.add_argument("--config", required=True)
    ins.add_argument("--repo", default=_repo_root())
    ins.add_argument("--aios-releases", dest="aios_releases")
    ins.set_defaults(func=cmd_install)

    ad = sub.add_parser("adopt", help="pin a workspace that already matches a release")
    ad.add_argument("--release", required=True)
    ad.add_argument("--target", required=True)
    ad.add_argument("--config", required=True)
    ad.add_argument("--repo", default=_repo_root())
    ad.add_argument("--aios-releases", dest="aios_releases")
    ad.add_argument("--existing", action="store_true",
                    help="adopt into an instance that already exists and isn't a Starter copy: create-only, "
                         "every path classified by the instance's own plan (3.1)")
    ad.add_argument("--plan", help="the instance's adoption plan, a path inside the target "
                                   "(default .aios/adoption.json); with --existing")
    ad.set_defaults(func=cmd_adopt)

    ve = sub.add_parser("verify", help="readback the workspace against its release")
    ve.add_argument("--target", default=".")
    ve.add_argument("--repo", help="also cross-check the install record against the pinned "
                                   "release in this source repo")
    ve.set_defaults(func=cmd_verify)

    up = sub.add_parser("upgrade", help="move to a newer approved release")
    up.add_argument("--release", required=True)
    up.add_argument("--target", default=".")
    up.add_argument("--repo", default=_repo_root())
    up.add_argument("--aios-releases", dest="aios_releases")
    up.add_argument("--dry-run", dest="dry_run", action="store_true",
                    help="run every check and print the managed-file changes; write nothing")
    up.add_argument("--no-vercel", dest="no_vercel", action="store_true",
                    help="3.0 folder move without a Vercel token: you state this repository isn't "
                         "deployed by Vercel (recorded; refused if Vercel's files are in the moving folders)")
    up.set_defaults(func=cmd_upgrade)

    rbk = sub.add_parser("rollback", help="restore the previous release")
    rbk.add_argument("--target", default=".")
    rbk.add_argument("--repo", help="the release's source (an ff-aios-starter clone): needed to undo a "
                                    "finished adoption, so only that release's own files are removed")
    rbk.set_defaults(func=cmd_rollback)

    st = sub.add_parser("start", help="role-scoped entry point")
    st.add_argument("--target", default=".")
    st.add_argument("--entry", help="which workspace to enter (refused if your role lacks it)")
    st.set_defaults(func=cmd_start)

    sa = sub.add_parser("sanitize", help="scan what would ship")
    sa.add_argument("--repo", default=_repo_root())
    sa.add_argument("--rev", default="HEAD")
    sa.add_argument("--release", help="scan exactly this manifest's file set")
    sa.add_argument("--denylist", help="client-name denylist, supplied at run time")
    sa.add_argument("--mode", choices=("release", "scan"), default="release")
    sa.add_argument("--allow", dest="allowlist",
                    default=os.path.join(_repo_root(), "release", "sanitize_allow.txt"),
                    help="terms that are intentional in this package (publisher branding)")
    sa.add_argument("--acknowledge-generic", dest="acknowledge_generic", action="store_true",
                    help="record that the skipped generic terms were reviewed and accepted")
    sa.add_argument("--allow-generic", dest="allow_generic", action="store_true",
                    help="also match denylist terms that are ordinary English words")
    sa.set_defaults(func=cmd_sanitize)

    ad = sub.add_parser("adapters", help="which shipped files are tool-specific")
    adsub = ad.add_subparsers(dest="subcommand")
    adc = adsub.add_parser("check", help="the manifest and the tree must agree")
    adc.add_argument("--repo", default=_repo_root())
    adc.set_defaults(func=cmd_adapters_check)
    adr = adsub.add_parser("render", help="write AGENTS.md from CLAUDE.md and the files it imports")
    adr.add_argument("--repo", default=_repo_root())
    adr.set_defaults(func=cmd_adapters_render)

    pr = sub.add_parser("protected", help="protected-text scan of the public tree")
    prsub = pr.add_subparsers(dest="subcommand")
    pf = prsub.add_parser("fingerprint", help="PRIVATE side: protected files -> fingerprint list")
    pf.add_argument("--source", action="append", required=True, metavar="LABEL=PATH",
                    help="an opaque label and the protected file, e.g. P-001=/private/path.md")
    pf.add_argument("--out", required=True, help="where to write the list (outside this repo)")
    pf.add_argument("--window", type=int, default=protected.DEFAULT_WINDOW)
    pf.add_argument("--min-hits", dest="min_hits", type=int, default=protected.DEFAULT_MIN_HITS)
    pf.set_defaults(func=cmd_protected_fingerprint)
    ps = prsub.add_parser("scan", help="fail if the public tree holds protected text")
    ps.add_argument("--repo", default=_repo_root())
    ps.add_argument("--fingerprints", help="the private list (or set %s)" % protected.ENV_LIST)
    ps.add_argument("--allowlist", help="default: %s" % protected.DEFAULT_ALLOWLIST)
    ps.set_defaults(func=cmd_protected_scan)
    pc = prsub.add_parser("check-allowlist", help="needs no private input; runs in public CI")
    pc.add_argument("--repo", default=_repo_root())
    pc.add_argument("--allowlist")
    pc.set_defaults(func=cmd_protected_check_allowlist)
    pp = prsub.add_parser("pin", help="re-pin the allow-list to the files' current bytes (reviewed act)")
    pp.add_argument("--repo", default=_repo_root())
    pp.add_argument("--allowlist")
    pp.set_defaults(func=cmd_protected_pin)

    go = sub.add_parser("governance", help="CODEOWNERS check / render")
    gosub = go.add_subparsers(dest="subcommand")
    gc = gosub.add_parser("check")
    gc.add_argument("--root", default=_repo_root())
    gc.add_argument("--repo-slug", dest="repo_slug")
    gc.add_argument("--use-config", action="store_true")
    gc.set_defaults(func=cmd_governance_check)
    gr = gosub.add_parser("render")
    gr.add_argument("--template",
                    default=os.path.join(_repo_root(), "templates", "governance",
                                         "CODEOWNERS.template"))
    gr.add_argument("--repo-slug", dest="repo_slug", required=True)
    gr.add_argument("--owner", action="append",
                    help="NAME=@handle [@handle...] (repeatable)")
    gr.add_argument("--out")
    gr.set_defaults(func=cmd_governance_render)

    bd = sub.add_parser("boundary", help="founder-lane checks")
    bdsub = bd.add_subparsers(dest="subcommand")
    bp = bdsub.add_parser("check-pr", help="fail a PR that changes founder-lane paths "
                                            "without a founder's approval of its head commit")
    bp.add_argument("--repo", default=".")
    bp.add_argument("--base", required=True)
    bp.add_argument("--head", required=True)
    bp.add_argument("--author", required=True)
    bp.add_argument("--approved-by", dest="approved_by", default="",
                    help="comma-separated logins that approved THIS head commit")
    bp.set_defaults(func=cmd_boundary_check_pr)

    hk = sub.add_parser("hook", help="Claude Code hooks")
    hksub = hk.add_subparsers(dest="subcommand")
    hp = hksub.add_parser("pre-edit", help="PreToolUse: hold the founder lane in the session")
    hp.set_defaults(func=cmd_hook_pre_edit)

    ic = sub.add_parser("instance", help="the instance contract checks")
    icsub = ic.add_subparsers(dest="instance_command")
    icc = icsub.add_parser("check", help="read-only: baseline files, the 3.0 folders, founder review "
                                         "at the new paths (asks GitHub whether it's enforced)")
    icc.add_argument("--target", default=".")
    icc.add_argument("--repo-slug", dest="repo_slug", help="owner/repo (default: the origin remote)")
    icc.add_argument("--offline", action="store_true",
                     help="skip GitHub; founder review then counts as unverified (a failure)")
    icc.set_defaults(func=cmd_instance_check)

    ws = sub.add_parser("workspace", help="Obsidian Workspace Kit over separate repositories")
    wssub = ws.add_subparsers(dest="workspace_command")
    wp = wssub.add_parser("plan", help="show what init/sync would do; changes nothing")
    wp.add_argument("--manifest", required=True)
    wp.add_argument("--parent", required=True)
    wp.add_argument("--offline", action="store_true", help="skip checking remote access")
    wp.set_defaults(func=cmd_workspace_plan)
    wi = wssub.add_parser("init", help="create the workspace folder and clone what is active")
    wi.add_argument("--manifest", required=True)
    wi.add_argument("--parent", required=True)
    wi.add_argument("--filter", help="partial clone filter for large repositories, e.g. blob:none")
    wi.set_defaults(func=cmd_workspace_init)
    wsy = wssub.add_parser("sync", help="clone newly active repositories and rebuild the maps")
    wsy.add_argument("--parent", required=True)
    wsy.add_argument("--filter")
    wsy.add_argument("--move-retired", action="store_true",
                     help="move pristine copies of no-longer-active repositories out of the "
                          "vault (moved, never deleted)")
    wsy.set_defaults(func=cmd_workspace_sync)
    wst = wssub.add_parser("status", help="each repository's state, without fetching")
    wst.add_argument("--parent", required=True)
    wst.set_defaults(func=cmd_workspace_status)

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return EXIT_ERROR
    try:
        return args.func(args)
    except Refusal as exc:
        return _report_refusal(exc)
    except KeyboardInterrupt:
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
