#!/usr/bin/env python3
"""Plant package problems in temporary copies and check tools/verify_package.py.

    python -B tests/verify/test_verify_package.py
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERIFIER = ROOT / "tools" / "verify_package.py"
CHILD_FLAGS = ["-B", "-X", "warn_default_encoding", "-W", "error::EncodingWarning"]
# Built from fragments so this file never contains the term it plants.
PRIVATE_TERM = "Office" + "Wars"


def package_files() -> list[str]:
    """The files a fresh checkout would contain."""
    listed = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        capture_output=True,
        check=False,
    )
    if listed.returncode == 0:
        names = listed.stdout.decode("utf-8", "surrogateescape").split("\0")
        return sorted(name for name in names if name and (ROOT / name).is_file())
    return sorted(
        path.relative_to(ROOT).as_posix()
        for path in ROOT.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(ROOT).parts
    )


def copy_package(destination: Path) -> Path:
    for name in package_files():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    return destination


def run_verifier(root: Path) -> tuple[int, dict]:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    completed = subprocess.run(
        [sys.executable, *CHILD_FLAGS, str(VERIFIER), "--root", str(root), "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )
    if completed.returncode not in (0, 1):
        raise AssertionError(f"verifier failed: {completed.returncode}\n{completed.stderr}")
    return completed.returncode, json.loads(completed.stdout)


def codes_by_path(payload: dict) -> set[tuple[str, str]]:
    return {(item["code"], item["path"]) for item in payload["problems"]}


def symlinks_supported() -> bool:
    """Windows creates symbolic links only with Developer Mode or elevation."""
    with tempfile.TemporaryDirectory(prefix="verify-symlink-probe-") as temp:
        try:
            os.symlink(Path(temp) / "target", Path(temp) / "link")
        except (OSError, NotImplementedError):
            return False
    return True


SYMLINKS = symlinks_supported()
DANGLING = "templates/dangling.md"


def plant_dangling_symlinks(root: Path) -> None:
    """A dangling link outside the skills and one standing in for a skill's metadata."""
    os.symlink("missing-target.md", root / DANGLING)
    metadata = root / "skills" / "game-debug" / "agents" / "openai.yaml"
    metadata.unlink()
    os.symlink("missing-openai.yaml", metadata)


BROKEN_LINK_PROBLEMS = {
    ("BROKEN_SYMLINK", DANGLING),
    ("BROKEN_SYMLINK", "skills/game-debug/agents/openai.yaml"),
    ("OPENAI_YAML_MISSING", "skills/game-debug"),
}


class FilesystemInventoryTest(unittest.TestCase):
    """An extracted archive: no .git, so every file is checked."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="verify-package-")
        self.root = copy_package(Path(self.temp.name) / "package")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_clean_copy_passes(self) -> None:
        returncode, payload = run_verifier(self.root)
        self.assertEqual(payload["problems"], [])
        self.assertEqual(returncode, 0)
        self.assertEqual(payload["inventory"], "filesystem")

    def test_every_planted_problem_is_reported_in_one_run(self) -> None:
        reference = self.root / "skills" / "game-plan" / "references" / "project-profile.md"
        reference.write_bytes(reference.read_bytes().replace(b"\n", b"\r\n"))
        notice = self.root / "NOTICE"
        notice.write_bytes(b"\xef\xbb\xbf" + notice.read_bytes())
        skill = self.root / "skills" / "game-debug" / "SKILL.md"
        skill.write_bytes(skill.read_bytes().replace(b"name: game-debug", b"name: Game-Debug", 1))
        cache = self.root / "skills" / "game-implement" / "scripts" / "__pycache__"
        cache.mkdir(parents=True)
        (cache / "helper.cpython-313.pyc").write_bytes(b"\x00\x01")
        readme = self.root / "README.md"
        readme.write_bytes(readme.read_bytes() + f"Built for {PRIVATE_TERM}.\n".encode("utf-8"))

        returncode, payload = run_verifier(self.root)
        found = codes_by_path(payload)
        expected = {
            ("CRLF", "skills/game-plan/references/project-profile.md"),
            ("BOM", "NOTICE"),
            ("FRONTMATTER_NAME_FORMAT", "skills/game-debug/SKILL.md"),
            ("FRONTMATTER_NAME_FOLDER", "skills/game-debug/SKILL.md"),
            ("DEBRIS", "skills/game-implement/scripts/__pycache__/helper.cpython-313.pyc"),
            ("FORBIDDEN_TERM", "README.md"),
        }
        self.assertEqual(returncode, 1)
        self.assertEqual(found, expected, payload["problems"])
        messages = [item["message"] for item in payload["problems"]]
        self.assertEqual(len(messages), len(set(messages)), "each problem needs its own message")

    def test_git_metadata_is_excluded_by_path_part(self) -> None:
        # A worktree or submodule has a .git file; nested .git folders also occur.
        (self.root / ".git").write_text("gitdir: /nowhere\n", encoding="utf-8", newline="\n")
        nested = self.root / "templates" / ".git"
        nested.mkdir()
        (nested / "config").write_bytes(f"[remote]\r\n\turl = {PRIVATE_TERM}\r\n".encode("utf-8"))
        returncode, payload = run_verifier(self.root)
        self.assertEqual(payload["problems"], [])
        self.assertEqual(returncode, 0)

    def test_text_policy_and_missing_prompt(self) -> None:
        template = self.root / "templates" / "GAME_PROJECT_PROFILE.template.md"
        template.write_bytes(template.read_bytes() + "Café notes.\n".encode("cp1252"))
        license_file = self.root / "LICENSE"
        license_file.write_bytes(license_file.read_bytes().rstrip(b"\n"))
        prompt = self.root / "skills" / "game-debug" / "agents" / "openai.yaml"
        kept = [
            line
            for line in prompt.read_text(encoding="utf-8").splitlines(keepends=True)
            if "default_prompt" not in line
        ]
        prompt.write_text("".join(kept), encoding="utf-8", newline="\n")
        returncode, payload = run_verifier(self.root)
        self.assertEqual(returncode, 1)
        self.assertEqual(
            codes_by_path(payload),
            {
                ("NOT_UTF8", "templates/GAME_PROJECT_PROFILE.template.md"),
                ("NO_FINAL_NEWLINE", "LICENSE"),
                ("DEFAULT_PROMPT_MISSING", "skills/game-debug/agents/openai.yaml"),
            },
            payload["problems"],
        )

    def test_a_package_without_skills(self) -> None:
        shutil.rmtree(self.root / "skills")
        returncode, payload = run_verifier(self.root)
        self.assertEqual(returncode, 1)
        self.assertEqual(
            codes_by_path(payload),
            {
                ("NO_SKILLS", "skills"),
                # The auditor's generated copy went with the skills.
                ("COPY_MISSING", "skills/game-skill-auditor/scripts/skill_frontmatter.py"),
            },
        )

    def test_an_internal_error_exits_3(self) -> None:
        # Break the inventory walk; the verifier must not report a failed check.
        program = (
            "import os, runpy, sys\n"
            "def broken_walk(*args, **kwargs):\n"
            "    raise RuntimeError('walk failed')\n"
            "os.walk = broken_walk\n"
            f"sys.argv = ['verify_package.py', '--root', {str(self.root)!r}]\n"
            f"runpy.run_path({str(VERIFIER)!r}, run_name='__main__')\n"
        )
        completed = subprocess.run(
            [sys.executable, *CHILD_FLAGS, "-c", program],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
            check=False,
        )
        self.assertEqual(completed.returncode, 3, completed.stdout + completed.stderr)
        self.assertIn("internal error", completed.stderr)
        self.assertIn("walk failed", completed.stderr)
        self.assertEqual(completed.stdout, "")

    @unittest.skipUnless(SYMLINKS, "symbolic links need extra privileges here")
    def test_dangling_symlinks_are_problems_not_internal_errors(self) -> None:
        plant_dangling_symlinks(self.root)
        returncode, payload = run_verifier(self.root)
        self.assertEqual(payload["inventory"], "filesystem")
        self.assertEqual(codes_by_path(payload), BROKEN_LINK_PROBLEMS, payload["problems"])
        self.assertEqual(returncode, 1)

    def test_generated_copies_must_match_their_source(self) -> None:
        copy = self.root / "skills" / "game-skill-auditor" / "scripts" / "skill_frontmatter.py"
        lines = copy.read_bytes().split(b"\n")
        lines[5] += b" # drift"
        copy.write_bytes(b"\n".join(lines))
        returncode, payload = run_verifier(self.root)
        self.assertEqual(returncode, 1)
        self.assertEqual(
            [(item["code"], item["path"], item["line"]) for item in payload["problems"]],
            [("COPY_DRIFT", "skills/game-skill-auditor/scripts/skill_frontmatter.py", 6)],
        )
        copy.write_bytes(b"\n".join(lines[1:]))
        returncode, payload = run_verifier(self.root)
        self.assertEqual(returncode, 1)
        self.assertEqual(
            codes_by_path(payload),
            {("COPY_HEADER", "skills/game-skill-auditor/scripts/skill_frontmatter.py")},
        )
        (self.root / "tools" / "lib" / "skill_frontmatter.py").unlink()
        copy.unlink()
        returncode, payload = run_verifier(self.root)
        self.assertEqual(returncode, 1)
        self.assertEqual(
            {(code, path) for code, path in codes_by_path(payload) if code == "COPY_MISSING"},
            {
                ("COPY_MISSING", "tools/lib/skill_frontmatter.py"),
                ("COPY_MISSING", "skills/game-skill-auditor/scripts/skill_frontmatter.py"),
            },
        )

    def test_missing_files_and_prompts(self) -> None:
        (self.root / "skills" / "game-ux-audit" / "agents" / "openai.yaml").unlink()
        prompt = self.root / "skills" / "game-qa-cleanup" / "agents" / "openai.yaml"
        prompt.write_text(
            prompt.read_text(encoding="utf-8").replace("$game-qa-cleanup", "$game-qa-cleanup-extra"),
            encoding="utf-8",
            newline="\n",
        )
        (self.root / "skills" / "orphan" / "notes").mkdir(parents=True)
        (self.root / "skills" / "orphan" / "notes" / "todo.md").write_text("notes\n", encoding="utf-8", newline="\n")
        returncode, payload = run_verifier(self.root)
        found = codes_by_path(payload)
        self.assertEqual(returncode, 1)
        self.assertIn(("OPENAI_YAML_MISSING", "skills/game-ux-audit"), found)
        self.assertIn(("DEFAULT_PROMPT_NAME", "skills/game-qa-cleanup/agents/openai.yaml"), found)
        self.assertIn(("SKILL_MD_MISSING", "skills/orphan"), found)


@unittest.skipUnless(shutil.which("git"), "git is not installed")
class GitInventoryTest(unittest.TestCase):
    """A git checkout: ignored files are skipped, untracked files are checked."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="verify-package-git-")
        self.root = copy_package(Path(self.temp.name) / "package")
        for arguments in (["init", "-q"], ["add", "-A"]):
            subprocess.run(
                ["git", "-c", "core.autocrlf=false", "-C", str(self.root), *arguments],
                capture_output=True,
                check=True,
            )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_ignored_debris_is_skipped_and_untracked_debris_is_reported(self) -> None:
        cache = self.root / "skills" / "game-implement" / "scripts" / "__pycache__"
        cache.mkdir(parents=True)
        (cache / "helper.cpython-313.pyc").write_bytes(b"\x00\x01")
        (self.root / "skills" / "game-plan" / ".DS_Store").write_bytes(b"\x00\x00\x00\x01Bud1")
        returncode, payload = run_verifier(self.root)
        self.assertEqual(payload["inventory"], "git")
        self.assertEqual(codes_by_path(payload), {("DEBRIS", "skills/game-plan/.DS_Store")})
        self.assertEqual(returncode, 1)

    @unittest.skipUnless(SYMLINKS, "symbolic links need extra privileges here")
    def test_tracked_dangling_symlinks_are_reported(self) -> None:
        plant_dangling_symlinks(self.root)
        # core.symlinks=true makes Git for Windows record the links as links.
        subprocess.run(
            ["git", "-c", "core.autocrlf=false", "-c", "core.symlinks=true", "-C", str(self.root), "add", "-A"],
            capture_output=True,
            check=True,
        )
        tracked = subprocess.run(
            ["git", "-C", str(self.root), "ls-files", "--", DANGLING],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        self.assertEqual(tracked.stdout.strip(), DANGLING)
        returncode, payload = run_verifier(self.root)
        self.assertEqual(payload["inventory"], "git")
        self.assertEqual(codes_by_path(payload), BROKEN_LINK_PROBLEMS, payload["problems"])
        self.assertEqual(returncode, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
