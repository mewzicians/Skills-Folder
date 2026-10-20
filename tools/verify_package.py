#!/usr/bin/env python3
"""Verify the skill suite package in one pass and report every problem.

Checks skill structure, portable frontmatter (docs/SKILL_SCHEMA.md), the
tracked-text policy, public-term hygiene, generated debris inside skills,
symbolic links that do not resolve to a file, and intentionally duplicated
files, which must stay byte-for-byte equal.
Inside a git checkout the inventory comes from git, so git-ignored files are
skipped; elsewhere, such as an extracted archive, every file is checked.

Exit codes: 0 pass, 1 problems found, 2 usage error, 3 internal error.
Standard library only.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import importlib.util
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import ModuleType

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
SCHEMA_PATH = TOOLS / "lib" / "skill_frontmatter.py"

# Built from fragments exactly as verify-package.ps1 builds it, so this file
# never contains the term it forbids.
FORBIDDEN = re.compile(
    "(?i)"
    + ("office" + r"\s*" + "wars")
    + "|"
    + ("office" + "wars")
    + "|"
    + ("offie" + r"\s+" + "war")
)
BINARY_SUFFIXES = {
    ".gif",
    ".gz",
    ".ico",
    ".jpeg",
    ".jpg",
    ".mp3",
    ".ogg",
    ".otf",
    ".pdf",
    ".png",
    ".ttf",
    ".wav",
    ".webp",
    ".woff",
    ".woff2",
    ".zip",
}
DEBRIS_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}
DEBRIS_SUFFIXES = {".pyc", ".pyo"}
PROMPT_LINE = re.compile(r"^\s{2}default_prompt:\s*(.*?)\s*$")
# Generated copies of a canonical file, as {copy: source}. A copy starts with
# COPY_HEADER naming its source; every byte after that line equals the source.
GENERATED_COPIES = {
    "skills/game-skill-auditor/scripts/skill_frontmatter.py": "tools/lib/skill_frontmatter.py",
}
COPY_HEADER = "# Generated copy of {source}. Edit that file, then recopy it below this line.\n"


@dataclass(frozen=True)
class Problem:
    code: str
    path: str
    message: str
    line: int | None = None

    def render(self) -> str:
        where = f"{self.path}:{self.line}" if self.line else self.path
        return f"{self.code} {where}: {self.message}"

    def as_dict(self) -> dict[str, object]:
        return {"code": self.code, "path": self.path, "line": self.line, "message": self.message}


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="backslashreplace")


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


def same_path(first: str | Path, second: str | Path) -> bool:
    def canonical(path: str | Path) -> str:
        return os.path.normcase(os.path.realpath(path))

    return canonical(first) == canonical(second)


def git_inventory(root: Path) -> list[str] | None:
    """Tracked plus untracked, non-ignored files, or None outside a git checkout."""

    def git(*arguments: str) -> subprocess.CompletedProcess[bytes] | None:
        try:
            return subprocess.run(
                ["git", "-C", str(root), *arguments],
                capture_output=True,
                check=False,
            )
        except OSError:
            return None

    top = git("rev-parse", "--show-toplevel")
    if top is None or top.returncode != 0:
        return None
    if not same_path(top.stdout.decode("utf-8", "replace").strip(), root):
        return None
    listed = git("ls-files", "-z", "--cached", "--others", "--exclude-standard")
    if listed is None or listed.returncode != 0:
        return None
    names = {name for name in listed.stdout.decode("utf-8", "surrogateescape").split("\0") if name}
    # Keep symbolic links that resolve to nothing, so verify() reports them.
    return sorted(
        name for name in names if (root / name).is_file() or (root / name).is_symlink()
    )


def walk_inventory(root: Path) -> list[str]:
    """Every file under root, skipping .git by path part (file or directory)."""
    files = []
    for directory, subdirectories, filenames in os.walk(root):
        subdirectories[:] = sorted(name for name in subdirectories if name != ".git")
        relative_directory = Path(directory).relative_to(root)
        for filename in filenames:
            relative = relative_directory / filename
            if ".git" not in relative.parts:
                files.append(relative.as_posix())
    return sorted(files)


def is_binary(path: str, data: bytes) -> bool:
    return PurePosixPath(path).suffix.lower() in BINARY_SUFFIXES or b"\0" in data[:8000]


def check_text(path: str, data: bytes, problems: list[Problem]) -> None:
    if data.startswith(b"\xef\xbb\xbf"):
        problems.append(Problem("BOM", path, "starts with a UTF-8 byte-order mark; save as UTF-8 without BOM."))
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as error:
        line = data[: error.start].count(b"\n") + 1
        problems.append(Problem("NOT_UTF8", path, f"is not valid UTF-8 (byte {error.start}).", line))
    if b"\r" in data:
        line = data[: data.index(b"\r")].count(b"\n") + 1
        problems.append(Problem("CRLF", path, "has CR or CRLF line endings; use LF.", line))
    if data and not data.endswith(b"\n"):
        problems.append(Problem("NO_FINAL_NEWLINE", path, "does not end with a newline."))


def check_forbidden(path: str, data: bytes, problems: list[Problem]) -> None:
    match = FORBIDDEN.search(path)
    if match:
        problems.append(Problem("FORBIDDEN_TERM", path, "the path contains a private project name."))
    text = data.decode("utf-8", "replace")
    match = FORBIDDEN.search(text)
    if match:
        line = text.count("\n", 0, match.start()) + 1
        problems.append(Problem("FORBIDDEN_TERM", path, "contains a private project name.", line))


def is_debris(path: str) -> bool:
    parts = PurePosixPath(path).parts
    return parts[:1] == ("skills",) and (
        "__pycache__" in parts
        or parts[-1] in DEBRIS_NAMES
        or PurePosixPath(path).suffix.lower() in DEBRIS_SUFFIXES
    )


def check_skill(root: Path, name: str, files: set[str], schema: ModuleType, problems: list[Problem]) -> None:
    base = f"skills/{name}"
    skill_md = f"{base}/SKILL.md"
    openai_yaml = f"{base}/agents/openai.yaml"
    if skill_md not in files:
        problems.append(Problem("SKILL_MD_MISSING", base, "has no SKILL.md."))
    else:
        report = schema.validate_skill_dir(root / "skills" / name, level="portable")
        for finding in report.findings:
            problems.append(Problem(f"FRONTMATTER_{finding.code}", skill_md, finding.message, finding.line))
    if openai_yaml not in files:
        problems.append(Problem("OPENAI_YAML_MISSING", base, "has no agents/openai.yaml."))
        return
    text = (root / openai_yaml).read_bytes().decode("utf-8", "replace")
    prompts = [
        (number, match.group(1))
        for number, line in enumerate(text.splitlines(), start=1)
        if (match := PROMPT_LINE.match(line))
    ]
    if not prompts:
        problems.append(Problem("DEFAULT_PROMPT_MISSING", openai_yaml, "has no interface default_prompt."))
        return
    number, prompt = prompts[0]
    if not re.search(re.escape(f"${name}") + r"(?![a-z0-9-])", prompt):
        problems.append(Problem("DEFAULT_PROMPT_NAME", openai_yaml, f"default_prompt does not name ${name}.", number))


def first_difference(first: bytes, second: bytes) -> int:
    """The 1-based line of the first byte where two texts differ."""
    index = next(
        (offset for offset, (a, b) in enumerate(zip(first, second)) if a != b),
        min(len(first), len(second)),
    )
    return first[:index].count(b"\n") + 1


def check_copies(root: Path, files: set[str], problems: list[Problem]) -> None:
    for copy, source in sorted(GENERATED_COPIES.items()):
        missing = [path for path in (copy, source) if path not in files]
        for path in missing:
            problems.append(Problem("COPY_MISSING", path, "is missing; it is half of a generated copy pair."))
        if missing:
            continue
        header = COPY_HEADER.format(source=source).encode("utf-8")
        data = (root / copy).read_bytes()
        if not data.startswith(header):
            problems.append(
                Problem("COPY_HEADER", copy, f"must start with the generated-copy header naming {source}.", 1)
            )
            continue
        body, expected = data[len(header) :], (root / source).read_bytes()
        if body != expected:
            problems.append(
                Problem(
                    "COPY_DRIFT",
                    copy,
                    f"differs from {source}; recopy it below the header.",
                    first_difference(body, expected) + 1,
                )
            )


def verify(root: Path) -> tuple[list[Problem], dict[str, object]]:
    schema = load_schema()
    files = git_inventory(root)
    mode = "git"
    if files is None:
        files, mode = walk_inventory(root), "filesystem"
    problems: list[Problem] = []
    skills = sorted(
        {
            PurePosixPath(path).parts[1]
            for path in files
            if PurePosixPath(path).parts[:1] == ("skills",)
            and len(PurePosixPath(path).parts) > 2
            and not PurePosixPath(path).parts[1].startswith(".")
        }
    )
    if not skills:
        problems.append(Problem("NO_SKILLS", "skills", "contains no skill folders."))
    broken = {path for path in files if (root / path).is_symlink() and not (root / path).is_file()}
    for path in sorted(broken):
        problems.append(
            Problem("BROKEN_SYMLINK", path, "is a symbolic link that does not resolve to a file.")
        )
    fileset = set(files) - broken
    for name in skills:
        check_skill(root, name, fileset, schema, problems)
    check_copies(root, fileset, problems)
    for path in files:
        if is_debris(path):
            problems.append(Problem("DEBRIS", path, "is generated debris; delete it before packaging."))
        if path in broken:
            continue
        data = (root / path).read_bytes()
        check_forbidden(path, data, problems)
        if not is_binary(path, data):
            check_text(path, data, problems)
    summary = {"root": str(root), "inventory": mode, "files": len(files), "skills": skills}
    return problems, summary


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT, help="package root (default: this repository)")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    if not root.is_dir():
        parser.error(f"--root is not a directory: {root}")
    problems, summary = verify(root)
    if args.as_json:
        print(json.dumps({**summary, "problems": [item.as_dict() for item in problems]}, indent=2))
    else:
        for problem in problems:
            print(problem.render())
        verdict = "FAIL" if problems else "PASS"
        print(
            f"{verdict}: {len(problems)} problem(s); {len(summary['skills'])} skills; "
            f"{summary['files']} files checked (inventory: {summary['inventory']})."
        )
    return 1 if problems else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:  # noqa: BLE001 - report, never mistake for a failed check
        print(f"verify_package.py: internal error: {error!r}", file=sys.stderr)
        sys.exit(3)
