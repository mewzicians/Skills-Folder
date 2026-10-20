#!/usr/bin/env python3
"""Build an on-demand repository-root ZIP from a vetted inventory, then byte-verify it.

    python -B build_repository_zip.py SOURCE OUTPUT.zip [options]

Inventory modes:
  default         every file under SOURCE
  --git-tracked   only the files git tracks under SOURCE. A tracked file that
                  differs from HEAD fails the build unless --allow-dirty is
                  passed, because the work-tree bytes are what get packaged.
  --allowlist F   exactly the paths listed in F, one per line ('#' starts a
                  comment; UTF-8, with or without a byte-order mark). An
                  unlisted file fails the build, except that git-ignored
                  files, links, and default excludes are skipped and listed
                  as excluded. A listed file that is one of those, or that
                  does not exist, also fails the build.

In every mode, files matching a default exclude (keys, certificates,
credentials, environments, editor and vault state, continuity ledgers,
backups, git metadata, caches, archives) are left out and listed, unless an
--include pattern names them. The default excludes are a denylist of common
names: they cannot know every secret a project keeps, so the default walk and
--git-tracked package any risky file they do not name. --allowlist is the
only fully fail-closed mode; use it for a public release.

Git-ignored files, symbolic links, the .git folder in any letter case, and
anything that is not a regular file, such as a FIFO, are never packaged.
Windows junctions count as symbolic links and are never followed, and a file
whose real path leaves SOURCE fails the build. An archive path may not hold
a control character, so no name can forge a contentDigest line.

When a .git folder or file exists at or above SOURCE, the builder needs git
to answer for it: if git is missing or fails, the build is refused rather
than run without git's ignore rules. GIT_DIR, GIT_WORK_TREE, GIT_INDEX_FILE,
and the other variables that redirect git are ignored.

The JSON summary lists every packaged path, every excluded path with its
reason, and two digests. contentDigest is the SHA-256 of the lines
"<sha256 of the file>  <path>", one per packaged file in path order, so it
depends only on names and bytes. zipSha256 also depends on the compressor:
DEFLATE output can change with the Python build's zlib, so a deflated
archive's hash is reproducible only with the same zlib. Pass --stored for
an archive whose bytes are reproducible everywhere. Inside a git work tree
the summary also records gitHead, the HEAD commit (null before the first
commit), and gitDirty, whether a tracked file under SOURCE differs from it.

Every entry has a fixed timestamp and a Unix mode: 0755 when git's index
records the file as executable or, outside Windows, when the file itself is
executable; otherwise 0644. Windows has no executable bit, so there only the
index counts. The summary's executable list names the 0755 entries.

Exit codes: 0 built and verified, 1 build refused or failed, 2 usage error.
Standard library only.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import fnmatch
import hashlib
import json
import os
import platform
import stat
import subprocess
import zipfile
import zlib
from pathlib import Path, PurePosixPath

ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
UNIX_FILE_MODE = 0o100644
UNIX_EXECUTABLE_MODE = 0o100755
CREATE_SYSTEM_UNIX = 3
DEFLATE_LEVEL = 9
# The bit that marks a Windows reparse tag as a name surrogate: a link to another path.
NAME_SURROGATE_TAG = 0x20000000

# (pattern, where it applies): "dir" matches a folder on the path, "file" the
# final name, "any" either, and "path" the last parts of the path, such as
# "kube/config". Matching ignores case. Some names are built from fragments
# so that this file never spells a private vault folder.
#
# This is a denylist of common names. It cannot know every secret a project
# keeps, so only --allowlist is fully fail-closed.
DEFAULT_EXCLUDES = (
    (".git*", "any"),
    (".env*", "any"),
    ("*.env", "file"),
    # Keys, certificates, and signing material.
    ("*.pem", "file"),
    ("*.key", "file"),
    ("*.p8", "file"),
    ("*.p12", "file"),
    ("*.pfx", "file"),
    ("*.keystore", "file"),
    ("*.jks", "file"),
    ("*.mobileprovision", "file"),
    ("*.ppk", "file"),
    ("*.gpg", "file"),
    ("id_rsa*", "file"),
    ("id_dsa*", "file"),
    ("id_ecdsa*", "file"),
    ("id_ed25519*", "file"),
    (".ssh", "dir"),
    (".gnupg", "dir"),
    # Credentials and service configuration.
    (".aws", "dir"),
    (".docker", "dir"),
    (".kube", "dir"),
    ("kube/config", "path"),
    ("credentials.json", "file"),
    ("secrets.*", "file"),
    ("google-services.json", "file"),
    ("GoogleService-Info.plist", "file"),
    (".htpasswd", "file"),
    (".npmrc", "file"),
    (".pypirc", "file"),
    (".netrc", "file"),
    ("*.tfstate", "file"),
    ("*.tfstate.*", "file"),
    # Environments, editors, vaults, ledgers, caches, and archives.
    (".venv", "dir"),
    ("venv", "dir"),
    ("node_modules", "dir"),
    (".vscode", "dir"),
    (".idea", "dir"),
    (".vs", "dir"),
    ("." + "obsidian", "dir"),
    ("CONTEXT_CONTINUITY*.md", "file"),
    ("*backup*", "dir"),
    ("*.bak", "file"),
    ("*~", "file"),
    ("__pycache__", "dir"),
    (".pytest_cache", "dir"),
    (".mypy_cache", "dir"),
    (".ruff_cache", "dir"),
    (".tox", "dir"),
    (".cache", "dir"),
    ("*.pyc", "file"),
    ("*.pyo", "file"),
    (".DS_Store", "file"),
    ("Thumbs.db", "file"),
    ("desktop.ini", "file"),
    ("*.zip", "file"),
)
# Variables that point git at another repository, index, or object store, or
# stop its search for one. The builder asks git about the source folder only.
GIT_REDIRECTS = frozenset(
    {
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_COMMON_DIR",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_CEILING_DIRECTORIES",
    }
)


class BuildError(Exception):
    """The build was refused or failed; the message says why."""


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parts_of(name: str) -> tuple[str, ...]:
    return PurePosixPath(name).parts


def shown_pattern(pattern: str, where: str) -> str:
    return pattern + ("/" if where == "dir" else "")


def default_exclude(name: str) -> tuple[str, str] | None:
    """The (display path, pattern) of the first default exclude that matches.

    Folders are checked outermost first, so an excluded folder is reported
    once rather than file by file.
    """
    parts = parts_of(name)
    folded_parts = [part.casefold() for part in parts]
    for index, folded in enumerate(folded_parts):
        is_dir = index < len(parts) - 1
        for pattern, where in DEFAULT_EXCLUDES:
            if where == "path":
                wanted = pattern.casefold().split("/")
                if is_dir or len(wanted) > len(parts):
                    continue
                if all(map(fnmatch.fnmatchcase, folded_parts[-len(wanted) :], wanted)):
                    return name, pattern
                continue
            if where == "dir" and not is_dir or where == "file" and is_dir:
                continue
            if fnmatch.fnmatchcase(folded, pattern.casefold()):
                display = "/".join(parts[: index + 1]) + ("/" if is_dir else "")
                return display, shown_pattern(pattern, where)
    return None


def included(name: str, patterns: list[str]) -> bool:
    """Whether an --include pattern names this file or a folder above it."""
    parts = parts_of(name)
    prefixes = ["/".join(parts[: index + 1]).casefold() for index in range(len(parts))]
    for pattern in patterns:
        folded = pattern.strip("/").casefold()
        if any(fnmatch.fnmatchcase(prefix, folded) for prefix in prefixes):
            return True
    return False


def git_environment() -> dict[str, str]:
    """This process's environment without the variables that redirect git.

    GIT_OPTIONAL_LOCKS=0 keeps git status and diff from rewriting the index,
    so a build never changes the repository it reads.
    """
    environment = {key: value for key, value in os.environ.items() if key.upper() not in GIT_REDIRECTS}
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    return environment


def git(
    source: Path, *arguments: str, stdin: bytes | None = None
) -> subprocess.CompletedProcess[bytes] | None:
    try:
        return subprocess.run(
            ["git", "-C", str(source), *arguments],
            input=stdin,
            capture_output=True,
            check=False,
            env=git_environment(),
        )
    except OSError:
        return None


def nul_list(data: bytes) -> list[str]:
    return sorted(name for name in data.decode("utf-8", "surrogateescape").split("\0") if name)


def git_paths(source: Path, *arguments: str) -> list[str]:
    completed = git(source, "ls-files", "-z", *arguments)
    if completed is None or completed.returncode != 0:
        raise BuildError("git ls-files failed under the source folder.")
    return nul_list(completed.stdout)


def git_ignored(source: Path, names: list[str]) -> set[str]:
    """The names git ignores. Tracked files are never ignored."""
    if not names:
        return set()
    request = "".join(name + "\0" for name in names).encode("utf-8", "surrogateescape")
    completed = git(source, "check-ignore", "-z", "--stdin", stdin=request)
    # Exit code 1 means that no name is ignored.
    if completed is None or completed.returncode not in (0, 1):
        raise BuildError("git check-ignore failed under the source folder.")
    return set(nul_list(completed.stdout))


def git_index_modes(source: Path) -> dict[str, str]:
    """The index mode of every file git tracks under source, such as 100755."""
    completed = git(source, "ls-files", "-s", "-z")
    if completed is None or completed.returncode != 0:
        raise BuildError("git ls-files failed under the source folder.")
    modes = {}
    for entry in completed.stdout.decode("utf-8", "surrogateescape").split("\0"):
        if entry:
            fields, _, name = entry.partition("\t")
            modes[name] = fields.split(" ", 1)[0]
    return modes


def git_head(source: Path) -> tuple[str | None, list[str]]:
    """HEAD's commit, or None before the first commit, and the tracked paths that differ from it."""
    head = git(source, "rev-parse", "--verify", "--quiet", "HEAD^{commit}")
    if head is None:
        raise BuildError("git rev-parse failed under the source folder.")
    if head.returncode != 0:
        return None, git_paths(source, "--cached")
    changed = git(source, "diff", "--name-only", "--no-renames", "--relative", "-z", "HEAD", "--", ".")
    if changed is None or changed.returncode != 0:
        raise BuildError("git diff failed under the source folder.")
    return head.stdout.decode("ascii").strip(), nul_list(changed.stdout)


def folders_of(name: str) -> list[str]:
    """The folders above name, outermost first; '' is the source folder."""
    parts = parts_of(name)
    return ["/".join(parts[:index]) for index in range(len(parts))]


def collapse(names: list[str], chosen: set[str]) -> dict[str, str]:
    """Show each chosen name as the outermost folder that holds only chosen names."""
    totals: dict[str, int] = {}
    hits: dict[str, int] = {}
    for name in names:
        for folder in folders_of(name):
            totals[folder] = totals.get(folder, 0) + 1
            hits[folder] = hits.get(folder, 0) + (name in chosen)
    shown = {}
    for name in chosen:
        folder = next((item for item in folders_of(name) if hits[item] == totals[item]), None)
        shown[name] = name if folder is None else (folder + "/" if folder else "./")
    return shown


def git_marker(source: Path) -> Path | None:
    """The nearest .git folder or file at or above source, if there is one."""
    for folder in (source, *source.parents):
        if os.path.lexists(folder / ".git"):
            return folder / ".git"
    return None


def inside_git_work_tree(source: Path) -> bool:
    """Whether git's ignore rules apply. Fails closed when git cannot answer.

    A source with no .git at or above it is a plain folder, such as an
    extracted copy. With one, a git that is missing or fails would leave
    ignored files unrecognized, so the build is refused instead.
    """
    completed = git(source, "rev-parse", "--is-inside-work-tree")
    if completed is not None and completed.returncode == 0 and completed.stdout.strip() == b"true":
        return True
    marker = git_marker(source)
    if marker is None:
        return False
    if completed is None:
        reason = "git is not installed or not on PATH"
    else:
        detail = completed.stderr.decode("utf-8", "replace").strip().splitlines()
        reason = detail[0] if detail else f"git rev-parse exited {completed.returncode}"
    raise BuildError(
        f"{marker} exists, but git cannot read the work tree ({reason}), so git-ignored "
        "files cannot be recognized. Fix git, or build from a copy without git metadata."
    )


def is_link(path: Path) -> bool:
    """A symbolic link, or on Windows a junction or another redirecting reparse point.

    pathlib's is_symlink() is False for a junction, and os.walk descends into
    one. A reparse point whose tag is a name surrogate points somewhere else;
    other reparse points, such as cloud-storage placeholders, hold the file's
    own data and are ordinary files.
    """
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode):
        return True
    if getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        tag = getattr(info, "st_reparse_tag", 0)
        return tag == 0 or bool(tag & NAME_SURROGATE_TAG)
    isjunction = getattr(os.path, "isjunction", None)
    return bool(isjunction is not None and isjunction(path))


def walk(source: Path) -> tuple[list[str], dict[str, str], list[str]]:
    """Every entry under source, the ones that are not regular files, and the .git entries skipped.

    The second value maps each link to "link" and each other non-regular
    entry, such as a FIFO or socket, to "special". A link to a folder is
    listed as one entry and never followed. A .git entry is skipped in any
    letter case, since Windows and macOS treat .Git as the same name.
    """
    names, irregular, git_entries = [], {}, []
    for directory, subdirectories, filenames in os.walk(source):
        relative = Path(directory).relative_to(source)
        descend = []
        for name in sorted(subdirectories):
            if name.casefold() == ".git":
                git_entries.append((relative / name).as_posix() + "/")
            elif is_link(Path(directory) / name):
                names.append((relative / name).as_posix())
                irregular[names[-1]] = "link"
            else:
                descend.append(name)
        subdirectories[:] = descend
        for filename in filenames:
            if filename.casefold() == ".git":
                git_entries.append((relative / filename).as_posix())
                continue
            names.append((relative / filename).as_posix())
            if is_link(Path(directory) / filename):
                irregular[names[-1]] = "link"
            elif not stat.S_ISREG(os.lstat(Path(directory) / filename).st_mode):
                irregular[names[-1]] = "special"
    return sorted(names), irregular, sorted(git_entries)


def read_inside(source: Path, name: str) -> bytes:
    """A packaged file's bytes, refused if its real path leaves the source folder."""
    path = source / name
    if not path.resolve(strict=True).is_relative_to(source):
        raise BuildError(f"{name} resolves outside the source folder; refusing to package it.")
    return path.read_bytes()


def read_allowlist(path: Path) -> list[str]:
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise BuildError(f"Cannot read the allowlist {path}: {error}") from error
    names = []
    for line in lines:
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        if "\\" in entry:
            raise BuildError(f"Allowlist entries use '/' separators: {entry}")
        names.append(entry[2:] if entry.startswith("./") else entry)
    if len(names) != len(set(names)):
        raise BuildError("The allowlist names a path more than once.")
    return sorted(names)


def control_character(name: str) -> bool:
    """A C0 or C1 control character, DEL, or an undecodable byte in a name."""
    return any(
        ord(char) < 0x20 or 0x7F <= ord(char) <= 0x9F or 0xD800 <= ord(char) <= 0xDFFF
        for char in name
    )


def validate_names(names: list[str]) -> None:
    folded_names: dict[str, str] = {}
    for name in names:
        if control_character(name):
            raise BuildError(f"Archive path holds a control character or invalid UTF-8: {name!r}")
        if name.startswith("/") or ".." in parts_of(name) or "\\" in name or ":" in name:
            raise BuildError(f"Unsafe archive path: {name}")
        folded = name.casefold()
        if folded in folded_names:
            raise BuildError(f"Case-insensitive duplicate: {folded_names[folded]} and {name}")
        folded_names[folded] = name


def select(
    source: Path,
    mode: str,
    allowlist: list[str] | None,
    includes: list[str],
    allow_dirty: bool = False,
) -> tuple[list[str], dict[str, str], dict[str, object]]:
    """Split the inventory into packaged names and excluded {path: reason}.

    The third value holds what git says: HEAD, whether tracked files differ
    from it, and the index modes, all empty outside a git work tree.
    """
    in_git = inside_git_work_tree(source)
    if mode == "git-tracked" and not in_git:
        raise BuildError("--git-tracked needs a source folder inside a git work tree.")
    facts: dict[str, object] = {"head": None, "dirty": None, "modes": {}}
    if in_git:
        head, changed = git_head(source)
        facts = {"head": head, "dirty": bool(changed), "modes": git_index_modes(source)}
        if mode == "git-tracked" and changed and not allow_dirty:
            shown = ", ".join(changed[:10]) + (f", and {len(changed) - 10} more" if len(changed) > 10 else "")
            state = "differ from HEAD" if head else "are not committed yet; HEAD has no commit"
            raise BuildError(
                f"--git-tracked packages work-tree bytes, and these tracked files {state}: "
                f"{shown}. Commit them, or pass --allow-dirty."
            )
    walked, irregular, git_entries = walk(source)
    ignored = git_ignored(source, walked) if in_git else set()
    shown_ignored = collapse(walked, ignored)
    excluded = {entry: "git metadata, never packaged" for entry in git_entries}
    if mode == "git-tracked":
        candidates = git_paths(source, "--cached")
        present = set(walked)
        missing = [name for name in candidates if name not in present]
        if missing:
            raise BuildError("Tracked files are missing from the work tree: " + ", ".join(missing))
        tracked = set(candidates)
        untracked = {name for name in walked if name not in tracked and name not in ignored}
        for name, shown in collapse(walked, untracked).items():
            excluded[shown] = "untracked"
        for name in ignored:
            excluded[shown_ignored[name]] = "git-ignored, never packaged"
    else:
        candidates = walked
    listed = set(allowlist or [])
    refused: list[str] = []
    packaged: list[str] = []
    for name in candidates:
        rule = default_exclude(name)
        if name in ignored:
            shown, reason = shown_ignored[name], "git-ignored, never packaged"
        elif irregular.get(name) == "link":
            shown, reason = name, "symbolic link or junction, never packaged"
        elif name in irregular:
            shown, reason = name, "not a regular file, never packaged"
        elif rule is not None and not included(name, includes):
            shown, reason = rule[0], f"default exclude {rule[1]}; --include overrides it"
        elif allowlist is not None and name not in listed:
            refused.append(f"{name}: not in the allowlist")
            continue
        else:
            packaged.append(name)
            continue
        if name in listed:
            refused.append(f"{name}: {reason}")
        else:
            excluded.setdefault(shown, reason)
    refused.extend(f"{name}: listed but not found" for name in sorted(listed - set(walked)))
    if refused:
        raise BuildError("The allowlist and the source disagree:\n  " + "\n  ".join(refused))
    return packaged, excluded, facts


def unix_mode(path: Path, index_mode: str | None) -> int:
    """0755 for a file git or, outside Windows, the file system marks executable."""
    executable = index_mode == "100755"
    if os.name != "nt":
        executable = executable or bool(path.stat().st_mode & 0o111)
    return UNIX_EXECUTABLE_MODE if executable else UNIX_FILE_MODE


def build(
    source: Path,
    output: Path,
    required: list[str],
    *,
    mode: str = "walk",
    allowlist: list[str] | None = None,
    includes: list[str] | None = None,
    stored: bool = False,
    allow_dirty: bool = False,
) -> dict[str, object]:
    source = source.resolve()
    output = output.resolve()
    if not source.is_dir():
        raise BuildError(f"The source folder does not exist: {source}")
    if output.suffix.lower() != ".zip":
        raise BuildError("The output must use the .zip extension.")
    if output.is_relative_to(source):
        raise BuildError("The output ZIP must be outside the source folder.")

    names, excluded, facts = select(source, mode, allowlist, includes or [], allow_dirty)
    if not names:
        raise BuildError("The source folder contains no packageable files.")
    validate_names(names)
    missing = [name for name in required if name not in names]
    if missing:
        raise BuildError("Required package paths are missing: " + ", ".join(missing))

    contents = {name: read_inside(source, name) for name in names}
    modes = {name: unix_mode(source / name, facts["modes"].get(name)) for name in names}
    compression = zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    try:
        with zipfile.ZipFile(temporary, "w") as archive:
            for name in names:
                info = zipfile.ZipInfo(name, ZIP_TIMESTAMP)
                info.create_system = CREATE_SYSTEM_UNIX
                info.external_attr = (modes[name] & 0xFFFF) << 16
                # The level goes on each entry: a ZipFile-wide compresslevel
                # does not reach entries written from a prebuilt ZipInfo.
                archive.writestr(
                    info,
                    contents[name],
                    compress_type=compression,
                    compresslevel=None if stored else DEFLATE_LEVEL,
                )
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)

    with zipfile.ZipFile(output, "r") as archive:
        if archive.namelist() != names:
            raise BuildError("The ZIP inventory differs from the selected files.")
        for name in names:
            if archive.read(name) != contents[name]:
                raise BuildError(f"Archived bytes differ: {name}")

    manifest = "".join(f"{sha256_hex(contents[name])}  {name}\n" for name in names)
    return {
        "source": str(source),
        "output": str(output),
        "mode": mode,
        "compression": "stored" if stored else f"deflated, level {DEFLATE_LEVEL}",
        "gitHead": facts["head"],
        "gitDirty": facts["dirty"],
        "fileCount": len(names),
        "executable": [name for name in names if modes[name] == UNIX_EXECUTABLE_MODE],
        "zipBytes": output.stat().st_size,
        "zipSha256": sha256_hex(output.read_bytes()).upper(),
        "contentDigest": sha256_hex(manifest.encode("utf-8")).upper(),
        "python": platform.python_version(),
        "zlib": zlib.ZLIB_RUNTIME_VERSION,
        "requiredPaths": required,
        "includes": includes or [],
        "packaged": names,
        "excluded": [{"path": path, "reason": excluded[path]} for path in sorted(excluded)],
    }


def configure_stdio() -> None:
    """Write UTF-8 to stdout and stderr and escape anything unencodable."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="backslashreplace")


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        epilog="Default excludes: "
        + ", ".join(shown_pattern(pattern, where) for pattern, where in DEFAULT_EXCLUDES)
        + ". They are a denylist; only --allowlist is fully fail-closed.",
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--git-tracked", action="store_true", help="package only files git tracks")
    modes.add_argument("--allowlist", type=Path, metavar="FILE", help="package exactly the listed paths")
    parser.add_argument(
        "--include",
        action="append",
        default=[],
        metavar="PATTERN",
        help="package files a default exclude would leave out (a path or glob; repeatable)",
    )
    parser.add_argument("--require", action="append", default=[], metavar="PATH")
    parser.add_argument("--stored", action="store_true", help="store without compression")
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="with --git-tracked, package tracked files even when they differ from HEAD",
    )
    args = parser.parse_args(argv)
    try:
        allowlist = read_allowlist(args.allowlist) if args.allowlist else None
        mode = "git-tracked" if args.git_tracked else "allowlist" if allowlist is not None else "walk"
        summary = build(
            args.source,
            args.output,
            args.require,
            mode=mode,
            allowlist=allowlist,
            includes=args.include,
            stored=args.stored,
            allow_dirty=args.allow_dirty,
        )
    except (BuildError, OSError) as error:
        print(f"build_repository_zip.py: {error}", file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
