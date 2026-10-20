#!/usr/bin/env python3
"""Verify the skill suite package in one pass and report every problem.

Checks skill structure, portable frontmatter (docs/SKILL_SCHEMA.md), the
tracked-text policy, public-term hygiene, generated debris inside skills,
symbolic links that do not resolve to a file, intentionally duplicated files,
which must stay byte-for-byte equal, the description and body budgets, and
the neutrality lint, which reports text that ties the suite to one author or
machine. Inside a git checkout the inventory comes from git, so git-ignored
files are skipped; elsewhere, such as an extracted archive, every file is
checked.

--lint runs only the neutrality lint, the same checks the default run makes.

Exit codes: 0 pass, 1 problems found, 2 usage error, 3 internal error.
Standard library only.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import fnmatch
import importlib.util
import json
import os
import re
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import ModuleType

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
SCHEMA_PATH = TOOLS / "lib" / "skill_frontmatter.py"

# Built from fragments, so this file never contains the term it forbids.
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
# Files that must stay byte-for-byte identical to one another. A pattern's
# '*' matches one path part.
IDENTICAL_GROUPS = ("skills/*/references/project-profile.md",)

# Budgets (docs/SKILL_SCHEMA.md, "Budgets"). Hosts list every description, so
# each one and their sum are capped in characters. A body's token estimate is
# its characters divided by CHARS_PER_TOKEN, rounded up: rough, but stable
# enough to compare one skill body with another and with its cap.
DESCRIPTION_CAP = 300
DESCRIPTION_TOTAL_CAP = 3600
CHARS_PER_TOKEN = 4
WORKFLOW_BODY_TOKEN_CAP = 1200
BODY_TOKEN_CAPS = {
    "game-context-continuity": 2000,
    "game-skill-auditor": 2500,
    "music-composer": 2000,
}

# Neutrality lint (part of the default run; --lint runs it alone). Every
# pattern is built from fragments, so this file never contains anything it
# reports.
# Only self-granting forms: ordinary consent text such as "after the user
# grants approval" or "to remove this local installation" is not a hit.
GRANT_PHRASES = (
    ("has", "stand" + "ing", "appro" + "val"),
    ("has", "stand" + "ing", "permis" + "sion"),
    ("gra" + "nts", "stand" + "ing"),
    ("gra" + "nted", "stand" + "ing"),
    ("This", "local", "instal" + "lation", "has", "stand" + "ing"),
    ("permis" + "sion", "as", "autho" + "rity"),
)
# Words may wrap onto the next line, so any whitespace separates them.
GRANT_FORM = re.compile(
    "|".join(r"\b" + r"\s+".join(map(re.escape, words)) + r"\b" for words in GRANT_PHRASES),
    re.IGNORECASE,
)
NEGATION = re.compile(r"\b(?:not|never|no|nobody|none|cannot|without|nor)\b|n't\b", re.IGNORECASE)
# A negation exempts a phrase only from the last few words of its own clause.
CLAUSE_BREAK = re.compile(r"[.!?;:,](?:\s|$)|\n\s*\n")
NEGATION_WINDOW = 3
# The profile template's field for pointing at a user's own written grant.
STANDING_FIELD = re.compile(r"^\s*[-*]\s*" + "Stand" + "ing appro" + r"vals\b", re.IGNORECASE)
NICKNAME = re.compile(r"\b" + "ch" + "ud" + r"s?\b", re.IGNORECASE)
# Windows (C:\\...), Git Bash (/c/...), WSL (/mnt/c/...), macOS, and Linux
# home folders. Each named group captures the account; a trailing slash is
# optional.
USER_PATH = re.compile(
    r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]{1,2}(?i:" + "us" + r"ers)[\\/]{1,2}"
    + r"(?P<win>[^\\/\s\"'`<>]+(?: (?i:users?)\b)?)"
    + r"|(?<![\w.~-])(?:/mnt)?/[A-Za-z]/(?i:" + "us" + r"ers)/(?P<drive>[A-Za-z0-9._-]+)(?![A-Za-z0-9._-])"
    + r"|(?<![\w.~-])/(?:" + "Us" + "ers|" + "ho" + r"me)/(?P<posix>[A-Za-z0-9._-]+)(?![A-Za-z0-9._-])"
)
# Shared Windows profiles and CI runner accounts are not personal.
SHARED_ACCOUNTS = {"public", "default", "default user", "all users", "runner", "runneradmin"}
EMAIL = re.compile(
    r"(?<![\w.%+-])[A-Za-z0-9._%+-]+@"
    r"(?P<domain>[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)*"
    r"\.(?P<tld>[A-Za-z]{2,24}))\b"
)
ALLOWED_EMAIL_DOMAINS = ("example.com", "example.org", "example.net")
# An "@2x" or "@1.5x" asset name, or a file suffix where a domain would end.
SCALED_ASSET = re.compile(r"\d+(?:\.\d+)?x\.", re.IGNORECASE)
FILE_SUFFIXES = {
    "avif", "bmp", "css", "gif", "html", "ico", "jpeg", "jpg", "js", "json", "md", "mp3", "mp4",
    "ogg", "otf", "pdf", "png", "py", "svg", "toml", "ttf", "txt", "wav", "webp", "woff", "woff2",
    "yaml", "yml",
}
# A wiki's Home.md is ordinary; vault folders are the private markers.
VAULT_NAME = re.compile(r"(?i:\." + "obsi" + r"dian)\b|\b" + "Wi" + r"ki/|\b" + "In" + r"box/")
LEDGER_FILE = "context_" + "continuity*.md"


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


def matches_parts(path: str, pattern: str) -> bool:
    parts, wanted = PurePosixPath(path).parts, PurePosixPath(pattern).parts
    return len(parts) == len(wanted) and all(
        fnmatch.fnmatchcase(part, glob) for part, glob in zip(parts, wanted)
    )


def check_identical(root: Path, files: set[str], problems: list[Problem]) -> None:
    """Report each copy that differs from the version most copies share."""
    for pattern in IDENTICAL_GROUPS:
        group = sorted(path for path in files if matches_parts(path, pattern))
        contents = {path: (root / path).read_bytes() for path in group}
        counts = Counter(contents.values())
        if len(counts) < 2:
            continue
        # The majority wins. Counter keeps first-seen order and max() keeps the
        # first maximum, so on a tie the alphabetically first copy wins.
        expected = max(counts, key=counts.__getitem__)
        reference = next(path for path in group if contents[path] == expected)
        for path in group:
            if contents[path] != expected:
                problems.append(
                    Problem(
                        "IDENTICAL_DRIFT",
                        path,
                        f"differs from {reference}, which {counts[expected]} of the {len(group)} "
                        f"files matching {pattern} share; keep them identical.",
                        first_difference(contents[path], expected),
                    )
                )


def estimated_tokens(text: str) -> int:
    return -(-len(text) // CHARS_PER_TOKEN)


def skill_body(text: str) -> str | None:
    """The text after the closing frontmatter delimiter, or None without one."""
    lines = text.split("\n")
    if lines[0].rstrip(" \t") != "---":
        return None
    for index in range(1, len(lines)):
        if lines[index].rstrip(" \t") == "---":
            return "\n".join(lines[index + 1 :])
    return None


def check_budgets(
    root: Path, skills: list[str], files: set[str], schema: ModuleType, problems: list[Problem]
) -> dict[str, object]:
    """Cap each description, their total, and each body's estimated tokens."""
    rows: dict[str, dict[str, int]] = {}
    total = 0
    for name in skills:
        skill_md = f"skills/{name}/SKILL.md"
        if skill_md not in files:
            continue
        data = (root / skill_md).read_bytes()
        description = schema.validate_text(data, folder=name).frontmatter.get("description")
        length = len(description) if isinstance(description, str) else 0
        total += length
        text = data.decode("utf-8", "replace").replace("\r\n", "\n")
        body = skill_body(text)
        tokens = estimated_tokens(body) if body is not None else 0
        cap = BODY_TOKEN_CAPS.get(name, WORKFLOW_BODY_TOKEN_CAP)
        rows[name] = {"description_characters": length, "body_estimated_tokens": tokens, "body_token_cap": cap}
        if length > DESCRIPTION_CAP:
            line = next(
                (number for number, row in enumerate(text.split("\n"), 1) if row.startswith("description:")),
                None,
            )
            problems.append(
                Problem(
                    "DESCRIPTION_BUDGET",
                    skill_md,
                    f"the description has {length} characters; the cap is {DESCRIPTION_CAP}.",
                    line,
                )
            )
        if tokens > cap:
            problems.append(
                Problem(
                    "BODY_BUDGET",
                    skill_md,
                    f"the body is about {tokens} estimated tokens (characters / {CHARS_PER_TOKEN}); "
                    f"the cap is {cap}. Move detail into an on-demand reference.",
                )
            )
    if total > DESCRIPTION_TOTAL_CAP:
        problems.append(
            Problem(
                "DESCRIPTION_TOTAL",
                "skills",
                f"descriptions total {total} characters; the suite cap is {DESCRIPTION_TOTAL_CAP}.",
            )
        )
    return {
        "description_cap": DESCRIPTION_CAP,
        "description_total": total,
        "description_total_cap": DESCRIPTION_TOTAL_CAP,
        "chars_per_token": CHARS_PER_TOKEN,
        "skills": rows,
    }


def render_budgets(budgets: dict[str, object]) -> list[str]:
    rows = budgets["skills"]
    width = max((len(name) for name in rows), default=5)
    lines = [f"{'skill':<{width}}  description  body tokens"]
    for name, row in rows.items():
        lines.append(
            f"{name:<{width}}  {row['description_characters']:>4}/{budgets['description_cap']:<6}"
            f"  {row['body_estimated_tokens']:>4}/{row['body_token_cap']}"
        )
    lines.append(f"{'total':<{width}}  {budgets['description_total']:>4}/{budgets['description_total_cap']}")
    return lines


def line_at(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def negated(text: str, start: int) -> bool:
    """Whether the words just before a phrase negate it, as in 'nobody has ...'.

    Only the last NEGATION_WINDOW words of the phrase's own clause count, so
    "Ask nobody; the agent has ..." is still a hit.
    """
    clause = CLAUSE_BREAK.split(text[max(0, start - 80) : start])[-1]
    words = re.findall(r"[A-Za-z']+", clause)[-NEGATION_WINDOW:]
    return NEGATION.search(" ".join(words)) is not None


def user_path_lines(text: str) -> list[int]:
    """Lines holding a personal home-folder path; shared and CI accounts pass."""
    lines = set()
    for match in USER_PATH.finditer(text):
        account = next(value for value in match.group("win", "drive", "posix") if value is not None)
        if account.casefold() not in SHARED_ACCOUNTS:
            lines.add(line_at(text, match.start()))
    return sorted(lines)


def email_lines(text: str) -> list[int]:
    """Lines holding a personal email address."""
    lines = set()
    for match in EMAIL.finditer(text):
        domain = match.group("domain")
        if SCALED_ASSET.match(domain) or match.group("tld").casefold() in FILE_SUFFIXES:
            continue
        if not email_allowed(match.group(0)):
            lines.add(line_at(text, match.start()))
    return sorted(lines)


def grant_hits(text: str) -> list[tuple[int, int, str]]:
    """Grant phrases as (first line, last line, phrases), merging adjacent ones."""
    spans: list[list[object]] = []
    for match in GRANT_FORM.finditer(text):
        line_start = text.rfind("\n", 0, match.start()) + 1
        line_end = text.find("\n", match.start())
        line = text[line_start : line_end if line_end >= 0 else len(text)]
        if STANDING_FIELD.match(line) or negated(text, match.start()):
            continue
        phrase = " ".join(match.group(0).split())
        if spans and not text[spans[-1][1] : match.start()].strip():
            spans[-1][1] = max(spans[-1][1], match.end())
            spans[-1][2] = f"{spans[-1][2]} + {phrase}"
        else:
            spans.append([match.start(), match.end(), phrase])
    return [(line_at(text, start), line_at(text, end - 1), phrase) for start, end, phrase in spans]


def email_allowed(address: str) -> bool:
    folded = address.casefold()
    domain = folded.rsplit("@", 1)[1]
    return (
        "noreply" in folded
        or "no-reply" in folded
        # An SSH remote such as git@<host>:owner/repo.git names no person.
        or folded.startswith("git@")
        or any(domain == allowed or domain.endswith("." + allowed) for allowed in ALLOWED_EMAIL_DOMAINS)
    )


def lint_text(path: str, text: str, problems: list[Problem]) -> None:
    for first, last, phrase in grant_hits(text):
        where = f"lines {first}-{last}" if last > first else f"line {first}"
        problems.append(
            Problem("LINT_GRANT_FORM", path, f"reads as a standing permission the text grants itself ({where}: '{phrase}').", first)
        )
    simple = (
        ("LINT_AGENT_NICKNAME", NICKNAME, "uses an author-specific delegated-agent nickname"),
        ("LINT_VAULT_NAME", VAULT_NAME, "names a private vault folder"),
    )
    for code, pattern, message in simple:
        lines = sorted({line_at(text, match.start()) for match in pattern.finditer(text)})
        for line in lines:
            problems.append(Problem(code, path, f"{message}.", line))
    for line in user_path_lines(text):
        problems.append(Problem("LINT_USER_PATH", path, "contains an absolute user path.", line))
    for line in email_lines(text):
        problems.append(Problem("LINT_PERSONAL_EMAIL", path, "contains a personal email address.", line))


def lint_files(root: Path, files: list[str], problems: list[Problem]) -> None:
    """The neutrality lint: findings for text that ties the suite to one author."""
    for path in files:
        if fnmatch.fnmatchcase(PurePosixPath(path).name.casefold(), LEDGER_FILE):
            problems.append(Problem("LINT_CONTINUITY_LEDGER", path, "is a continuity ledger; never commit one."))
        if user_path_lines(path):
            problems.append(Problem("LINT_USER_PATH", path, "the path contains an absolute user path."))
        for code, pattern, message in (
            ("LINT_VAULT_NAME", VAULT_NAME, "the path names a private vault folder."),
            ("LINT_AGENT_NICKNAME", NICKNAME, "the path uses an author-specific nickname."),
        ):
            if pattern.search(path):
                problems.append(Problem(code, path, message))
        full = root / path
        if full.is_symlink() and not full.is_file():
            continue
        data = full.read_bytes()
        if not is_binary(path, data):
            lint_text(path, data.decode("utf-8", "replace"), problems)


def lint(root: Path) -> tuple[list[Problem], dict[str, object]]:
    """Only the neutrality lint, for --lint."""
    files = git_inventory(root)
    mode = "git"
    if files is None:
        files, mode = walk_inventory(root), "filesystem"
    problems: list[Problem] = []
    lint_files(root, files, problems)
    summary = {"root": str(root), "inventory": mode, "files": len(files), "mode": "lint"}
    return problems, summary


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
    check_identical(root, fileset, problems)
    budgets = check_budgets(root, skills, fileset, schema, problems)
    for path in files:
        if is_debris(path):
            problems.append(Problem("DEBRIS", path, "is generated debris; delete it before packaging."))
        if path in broken:
            continue
        data = (root / path).read_bytes()
        check_forbidden(path, data, problems)
        if not is_binary(path, data):
            check_text(path, data, problems)
    lint_files(root, files, problems)
    summary = {"root": str(root), "inventory": mode, "files": len(files), "skills": skills, "budgets": budgets}
    return problems, summary


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT, help="package root (default: this repository)")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument(
        "--lint",
        action="store_true",
        help=(
            "run only the neutrality lint, which the default run also makes: "
            "self-granted permission, author-specific names, absolute user paths, "
            "personal email addresses, private vault names, and committed continuity ledgers"
        ),
    )
    parser.add_argument(
        "--budgets",
        action="store_true",
        help="also print each skill's description length and estimated body tokens against its cap",
    )
    args = parser.parse_args(argv)
    root = args.root.resolve()
    if not root.is_dir():
        parser.error(f"--root is not a directory: {root}")
    problems, summary = lint(root) if args.lint else verify(root)
    if args.as_json:
        print(json.dumps({**summary, "problems": [item.as_dict() for item in problems]}, indent=2))
    else:
        for problem in problems:
            print(problem.render())
        if not args.lint:
            budgets = summary["budgets"]
            if args.budgets:
                for line in render_budgets(budgets):
                    print(line)
            print(
                f"Budgets: descriptions total {budgets['description_total']} of "
                f"{budgets['description_total_cap']} characters, at most {budgets['description_cap']} each; "
                "--budgets lists every skill."
            )
        verdict = "FAIL" if problems else "PASS"
        scope = "neutrality lint" if args.lint else f"{len(summary['skills'])} skills, budgets, and neutrality lint"
        print(
            f"{verdict}: {len(problems)} problem(s); {scope}; "
            f"{summary['files']} files checked (inventory: {summary['inventory']})."
        )
    return 1 if problems else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:  # noqa: BLE001 - report, never mistake for a failed check
        print(f"verify_package.py: internal error: {error!r}", file=sys.stderr)
        sys.exit(3)
