#!/usr/bin/env python3
"""Check what skills/game-release/scripts/build_repository_zip.py packages, excludes, and refuses.

Every risky file is generated at test time with placeholder text; the
repository never holds a real or fake secret.

    python -B tests/zip/test_build_repository_zip.py
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT / "skills" / "game-release" / "scripts" / "build_repository_zip.py"
CHILD_FLAGS = ["-B", "-X", "warn_default_encoding", "-W", "error::EncodingWarning"]
# Built from fragments so this file never spells a private vault folder.
VAULT = "." + "obsidian"

TRACKED = {
    "index.html": "game\n",
    "README.md": "readme\n",
    "assets/sprite.txt": "sprite\n",
    ".gitignore": "*.log\n",
    ".github/workflows/ci.yml": "ci\n",
}
RISKY = {
    ".env": "placeholder\n",
    ".venv/pyvenv.cfg": "placeholder\n",
    "node_modules/pkg/index.js": "placeholder\n",
    ".vscode/settings.json": "{}\n",
    f"{VAULT}/workspace.json": "{}\n",
    "CONTEXT_CONTINUITY.task.md": "placeholder\n",
    "id_rsa": "placeholder\n",
    "deploy.pem": "placeholder\n",
    ".suite-backup-20990101/SKILL.md": "placeholder\n",
}
UNTRACKED = {"notes.txt": "notes\n"}
IGNORED = {"debug.log": "log\n"}
RISKY_SHOWN = {
    ".env": "default exclude .env*",
    ".venv/": "default exclude .venv/",
    "node_modules/": "default exclude node_modules/",
    ".vscode/": "default exclude .vscode/",
    f"{VAULT}/": f"default exclude {VAULT}/",
    "CONTEXT_CONTINUITY.task.md": "default exclude CONTEXT_CONTINUITY*.md",
    "id_rsa": "default exclude id_rsa*",
    "deploy.pem": "default exclude *.pem",
    ".suite-backup-20990101/": "default exclude *backup*/",
    ".gitignore": "default exclude .git*",
    ".github/": "default exclude .git*",
}
# Release signing material and credentials, as {path: (shown path, pattern)}.
RELEASE_SECRETS = {
    "android/release.keystore": ("android/release.keystore", "*.keystore"),
    "android/upload.jks": ("android/upload.jks", "*.jks"),
    "certs/dist.p12": ("certs/dist.p12", "*.p12"),
    "certs/dist.pfx": ("certs/dist.pfx", "*.pfx"),
    "AuthKey_PLACEHOLDER.p8": ("AuthKey_PLACEHOLDER.p8", "*.p8"),
    "ios/app.mobileprovision": ("ios/app.mobileprovision", "*.mobileprovision"),
    "putty.ppk": ("putty.ppk", "*.ppk"),
    "id_dsa": ("id_dsa", "id_dsa*"),
    "credentials.json": ("credentials.json", "credentials.json"),
    "config/secrets.yaml": ("config/secrets.yaml", "secrets.*"),
    "save.bak": ("save.bak", "*.bak"),
    "notes.txt~": ("notes.txt~", "*~"),
    "android/app/google-services.json": ("android/app/google-services.json", "google-services.json"),
    "ios/GoogleService-Info.plist": ("ios/GoogleService-Info.plist", "GoogleService-Info.plist"),
    "config/prod.env": ("config/prod.env", "*.env"),
    "web/.htpasswd": ("web/.htpasswd", ".htpasswd"),
    ".docker/config.json": (".docker/", ".docker/"),
    "deploy/kube/config": ("deploy/kube/config", "kube/config"),
    ".kube/config": (".kube/", ".kube/"),
    ".gnupg/pubring.kbx": (".gnupg/", ".gnupg/"),
    "secring.gpg": ("secring.gpg", "*.gpg"),
    "infra/terraform.tfstate": ("infra/terraform.tfstate", "*.tfstate"),
    "infra/terraform.tfstate.backup": ("infra/terraform.tfstate.backup", "*.tfstate.*"),
    ".vs/slnx.sqlite": (".vs/", ".vs/"),
}
# Ordinary files whose names resemble a release secret.
LOOKALIKES = {
    "docs/environment.md": "docs\n",
    "src/keystore.py": "code\n",
    "kube/deploy.yaml": "manifest\n",
    "config/settings.json": "{}\n",
    "infra/main.tf": "terraform\n",
}
GIT = ["git", "-c", "core.autocrlf=false", "-c", "user.name=Probe", "-c", "user.email=probe@example.com"]


def write_files(root: Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")


def run_builder(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *CHILD_FLAGS, str(BUILDER), *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
        check=False,
    )


def symlinks_supported() -> bool:
    """Windows creates symbolic links only with Developer Mode or elevation."""
    with tempfile.TemporaryDirectory(prefix="zip-symlink-probe-") as temp:
        try:
            os.symlink(Path(temp) / "target", Path(temp) / "link")
        except (OSError, NotImplementedError):
            return False
    return True


class BuilderTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="zip-builder-")
        self.base = Path(self.temp.name)
        self.source = self.base / "mirror"
        write_files(self.source, {**TRACKED, **RISKY, **UNTRACKED, **IGNORED})

    def tearDown(self) -> None:
        self.temp.cleanup()

    def init_git(self) -> None:
        subprocess.run([*GIT, "-C", str(self.source), "init", "-q"], check=True, capture_output=True)
        subprocess.run([*GIT, "-C", str(self.source), "add", *TRACKED], check=True, capture_output=True)
        subprocess.run([*GIT, "-C", str(self.source), "commit", "-q", "-m", "probe"], check=True, capture_output=True)

    def build(self, *arguments: str, output: str = "out.zip") -> tuple[int, dict, str]:
        completed = run_builder(str(self.source), str(self.base / output), *arguments)
        payload = json.loads(completed.stdout) if completed.returncode == 0 else {}
        return completed.returncode, payload, completed.stderr

    def excluded(self, payload: dict) -> dict[str, str]:
        return {item["path"]: item["reason"] for item in payload["excluded"]}

    def archive_names(self, output: str = "out.zip") -> list[str]:
        with zipfile.ZipFile(self.base / output) as archive:
            return archive.namelist()


@unittest.skipUnless(shutil.which("git"), "git is not installed")
class GitTreeTest(BuilderTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.init_git()

    def test_risky_files_are_excluded_and_listed(self) -> None:
        returncode, payload, stderr = self.build()
        self.assertEqual(returncode, 0, stderr)
        self.assertEqual(payload["packaged"], ["README.md", "assets/sprite.txt", "index.html", "notes.txt"])
        self.assertEqual(self.archive_names(), payload["packaged"])
        excluded = self.excluded(payload)
        for shown, reason in RISKY_SHOWN.items():
            self.assertTrue(excluded.get(shown, "").startswith(reason), (shown, excluded.get(shown)))
        self.assertEqual(excluded["debug.log"], "git-ignored, never packaged")
        self.assertEqual(excluded[".git/"], "git metadata, never packaged")

    def test_include_overrides_a_default_exclude_but_never_an_ignored_file(self) -> None:
        returncode, payload, stderr = self.build("--include", ".github", "--include", ".env", "--include", "*.log")
        self.assertEqual(returncode, 0, stderr)
        self.assertIn(".github/workflows/ci.yml", payload["packaged"])
        self.assertIn(".env", payload["packaged"])
        self.assertNotIn("debug.log", payload["packaged"])
        self.assertEqual(self.excluded(payload)["debug.log"], "git-ignored, never packaged")

    def test_git_tracked_packages_only_what_git_tracks(self) -> None:
        tracked = subprocess.run(
            ["git", "-C", str(self.source), "ls-files"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        ).stdout.split()
        returncode, payload, stderr = self.build("--git-tracked")
        self.assertEqual(returncode, 0, stderr)
        excluded = self.excluded(payload)
        # Repository metadata matches the .git* default exclude, like any other.
        self.assertEqual(payload["packaged"], ["README.md", "assets/sprite.txt", "index.html"])
        self.assertTrue(excluded[".gitignore"].startswith("default exclude .git*"))
        self.assertEqual(excluded["notes.txt"], "untracked")
        self.assertEqual(excluded["debug.log"], "git-ignored, never packaged")
        returncode, payload, stderr = self.build("--git-tracked", "--include", ".git?*")
        self.assertEqual(returncode, 0, stderr)
        self.assertEqual(payload["packaged"], sorted(tracked))
        self.assertEqual(self.archive_names(), sorted(tracked))

    def test_an_allowlist_must_match_the_source(self) -> None:
        allowlist = self.base / "allowlist.txt"
        allowlist.write_text("# public files\nREADME.md\nindex.html\n", encoding="utf-8", newline="\n")
        returncode, _, stderr = self.build("--allowlist", str(allowlist))
        self.assertEqual(returncode, 1)
        self.assertIn("assets/sprite.txt: not in the allowlist", stderr)
        self.assertIn("notes.txt: not in the allowlist", stderr)
        self.assertFalse((self.base / "out.zip").exists())

        allowlist.write_text("README.md\nindex.html\nassets/sprite.txt\nnotes.txt\nmissing.txt\n.env\ndebug.log\n", encoding="utf-8")
        returncode, _, stderr = self.build("--allowlist", str(allowlist))
        self.assertEqual(returncode, 1)
        self.assertIn("missing.txt: listed but not found", stderr)
        self.assertIn(".env: default exclude .env*", stderr)
        self.assertIn("debug.log: git-ignored, never packaged", stderr)

        allowlist.write_text("README.md\nindex.html\nassets/sprite.txt\nnotes.txt\n.env\n", encoding="utf-8")
        returncode, payload, stderr = self.build("--allowlist", str(allowlist), "--include", ".env")
        self.assertEqual(returncode, 0, stderr)
        self.assertEqual(payload["packaged"], [".env", "README.md", "assets/sprite.txt", "index.html", "notes.txt"])

    def test_git_tracked_refuses_a_dirty_tree_unless_allowed(self) -> None:
        head = subprocess.run(
            ["git", "-C", str(self.source), "rev-parse", "HEAD"], capture_output=True, check=True
        ).stdout.decode("ascii").strip()
        returncode, payload, stderr = self.build("--git-tracked")
        self.assertEqual(returncode, 0, stderr)
        self.assertEqual((payload["gitHead"], payload["gitDirty"]), (head, False))
        (self.source / "index.html").write_text("uncommitted edit\n", encoding="utf-8", newline="\n")
        returncode, _, stderr = self.build("--git-tracked", output="dirty.zip")
        self.assertEqual(returncode, 1)
        self.assertIn("differ from HEAD: index.html", stderr)
        self.assertIn("--allow-dirty", stderr)
        self.assertFalse((self.base / "dirty.zip").exists())
        returncode, payload, stderr = self.build("--git-tracked", "--allow-dirty", "--stored", output="dirty.zip")
        self.assertEqual(returncode, 0, stderr)
        self.assertEqual((payload["gitHead"], payload["gitDirty"]), (head, True))
        with zipfile.ZipFile(self.base / "dirty.zip") as archive:
            self.assertEqual(archive.read("index.html"), b"uncommitted edit\n")
        # The default walk records the same facts but does not refuse.
        returncode, payload, stderr = self.build(output="walk.zip")
        self.assertEqual(returncode, 0, stderr)
        self.assertEqual((payload["gitHead"], payload["gitDirty"]), (head, True))

    def test_executable_bits_follow_the_git_index(self) -> None:
        script = self.source / "tools" / "run.sh"
        write_files(self.source, {"tools/run.sh": "#!/bin/sh\n"})
        script.chmod(0o755)
        subprocess.run([*GIT, "-C", str(self.source), "add", "tools/run.sh"], check=True, capture_output=True)
        subprocess.run(
            [*GIT, "-C", str(self.source), "update-index", "--chmod=+x", "tools/run.sh"],
            check=True,
            capture_output=True,
        )
        subprocess.run([*GIT, "-C", str(self.source), "commit", "-q", "-m", "tool"], check=True, capture_output=True)
        returncode, payload, stderr = self.build("--git-tracked")
        self.assertEqual(returncode, 0, stderr)
        self.assertEqual(payload["executable"], ["tools/run.sh"])
        with zipfile.ZipFile(self.base / "out.zip") as archive:
            modes = {info.filename: info.external_attr >> 16 for info in archive.infolist()}
        self.assertEqual(modes.pop("tools/run.sh"), 0o100755)
        self.assertEqual(set(modes.values()), {0o100644})

    def test_a_wholly_ignored_source_packages_nothing(self) -> None:
        outer = self.base / "outer"
        outer.mkdir()
        subprocess.run([*GIT, "-C", str(outer), "init", "-q"], check=True, capture_output=True)
        (outer / ".gitignore").write_text("mirror/\n", encoding="utf-8", newline="\n")
        write_files(outer / "mirror", {"a.txt": "a\n"})
        completed = run_builder(str(outer / "mirror"), str(self.base / "outer.zip"))
        self.assertEqual(completed.returncode, 1)
        self.assertIn("no packageable files", completed.stderr)


@unittest.skipUnless(shutil.which("git"), "git is not installed")
class GitFailureTest(BuilderTestCase):
    """Inside a git work tree, a git that cannot answer refuses the build."""

    def setUp(self) -> None:
        super().setUp()
        self.init_git()

    def build_with(self, environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, *CHILD_FLAGS, str(BUILDER), str(self.source), str(self.base / "out.zip")],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=dict(environment, PYTHONDONTWRITEBYTECODE="1"),
            check=False,
        )

    def assert_refused(self, completed: subprocess.CompletedProcess[str], reason: str) -> None:
        self.assertEqual(completed.returncode, 1, completed.stdout)
        self.assertIn("git cannot read the work tree", completed.stderr)
        self.assertIn(reason, completed.stderr)
        self.assertFalse((self.base / "out.zip").exists())

    def test_git_missing_from_path(self) -> None:
        empty = self.base / "no-git-here"
        empty.mkdir()
        environment = {key: value for key, value in os.environ.items() if key.upper() != "PATH"}
        completed = self.build_with(dict(environment, PATH=str(empty)))
        self.assert_refused(completed, "git is not installed or not on PATH")

    def test_a_broken_repository(self) -> None:
        (self.source / ".git" / "HEAD").write_text("not a ref\n", encoding="utf-8", newline="\n")
        self.assert_refused(self.build_with(dict(os.environ)), "fatal:")

    def test_a_failing_git_in_process(self) -> None:
        module = load_builder()
        refusal = subprocess.CompletedProcess([], 128, b"", b"fatal: detected dubious ownership\n")
        for outcome in (refusal, OSError("git cannot start")):
            with self.subTest(outcome=outcome):
                patch = {"side_effect": outcome} if isinstance(outcome, Exception) else {"return_value": outcome}
                with mock.patch.object(module.subprocess, "run", **patch):
                    with self.assertRaisesRegex(module.BuildError, "git cannot read the work tree"):
                        module.build(self.source, self.base / "in-process.zip", [])
        self.assertFalse((self.base / "in-process.zip").exists())

    def test_redirect_variables_are_ignored(self) -> None:
        elsewhere = self.base / "elsewhere"
        elsewhere.mkdir()
        environment = dict(
            os.environ,
            GIT_DIR=str(elsewhere / "missing.git"),
            GIT_WORK_TREE=str(elsewhere),
            GIT_INDEX_FILE=str(elsewhere / "index"),
        )
        completed = self.build_with(environment)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertNotIn("debug.log", payload["packaged"])
        self.assertEqual(self.excluded(payload)["debug.log"], "git-ignored, never packaged")


class DeterminismTest(BuilderTestCase):
    """No git here: a plain folder, as when building from an extracted copy."""

    def test_digests_and_entry_metadata(self) -> None:
        first = self.build(output="first.zip")
        second = self.build(output="second.zip")
        stored = self.build("--stored", output="stored.zip")
        stored_again = self.build("--stored", output="stored-again.zip")
        for returncode, _, stderr in (first, second, stored, stored_again):
            self.assertEqual(returncode, 0, stderr)
        self.assertEqual(first[1]["zipSha256"], second[1]["zipSha256"])
        self.assertEqual(stored[1]["zipSha256"], stored_again[1]["zipSha256"])
        self.assertNotEqual(first[1]["zipSha256"], stored[1]["zipSha256"])
        self.assertEqual(first[1]["contentDigest"], stored[1]["contentDigest"])
        names = first[1]["packaged"]
        manifest = "".join(
            f"{hashlib.sha256((self.source / name).read_bytes()).hexdigest()}  {name}\n" for name in names
        )
        self.assertEqual(first[1]["contentDigest"], hashlib.sha256(manifest.encode("utf-8")).hexdigest().upper())
        for output, compression in (("first.zip", zipfile.ZIP_DEFLATED), ("stored.zip", zipfile.ZIP_STORED)):
            with zipfile.ZipFile(self.base / output) as archive:
                for info in archive.infolist():
                    self.assertEqual(info.create_system, 3)
                    self.assertEqual(info.date_time, (1980, 1, 1, 0, 0, 0))
                    self.assertEqual(info.compress_type, compression)
                    self.assertEqual(info.external_attr >> 16, 0o100644)

    def test_without_git_every_risky_file_is_still_excluded(self) -> None:
        returncode, payload, stderr = self.build()
        self.assertEqual(returncode, 0, stderr)
        self.assertEqual(
            payload["packaged"], ["README.md", "assets/sprite.txt", "debug.log", "index.html", "notes.txt"]
        )
        excluded = self.excluded(payload)
        for shown, reason in RISKY_SHOWN.items():
            self.assertTrue(excluded.get(shown, "").startswith(reason), (shown, excluded.get(shown)))
        completed = run_builder(str(self.source), str(self.base / "tracked.zip"), "--git-tracked")
        if shutil.which("git"):
            self.assertEqual(completed.returncode, 1)
            self.assertIn("--git-tracked needs", completed.stderr)

    def test_refusals(self) -> None:
        completed = run_builder(str(self.source), str(self.source / "inside.zip"))
        self.assertEqual(completed.returncode, 1)
        self.assertIn("outside the source folder", completed.stderr)
        completed = run_builder(str(self.source), str(self.base / "out.tar"))
        self.assertEqual(completed.returncode, 1)
        completed = run_builder(str(self.source), str(self.base / "out.zip"), "--require", "missing.txt")
        self.assertEqual(completed.returncode, 1)
        self.assertIn("missing.txt", completed.stderr)
        self.assertFalse((self.base / "out.zip").exists())

    def test_no_git_facts_outside_a_work_tree(self) -> None:
        returncode, payload, stderr = self.build()
        self.assertEqual(returncode, 0, stderr)
        self.assertEqual((payload["gitHead"], payload["gitDirty"], payload["executable"]), (None, None, []))

    def test_a_git_folder_in_any_case_is_never_packaged(self) -> None:
        write_files(self.source, {"vendor/.Git/config": "placeholder\n", "vendor/lib.js": "lib\n"})
        returncode, payload, stderr = self.build("--include", "*")
        self.assertEqual(returncode, 0, stderr)
        self.assertNotIn("vendor/.Git/config", payload["packaged"])
        self.assertIn("vendor/lib.js", payload["packaged"])
        self.assertEqual(self.excluded(payload)["vendor/.Git/"], "git metadata, never packaged")

    def test_an_allowlist_may_start_with_a_byte_order_mark(self) -> None:
        allowlist = self.base / "allowlist.txt"
        allowlist.write_bytes(b"\xef\xbb\xbfREADME.md\nindex.html\nassets/sprite.txt\nnotes.txt\ndebug.log\n")
        returncode, payload, stderr = self.build("--allowlist", str(allowlist))
        self.assertEqual(returncode, 0, stderr)
        self.assertEqual(payload["packaged"], ["README.md", "assets/sprite.txt", "debug.log", "index.html", "notes.txt"])

    def test_control_characters_are_refused_in_archive_names(self) -> None:
        module = load_builder()
        module.validate_names(["ok.txt", "café.txt"])
        for name in ("bad\nname.txt", "bad\rname.txt", "tab\there.txt", "bell\x07.txt", "del\x7f.txt", "c1\x85.txt", "raw\udcff.txt"):
            with self.subTest(name=name):
                with self.assertRaisesRegex(module.BuildError, "control character"):
                    module.validate_names(["ok.txt", name])

    @unittest.skipIf(os.name == "nt", "Windows file names cannot hold a newline")
    def test_a_newline_in_a_file_name_fails_the_build(self) -> None:
        write_files(self.source, {"forged\nname.txt": "placeholder\n"})
        completed = run_builder(str(self.source), str(self.base / "out.zip"))
        self.assertEqual(completed.returncode, 1)
        self.assertIn("control character", completed.stderr)
        self.assertFalse((self.base / "out.zip").exists())

    @unittest.skipIf(os.name == "nt", "Windows has no executable bit")
    def test_an_executable_file_keeps_its_bit(self) -> None:
        (self.source / "assets" / "sprite.txt").chmod(0o755)
        returncode, payload, stderr = self.build()
        self.assertEqual(returncode, 0, stderr)
        self.assertEqual(payload["executable"], ["assets/sprite.txt"])

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFOs need a POSIX system")
    def test_a_fifo_is_never_opened_or_packaged(self) -> None:
        os.mkfifo(self.source / "pipe")
        returncode, payload, stderr = self.build("--include", "pipe")
        self.assertEqual(returncode, 0, stderr)
        self.assertNotIn("pipe", payload["packaged"])
        self.assertEqual(self.excluded(payload)["pipe"], "not a regular file, never packaged")

    @unittest.skipUnless(symlinks_supported(), "symbolic links need extra privileges here")
    def test_symbolic_links_are_never_packaged(self) -> None:
        os.symlink(self.source / "README.md", self.source / "linked.md")
        outside = self.base / "outside"
        write_files(outside, {"private.txt": "placeholder\n"})
        os.symlink(outside, self.source / "linked-folder", target_is_directory=True)
        returncode, payload, stderr = self.build("--include", "linked.md", "--include", "linked-folder")
        self.assertEqual(returncode, 0, stderr)
        for name in ("linked.md", "linked-folder"):
            self.assertNotIn(name, payload["packaged"])
            self.assertEqual(self.excluded(payload)[name], "symbolic link or junction, never packaged")
        self.assertNotIn("linked-folder/private.txt", payload["packaged"])


class ReleaseSecretTest(BuilderTestCase):
    """Common signing material and credentials are default excludes."""

    def test_release_secrets_are_excluded_and_lookalikes_are_not(self) -> None:
        write_files(self.source, {name: "placeholder\n" for name in RELEASE_SECRETS})
        write_files(self.source, LOOKALIKES)
        returncode, payload, stderr = self.build()
        self.assertEqual(returncode, 0, stderr)
        excluded = self.excluded(payload)
        for name, (shown, pattern) in RELEASE_SECRETS.items():
            with self.subTest(name=name):
                self.assertNotIn(name, payload["packaged"])
                self.assertEqual(excluded.get(shown), f"default exclude {pattern}; --include overrides it")
        for name in LOOKALIKES:
            self.assertIn(name, payload["packaged"])
        self.assertNotIn(".vs/slnx.sqlite", self.archive_names())

    def test_include_still_overrides_a_secret_pattern(self) -> None:
        write_files(self.source, {"deploy/kube/config": "placeholder\n", "config/prod.env": "placeholder\n"})
        returncode, payload, stderr = self.build("--include", "deploy/kube/config", "--include", "*.env")
        self.assertEqual(returncode, 0, stderr)
        self.assertIn("deploy/kube/config", payload["packaged"])
        self.assertIn("config/prod.env", payload["packaged"])


def load_builder() -> object:
    spec = importlib.util.spec_from_file_location("build_repository_zip_probe", BUILDER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(os.name == "nt", "junctions are a Windows feature")
class JunctionTest(BuilderTestCase):
    """A junction needs no privilege to create, and pathlib does not call it a link."""

    def setUp(self) -> None:
        super().setUp()
        self.outside = self.base / "outside"
        write_files(self.outside, {"private.txt": "placeholder\n"})
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(self.source / "linked"), str(self.outside)],
            check=True,
            capture_output=True,
        )
        self.assertFalse((self.source / "linked").is_symlink())

    def test_a_junction_is_never_followed(self) -> None:
        returncode, payload, stderr = self.build("--include", "linked", "--stored")
        self.assertEqual(returncode, 0, stderr)
        self.assertNotIn("linked/private.txt", payload["packaged"])
        self.assertEqual(self.excluded(payload)["linked"], "symbolic link or junction, never packaged")
        self.assertNotIn("linked/private.txt", self.archive_names())
        self.assertTrue((self.outside / "private.txt").is_file())

    def test_a_file_whose_real_path_leaves_the_source_is_refused(self) -> None:
        # With link detection disabled the walk enters the junction; the
        # real-path check must still refuse the file behind it.
        module = load_builder()
        with mock.patch.object(module, "is_link", return_value=False):
            with self.assertRaisesRegex(module.BuildError, "linked/private.txt resolves outside the source"):
                module.build(self.source, self.base / "in-process.zip", [])
        self.assertFalse((self.base / "in-process.zip").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
