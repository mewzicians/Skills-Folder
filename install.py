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
is deleted.

Exit codes: 0 done or nothing to do, 1 failed (changes rolled back), 2 usage
or environment error, 3 refused by a safety check (nothing changed),
4 cancelled at the prompt (nothing changed). Python 3.11 or later, standard
library only, and no network access.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import datetime
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

EXIT_OK, EXIT_FAILED, EXIT_USAGE, EXIT_REFUSED, EXIT_CANCELLED = 0, 1, 2, 3, 4
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


def is_link(path: Path) -> bool:
    """A symbolic link, or on Windows a junction."""
    try:
        info = os.lstat(path)
    except OSError:
        return False
    if stat.S_ISLNK(info.st_mode):
        return True
    tag = getattr(info, "st_reparse_tag", 0)
    return tag in (getattr(stat, "IO_REPARSE_TAG_SYMLINK", -1), getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", -1))


def links_inside(root: Path) -> list[str]:
    found = []
    for directory, folders, files in os.walk(root):
        for name in sorted(folders + files):
            if is_link(Path(directory) / name):
                found.append((Path(directory) / name).relative_to(root).as_posix())
        folders[:] = [name for name in folders if not is_link(Path(directory) / name)]
    return found


def is_debris(name: str) -> bool:
    return name in DEBRIS_FILES or name.endswith(DEBRIS_SUFFIXES)


def tree_files(root: Path, include_debris: bool = False) -> list[tuple[str, Path]]:
    files = []
    for directory, folders, names in os.walk(root):
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


def remove_tree(path: Path) -> None:
    """Remove a tree this installer created (a stage or an unused backup copy)."""

    def make_writable(function, name, *_):
        os.chmod(name, stat.S_IWRITE | stat.S_IREAD)
        function(name)

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


def now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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


def read_ledger(path: Path) -> dict:
    if not path.exists():
        return {"schema": LEDGER_SCHEMA, "roots": {}}
    try:
        ledger = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise UsageError(f"cannot read the install ledger {path}: {error}. Move it aside to continue.") from error
    if not isinstance(ledger, dict) or not isinstance(ledger.get("roots"), dict):
        raise UsageError(f"the install ledger {path} has an unknown shape. Move it aside to continue.")
    return ledger


def recorded(ledger: dict, root: Path) -> dict[str, dict]:
    entry = ledger["roots"].get(root_key(root), {})
    skills = entry.get("skills", {}) if isinstance(entry, dict) else {}
    return {name: value for name, value in skills.items() if isinstance(value, dict)} if isinstance(skills, dict) else {}


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
    links = links_inside(path)
    if links:
        return Item(name, "link", "", path, f"holds a link ({links[0]}), which this installer never touches")
    current = tree_digest(path)
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
    roots = other_roots(target)
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
        for label, root in roots:
            other = root / skill.name
            if os.path.lexists(other):
                if item.action in CHANGES and not args.allow_duplicate_names:
                    item.action, item.override, item.other_path = "refuse", "--allow-duplicate-names", other
                    item.reason = (
                        f"{item.path} would share its name with {other} ({label}); the same host loads both"
                    )
                elif item.action in CHANGES + ("skip",):
                    plan.warnings.append(f"{skill.name} is also in {other} ({label}); the host loads both.")
                break
        plan.items.append(item)
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
        if item.state == "link":
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
    digests = {skill.name: skill.digest for skill in source.skills}
    for name in sorted(set(digests) | set(records)):
        item = inspect_copy(name, target.root / name, records.get(name), digests.get(name), source.version)
        if item.state == "absent":
            continue
        if item.state == "link":
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

    def save(self) -> None:
        write_atomic(self.journal_path, json.dumps(self.journal, indent=2) + "\n")

    def begin(self) -> None:
        self.plan.state.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(self.journal_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as error:
            raise UsageError(
                f"{self.journal_path} exists: another install.py run is active, or one was interrupted. "
                "If none is running, run this command again to roll the interrupted run back."
            ) from error
        os.close(descriptor)
        self.journal = {
            "id": self.id,
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
        self.save()

    def rename(self, source: Path, destination: Path) -> None:
        if os.path.lexists(destination):
            raise InstallError(f"{destination} already exists")
        self.journal["renames"].append({"from": str(source), "to": str(destination)})
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
        for item in plan.changes:
            if item.action == "remove":
                continue
            skill = sources[item.skill]
            staged = stage / "new" / skill.name
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
            self.journal["backup"] = str(backup)
            self.save()
            backup.mkdir(parents=True)
            manifest = []
            for item in replaced:
                expected = tree_digest(item.path, include_debris=True)
                copy_tree(item.path, backup / item.skill, include_debris=True)
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
                self.rename(item.path, stage / "old" / item.skill)
            if item.action in CHANGES:
                self.rename(stage / "new" / item.skill, item.path)
        self.write_ledger()
        self.journal["committed"] = True
        self.save()
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
        """After the commit: drop the stage, whose old copies the backup holds. Never rolls back."""
        try:
            stage = self.journal.get("stage")
            if stage and Path(stage).exists():
                remove_tree(Path(stage))
            self.journal_path.unlink()
        except OSError as error:
            return f"the change is complete, but cleanup stopped ({error}); the next run finishes it."
        return None

    def rollback(self) -> list[str]:
        """Undo every recorded step; return the problems that kept it from finishing."""
        return undo(self.journal, self.journal_path, self.rolled_back)


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


def undo(journal: dict, journal_path: Path, log: list[str]) -> list[str]:
    problems = []
    for step in reversed(journal.get("renames", [])):
        source, destination = Path(step["from"]), Path(step["to"])
        if os.path.lexists(destination) and not os.path.lexists(source):
            try:
                os.rename(destination, source)
                log.append(f"restored {source}")
            except OSError as error:
                problems.append(f"could not move {destination} back to {source}: {error}")
        elif not os.path.lexists(source):
            problems.append(f"{source} and {destination} are both missing")
    ledger = Path(journal["ledger"])
    if journal.get("ledger_written"):
        before = journal.get("ledger_before")
        try:
            current = ledger.read_text(encoding="utf-8") if ledger.exists() else None
            if current != before:
                if before is None:
                    ledger.unlink()
                else:
                    write_atomic(ledger, before)
                log.append(f"restored {ledger}")
        except OSError as error:
            problems.append(f"could not restore {ledger}: {error}")
    stage = journal.get("stage")
    if stage and Path(stage).exists():
        old = Path(stage) / "old"
        if old.exists() and any(old.iterdir()):
            problems.append(f"kept {stage}, which still holds skills that could not be moved back")
        else:
            remove_tree(Path(stage))
    for folder in reversed(journal.get("created", [])):
        try:
            Path(folder).rmdir()
            log.append(f"removed the empty folder {folder}, which this run created")
        except OSError:
            pass
    backup = journal.get("backup")
    if backup and Path(backup).exists():
        if problems:
            problems.append(f"kept the backup {backup}")
        else:
            remove_tree(Path(backup))
    if not problems and journal_path.exists():
        journal_path.unlink()
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
    journal_path = state / JOURNAL_NAME
    try:
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        if not isinstance(journal, dict) or not isinstance(journal.get("renames"), list) or "ledger" not in journal:
            raise ValueError("unknown shape")
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise UsageError(
            f"{journal_path} records an interrupted run but cannot be read ({error}). Check the skills folder "
            "and the backups by hand, then move the journal aside."
        ) from error
    committed = journal.get("committed")
    out.say(f"A previous run ({journal.get('command')} into {journal.get('root')}) did not finish: {journal_path}")
    out.say("  It will be finished (its changes are complete)." if committed else "  Its changes will be rolled back.")
    if not ask("Recover it now?", args, out):
        return EXIT_CANCELLED, {"result": "cancelled", "journal": str(journal_path)}
    log: list[str] = []
    if committed:
        stage = journal.get("stage")
        if stage and Path(stage).exists():
            remove_tree(Path(stage))
        journal_path.unlink()
        problems = []
    else:
        problems = undo(journal, journal_path, log)
    for line in log:
        out.say(f"  {line}")
    for problem in problems:
        out.say(f"  PROBLEM: {problem}")
    out.say("Recovered. Nothing else was done; run the command again." if not problems else "Recovery is incomplete.")
    return EXIT_FAILED, {"result": "recovered" if not problems else "failed", "rolled_back": log, "errors": problems}


def run_change(command: str, args, out: Reporter) -> tuple[int, dict]:
    source = load_source()
    target = resolve_target(args.target, args.project, args.dest)
    state = state_dir()
    check_locations(target, state)
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
    transaction.begin()
    try:
        backup = transaction.run()
    except BaseException as error:  # noqa: BLE001 - every failure, including Ctrl+C, rolls back
        problems = transaction.rollback()
        out.say(f"Failed: {error!r}" if isinstance(error, KeyboardInterrupt) else f"Failed: {error}")
        for line in transaction.rolled_back:
            out.say(f"  rolled back: {line}")
        for problem in problems:
            out.say(f"  PROBLEM: {problem}")
        out.say("Every change was rolled back." if not problems else "The rollback is incomplete; see above.")
        return finish(
            EXIT_FAILED, "failed", error=str(error), rolled_back=transaction.rolled_back, errors=problems,
            stage=transaction.journal.get("stage"),
        )
    cleanup = transaction.finish()
    if cleanup:
        plan.warnings.append(cleanup)
        out.say(f"Note: {cleanup}")
    done = len(plan.changes) + len(plan.moves)
    out.say(f"Done: {done} change(s) applied." + (f" Backups: {backup}" if backup else ""))
    if command == "install":
        out.say("Start a new agent session, then check the list with /skills.")
    return finish(EXIT_OK, "done", backup=backup, stage=transaction.journal.get("stage"))


def record_skips(plan: Plan) -> None:
    """Record identical copies in the ledger, so later upgrades can recognize them."""
    path = plan.state / LEDGER_NAME
    ledger = read_ledger(path)
    entry = ledger["roots"].get(root_key(plan.target.root), {})
    known = entry.get("skills", {}) if isinstance(entry, dict) else {}
    digests = {skill.name: skill.digest for skill in plan.source.skills}
    if all(
        isinstance(known.get(item.skill), dict)
        and known[item.skill].get("digest") == digests[item.skill]
        and known[item.skill].get("version") == plan.source.version
        for item in plan.items
        if item.action == "skip"
    ):
        return
    entry = ledger["roots"].setdefault(root_key(plan.target.root), {})
    entry.update(path=str(plan.target.root), target=plan.target.name)
    apply_records(entry.setdefault("skills", {}), plan)
    plan.state.mkdir(parents=True, exist_ok=True)
    write_atomic(path, json.dumps(ledger, indent=2, sort_keys=True) + "\n")


def status_of(target: Target, state: Path, source: Source, ledger: dict, out: Reporter) -> dict:
    records = recorded(ledger, target.root)
    out.say(f"{target.name}: {target.root}{'' if target.root.exists() else ' (does not exist)'}")
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
    duplicates = []
    for label, root in other_roots(target):
        names = [skill.name for skill in source.skills if os.path.lexists(root / skill.name)]
        duplicates.extend({"skill": name, "other_path": str(root / name), "root": label} for name in names)
        if names and present:
            shared = [item.skill for item in present if item.skill in names]
            if shared:
                out.say(f"  Note: {len(shared)} of these are also in {root} ({label}); the host loads both.")
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
    journal = state / JOURNAL_NAME
    if journal.exists():
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
        "interrupted": journal.exists(),
        "result": "status",
        "exit_code": EXIT_OK,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="install.py",
        description="Install, check, or uninstall the Skills Folder skills for Codex or Claude Code.",
        epilog="Exit codes: 0 done, 1 failed and rolled back, 2 usage error, 3 refused, 4 cancelled.",
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
    except KeyboardInterrupt:
        code, payload = EXIT_CANCELLED, {"result": "cancelled"}
        out.say("Cancelled.")
    payload.setdefault("exit_code", code)
    if args.as_json:
        print(json.dumps(payload, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
