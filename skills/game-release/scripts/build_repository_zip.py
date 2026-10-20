#!/usr/bin/env python3
"""Build an on-demand repository-root ZIP that fails closed, then byte-verify it.

    python -B build_repository_zip.py SOURCE OUTPUT.zip [options]

Inventory modes:
  default         every file under SOURCE
  --git-tracked   only the files git tracks under SOURCE
  --allowlist F   exactly the paths listed in F, one per line ('#' starts a
                  comment); any other file under SOURCE fails the build

In every mode, files matching a default exclude (secrets, credentials,
environments, editor and vault state, continuity ledgers, backups, git
metadata, caches, archives) are left out and listed, unless an --include
pattern names them. Git-ignored files, symbolic links, and the .git folder
are never packaged. When a .git folder or file exists at or above SOURCE, the
builder needs git to answer for it: if git is missing or fails, the build is
refused rather than run without git's ignore rules. GIT_DIR, GIT_WORK_TREE,
GIT_INDEX_FILE, and the other variables that redirect git are ignored.

The JSON summary lists every packaged path, every excluded path with its
reason, and two digests. contentDigest is the SHA-256 of the lines
"<sha256 of the file>  <path>", one per packaged file in path order, so it
depends only on names and bytes. zipSha256 also depends on the compressor:
DEFLATE output can change with the Python build's zlib, so a deflated
archive's hash is reproducible only with the same zlib. Pass --stored for
an archive whose bytes are reproducible everywhere.

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
import subprocess
import zipfile
import zlib
from pathlib import Path, PurePosixPath

ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
UNIX_FILE_MODE = 0o100644
CREATE_SYSTEM_UNIX = 3
DEFLATE_LEVEL = 9

# (pattern, where it applies): "dir" matches a folder on the path, "file" the
# final name, "any" either. Matching ignores case. Some names are built from
# fragments so that this file never spells a private vault folder.
DEFAULT_EXCLUDES = (
    (".git*", "any"),
    (".env*", "any"),
    ("*.pem", "file"),
    ("*.key", "file"),
    ("id_rsa*", "file"),
    ("id_ecdsa*", "file"),
    ("id_ed25519*", "file"),
    (".ssh", "dir"),
    (".aws", "dir"),
    (".npmrc", "file"),
    (".pypirc", "file"),
    (".netrc", "file"),
    (".venv", "dir"),
    ("venv", "dir"),
    ("node_modules", "dir"),
    (".vscode", "dir"),
    (".idea", "dir"),
    ("." + "obsidian", "dir"),
    ("CONTEXT_CONTINUITY*.md", "file"),
    ("*backup*", "dir"),
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


def default_exclude(name: str) -> tuple[str, str] | None:
    """The (display path, pattern) of the first default exclude that matches."""
    parts = parts_of(name)
    for index, part in enumerate(parts):
        is_dir = index < len(parts) - 1
        folded = part.casefold()
        for pattern, where in DEFAULT_EXCLUDES:
            if where == "dir" and not is_dir or where == "file" and is_dir:
                continue
            if fnmatch.fnmatchcase(folded, pattern.casefold()):
                display = "/".join(parts[: index + 1]) + ("/" if is_dir else "")
                return display, pattern + ("/" if where == "dir" else "")
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
    """This process's environment without the variables that redirect git."""
    return {key: value for key, value in os.environ.items() if key.upper() not in GIT_REDIRECTS}


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


def walk(source: Path) -> tuple[list[str], list[str]]:
    """Files and symbolic links under source, and the .git entries skipped."""
    names, git_entries = [], []
    for directory, subdirectories, filenames in os.walk(source):
        relative = Path(directory).relative_to(source)
        descend = []
        for name in sorted(subdirectories):
            if name == ".git":
                git_entries.append((relative / name).as_posix() + "/")
            elif (Path(directory) / name).is_symlink():
                names.append((relative / name).as_posix())
            else:
                descend.append(name)
        subdirectories[:] = descend
        for filename in filenames:
            if filename == ".git":
                git_entries.append((relative / filename).as_posix())
            else:
                names.append((relative / filename).as_posix())
    return sorted(names), sorted(git_entries)


def read_allowlist(path: Path) -> list[str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
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


def validate_names(names: list[str]) -> None:
    folded_names: dict[str, str] = {}
    for name in names:
        if name.startswith("/") or ".." in parts_of(name) or "\\" in name or ":" in name:
            raise BuildError(f"Unsafe archive path: {name}")
        folded = name.casefold()
        if folded in folded_names:
            raise BuildError(f"Case-insensitive duplicate: {folded_names[folded]} and {name}")
        folded_names[folded] = name


def select(
    source: Path, mode: str, allowlist: list[str] | None, includes: list[str]
) -> tuple[list[str], dict[str, str]]:
    """Split the inventory into packaged names and excluded {path: reason}."""
    in_git = inside_git_work_tree(source)
    if mode == "git-tracked" and not in_git:
        raise BuildError("--git-tracked needs a source folder inside a git work tree.")
    walked, git_entries = walk(source)
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
        elif (source / name).is_symlink():
            shown, reason = name, "symbolic link, never packaged"
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
    return packaged, excluded


def build(
    source: Path,
    output: Path,
    required: list[str],
    *,
    mode: str = "walk",
    allowlist: list[str] | None = None,
    includes: list[str] | None = None,
    stored: bool = False,
) -> dict[str, object]:
    source = source.resolve()
    output = output.resolve()
    if not source.is_dir():
        raise BuildError(f"The source folder does not exist: {source}")
    if output.suffix.lower() != ".zip":
        raise BuildError("The output must use the .zip extension.")
    if output.is_relative_to(source):
        raise BuildError("The output ZIP must be outside the source folder.")

    names, excluded = select(source, mode, allowlist, includes or [])
    if not names:
        raise BuildError("The source folder contains no packageable files.")
    validate_names(names)
    missing = [name for name in required if name not in names]
    if missing:
        raise BuildError("Required package paths are missing: " + ", ".join(missing))

    contents = {name: (source / name).read_bytes() for name in names}
    compression = zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    try:
        with zipfile.ZipFile(temporary, "w") as archive:
            for name in names:
                info = zipfile.ZipInfo(name, ZIP_TIMESTAMP)
                info.create_system = CREATE_SYSTEM_UNIX
                info.external_attr = (UNIX_FILE_MODE & 0xFFFF) << 16
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
        "fileCount": len(names),
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
        + ", ".join(pattern + ("/" if where == "dir" else "") for pattern, where in DEFAULT_EXCLUDES),
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
        )
    except (BuildError, OSError) as error:
        print(f"build_repository_zip.py: {error}", file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
