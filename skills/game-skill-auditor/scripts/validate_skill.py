#!/usr/bin/env python3
"""Validate one skill's SKILL.md frontmatter with the bundled schema module.

This is the auditor's own structural validator. It needs only the Python
standard library: skill_frontmatter.py beside it is a generated copy of the
suite's schema module, which docs/SKILL_SCHEMA.md describes.

    python -B scripts/validate_skill.py <skill_directory>

It checks the Agent Skills specification level: specification violations and
YAML the schema cannot read safely are errors, and portability concerns are
printed as warnings. It prints each finding, then "Skill is valid!" with exit
code 0, or "Skill is invalid." with exit code 1. Exit code 2 is a usage error
and 3 an internal error.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import importlib.util
from pathlib import Path
from types import ModuleType

SCHEMA_PATH = Path(__file__).resolve().with_name("skill_frontmatter.py")
LEVEL = "spec"


def load_schema() -> ModuleType:
    """Load the schema copy beside this file by path, never from sys.path."""
    spec = importlib.util.spec_from_file_location("auditor_skill_frontmatter", SCHEMA_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {SCHEMA_PATH}")
    module = importlib.util.module_from_spec(spec)
    # Dataclasses resolve their module through sys.modules while the class is built.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="backslashreplace")


def main(argv: list[str]) -> int:
    configure_stdio()
    if len(argv) != 1 or argv[0].startswith("-"):
        print("Usage: python validate_skill.py <skill_directory>", file=sys.stderr)
        return 2
    report = load_schema().validate_skill_dir(argv[0], level=LEVEL)
    for finding in report.findings:
        where = f"SKILL.md:{finding.line}" if finding.line else report.path
        print(f"{where}: {finding.severity} {finding.code}: {finding.message}")
    print("Skill is valid!" if report.valid else "Skill is invalid.")
    return 0 if report.valid else 1


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as error:  # noqa: BLE001 - report, never mistake for invalid
        print(f"validate_skill.py: internal error: {error!r}", file=sys.stderr)
        sys.exit(3)
