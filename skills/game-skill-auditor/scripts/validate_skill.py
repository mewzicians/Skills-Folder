#!/usr/bin/env python3
"""Validate one skill's SKILL.md frontmatter with the bundled schema module.

This is the auditor's own structural validator. It needs only the Python
standard library: skill_frontmatter.py beside it is a generated copy of the
suite's schema module, which docs/SKILL_SCHEMA.md describes.

    python -B scripts/validate_skill.py <skill_directory>

It checks the Agent Skills specification level, where specification
violations and YAML the schema cannot read safely are errors. It also fails
on everything in CODEX_REJECTS, which the specification level only warns
about or allows but Codex's skill-creator validator rejects: tabs, a
byte-order mark, a delimiter with trailing spaces, U+0085, U+2028, or U+2029
in the frontmatter, keys other than name, description, license,
allowed-tools, and metadata (so 'compatibility' and Claude Code-only keys
too), '<' or '>' in the description, and an unfinished [TODO: ...] line. A
skill that passes here therefore passes those checks there. Other
portability concerns, such as CRLF line endings, which Codex's validator
reads as LF, are printed as warnings.

It prints each finding, then "Skill is valid!" with exit code 0, or "Skill
is invalid." with exit code 1. Exit code 2 is a usage error and 3 an
internal error.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import importlib.util
from pathlib import Path
from types import ModuleType

SCHEMA_PATH = Path(__file__).resolve().with_name("skill_frontmatter.py")
LEVEL = "spec"
# Findings that Codex's validator rejects but the spec level only warns
# about or, for COMPATIBILITY_KEY, does not report. Each is an error here.
CODEX_REJECTS = frozenset(
    {
        "BOM",
        "CLAUDE_ONLY_KEY",
        "COMPATIBILITY_KEY",
        "DELIMITER_SPACING",
        "DESCRIPTION_ANGLE_BRACKETS",
        "TAB",
        "TODO_PLACEHOLDER",
        "UNICODE_LINE_BREAK",
        "UNKNOWN_KEY",
    }
)


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


def findings(schema: ModuleType, path: str) -> tuple[str, list[tuple[str, object]]]:
    """The display path and (severity, finding) pairs, with Codex's rejections as errors."""
    spec = schema.validate_skill_dir(path, level=LEVEL)
    # The portable level reports every code, including ones the spec level drops.
    portable = schema.validate_skill_dir(path, level="portable")
    seen = {(item.code, item.line) for item in spec.findings}
    pairs = [
        ("error" if item.code in CODEX_REJECTS else item.severity, item) for item in spec.findings
    ]
    pairs += [
        ("error", item)
        for item in portable.findings
        if item.code in CODEX_REJECTS and (item.code, item.line) not in seen
    ]
    pairs.sort(key=lambda pair: (pair[1].line or 0, pair[1].code))
    return spec.path, pairs


def main(argv: list[str]) -> int:
    configure_stdio()
    if len(argv) != 1 or argv[0].startswith("-"):
        print("Usage: python validate_skill.py <skill_directory>", file=sys.stderr)
        return 2
    path, pairs = findings(load_schema(), argv[0])
    for severity, finding in pairs:
        where = f"SKILL.md:{finding.line}" if finding.line else path
        rejected = " Codex's validator rejects this." if finding.code in CODEX_REJECTS else ""
        print(f"{where}: {severity} {finding.code}: {finding.message}{rejected}")
    valid = not any(severity == "error" for severity, _ in pairs)
    print("Skill is valid!" if valid else "Skill is invalid.")
    return 0 if valid else 1


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as error:  # noqa: BLE001 - report, never mistake for invalid
        print(f"validate_skill.py: internal error: {error!r}", file=sys.stderr)
        sys.exit(3)
