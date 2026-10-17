"""Loaded by every CLI process the integration test runs, through PYTHONPATH: records each write and each git run
to the file AIOS_AUDIT_LOG names, one JSON line per event, for the test's runtime checks (audit_writes.py, the
runtime backstop to the static write-site inventory; Chat Zero, review round 63). Does nothing without it."""
import json
import os
import sys

_LOG = os.environ.get("AIOS_AUDIT_LOG")
if _LOG:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        import audit_writes
    finally:
        del sys.path[0]
    _fh = open(_LOG, "a", buffering=1)
    _log = os.path.abspath(_LOG)

    class _Log(object):
        def add(self, found):
            for item in found:
                if item[0] == "git":
                    row = {"git": item[1], "cwd": item[2]}
                elif item[1] and os.path.abspath(item[1]) != _log:
                    row = {"kind": item[0], "path": item[1], "folder": item[2]}
                else:
                    continue
                row.update(pid=os.getpid(), cmd=sys.argv[1:3])
                _fh.write(json.dumps(row) + "\n")

    audit_writes.install()
    audit_writes._ACTIVE.append(_Log())
