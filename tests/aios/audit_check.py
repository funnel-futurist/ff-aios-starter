"""The integration test's runtime checks over the audit log its CLI processes wrote (audit_site/sitecustomize.py):
every write the CLI made stays in the test's own folder or the system's temporary folder; none goes into a
repository's .git folder but the installer's own guard; none goes into the Starter's source repository, which is
another repository to every workspace; every git command the CLI ran only reads; and the log isn't empty.
Usage: audit_check.py <log> <work folder> <source repository>. Prints one PASS or FAIL line per check."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_write_sites import git_kind  # noqa: E402

log, work, source = sys.argv[1], os.path.realpath(sys.argv[2]), os.path.realpath(sys.argv[3])
temp = {os.path.realpath(p) for p in ("/tmp", "/var/tmp", os.environ.get("TMPDIR") or "/tmp")}
rows = [json.loads(line) for line in open(log)] if os.path.exists(log) else []
# The null device takes discarded output; it isn't a file.
writes = [r for r in rows if "path" in r and not r["path"].startswith("<") and r["path"] != os.devnull]
gits = [r for r in rows if "git" in r]


def inside(path, root):
    return path == root or path.startswith(root + os.sep)


def line(ok, label, bad=()):
    print("%s  %s" % ("PASS" if ok else "FAIL", label))
    for b in list(bad)[:10]:
        print("        %s" % b)


real = [(os.path.realpath(r["path"]), r) for r in writes]
line(len(writes) > 50 and len(gits) > 10, "runtime audit recorded the CLI's writes and git runs (%d writes, %d git runs, %d "
     "processes)" % (len(writes), len(gits), len({r["pid"] for r in rows})))
outside = [p for p, _ in real if not inside(p, work) and not any(inside(p, t) for t in temp)]
line(not outside, "runtime audit: no write outside the test's folder or the system's temporary folder", outside)
in_git = [p for p, _ in real if "/.git/" in p + "/" and not p.endswith("/.git/aios-guard")]
line(not in_git, "runtime audit: no write inside a repository's .git folder but the installer's guard", in_git)
in_source = ["%s (%s)" % (p, " ".join(r["cmd"])) for p, r in real if inside(p, source)]
line(not in_source, "runtime audit: no write into the Starter's source repository, another repository to every "
     "workspace", in_source)
writing = ["%s (%s)" % (" ".join(r["git"]), " ".join(r["cmd"])) for r in gits if git_kind(r["git"][1:])]
line(not writing, "runtime audit: every git command the CLI ran only reads", writing)
