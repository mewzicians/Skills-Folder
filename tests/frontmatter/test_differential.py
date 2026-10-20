#!/usr/bin/env python3
"""Compare the schema module with PyYAML on generated SKILL.md files.

CI only: PyYAML is a test dependency pinned in requirements-ci.txt and never
a run-time one. Without that exact PyYAML version the test is skipped, unless
SKILL_SUITE_REQUIRE_PYYAML=1 is set, as CI sets it, which turns the skip into
a failure. Run with:

    python -B tests/frontmatter/test_differential.py
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import importlib.util
import os
import random
import re
import unittest
from pathlib import Path

try:
    import yaml  # CI-only test dependency; see requirements-ci.txt.
except ImportError:
    yaml = None

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "tools" / "lib" / "skill_frontmatter.py"
REQUIREMENTS = ROOT / "requirements-ci.txt"
SEEDS = range(4)
DOCUMENTS_PER_SEED = 2000
# Warnings for problems PyYAML is allowed to disagree about: YAML 1.2 allows
# tabs, and PyYAML reads U+0085, U+2028, and U+2029 as line breaks.
PYYAML_EXEMPT = {"TAB", "UNICODE_LINE_BREAK"}
FRONTMATTER = re.compile(r"^---\n(.*?)\n---", re.DOTALL)


def load_schema():
    spec = importlib.util.spec_from_file_location("skill_frontmatter", SCHEMA_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SCHEMA = load_schema()


def pinned_version() -> str | None:
    match = re.search(r"(?im)^pyyaml==([^\s\\;]+)", REQUIREMENTS.read_text(encoding="utf-8"))
    return match.group(1) if match else None


def skip_reason() -> str | None:
    pinned = pinned_version()
    if yaml is None:
        return "PyYAML is not installed"
    if yaml.__version__ != pinned:
        return f"PyYAML {yaml.__version__} is installed; requirements-ci.txt pins {pinned}"
    return None


SKIP_REASON = skip_reason()
if SKIP_REASON and os.environ.get("SKILL_SUITE_REQUIRE_PYYAML") == "1":
    raise SystemExit(f"test_differential.py: {SKIP_REASON}, but SKILL_SUITE_REQUIRE_PYYAML=1")


ATOMS = [
    "Use when testing", "plain words", "it's", "café → \U0001f3ae", "a:b", "a: b", "a #b",
    "a#b", "trailing:", "yes", "No", "on", "y", "null", "~", "", "1.5", "0x1F", "0b_", "1:20",
    "2026-10-16", "2026-02-30", "2026-1-1 25:00:00", ".inf", "=", "<<", "-", "- a", "-a", "?", "? a",
    ":a", "@x", "`x", "%x", "*alias", "&anchor a", "!tag a", "!!str a", "|", ">", "[a, b]", "[a",
    "[a: b]", "[*.md]", "[=]", "[a #c]", "{a: b}", "{a", "{<<: a}", "[TODO: x]", "<b>", "Bash(git add:*)",
    "\t", "a\tb", "x\u2028y", "éè", "\\", "\\n",
]
KEYS = [
    "name", "description", "description", "license", "metadata", "compatibility", "allowed-tools",
    "when_to_use", "argument-hint", "hooks", "paths", "model", "x-extra",
]


def scalar(rng: random.Random) -> str:
    text = rng.choice(ATOMS) + (rng.choice(ATOMS) if rng.random() < 0.2 else "")
    form = rng.random()
    if form < 0.15:
        return '"' + text.replace("\\", rng.choice(["\\\\", "\\", "\\q"])).replace('"', '\\"') + '"'
    if form < 0.25:
        return "'" + text.replace("'", "''") + "'"
    if form < 0.28:
        return rng.choice(['"open', "'open", '"', "'"])
    return text


def value_lines(rng: random.Random, key: str) -> list[str]:
    form = rng.random()
    indent = " " * rng.choice([1, 2, 2, 4])
    if form < 0.55:
        return [f"{key}: {scalar(rng)}"]
    if form < 0.63:
        header = rng.choice(["|", ">", "|-", ">+", "|2", ">1-"])
        body = [indent + scalar(rng) for _ in range(rng.randint(0, 3))]
        if body and rng.random() < 0.3:
            body.insert(rng.randint(0, len(body)), "")
        return [f"{key}: {header}", *body]
    if form < 0.73:
        lines = [f"{key}:"]
        for _ in range(rng.randint(1, 3)):
            if rng.random() < 0.25:
                lines.append(f"{indent}- k: {scalar(rng)}")
                if rng.random() < 0.5:
                    lines.append(f"{indent}  j: {scalar(rng)}")
            else:
                lines.append(f"{indent}- {scalar(rng)}")
        return lines
    if form < 0.85:
        lines = [f"{key}:"]
        for _ in range(rng.randint(1, 3)):
            sub = rng.choice(["version", "author", "yes", "1", "a.b", "x-y", "nested", "0b_"])
            lines.append(f"{indent}{sub}: {scalar(rng)}")
            if rng.random() < 0.15:
                lines.append(f"{indent}  deeper: {scalar(rng)}")
        return lines
    if form < 0.93:
        return [f"{key}: {scalar(rng)}", indent + scalar(rng)]
    return [f"{key}:", indent + scalar(rng)]


def make_document(rng: random.Random) -> str:
    keys = ["name", "description"] + [rng.choice(KEYS) for _ in range(rng.randint(0, 3))]
    rng.shuffle(keys)
    lines: list[str] = []
    for key in keys:
        if key == "name" and rng.random() < 0.75:
            lines.append("name: case-skill")
        elif key == "description" and rng.random() < 0.4:
            lines.append("description: Use when testing the validator.")
        else:
            lines.extend(value_lines(rng, key))
        if rng.random() < 0.08:
            lines.append(rng.choice(["# comment", "", "  # comment"]))
    body = rng.choice(
        [
            "# Case Skill\n",
            "# Case Skill\n",
            "# Case Skill\n",
            "[TODO: finish]\n",
            "See below.\u2028[TODO: finish]\n",
            "See below.\f[TODO: finish]\n",
            "```\n[TODO: inside a fence]\n```\n",
            "   [TODO: indented three]\n",
            "    [TODO: indented four]\n",
        ]
    )
    return "---\n" + "\n".join(lines) + "\n---\n\n" + body


def pyyaml_load(document: str) -> tuple[str, object]:
    match = FRONTMATTER.match(document)
    if match is None:
        return "no frontmatter", None
    try:
        loaded = yaml.safe_load(match.group(1))
    except yaml.YAMLError as error:
        return "invalid", str(error).splitlines()[0]
    except Exception as error:  # noqa: BLE001 - Codex's validator would crash
        return "crash", repr(error)
    return ("ok", loaded) if isinstance(loaded, dict) else ("not a mapping", loaded)


def codex_accepts(document: str, frontmatter: dict) -> str | None:
    """The rules of Codex's current skill-creator validator after a clean load."""
    allowed = {"name", "description", "license", "allowed-tools", "metadata"}
    if set(frontmatter) - allowed:
        return "unexpected key"
    if "name" not in frontmatter or "description" not in frontmatter:
        return "missing name or description"
    name, description = frontmatter["name"], frontmatter["description"]
    if not isinstance(name, str) or not isinstance(description, str):
        return "name or description is not a string"
    name, description = name.strip(), description.strip()
    if name and (
        not re.match(r"^[a-z0-9-]+$", name)
        or name.startswith("-")
        or name.endswith("-")
        or "--" in name
        or len(name) > 64
    ):
        return "bad name"
    if description.startswith("[TODO:"):
        return "TODO description"
    if description and ("<" in description or ">" in description or len(description) > 1024):
        return "bad description"
    fence_marker, fence_length = None, 0
    for line in document[FRONTMATTER.match(document).end() :].splitlines():
        fence = re.match(r"^[ \t]*(?:(?:[-+*]|\d+[.)])[ \t]+)?(`{3,}|~{3,})(.*)$", line)
        if fence:
            marker = fence.group(1)
            if fence_marker is None:
                fence_marker, fence_length = marker[0], len(marker)
            elif marker[0] == fence_marker and len(marker) >= fence_length and not fence.group(2).strip():
                fence_marker, fence_length = None, 0
            continue
        if fence_marker is None and re.fullmatch(r"[ ]{0,3}\[TODO:[^\n]*\][ \t]*", line):
            return "TODO body line"
    return None


def same_strings(ours: object, theirs: object) -> bool:
    """Equal wherever PyYAML produced strings; the schema keeps source text otherwise."""
    if isinstance(theirs, str):
        return ours == theirs
    if isinstance(theirs, list):
        return isinstance(ours, list) and len(ours) == len(theirs) and all(
            same_strings(a, b) for a, b in zip(ours, theirs)
        )
    if isinstance(theirs, dict):
        return isinstance(ours, dict) and all(
            key in ours and same_strings(ours[key], value)
            for key, value in theirs.items()
            if isinstance(key, str)
        )
    return True


@unittest.skipIf(SKIP_REASON is not None, SKIP_REASON or "")
class DifferentialTest(unittest.TestCase):
    def documents(self):
        for seed in SEEDS:
            rng = random.Random(seed)
            for number in range(DOCUMENTS_PER_SEED):
                yield f"seed {seed} document {number}", make_document(rng)

    def test_portable_documents_load_identically_in_pyyaml_and_codex(self) -> None:
        accepted = 0
        for label, document in self.documents():
            report = SCHEMA.validate_text(document.encode("utf-8"), folder="case-skill")
            if not report.valid:
                continue
            accepted += 1
            status, loaded = pyyaml_load(document)
            with self.subTest(label, document=document):
                self.assertEqual(status, "ok", loaded)
                self.assertEqual(loaded, report.frontmatter)
                self.assertIsNone(codex_accepts(document, loaded))
        # The generator must keep producing enough valid documents to matter.
        self.assertGreater(accepted, 300)

    def test_spec_documents_load_in_pyyaml(self) -> None:
        accepted = 0
        for label, document in self.documents():
            report = SCHEMA.validate_text(document.encode("utf-8"), folder="case-skill", level="spec")
            if not report.valid or {item.code for item in report.findings} & PYYAML_EXEMPT:
                continue
            accepted += 1
            status, loaded = pyyaml_load(document)
            with self.subTest(label, document=document):
                self.assertEqual(status, "ok", loaded)
                self.assertEqual(set(loaded), set(report.frontmatter))
                for key, value in report.frontmatter.items():
                    self.assertTrue(same_strings(value, loaded[key]), (key, value, loaded[key]))
        self.assertGreater(accepted, 1000)

    def test_neither_level_crashes_on_rejected_yaml(self) -> None:
        for label, document in self.documents():
            if pyyaml_load(document)[0] == "ok":
                continue
            for level in SCHEMA.LEVELS:
                with self.subTest(label, level=level):
                    SCHEMA.validate_text(document.encode("utf-8"), folder="case-skill", level=level)


if __name__ == "__main__":
    unittest.main(verbosity=2)
