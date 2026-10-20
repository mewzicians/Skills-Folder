#!/usr/bin/env python3
"""Verify the skill suite package in one pass and report every problem.

Checks skill structure, portable frontmatter (docs/SKILL_SCHEMA.md), the
tracked-text policy, public-term hygiene, generated debris inside skills,
symbolic links that do not resolve to a file, intentionally duplicated files,
which must stay byte-for-byte equal and present in every skill not exempt
from carrying one, the explicit-only skills' invocation policy and wording,
the root plugin's manifests and marketplaces, the description and body
budgets, and the neutrality lint, which reports text that ties the suite to
one author or machine. Inside a git checkout the inventory comes from git, so
git-ignored files are skipped; elsewhere, such as an extracted archive, every
file is checked.

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
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import ModuleType

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
SCHEMA_PATH = TOOLS / "lib" / "skill_frontmatter.py"

# Built from fragments, so this file never contains the term it forbids. Any
# run of whitespace, hyphens, or underscores may separate the two words, in any
# case, so spaced names and slugs such as kebab, snake, and joined forms match.
FORBIDDEN = re.compile(
    "(?i)"
    + ("office" + r"[\s_-]*" + "wars")
    + "|"
    + ("offie" + r"[\s_-]*" + "war")
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
# Files that must stay byte-for-byte identical to one another, as
# {pattern: skills exempt from carrying one}. The pattern's one '*' stands for
# a skill folder. Every other skill must carry a copy, so deleting one, or
# adding a skill without one, fails; an exempt skill that gains one fails too,
# so the exemption stays exact.
IDENTICAL_GROUPS = {
    # The auditor audits skills rather than a game, so it has no profile router.
    "skills/*/references/project-profile.md": frozenset({"game-skill-auditor"}),
}

# Skills with side effects run only when the user names them
# (docs/SKILL_SCHEMA.md, "Explicit-Only Skills"). Each keeps Codex's switch off
# in agents/openai.yaml and says so in its description for Claude Code.
EXPLICIT_ONLY = ("game-full-verification", "game-qa-cleanup", "game-release")
EXPLICIT_WORDING = "Use when the user explicitly asks"
TOP_LEVEL_KEY = re.compile(r"^(?P<key>[A-Za-z_][\w-]*):\s*(?:#.*)?$")
IMPLICIT_OFF = re.compile(r"^\s+allow_implicit_invocation:\s*false\s*(?:#.*)?$")

# Budgets (docs/SKILL_SCHEMA.md, "Budgets"). Hosts list every description, so
# each one and their sum are capped in characters. A body's token estimate is
# its characters divided by CHARS_PER_TOKEN, rounded up: rough, but stable
# enough to compare one skill body with another and with its cap.
DESCRIPTION_CAP = 300
DESCRIPTION_TOTAL_CAP = 3600
CHARS_PER_TOKEN = 4
# Body caps are deliberate ratchets. Lower one when a body shrinks for good;
# raise one only to restore a rule that cannot move into a reference, by at
# most 10% at a time, and record the reason here and in docs/SKILL_SCHEMA.md.
WORKFLOW_BODY_TOKEN_CAP = 1200
BODY_TOKEN_CAPS = {
    "game-context-continuity": 2000,
    "game-skill-auditor": 2500,
    # 2000 until the C2 review: raised 10% to restore the scope gate, which
    # classifies a request before any project read, and the project-attached
    # reads, after the working-mode detail moved into a reference.
    "music-composer": 2200,
}

# Neutrality lint (part of the default run; --lint runs it alone). Every
# pattern is built from fragments, so this file never contains anything it
# reports.
#
# Text is normalized before matching, and never gains or loses a line break, so
# line numbers still point at the original: NFKC folds full-width and other
# compatibility forms, zero-width characters and soft hyphens are dropped, and
# common Cyrillic and Greek lookalikes become the Latin letters they imitate.
# The prose checks (grant forms and the nickname) also drop Markdown emphasis
# and code marks.
ZERO_WIDTH = dict.fromkeys(map(ord, "\u00ad\u180e\u200b\u200c\u200d\u2060\ufeff"))
LOOKALIKES = str.maketrans(
    "\u0410\u0412\u0415\u041a\u041c\u041d\u041e\u0420\u0421\u0422\u0425\u0405\u0406\u0408"
    "\u0430\u0435\u043e\u0440\u0441\u0443\u0445\u0455\u0456\u0458\u04bb"
    "\u0391\u0392\u0395\u0396\u0397\u0399\u039a\u039c\u039d\u039f\u03a1\u03a4\u03a5\u03a7"
    "\u03bf\u03b1\u03b9\u03ba\u03bd\u03c1\u03c4\u03c5",
    "ABEKMHOPCTXSIJ" "aeopcyxsijh" "ABEZHIKMNOPTYX" "oaikvptu",
)
PROSE_MARKS = str.maketrans({"*": "", "`": "", "_": " ", "\u2019": "'"})

# Only self-granting forms: consent text such as "after the user grants
# approval", "to remove this local installation", or a court that grants
# standing to a plaintiff is not a hit. Words may wrap onto the next line or
# join with hyphens.
SEP = r"[\s-]+"
STANDING = "stand" + "ing"
GRANT_OBJECT = "(?:appro" + "vals?|permis" + "sions?)"
GRANT_FORMS = (
    # has, have, holds, carries, or assumes + standing + approval or permission
    r"\b(?:has|have|holds?|carr(?:y|ies)|assumes?)" + SEP + STANDING + SEP + GRANT_OBJECT,
    # grant, grants, granted, or granting + standing + approval or permission
    r"\bgra" + "nt(?:s|ed|ing)?" + SEP + STANDING + SEP + GRANT_OBJECT,
    # give, gives, given, or giving, then up to two words such as "the agent"
    r"\bgiv(?:e|es|en|ing)(?:" + SEP + "[A-Za-z]+){0,2}" + SEP + STANDING + SEP + GRANT_OBJECT,
    # standing + approval or permission + is, are, was, were, or has been + granted
    r"\b" + STANDING + SEP + GRANT_OBJECT + SEP
    + r"(?:is|are|was|were|(?:has|have)" + SEP + "been)(?:" + SEP + "hereby)?" + SEP + "gra" + "nted",
    r"\bthis" + SEP + "local" + SEP + "instal" + "lation" + SEP + "has" + SEP + STANDING,
    r"\bpermis" + "sion" + SEP + "as" + SEP + "autho" + "rity",
    r"\b(?:is|are)" + SEP + "pre-?appro" + "ved" + SEP + "(?:to|for)",
    r"\bwith" + "out" + SEP + "ask" + "ing" + "(?:" + SEP + "for)?" + SEP + GRANT_OBJECT,
)
GRANT_FORM = re.compile("|".join(f"(?:{form})" + r"\b" for form in GRANT_FORMS), re.IGNORECASE)
# A grant form is exempt when, within its own clause, a negator stands at most
# two words before it ("nobody has", "never grants", "does not have"), or a
# condition introduces it ("if", "whether", "unless", or "until", "once",
# "after", "when", or "before" with a grant the user gives in writing), or the
# sentence is a question, or it is quoted after a negation ("do not write '...'").
# A conjunction ends the search, so "asks no questions and has" is still a hit.
WORD = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
NEGATORS = {"cannot", "neither", "never", "no", "nobody", "none", "nor", "not", "nothing", "nowhere", "without"}
NEGATION_REACH = 3
CONJUNCTIONS = {
    "although", "and", "as", "because", "but", "for", "hence", "or", "since", "so", "then", "though",
    "thus", "while", "yet",
}
CONDITIONALS = {"if", "unless", "whether"}
TIME_CONDITIONS = {"after", "before", "once", "until", "when"}
IN_WRITING = re.compile(r"\bin\s+writ" + r"ing\b", re.IGNORECASE)
CLAUSE_BREAK = re.compile(r"[.!?;:,](?:\s|$)|\n\s*\n|\n\s*(?:[-+]|\d+[.)])\s")
SENTENCE_END = re.compile(r"[.!?](?=\s|$)|\n\s*\n")
QUOTES = "'\"\u201c\u201d\u2018"
# The profile template's field for pointing at a user's own written grant,
# exempt only as this exact line.
STANDING_FIELD = "- Stand" + "ing approvals (path to the user's own written grant; default none):"
NICKNAME = re.compile(r"\b" + "ch" + "ud" + r"s?\b", re.IGNORECASE)
# Windows drive paths (also in file URLs, where the colon may be %3A), UNC
# shares, Git Bash (/c/...), WSL (/mnt/c/...), macOS, and Linux home folders,
# and tilde-account paths. Each named group captures the account; a trailing
# slash is optional.
USER_PATH = re.compile(
    r"(?<![A-Za-z0-9])[A-Za-z](?::|%3[Aa])[\\/]{1,2}(?i:" + "us" + r"ers)[\\/]{1,2}"
    + r"(?P<win>[^\\/\s\"'`<>]+(?: (?i:users?)\b)?)"
    + r"|(?<![\\\w])\\\\[^\\/\s]+\\(?i:" + "us" + r"ers)\\(?P<unc>[^\\/\s\"'`<>]+)"
    + r"|(?<![\w.~-])(?:/mnt)?/[A-Za-z]/(?i:" + "us" + r"ers)/(?P<drive>[A-Za-z0-9._-]+)(?![A-Za-z0-9._-])"
    + r"|(?<![\w.~-])/(?:" + "Us" + "ers|" + "ho" + r"me)/(?P<posix>[A-Za-z0-9._-]+)(?![A-Za-z0-9._-])"
    + r"|(?<![\w~])~(?P<tilde>[A-Za-z][A-Za-z0-9._-]*)(?=[\\/])"
)
# Shared Windows profiles, CI runner and package-manager accounts, and
# placeholders such as USERNAME, %USERNAME%, $env:USERNAME, or <user> are not
# personal.
SHARED_ACCOUNTS = {
    "all users", "default", "default user", "linuxbrew", "name", "public", "runner", "runneradmin",
    "shared", "user", "username", "you",
}
PLACEHOLDER_MARKS = re.compile(r"^\$(?:env:)?|[%{}<>\[\]]", re.IGNORECASE)
EMAIL = re.compile(
    r"(?<![\w.%+-])[\w.%+-]+@"
    r"(?P<domain>[^\W_](?:[\w-]*[^\W_])?(?:\.[^\W_](?:[\w-]*[^\W_])?)*\.(?P<tld>[^\W\d_]{2,24}))\b"
)
# Documentation domains (RFC 2606), noreply domains, and SSH remotes on known
# git hosts name no person. Each is matched as a whole domain.
ALLOWED_EMAIL_DOMAINS = ("example.com", "example.org", "example.net")
RESERVED_TLDS = {"example", "invalid", "localhost", "test"}
NOREPLY_DOMAINS = {"users.noreply.github.com", "users.noreply.gitlab.com", "users.noreply.codeberg.org"}
SERVICE_ADDRESSES = {"noreply@" + "github.com"}
GIT_HOSTS = {
    "bitbucket.org", "codeberg.org", "gitea.com", "github.com", "gitlab.com", "git.sr.ht",
    "ssh.dev.azure.com", "vs-ssh.visualstudio.com",
}
# An SSH login names a host account, not a person: after ssh, scp, sftp, or
# rsync, after ssh://, or on a host inside an internal-only domain.
SSH_TARGET = re.compile(r"(?:\b(?:ssh|scp|sftp|rsync)(?:\s+-\S+(?:\s+\d+)?)*\s+|ssh://)$", re.IGNORECASE)
INTERNAL_LABELS = {"internal", "intranet", "lan", "local", "localdomain"}
# An "@2x" or "@1.5x" asset name, or a file suffix where a domain would end.
SCALED_ASSET = re.compile(r"\d+(?:\.\d+)?x\.", re.IGNORECASE)
FILE_SUFFIXES = {
    "avif", "bmp", "css", "gif", "html", "ico", "jpeg", "jpg", "js", "json", "md", "mp3", "mp4",
    "ogg", "otf", "pdf", "png", "py", "svg", "toml", "ttf", "txt", "wav", "webp", "woff", "woff2",
    "yaml", "yml",
}
# Vault markers, matched only as exact folder names: the Obsidian settings
# folder (not a longer name that starts the same way) or a capitalized Wiki
# folder marks a vault on its own. An Inbox folder or a lowercase wiki folder is
# ordinary alone and a marker only alongside another marker. A wiki's Home.md is
# ordinary.
STRONG_VAULT = re.compile(
    r"(?<![\w.-])\.(?i:" + "obsi" + r"dian)(?![\w-])(?!\.\w)|(?<![\w.-])" + "Wi" + r"ki[\\/]"
)
WEAK_VAULT = re.compile(r"(?<![\w.-])(?i:(?P<kind>" + "in" + "box|" + "wi" + r"ki))[\\/]")
LEDGER_FILE = "context_" + "continuity*.md"

# Plugin manifests. The repository root is one plugin for both hosts. Claude
# Code reads .claude-plugin/plugin.json and the marketplace beside it; Codex
# and other Agent Plugins 1.0.0 clients read the portable plugin.json, and
# Codex reads .agents/plugins/marketplace.json. The portable file's rules
# restate https://agent-plugins.org/schemas/1.0.0/plugin.schema.json with the
# standard library; client-specific keys belong under its extensions.
CLAUDE_MANIFEST = ".claude-plugin/plugin.json"
CLAUDE_MARKETPLACE = ".claude-plugin/marketplace.json"
PORTABLE_MANIFEST = "plugin.json"
CODEX_MARKETPLACE = ".agents/plugins/marketplace.json"
PLUGIN_SCHEMA_URL = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
PORTABLE_KEYS = {
    "$schema", "name", "version", "description", "author", "homepage", "repository", "license",
    "keywords", "extensions",
}
PORTABLE_NAME = re.compile(r"^(?!.*(?:--|\.\.))[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")
AUTHOR_KEYS = {"name", "email", "url"}
EXTENSION_NAMESPACE = re.compile(r"^[a-z0-9-]+(?:\.[a-z0-9-]+)+$")
KEBAB_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
# Claude Code refuses these plugin and marketplace names; the suite also avoids
# the generic "agent-skills".
RESERVED_PREFIXES = ("claude-", "anthropic-", "anthropics-", "cc-plugin-")
RESERVED_NAMES = {"claude", "anthropic", "claude-code", "claude-mods", "agent-skills"}
SUITE_LICENSE = "Apache-2.0"

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
    # The lint's normalization also catches full-width and lookalike spellings.
    match = FORBIDDEN.search(normalize(path))
    if match:
        problems.append(Problem("FORBIDDEN_TERM", path, "the path contains a private project name."))
    text = normalize(data.decode("utf-8", "replace"))
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


def implicit_invocation_disabled(text: str) -> bool:
    """Whether agents/openai.yaml sets policy.allow_implicit_invocation: false."""
    in_policy = False
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line[0].isspace():
            match = TOP_LEVEL_KEY.match(line)
            in_policy = match is not None and match.group("key") == "policy"
        elif in_policy and IMPLICIT_OFF.match(line):
            return True
    return False


def check_explicit_only(root: Path, files: set[str], schema: ModuleType, problems: list[Problem]) -> None:
    """Each explicit-only skill keeps its policy switch off and its explicit wording."""
    for name in EXPLICIT_ONLY:
        skill_md = f"skills/{name}/SKILL.md"
        metadata = f"skills/{name}/agents/openai.yaml"
        if skill_md not in files:
            problems.append(Problem("EXPLICIT_ONLY_MISSING", f"skills/{name}", "is an explicit-only skill, but it is missing."))
            continue
        data = (root / skill_md).read_bytes()
        description = schema.validate_text(data, folder=name).frontmatter.get("description")
        if not isinstance(description, str) or EXPLICIT_WORDING not in description:
            line = next(
                (
                    number
                    for number, row in enumerate(data.decode("utf-8", "replace").split("\n"), 1)
                    if row.startswith("description:")
                ),
                None,
            )
            problems.append(
                Problem(
                    "EXPLICIT_ONLY_WORDING",
                    skill_md,
                    f"is explicit-only, so its description must say \"{EXPLICIT_WORDING} ...\".",
                    line,
                )
            )
        if metadata in files and not implicit_invocation_disabled(
            (root / metadata).read_bytes().decode("utf-8", "replace")
        ):
            problems.append(
                Problem(
                    "EXPLICIT_ONLY_POLICY",
                    metadata,
                    "is explicit-only, so it must set policy.allow_implicit_invocation: false.",
                )
            )


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


def check_identical(root: Path, files: set[str], skills: list[str], problems: list[Problem]) -> None:
    """Report a missing or unexpected copy, and each copy that differs from the version most share."""
    for pattern, exempt in IDENTICAL_GROUPS.items():
        for name in skills:
            expected = pattern.replace("*", name, 1)
            if name not in exempt and expected not in files:
                problems.append(
                    Problem(
                        "IDENTICAL_MISSING",
                        expected,
                        f"is missing; every skill except {', '.join(sorted(exempt)) or 'none'} "
                        f"carries an identical copy of {pattern}.",
                    )
                )
            elif name in exempt and expected in files:
                problems.append(
                    Problem(
                        "IDENTICAL_UNEXPECTED",
                        expected,
                        f"exists, but {name} is exempt from {pattern}; remove the copy or the exemption.",
                    )
                )
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


def load_manifest(root: Path, path: str, files: set[str], problems: list[Problem]) -> dict | None:
    """A manifest's JSON object, or None after reporting why it cannot be read."""
    if path not in files:
        problems.append(Problem("MANIFEST_MISSING", path, "is missing; the root plugin needs every manifest."))
        return None
    data = (root / path).read_bytes()
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        line = getattr(error, "lineno", None)
        problems.append(Problem("MANIFEST_JSON", path, f"is not valid UTF-8 JSON: {error}.", line))
        return None
    if not isinstance(value, dict):
        problems.append(Problem("MANIFEST_JSON", path, "must hold one JSON object."))
        return None
    return value


def text_value(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def require_text(manifest: dict, keys: tuple[str, ...], path: str, problems: list[Problem], where: str = "") -> None:
    for key in keys:
        if not text_value(manifest.get(key)):
            problems.append(Problem("MANIFEST_KEY", path, f"needs a non-empty string {where}{key}."))


def check_plugin_name(name: object, path: str, problems: list[Problem], what: str = "name") -> None:
    if not isinstance(name, str):
        return
    if not KEBAB_NAME.match(name) or len(name) > 64:
        problems.append(Problem("MANIFEST_NAME", path, f"{what} {name!r} must be kebab-case, at most 64 characters."))
    if name in RESERVED_NAMES or name.startswith(RESERVED_PREFIXES):
        problems.append(Problem("MANIFEST_NAME", path, f"{what} {name!r} is reserved by an agent host; choose another."))


def check_author(author: object, path: str, problems: list[Problem]) -> None:
    if not isinstance(author, dict) or not text_value(author.get("name")):
        problems.append(Problem("MANIFEST_KEY", path, "needs author as an object with a non-empty name."))
        return
    for key, value in author.items():
        if key not in AUTHOR_KEYS or not isinstance(value, str):
            problems.append(Problem("MANIFEST_SCHEMA", path, f"author.{key} must be one of name, email, or url, as a string."))


def check_portable_manifest(manifest: dict, path: str, problems: list[Problem]) -> None:
    """The Agent Plugins 1.0.0 schema, plus the keys this suite always fills."""
    if manifest.get("$schema") != PLUGIN_SCHEMA_URL:
        problems.append(Problem("MANIFEST_SCHEMA", path, f"$schema must be {PLUGIN_SCHEMA_URL}."))
    name = manifest.get("name")
    if not isinstance(name, str) or not 1 <= len(name) <= 64 or not PORTABLE_NAME.match(name):
        problems.append(
            Problem("MANIFEST_SCHEMA", path, "name must be 1-64 lowercase letters, digits, dots, or single hyphens.")
        )
    for key in sorted(set(manifest) - PORTABLE_KEYS):
        problems.append(
            Problem("MANIFEST_SCHEMA", path, f"{key!r} is not an Agent Plugins key; put client data under extensions.")
        )
    for key in ("version", "description", "homepage", "repository", "license"):
        if key in manifest and not isinstance(manifest[key], str):
            problems.append(Problem("MANIFEST_SCHEMA", path, f"{key} must be a string."))
    keywords = manifest.get("keywords", [])
    if not isinstance(keywords, list) or not all(isinstance(word, str) for word in keywords):
        problems.append(Problem("MANIFEST_SCHEMA", path, "keywords must be a list of strings."))
    extensions = manifest.get("extensions", {})
    if not isinstance(extensions, dict):
        problems.append(Problem("MANIFEST_SCHEMA", path, "extensions must be an object."))
    else:
        for namespace, value in extensions.items():
            if not EXTENSION_NAMESPACE.match(namespace) or not isinstance(value, dict):
                problems.append(
                    Problem(
                        "MANIFEST_SCHEMA",
                        path,
                        f"extensions.{namespace} must be a reverse-domain namespace holding an object.",
                    )
                )
    if "author" in manifest:
        check_author(manifest["author"], path, problems)
    require_text(manifest, ("version", "description", "license"), path, problems)


def check_manifests(root: Path, files: set[str], problems: list[Problem]) -> dict[str, dict]:
    """Each plugin manifest parses, carries its required keys, and names the same plugin."""
    loaded = {
        path: manifest
        for path in (CLAUDE_MANIFEST, CLAUDE_MARKETPLACE, PORTABLE_MANIFEST, CODEX_MARKETPLACE)
        if (manifest := load_manifest(root, path, files, problems)) is not None
    }
    plugin_names = {}
    claude = loaded.get(CLAUDE_MANIFEST)
    if claude is not None:
        require_text(claude, ("name", "version", "description", "homepage", "repository", "license"), CLAUDE_MANIFEST, problems)
        check_author(claude.get("author"), CLAUDE_MANIFEST, problems)
        check_plugin_name(claude.get("name"), CLAUDE_MANIFEST, problems)
        plugin_names[CLAUDE_MANIFEST] = claude.get("name")
    portable = loaded.get(PORTABLE_MANIFEST)
    if portable is not None:
        check_portable_manifest(portable, PORTABLE_MANIFEST, problems)
        check_plugin_name(portable.get("name"), PORTABLE_MANIFEST, problems)
        plugin_names[PORTABLE_MANIFEST] = portable.get("name")
    for path, manifest in ((CLAUDE_MANIFEST, claude), (PORTABLE_MANIFEST, portable)):
        if manifest is not None and text_value(manifest.get("license")) and manifest["license"] != SUITE_LICENSE:
            problems.append(Problem("MANIFEST_KEY", path, f"license must be {SUITE_LICENSE}, as in LICENSE."))
    for path in (CLAUDE_MARKETPLACE, CODEX_MARKETPLACE):
        marketplace = loaded.get(path)
        if marketplace is None:
            continue
        require_text(marketplace, ("name",), path, problems)
        check_plugin_name(marketplace.get("name"), path, problems, "marketplace name")
        if path == CLAUDE_MARKETPLACE:
            owner = marketplace.get("owner")
            if not isinstance(owner, dict) or not text_value(owner.get("name")):
                problems.append(Problem("MANIFEST_KEY", path, "needs owner as an object with a non-empty name."))
        entries = marketplace.get("plugins")
        if not isinstance(entries, list) or not entries or not all(isinstance(entry, dict) for entry in entries):
            problems.append(Problem("MANIFEST_KEY", path, "needs plugins as a non-empty list of objects."))
            continue
        for index, entry in enumerate(entries):
            where = f"plugins[{index}]."
            require_text(entry, ("name",), path, problems, where)
            source = entry.get("source")
            if not (text_value(source) or (isinstance(source, dict) and text_value(source.get("source")))):
                problems.append(Problem("MANIFEST_KEY", path, f"needs {where}source as a path or a source object."))
            if path == CLAUDE_MARKETPLACE and isinstance(source, str) and source != "./":
                problems.append(Problem("MANIFEST_KEY", path, f"{where}source must be './', the repository root plugin."))
            if path == CODEX_MARKETPLACE:
                policy = entry.get("policy")
                if not isinstance(policy, dict):
                    problems.append(Problem("MANIFEST_KEY", path, f"needs {where}policy as an object."))
                else:
                    require_text(policy, ("installation", "authentication"), path, problems, where + "policy.")
                require_text(entry, ("category",), path, problems, where)
            plugin_names[f"{path} {where}name"] = entry.get("name")
    named = {where: name for where, name in plugin_names.items() if isinstance(name, str)}
    if len(set(named.values())) > 1:
        listing = ", ".join(f"{where} = {name!r}" for where, name in sorted(named.items()))
        problems.append(Problem("MANIFEST_NAME", PORTABLE_MANIFEST, f"the plugin names disagree: {listing}."))
    plugin_folder = sorted(path for path in files if PurePosixPath(path).parts[:1] == ("agents",))
    if plugin_folder:
        problems.append(
            Problem(
                "MANIFEST_AGENTS_FOLDER",
                plugin_folder[0],
                "the root plugin carries no agents/ folder; hosts would load it as plugin subagents.",
            )
        )
    return loaded


def line_at(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def normalize(text: str) -> str:
    """Fold compatibility forms and lookalike letters, and drop zero-width characters.

    Every step keeps each line break, so line numbers in the result still
    point at the original text.
    """
    return unicodedata.normalize("NFKC", text.translate(ZERO_WIDTH)).translate(LOOKALIKES)


def prose(text: str) -> str:
    """The normalized text without Markdown emphasis or code marks."""
    return normalize(text).translate(PROSE_MARKS)


def clause_before(text: str, start: int) -> str:
    """The text from the start of a phrase's clause up to the phrase."""
    return CLAUSE_BREAK.split(text[max(0, start - 200) : start])[-1]


def sentence_after(text: str, end: int) -> tuple[str, str]:
    """The rest of a phrase's sentence, and the mark that ends it."""
    match = SENTENCE_END.search(text, end)
    if match is None:
        return text[end:], ""
    return text[end : match.start()], match.group(0)


def context_exempts(before: str, after: str) -> bool:
    """Whether the words before a phrase negate it or make it a condition."""
    words = [word.lower() for word in WORD.findall(before)]
    for distance, word in enumerate(reversed(words), start=1):
        if word in CONJUNCTIONS:
            return False
        if distance <= NEGATION_REACH and (word in NEGATORS or word.endswith("n't")):
            return True
        if word in CONDITIONALS or (word in TIME_CONDITIONS and IN_WRITING.search(after)):
            return True
    return False


def quote_opening(line: str, start: int, end: int) -> int | None:
    """Where an open quotation holding line[start:end] begins, or None."""
    opening = None
    for index in range(min(start, len(line))):
        char = line[index]
        if char not in QUOTES:
            continue
        before = line[index - 1] if index else " "
        after = line[index + 1] if index + 1 < len(line) else " "
        if opening is None:
            if (before.isspace() or before in "([{") and not after.isspace():
                opening = index
        elif not before.isspace() and not after.isalnum():
            opening = None
    if opening is not None and any(char in QUOTES for char in line[end:]):
        return opening
    return None


def account_is_shared(account: str) -> bool:
    return PLACEHOLDER_MARKS.sub("", account).casefold() in SHARED_ACCOUNTS


def user_path_lines(text: str) -> list[int]:
    """Lines holding a personal home-folder path; shared, CI, and placeholder accounts pass."""
    lines = set()
    for match in USER_PATH.finditer(text):
        account = next(
            value for value in match.group("win", "unc", "drive", "posix", "tilde") if value is not None
        )
        if not account_is_shared(account):
            lines.add(line_at(text, match.start()))
    return sorted(lines)


def email_lines(text: str) -> list[int]:
    """Lines holding a personal email address."""
    lines = set()
    for match in EMAIL.finditer(text):
        domain = match.group("domain")
        if SCALED_ASSET.match(domain) or match.group("tld").casefold() in FILE_SUFFIXES:
            continue
        line_start = text.rfind("\n", 0, match.start()) + 1
        if SSH_TARGET.search(text[line_start : match.start()]):
            continue
        if not email_allowed(match.group(0)):
            lines.add(line_at(text, match.start()))
    return sorted(lines)


def email_allowed(address: str) -> bool:
    folded = address.casefold()
    local, domain = folded.rsplit("@", 1)
    labels = domain.split(".")
    return (
        folded in SERVICE_ADDRESSES
        or domain in NOREPLY_DOMAINS
        # An SSH remote such as git@<host>:owner/repo.git names no person.
        or (local == "git" and domain in GIT_HOSTS)
        or labels[-1] in RESERVED_TLDS
        or any(label in INTERNAL_LABELS for label in labels)
        or any(domain == allowed or domain.endswith("." + allowed) for allowed in ALLOWED_EMAIL_DOMAINS)
    )


def grant_hits(text: str) -> list[tuple[int, int, str]]:
    """Self-granting phrases as (first line, last line, phrases), merging adjacent ones."""
    spans: list[list[object]] = []
    for match in GRANT_FORM.finditer(text):
        line_start = text.rfind("\n", 0, match.start()) + 1
        line_end = text.find("\n", match.start())
        line = text[line_start : line_end if line_end >= 0 else len(text)]
        if line.strip() == STANDING_FIELD:
            continue
        after, mark = sentence_after(text, match.end())
        if mark == "?" and not re.search(r"[;:]", after):
            continue
        if context_exempts(clause_before(text, match.start()), after):
            continue
        opening = quote_opening(line, match.start() - line_start, match.end() - line_start)
        if opening is not None and context_exempts(clause_before(text, line_start + opening), ""):
            continue
        phrase = " ".join(match.group(0).split())
        if spans and not text[spans[-1][1] : match.start()].strip():
            spans[-1][1] = max(spans[-1][1], match.end())
            spans[-1][2] = f"{spans[-1][2]} + {phrase}"
        else:
            spans.append([match.start(), match.end(), phrase])
    return [(line_at(text, start), line_at(text, end - 1), phrase) for start, end, phrase in spans]


def vault_lines(text: str) -> list[int]:
    """Lines naming a vault folder: any strong marker, or two kinds of weak ones."""
    strong = [match.start() for match in STRONG_VAULT.finditer(text)]
    weak = list(WEAK_VAULT.finditer(text))
    if not strong and len({match.group("kind").casefold() for match in weak}) < 2:
        return []
    return sorted({line_at(text, offset) for offset in strong + [match.start() for match in weak]})


def vault_paths(files: list[str]) -> set[str]:
    """Paths naming a vault folder, judged across the whole inventory."""
    strong = {path for path in files if STRONG_VAULT.search(normalize(path))}
    weak = {
        path: {match.group("kind").casefold() for match in WEAK_VAULT.finditer(normalize(path))}
        for path in files
    }
    weak = {path: kinds for path, kinds in weak.items() if kinds}
    if strong or len(set().union(*weak.values())) >= 2:
        return strong | set(weak)
    return strong


def lint_text(path: str, text: str, problems: list[Problem]) -> None:
    plain = normalize(text)
    words = plain.translate(PROSE_MARKS)
    for first, last, phrase in grant_hits(words):
        where = f"lines {first}-{last}" if last > first else f"line {first}"
        problems.append(
            Problem("LINT_GRANT_FORM", path, f"reads as a standing permission the text grants itself ({where}: '{phrase}').", first)
        )
    for line in sorted({line_at(words, match.start()) for match in NICKNAME.finditer(words)}):
        problems.append(Problem("LINT_AGENT_NICKNAME", path, "uses an author-specific delegated-agent nickname.", line))
    for line in vault_lines(plain):
        problems.append(Problem("LINT_VAULT_NAME", path, "names a private vault folder.", line))
    for line in user_path_lines(plain):
        problems.append(Problem("LINT_USER_PATH", path, "contains an absolute user path.", line))
    for line in email_lines(plain):
        problems.append(Problem("LINT_PERSONAL_EMAIL", path, "contains a personal email address.", line))


def lint_files(root: Path, files: list[str], problems: list[Problem]) -> None:
    """The neutrality lint: findings for text that ties the suite to one author."""
    vault = vault_paths(files)
    for path in files:
        plain = normalize(path)
        if fnmatch.fnmatchcase(PurePosixPath(plain).name.casefold(), LEDGER_FILE):
            problems.append(Problem("LINT_CONTINUITY_LEDGER", path, "is a continuity ledger; never commit one."))
        if user_path_lines(plain):
            problems.append(Problem("LINT_USER_PATH", path, "the path contains an absolute user path."))
        if path in vault:
            problems.append(Problem("LINT_VAULT_NAME", path, "the path names a private vault folder."))
        if NICKNAME.search(plain.translate(PROSE_MARKS)):
            problems.append(Problem("LINT_AGENT_NICKNAME", path, "the path uses an author-specific nickname."))
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
    check_identical(root, fileset, skills, problems)
    check_explicit_only(root, fileset, schema, problems)
    check_manifests(root, fileset, problems)
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
        scope = (
            "neutrality lint"
            if args.lint
            else f"{len(summary['skills'])} skills, plugin manifests, budgets, and neutrality lint"
        )
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
