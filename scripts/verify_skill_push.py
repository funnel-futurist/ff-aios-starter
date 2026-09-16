#!/usr/bin/env python3
"""Validate changed skills in every outgoing commit, without executing that tree."""
import io
import pathlib
import re
import subprocess
import sys
import tarfile
import tempfile

import verify_skills as validator

ROOT = pathlib.Path(__file__).resolve().parent.parent
ZERO = "0" * 40


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def public_check(folder):
    body = (folder / "SKILL.md").read_text()
    report = validator.check(folder)
    errors = [key for key, passed in report["checks"].items() if not passed]
    # The public contract requires literal labels, not pictograms alone.
    for _, section, _, _ in validator._cl_sections(body):
        for item in validator._cl_items(section):
            if not re.search(r"(?i)\bExample\s*:", item.replace("*", "")):
                errors.append("literal Example: label")
            if not re.search(r"(?i)\bCounter-example\s*:", item.replace("*", "")):
                errors.append("literal Counter-example: label")
    if report["is_producer"] and not report["has_gather_block"]:
        errors.append("producing skill needs GATHER G-n items")
    if report["resources_dead"] or report["resources_unanchored"]:
        errors.append("Resource links must resolve locally")
    # This is a bounded structural check, not a complete secret/IP classifier.
    private_link = re.compile(r"https?://(?:docs\.google\.com|[^/]+\.slack\.com)/", re.I)
    secret = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\b(?:sk_live_|ghp_)[A-Za-z0-9]{16,}")
    for file in folder.rglob("*"):
        if file.is_symlink():
            errors.append("skill symlink")
        elif file.is_file():
            text = file.read_text(errors="replace")
            if private_link.search(text):
                errors.append("workspace document/message URL")
            if secret.search(text):
                errors.append("credential marker")
    return sorted(set(errors))


def snapshot(commit, destination):
    # Refuse archive links before extraction. No candidate code is executed.
    archive = tarfile.open(fileobj=io.BytesIO(git("archive", "--format=tar", commit)))
    members = archive.getmembers()
    for member in members:
        path = pathlib.PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts or not (member.isfile() or member.isdir()):
            raise ValueError("unsafe repository archive entry")
    for member in members:
        target = destination / member.name
        if member.isdir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.extractfile(member).read())


def verify_push(remote, lines):
    commits = set()
    for line in lines:
        parts = line.split()
        if len(parts) != 4:
            raise ValueError("invalid pre-push input")
        _, local, _, old = parts
        if local == ZERO:
            continue
        if not re.fullmatch(r"[0-9a-f]{40,64}", local + "") or not re.fullmatch(r"[0-9a-f]{40,64}", old):
            raise ValueError("invalid object id")
        args = ["rev-list", local]
        if old != ZERO:
            args += ["^" + old]
        else:
            args += ["--not", "--remotes=" + remote]
        commits.update(git(*args).decode().splitlines())
    failures = []
    for commit in sorted(commits):
        changed = git("diff-tree", "--root", "--no-commit-id", "-r", "-m", "--name-only", "-z", commit).decode().split("\0")
        names = {path.split("/")[2] for path in changed if path.startswith(".claude/skills/") and len(path.split("/")) >= 3 and path.split("/")[2] != "README.md"}
        with tempfile.TemporaryDirectory(prefix="skill-push-") as tmp:
            tree = pathlib.Path(tmp)
            snapshot(commit, tree)
            validator.REPO = tree
            validator.SKILLS = tree / ".claude/skills"
            validator._BASENAME_INDEX = None
            # Reference-only changes must revalidate the skills that consume them.
            external = [p for p in changed if p]
            if validator.SKILLS.is_dir():
                for skill in validator.SKILLS.iterdir():
                    if not skill.is_dir():
                        continue
                    documents = "\n".join(p.read_text(errors="replace") for p in skill.rglob("*.md"))
                    if any(p in documents or pathlib.PurePosixPath(p).name in documents for p in external):
                        names.add(skill.name)
            for name in sorted(names):
                folder = validator.SKILLS / name
                if not folder.exists():  # Entire skill deliberately removed.
                    continue
                if not folder.is_dir() or not (folder / "SKILL.md").is_file():
                    failures.append((commit, name, ["missing SKILL.md"]))
                    continue
                errors = public_check(folder)
                if errors:
                    failures.append((commit, name, errors))
    for commit, name, errors in failures:
        print(f"FAIL {commit[:12]} {name}: {', '.join(errors)}", file=sys.stderr)
    if failures:
        print("Push blocked by skill validation.", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        remote = sys.argv[1]
        if remote.startswith("-") or not re.fullmatch(r"[A-Za-z0-9._/-]+", remote):
            raise ValueError("unsupported remote name")
        raise SystemExit(verify_push(remote, sys.stdin.read().splitlines()))
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print("Skill verification failed closed: " + str(error), file=sys.stderr)
        raise SystemExit(1)
