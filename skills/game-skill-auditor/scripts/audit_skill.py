#!/usr/bin/env python3
"""Supplementary static audit for Codex skill packages."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path


ALLOWED_FRONTMATTER = {
    "name",
    "description",
    "license",
    "allowed-tools",
    "metadata",
}
KNOWN_TOP_LEVEL = {
    "SKILL.md",
    "LICENSE",
    "LICENSE.txt",
    "license.txt",
    "agents",
    "assets",
    "references",
    "scripts",
}
EXTRANEOUS_DOCS = {
    "README.md",
    "INSTALLATION_GUIDE.md",
    "QUICK_REFERENCE.md",
    "CHANGELOG.md",
}
GENERATED_ARTIFACT_NAMES = {
    "__pycache__",
    ".DS_Store",
    "Thumbs.db",
}
NAME_PATTERN = re.compile(r"^[a-z0-9-]+$")
FRONTMATTER_PATTERN = re.compile(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)", re.DOTALL)
MARKDOWN_LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
ABSOLUTE_PATH_PATTERN = re.compile(
    r"(?:"
    r"(?<![A-Za-z0-9])[A-Za-z]:\\[A-Za-z0-9_. -]{2,}"
    r"|\\\\[A-Za-z0-9_. -]{2,}\\"
    r"|/(?:Users|home)/"
    r")"
)
TEXT_RESOURCE_SUFFIXES = {
    ".json",
    ".md",
    ".py",
    ".txt",
    ".yaml",
    ".yml",
}


def issue(severity: str, code: str, message: str, location: str) -> dict[str, str]:
    return {
        "severity": severity,
        "code": code,
        "message": message,
        "location": location,
    }


def scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def parse_frontmatter(text: str) -> tuple[dict[str, str], list[dict[str, str]]]:
    findings: list[dict[str, str]] = []
    match = FRONTMATTER_PATTERN.match(text)
    if not match:
        findings.append(
            issue("ERROR", "FRONTMATTER", "Missing or invalid YAML frontmatter.", "SKILL.md")
        )
        return {}, findings

    values: dict[str, str] = {}
    for line_number, line in enumerate(match.group(1).splitlines(), start=2):
        key_match = re.match(r"^([A-Za-z0-9_-]+):(?:\s*(.*))?$", line)
        if not key_match:
            if (
                line.strip()
                and not line.lstrip().startswith("#")
                and not line.startswith((" ", "\t"))
            ):
                findings.append(
                    issue(
                        "ERROR",
                        "FRONTMATTER_SYNTAX",
                        "Malformed top-level YAML frontmatter line.",
                        f"SKILL.md:{line_number}",
                    )
                )
            continue
        key = key_match.group(1)
        if key in values:
            findings.append(
                issue(
                    "ERROR",
                    "FRONTMATTER_DUPLICATE",
                    f"Duplicate top-level frontmatter key '{key}'.",
                    f"SKILL.md:{line_number}",
                )
            )
        values[key] = scalar(key_match.group(2) or "")
        if key not in ALLOWED_FRONTMATTER:
            findings.append(
                issue(
                    "ERROR",
                    "FRONTMATTER_KEY",
                    f"Unexpected top-level frontmatter key '{key}'.",
                    f"SKILL.md:{line_number}",
                )
            )
    return values, findings


def line_number(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def without_fenced_code(text: str) -> str:
    output: list[str] = []
    active_marker = ""
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        marker = next(
            (
                candidate
                for candidate in ("```", "~~~")
                if stripped.startswith(candidate)
            ),
            "",
        )
        if active_marker:
            output.append("\n" if line.endswith("\n") else "")
            if marker == active_marker:
                active_marker = ""
            continue
        if marker:
            active_marker = marker
            output.append("\n" if line.endswith("\n") else "")
            continue
        output.append(line)
    return "".join(output)


def audit_markdown(path: Path, root: Path, findings: list[dict[str, str]]) -> None:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        findings.append(
            issue("ERROR", "ENCODING", "Markdown is not valid UTF-8.", str(path.relative_to(root)))
        )
        return

    relative = str(path.relative_to(root))
    fence_counts = {
        "```": sum(1 for line in text.splitlines() if line.strip().startswith("```")),
        "~~~": sum(1 for line in text.splitlines() if line.strip().startswith("~~~")),
    }
    for marker, count in fence_counts.items():
        if count % 2:
            findings.append(
                issue(
                    "WARN",
                    "CODE_FENCE",
                    f"Unbalanced {marker} code fence count ({count}).",
                    relative,
                )
            )

    headings = [
        line.strip()
        for line in text.splitlines()
        if re.match(r"^#{1,6}\s+\S", line.strip())
    ]
    for heading, count in Counter(headings).items():
        if count > 1:
            findings.append(
                issue(
                    "WARN",
                    "DUPLICATE_HEADING",
                    f"Heading appears {count} times: {heading}",
                    relative,
                )
            )

    link_text = without_fenced_code(text)
    for match in MARKDOWN_LINK_PATTERN.finditer(link_text):
        target = match.group(1).strip().strip("<>")
        if not target or target.startswith(("#", "http://", "https://", "mailto:")):
            continue
        target_without_anchor = target.split("#", 1)[0]
        resolved = (path.parent / target_without_anchor).resolve()
        if not resolved.exists():
            findings.append(
                issue(
                    "ERROR",
                    "BROKEN_LINK",
                    f"Referenced file does not exist: {target}",
                    f"{relative}:{line_number(link_text, match.start())}",
                )
            )


def audit_portability(
    path: Path,
    root: Path,
    findings: list[dict[str, str]],
) -> None:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return
    match = next(
        (
            candidate
            for candidate in ABSOLUTE_PATH_PATTERN.finditer(text)
            if not (
                line_number(text, candidate.start()) == 1
                and text.startswith("#!")
            )
        ),
        None,
    )
    if match is not None:
        relative = str(path.relative_to(root))
        findings.append(
            issue(
                "WARN",
                "PORTABILITY",
                f"User-specific absolute path detected: {match.group(0)}",
                f"{relative}:{line_number(text, match.start())}",
            )
        )


def parse_openai_yaml(path: Path) -> dict[str, tuple[str, bool, int]]:
    values: dict[str, tuple[str, bool, int]] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        match = re.match(
            r"^\s{2}(display_name|short_description|default_prompt):\s*(.*?)\s*$",
            line,
        )
        if not match:
            continue
        raw = match.group(2)
        quoted = len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in {'"', "'"}
        values[match.group(1)] = (scalar(raw), quoted, line_number)
    return values


def audit_skill(skill_path: Path) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    skill_path = skill_path.resolve()
    skill_md = skill_path / "SKILL.md"

    if not skill_path.is_dir():
        return [issue("ERROR", "PATH", "Skill path is not a directory.", str(skill_path))]
    if not skill_md.is_file():
        return [issue("ERROR", "SKILL_MD", "SKILL.md is missing.", str(skill_path))]

    text = skill_md.read_text(encoding="utf-8-sig")
    frontmatter, frontmatter_findings = parse_frontmatter(text)
    findings.extend(frontmatter_findings)

    name = frontmatter.get("name", "").strip()
    description = frontmatter.get("description", "").strip()

    if not name:
        findings.append(issue("ERROR", "NAME", "Frontmatter name is missing.", "SKILL.md"))
    else:
        if not NAME_PATTERN.fullmatch(name) or name.startswith("-") or name.endswith("-") or "--" in name:
            findings.append(
                issue("ERROR", "NAME_FORMAT", f"Invalid hyphen-case skill name: {name}", "SKILL.md")
            )
        if len(name) > 64:
            findings.append(
                issue("ERROR", "NAME_LENGTH", f"Skill name has {len(name)} characters; maximum is 64.", "SKILL.md")
            )
        if skill_path.name != name:
            findings.append(
                issue(
                    "ERROR",
                    "FOLDER_NAME",
                    f"Folder '{skill_path.name}' does not match skill name '{name}'.",
                    str(skill_path),
                )
            )

    if not description:
        findings.append(
            issue("ERROR", "DESCRIPTION", "Frontmatter description is missing.", "SKILL.md")
        )
    else:
        if len(description) > 1024:
            findings.append(
                issue(
                    "ERROR",
                    "DESCRIPTION_LENGTH",
                    f"Description has {len(description)} characters; maximum is 1024.",
                    "SKILL.md",
                )
            )
        if not re.search(r"\b(use when|use for|use if|when codex|use to)\b", description, re.I):
            findings.append(
                issue(
                    "WARN",
                    "TRIGGER_LANGUAGE",
                    "Description may not clearly state when the skill should trigger.",
                    "SKILL.md",
                )
            )

    todo_match = re.search(r"\[TODO|TODO:|FIXME|TBD", text, re.I)
    if todo_match:
        findings.append(
            issue(
                "ERROR",
                "PLACEHOLDER",
                "Unresolved placeholder found.",
                f"SKILL.md:{line_number(text, todo_match.start())}",
            )
        )

    skill_lines = len(text.splitlines())
    if skill_lines > 500:
        findings.append(
            issue(
                "WARN",
                "SKILL_LENGTH",
                f"SKILL.md has {skill_lines} lines; prefer fewer than 500.",
                "SKILL.md",
            )
        )

    for child in skill_path.iterdir():
        if child.name not in KNOWN_TOP_LEVEL:
            findings.append(
                issue(
                    "WARN",
                    "TOP_LEVEL_FILE",
                    f"Unexpected top-level entry: {child.name}",
                    child.name,
                )
            )
        if child.is_file() and child.name in EXTRANEOUS_DOCS:
            findings.append(
                issue(
                    "WARN",
                    "EXTRANEOUS_DOC",
                    f"Auxiliary document is usually unnecessary inside a skill: {child.name}",
                    child.name,
                )
            )

    for artifact in skill_path.rglob("*"):
        if artifact.name in GENERATED_ARTIFACT_NAMES or artifact.suffix in {".pyc", ".pyo"}:
            findings.append(
                issue(
                    "WARN",
                    "GENERATED_ARTIFACT",
                    "Remove generated cache or operating-system artifacts from the skill package.",
                    str(artifact.relative_to(skill_path)),
                )
            )

    for resource_name in ("assets", "references", "scripts"):
        resource_path = skill_path / resource_name
        if resource_path.is_dir() and not any(resource_path.iterdir()):
            findings.append(
                issue(
                    "WARN",
                    "EMPTY_RESOURCE_DIR",
                    f"Remove empty resource directory '{resource_name}'.",
                    resource_name,
                )
            )

    references = skill_path / "references"
    if references.is_dir():
        for item in references.rglob("*"):
            if item.is_file() and len(item.relative_to(references).parts) > 1:
                findings.append(
                    issue(
                        "WARN",
                        "DEEP_REFERENCE",
                        "Keep references one level below SKILL.md when practical.",
                        str(item.relative_to(skill_path)),
                    )
                )

    for markdown in skill_path.rglob("*.md"):
        audit_markdown(markdown, skill_path, findings)

    for text_resource in skill_path.rglob("*"):
        if (
            text_resource.is_file()
            and (
                text_resource.name == "SKILL.md"
                or text_resource.suffix.casefold() in TEXT_RESOURCE_SUFFIXES
            )
        ):
            audit_portability(text_resource, skill_path, findings)

    for python_file in (skill_path / "scripts").glob("*.py") if (skill_path / "scripts").is_dir() else []:
        relative = str(python_file.relative_to(skill_path))
        try:
            source = python_file.read_text(encoding="utf-8-sig")
            compile(source, str(python_file), "exec")
        except (SyntaxError, UnicodeDecodeError) as error:
            findings.append(
                issue("ERROR", "PYTHON_SYNTAX", f"Python script does not compile: {error}", relative)
            )

    openai_yaml = skill_path / "agents" / "openai.yaml"
    if not openai_yaml.is_file():
        findings.append(
            issue(
                "WARN",
                "OPENAI_YAML",
                "agents/openai.yaml is recommended for skill discovery UI.",
                "agents/openai.yaml",
            )
        )
    else:
        openai_text = openai_yaml.read_text(encoding="utf-8-sig")
        for key in ("display_name", "short_description", "default_prompt"):
            occurrences = len(
                re.findall(rf"^\s{{2}}{re.escape(key)}\s*:", openai_text, re.MULTILINE)
            )
            if occurrences > 1:
                findings.append(
                    issue(
                        "ERROR",
                        "OPENAI_DUPLICATE_FIELD",
                        f"Interface field '{key}' appears {occurrences} times.",
                        "agents/openai.yaml",
                    )
                )
        values = parse_openai_yaml(openai_yaml)
        for key in ("display_name", "short_description", "default_prompt"):
            if key not in values:
                findings.append(
                    issue(
                        "WARN",
                        "OPENAI_FIELD",
                        f"Missing interface field '{key}'.",
                        "agents/openai.yaml",
                    )
                )
                continue
            value, quoted, value_line = values[key]
            if not quoted:
                findings.append(
                    issue(
                        "WARN",
                        "OPENAI_QUOTING",
                        f"Quote the string value for '{key}'.",
                        f"agents/openai.yaml:{value_line}",
                    )
                )
            if not value:
                findings.append(
                    issue(
                        "WARN",
                        "OPENAI_EMPTY",
                        f"Interface field '{key}' is empty.",
                        f"agents/openai.yaml:{value_line}",
                    )
                )

        short_value = values.get("short_description", ("", True, 0))[0]
        if short_value and not 25 <= len(short_value) <= 64:
            findings.append(
                issue(
                    "WARN",
                    "OPENAI_SHORT_DESCRIPTION",
                    f"short_description has {len(short_value)} characters; expected 25-64.",
                    "agents/openai.yaml",
                )
            )

        default_prompt = values.get("default_prompt", ("", True, 0))[0]
        if name and default_prompt and f"${name}" not in default_prompt:
            findings.append(
                issue(
                    "WARN",
                    "OPENAI_DEFAULT_PROMPT",
                    f"default_prompt should explicitly mention '${name}'.",
                    "agents/openai.yaml",
                )
            )

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill_path", type=Path)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return a failing exit code when warnings are present.",
    )
    args = parser.parse_args()

    findings = audit_skill(args.skill_path)
    counts = Counter(item["severity"] for item in findings)

    if args.as_json:
        print(
            json.dumps(
                {
                    "skill_path": str(args.skill_path.resolve()),
                    "findings": findings,
                    "summary": {
                        "errors": counts["ERROR"],
                        "warnings": counts["WARN"],
                    },
                },
                indent=2,
            )
        )
    else:
        if not findings:
            print("PASS: no static audit findings.")
        for item in findings:
            print(
                f"[{item['severity']}] {item['code']} "
                f"{item['location']} - {item['message']}"
            )
        print(
            f"Summary: {counts['ERROR']} error(s), {counts['WARN']} warning(s)."
        )

    if counts["ERROR"]:
        return 1
    if args.strict and counts["WARN"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
