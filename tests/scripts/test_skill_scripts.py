#!/usr/bin/env python3
"""Check behavior of the scripts bundled inside skills.

    python -B tests/scripts/test_skill_scripts.py
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
AUDITOR = ROOT / "skills" / "game-skill-auditor"
AUDIT_SCRIPT = AUDITOR / "scripts" / "audit_skill.py"
SELF_TEST = AUDITOR / "scripts" / "self_test.py"
LEDGER_SCRIPT = ROOT / "skills" / "game-context-continuity" / "scripts" / "continuity_ledger.py"
CHILD_FLAGS = ["-B", "-X", "warn_default_encoding", "-W", "error::EncodingWarning"]
BOM = b"\xef\xbb\xbf"


def load_script(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_python(*arguments: str, flags: list[str] = CHILD_FLAGS) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    env.pop("PYTHONWARNINGS", None)
    return subprocess.run(
        [sys.executable, *flags, *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )


class ContinuityLedgerTest(unittest.TestCase):
    """create_text_exclusive must work, and refuse to overwrite, without hard links."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="ledger-")
        self.root = Path(self.temp.name)
        self.ledger = load_script(LEDGER_SCRIPT, "continuity_ledger")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def no_links(self):
        return mock.patch("os.link", side_effect=PermissionError(1, "no hard links here"))

    def test_fallback_creates_the_file_and_leaves_no_temporary(self) -> None:
        path = self.root / "ledger.md"
        with self.no_links() as link:
            self.ledger.create_text_exclusive(path, "first\nline\n")
        self.assertTrue(link.called)
        self.assertEqual(path.read_bytes(), b"first\nline\n")
        self.assertEqual(sorted(item.name for item in self.root.iterdir()), ["ledger.md"])

    def test_fallback_refuses_to_overwrite(self) -> None:
        path = self.root / "ledger.md"
        path.write_bytes(b"original\n")
        with self.no_links(), self.assertRaises(FileExistsError):
            self.ledger.create_text_exclusive(path, "replacement\n")
        self.assertEqual(path.read_bytes(), b"original\n")
        self.assertEqual(sorted(item.name for item in self.root.iterdir()), ["ledger.md"])

    def test_hard_link_path_refuses_to_overwrite(self) -> None:
        path = self.root / "ledger.md"
        self.ledger.create_text_exclusive(path, "first\n")
        with self.assertRaises(FileExistsError):
            self.ledger.create_text_exclusive(path, "second\n")
        self.assertEqual(path.read_bytes(), b"first\n")
        self.assertEqual(sorted(item.name for item in self.root.iterdir()), ["ledger.md"])

    def test_init_command_without_hard_links(self) -> None:
        program = (
            "import os, runpy, sys\n"
            "def no_link(*args, **kwargs):\n"
            "    raise PermissionError(1, 'no hard links here')\n"
            "os.link = no_link\n"
            f"sys.argv = [{str(LEDGER_SCRIPT)!r}, *sys.argv[1:]]\n"
            f"runpy.run_path({str(LEDGER_SCRIPT)!r}, run_name='__main__')\n"
        )
        arguments = ["-c", program, "init", "--workspace", str(self.root), "--objective", "Test the fallback."]
        created = run_python(*arguments)
        self.assertEqual(created.returncode, 0, created.stderr)
        ledger = Path(created.stdout.strip())
        self.assertTrue(ledger.is_file())
        before = ledger.read_bytes()
        refused = run_python(*arguments)
        self.assertEqual(refused.returncode, 1, refused.stderr)
        self.assertIn("refusing to overwrite", refused.stderr)
        self.assertEqual(ledger.read_bytes(), before)
        self.assertEqual([item for item in ledger.parent.iterdir() if item.suffix == ".tmp"], [])


class AuditorEncodingTest(unittest.TestCase):
    """audit_skill.py reports encoding problems as ERROR ENCODING findings."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="audit-encoding-")
        self.package = Path(self.temp.name) / "game-plan"
        shutil.copytree(ROOT / "skills" / "game-plan", self.package)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def audit(self) -> tuple[int, list[dict]]:
        completed = run_python(str(AUDIT_SCRIPT), str(self.package), "--json")
        self.assertIn(completed.returncode, (0, 1), completed.stderr)
        return completed.returncode, json.loads(completed.stdout)["findings"]

    def encoding_findings(self, findings: list[dict]) -> list[tuple[str, str]]:
        return [(item["severity"], item["location"]) for item in findings if item["code"] == "ENCODING"]

    def test_clean_copy_has_no_encoding_finding(self) -> None:
        returncode, findings = self.audit()
        self.assertEqual(self.encoding_findings(findings), [])
        self.assertEqual(returncode, 0, findings)

    def test_bom_in_skill_md(self) -> None:
        skill = self.package / "SKILL.md"
        skill.write_bytes(BOM + skill.read_bytes())
        returncode, findings = self.audit()
        self.assertEqual(returncode, 1)
        self.assertEqual(self.encoding_findings(findings), [("ERROR", "SKILL.md:1")])

    def test_skill_md_not_utf8(self) -> None:
        skill = self.package / "SKILL.md"
        skill.write_bytes(skill.read_bytes() + "Café notes.\n".encode("cp1252"))
        returncode, findings = self.audit()
        self.assertEqual(returncode, 1)
        self.assertEqual(self.encoding_findings(findings), [("ERROR", "SKILL.md")])

    def test_openai_yaml_not_utf8(self) -> None:
        metadata = self.package / "agents" / "openai.yaml"
        metadata.write_bytes(metadata.read_bytes() + "# Café\n".encode("cp1252"))
        returncode, findings = self.audit()
        self.assertEqual(returncode, 1)
        self.assertEqual(self.encoding_findings(findings), [("ERROR", "agents/openai.yaml")])


class SelfTestFlagsTest(unittest.TestCase):
    """The auditor self-test passes its encoding flags on to the scorers it runs."""

    def child_flags(self, flags: list[str]) -> list[str]:
        program = (
            "import json, runpy, shutil\n"
            f"namespace = runpy.run_path({str(SELF_TEST)!r}, run_name='self_test')\n"
            "shutil.rmtree(namespace['OUT_DIR'], ignore_errors=True)\n"
            "print(json.dumps(namespace['child_flags']()))\n"
        )
        completed = run_python("-c", program, flags=flags)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)

    def test_flags_are_inherited(self) -> None:
        self.assertEqual(self.child_flags(CHILD_FLAGS), CHILD_FLAGS)

    def test_no_extra_flags_without_them(self) -> None:
        self.assertEqual(self.child_flags(["-B"]), ["-B"])


class AssessorIdentityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="skill-scripts-")
        self.root = Path(self.temp.name)
        self.assessor = load_script(AUDITOR / "scripts" / "assess_evidence.py", "assess_evidence")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def copy_auditor(self, name: str, bom: bool = False) -> Path:
        package = self.root / name
        shutil.copytree(AUDITOR, package)
        if bom:
            skill = package / "SKILL.md"
            skill.write_bytes(BOM + skill.read_bytes())
        return package

    def test_a_bom_hides_the_package_name(self) -> None:
        self.assertEqual(self.assessor.skill_package_name(self.copy_auditor("plain")), "game-skill-auditor")
        self.assertEqual(self.assessor.skill_package_name(self.copy_auditor("bom", bom=True)), "")

    def test_lineage_requires_a_name(self) -> None:
        # Two BOM'd packages both read as "", which must not count as a match.
        target = self.copy_auditor("target", bom=True)
        mutated = self.copy_auditor("mutated", bom=True)
        self.assertFalse(self.assessor.package_has_lineage(target, mutated))
        self.assertTrue(
            self.assessor.package_has_lineage(self.copy_auditor("a"), self.copy_auditor("b"))
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
