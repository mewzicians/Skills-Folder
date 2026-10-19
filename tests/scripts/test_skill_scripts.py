#!/usr/bin/env python3
"""Check behavior of the scripts bundled inside skills.

    python -B tests/scripts/test_skill_scripts.py
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
AUDITOR = ROOT / "skills" / "game-skill-auditor"
BOM = b"\xef\xbb\xbf"


def load_script(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
