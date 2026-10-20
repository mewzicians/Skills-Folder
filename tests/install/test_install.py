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
import subprocess
import tempfile
import unittest
from pathlib import Path
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
        self.assertEqual(tree(homes.home), {})
        self.assertFalse(homes.ledger.exists())

    def test_an_interrupted_run_is_rolled_back_on_the_next_run(self) -> None:
        # Simulate a crash: the failure happens, but no rollback runs.
        with mock.patch.object(INSTALL, "undo", lambda journal, path, log: []):
            with mock.patch.object(INSTALL.os, "rename", failing_rename(3, OSError("power cut"))):
                code, payload, err = run_here(self.homes, "install", "--yes")
        self.assertEqual(code, 1, err)
        self.assertTrue((self.homes.state / "journal.json").exists())
        self.assertNotEqual(tree(self.homes.codex), self.before)
        code, payload, err = run_cli(self.homes, "status", "--target", "codex")
        self.assertTrue(payload["interrupted"])
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
