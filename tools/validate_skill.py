#!/usr/bin/env python3
"""Validate SKILL.md frontmatter against docs/SKILL_SCHEMA.md.

With no path, every folder in this repository's skills/ is checked. Glob
patterns such as "skills/*" are expanded here rather than by the shell, so
the same command works in PowerShell, cmd, and POSIX shells.

Exit codes: 0 every skill is valid, 1 at least one skill is invalid,
2 usage error, 3 internal error. Standard library only.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import glob
import importlib.util
import json
import os
from pathlib import Path
from types import ModuleType

TOOLS = Path(__file__).resolve().parent
SCHEMA_PATH = TOOLS / "lib" / "skill_frontmatter.py"
SKILLS_ROOT = TOOLS.parent / "skills"
GLOB_CHARACTERS = frozenset("*?[")


def load_schema() -> ModuleType:
    """Load the canonical schema module by path, without writing bytecode."""
    existing = sys.modules.get("skill_frontmatter")
    if existing is not None and Path(getattr(existing, "__file__", "")) == SCHEMA_PATH:
        return existing
    spec = importlib.util.spec_from_file_location("skill_frontmatter", SCHEMA_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {SCHEMA_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="backslashreplace")


def build_parser(levels: tuple[str, ...]) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the SKILL.md frontmatter of one or more skill folders. "
            "'portable' is this suite's gate; 'spec' checks skills written by "
            "others and reports portability concerns as warnings."
        )
    )
    parser.add_argument(
        "skills",
        nargs="*",
        metavar="SKILL_DIR",
        help=(
            "a skill folder or a glob pattern such as 'skills/*' "
            "(default: every folder in this repository's skills/)"
        ),
    )
    parser.add_argument("--level", choices=levels, default="portable")
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def display(path: Path) -> str:
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def skill_paths(arguments: list[str]) -> list[str]:
    """Expand glob patterns; with no arguments, list this repository's skills."""
    if not arguments:
        return [
            display(path)
            for path in sorted(SKILLS_ROOT.iterdir())
            if path.is_dir() and not path.name.startswith(".")
        ]
    paths: list[str] = []
    for argument in arguments:
        if not GLOB_CHARACTERS.intersection(argument) or os.path.lexists(argument):
            paths.append(argument)
            continue
        matches = sorted(match for match in glob.glob(argument) if os.path.isdir(match))
        # A pattern that matches no folder is reported as a missing path.
        paths.extend(matches or [argument])
    return paths


def render_text(reports: list) -> str:
    lines = []
    for report in reports:
        if report.errors:
            status = "FAIL"
        elif report.warnings:
            status = "WARN"
        else:
            status = "PASS"
        counts = ""
        if report.findings:
            counts = f" ({report.errors} error(s), {report.warnings} warning(s))"
        lines.append(f"{status} {report.path}{counts}")
        for finding in report.findings:
            where = f"SKILL.md:{finding.line}" if finding.line else "SKILL.md"
            lines.append(f"  {where}: {finding.severity} {finding.code}: {finding.message}")
    valid = sum(report.valid for report in reports)
    level = reports[0].level if reports else "portable"
    lines.append(
        f"Summary: {valid} valid, {len(reports) - valid} invalid at the {level} level."
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    schema = load_schema()
    args = build_parser(schema.LEVELS).parse_args(argv)
    reports = [
        schema.validate_skill_dir(path, level=args.level) for path in skill_paths(args.skills)
    ]
    if args.as_json:
        payload = {
            "level": args.level,
            "valid": sum(report.valid for report in reports),
            "invalid": sum(not report.valid for report in reports),
            "skills": [report.as_dict() for report in reports],
        }
        print(json.dumps(payload, indent=2))
    else:
        print(render_text(reports))
    return 0 if all(report.valid for report in reports) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:  # noqa: BLE001 - report, never mistake for invalid
        print(f"validate_skill.py: internal error: {error!r}", file=sys.stderr)
        sys.exit(3)
