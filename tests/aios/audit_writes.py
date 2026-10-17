"""Starter 3.1: the runtime backstop to the write-site inventory (Chat Zero, review round 63).

Python's audit hooks (sys.addaudithook, PEP 578) report every write the interpreter makes, whatever the source
looks like: a file opened for writing (by mode or by os.open's flags), rename and replace, remove, mkdir,
rmdir, chmod, link, symlink, truncate, utime, chown, shutil's tree and copy calls, temporary files, and every
`git` run as a subprocess, with its arguments. The static inventory (test_write_sites.py) reads the source;
this records what actually runs, so a write in a form the scanner can't read is still seen.

One hook is installed per process and stays (an audit hook can't be removed); it records only while a
Recording is active, and never lets an error of its own reach the code being recorded.
"""

import os
import sys
import threading

_LOCAL = threading.local()
_ACTIVE = []
_INSTALLED = []
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
# event -> (index of each path it writes, index of its dir_fd for that path or None, whether the path is a folder)
_PATHS = {
    "os.rename": [(0, 2, False), (1, 3, False)],   # os.replace raises it too
    "os.link": [(1, 3, False)],
    "os.symlink": [(1, 2, False)],
    "os.remove": [(0, 1, False)],                 # os.unlink raises it too
    "os.rmdir": [(0, 1, True)],
    "os.mkdir": [(0, 2, True)],
    "os.chmod": [(0, 2, False)],
    "os.chown": [(0, 3, False)],
    "os.utime": [(0, 3, False)],
    "os.truncate": [(0, None, False)],
    "os.chflags": [(0, None, False)],
    "os.lchflags": [(0, None, False)],
    "os.setxattr": [(0, None, False)],
    "os.removexattr": [(0, None, False)],
    "shutil.rmtree": [(0, None, True)],
    "shutil.copyfile": [(1, None, False)],
    "shutil.copymode": [(1, None, False)],
    "shutil.copystat": [(1, None, False)],
    "shutil.copytree": [(1, None, True)],
    "shutil.move": [(0, None, False), (1, None, False)],
    "tempfile.mkstemp": [(0, None, False)],
    "tempfile.mkdtemp": [(0, None, True)],
}


def _fd_path(fd):
    """The path an open file descriptor names, where the system can say."""
    try:
        import fcntl
        if hasattr(fcntl, "F_GETPATH"):
            return os.fsdecode(fcntl.fcntl(fd, fcntl.F_GETPATH, bytes(1024)).split(b"\0", 1)[0])
    except (OSError, ValueError, ImportError):
        pass
    try:
        return os.readlink("/proc/self/fd/%d" % fd)
    except OSError:
        return None


def _path(value, dir_fd=None):
    if isinstance(value, int) or value is None:
        return None if value is None else (_fd_path(value) or "<fd %d>" % value)
    value = os.fsdecode(value)
    if dir_fd not in (None, -1) and isinstance(dir_fd, int) and not os.path.isabs(value):
        base = _fd_path(dir_fd)
        value = os.path.join(base, value) if base else "<dir fd %d>/%s" % (dir_fd, value)
    return os.path.abspath(value)


def parse(event, args):
    """[(kind, path, is_folder)] for a write, [("git", argv, cwd)] for a git subprocess, else []."""
    if event == "open":
        path, mode, flags = (list(args) + [None, None, None])[:3]
        # By the mode's access part only: "r:xz" reads (independent review, round 65).
        writes = (isinstance(mode, str) and any(c in mode.split(":")[0].split("|")[0] for c in "wax+")) or \
            (isinstance(flags, int) and flags & _WRITE_FLAGS)
        # An open of a file descriptor too (os.fdopen): by the path it names, where the system can say (round 63).
        return [("open", _path(path), False)] if writes else []
    if event == "subprocess.Popen":
        executable, argv, cwd = (list(args) + [None, None, None])[:3]
        argv = [argv] if isinstance(argv, (str, bytes)) else list(argv or [])
        argv = [os.fsdecode(a) if isinstance(a, (str, bytes)) else str(a) for a in argv]
        name = os.path.basename(os.fsdecode(executable) if executable else (argv[0] if argv else ""))
        return [("git", argv, os.fsdecode(cwd) if cwd else os.getcwd())] if name == "git" else []
    out = []
    for index, fd_index, folder in _PATHS.get(event, ()):
        if index < len(args):
            fd = args[fd_index] if fd_index is not None and fd_index < len(args) else None
            out.append((event, _path(args[index], fd), folder))
    return out


def _hook(event, args):
    if not _ACTIVE or getattr(_LOCAL, "busy", False):
        return
    _LOCAL.busy = True
    try:
        found = parse(event, args)
        for recording in list(_ACTIVE):
            recording.add(found)
    except Exception:  # noqa: BLE001 - the recorder must never change what it records
        pass
    finally:
        _LOCAL.busy = False


def install():
    if not _INSTALLED:
        sys.addaudithook(_hook)
        _INSTALLED.append(True)


class Recording(object):
    """Every write made, and every git run, while active: `writes` holds (kind, absolute path, is_folder),
    `gits` holds (argv, cwd)."""

    def __init__(self):
        self.writes, self.gits = [], []

    def add(self, found):
        for item in found:
            (self.gits.append(item[1:]) if item[0] == "git" else self.writes.append(item))

    def __enter__(self):
        install()
        _ACTIVE.append(self)
        return self

    def __exit__(self, *exc):
        _ACTIVE.remove(self)
        return False

    def under(self, root):
        """(relative path, is_folder) of each write inside `root`, resolved the way the disk resolves it."""
        real_root = os.path.realpath(root)
        out = []
        for _kind, path, folder in self.writes:
            if not path or path.startswith("<"):
                continue
            real = os.path.realpath(path)
            if real.startswith(real_root + os.sep):
                out.append((os.path.relpath(real, real_root).replace(os.sep, "/"), folder))
        return out

    def git_dirs(self):
        """Each git run's repository folder: its -C path, else its working folder."""
        out = []
        for argv, cwd in self.gits:
            where = cwd
            for i, word in enumerate(argv[:-1]):
                if word == "-C":
                    where = os.path.join(where, argv[i + 1])
            out.append((argv, os.path.abspath(where)))
        return out
