#!/usr/bin/env python3
"""Check the frontmatter schema against its corpus and its documentation.

Every case in cases.json is written to a temporary skill folder at run time,
so risky bytes (BOM, CRLF, cp1252) never live in the repository. Run with:

    python -B tests/frontmatter/test_frontmatter.py
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CASES_PATH = Path(__file__).resolve().with_name("cases.json")
SCHEMA_DOC = ROOT / "docs" / "SKILL_SCHEMA.md"
SCHEMA_PATH = ROOT / "tools" / "lib" / "skill_frontmatter.py"
VALIDATOR = ROOT / "tools" / "validate_skill.py"
CHILD_FLAGS = ["-B", "-X", "warn_default_encoding", "-W", "error::EncodingWarning"]


def load_schema():
    spec = importlib.util.spec_from_file_location("skill_frontmatter", SCHEMA_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SCHEMA = load_schema()
CASES = json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]


def expand(case: dict, text: str) -> str:
    fill = case.get("fill")
    if fill:
        text = text.replace("@@FILL@@", fill["char"] * fill["count"])
    return text


def write_case(case: dict, root: Path) -> Path:
    folder = root / case["id"] / expand(case, case.get("folder", "case-skill"))
    folder.mkdir(parents=True)
    text = expand(case, case["skill_md"])
    (folder / "SKILL.md").write_bytes(text.encode(case.get("encoding", "utf-8")))
    return folder


def verdict(expected: dict) -> str:
    errors, warnings = expected["errors"], expected["warnings"]
    if errors:
        cell = "invalid: " + ", ".join(errors)
        return cell + ("; warns " + ", ".join(warnings) if warnings else "")
    return "valid; warns " + ", ".join(warnings) if warnings else "valid"


def child_env(**extra: str) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.update(extra)
    return env


def run_validator(
    *arguments: str, cwd: Path | None = None, **env: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *CHILD_FLAGS, str(VALIDATOR), *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=child_env(**env),
        cwd=cwd,
        check=False,
    )


class CorpusTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="frontmatter-corpus-")
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_case_ids_are_unique(self) -> None:
        ids = [case["id"] for case in CASES]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_case_matches_its_verdicts(self) -> None:
        for case in CASES:
            folder = write_case(case, self.root)
            for level in SCHEMA.LEVELS:
                with self.subTest(case=case["id"], level=level):
                    report = SCHEMA.validate_skill_dir(folder, level=level)
                    errors = sorted({f.code for f in report.findings if f.severity == "error"})
                    warnings = sorted({f.code for f in report.findings if f.severity == "warning"})
                    self.assertEqual(
                        {"errors": errors, "warnings": warnings},
                        case[level],
                        [f.as_dict() for f in report.findings],
                    )
                    self.assertEqual(report.valid, not case[level]["errors"])

    def test_documentation_lists_every_verdict(self) -> None:
        document = SCHEMA_DOC.read_text(encoding="utf-8")
        missing = []
        for case in CASES:
            row = (
                f"| `{case['id']}` | {case['summary']} | "
                f"{verdict(case['portable'])} | {verdict(case['spec'])} |"
            )
            if row not in document:
                missing.append(row)
        self.assertEqual(missing, [], "Update the corpus table in docs/SKILL_SCHEMA.md")

    def test_every_rule_code_is_documented(self) -> None:
        document = SCHEMA_DOC.read_text(encoding="utf-8")
        undocumented = [code for code in SCHEMA.RULES if f"`{code}`" not in document]
        self.assertEqual(undocumented, [])

    def test_committed_skills_are_portable(self) -> None:
        skills = sorted(path for path in (ROOT / "skills").iterdir() if path.is_dir())
        self.assertTrue(skills)
        for skill in skills:
            with self.subTest(skill=skill.name):
                report = SCHEMA.validate_skill_dir(skill, level="portable")
                self.assertEqual([f.as_dict() for f in report.findings], [])


class CommandLineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="frontmatter-cli-")
        self.root = Path(self.temp.name)
        self.by_id = {case["id"]: case for case in CASES}

    def tearDown(self) -> None:
        self.temp.cleanup()

    def case_dir(self, case_id: str) -> str:
        return str(write_case(self.by_id[case_id], self.root))

    def test_exit_codes(self) -> None:
        valid = self.case_dir("valid-minimal")
        invalid = self.case_dir("bom")
        self.assertEqual(run_validator(valid).returncode, 0)
        self.assertEqual(run_validator(invalid).returncode, 1)
        self.assertEqual(run_validator("--level", "spec", invalid).returncode, 0)
        self.assertEqual(run_validator(valid, invalid).returncode, 1)
        self.assertEqual(run_validator("--level").returncode, 2)
        self.assertEqual(run_validator("--level", "strictest", valid).returncode, 2)

    def test_no_path_validates_every_repository_skill(self) -> None:
        # Run from elsewhere: the default is this repository's skills/, not the cwd's.
        completed = run_validator("--json", cwd=self.root)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        payload = json.loads(completed.stdout)
        expected = sorted(path.name for path in (ROOT / "skills").iterdir() if path.is_dir())
        self.assertEqual(sorted(Path(item["path"]).name for item in payload["skills"]), expected)
        self.assertEqual(payload["valid"], len(expected))

    def test_glob_patterns_are_expanded_without_a_shell(self) -> None:
        # subprocess passes the pattern verbatim, as PowerShell and cmd do.
        self.case_dir("valid-minimal")
        self.case_dir("bom")
        completed = run_validator("--json", str(self.root / "*" / "case-skill"))
        self.assertEqual(completed.returncode, 1, completed.stderr)
        payload = json.loads(completed.stdout)
        found = {Path(item["path"]).parent.name: item["valid"] for item in payload["skills"]}
        self.assertEqual(found, {"valid-minimal": True, "bom": False})

        unmatched = run_validator("--json", str(self.root / "missing-*"))
        self.assertEqual(unmatched.returncode, 1, unmatched.stderr)
        codes = [item["code"] for item in json.loads(unmatched.stdout)["skills"][0]["findings"]]
        self.assertEqual(codes, ["PATH"])

    def test_existing_path_with_glob_characters_is_literal(self) -> None:
        # As a pattern, 'set[1]' would match 'set1', whose skill is invalid.
        folder = write_case(self.by_id["valid-minimal"], self.root / "set[1]")
        write_case(self.by_id["bom"], self.root / "set1")
        completed = run_validator("--json", str(folder))
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual([item["path"] for item in payload["skills"]], [str(folder)])

    def test_json_output(self) -> None:
        completed = run_validator("--json", self.case_dir("crlf"))
        self.assertEqual(completed.returncode, 1, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["invalid"], 1)
        self.assertEqual(payload["skills"][0]["findings"][0]["code"], "CRLF")

    def test_non_ascii_under_a_legacy_locale(self) -> None:
        # Curly quotes, an arrow, and an emoji must validate with the locale's
        # default encoding left as it is (cp1252 on Windows) and a cp1252 pipe.
        for case_id in ("curly-quotes", "non-ascii"):
            with self.subTest(case=case_id):
                completed = run_validator(
                    self.case_dir(case_id), PYTHONUTF8="0", PYTHONIOENCODING="cp1252"
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertEqual(completed.stderr, "")

    def test_text_output_survives_unencodable_characters(self) -> None:
        folder = self.root / "arrow" / "a-b"
        folder.mkdir(parents=True)
        (folder / "SKILL.md").write_text(
            "---\nname: a\u2192b\ndescription: Use when testing.\n---\n",
            encoding="utf-8",
            newline="\n",
        )
        completed = run_validator(str(folder), PYTHONUTF8="0", PYTHONIOENCODING="cp1252")
        self.assertEqual(completed.returncode, 1, completed.stderr)
        self.assertIn("NAME_FORMAT", completed.stdout)
        self.assertNotIn("Traceback", completed.stderr)

    def test_runs_without_pyyaml(self) -> None:
        # Block any PyYAML import, then run the CLI over every committed skill.
        skills = sorted(str(path) for path in (ROOT / "skills").iterdir() if path.is_dir())
        argv = ["validate_skill.py", "--level", "portable", *skills]
        program = (
            "import runpy, sys; sys.modules['yaml'] = None; "
            f"sys.argv = {argv!r}; "
            f"runpy.run_path({str(VALIDATOR)!r}, run_name='__main__')"
        )
        completed = subprocess.run(
            [sys.executable, *CHILD_FLAGS, "-c", program],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=child_env(),
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

    def test_no_tool_imports_yaml(self) -> None:
        sources = [*ROOT.joinpath("tools").rglob("*.py"), *ROOT.joinpath("tests").rglob("*.py")]
        offenders = [
            str(path.relative_to(ROOT))
            for path in sources
            if any(
                line.strip().startswith(("import yaml", "from yaml"))
                for line in path.read_text(encoding="utf-8").splitlines()
            )
        ]
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
