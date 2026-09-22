#!/usr/bin/env python3
"""aios - the install contract for an AIOS workspace.

    release build     cut a DRAFT release manifest from a pinned commit
    release verify    is this manifest pinned, intact and approved?
    install           install an approved release into a clean workspace
    adopt             pin an existing workspace that already matches a release
    verify            readback: does the workspace still match its release?
    upgrade           move to a newer approved release, preserving your work
    rollback          restore the previous release (also recovers a killed upgrade)
    start             role-scoped entry point
    sanitize          what would ship: secrets, client names, internal URLs
    governance        CODEOWNERS check / render

Exit codes are part of the contract: 0 ok, 1 error, 2 package, 3 role, 4 credential,
5 state, 6 verify, 7 sanitize, 8 governance.

Python 3.9+, standard library only.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from aioslib import governance, install as install_mod, orgconfig, release as release_mod  # noqa: E402
from aioslib import roles, sanitize, util  # noqa: E402
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
    record = install_mod.adopt(target, manifest, repo, config,
                               _aios_lookup_from(args.aios_releases))
    _say("pinned %s to %s (%d managed files matched byte for byte)"
         % (target, record["release"]["release_id"], len(record["managed"])))
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
    problems, summary = install_mod.verify(target, record)
    _say("workspace: %s" % target)
    _say("release:   %s (%s)" % (summary["release_id"], summary["version"]))
    _say("managed:   %d/%d files re-hashed from disk"
         % (summary["managed_checked"], summary["managed_total"]))
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
    before = install_mod.load_record(target)
    record = install_mod.upgrade(target, manifest, repo, _aios_lookup_from(args.aios_releases))
    _say("upgraded %s: %s -> %s"
         % (target, before["release"]["version"], record["release"]["version"]))
    _say("  by:       %s (%s)" % (login, role))
    _say("  managed:  %d files, verified by readback" % len(record["managed"]))
    _say("  state:    untouched (seed and unmanaged files were not written)")
    _say("  rollback: available (%s)" % record["previous"]["backup"])
    return EXIT_OK


def cmd_rollback(args):
    target = os.path.abspath(args.target)
    config = orgconfig.load(target)
    policy = roles.load_policy(target)
    login, role = roles.require_lifecycle(policy, config, "rollback")
    record, summary, how = install_mod.rollback(target)
    _say("%s" % how)
    _say("  by:       %s (%s)" % (login, role))
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
                      ["run `gh auth login`"])
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
        _say("not yours in this workspace: %s" % ", ".join(denied))
    return EXIT_OK


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
    findings, scanned = sanitize.scan_release(repo, rev, paths, args.denylist, args.mode)
    _say("scanned %d file(s) at %s" % (scanned, rev[:12]))
    _say("denylist: %s" % (args.denylist or "(none - mode %s)" % args.mode))
    if findings:
        _say("findings: %d" % len(findings))
        for f in findings[:50]:
            _say("  %s:%s  %s  %s  fp=%s"
                 % (f["path"], f["line"], f["kind"], f["detail"], f["fingerprint"]))
        return EXIT_SANITIZE
    _say("findings: 0 (no credential shapes, denylisted names or internal hosts)")
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
    ad.set_defaults(func=cmd_adopt)

    ve = sub.add_parser("verify", help="readback the workspace against its release")
    ve.add_argument("--target", default=".")
    ve.set_defaults(func=cmd_verify)

    up = sub.add_parser("upgrade", help="move to a newer approved release")
    up.add_argument("--release", required=True)
    up.add_argument("--target", default=".")
    up.add_argument("--repo", default=_repo_root())
    up.add_argument("--aios-releases", dest="aios_releases")
    up.set_defaults(func=cmd_upgrade)

    rbk = sub.add_parser("rollback", help="restore the previous release")
    rbk.add_argument("--target", default=".")
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
    sa.set_defaults(func=cmd_sanitize)

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
