#!/usr/bin/env python3
"""Check install.py in temporary homes: targets, decisions, rollback, backups, and no network.

Every test points HOME, USERPROFILE, CODEX_HOME, CLAUDE_CONFIG_DIR,
LOCALAPPDATA, and XDG_STATE_HOME into a temporary folder. The module also
snapshots the real skill folders, the real state folders, and this checkout
before the first test and fails if any of them changed after the last one.

    python -B tests/install/test_install.py
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import shutil
import socket
import stat
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "install.py"
CHILD_FLAGS = ["-B", "-X", "warn_default_encoding", "-W", "error::EncodingWarning"]
HOME_KEYS = ("HOME", "USERPROFILE", "CODEX_HOME", "CLAUDE_CONFIG_DIR", "LOCALAPPDATA", "XDG_STATE_HOME")
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
SKILLS = sorted(path.name for path in (ROOT / "skills").iterdir() if path.is_dir() and not path.name.startswith("."))
RETIRED = ("game-github-package", "game-skill-creator", "game-skill-installer")
PACKAGE_PARTS = ("install.py", "VERSION", "tools/lib/skill_frontmatter.py", "skills")


def load_installer():
    spec = importlib.util.spec_from_file_location("skills_folder_install", INSTALLER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


INSTALL = load_installer()


# ------------------------------------------------- the real-location guard


def real_locations() -> list[Path]:
    """Every real folder install.py could write to, read before any test changes the environment."""
    env, home = os.environ, Path.home()
    codex = Path(env["CODEX_HOME"]) if env.get("CODEX_HOME") else home / ".codex"
    claude = Path(env["CLAUDE_CONFIG_DIR"]) if env.get("CLAUDE_CONFIG_DIR") else home / ".claude"
    local = Path(env["LOCALAPPDATA"]) if env.get("LOCALAPPDATA") else home / "AppData" / "Local"
    xdg = Path(env["XDG_STATE_HOME"]) if env.get("XDG_STATE_HOME") else home / ".local" / "state"
    return [
        home / ".agents",
        codex / "skills",
        claude / "skills",
        local / "skills-folder",
        home / "Library" / "Application Support" / "skills-folder",
        xdg / "skills-folder",
        ROOT,
    ]


def snapshot(path: Path) -> dict[str, tuple[int, int]] | None:
    """Each entry's size and modification time; directories change when entries come or go."""
    if not os.path.lexists(path):
        return None
    entries = {".": (0, os.lstat(path).st_mtime_ns)}
    for directory, folders, files in os.walk(path):
        if Path(directory) == ROOT:
            folders[:] = [name for name in folders if name != ".git"]
        for name in folders + files:
            full = Path(directory) / name
            info = os.lstat(full)
            size = 0 if full.is_dir() else info.st_size
            entries[full.relative_to(path).as_posix()] = (size, info.st_mtime_ns)
    return entries


REAL_BEFORE: dict[str, object] = {}


def setUpModule() -> None:
    for path in real_locations():
        REAL_BEFORE[str(path)] = snapshot(path)


def tearDownModule() -> None:
    changed = [path for path, before in REAL_BEFORE.items() if snapshot(Path(path)) != before]
    if changed:
        raise AssertionError("install tests changed real folders outside the temporary homes: " + ", ".join(changed))


# --------------------------------------------------------------- helpers


class Homes:
    """A temporary home with every folder install.py reads from the environment."""

    def __init__(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="install-test-")
        self.root = Path(self.temp.name).resolve()
        self.home = self.root / "home"
        self.codex_home = self.root / "codex-home"
        self.claude_config = self.root / "claude-config"
        self.localappdata = self.root / "localappdata"
        self.xdg_state = self.root / "xdg-state"
        for folder in (self.home, self.codex_home, self.claude_config, self.localappdata, self.xdg_state):
            folder.mkdir()
        self.env = {
            "HOME": str(self.home),
            "USERPROFILE": str(self.home),
            "CODEX_HOME": str(self.codex_home),
            "CLAUDE_CONFIG_DIR": str(self.claude_config),
            "LOCALAPPDATA": str(self.localappdata),
            "XDG_STATE_HOME": str(self.xdg_state),
        }

    def cleanup(self) -> None:
        self.temp.cleanup()

    @property
    def state(self) -> Path:
        if os.name == "nt":
            return self.localappdata / "skills-folder"
        if sys.platform == "darwin":
            return self.home / "Library" / "Application Support" / "skills-folder"
        return self.xdg_state / "skills-folder"

    @property
    def codex(self) -> Path:
        return self.home / ".agents" / "skills"

    @property
    def legacy(self) -> Path:
        return self.codex_home / "skills"

    @property
    def claude(self) -> Path:
        return self.claude_config / "skills"

    @property
    def ledger(self) -> Path:
        return self.state / "install-ledger.json"

    def backups(self) -> list[Path]:
        folder = self.state / "backups"
        return sorted(folder.iterdir()) if folder.exists() else []


def child_env(homes: Homes, **overrides: str) -> dict[str, str]:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    env.pop("PYTHONWARNINGS", None)
    env.update(homes.env)
    env.update(overrides)
    return env


def run_cli(homes: Homes, *args: str, stdin: str = "", installer: Path = INSTALLER, **overrides: str):
    """Run install.py as a program; return (exit code, JSON result, human text on stderr)."""
    completed = subprocess.run(
        [sys.executable, *CHILD_FLAGS, str(installer), *args, "--json"],
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=child_env(homes, **overrides),
        cwd=str(homes.root),
        check=False,
    )
    try:
        payload = json.loads(completed.stdout)
    except ValueError as error:
        raise AssertionError(f"no JSON result ({completed.returncode}):\n{completed.stdout}\n{completed.stderr}") from error
    return completed.returncode, payload, completed.stderr


def run_text(homes: Homes, *args: str, stdin: str = "", **overrides: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, *CHILD_FLAGS, str(INSTALLER), *args],
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=child_env(homes, **overrides),
        cwd=str(homes.root),
        check=False,
    )


def run_here(homes: Homes, *args: str, stdin: str = "", **overrides: str):
    """Run install.main() in this process, for fault injection; same return shape as run_cli."""
    env = dict(homes.env, **overrides)
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.dict(os.environ, env), mock.patch.object(sys, "stdin", io.StringIO(stdin)):
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = INSTALL.main([*args, "--json"])
    return code, json.loads(out.getvalue()), err.getvalue()


def outside_state(homes: Homes, entries: dict[str, str]) -> dict[str, str]:
    """tree(homes.home) without the state folder, which sits under the home folder on macOS."""
    if not INSTALL.is_within(homes.state, homes.home):
        return entries
    prefix = homes.state.relative_to(homes.home).as_posix()
    parents = {"/".join(prefix.split("/")[: index + 1]) + "/" for index in range(prefix.count("/") + 1)}
    return {key: value for key, value in entries.items() if key not in parents and not key.startswith(prefix + "/")}


def exited_pid() -> int:
    """The ID of a process that has already ended."""
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait()
    return process.pid


def mark_writer_exited(homes: Homes) -> None:
    """Make the journal's writer a process that ended, as after a crash, rather than this test process."""
    path = homes.state / "journal.json"
    journal = json.loads(path.read_text(encoding="utf-8"))
    journal["pid"] = exited_pid()
    path.write_text(json.dumps(journal, indent=2) + "\n", encoding="utf-8", newline="\n")


def tree(root: Path) -> dict[str, str]:
    """Every file and folder under root, with each file's SHA-256."""
    if not root.exists():
        return {}
    entries = {}
    for directory, folders, files in os.walk(root):
        for name in folders:
            entries[(Path(directory) / name).relative_to(root).as_posix() + "/"] = "dir"
        for name in files:
            path = Path(directory) / name
            entries[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return entries


def source_digest(name: str) -> str:
    return INSTALL.tree_digest(ROOT / "skills" / name)


def edit_ledger(homes: Homes, root: Path, name: str, **values) -> None:
    ledger = json.loads(homes.ledger.read_text(encoding="utf-8"))
    skills = ledger["roots"][INSTALL.root_key(root)]["skills"]
    if values.get("remove"):
        skills.pop(name)
    else:
        skills[name].update(values)
    homes.ledger.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8", newline="\n")


def modify(root: Path, name: str, text: str = "Local note.\n") -> str:
    """Append to an installed SKILL.md; return the copy's new digest."""
    skill = root / name / "SKILL.md"
    skill.write_bytes(skill.read_bytes() + text.encode("utf-8"))
    return INSTALL.tree_digest(root / name)


def plant_retired(root: Path) -> None:
    for name in RETIRED:
        folder = root / name
        folder.mkdir(parents=True)
        (folder / "SKILL.md").write_text(f"---\nname: {name}\ndescription: Retired.\n---\n", encoding="utf-8", newline="\n")


def actions(payload: dict) -> dict[str, str]:
    return {item["skill"]: item["action"] for item in payload["plan"] + payload["retired"]}


class HomesTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.homes = Homes()
        self.addCleanup(self.homes.cleanup)

    def assertInsideHomes(self, payload: dict) -> None:
        """Every path the installer reports writing lies inside the temporary homes."""
        paths = [payload.get(key) for key in ("destination", "state_dir", "ledger", "backup", "stage")]
        paths += [item.get("path") for item in payload.get("plan", []) + payload.get("retired", [])]
        for path in filter(None, paths):
            self.assertTrue(INSTALL.is_within(Path(path), self.homes.root), f"{path} is outside the temporary homes")

    def assertInstalled(self, root: Path) -> None:
        for name in SKILLS:
            with self.subTest(skill=name):
                self.assertEqual(INSTALL.tree_digest(root / name), source_digest(name))
        ledger = json.loads(self.homes.ledger.read_text(encoding="utf-8"))
        recorded = ledger["roots"][INSTALL.root_key(root)]["skills"]
        self.assertEqual(sorted(recorded), SKILLS)
        for name, record in recorded.items():
            self.assertEqual(record["version"], VERSION)
            self.assertEqual(record["digest"], source_digest(name))

    def assertNoSuiteSkills(self, root: Path) -> None:
        self.assertEqual([name for name in SKILLS if (root / name).exists()], [])


# ----------------------------------------------------------------- tests


class TargetTest(HomesTestCase):
    """Each target resolves where its host looks, and a fresh install lands there."""

    def test_fresh_install_per_target(self) -> None:
        project = self.homes.root / "project"
        cases = {
            "codex": ((), lambda homes: homes.codex),
            "codex-legacy": ((), lambda homes: homes.legacy),
            "codex-project": (("--project", "PROJECT"), lambda homes: homes.root / "project" / ".agents" / "skills"),
            "claude": ((), lambda homes: homes.claude),
            "claude-project": (("--project", "PROJECT"), lambda homes: homes.root / "project" / ".claude" / "skills"),
        }
        for target, (extra, where) in cases.items():
            with self.subTest(target=target):
                homes = Homes()
                self.addCleanup(homes.cleanup)
                project = homes.root / "project"
                project.mkdir()
                extra = tuple(str(project) if part == "PROJECT" else part for part in extra)
                code, payload, err = run_cli(homes, "install", "--target", target, *extra, "--yes")
                self.assertEqual(code, 0, err)
                self.assertEqual(payload["result"], "done")
                self.assertEqual(Path(payload["destination"]), where(homes))
                self.homes = homes
                self.assertInstalled(where(homes))
                self.assertInsideHomes(payload)
                self.assertEqual(homes.backups(), [], "a fresh install backs nothing up")

    def test_dest_and_default_target(self) -> None:
        dest = self.homes.root / "elsewhere" / "skills"
        code, payload, err = run_cli(self.homes, "install", "--dest", str(dest), "--yes")
        self.assertEqual(code, 0, err)
        self.assertInstalled(dest)
        self.assertIn("--dest skips the check for same-name skills in other folders.", payload["warnings"])
        code, payload, err = run_cli(self.homes, "install", "--yes")
        self.assertEqual(code, 0, err)
        self.assertEqual(Path(payload["destination"]), self.homes.codex)
        self.assertInstalled(self.homes.codex)

    def test_claude_without_a_config_dir_uses_the_home_folder(self) -> None:
        code, payload, err = run_cli(self.homes, "install", "--target", "claude", "--yes", CLAUDE_CONFIG_DIR="")
        self.assertEqual(code, 0, err)
        self.assertEqual(Path(payload["destination"]), self.homes.home / ".claude" / "skills")

    def test_empty_codex_home_means_unset(self) -> None:
        code, payload, err = run_cli(self.homes, "install", "--target", "codex-legacy", "--yes", CODEX_HOME="")
        self.assertEqual(code, 0, err)
        self.assertEqual(Path(payload["destination"]), self.homes.home / ".codex" / "skills")
        self.assertInstalled(self.homes.home / ".codex" / "skills")

    def test_codex_home_must_exist_and_is_never_tilde_expanded(self) -> None:
        for value in (str(self.homes.root / "missing"), "~/codex-home"):
            with self.subTest(value=value):
                code, payload, err = run_cli(self.homes, "install", "--target", "codex-legacy", "--yes", CODEX_HOME=value)
                self.assertEqual(code, 2, err)
                self.assertEqual(payload["result"], "usage-error")
                self.assertIn("does not expand '~'", payload["error"])
        self.assertEqual(tree(self.homes.home), {})
        self.assertFalse(self.homes.state.exists())

    def test_bad_target_combinations_are_usage_errors(self) -> None:
        project = self.homes.root / "project"
        project.mkdir()
        cases = [
            ("install", "--target", "codex-project"),
            ("install", "--target", "claude", "--project", str(project)),
            ("install", "--target", "codex", "--dest", str(self.homes.root / "d")),
            ("install", "--target", "claude-project", "--project", str(self.homes.root / "missing")),
            ("install", "--dest", str(ROOT / "skills")),
            ("install", "--dest", str(ROOT)),
            ("install", "--dest", str(self.homes.state / "backups")),
        ]
        for args in cases:
            with self.subTest(args=args[1:]):
                code, payload, err = run_cli(self.homes, *args, "--yes")
                self.assertEqual(code, 2, err)
                self.assertEqual(payload["result"], "usage-error")
        self.assertEqual(tree(self.homes.home), {})

    def test_version_flag(self) -> None:
        completed = run_text(self.homes, "--version")
        self.assertEqual((completed.returncode, completed.stdout.strip()), (0, VERSION))


class DecisionTest(HomesTestCase):
    """Per-skill decisions from the version, the tree digest, and the ledger."""

    def setUp(self) -> None:
        super().setUp()
        code, payload, err = run_here(self.homes, "install", "--yes")
        self.assertEqual(code, 0, err)

    def test_a_rerun_reports_every_skill_current(self) -> None:
        before = tree(self.homes.codex)
        code, payload, err = run_cli(self.homes, "install", "--yes")
        self.assertEqual(code, 0, err)
        self.assertEqual(payload["result"], "nothing-to-do")
        self.assertEqual(set(actions(payload).values()), {"skip"})
        self.assertEqual(tree(self.homes.codex), before)
        self.assertEqual(self.homes.backups(), [])

    def test_an_older_version_upgrades_with_a_backup(self) -> None:
        changed = modify(self.homes.codex, "game-plan", "From an older release.\n")
        old_bytes = (self.homes.codex / "game-plan" / "SKILL.md").read_bytes()
        edit_ledger(self.homes, self.homes.codex, "game-plan", version="1.0.0", digest=changed)
        code, payload, err = run_here(self.homes, "install", "--yes")
        self.assertEqual(code, 0, err)
        self.assertEqual(actions(payload)["game-plan"], "upgrade")
        self.assertEqual({action for name, action in actions(payload).items() if name != "game-plan"}, {"skip"})
        self.assertInstalled(self.homes.codex)
        [backup] = self.homes.backups()
        self.assertEqual(Path(payload["backup"]), backup)
        self.assertEqual((backup / "game-plan" / "SKILL.md").read_bytes(), old_bytes)
        manifest = json.loads((backup / "backup.json").read_text(encoding="utf-8"))
        self.assertEqual([entry["skill"] for entry in manifest["skills"]], ["game-plan"])
        self.assertInsideHomes(payload)

    def test_a_newer_version_is_refused_with_exit_3(self) -> None:
        changed = modify(self.homes.codex, "game-debug", "From a later release.\n")
        edit_ledger(self.homes, self.homes.codex, "game-debug", version="9.0.0", digest=changed)
        before, ledger = tree(self.homes.codex), self.homes.ledger.read_bytes()
        code, payload, err = run_cli(self.homes, "install", "--yes")
        self.assertEqual(code, 3, err)
        self.assertEqual(payload["result"], "refused")
        item = next(entry for entry in payload["plan"] if entry["skill"] == "game-debug")
        self.assertEqual((item["state"], item["action"], item["override"]), ("newer", "refuse", "--allow-downgrade"))
        self.assertEqual((tree(self.homes.codex), self.homes.ledger.read_bytes()), (before, ledger))
        self.assertEqual(self.homes.backups(), [])
        code, payload, err = run_cli(self.homes, "install", "--yes", "--allow-downgrade")
        self.assertEqual(code, 0, err)
        self.assertEqual(actions(payload)["game-debug"], "downgrade")
        self.assertInstalled(self.homes.codex)
        self.assertEqual(len(self.homes.backups()), 1)

    def test_different_bytes_with_no_recorded_version_are_refused(self) -> None:
        modify(self.homes.codex, "game-implement")
        edit_ledger(self.homes, self.homes.codex, "game-implement", remove=True)
        before = tree(self.homes.codex)
        code, payload, err = run_cli(self.homes, "install", "--yes")
        self.assertEqual(code, 3, err)
        item = next(entry for entry in payload["plan"] if entry["skill"] == "game-implement")
        self.assertEqual((item["state"], item["override"]), ("unrecorded", "--replace-modified"))
        self.assertEqual(tree(self.homes.codex), before)
        code, payload, err = run_cli(self.homes, "install", "--yes", "--replace-modified")
        self.assertEqual(code, 0, err)
        self.assertEqual(actions(payload)["game-implement"], "replace")
        self.assertInstalled(self.homes.codex)
        [backup] = self.homes.backups()
        self.assertTrue((backup / "game-implement" / "SKILL.md").read_bytes().endswith(b"Local note.\n"))

    def test_local_edits_since_install_are_refused(self) -> None:
        modify(self.homes.codex, "game-ux-audit")
        code, payload, err = run_cli(self.homes, "install", "--yes")
        self.assertEqual(code, 3, err)
        item = next(entry for entry in payload["plan"] if entry["skill"] == "game-ux-audit")
        self.assertEqual((item["state"], item["override"]), ("modified", "--replace-modified"))
        code, payload, err = run_cli(self.homes, "install", "--yes", "--replace-modified")
        self.assertEqual(code, 0, err)
        self.assertInstalled(self.homes.codex)

    def test_a_same_name_skill_in_another_loaded_root_is_refused(self) -> None:
        completed = run_text(self.homes, "install", "--target", "codex-legacy", "--yes")
        self.assertEqual(completed.returncode, 3, completed.stderr)
        line = next(row for row in completed.stdout.splitlines() if "game-plan" in row and "REFUSED" in row)
        self.assertIn(str(self.homes.legacy / "game-plan"), line)
        self.assertIn(str(self.homes.codex / "game-plan"), line)
        self.assertIn("--allow-duplicate-names", completed.stdout)
        self.assertFalse(self.homes.legacy.exists())
        code, payload, err = run_cli(self.homes, "install", "--target", "codex-legacy", "--yes", "--allow-duplicate-names")
        self.assertEqual(code, 0, err)
        self.assertInstalled(self.homes.legacy)
        self.assertTrue(any("the host loads both" in warning for warning in payload["warnings"]))

    def test_other_hosts_are_not_duplicates(self) -> None:
        code, payload, err = run_cli(self.homes, "install", "--target", "claude", "--yes")
        self.assertEqual(code, 0, err)
        self.assertInstalled(self.homes.claude)

    def test_retired_skills_are_offered_for_backup(self) -> None:
        plant_retired(self.homes.codex)
        code, payload, err = run_cli(self.homes, "install", "--keep-retired", "--yes")
        self.assertEqual(code, 0, err)
        self.assertEqual({actions(payload)[name] for name in RETIRED}, {"keep"})
        # Declined at the prompt: nothing moves.
        code, payload, err = run_cli(self.homes, "install", stdin="n\n")
        self.assertEqual(code, 4, err)
        self.assertTrue(all((self.homes.codex / name).exists() for name in RETIRED))
        code, payload, err = run_cli(self.homes, "install", stdin="y\n")
        self.assertEqual(code, 0, err)
        self.assertEqual({actions(payload)[name] for name in RETIRED}, {"retire"})
        self.assertFalse(any((self.homes.codex / name).exists() for name in RETIRED))
        [backup] = self.homes.backups()
        self.assertEqual(sorted(path.name for path in backup.iterdir() if path.is_dir()), list(RETIRED))
        self.assertInstalled(self.homes.codex)

    def test_retired_skills_and_an_upgrade_take_separate_answers(self) -> None:
        plant_retired(self.homes.codex)
        changed = modify(self.homes.codex, "game-plan")
        edit_ledger(self.homes, self.homes.codex, "game-plan", version="1.0.0", digest=changed)
        code, payload, err = run_cli(self.homes, "install", stdin="y\nn\n")
        self.assertEqual(code, 0, err)
        self.assertEqual(actions(payload)["game-plan"], "upgrade")
        self.assertEqual({actions(payload)[name] for name in RETIRED}, {"keep"})
        self.assertTrue(all((self.homes.codex / name).exists() for name in RETIRED))
        self.assertInstalled(self.homes.codex)

    def test_status_reports_each_state_and_changes_nothing(self) -> None:
        changed = modify(self.homes.codex, "game-plan")
        edit_ledger(self.homes, self.homes.codex, "game-plan", version="1.0.0", digest=changed)
        modify(self.homes.codex, "game-debug")
        shutil.rmtree(self.homes.codex / "music-composer")
        plant_retired(self.homes.codex)
        before = (tree(self.homes.root), self.homes.ledger.read_bytes())
        code, payload, err = run_cli(self.homes, "status", "--target", "codex")
        self.assertEqual(code, 0, err)
        [report] = payload["targets"]
        states = {item["skill"]: item["state"] for item in report["skills"]}
        self.assertEqual(states["game-plan"], "older")
        self.assertEqual(states["game-debug"], "modified")
        self.assertEqual(states["music-composer"], "absent")
        self.assertEqual(states["game-release"], "current")
        self.assertEqual(sorted(item["skill"] for item in report["retired"]), list(RETIRED))
        self.assertEqual((tree(self.homes.root), self.homes.ledger.read_bytes()), before)
        code, payload, err = run_cli(self.homes, "status")
        self.assertEqual(code, 0, err)
        self.assertEqual([item["target"] for item in payload["targets"]], ["codex", "codex-legacy", "claude"])


def plant_skill(folder: Path, name: str | None, description: str = "Another copy.") -> None:
    """A SKILL.md in folder; name None leaves the frontmatter without a name."""
    folder.mkdir(parents=True)
    lines = ["---"] + ([f"name: {name}"] if name else []) + [f"description: {description}", "---", "Body.", ""]
    (folder / "SKILL.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")


class DuplicateNameTest(HomesTestCase):
    """Codex loads skills by frontmatter name, from anywhere in a root outside hidden folders."""

    def refusals(self, payload: dict) -> dict[str, str]:
        return {item["skill"]: item["other_path"] for item in payload["plan"] if item["action"] == "refuse"}

    def test_a_renamed_or_nested_copy_is_a_duplicate(self) -> None:
        legacy = self.homes.legacy
        plant_skill(legacy / "my-old-plan", "game-plan")
        plant_skill(legacy / "vendor" / "game-debug", "game-debug")
        # Codex reads a SKILL.md at most six levels down: a skill folder five levels down counts, six does not.
        plant_skill(legacy / "vendor" / "a" / "b" / "c" / "game-qa-cleanup", "game-qa-cleanup")
        plant_skill(legacy / "vendor" / "a" / "b" / "c" / "d" / "music-composer", "music-composer")
        plant_skill(legacy / ".hidden" / "game-ux-audit", "game-ux-audit")
        plant_skill(legacy / "vendor" / ".cache" / "game-release", "game-release")
        plant_skill(legacy / "game-implement-notes", "something-else")
        plant_skill(legacy / "game-balance-lab-old", None)
        code, payload, err = run_cli(self.homes, "install", "--yes")
        self.assertEqual((code, payload["result"]), (3, "refused"), err)
        self.assertEqual(
            self.refusals(payload),
            {
                "game-plan": str(legacy / "my-old-plan"),
                "game-debug": str(legacy / "vendor" / "game-debug"),
                "game-qa-cleanup": str(legacy / "vendor" / "a" / "b" / "c" / "game-qa-cleanup"),
            },
        )
        self.assertFalse(self.homes.codex.exists())
        code, status, err = run_cli(self.homes, "status", "--target", "codex")
        self.assertEqual(
            sorted(entry["skill"] for entry in status["targets"][0]["duplicates"]),
            ["game-debug", "game-plan", "game-qa-cleanup"],
        )
        code, payload, err = run_cli(self.homes, "install", "--yes", "--allow-duplicate-names")
        self.assertEqual(code, 0, err)
        self.assertInstalled(self.homes.codex)
        warnings = " ".join(payload["warnings"])
        self.assertIn(str(legacy / "my-old-plan"), warnings)
        self.assertIn(str(legacy / "vendor" / "game-debug"), warnings)

    def test_a_renamed_copy_in_the_target_itself_is_a_duplicate(self) -> None:
        plant_skill(self.homes.codex / "my-old-plan", "game-plan")
        code, payload, err = run_cli(self.homes, "install", "--yes")
        self.assertEqual((code, payload["result"]), (3, "refused"), err)
        self.assertEqual(self.refusals(payload), {"game-plan": str(self.homes.codex / "my-old-plan")})
        self.assertIn("(codex)", next(item["reason"] for item in payload["plan"] if item["skill"] == "game-plan"))

    def test_claude_roots_keep_the_folder_name_check(self) -> None:
        plant_skill(self.homes.claude / "my-old-plan", "game-plan")
        plant_skill(self.homes.claude / "game-debug", "game-debug")
        project = self.homes.root / "game"
        project.mkdir()
        code, payload, err = run_cli(
            self.homes, "install", "--target", "claude-project", "--project", str(project), "--yes"
        )
        self.assertEqual((code, payload["result"]), (3, "refused"), err)
        self.assertEqual(self.refusals(payload), {"game-debug": str(self.homes.claude / "game-debug")})

    def test_version_1_copies_point_to_the_upgrade_commands(self) -> None:
        for name in SKILLS:
            shutil.copytree(ROOT / "skills" / name, self.homes.legacy / name)
        completed = run_text(self.homes, "install", "--yes")
        self.assertEqual(completed.returncode, 3, completed.stderr)
        self.assertIn("python install.py uninstall --target codex-legacy --include-modified", completed.stdout)
        self.assertIn("python install.py install --target codex-legacy --replace-modified", completed.stdout)
        self.assertIn("Upgrading from 1.0.x", completed.stdout)
        # Copies this installer recorded there are not version 1.0 copies.
        homes = Homes()
        self.addCleanup(homes.cleanup)
        code, payload, err = run_cli(homes, "install", "--target", "codex-legacy", "--yes")
        self.assertEqual(code, 0, err)
        completed = run_text(homes, "install", "--yes")
        self.assertEqual(completed.returncode, 3, completed.stderr)
        self.assertNotIn("Upgrading from 1.0.x", completed.stdout)


class ConfirmationTest(HomesTestCase):
    def test_the_plan_is_applied_only_after_a_yes(self) -> None:
        for answer in ("n\n", "", "maybe\n"):
            with self.subTest(answer=answer):
                code, payload, err = run_cli(self.homes, "install", stdin=answer)
                self.assertEqual(code, 4, err)
                self.assertEqual(payload["result"], "cancelled")
                self.assertFalse(self.homes.codex.exists())
                self.assertFalse(self.homes.ledger.exists())
        code, payload, err = run_cli(self.homes, "install", stdin="yes\n")
        self.assertEqual(code, 0, err)
        self.assertInstalled(self.homes.codex)
        self.assertIn("Apply these 12 change(s)?", err)


class UninstallTest(HomesTestCase):
    def setUp(self) -> None:
        super().setUp()
        code, payload, err = run_here(self.homes, "install", "--yes")
        self.assertEqual(code, 0, err)

    def test_uninstall_moves_every_skill_to_backups(self) -> None:
        digests = {name: INSTALL.tree_digest(self.homes.codex / name) for name in SKILLS}
        code, payload, err = run_cli(self.homes, "uninstall", "--yes")
        self.assertEqual(code, 0, err)
        self.assertEqual(set(actions(payload).values()), {"remove"})
        self.assertNoSuiteSkills(self.homes.codex)
        [backup] = self.homes.backups()
        self.assertEqual({name: INSTALL.tree_digest(backup / name) for name in SKILLS}, digests)
        ledger = json.loads(self.homes.ledger.read_text(encoding="utf-8"))
        self.assertNotIn(INSTALL.root_key(self.homes.codex), ledger["roots"])
        self.assertInsideHomes(payload)
        code, payload, err = run_cli(self.homes, "uninstall", "--yes")
        self.assertEqual((code, payload["result"]), (0, "nothing-to-do"))

    def test_uninstall_refuses_copies_it_cannot_vouch_for(self) -> None:
        modify(self.homes.codex, "game-plan")
        code, payload, err = run_cli(self.homes, "uninstall", "--yes")
        self.assertEqual(code, 3, err)
        self.assertTrue((self.homes.codex / "game-debug").exists())
        code, payload, err = run_cli(self.homes, "uninstall", "--yes", "--include-modified")
        self.assertEqual(code, 0, err)
        self.assertNoSuiteSkills(self.homes.codex)
        [backup] = self.homes.backups()
        self.assertTrue((backup / "game-plan" / "SKILL.md").read_bytes().endswith(b"Local note.\n"))

    def test_uninstall_also_offers_retired_skills(self) -> None:
        plant_retired(self.homes.codex)
        code, payload, err = run_cli(self.homes, "uninstall", "--yes")
        self.assertEqual(code, 0, err)
        self.assertEqual(sorted(path.name for path in self.homes.codex.iterdir()), [])


def failing_rename(after: int, error: BaseException):
    """os.rename that raises once, on call number after + 1, and otherwise renames."""
    real_rename = os.rename
    calls = {"count": 0}

    def rename(source, destination):
        calls["count"] += 1
        if calls["count"] == after + 1:
            raise error
        return real_rename(source, destination)

    return rename


class AtomicityTest(HomesTestCase):
    """Any failure rolls every change back; an interrupted run is recovered."""

    def setUp(self) -> None:
        super().setUp()
        code, payload, err = run_here(self.homes, "install", "--yes")
        self.assertEqual(code, 0, err)
        for name in ("game-debug", "game-plan", "music-composer"):
            changed = modify(self.homes.codex, name, "From an older release.\n")
            edit_ledger(self.homes, self.homes.codex, name, version="1.0.0", digest=changed)
        plant_retired(self.homes.codex)
        self.before = tree(self.homes.codex)
        self.ledger_before = self.homes.ledger.read_bytes()

    def assertUnchanged(self) -> None:
        self.assertEqual(tree(self.homes.codex), self.before)
        self.assertEqual(self.homes.ledger.read_bytes(), self.ledger_before)
        self.assertEqual([path.name for path in self.homes.codex.parent.iterdir()], ["skills"])
        self.assertFalse((self.homes.state / "journal.json").exists())
        self.assertEqual(self.homes.backups(), [])

    def test_a_failure_in_the_middle_of_the_swap_rolls_everything_back(self) -> None:
        # Nine renames: three upgraded skills out and back in, and three retired
        # skills out. Fail on the first, an early, a middle, and the last one.
        for after in (0, 1, 4, 8):
            with self.subTest(after=after):
                with mock.patch.object(INSTALL.os, "rename", failing_rename(after, OSError("injected failure"))):
                    code, payload, err = run_here(self.homes, "install", "--yes")
                self.assertEqual(code, 1, err)
                self.assertEqual(payload["result"], "failed")
                self.assertIn("injected failure", payload["error"])
                self.assertEqual(payload["errors"], [])
                if after:
                    self.assertTrue(payload["rolled_back"])
                self.assertIn("Every change was rolled back.", err)
                self.assertUnchanged()
        code, payload, err = run_here(self.homes, "install", "--yes")
        self.assertEqual(code, 0, err)
        self.assertInstalled(self.homes.codex)

    def test_ctrl_c_during_the_swap_rolls_back(self) -> None:
        with mock.patch.object(INSTALL.os, "rename", failing_rename(2, KeyboardInterrupt())):
            code, payload, err = run_here(self.homes, "install", "--yes")
        self.assertEqual((code, payload["result"]), (1, "failed"))
        self.assertIn("Interrupted (Ctrl+C); rolling back.", err)
        self.assertIn("Every change was rolled back.", err)
        self.assertUnchanged()

    def test_ctrl_c_during_the_cleanup_reports_the_change_done(self) -> None:
        def interrupted(path):
            raise KeyboardInterrupt

        with mock.patch.object(INSTALL, "remove_tree", interrupted):
            code, payload, err = run_here(self.homes, "install", "--yes")
        self.assertEqual((code, payload["result"], payload["committed"]), (1, "interrupted", True), err)
        self.assertIn("Done: every change was applied; the next run finishes the cleanup.", err)
        self.assertInstalled(self.homes.codex)
        code, payload, err = run_here(self.homes, "install", "--yes")
        self.assertEqual((code, payload["result"]), (1, "recovered"), err)
        self.assertInstalled(self.homes.codex)
        self.assertEqual([path.name for path in self.homes.codex.parent.iterdir()], ["skills"])

    def test_a_second_ctrl_c_during_the_rollback_leaves_it_to_the_next_run(self) -> None:
        real_rename = os.rename
        calls = {"count": 0}

        def rename(source, destination):
            calls["count"] += 1
            if calls["count"] == 4:
                raise OSError("injected failure")
            if calls["count"] == 5:  # the rollback's first move back
                raise KeyboardInterrupt
            return real_rename(source, destination)

        with mock.patch.object(INSTALL.os, "rename", rename):
            code, payload, err = run_here(self.homes, "install", "--yes")
        self.assertEqual((code, payload["result"], payload["committed"]), (1, "interrupted", False), err)
        self.assertIn("Failed: injected failure", err)
        self.assertIn("Run this command again to roll back the rest.", err)
        self.assertTrue((self.homes.state / "journal.json").exists())
        code, payload, err = run_here(self.homes, "install", "--yes")
        self.assertEqual((code, payload["result"]), (1, "recovered"), err)
        self.assertUnchanged()

    def test_ctrl_c_during_a_recovery_leaves_it_to_the_next_run(self) -> None:
        with mock.patch.object(INSTALL, "undo", lambda journal, path, log: []):
            with mock.patch.object(INSTALL.os, "rename", failing_rename(3, OSError("power cut"))):
                code, payload, err = run_here(self.homes, "install", "--yes")
        self.assertEqual(code, 1, err)
        with mock.patch.object(INSTALL.os, "rename", failing_rename(1, KeyboardInterrupt())):
            code, payload, err = run_here(self.homes, "install", "--yes")
        self.assertEqual((code, payload["result"], payload["committed"]), (1, "interrupted", False), err)
        self.assertIn("Run this command again to roll back the rest.", err)
        code, payload, err = run_here(self.homes, "install", "--yes")
        self.assertEqual((code, payload["result"]), (1, "recovered"), err)
        self.assertUnchanged()

    def test_ctrl_c_before_any_change_is_a_cancel(self) -> None:
        def interrupted(*args, **kwargs):
            raise KeyboardInterrupt

        for where in ("ask", "save"):
            with self.subTest(where=where):
                owner = INSTALL if where == "ask" else INSTALL.Transaction
                with mock.patch.object(owner, where, interrupted):
                    code, payload, err = run_here(self.homes, "install", *([] if where == "ask" else ["--yes"]))
                self.assertEqual((code, payload["result"]), (4, "cancelled"), err)
                self.assertIn("Cancelled. Nothing was changed.", err)
                self.assertUnchanged()

    def test_a_failed_ledger_write_rolls_the_swap_back(self) -> None:
        real_write = INSTALL.write_atomic

        def write(path, text):
            if Path(path).name == "install-ledger.json":
                raise OSError("disk full")
            return real_write(path, text)

        with mock.patch.object(INSTALL, "write_atomic", write):
            code, payload, err = run_here(self.homes, "install", "--yes")
        self.assertEqual(code, 1, err)
        self.assertIn("disk full", payload["error"])
        self.assertUnchanged()

    def test_a_staged_copy_that_differs_from_its_source_is_never_swapped_in(self) -> None:
        real_copy = shutil.copyfile

        def corrupt(source, destination, *args, **kwargs):
            result = real_copy(source, destination, *args, **kwargs)
            if Path(source).name == "SKILL.md" and Path(source).parent.name == "game-plan":
                Path(destination).write_bytes(b"---\nname: game-plan\ndescription: Corrupted.\n---\n")
            return result

        with mock.patch.object(INSTALL.shutil, "copyfile", corrupt):
            code, payload, err = run_here(self.homes, "install", "--yes")
        self.assertEqual(code, 1, err)
        self.assertIn("staged copy of game-plan differs", payload["error"])
        self.assertUnchanged()

    def test_a_fresh_install_that_fails_removes_the_folders_it_created(self) -> None:
        homes = Homes()
        self.addCleanup(homes.cleanup)
        with mock.patch.object(INSTALL.os, "rename", failing_rename(4, OSError("injected failure"))):
            code, payload, err = run_here(homes, "install", "--yes")
        self.assertEqual(code, 1, err)
        self.assertEqual(outside_state(homes, tree(homes.home)), {})
        self.assertFalse(homes.ledger.exists())

    def test_an_interrupted_run_is_rolled_back_on_the_next_run(self) -> None:
        # Simulate a crash: the failure happens, but no rollback runs.
        with mock.patch.object(INSTALL, "undo", lambda journal, path, log: []):
            with mock.patch.object(INSTALL.os, "rename", failing_rename(3, OSError("power cut"))):
                code, payload, err = run_here(self.homes, "install", "--yes")
        self.assertEqual(code, 1, err)
        self.assertTrue((self.homes.state / "journal.json").exists())
        self.assertNotEqual(tree(self.homes.codex), self.before)
        mark_writer_exited(self.homes)
        code, payload, err = run_cli(self.homes, "status", "--target", "codex")
        self.assertEqual((payload["interrupted"], payload["active"]), (True, False))
        code, payload, err = run_cli(self.homes, "install", stdin="n\n")
        self.assertEqual((code, payload["result"]), (4, "cancelled"))
        code, payload, err = run_cli(self.homes, "install", "--yes")
        self.assertEqual((code, payload["result"]), (1, "recovered"), err)
        self.assertUnchanged()
        code, payload, err = run_cli(self.homes, "install", "--yes")
        self.assertEqual(code, 0, err)
        self.assertInstalled(self.homes.codex)

    def test_a_cleanup_failure_after_the_commit_never_rolls_back(self) -> None:
        def stuck(path):
            raise OSError("a file is in use")

        with mock.patch.object(INSTALL, "remove_tree", stuck):
            code, payload, err = run_here(self.homes, "install", "--yes")
        self.assertEqual((code, payload["result"]), (0, "done"), err)
        self.assertTrue(any("cleanup stopped" in warning for warning in payload["warnings"]))
        self.assertInstalled(self.homes.codex)
        journal = json.loads((self.homes.state / "journal.json").read_text(encoding="utf-8"))
        self.assertTrue(journal["committed"])
        mark_writer_exited(self.homes)
        # The next run finishes the cleanup and leaves the installed skills alone.
        code, payload, err = run_cli(self.homes, "install", "--yes")
        self.assertEqual((code, payload["result"]), (1, "recovered"), err)
        self.assertInstalled(self.homes.codex)
        self.assertEqual([path.name for path in self.homes.codex.parent.iterdir()], ["skills"])
        self.assertFalse((self.homes.state / "journal.json").exists())

    def test_a_damaged_journal_is_reported_not_guessed_at(self) -> None:
        (self.homes.state / "journal.json").write_text('{"renames": [', encoding="utf-8")
        code, payload, err = run_cli(self.homes, "install", "--yes")
        self.assertEqual((code, payload["result"]), (2, "usage-error"), err)
        self.assertIn("cannot be read", payload["error"])
        self.assertEqual(tree(self.homes.codex), self.before)

    def test_skipped_skills_keep_their_install_record(self) -> None:
        before = json.loads(self.ledger_before)["roots"][INSTALL.root_key(self.homes.codex)]["skills"]
        code, payload, err = run_here(self.homes, "install", "--yes")
        self.assertEqual(code, 0, err)
        after = json.loads(self.homes.ledger.read_text(encoding="utf-8"))["roots"][INSTALL.root_key(self.homes.codex)]
        self.assertEqual(after["skills"]["game-release"], before["game-release"])
        self.assertEqual(after["skills"]["game-plan"]["version"], VERSION)

    def test_backups_never_sit_under_a_skills_root(self) -> None:
        code, payload, err = run_here(self.homes, "install", "--yes")
        self.assertEqual(code, 0, err)
        [backup] = self.homes.backups()
        self.assertTrue(INSTALL.is_within(backup, self.homes.state))
        for root in (self.homes.codex, self.homes.legacy, self.homes.claude, self.homes.home / ".claude" / "skills"):
            self.assertFalse(INSTALL.is_within(backup, root))
        self.assertEqual(sorted(path.name for path in self.homes.codex.iterdir()), SKILLS)
        self.assertEqual([path.name for path in self.homes.codex.parent.iterdir()], ["skills"])


RUN_ID = "20261020T120000Z-abc123"


def journal_for(homes: Homes, root: Path, **values) -> dict:
    """A journal for an interrupted run into root that touched nothing, as install.py writes one."""
    journal = {
        "id": RUN_ID,
        "command": "install",
        "root": str(root),
        "created": [],
        "stage": str(INSTALL.real(root).parent / f".skills-folder-stage-{RUN_ID}"),
        "backup": None,
        "renames": [],
        "ledger": str(homes.state / "install-ledger.json"),
        "ledger_before": None,
        "ledger_written": False,
        "committed": False,
    }
    journal.update(values)
    return journal


def write_journal(homes: Homes, journal: dict) -> Path:
    path = homes.state / "journal.json"
    path.write_text(json.dumps(journal, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path


class LedgerAndJournalSafetyTest(HomesTestCase):
    """Ledger and journal data become paths only inside the run's own folders."""

    def setUp(self) -> None:
        super().setUp()
        code, payload, err = run_here(self.homes, "install", "--yes")
        self.assertEqual(code, 0, err)
        self.victims = [self.homes.home / "victim", self.homes.state / "victim", self.homes.root / "abs-victim"]
        for folder in self.victims:
            folder.mkdir(parents=True)
            (folder / "data.txt").write_text("Keep me.\n", encoding="utf-8", newline="\n")
        self.victims_before = {str(folder): tree(folder) for folder in self.victims}

    def assertVictimsUntouched(self) -> None:
        self.assertEqual({str(folder): tree(folder) for folder in self.victims}, self.victims_before)

    def test_ledger_names_that_are_not_skill_names_are_ignored(self) -> None:
        ledger = json.loads(self.homes.ledger.read_text(encoding="utf-8"))
        skills = ledger["roots"][INSTALL.root_key(self.homes.codex)]["skills"]
        digest = INSTALL.tree_digest(self.victims[0])
        names = [
            "../../victim", "..\\..\\victim", "game-plan/../../../victim", str(self.victims[2]), "/abs-victim",
            ".", "..", "Game-Plan", "game-plan\n", "game--plan", "a" * 65,
        ]
        for name in names:
            skills[name] = {"version": VERSION, "digest": digest}
        self.homes.ledger.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8", newline="\n")
        code, status, err = run_cli(self.homes, "status", "--target", "codex")
        self.assertEqual(code, 0, err)
        self.assertEqual(sorted(item["skill"] for item in status["targets"][0]["skills"]), SKILLS)
        code, payload, err = run_cli(self.homes, "uninstall", "--yes", "--include-modified")
        self.assertEqual(code, 0, err)
        self.assertEqual(sorted(actions(payload)), SKILLS)
        self.assertTrue(any("which are not skill names" in warning for warning in payload["warnings"]))
        self.assertNoSuiteSkills(self.homes.codex)
        [backup] = self.homes.backups()
        self.assertEqual(sorted(path.name for path in backup.iterdir()), sorted(SKILLS + ["backup.json"]))
        self.assertVictimsUntouched()
        in_home = {path.name for path in self.homes.home.iterdir()} - {"Library"}  # the macOS state folder
        self.assertEqual(in_home, {".agents", "victim"})
        self.assertEqual([path.name for path in self.homes.codex.parent.iterdir()], ["skills"])
        expected = {"backups", "install-ledger.json", "install.lock", "victim"}
        self.assertLessEqual({path.name for path in self.homes.state.iterdir()}, expected)

    def test_a_journal_naming_paths_outside_its_run_is_refused(self) -> None:
        root, victim = self.homes.codex, self.victims[0]
        base = journal_for(self.homes, root)
        stage = Path(base["stage"])
        cases = {
            "backup outside the backups folder": {"backup": str(victim)},
            "backup elsewhere in the state folder": {"backup": str(self.homes.state / "victim")},
            "stage": {"stage": str(victim)},
            "ledger": {"ledger": str(victim / "data.txt"), "ledger_written": True, "ledger_before": "Replaced.\n"},
            "created folder": {"created": [str(victim)]},
            "created folders as text": {"created": str(root)},
            "moves as text": {"renames": str(victim)},
            "move from outside": {"renames": [{"from": str(victim), "to": str(stage / "old" / "victim")}]},
            "move to outside": {"renames": [{"from": str(stage / "new" / "game-plan"), "to": str(victim)}]},
            "traversal": {
                "renames": [
                    {"from": str(root / ".." / ".." / "victim"), "to": str(stage / "old" / ".." / ".." / "victim")}
                ]
            },
            "absolute name": {"renames": [{"from": str(self.victims[2]), "to": str(stage / "old" / "abs-victim")}]},
            "run id": {"id": "..", "stage": str(INSTALL.real(root).parent / ".skills-folder-stage-..")},
            "relative root": {"root": "skills"},
        }
        before = tree(root)
        for label, values in cases.items():
            with self.subTest(case=label):
                write_journal(self.homes, dict(base, **values))
                code, payload, err = run_cli(self.homes, "install", "--yes")
                self.assertEqual((code, payload["result"]), (2, "usage-error"), err)
                expected = "cannot be read" if label == "moves as text" else "was not acted on"
                self.assertIn(expected, payload["error"])
                self.assertVictimsUntouched()
                self.assertEqual(tree(root), before)
                self.assertTrue((self.homes.state / "journal.json").exists())
        # The same journal naming only its own run's paths is recovered.
        write_journal(self.homes, base)
        code, payload, err = run_cli(self.homes, "install", "--yes")
        self.assertEqual((code, payload["result"]), (1, "recovered"), err)
        self.assertFalse((self.homes.state / "journal.json").exists())

    def test_rollback_acts_on_nothing_when_a_step_leaves_the_run(self) -> None:
        journal = journal_for(self.homes, self.homes.codex, backup=str(self.victims[0]))
        path = write_journal(self.homes, journal)
        log: list[str] = []
        problems = INSTALL.undo(journal, path, log)
        self.assertTrue(problems)
        self.assertTrue(all("nothing was rolled back" in problem for problem in problems), problems)
        self.assertEqual(log, [])
        self.assertVictimsUntouched()
        self.assertTrue(path.exists())

    def test_every_write_lands_in_the_run_folders(self) -> None:
        target = INSTALL.Target("codex", "codex", self.homes.codex)
        plan = INSTALL.Plan("install", target, self.homes.state, INSTALL.load_source())
        outside = INSTALL.Item("../../victim", "older", "upgrade", self.homes.codex / ".." / ".." / "victim", "")
        plan.items.append(outside)
        transaction = INSTALL.Transaction(plan)
        transaction.begin()
        with self.assertRaises(INSTALL.InstallError):
            transaction.run()
        self.assertEqual(transaction.rollback(), [])
        self.assertVictimsUntouched()
        self.assertEqual([path.name for path in self.homes.codex.parent.iterdir()], ["skills"])
        self.assertFalse((self.homes.state / "journal.json").exists())

    def test_recovery_leaves_a_copy_that_changed_after_the_run(self) -> None:
        changed = modify(self.homes.codex, "game-plan", "From an older release.\n")
        edit_ledger(self.homes, self.homes.codex, "game-plan", version="1.0.0", digest=changed)
        real_write = INSTALL.write_atomic

        def crash_at_the_ledger(path, text):
            if Path(path).name == "install-ledger.json":
                raise OSError("power cut")
            return real_write(path, text)

        # Simulate a crash after the swap: the failure happens, but no rollback runs.
        with mock.patch.object(INSTALL, "undo", lambda journal, path, log: []):
            with mock.patch.object(INSTALL, "write_atomic", crash_at_the_ledger):
                code, payload, err = run_here(self.homes, "install", "--yes")
        self.assertEqual(code, 1, err)
        modify(self.homes.codex, "game-plan", "Edited after the crash.\n")
        edited = tree(self.homes.codex / "game-plan")
        code, payload, err = run_here(self.homes, "install", "--yes")
        self.assertEqual((code, payload["result"]), (1, "failed"), err)
        self.assertTrue(any("game-plan in place" in problem for problem in payload["errors"]), payload["errors"])
        self.assertEqual(tree(self.homes.codex / "game-plan"), edited)
        self.assertTrue((self.homes.state / "journal.json").exists())


SLOW_RUN = """
import importlib.util, os, sys, time
from pathlib import Path

installer, marker, release = sys.argv[1:4]
spec = importlib.util.spec_from_file_location("install_slowed", installer)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
real_rename = os.rename


def slow_rename(source, destination):
    # Pause at the first swap, with the journal written and the lock held, until released.
    if not Path(marker).exists():
        Path(marker).write_text("swapping\\n", encoding="utf-8")
        deadline = time.monotonic() + 120
        while not Path(release).exists() and time.monotonic() < deadline:
            time.sleep(0.05)
    return real_rename(source, destination)


module.os.rename = slow_rename
sys.exit(module.main(sys.argv[4:]))
"""


class ConcurrencyTest(HomesTestCase):
    """One run at a time: a second run refuses while the first holds the state lock, recovery included."""

    def setUp(self) -> None:
        super().setUp()
        code, payload, err = run_here(self.homes, "install", "--yes")
        self.assertEqual(code, 0, err)
        for name in ("game-debug", "game-plan", "music-composer"):
            changed = modify(self.homes.codex, name, "From an older release.\n")
            edit_ledger(self.homes, self.homes.codex, name, version="1.0.0", digest=changed)

    def test_a_second_run_refuses_while_the_first_is_mid_swap(self) -> None:
        marker, release = self.homes.root / "swapping.txt", self.homes.root / "release.txt"
        first = subprocess.Popen(
            [sys.executable, *CHILD_FLAGS, "-c", SLOW_RUN, str(INSTALLER), str(marker), str(release), "install",
             "--yes", "--json"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=child_env(self.homes),
            cwd=str(self.homes.root),
        )
        self.addCleanup(lambda: first.poll() is None and first.kill())
        deadline = time.monotonic() + 60
        while not marker.exists():
            self.assertIsNone(first.poll(), "the first run ended before its first swap")
            self.assertLess(time.monotonic(), deadline, "the first run never reached its first swap")
            time.sleep(0.05)
        journal = self.homes.state / "journal.json"
        during = (tree(self.homes.codex.parent), journal.read_bytes(), self.homes.ledger.read_bytes())
        for args in (("install", "--yes"), ("uninstall", "--yes", "--include-modified")):
            with self.subTest(args=args):
                code, payload, err = run_cli(self.homes, *args)
                self.assertEqual((code, payload["result"]), (2, "usage-error"), err)
                self.assertIn("another install.py run is using", payload["error"])
                after = (tree(self.homes.codex.parent), journal.read_bytes(), self.homes.ledger.read_bytes())
                self.assertEqual(after, during)
        code, status, err = run_cli(self.homes, "status", "--target", "codex")
        self.assertEqual((code, status["active"], status["interrupted"]), (0, True, False), err)
        release.write_text("go\n", encoding="utf-8")
        out, err = first.communicate(timeout=120)
        self.assertEqual(first.returncode, 0, err)
        self.assertEqual(json.loads(out)["result"], "done")
        self.assertInstalled(self.homes.codex)
        self.assertFalse(journal.exists())
        self.assertEqual([path.name for path in self.homes.codex.parent.iterdir()], ["skills"])

    def test_the_lock_covers_recovery(self) -> None:
        write_journal(self.homes, journal_for(self.homes, self.homes.codex))
        before = (tree(self.homes.codex), self.homes.ledger.read_bytes())
        with INSTALL.StateLock(self.homes.state):
            code, payload, err = run_cli(self.homes, "install", "--yes")
            self.assertEqual((code, payload["result"]), (2, "usage-error"), err)
            self.assertIn("another install.py run is using", payload["error"])
        self.assertEqual((tree(self.homes.codex), self.homes.ledger.read_bytes()), before)
        self.assertTrue((self.homes.state / "journal.json").exists())
        # Released, the same journal is recovered.
        code, payload, err = run_cli(self.homes, "install", "--yes")
        self.assertEqual((code, payload["result"]), (1, "recovered"), err)

    def test_recovery_waits_while_the_journal_writer_runs(self) -> None:
        journal = self.homes.state / "journal.json"
        write_journal(self.homes, journal_for(self.homes, self.homes.codex, pid=os.getpid(), started=INSTALL.now()))
        code, payload, err = run_cli(self.homes, "install", "--yes")
        self.assertEqual((code, payload["result"]), (2, "usage-error"), err)
        self.assertIn(f"process {os.getpid()}", payload["error"])
        self.assertIn("is still running", payload["error"])
        self.assertTrue(journal.exists())
        code, status, err = run_cli(self.homes, "status", "--target", "codex")
        self.assertEqual((status["active"], status["interrupted"]), (True, False))
        # A live process that started after the journal reuses the ID, so it is not the writer.
        reused = journal_for(self.homes, self.homes.codex, pid=os.getpid(), started="2000-01-01T00:00:00Z")
        write_journal(self.homes, reused)
        code, payload, err = run_cli(self.homes, "install", "--yes")
        self.assertEqual((code, payload["result"]), (1, "recovered"), err)
        write_journal(self.homes, journal_for(self.homes, self.homes.codex, pid=exited_pid(), started=INSTALL.now()))
        code, payload, err = run_cli(self.homes, "install", "--yes")
        self.assertEqual((code, payload["result"]), (1, "recovered"), err)

    def test_the_journal_records_its_writer(self) -> None:
        with mock.patch.object(INSTALL, "undo", lambda journal, path, log: []):
            with mock.patch.object(INSTALL.os, "rename", failing_rename(1, OSError("power cut"))):
                code, payload, err = run_here(self.homes, "install", "--yes")
        self.assertEqual(code, 1, err)
        journal = json.loads((self.homes.state / "journal.json").read_text(encoding="utf-8"))
        self.assertEqual(journal["pid"], os.getpid())
        self.assertLessEqual(abs(INSTALL.parse_time(journal["started"]) - time.time()), 120)
        sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        self.addCleanup(sleeper.wait)
        self.addCleanup(sleeper.kill)
        self.assertTrue(INSTALL.writer_running(sleeper.pid, INSTALL.now()))
        self.assertFalse(INSTALL.writer_running(sleeper.pid, "2000-01-01T00:00:00Z"))
        self.assertFalse(INSTALL.writer_running(exited_pid(), INSTALL.now()))
        self.assertFalse(INSTALL.writer_running(os.getpid(), INSTALL.now()))


class SourceTest(HomesTestCase):
    """The installer validates its own package before it plans anything."""

    def setUp(self) -> None:
        super().setUp()
        self.package = self.homes.root / "package"
        for part in PACKAGE_PARTS:
            source, target = ROOT / part, self.package / part
            if source.is_dir():
                shutil.copytree(source, target)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        self.installer = self.package / "install.py"

    def refused(self, fragment: str) -> None:
        code, payload, err = run_cli(self.homes, "install", "--yes", installer=self.installer)
        self.assertEqual(code, 3, err)
        self.assertEqual(payload["result"], "refused")
        self.assertIn(fragment, payload["error"])
        self.assertFalse((self.homes.home / ".agents").exists())

    def test_the_copied_package_installs(self) -> None:
        code, payload, err = run_cli(self.homes, "install", "--yes", installer=self.installer)
        self.assertEqual(code, 0, err)
        self.assertInstalled(self.homes.codex)

    def test_invalid_frontmatter_is_refused(self) -> None:
        skill = self.package / "skills" / "game-debug" / "SKILL.md"
        skill.write_bytes(skill.read_bytes().replace(b"name: game-debug", b"name: Game-Debug", 1))
        self.refused("game-debug: NAME_FORMAT")

    def test_a_bad_version_file_is_refused(self) -> None:
        (self.package / "VERSION").write_text("1.1\n", encoding="utf-8", newline="\n")
        self.refused("must hold one version")

    def test_a_missing_schema_module_is_refused(self) -> None:
        (self.package / "tools" / "lib" / "skill_frontmatter.py").unlink()
        self.refused("skill_frontmatter.py is missing")

    @unittest.skipUnless(hasattr(os, "symlink"), "no symbolic links")
    def test_a_linked_source_is_refused(self) -> None:
        link = self.package / "skills" / "game-plan" / "linked.md"
        try:
            os.symlink(self.package / "VERSION", link)
        except (OSError, NotImplementedError):
            self.skipTest("symbolic links need extra privileges here")
        self.refused("game-plan: holds a link (linked.md)")

    @unittest.skipUnless(os.name == "nt", "junctions are a Windows feature")
    def test_a_junction_is_a_link_in_the_source_and_the_target(self) -> None:
        import _winapi

        outside = self.homes.root / "outside"
        outside.mkdir()
        _winapi.CreateJunction(str(outside), str(self.package / "skills" / "game-plan" / "joined"))
        self.refused("game-plan: holds a link (joined)")
        (self.package / "skills" / "game-plan" / "joined").rmdir()
        # An installed copy that is a junction is never replaced.
        self.homes.codex.mkdir(parents=True)
        shutil.copytree(ROOT / "skills" / "game-debug", outside / "game-debug")
        _winapi.CreateJunction(str(outside / "game-debug"), str(self.homes.codex / "game-debug"))
        code, payload, err = run_cli(self.homes, "install", "--yes", "--replace-modified", installer=self.installer)
        self.assertEqual(code, 3, err)
        item = next(entry for entry in payload["plan"] if entry["skill"] == "game-debug")
        self.assertEqual((item["state"], item["action"]), ("link", "refuse"))


class DeniedAccess(PermissionError):
    """Windows' Access is denied, on any system."""

    winerror = 5

    def __str__(self) -> str:
        return "[WinError 5] Access is denied: 'game-plan'"


class ErrorMessageTest(HomesTestCase):
    """An operating-system error is a plain message with exit 2, never a traceback."""

    def test_an_os_error_is_a_message_not_a_traceback(self) -> None:
        self.homes.state.parent.mkdir(parents=True, exist_ok=True)
        self.homes.state.write_text("Not a folder.\n", encoding="utf-8", newline="\n")
        for args in (("install", "--yes"), ("uninstall", "--yes")):
            with self.subTest(args=args):
                completed = run_text(self.homes, *args)
                self.assertEqual(completed.returncode, 2, completed.stderr)
                self.assertNotIn("Traceback", completed.stdout + completed.stderr)
                self.assertIn("install.py: [", completed.stdout)
                self.assertIn("skills-folder", completed.stdout)
        self.assertFalse(self.homes.codex.exists())

    def test_access_denied_suggests_closing_a_host_or_editor(self) -> None:
        code, payload, err = run_here(self.homes, "install", "--yes")
        self.assertEqual(code, 0, err)
        changed = modify(self.homes.codex, "game-plan", "From an older release.\n")
        edit_ledger(self.homes, self.homes.codex, "game-plan", version="1.0.0", digest=changed)
        with mock.patch.object(INSTALL.os, "rename", failing_rename(0, DeniedAccess(13, "Access is denied"))):
            code, payload, err = run_here(self.homes, "install", "--yes")
        self.assertEqual((code, payload["result"]), (1, "failed"), err)
        self.assertIn("may be holding files in that folder open", err)
        with mock.patch.object(INSTALL, "read_ledger", lambda path: (_ for _ in ()).throw(DeniedAccess(13, "denied"))):
            code, payload, err = run_here(self.homes, "install", "--yes")
        self.assertEqual((code, payload["result"]), (2, "usage-error"), err)
        self.assertIn("may be holding files in that folder open", err)
        self.assertIsNone(INSTALL.access_hint(OSError("something else")))


BUILDER = ROOT / "skills" / "game-release" / "scripts" / "build_repository_zip.py"


class LinkTest(unittest.TestCase):
    """install.py and the archive builder agree on what is a link."""

    def test_is_link_matches_the_archive_builder(self) -> None:
        spec = importlib.util.spec_from_file_location("build_repository_zip_for_install_tests", BUILDER)
        builder = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = builder
        self.addCleanup(sys.modules.pop, spec.name, None)
        spec.loader.exec_module(builder)
        reparse = stat.FILE_ATTRIBUTE_REPARSE_POINT
        cases = {
            "symbolic link": (stat.S_IFLNK | 0o777, 0, 0, True),
            "Windows symbolic link": (stat.S_IFREG | 0o644, reparse, 0xA000000C, True),
            "junction": (stat.S_IFDIR | 0o755, reparse, 0xA0000003, True),
            "another name surrogate (WSL link)": (stat.S_IFREG | 0o644, reparse, 0xA000001D, True),
            "reparse point with no readable tag": (stat.S_IFREG | 0o644, reparse, 0, True),
            "cloud placeholder, which holds its own data": (stat.S_IFREG | 0o644, reparse, 0x9000001A, False),
            "plain folder": (stat.S_IFDIR | 0o755, 0, 0, False),
        }
        for label, (mode, attributes, tag, expected) in cases.items():
            with self.subTest(case=label):
                info = SimpleNamespace(st_mode=mode, st_file_attributes=attributes, st_reparse_tag=tag)
                with mock.patch.object(os, "lstat", return_value=info), mock.patch.object(
                    os.path, "isjunction", return_value=False, create=True
                ):
                    self.assertEqual(INSTALL.is_link(Path("entry")), expected)
                    self.assertEqual(builder.is_link(Path("entry")), expected)


class UnreadableTest(HomesTestCase):
    """An unreadable copy is refused by name, and removal problems are reported, never raised."""

    def setUp(self) -> None:
        super().setUp()
        code, payload, err = run_here(self.homes, "install", "--yes")
        self.assertEqual(code, 0, err)

    def test_a_walk_error_raises_instead_of_skipping_a_folder(self) -> None:
        with self.assertRaises(OSError):
            INSTALL.tree_files(self.homes.root / "missing")

    def test_an_unreadable_copy_is_refused_by_name(self) -> None:
        real_digest = INSTALL.tree_digest
        target = self.homes.codex / "game-plan"

        def digest(root, include_debris=False):
            if INSTALL.same_path(root, target):
                raise PermissionError(13, "Permission denied", str(target / "references"))
            return real_digest(root, include_debris)

        with mock.patch.object(INSTALL, "tree_digest", digest):
            for args, expected in ((("install", "--yes", "--replace-modified"), 3), (("uninstall", "--yes"), 3)):
                with self.subTest(args=args):
                    code, payload, err = run_here(self.homes, *args)
                    self.assertEqual((code, payload["result"]), (expected, "refused"), err)
                    item = next(entry for entry in payload["plan"] if entry["skill"] == "game-plan")
                    self.assertEqual((item["state"], item["action"]), ("unreadable", "refuse"))
                    self.assertIn("cannot be read", item["reason"])
            code, payload, err = run_here(self.homes, "status", "--target", "codex")
            self.assertEqual(code, 0, err)
        self.assertInstalled(self.homes.codex)

    def test_a_cleanup_that_cannot_remove_the_stage_is_reported(self) -> None:
        def stuck(path):
            raise PermissionError(13, "Permission denied", str(path))

        write_journal(self.homes, journal_for(self.homes, self.homes.codex, committed=True))
        Path(journal_for(self.homes, self.homes.codex)["stage"]).mkdir()
        with mock.patch.object(INSTALL, "remove_tree", stuck):
            code, payload, err = run_here(self.homes, "install", "--yes")
        self.assertEqual((code, payload["result"]), (1, "failed"), err)
        self.assertIn("could not finish the cleanup", " ".join(payload["errors"]))
        self.assertTrue((self.homes.state / "journal.json").exists())
        write_journal(self.homes, journal_for(self.homes, self.homes.codex))
        with mock.patch.object(INSTALL, "remove_tree", stuck):
            code, payload, err = run_here(self.homes, "install", "--yes")
        self.assertEqual((code, payload["result"]), (1, "failed"), err)
        self.assertIn("could not remove", " ".join(payload["errors"]))
        code, payload, err = run_here(self.homes, "install", "--yes")
        self.assertEqual((code, payload["result"]), (1, "recovered"), err)


POSIX_PERMISSIONS = os.name == "posix" and hasattr(os, "geteuid") and os.geteuid() != 0


@unittest.skipUnless(POSIX_PERMISSIONS, "POSIX permissions, as a user other than root")
class PosixPermissionTest(HomesTestCase):
    """Folders without read, write, or search permission are removed and recovered without a traceback."""

    def lock_down(self, folder: Path, mode: int) -> None:
        os.chmod(folder, mode)
        self.addCleanup(lambda: folder.exists() and os.chmod(folder, stat.S_IRWXU))

    def test_remove_tree_keeps_search_permission_on_folders(self) -> None:
        tree_root = self.homes.root / "stage"
        for folder in ("closed", "read-only", "read-only/inner"):
            (tree_root / folder).mkdir(parents=True)
            (tree_root / folder / "file.txt").write_text("x\n", encoding="utf-8")
        os.chmod(tree_root / "read-only" / "file.txt", stat.S_IRUSR)
        self.lock_down(tree_root / "read-only", stat.S_IRUSR | stat.S_IXUSR)
        self.lock_down(tree_root / "closed", 0)
        INSTALL.remove_tree(tree_root)
        self.assertFalse(tree_root.exists())

    def test_recovery_removes_a_stage_holding_an_unreadable_folder(self) -> None:
        code, payload, err = run_here(self.homes, "install", "--yes")
        self.assertEqual(code, 0, err)
        journal = journal_for(self.homes, self.homes.codex, committed=True)
        stage = Path(journal["stage"])
        shutil.copytree(ROOT / "skills" / "game-plan", stage / "old" / "game-plan")
        self.lock_down(stage / "old" / "game-plan" / "references", 0)
        write_journal(self.homes, journal)
        completed = run_text(self.homes, "install", "--yes")
        self.assertEqual(completed.returncode, 1, completed.stderr)
        self.assertNotIn("Traceback", completed.stdout + completed.stderr)
        self.assertIn("Recovered.", completed.stdout)
        self.assertFalse(stage.exists())

    def test_an_unreadable_installed_copy_is_left_and_reported(self) -> None:
        code, payload, err = run_here(self.homes, "install", "--yes")
        self.assertEqual(code, 0, err)
        self.lock_down(self.homes.codex / "game-plan" / "references", 0)
        for args in (("status", "--target", "codex"), ("install", "--yes", "--replace-modified"), ("uninstall", "--yes")):
            with self.subTest(args=args):
                completed = run_text(self.homes, *args)
                self.assertNotIn("Traceback", completed.stdout + completed.stderr)
                self.assertIn("unreadable" if args[0] == "status" else "REFUSED", completed.stdout)
        self.assertTrue((self.homes.codex / "game-plan").exists())


class NetworkTest(HomesTestCase):
    """install.py never opens a socket."""

    def test_no_socket_in_process(self) -> None:
        attempts = []

        class GuardedSocket(socket.socket):
            def __init__(self, *args, **kwargs):
                attempts.append(("socket", args))
                raise OSError("network blocked by the test")

        def blocked(name):
            def call(*args, **kwargs):
                attempts.append((name, args))
                raise OSError("network blocked by the test")

            return call

        with mock.patch.object(socket, "socket", GuardedSocket), mock.patch.object(
            socket, "create_connection", blocked("create_connection")
        ), mock.patch.object(socket, "getaddrinfo", blocked("getaddrinfo")):
            for args in (("install", "--yes"), ("status",), ("uninstall", "--yes")):
                code, payload, err = run_here(self.homes, *args)
                self.assertEqual(code, 0, err)
        self.assertEqual(attempts, [])

    def test_no_socket_in_a_real_run(self) -> None:
        marker = self.homes.root / "network-attempted.txt"
        program = (
            "import runpy, socket, sys\n"
            "def blocked(*args, **kwargs):\n"
            f"    open({str(marker)!r}, 'a', encoding='utf-8').write(repr(args) + '\\n')\n"
            "    raise OSError('network blocked by the test')\n"
            "class GuardedSocket(socket.socket):\n"
            "    def __init__(self, *args, **kwargs):\n"
            "        blocked(*args)\n"
            "socket.socket = GuardedSocket\n"
            "socket.create_connection = blocked\n"
            "socket.getaddrinfo = blocked\n"
            f"sys.argv = [{str(INSTALLER)!r}] + sys.argv[1:]\n"
            f"runpy.run_path({str(INSTALLER)!r}, run_name='__main__')\n"
        )
        for args in (("install", "--yes"), ("status",), ("uninstall", "--yes")):
            completed = subprocess.run(
                [sys.executable, *CHILD_FLAGS, "-c", program, *args, "--json"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=child_env(self.homes),
                cwd=str(self.homes.root),
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertFalse(marker.exists(), marker.read_text(encoding="utf-8") if marker.exists() else "")


class PythonFloorTest(HomesTestCase):
    def test_an_older_python_is_told_the_floor(self) -> None:
        err = io.StringIO()
        with mock.patch.dict(os.environ, self.homes.env), mock.patch.object(sys, "version_info", (3, 10, 14, "final", 0)):
            with contextlib.redirect_stderr(err):
                code = INSTALL.main(["install", "--yes"])
        self.assertEqual(code, 2)
        self.assertIn("needs Python 3.11 or later", err.getvalue())
        self.assertFalse(self.homes.codex.exists())


class EndToEndTest(HomesTestCase):
    """install, status, and uninstall as a user runs them, for every target."""

    def test_every_target_round_trip(self) -> None:
        for target in ("codex", "codex-legacy", "codex-project", "claude", "claude-project", "dest"):
            with self.subTest(target=target):
                homes = Homes()
                self.addCleanup(homes.cleanup)
                self.homes = homes
                project = homes.root / "game"
                project.mkdir()
                where = {
                    "codex": ("--target", "codex"),
                    "codex-legacy": ("--target", "codex-legacy"),
                    "codex-project": ("--target", "codex-project", "--project", str(project)),
                    "claude": ("--target", "claude"),
                    "claude-project": ("--target", "claude-project", "--project", str(project)),
                    "dest": ("--dest", str(homes.root / "custom" / "skills")),
                }[target]
                code, payload, err = run_cli(homes, "install", *where, "--yes")
                self.assertEqual(code, 0, err)
                root = Path(payload["destination"])
                self.assertInstalled(root)
                code, status, err = run_cli(homes, "status", *where)
                self.assertEqual(code, 0, err)
                self.assertEqual({item["state"] for item in status["targets"][0]["skills"]}, {"current"})
                code, removed, err = run_cli(homes, "uninstall", *where, "--yes")
                self.assertEqual(code, 0, err)
                self.assertNoSuiteSkills(root)
                [backup] = homes.backups()
                self.assertEqual(sorted(path.name for path in backup.iterdir() if path.is_dir()), SKILLS)
                for result in (payload, status, removed):
                    self.assertInsideHomes(result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
