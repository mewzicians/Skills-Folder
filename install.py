#!/usr/bin/env python3
"""Install, check, or uninstall the Skills Folder skills for Codex or Claude Code.

    python install.py install                     Codex, in ~/.agents/skills
    python install.py install --target claude     Claude Code, in ~/.claude/skills
    python install.py status                      what is installed where
    python install.py uninstall --target claude   move the skills to backups

Targets: codex ($HOME/.agents/skills, the default), codex-legacy
($CODEX_HOME/skills, or ~/.codex/skills when CODEX_HOME is unset or empty),
codex-project (--project DIR: DIR/.agents/skills), claude
($CLAUDE_CONFIG_DIR/skills, or ~/.claude/skills), claude-project (--project
DIR: DIR/.claude/skills), or any folder with --dest.

Every run shows its plan and asks before changing anything (--yes skips the
question). Each skill is installed when absent, skipped when identical,
upgraded when an older version is recorded, and refused when the installed
copy is newer, holds bytes this installer cannot account for, or shares its
name with a skill in another folder the same host loads. Changes are staged
next to the skills folder, validated, swapped in by rename, and rolled back
together on any failure. Replaced and uninstalled skills move to a backup
folder in your user state folder, never inside a skills folder, and nothing
is deleted. One install or uninstall runs at a time: each holds a lock on
the state folder from start to finish, and a run that finds another one
active refuses.

Exit codes: 0 done or nothing to do, 1 failed or interrupted after a change
began (rolled back, or the next run finishes or rolls it back), 2 usage or
environment error, 3 refused by a safety check (nothing changed), 4 cancelled
before any change, at the prompt or with Ctrl+C (nothing changed). Python
3.11 or later, standard library only, and no network access.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import datetime
import errno
import hashlib
import importlib.util
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

MIN_PYTHON = (3, 11)
PACKAGE_ROOT = Path(__file__).resolve().parent
SKILLS_SOURCE = PACKAGE_ROOT / "skills"
VERSION_FILE = PACKAGE_ROOT / "VERSION"
SCHEMA_MODULE = PACKAGE_ROOT / "tools" / "lib" / "skill_frontmatter.py"

TARGETS = ("codex", "codex-legacy", "codex-project", "claude", "claude-project")
PROJECT_TARGETS = ("codex-project", "claude-project")
STATE_FOLDER = "skills-folder"
LEDGER_NAME = "install-ledger.json"
JOURNAL_NAME = "journal.json"
LOCK_NAME = "install.lock"
STAGE_PREFIX = ".skills-folder-stage-"
LEDGER_SCHEMA = 1
# Skills that versions 1.0.x installed and later versions removed or renamed.
RETIRED = ("game-github-package", "game-skill-creator", "game-skill-installer")
# Files a host or interpreter may add to an installed skill. They are left out
# of digests and new copies, and kept in backups.
DEBRIS_DIRS = frozenset({"__pycache__"})
DEBRIS_FILES = frozenset({".DS_Store", "Thumbs.db", "desktop.ini"})
DEBRIS_SUFFIXES = (".pyc", ".pyo")
VERSION_PATTERN = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
# A skill name as a path part: lowercase kebab-case, at most 64 characters.
# Ledger and journal data become paths only through child(), which applies it.
SKILL_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
MAX_SKILL_NAME = 64
RUN_ID = re.compile(r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{6}")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
# How Codex finds skills in a folder (codex-rs/ext/skills/src/loader): every
# SKILL.md at most six levels below it (a skill folder at most five), outside
# hidden folders, in at most 2,000 folders, named by its frontmatter name or
# else its folder's name.
CODEX_SCAN_DEPTH = 6
CODEX_SCAN_FOLDERS = 2000

EXIT_OK, EXIT_FAILED, EXIT_USAGE, EXIT_REFUSED, EXIT_CANCELLED = 0, 1, 2, 3, 4
# A Windows reparse tag with this bit set redirects to another name, as a
# symbolic link or a junction does (the same test as build_repository_zip.py).
NAME_SURROGATE_TAG = 0x20000000
CHANGES = ("install", "upgrade", "downgrade", "replace")


class UsageError(Exception):
    """A bad argument or environment; nothing was changed."""


class SourceError(Exception):
    """This package's own files fail validation; nothing was changed."""


class InstallError(Exception):
    """A step failed; the caller rolls back."""


# ---------------------------------------------------------------- paths


def home() -> Path:
    return Path.home()


def codex_home() -> Path:
    """CODEX_HOME as Codex reads it: empty means unset, '~' is not expanded, and it must exist."""
    value = os.environ.get("CODEX_HOME", "")
    if value == "":
        return home() / ".codex"
    path = Path(value)
    if not path.is_dir():
        raise UsageError(
            f"CODEX_HOME is set to {value!r}, which is not an existing folder. Codex requires it to "
            "exist and does not expand '~'. Set CODEX_HOME to an existing absolute path, or unset it "
            f"to use {home() / '.codex'}."
        )
    return path.resolve()


def claude_config_dir() -> Path:
    value = os.environ.get("CLAUDE_CONFIG_DIR", "")
    if value == "":
        return home() / ".claude"
    path = Path(value)
    if not path.is_absolute():
        raise UsageError(f"CLAUDE_CONFIG_DIR is set to {value!r}; use an absolute path, or unset it.")
    return path


def state_dir() -> Path:
    """The per-user folder for the install ledger and backups."""
    if os.name == "nt":
        value = os.environ.get("LOCALAPPDATA", "")
        base = Path(value) if value and Path(value).is_absolute() else home() / "AppData" / "Local"
    elif sys.platform == "darwin":
        base = home() / "Library" / "Application Support"
    else:
        value = os.environ.get("XDG_STATE_HOME", "")
        base = Path(value) if value and Path(value).is_absolute() else home() / ".local" / "state"
    return base / STATE_FOLDER


def real(path: Path) -> Path:
    return Path(os.path.realpath(path))


def same_path(first: Path, second: Path) -> bool:
    return os.path.normcase(str(real(first))) == os.path.normcase(str(real(second)))


def is_within(path: Path, parent: Path) -> bool:
    """Whether path is parent or lies inside it, after resolving links."""
    child, base = os.path.normcase(str(real(path))), os.path.normcase(str(real(parent)))
    try:
        return os.path.commonpath([child, base]) == base
    except ValueError:  # different drives
        return False


def child(root: Path, name: object) -> Path | None:
    """root/name when name is a skill name that stays directly inside root; otherwise None."""
    if not isinstance(name, str) or len(name) > MAX_SKILL_NAME or not SKILL_NAME.fullmatch(name):
        return None
    path = root / name
    return path if path.parent == root else None


def named(root: Path, name: str) -> Path:
    """child() for a path this run is about to write; refuses anything else."""
    path = child(root, name)
    if path is None:
        raise InstallError(f"{name!r} is not a skill name, so nothing was written for it outside {root}")
    return path


def is_link(path: Path) -> bool:
    """A symbolic link, or on Windows a junction or another redirecting reparse point.

    The same test as build_repository_zip.py's is_link(): a reparse point
    whose tag is a name surrogate, or whose tag cannot be read, points
    somewhere else; other reparse points, such as cloud-storage placeholders,
    hold the file's own data and are ordinary files.
    """
    try:
        info = os.lstat(path)
    except OSError:
        return False
    if stat.S_ISLNK(info.st_mode):
        return True
    if getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        tag = getattr(info, "st_reparse_tag", 0)
        return tag == 0 or bool(tag & NAME_SURROGATE_TAG)
    isjunction = getattr(os.path, "isjunction", None)
    return bool(isjunction is not None and isjunction(path))


def raise_error(error: OSError) -> None:
    """os.walk's onerror: an unreadable folder stops the walk instead of being skipped."""
    raise error


def links_inside(root: Path) -> list[str]:
    found = []
    for directory, folders, files in os.walk(root, onerror=raise_error):
        for name in sorted(folders + files):
            if is_link(Path(directory) / name):
                found.append((Path(directory) / name).relative_to(root).as_posix())
        folders[:] = [name for name in folders if not is_link(Path(directory) / name)]
    return found


def is_debris(name: str) -> bool:
    return name in DEBRIS_FILES or name.endswith(DEBRIS_SUFFIXES)


def tree_files(root: Path, include_debris: bool = False) -> list[tuple[str, Path]]:
    """Every file under root, by relative path; an unreadable folder raises, so no digest or copy omits it."""
    files = []
    for directory, folders, names in os.walk(root, onerror=raise_error):
        if not include_debris:
            folders[:] = [name for name in folders if name not in DEBRIS_DIRS]
        relative = Path(directory).relative_to(root)
        for name in names:
            if include_debris or not is_debris(name):
                files.append(((relative / name).as_posix(), Path(directory) / name))
    return sorted(files)


def tree_digest(root: Path, include_debris: bool = False) -> str:
    """SHA-256 over each file's relative path and content hash, in path order."""
    digest = hashlib.sha256()
    for relative, path in tree_files(root, include_debris):
        digest.update(relative.encode("utf-8") + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).hexdigest().encode("ascii") + b"\n")
    return "sha256:" + digest.hexdigest()


def copy_tree(source: Path, destination: Path, include_debris: bool) -> None:
    destination.mkdir()
    for relative, path in tree_files(source, include_debris):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        if os.name != "nt":
            shutil.copymode(path, target)


def is_folder(path: str | Path) -> bool:
    try:
        return stat.S_ISDIR(os.lstat(path).st_mode)
    except OSError:
        return False


def open_folders(folder: str | Path) -> None:
    """Give each folder in a tree owner read, write, and search permission, top down, never following a link."""
    os.chmod(folder, stat.S_IRWXU)
    with os.scandir(folder) as entries:
        inner = [entry.path for entry in entries if entry.is_dir(follow_symlinks=False)]
    for path in inner:
        open_folders(path)


def remove_tree(path: Path) -> None:
    """Remove a tree this installer created or moved aside: a stage, or an unused backup copy.

    On POSIX every folder first gets owner read, write, and search
    permission, so a copy holding an unreadable or read-only folder is
    removed too; a folder never loses its search (execute) bit. Read-only
    files become writable. Links are removed, never followed.
    """

    def make_writable(function, name, *_):
        parent = os.path.dirname(name)
        if os.name != "nt" and parent and is_folder(parent):
            os.chmod(parent, stat.S_IRWXU)
        if not os.path.islink(name):
            os.chmod(name, stat.S_IRWXU if is_folder(name) else stat.S_IREAD | stat.S_IWRITE)
        function(name)

    if os.name != "nt" and is_folder(path):
        open_folders(path)
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=make_writable)  # novermin: 3.12 renamed onerror, which now warns
    else:
        shutil.rmtree(path, onerror=make_writable)


def write_atomic(path: Path, text: str) -> None:
    temporary = path.with_name(f"{path.name}.tmp-{secrets.token_hex(4)}")
    try:
        with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def access_hint(error: object) -> str | None:
    """A hint for Windows' Access is denied (WinError 5), which open files usually cause."""
    if getattr(error, "winerror", None) == 5 or "[WinError 5]" in str(error):
        return (
            "Windows denied access (WinError 5). An agent host, an editor, or another program may be holding "
            "files in that folder open; close it, then run this command again."
        )
    return None


def now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------ the lock


def lock_exclusively(handle) -> bool:
    """Take an exclusive lock on handle's file without waiting; False when another process holds it."""
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as error:
            if error.errno in (errno.EACCES, getattr(errno, "EDEADLOCK", errno.EDEADLK)):
                return False
            raise
        return True
    import fcntl

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return False
    return True


def unlock(handle) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class StateLock:
    """An exclusive OS lock on the state folder, held for a whole install or uninstall, recovery included.

    The lock alone decides whether another run is active: a run that holds
    it knows no other run on this machine is changing anything, so it may
    recover a journal it finds. The lock file stays in place between runs;
    the operating system releases the lock when the process ends, however it
    ends.
    """

    def __init__(self, state: Path) -> None:
        self.path = state / LOCK_NAME
        self.handle = None

    def __enter__(self) -> "StateLock":
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            handle = open(self.path, "a+b")
        except OSError as error:
            variable = "LOCALAPPDATA" if os.name == "nt" else None if sys.platform == "darwin" else "XDG_STATE_HOME"
            raise UsageError(
                f"cannot open the lock file {self.path} ({error}), so nothing was changed. Make "
                f"{self.path.parent} a folder you can write to"
                + (f", or set {variable} to another absolute path" if variable else "")
                + ", then run this command again."
            ) from error
        try:
            locked = lock_exclusively(handle)
        except BaseException:
            handle.close()
            raise
        if not locked:
            handle.close()
            raise UsageError(
                f"another install.py run is using {self.path.parent} (it holds {self.path}), so nothing was "
                "changed. Wait for that run to finish, then run this command again."
            )
        self.handle = handle
        return self

    def __exit__(self, *details) -> None:
        try:
            unlock(self.handle)
        except OSError:
            pass
        finally:
            self.handle.close()


def lock_held(state: Path) -> bool:
    """Whether another run holds the state lock now; status tests it without waiting or creating anything."""
    try:
        with open(state / LOCK_NAME, "rb") as handle:
            if not lock_exclusively(handle):
                return True
            unlock(handle)
    except OSError:
        pass
    return False


# --------------------------------------------------------------- source


@dataclass
class SourceSkill:
    name: str
    path: Path
    digest: str
    scripts: list[str]


@dataclass
class Source:
    version: str
    skills: list[SourceSkill]
    commit: str | None


def load_schema():
    existing = sys.modules.get("skill_frontmatter")
    if existing is not None and Path(getattr(existing, "__file__", "")) == SCHEMA_MODULE:
        return existing
    if not SCHEMA_MODULE.is_file():
        raise SourceError(f"{SCHEMA_MODULE} is missing; download or clone the whole repository.")
    spec = importlib.util.spec_from_file_location("skill_frontmatter", SCHEMA_MODULE)
    if spec is None or spec.loader is None:
        raise SourceError(f"cannot load {SCHEMA_MODULE}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def validation_problems(schema, path: Path, name: str) -> list[str]:
    report = schema.validate_skill_dir(path, level="portable")
    return [f"{name}: {item.code}: {item.message}" for item in report.findings if item.severity == "error"]


def source_commit() -> str | None:
    if not (PACKAGE_ROOT / ".git").exists():
        return None
    try:
        completed = subprocess.run(
            ["git", "-C", str(PACKAGE_ROOT), "rev-parse", "--verify", "HEAD"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
            env=dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0"),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = completed.stdout.strip()
    return value if completed.returncode == 0 and re.fullmatch(r"[0-9a-f]{40,64}", value) else None


def load_source() -> Source:
    """Read VERSION and every skill, refusing links and invalid frontmatter."""
    try:
        version = VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise SourceError(f"cannot read {VERSION_FILE}: {error}") from error
    if not VERSION_PATTERN.match(version):
        raise SourceError(f"{VERSION_FILE} must hold one version such as 1.1.0, not {version!r}.")
    if not SKILLS_SOURCE.is_dir() or is_link(SKILLS_SOURCE):
        raise SourceError(f"{SKILLS_SOURCE} is missing or is a link.")
    schema = load_schema()
    problems, skills = [], []
    for entry in sorted(SKILLS_SOURCE.iterdir()):
        if entry.name.startswith("."):
            continue
        if is_link(entry):
            problems.append(f"{entry.name}: the skill folder is a link; this installer copies only real folders.")
            continue
        if not entry.is_dir():
            continue
        links = links_inside(entry)
        if links:
            problems.append(f"{entry.name}: holds a link ({links[0]}); this installer copies only real files.")
            continue
        found = validation_problems(schema, entry, entry.name)
        if found:
            problems.extend(found)
            continue
        scripts = [f"{entry.name}/{relative}" for relative, _ in tree_files(entry) if relative.startswith("scripts/")]
        skills.append(SourceSkill(entry.name, entry, tree_digest(entry), scripts))
    if problems:
        raise SourceError("this package's skills failed validation:\n  " + "\n  ".join(problems))
    if not skills:
        raise SourceError(f"{SKILLS_SOURCE} holds no skills.")
    return Source(version, skills, source_commit())


def parse_version(text: object) -> tuple[int, int, int] | None:
    match = VERSION_PATTERN.match(text) if isinstance(text, str) else None
    return tuple(int(part) for part in match.groups()) if match else None


# --------------------------------------------------------------- target


@dataclass
class Target:
    name: str
    host: str | None
    root: Path
    project: Path | None = None


def user_path(text: str) -> Path:
    return Path(os.path.expanduser(text)).absolute()


def resolve_target(name: str | None, project: str | None, dest: str | None) -> Target:
    if dest is not None:
        if name is not None or project is not None:
            raise UsageError("use --dest on its own, without --target or --project.")
        return Target("dest", None, user_path(dest))
    name = name or "codex"
    if name in PROJECT_TARGETS:
        if project is None:
            raise UsageError(f"--target {name} needs --project DIR, the project's folder.")
        folder = user_path(project)
        if not folder.is_dir():
            raise UsageError(f"--project {project!r} is not an existing folder.")
        folder = folder.resolve()
        hidden = ".agents" if name == "codex-project" else ".claude"
        return Target(name, name.split("-")[0], folder / hidden / "skills", folder)
    if project is not None:
        raise UsageError("--project works only with --target codex-project or claude-project.")
    if name == "codex":
        return Target(name, "codex", home() / ".agents" / "skills")
    if name == "codex-legacy":
        return Target(name, "codex", codex_home() / "skills")
    return Target(name, "claude", claude_config_dir() / "skills")


def other_roots(target: Target) -> list[tuple[str, Path]]:
    """Other folders the same host loads skills from."""
    roots: list[tuple[str, Path]] = []
    if target.host == "codex":
        roots.append(("codex", home() / ".agents" / "skills"))
        try:
            roots.append(("codex-legacy", codex_home() / "skills"))
        except UsageError:
            pass
        if os.name != "nt":
            roots.append(("codex-system", Path("/etc/codex/skills")))
        if target.project is not None:
            roots.append(("codex-project", target.project / ".agents" / "skills"))
    elif target.host == "claude":
        try:
            roots.append(("claude", claude_config_dir() / "skills"))
        except UsageError:
            pass
        if target.project is not None:
            roots.append(("claude-project", target.project / ".claude" / "skills"))
    unique: list[tuple[str, Path]] = []
    for label, root in roots:
        if not same_path(root, target.root) and not any(same_path(root, seen) for _, seen in unique):
            unique.append((label, root))
    return unique


def frontmatter_name(folder: Path, schema) -> str | None:
    """The name a host gives the skill in folder: its frontmatter name, or else the folder's name."""
    try:
        data = (folder / "SKILL.md").read_bytes()
    except OSError:
        return None
    name = schema.validate_text(data, folder=folder.name, level="portable").frontmatter.get("name")
    return name.strip() if isinstance(name, str) and name.strip() else folder.name


def codex_skills(root: Path, schema) -> list[tuple[str, Path]]:
    """(name, folder) for each skill Codex would load from root."""
    found: list[tuple[str, Path]] = []
    if not root.is_dir():
        return found
    for count, (directory, folders, files) in enumerate(os.walk(root, followlinks=True)):
        here = Path(directory)
        if count >= CODEX_SCAN_FOLDERS:
            break
        depth = len(here.relative_to(root).parts)
        visible = [name for name in folders if not name.startswith(".") and name not in DEBRIS_DIRS]
        folders[:] = sorted(visible) if depth + 1 < CODEX_SCAN_DEPTH else []
        if here != root and "SKILL.md" in files:
            name = frontmatter_name(here, schema)
            if name is not None:
                found.append((name, here))
    return found


def duplicate_copies(target: Target, source: Source) -> list[tuple[str, str, Path]]:
    """(skill, label, folder) for each other copy the target's host would load under a suite skill's name.

    A folder with the skill's name in another root counts for every host.
    For Codex, so does any skill whose frontmatter name matches, anywhere
    Codex looks in those roots or in the target itself.
    """
    names = [skill.name for skill in source.skills]
    roots = other_roots(target)
    found = [(name, label, root / name) for label, root in roots for name in names if os.path.lexists(root / name)]
    if target.host == "codex":
        schema = load_schema()
        for label, root in [(target.name, target.root), *roots]:
            for name, folder in codex_skills(root, schema):
                if name not in names or same_path(folder, target.root / name):
                    continue
                if not any(name == seen and same_path(folder, path) for seen, _, path in found):
                    found.append((name, label, folder))
    return found


def check_locations(target: Target, state: Path) -> None:
    if os.path.lexists(target.root) and not target.root.is_dir():
        raise UsageError(f"the destination {target.root} exists and is not a folder.")
    if is_within(target.root, PACKAGE_ROOT) or is_within(PACKAGE_ROOT, target.root):
        raise UsageError(
            f"the destination {target.root} overlaps this package at {PACKAGE_ROOT}; choose a folder outside it."
        )
    if is_within(target.root, state) or is_within(state, target.root):
        raise UsageError(f"the destination {target.root} overlaps the installer's state folder {state}.")
    for _, root in [("target", target.root)] + other_roots(target):
        if is_within(state, root):
            raise UsageError(
                f"the backup folder {state} would sit inside the skills folder {root}; "
                "point LOCALAPPDATA or XDG_STATE_HOME elsewhere."
            )


# --------------------------------------------------------------- ledger


def root_key(root: Path) -> str:
    return os.path.normcase(str(real(root)))


LEDGER_ASIDE = (
    "Move it aside to continue; the installed skills then count as unrecorded, so replacing them needs "
    "--replace-modified."
)


def read_ledger(path: Path) -> dict:
    """The install ledger, or an empty one when there is none. Any other shape is an error that names the file."""
    if not path.exists():
        return {"schema": LEDGER_SCHEMA, "roots": {}}
    try:
        ledger = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, RecursionError) as error:
        raise UsageError(f"cannot read the install ledger {path}: {error}. {LEDGER_ASIDE}") from error
    roots = ledger.get("roots") if isinstance(ledger, dict) else None
    if not isinstance(roots, dict) or not all(
        isinstance(entry, dict)
        and isinstance(entry.get("skills", {}), dict)
        and all(isinstance(record, dict) for record in entry.get("skills", {}).values())
        for entry in roots.values()
    ):
        raise UsageError(f"the install ledger {path} has an unknown shape. {LEDGER_ASIDE}")
    return ledger


def ledger_skills(ledger: dict, root: Path) -> dict:
    return ledger["roots"].get(root_key(root), {}).get("skills", {})


def recorded(ledger: dict, root: Path) -> dict[str, dict]:
    """The ledger's records for root whose names are skill names; nothing else becomes a path."""
    return {name: value for name, value in ledger_skills(ledger, root).items() if child(root, name) is not None}


def ignored_records(ledger: dict, root: Path) -> list[str]:
    """A warning for ledger records whose names are not skill names, if there are any."""
    names = sorted(repr(name) for name in ledger_skills(ledger, root) if child(root, name) is None)
    if not names:
        return []
    return [f"the install record for {root} lists {', '.join(names)}, which are not skill names; ignored them."]


# ----------------------------------------------------------------- plan


@dataclass
class Item:
    skill: str
    state: str
    action: str
    path: Path
    reason: str
    installed_version: str | None = None
    digest: str | None = None
    override: str | None = None
    other_path: Path | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "skill": self.skill,
            "state": self.state,
            "action": self.action,
            "path": str(self.path),
            "reason": self.reason,
            "installed_version": self.installed_version,
            "override": self.override,
            "other_path": str(self.other_path) if self.other_path else None,
        }


@dataclass
class Plan:
    command: str
    target: Target
    state: Path
    source: Source
    items: list[Item] = field(default_factory=list)
    retired: list[Item] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def refused(self) -> list[Item]:
        return [item for item in self.items + self.retired if item.action == "refuse"]

    @property
    def changes(self) -> list[Item]:
        return [item for item in self.items if item.action in CHANGES + ("remove",)]

    @property
    def moves(self) -> list[Item]:
        return [item for item in self.retired if item.action == "retire"]


def inspect_copy(name: str, path: Path, record: dict | None, digest: str | None, version: str | None) -> Item:
    """What sits at path, compared with the source digest and the ledger record."""
    installed = record.get("version") if record else None
    if not os.path.lexists(path):
        return Item(name, "absent", "", path, "not installed")
    if is_link(path) or not path.is_dir():
        return Item(name, "link", "", path, "is a link or a file, which this installer never touches")
    try:
        links = links_inside(path)
        current = tree_digest(path)
    except OSError as error:
        return Item(name, "unreadable", "", path, f"cannot be read ({error}); fix its permissions first")
    if links:
        return Item(name, "link", "", path, f"holds a link ({links[0]}), which this installer never touches")
    item = Item(name, "", "", path, "", installed, current)
    if digest is not None and current == digest:
        item.state, item.reason = "current", f"identical to {version}"
    elif record is None or parse_version(installed) is None:
        item.state, item.reason, item.installed_version = "unrecorded", "differs, and no version is recorded", None
    elif record.get("digest") != current:
        item.state, item.reason = "modified", f"changed since this installer put {installed} here"
    elif version is None:
        item.state, item.reason = "recorded", f"installed as {installed}"
    else:
        order = (parse_version(installed) > parse_version(version)) - (parse_version(installed) < parse_version(version))
        item.state = {-1: "older", 0: "same-version", 1: "newer"}[order]
        item.reason = {
            -1: f"{installed} is installed; {version} is available",
            0: f"differs from {version} under the same version",
            1: f"{installed} is installed, newer than {version}",
        }[order]
    return item


def plan_install(target: Target, state: Path, source: Source, ledger: dict, args) -> Plan:
    plan = Plan("install", target, state, source)
    records = recorded(ledger, target.root)
    plan.warnings.extend(ignored_records(ledger, target.root))
    duplicates = duplicate_copies(target, source)
    legacy = dict(other_roots(target)).get("codex-legacy")
    legacy_records = recorded(ledger, legacy) if legacy is not None else {}
    unrecorded_legacy = False
    for skill in source.skills:
        item = inspect_copy(skill.name, target.root / skill.name, records.get(skill.name), skill.digest, source.version)
        if item.state == "absent":
            item.action, item.reason = "install", f"new: {source.version}"
        elif item.state == "current":
            item.action = "skip"
        elif item.state == "older":
            item.action = "upgrade"
        elif item.state == "newer":
            item.action, item.override = ("downgrade", None) if args.allow_downgrade else ("refuse", "--allow-downgrade")
        elif item.state in ("unrecorded", "modified", "same-version"):
            item.action, item.override = ("replace", None) if args.replace_modified else ("refuse", "--replace-modified")
        else:
            item.action = "refuse"
        for name, label, other in duplicates:
            if name != skill.name:
                continue
            if item.action in CHANGES and not args.allow_duplicate_names:
                item.action, item.override, item.other_path = "refuse", "--allow-duplicate-names", other
                item.reason = f"{item.path} would share its name with {other} ({label}); the same host loads both"
                if legacy is not None and same_path(other, legacy / name) and name not in legacy_records:
                    unrecorded_legacy = True
            elif item.action in CHANGES + ("skip",):
                plan.warnings.append(f"{skill.name} is also in {other} ({label}); the host loads both.")
            break
        plan.items.append(item)
    if unrecorded_legacy:
        plan.warnings.append(
            f"the copies in {legacy} have no install record, as version 1.0 installed them. To move to "
            f"{target.root}, run 'python install.py uninstall --target codex-legacy --include-modified', then "
            "this command again; to keep the old folder instead, run 'python install.py install --target "
            "codex-legacy --replace-modified'. The README's \"Upgrading from 1.0.x\" explains both."
        )
    if target.host is None:
        plan.warnings.append("--dest skips the check for same-name skills in other folders.")
    plan.retired = plan_retired(target, args)
    return plan


def plan_retired(target: Target, args) -> list[Item]:
    items = []
    for name in RETIRED:
        item = inspect_copy(name, target.root / name, None, None, None)
        if item.state == "absent":
            continue
        if item.state in ("link", "unreadable"):
            item.action = "keep"
        elif args.keep_retired:
            item.action, item.reason = "keep", "retired in 1.1.0; kept because of --keep-retired"
        else:
            item.action, item.reason = "retire", "retired in 1.1.0; offered for a move to backups"
        items.append(item)
    return items


def plan_uninstall(target: Target, state: Path, source: Source, ledger: dict, args) -> Plan:
    plan = Plan("uninstall", target, state, source)
    records = recorded(ledger, target.root)
    plan.warnings.extend(ignored_records(ledger, target.root))
    digests = {skill.name: skill.digest for skill in source.skills}
    # A retired skill is planned only once, as a retired skill, even if the ledger records it.
    for name in sorted((set(digests) | set(records)) - set(RETIRED)):
        item = inspect_copy(name, target.root / name, records.get(name), digests.get(name), source.version)
        if item.state == "absent":
            continue
        if item.state in ("link", "unreadable"):
            item.action = "refuse"
        elif item.state in ("unrecorded", "modified") and not args.include_modified:
            item.action, item.override = "refuse", "--include-modified"
        else:
            item.action = "remove"
        plan.items.append(item)
    plan.retired = plan_retired(target, args)
    return plan


# ---------------------------------------------------------------- output


class Reporter:
    def __init__(self, as_json: bool) -> None:
        self.stream = sys.stderr if as_json else sys.stdout

    def say(self, text: str = "") -> None:
        print(text, file=self.stream, flush=True)


LABELS = {
    "install": "install",
    "skip": "skip",
    "upgrade": "upgrade",
    "downgrade": "downgrade",
    "replace": "replace",
    "remove": "move to backups",
    "retire": "move to backups",
    "keep": "leave",
    "refuse": "REFUSED",
}


def show_plan(plan: Plan, out: Reporter) -> None:
    target = plan.target
    out.say(f"Skills Folder {plan.source.version}: {plan.command} for {target.name}")
    out.say(f"  Skills folder: {target.root}{'' if target.root.exists() else ' (will be created)'}")
    out.say(f"  Source:        {PACKAGE_ROOT}" + (f" (commit {plan.source.commit[:12]})" if plan.source.commit else ""))
    out.say(f"  Backups:       {plan.state / 'backups'}")
    out.say()
    for item in plan.items:
        out.say(f"  {LABELS[item.action]:<16} {item.skill:<26} {item.reason}")
        if item.override:
            out.say(f"  {'':<16} {'':<26} to proceed anyway, add {item.override}")
    if plan.retired:
        out.say()
        out.say("  Skills that 1.0.x installed and 1.1.0 retired:")
        for item in plan.retired:
            out.say(f"  {LABELS[item.action]:<16} {item.skill:<26} {item.reason}")
    for warning in plan.warnings:
        out.say(f"  Note: {warning}")
    if plan.command == "install" and plan.changes:
        scripts = [script for skill in plan.source.skills for script in skill.scripts]
        if scripts:
            out.say()
            out.say("  These skills bundle Python scripts, which run only when an agent runs them:")
            for script in scripts:
                out.say(f"    {script}")
    out.say()


def ask(question: str, args, out: Reporter) -> bool:
    if args.yes:
        return True
    out.stream.write(f"{question} [y/N] ")
    out.stream.flush()
    answer = sys.stdin.readline() if sys.stdin is not None else ""
    return answer.strip().lower() in ("y", "yes")


# ----------------------------------------------------------- transaction


class Transaction:
    """Stage, back up, swap by rename, and record each step so any failure rolls back."""

    def __init__(self, plan: Plan) -> None:
        self.plan = plan
        self.id = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(3)
        self.journal_path = plan.state / JOURNAL_NAME
        self.ledger_path = plan.state / LEDGER_NAME
        self.journal: dict = {}
        self.rolled_back: list[str] = []
        self.committed = False

    @property
    def started(self) -> bool:
        """Whether this run's journal is on disk, so a failure from here on has steps to undo."""
        return bool(self.journal) and self.journal_path.exists()

    def save(self) -> None:
        write_atomic(self.journal_path, json.dumps(self.journal, indent=2) + "\n")

    def begin(self) -> None:
        """Create the journal, which must not exist yet.

        The state lock keeps other runs out. Exclusive creation also stops a
        second run on a file system that ignores the lock from overwriting
        this one's journal.
        """
        self.plan.state.mkdir(parents=True, exist_ok=True)
        journal = {
            "id": self.id,
            "pid": os.getpid(),
            "started": now(),
            "command": self.plan.command,
            "root": str(self.plan.target.root),
            "created": [],
            "stage": None,
            "backup": None,
            "renames": [],
            "ledger": str(self.ledger_path),
            "ledger_before": self.ledger_path.read_text(encoding="utf-8") if self.ledger_path.exists() else None,
            "ledger_written": False,
            "committed": False,
        }
        try:
            open(self.journal_path, "xb").close()
        except FileExistsError:
            raise UsageError(
                f"{self.journal_path} appeared while this run was planning, so another install.py run has begun "
                "(the state folder may be on a file system that ignores the lock). Nothing was changed. Wait for "
                "that run to finish, then run this command again."
            ) from None
        self.journal = journal
        try:
            self.save()
        except BaseException:
            self.journal = {}  # nothing began: drop the empty journal this run just created
            try:
                self.journal_path.unlink()
            except OSError:
                pass
            raise

    def rename(self, source: Path, destination: Path, digest: str | None = None) -> None:
        if os.path.lexists(destination):
            raise InstallError(f"{destination} already exists")
        step = {"from": str(source), "to": str(destination)}
        if digest is not None:
            step["digest"] = digest
        self.journal["renames"].append(step)
        self.save()
        os.rename(source, destination)

    def run(self) -> str | None:
        """Apply the plan after begin(); return the backup folder, if one was written."""
        plan, root = self.plan, self.plan.target.root
        missing = []
        for folder in [root, *root.parents]:
            if folder.exists():
                break
            missing.append(folder)
        for folder in reversed(missing):
            folder.mkdir()
            self.journal["created"].append(str(folder))
            self.save()
        stage = real(root).parent / f"{STAGE_PREFIX}{self.id}"
        self.journal["stage"] = str(stage)
        self.save()
        (stage / "new").mkdir(parents=True)
        (stage / "old").mkdir()
        sources = {skill.name: skill for skill in plan.source.skills}
        schema = load_schema()
        for item in plan.changes + plan.moves:
            if named(root, item.skill) != item.path:
                raise InstallError(f"{item.path} is not {root / item.skill}; nothing outside {root} is changed")
        for item in plan.changes:
            if item.action == "remove":
                continue
            skill = sources[item.skill]
            staged = named(stage / "new", skill.name)
            copy_tree(skill.path, staged, include_debris=False)
            if tree_digest(staged) != skill.digest:
                raise InstallError(f"the staged copy of {skill.name} differs from its source")
            problems = validation_problems(schema, staged, skill.name)
            if problems:
                raise InstallError("the staged copy failed validation: " + "; ".join(problems))
        replaced = [item for item in plan.changes if item.state != "absent"] + plan.moves
        backup = None
        if replaced:
            backup = plan.state / "backups" / f"{self.id}-{plan.command}-{plan.target.name}"
            backup.mkdir(parents=True)  # recorded only once this run has made it, so a rollback removes only its own
            self.journal["backup"] = str(backup)
            self.save()
            manifest = []
            for item in replaced:
                expected = tree_digest(item.path, include_debris=True)
                copy_tree(item.path, named(backup, item.skill), include_debris=True)
                if tree_digest(backup / item.skill, include_debris=True) != expected:
                    raise InstallError(f"the backup copy of {item.skill} does not match the original")
                manifest.append(
                    {
                        "skill": item.skill,
                        "from": str(item.path),
                        "version": item.installed_version,
                        "digest": item.digest,
                        "reason": item.action,
                    }
                )
            write_atomic(
                backup / "backup.json",
                json.dumps({"created": now(), "command": plan.command, "skills": manifest}, indent=2) + "\n",
            )
        for item in sorted(plan.changes + plan.moves, key=lambda entry: entry.skill):
            if item.state != "absent":
                self.rename(item.path, named(stage / "old", item.skill))
            if item.action in CHANGES:
                self.rename(named(stage / "new", item.skill), item.path, sources[item.skill].digest)
        self.write_ledger()
        self.journal["committed"] = True
        self.save()
        self.committed = True
        return str(backup) if backup else None

    def write_ledger(self) -> None:
        plan = self.plan
        ledger = read_ledger(self.ledger_path)
        key = root_key(plan.target.root)
        entry = ledger["roots"].setdefault(key, {})
        entry.update(path=str(plan.target.root), target=plan.target.name)
        skills = entry.setdefault("skills", {})
        apply_records(skills, plan)
        if not skills:
            del ledger["roots"][key]
        ledger["schema"] = LEDGER_SCHEMA
        self.journal["ledger_written"] = True
        self.save()
        write_atomic(self.ledger_path, json.dumps(ledger, indent=2, sort_keys=True) + "\n")

    def finish(self) -> str | None:
        return finish_committed(self.journal, self.journal_path)

    def rollback(self) -> list[str]:
        """Undo every recorded step, this run's backup included; return the problems that kept it from finishing."""
        return undo(self.journal, self.journal_path, self.rolled_back, own_backup=True)


def finish_committed(journal: dict, journal_path: Path) -> str | None:
    """After a commit: drop the stage, whose old copies the backup holds, then the journal. Never rolls back."""
    stage = journal.get("stage")
    try:
        if stage and os.path.lexists(stage):
            remove_tree(Path(stage))
        journal_path.unlink()
    except OSError as error:
        hint = access_hint(error)
        return f"the change is complete, but the cleanup stopped ({error}); the next run finishes it." + (
            f" {hint}" if hint else ""
        )
    return None


def apply_records(skills: dict, plan: Plan) -> None:
    sources = {skill.name: skill for skill in plan.source.skills}
    for item in plan.items:
        known = skills.get(item.skill)
        if (
            item.action == "skip"
            and isinstance(known, dict)
            and known.get("digest") == sources[item.skill].digest
            and known.get("version") == plan.source.version
        ):
            continue
        if item.action in CHANGES or item.action == "skip":
            skills[item.skill] = {
                "version": plan.source.version,
                "digest": sources[item.skill].digest,
                "installed_at": now(),
                "source_commit": plan.source.commit,
            }
        elif item.action == "remove":
            skills.pop(item.skill, None)


def same_text(first: object, second: Path) -> bool:
    """Whether a journal value names second, compared as text since either may be missing."""
    if not isinstance(first, str):
        return False
    return os.path.normcase(os.path.normpath(first)) == os.path.normcase(os.path.normpath(str(second)))


def journal_problems(journal: dict, state: Path) -> list[str]:
    """Each journal path that is not one its run writes: the skills folder, the stage, the backup, the ledger."""
    run_id, root_text = journal.get("id"), journal.get("root")
    if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
        return [f"its run id {run_id!r} is not one this installer writes"]
    if not isinstance(root_text, str) or not Path(root_text).is_absolute():
        return [f"its skills folder {root_text!r} is not an absolute path"]
    root = Path(root_text)
    problems = []
    stage = real(root).parent / f"{STAGE_PREFIX}{run_id}"
    if journal.get("stage") is not None and not same_text(journal.get("stage"), stage):
        problems.append(f"its stage {journal.get('stage')!r} is not {stage}")
    backup = journal.get("backup")
    if backup is not None and not (
        isinstance(backup, str)
        and same_text(str(Path(backup).parent), state / "backups")
        and Path(backup).name.startswith(f"{run_id}-")
    ):
        problems.append(f"its backup {backup!r} is not a folder in {state / 'backups'} named for the run")
    if not same_text(journal.get("ledger"), state / LEDGER_NAME):
        problems.append(f"its ledger {journal.get('ledger')!r} is not {state / LEDGER_NAME}")
    if not isinstance(journal.get("ledger_before"), (str, type(None))):
        problems.append("its copy of the earlier ledger is not text")
    for flag in ("ledger_written", "committed"):
        if not isinstance(journal.get(flag), bool):
            problems.append(f"its {flag} flag is {journal.get(flag)!r}, not true or false")
    created, renames = journal.get("created", []), journal.get("renames")
    if not isinstance(created, list) or not isinstance(renames, list):
        problems.append("its lists of created folders and moves are not lists")
        return problems
    for folder in created:
        if not any(same_text(folder, parent) for parent in (root, *root.parents)):
            problems.append(f"it lists {folder!r} as a folder it created, which is neither {root} nor above it")
    for step in renames:
        source = step.get("from") if isinstance(step, dict) else None
        destination = step.get("to") if isinstance(step, dict) else None
        name = Path(destination).name if isinstance(destination, str) else None
        inside = child(root, name)
        digest = step.get("digest") if isinstance(step, dict) else None
        outward = inside is not None and same_text(source, inside) and same_text(destination, stage / "old" / name)
        inward = inside is not None and same_text(source, stage / "new" / name) and same_text(destination, inside)
        if not (outward or inward):
            problems.append(f"it records a move from {source!r} to {destination!r}, outside {root} and its stage")
        elif inward and not (isinstance(digest, str) and DIGEST.fullmatch(digest)):
            problems.append(f"its move of a new copy into {destination!r} records no digest to check it by")
    return problems


def undo(journal: dict, journal_path: Path, log: list[str], own_backup: bool = False) -> list[str]:
    """Reverse a run's recorded steps; return the problems that kept it from finishing.

    Every skill moves back first. Only when all of them have does the ledger
    get its earlier text back and the journal get saved with nothing left to
    undo, before any cleanup, so a later run never undoes a move twice; it
    only finishes the cleanup. A backup is removed only with own_backup, by
    the run that just wrote it. A recovery keeps it and says where it is,
    since a journal found on disk may be stale.
    """
    problems = journal_problems(journal, journal_path.parent)
    if problems:
        return [f"nothing was rolled back, because {problem}" for problem in problems]
    for step in reversed(journal["renames"]):
        source, destination, digest = Path(step["from"]), Path(step["to"]), step.get("digest")
        if not os.path.lexists(destination):
            if digest is None and not os.path.lexists(source):
                problems.append(f"{source} is missing, and so is {destination}, where this run moved it")
            continue  # the move never happened or is already undone, or the new copy is gone
        if os.path.lexists(source):
            if digest is None:
                problems.append(f"kept {destination}, because {source} is in its way")
            continue
        if digest is not None:
            try:
                changed = tree_digest(destination) != digest
            except OSError:
                changed = True
            if changed:
                problems.append(f"left {destination} in place, because it changed after this run put it there")
                continue
        try:
            os.rename(destination, source)
            log.append(f"restored {source}" if digest is None else f"took out {destination}, which this run put there")
        except OSError as error:
            problems.append(f"could not move {destination} back to {source}: {error}")
    if not problems and (journal["renames"] or journal["ledger_written"]):
        ledger, before = Path(journal["ledger"]), journal.get("ledger_before")
        try:
            if journal["ledger_written"]:
                current = ledger.read_text(encoding="utf-8", errors="replace") if ledger.exists() else None
                if current != before:
                    if before is None:
                        ledger.unlink()
                    else:
                        write_atomic(ledger, before)
                    log.append(f"restored {ledger}")
            journal.update(renames=[], ledger_written=False, committed=False)
            write_atomic(journal_path, json.dumps(journal, indent=2) + "\n")
        except OSError as error:
            problems.append(f"could not restore {ledger} and record the rollback in {journal_path}: {error}")
    stage = journal.get("stage")
    if not problems and stage and os.path.lexists(stage):
        old = Path(stage) / "old"
        try:
            if old.is_dir() and any(old.iterdir()):
                problems.append(f"kept {stage}, which still holds skills that could not be moved back")
            else:
                remove_tree(Path(stage))
        except OSError as error:
            problems.append(f"could not remove {stage}: {error}")
    if not problems:
        for folder in reversed(journal.get("created", [])):
            try:
                Path(folder).rmdir()
                log.append(f"removed the empty folder {folder}, which this run created")
            except OSError:
                pass
    backup = journal.get("backup")
    if backup and os.path.lexists(backup):
        if own_backup and not problems:
            try:
                remove_tree(Path(backup))
            except OSError as error:
                log.append(f"could not remove the unused backup {backup} ({error}); you may delete it")
        else:
            log.append(f"kept the backup {backup}")
    if not problems:
        try:
            journal_path.unlink()
        except OSError as error:
            problems.append(f"could not delete {journal_path} ({error}); the next run finishes the cleanup")
    return problems


# ------------------------------------------------------------- commands


def result_payload(plan: Plan | None, target: Target | None, state: Path | None, **extra) -> dict:
    payload: dict[str, object] = {
        "installer_version": plan.source.version if plan else None,
        "command": plan.command if plan else None,
        "target": target.name if target else None,
        "destination": str(target.root) if target else None,
        "state_dir": str(state) if state else None,
        "ledger": str(state / LEDGER_NAME) if state else None,
        "source": str(PACKAGE_ROOT),
        "source_commit": plan.source.commit if plan else None,
        "plan": [item.as_dict() for item in plan.items] if plan else [],
        "retired": [item.as_dict() for item in plan.retired] if plan else [],
        "warnings": plan.warnings if plan else [],
    }
    payload.update(extra)
    return payload


def recover(state: Path, args, out: Reporter) -> tuple[int, dict]:
    """Finish or roll back the run that a journal found at startup records. It never deletes a backup."""
    journal_path = state / JOURNAL_NAME
    try:
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        if not isinstance(journal, dict) or not isinstance(journal.get("renames"), list) or "ledger" not in journal:
            raise ValueError("unknown shape")
    except (OSError, UnicodeDecodeError, ValueError, RecursionError) as error:
        raise UsageError(
            f"{journal_path} records an interrupted run but cannot be read ({error}). Check the skills folder "
            "and the backups by hand, then move the journal aside."
        ) from error
    problems = journal_problems(journal, state)
    if problems:
        raise UsageError(
            f"{journal_path} records an interrupted run, but {'; '.join(problems)}. A journal names only that "
            "run's skills folder, stage, backup, and ledger, so this one was not acted on and nothing was "
            "changed. Check the skills folder and the backups by hand, then move the journal aside."
        )
    committed = journal["committed"] is True
    out.say(f"A previous run ({journal.get('command')} into {journal.get('root')}) did not finish: {journal_path}")
    if committed:
        out.say("  It will be finished (its changes are complete).")
    elif journal["renames"] or journal["ledger_written"]:
        out.say("  Its changes will be rolled back.")
    else:
        out.say("  Every skill is already in place; only its cleanup is left.")
    if not ask("Recover it now?", args, out):
        out.say("Not recovered, and nothing was changed. The next install or uninstall offers this again.")
        return EXIT_CANCELLED, {"result": "cancelled", "journal": str(journal_path)}
    log: list[str] = []
    try:
        if committed:
            problem = finish_committed(journal, journal_path)
            problems = [problem] if problem else []
        else:
            problems = undo(journal, journal_path, log)
    except KeyboardInterrupt:
        for line in log:
            out.say(f"  {line}")
        out.say(
            "Interrupted. The earlier run's changes are complete; run this command again to finish its cleanup."
            if committed
            else "Interrupted, so the rollback is not finished. Run this command again to roll back the rest."
        )
        return EXIT_FAILED, {"result": "interrupted", "committed": bool(committed), "rolled_back": log, "errors": []}
    for line in log:
        out.say(f"  {line}")
    for problem in problems:
        out.say(f"  PROBLEM: {problem}")
    hint = next(filter(None, map(access_hint, problems)), None)
    if hint:
        out.say(f"  {hint}")
    out.say(
        "Recovered. Nothing else was done; run the command again."
        if not problems
        else "Recovery is incomplete. Fix the problems above, then run this command again."
    )
    return EXIT_FAILED, {"result": "recovered" if not problems else "failed", "rolled_back": log, "errors": problems}


def run_change(command: str, args, out: Reporter) -> tuple[int, dict]:
    source = load_source()
    target = resolve_target(args.target, args.project, args.dest)
    state = state_dir()
    check_locations(target, state)
    with StateLock(state):
        return change_locked(command, args, out, source, target, state)


def change_locked(command: str, args, out: Reporter, source: Source, target: Target, state: Path) -> tuple[int, dict]:
    """Plan and apply one change while this process holds the state lock."""
    if (state / JOURNAL_NAME).exists():
        code, extra = recover(state, args, out)
        return code, result_payload(None, target, state, **extra)
    ledger = read_ledger(state / LEDGER_NAME)
    planner = plan_install if command == "install" else plan_uninstall
    plan = planner(target, state, source, ledger, args)
    show_plan(plan, out)

    def finish(code: int, result: str, **extra) -> tuple[int, dict]:
        return code, result_payload(plan, target, state, result=result, exit_code=code, **extra)

    if plan.refused:
        out.say(f"Refused: {len(plan.refused)} item(s) above need attention. Nothing was changed.")
        return finish(EXIT_REFUSED, "refused")
    if plan.changes and not ask(f"Apply these {len(plan.changes)} change(s)?", args, out):
        out.say("Cancelled. Nothing was changed.")
        return finish(EXIT_CANCELLED, "cancelled")
    if plan.moves and not ask(f"Also move the {len(plan.moves)} retired skill(s) to backups?", args, out):
        for item in plan.moves:
            item.action, item.reason = "keep", "retired in 1.1.0; you chose to leave it"
        if not plan.changes:
            out.say("Nothing was changed.")
            return finish(EXIT_CANCELLED, "cancelled")
    if not plan.changes and not plan.moves:
        if command == "install" and any(item.action == "skip" for item in plan.items):
            record_skips(plan)
        out.say("Nothing to do: every skill is already in place." if command == "install" else "Nothing to uninstall.")
        return finish(EXIT_OK, "nothing-to-do")
    transaction = Transaction(plan)
    try:
        transaction.begin()
        transaction.run()
    except BaseException as error:  # noqa: BLE001 - every failure, including Ctrl+C, rolls back
        if not transaction.started:
            raise  # nothing changed: a usage error, or Ctrl+C before the journal, which main reports
        if not transaction.committed:
            return roll_back(transaction, error, out, finish)
    backup = transaction.journal.get("backup")
    try:
        cleanup = transaction.finish()
    except KeyboardInterrupt:
        out.say("Interrupted during the cleanup. Done: every change was applied; the next run finishes the cleanup.")
        return finish(
            EXIT_FAILED, "interrupted", committed=True, backup=backup, stage=transaction.journal.get("stage")
        )
    if cleanup:
        plan.warnings.append(cleanup)
        out.say(f"Note: {cleanup}")
    done = len(plan.changes) + len(plan.moves)
    out.say(f"Done: {done} change(s) applied." + (f" Backups: {backup}" if backup else ""))
    if command == "install":
        out.say("Start a new agent session, then check the list with /skills.")
    return finish(EXIT_OK, "done", backup=backup, stage=transaction.journal.get("stage"))


def roll_back(transaction: Transaction, error: BaseException, out: Reporter, finish) -> tuple[int, dict]:
    """Undo a run that failed or was interrupted before its commit, and report the outcome."""
    interrupted = isinstance(error, KeyboardInterrupt)
    stage = transaction.journal.get("stage")
    out.say("Interrupted (Ctrl+C); rolling back." if interrupted else f"Failed: {error}")
    try:
        problems = transaction.rollback()
    except KeyboardInterrupt:
        out.say("Interrupted, so the rollback is not finished. Run this command again to roll back the rest.")
        return finish(
            EXIT_FAILED, "interrupted", committed=False, error="interrupted" if interrupted else str(error),
            rolled_back=transaction.rolled_back, errors=[], stage=stage,
        )
    for line in transaction.rolled_back:
        out.say(f"  {line}")
    for problem in problems:
        out.say(f"  PROBLEM: {problem}")
    hint = next(filter(None, map(access_hint, [error, *problems])), None)
    if hint:
        out.say(f"  {hint}")
    out.say(
        "Every change was rolled back."
        if not problems
        else "The rollback is incomplete. Fix the problems above, then run this command again."
    )
    return finish(
        EXIT_FAILED, "failed", error="interrupted" if interrupted else str(error), rolled_back=transaction.rolled_back,
        errors=problems, stage=stage,
    )


def record_skips(plan: Plan) -> None:
    """Record identical copies in the ledger, so later upgrades can recognize them."""
    path = plan.state / LEDGER_NAME
    ledger = read_ledger(path)
    entry = ledger["roots"].setdefault(root_key(plan.target.root), {})
    skills = entry.setdefault("skills", {})
    before = json.dumps(skills, sort_keys=True)
    apply_records(skills, plan)
    if json.dumps(skills, sort_keys=True) == before:
        return
    entry.update(path=str(plan.target.root), target=plan.target.name)
    plan.state.mkdir(parents=True, exist_ok=True)
    write_atomic(path, json.dumps(ledger, indent=2, sort_keys=True) + "\n")


def status_of(target: Target, state: Path, source: Source, ledger: dict, out: Reporter) -> dict:
    records = recorded(ledger, target.root)
    out.say(f"{target.name}: {target.root}{'' if target.root.exists() else ' (does not exist)'}")
    for warning in ignored_records(ledger, target.root):
        out.say(f"  Note: {warning}")
    items = [
        inspect_copy(skill.name, target.root / skill.name, records.get(skill.name), skill.digest, source.version)
        for skill in source.skills
    ]
    present = [item for item in items if item.state != "absent"]
    for item in present:
        out.say(f"  {item.state:<13} {item.skill:<26} {item.reason}")
    if not present:
        out.say("  No skill from this suite is installed here.")
    elif len(present) < len(items):
        out.say(f"  {len(items) - len(present)} other skill(s) from this suite are not installed here.")
    retired = []
    for name in RETIRED:
        item = inspect_copy(name, target.root / name, None, None, None)
        if item.state != "absent":
            retired.append(item)
            out.say(f"  {'retired':<13} {item.skill:<26} from 1.0.x; install offers to move it to backups")
    duplicates = [
        {"skill": name, "other_path": str(path), "root": label}
        for name, label, path in duplicate_copies(target, source)
    ]
    for entry in duplicates:
        if any(item.skill == entry["skill"] for item in present):
            out.say(f"  Note: {entry['skill']} is also at {entry['other_path']} ({entry['root']}); the host loads both.")
    return {
        "target": target.name,
        "destination": str(target.root),
        "exists": target.root.exists(),
        "skills": [item.as_dict() for item in items],
        "retired": [item.as_dict() for item in retired],
        "duplicates": duplicates,
    }


def run_status(args, out: Reporter) -> tuple[int, dict]:
    source = load_source()
    state = state_dir()
    ledger = read_ledger(state / LEDGER_NAME)
    if args.target or args.project or args.dest:
        targets = [resolve_target(args.target, args.project, args.dest)]
        errors = []
    else:
        targets, errors = [], []
        for name in ("codex", "codex-legacy", "claude"):
            try:
                targets.append(resolve_target(name, None, None))
            except UsageError as error:
                errors.append(f"{name}: {error}")
    out.say(f"Skills Folder {source.version} at {PACKAGE_ROOT}")
    out.say(f"Ledger and backups: {state}")
    reports = []
    for target in targets:
        out.say()
        reports.append(status_of(target, state, source, ledger, out))
    for error in errors:
        out.say()
        out.say(error)
    journal, active = state / JOURNAL_NAME, lock_held(state)
    if active:
        out.say()
        out.say(f"Another install.py run is in progress; it holds {state / LOCK_NAME}.")
    elif journal.exists():
        out.say()
        out.say(f"An interrupted run left {journal}; the next install or uninstall offers to recover it.")
    return EXIT_OK, {
        "installer_version": source.version,
        "command": "status",
        "state_dir": str(state),
        "ledger": str(state / LEDGER_NAME),
        "source": str(PACKAGE_ROOT),
        "targets": reports,
        "errors": errors,
        "interrupted": journal.exists() and not active,
        "active": active,
        "result": "status",
        "exit_code": EXIT_OK,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="install.py",
        description="Install, check, or uninstall the Skills Folder skills for Codex or Claude Code.",
        epilog=(
            "Exit codes: 0 done, 1 failed or interrupted after a change began, 2 usage or environment error, "
            "3 refused, 4 cancelled before any change."
        ),
    )
    parser.add_argument("--version", action="store_true", help="print the suite version and exit")
    commands = parser.add_subparsers(dest="command", metavar="{install,status,uninstall}")
    where = argparse.ArgumentParser(add_help=False)
    where.add_argument("--target", choices=TARGETS, help="where the skills go (default: codex)")
    where.add_argument("--project", metavar="DIR", help="the project folder for codex-project or claude-project")
    where.add_argument("--dest", metavar="DIR", help="any skills folder, instead of --target")
    where.add_argument("--json", action="store_true", dest="as_json", help="print a JSON result on stdout")
    change = argparse.ArgumentParser(add_help=False)
    change.add_argument("--yes", "-y", action="store_true", help="apply the plan without asking")
    change.add_argument("--keep-retired", action="store_true", help="leave retired 1.0.x skills in place")
    install = commands.add_parser("install", parents=[where, change], help="install or upgrade every skill")
    install.add_argument("--allow-downgrade", action="store_true", help="replace a newer installed version")
    install.add_argument(
        "--replace-modified", action="store_true", help="replace copies whose bytes no recorded version explains"
    )
    install.add_argument(
        "--allow-duplicate-names", action="store_true", help="install even if another loaded folder has the same skill"
    )
    commands.add_parser("status", parents=[where], help="show what is installed where; changes nothing")
    uninstall = commands.add_parser("uninstall", parents=[where, change], help="move the skills to backups")
    uninstall.add_argument(
        "--include-modified", action="store_true", help="also move copies this installer did not put there unchanged"
    )
    return parser


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="backslashreplace")


def main(argv: list[str] | None = None) -> int:
    if sys.version_info < MIN_PYTHON:
        print(
            f"install.py needs Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} or later; this is "
            f"{sys.version_info[0]}.{sys.version_info[1]}. See the README's Python table.",
            file=sys.stderr,
        )
        return EXIT_USAGE
    configure_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.version:
        print(VERSION_FILE.read_text(encoding="utf-8").strip())
        return EXIT_OK
    if args.command is None:
        parser.print_help()
        return EXIT_USAGE
    out = Reporter(args.as_json)
    try:
        if args.command == "status":
            code, payload = run_status(args, out)
        else:
            code, payload = run_change(args.command, args, out)
    except UsageError as error:
        code, payload = EXIT_USAGE, {"result": "usage-error", "error": str(error)}
        out.say(f"install.py: {error}")
    except SourceError as error:
        code, payload = EXIT_REFUSED, {"result": "refused", "error": str(error)}
        out.say(f"install.py: {error}")
    except OSError as error:
        code, payload = EXIT_USAGE, {"result": "usage-error", "error": str(error)}
        out.say(f"install.py: {error}")
        hint = access_hint(error)
        if hint:
            out.say(f"  {hint}")
    except KeyboardInterrupt:
        code, payload = EXIT_CANCELLED, {"result": "cancelled"}
        out.say("Cancelled. Nothing was changed.")
    payload.setdefault("exit_code", code)
    if args.as_json:
        print(json.dumps(payload, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
