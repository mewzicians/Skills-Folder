"""SKILL.md frontmatter schema and a standard-library YAML-subset parser.

This is the repository's canonical schema module. docs/SKILL_SCHEMA.md
describes the rules; this file implements them. It never imports PyYAML.

Two levels share one parser:

- ``portable``: the gate for this suite's own skills. Every rule is an error.
- ``spec``: for skills written by others. Violations of the Agent Skills
  specification are errors; portability concerns are warnings.

Each finding carries a stable code. ``RULES`` maps every code to its severity
at each level, so the two levels can never drift apart silently.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Union

LEVELS = ("portable", "spec")

NAME_MAX_LENGTH = 64
DESCRIPTION_MAX_LENGTH = 1024
COMPATIBILITY_MAX_LENGTH = 500
MAX_NESTING = 8

REQUIRED_KEYS = ("name", "description")
PORTABLE_OPTIONAL_KEYS = ("license", "metadata")
SPEC_ONLY_KEYS = ("compatibility", "allowed-tools")
SPEC_KEYS = REQUIRED_KEYS + PORTABLE_OPTIONAL_KEYS + SPEC_ONLY_KEYS
CLAUDE_ONLY_KEYS = (
    "agent",
    "argument-hint",
    "arguments",
    "background",
    "context",
    "disable-model-invocation",
    "disallowed-tools",
    "effort",
    "hooks",
    "model",
    "paths",
    "shell",
    "user-invocable",
    "when_to_use",
)

# code -> (severity at the portable level, severity at the spec level).
# None means the code is not reported at that level.
RULES: dict[str, tuple[str | None, str | None]] = {
    "PATH": ("error", "error"),
    "SKILL_MD_MISSING": ("error", "error"),
    "READ_ERROR": ("error", "error"),
    "ENCODING": ("error", "error"),
    "BOM": ("error", "warning"),
    "CRLF": ("error", "warning"),
    "CONTROL_CHARACTER": ("error", "error"),
    "UNICODE_LINE_BREAK": ("error", "warning"),
    "FRONTMATTER_MISSING": ("error", "error"),
    "FRONTMATTER_UNTERMINATED": ("error", "error"),
    "DELIMITER_SPACING": ("error", "warning"),
    "TAB": ("error", "warning"),
    "TAB_INDENT": ("error", "error"),
    "SYNTAX": ("error", "error"),
    "UNSUPPORTED": ("error", "error"),
    "DUPLICATE_KEY": ("error", "error"),
    "UNKNOWN_KEY": ("error", "warning"),
    "COMPATIBILITY_KEY": ("error", None),
    "ALLOWED_TOOLS_KEY": ("error", None),
    "CLAUDE_ONLY_KEY": ("error", "warning"),
    "BLOCK_SCALAR": ("error", None),
    "MULTILINE_SCALAR": ("error", None),
    "COMMENT_IN_VALUE": ("error", "warning"),
    "NON_STRING": ("error", "error"),
    "METADATA_TYPE": ("error", "error"),
    "METADATA_NESTED": ("error", "error"),
    "NAME_MISSING": ("error", "error"),
    "NAME_FORMAT": ("error", "error"),
    "NAME_LENGTH": ("error", "error"),
    "NAME_FOLDER": ("error", "error"),
    "DESCRIPTION_MISSING": ("error", "error"),
    "DESCRIPTION_EMPTY": ("error", "error"),
    "DESCRIPTION_LENGTH": ("error", "error"),
    "DESCRIPTION_ANGLE_BRACKETS": ("error", "warning"),
    "COMPATIBILITY_LENGTH": (None, "error"),
    "ALLOWED_TOOLS_FORMAT": (None, "warning"),
    "TODO_PLACEHOLDER": ("error", "warning"),
}

NAME_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_KEY_RE = re.compile(r"([A-Za-z0-9_][A-Za-z0-9_.-]*):(.*)")
_HEADER_RE = re.compile(r"([|>])([1-9][+-]?|[+-][1-9]?)?(?: +(?:#.*)?)?")
_LENIENT_IGNORED = frozenset(
    {"UNSUPPORTED", "BLOCK_SCALAR", "MULTILINE_SCALAR", "COMMENT_IN_VALUE"}
)
_FENCE_RE = re.compile(r"^[ \t]*(?:(?:[-+*]|\d+[.)])[ \t]+)?(`{3,}|~{3,})(.*)$")
_TODO_LINE_RE = re.compile(r"[ ]{0,3}\[TODO:[^\n]*\][ \t]*")

# Plain scalars that YAML 1.1 (PyYAML) or the YAML 1.2 core schema loads as
# something other than a string. Matching any of them makes a value
# non-portable as a string, so the portable level demands quotes.
_IMPLICIT_TYPES = (
    ("null", re.compile(r"(?:~|null|Null|NULL)?")),
    (
        "boolean",
        re.compile(
            r"(?:y|Y|yes|Yes|YES|n|N|no|No|NO|true|True|TRUE|false|False|FALSE"
            r"|on|On|ON|off|Off|OFF)"
        ),
    ),
    (
        "integer",
        re.compile(
            r"[-+]?0b[0-1_]+|[-+]?0[0-7_]+|[-+]?(?:0|[1-9][0-9_]*)"
            r"|[-+]?0x[0-9a-fA-F_]+|[-+]?[1-9][0-9_]*(?::[0-5]?[0-9])+"
            r"|[-+]?[0-9]+|0o[0-7]+"
        ),
    ),
    (
        "float",
        re.compile(
            r"[-+]?[0-9][0-9_]*\.[0-9_]*(?:[eE][-+][0-9]+)?"
            r"|\.[0-9][0-9_]*(?:[eE][-+][0-9]+)?"
            r"|[-+]?[0-9][0-9_]*(?::[0-5]?[0-9])+\.[0-9_]*"
            r"|[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN)"
            r"|[-+]?(?:\.[0-9]+|[0-9]+(?:\.[0-9]*)?)(?:[eE][-+]?[0-9]+)?"
        ),
    ),
    (
        "timestamp",
        re.compile(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}"
            r"|[0-9]{4}-[0-9]{1,2}-[0-9]{1,2}(?:[Tt]|[ \t]+)[0-9]{1,2}:[0-9]{2}"
            r":[0-9]{2}(?:\.[0-9]*)?(?:[ \t]*(?:Z|[-+][0-9]{1,2}(?::[0-9]{2})?))?"
        ),
    ),
    ("merge or value indicator", re.compile(r"<<|=")),
)

_SIMPLE_ESCAPES = {
    "0": "\0",
    "a": "\a",
    "b": "\b",
    "t": "\t",
    "\t": "\t",
    "n": "\n",
    "v": "\v",
    "f": "\f",
    "r": "\r",
    "e": "\x1b",
    " ": " ",
    '"': '"',
    "/": "/",
    "\\": "\\",
    "N": "\x85",
    "_": "\xa0",
    "L": "\u2028",
    "P": "\u2029",
}
_HEX_ESCAPES = {"x": 2, "u": 4, "U": 8}


def resolve_plain(text: str) -> str:
    """Return the YAML type a plain scalar loads as ("string" if none)."""
    for kind, pattern in _IMPLICIT_TYPES:
        if pattern.fullmatch(text):
            return kind
    return "string"


@dataclass
class Scalar:
    value: str
    style: str
    line: int
    kind: str = "string"


@dataclass
class Mapping:
    entries: dict[str, tuple[int, "Node"]]
    line: int


@dataclass
class Sequence:
    items: list["Node"]
    line: int


@dataclass
class Opaque:
    """A value the parser deliberately leaves unparsed."""

    kind: str
    line: int


Node = Union[Scalar, Mapping, Sequence, Opaque]


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    message: str
    line: int | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "severity": self.severity,
            "code": self.code,
            "line": self.line,
            "message": self.message,
        }


@dataclass
class Report:
    path: str
    level: str
    findings: list[Finding] = field(default_factory=list)
    frontmatter: dict[str, object] = field(default_factory=dict)

    @property
    def errors(self) -> int:
        return sum(item.severity == "error" for item in self.findings)

    @property
    def warnings(self) -> int:
        return sum(item.severity == "warning" for item in self.findings)

    @property
    def valid(self) -> bool:
        return self.errors == 0

    @property
    def codes(self) -> list[str]:
        return sorted({item.code for item in self.findings})

    def as_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "level": self.level,
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "findings": [item.as_dict() for item in self.findings],
            "frontmatter": self.frontmatter,
        }


def _leading_spaces(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _is_blank(line: str) -> bool:
    return not line.strip(" \t")


def _is_comment(line: str) -> bool:
    return line.lstrip(" \t").startswith("#")


def _is_dash(content: str) -> bool:
    return content == "-" or content.startswith(("- ", "-\t"))


def _scan_quoted(text: str) -> tuple[str | None, int, str | None]:
    """Scan a one-line quoted scalar. Returns (value, end, problem)."""
    quote = text[0]
    out: list[str] = []
    index = 1
    while index < len(text):
        char = text[index]
        if quote == "'":
            if char == "'":
                if text[index + 1 : index + 2] == "'":
                    out.append("'")
                    index += 2
                    continue
                return "".join(out), index + 1, None
            out.append(char)
            index += 1
            continue
        if char == '"':
            return "".join(out), index + 1, None
        if char != "\\":
            out.append(char)
            index += 1
            continue
        if index + 1 >= len(text):
            return None, index, "unterminated"
        escape = text[index + 1]
        if escape in _SIMPLE_ESCAPES:
            out.append(_SIMPLE_ESCAPES[escape])
            index += 2
            continue
        width = _HEX_ESCAPES.get(escape)
        digits = text[index + 2 : index + 2 + width] if width else ""
        if not width or len(digits) != width or not all(
            digit in "0123456789abcdefABCDEF" for digit in digits
        ):
            return None, index, f"invalid escape sequence '\\{escape}{digits}'"
        code_point = int(digits, 16)
        if code_point > 0x10FFFF or 0xD800 <= code_point <= 0xDFFF:
            return None, index, f"escape '\\{escape}{digits}' is not a Unicode scalar"
        out.append(chr(code_point))
        index += 2 + width
    return None, len(text), "unterminated"


def _flow_end(text: str) -> int | None:
    """Return the index after a one-line flow collection, or None."""
    depth = 0
    quote = ""
    index = 0
    while index < len(text):
        char = text[index]
        if quote:
            if quote == '"' and char == "\\":
                index += 2
                continue
            if char == quote:
                if quote == "'" and text[index + 1 : index + 2] == "'":
                    index += 2
                    continue
                quote = ""
        elif char in "\"'":
            quote = char
        elif char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return None


class _Parser:
    """Line-oriented parser for the frontmatter YAML subset."""

    def __init__(self, lines: list[str], first_line: int) -> None:
        self.lines = lines
        self.first_line = first_line
        self.raw: list[tuple[str, int | None, str]] = []

    def lineno(self, index: int) -> int:
        return self.first_line + index

    def add(self, code: str, index: int | None, message: str) -> None:
        self.raw.append(
            (code, None if index is None else self.lineno(index), message)
        )

    def has_break(self, index: int) -> bool:
        # The frontmatter text ends before the newline that precedes the
        # closing delimiter, exactly as PyYAML sees it in Codex's validator.
        return index < len(self.lines) - 1

    def next_content(self, index: int) -> int | None:
        while index < len(self.lines):
            line = self.lines[index]
            if not _is_blank(line) and not _is_comment(line):
                return index
            index += 1
        return None

    def skip_deeper(self, index: int, indent: int, compact: bool = False) -> int:
        """Skip lines indented deeper than ``indent``.

        With ``compact``, sequence entries at exactly ``indent`` are skipped
        too, because YAML allows '- ' entries at their key's indentation.
        """
        while index < len(self.lines):
            line = self.lines[index]
            if not _is_blank(line) and not _is_comment(line):
                spaces = _leading_spaces(line)
                deeper = spaces > indent
                compact_entry = compact and spaces == indent and _is_dash(line[spaces:])
                if not deeper and not compact_entry:
                    break
            index += 1
        return index

    def parse(self) -> dict[str, tuple[int, Node]]:
        entries, _ = self.mapping(0, 0, -1, 0)
        return entries

    def diagnose_key(self, index: int, content: str) -> None:
        if content.startswith(("\"", "'")):
            self.add("UNSUPPORTED", index, "Quoted keys are outside the supported YAML subset.")
        elif _is_dash(content):
            self.add(
                "SYNTAX",
                index,
                "Expected 'key: value'; found a sequence entry. Frontmatter must be a mapping.",
            )
        elif content == "?" or content.startswith(("? ", "?\t")):
            self.add("SYNTAX", index, "Complex mapping keys ('? ') are not allowed here.")
        elif content == "..." or content.startswith(("... ", "...\t")):
            self.add("UNSUPPORTED", index, "YAML document markers are not allowed inside frontmatter.")
        elif re.match(r"[^:#]*[^\s:#][ \t]+:(?:[ \t]|$)", content):
            self.add("UNSUPPORTED", index, "Put no space between a key and its ':'.")
        elif re.search(r":(?:[ \t]|$)", content):
            self.add(
                "UNSUPPORTED",
                index,
                "Keys may use only letters, digits, '_', '.', and '-' and must not start with '.' or '-'.",
            )
        elif re.match(r"[A-Za-z0-9_][A-Za-z0-9_.-]*:\S", content):
            self.add("SYNTAX", index, "Put a space after the ':' that ends a key.")
        else:
            self.add("SYNTAX", index, "Expected 'key: value'.")

    @staticmethod
    def key_match(content: str) -> re.Match[str] | None:
        match = _KEY_RE.fullmatch(content)
        if match and (not match.group(2) or match.group(2)[0] in " \t"):
            return match
        return None

    def mapping(
        self, index: int, indent: int, parent: int, depth: int
    ) -> tuple[dict[str, tuple[int, Node]], int]:
        entries: dict[str, tuple[int, Node]] = {}
        while index < len(self.lines):
            line = self.lines[index]
            if _is_blank(line) or _is_comment(line):
                index += 1
                continue
            spaces = _leading_spaces(line)
            if spaces < indent:
                if spaces > parent:
                    self.add("SYNTAX", index, "Indentation does not match any enclosing mapping.")
                    index += 1
                    continue
                break
            if line[spaces] == "\t":
                self.add("TAB_INDENT", index, "Indent with spaces; YAML forbids tabs in indentation.")
                index = self.skip_deeper(index + 1, spaces)
                continue
            if spaces > indent:
                where = "a top-level key" if indent == 0 else "a nested key"
                self.add(
                    "SYNTAX",
                    index,
                    f"Unexpected indentation; expected {where} at column {indent + 1}.",
                )
                index += 1
                continue
            content = line[spaces:]
            match = self.key_match(content)
            if not match:
                self.diagnose_key(index, content)
                index += 1
                continue
            key, rest = match.group(1), match.group(2)
            key_line = self.lineno(index)
            if key in entries:
                self.add("DUPLICATE_KEY", index, f"Duplicate key '{key}'.")
            lenient = depth == 0 and key not in SPEC_KEYS
            node, index = self.value(index, rest, indent, lenient, depth)
            entries[key] = (key_line, node)
        return entries, index

    def value(
        self, index: int, rest: str, indent: int, lenient: bool, depth: int
    ) -> tuple[Node, int]:
        text = rest.lstrip(" \t")
        if "\t" in rest[: len(rest) - len(text)]:
            self.add("TAB", index, "A tab separates a key from its value; use a space.")
        mark = len(self.raw)
        if not text or text.startswith("#"):
            node, end = self.nested(index, indent, depth)
        else:
            node, end = self.inline(index, text, indent, depth)
        if lenient:
            # Keys outside the spec are checked for YAML syntax only; the
            # subset's limits and portability rules do not apply to them.
            self.raw[mark:] = [
                item for item in self.raw[mark:] if item[0] not in _LENIENT_IGNORED
            ]
        return node, end

    def nested(self, index: int, indent: int, depth: int) -> tuple[Node, int]:
        start = self.next_content(index + 1)
        empty = Scalar("", "plain", self.lineno(index), "null")
        if start is None:
            return empty, index + 1
        line = self.lines[start]
        spaces = _leading_spaces(line)
        content = line[spaces:]
        if spaces < indent or (spaces == indent and not _is_dash(content)):
            return empty, index + 1
        if content.startswith("\t"):
            self.add("TAB_INDENT", start, "Indent with spaces; YAML forbids tabs in indentation.")
            return Opaque("invalid", self.lineno(start)), self.skip_deeper(start + 1, indent)
        if depth >= MAX_NESTING:
            self.add("UNSUPPORTED", start, "Nesting is deeper than the supported limit.")
            return Opaque("nested", self.lineno(start)), self.skip_deeper(start, indent)
        if _is_dash(content):
            return self.sequence(start, spaces, indent, depth + 1)
        if self.key_match(content):
            entries, end = self.mapping(start, spaces, indent, depth + 1)
            return Mapping(entries, self.lineno(start)), end
        self.add(
            "MULTILINE_SCALAR",
            index,
            "The value starts on the line after its key; keep it on the key's line.",
        )
        return self.inline(start, content, indent, depth)

    def inline(self, index: int, text: str, indent: int, depth: int) -> tuple[Node, int]:
        first = text[0]
        line = self.lineno(index)
        if first in "|>":
            self.add(
                "BLOCK_SCALAR",
                index,
                "Block scalars ('|' or '>') are not portable here; write the value on one line.",
            )
            return self.block_scalar(index, text, indent)
        if first in "\"'":
            value, end, problem = _scan_quoted(text)
            if problem == "unterminated":
                self.add(
                    "UNSUPPORTED",
                    index,
                    "Quoted values must close on the same line; multi-line quoted scalars "
                    "are outside the supported subset.",
                )
                return Opaque("unterminated quote", line), self.skip_deeper(index + 1, indent)
            if problem:
                self.add("SYNTAX", index, f"Invalid double-quoted value: {problem}.")
                return Opaque("invalid", line), self.after_inline(index, indent)
            tail = text[end:]
            remainder = tail.lstrip(" \t")
            if remainder and not (remainder.startswith("#") and len(tail) > len(remainder)):
                self.add("SYNTAX", index, "Unexpected text after the closing quote.")
            style = "double" if first == '"' else "single"
            return Scalar(value or "", style, line), self.after_inline(index, indent)
        if first in "[{":
            end = _flow_end(text)
            kind = "flow sequence" if first == "[" else "flow mapping"
            if end is None:
                self.add("UNSUPPORTED", index, f"A {kind} must close on the same line.")
                return Opaque(kind, line), self.skip_deeper(index + 1, indent)
            tail = text[end:]
            remainder = tail.lstrip(" \t")
            if remainder and not (remainder.startswith("#") and len(tail) > len(remainder)):
                self.add("SYNTAX", index, f"Unexpected text after the {kind}.")
            if first == "{":
                self.add(
                    "UNSUPPORTED",
                    index,
                    "Flow mappings ('{...}') are outside the supported subset.",
                )
            return Opaque(kind, line), self.after_inline(index, indent)
        if first in "&*!":
            self.add(
                "UNSUPPORTED",
                index,
                "Anchors ('&'), aliases ('*'), and tags ('!') are outside the supported subset.",
            )
            return Opaque("unsupported", line), self.skip_deeper(index + 1, indent)
        if first in "%@`,]}":
            self.add("SYNTAX", index, f"A plain value cannot start with '{first}'; quote the value.")
            return Opaque("invalid", line), self.skip_deeper(index + 1, indent)
        if first in "-?:" and (len(text) == 1 or text[1] in " \t"):
            self.add("SYNTAX", index, f"A value cannot start with '{first} '; quote the value.")
            return Opaque("invalid", line), self.skip_deeper(index + 1, indent)
        return self.plain(index, text, indent)

    def after_inline(self, index: int, indent: int) -> int:
        """Reject deeper lines that follow a value that is already complete."""
        end = self.skip_deeper(index + 1, indent)
        extra = self.next_content(index + 1)
        if extra is not None and extra < end:
            self.add("SYNTAX", extra, "Unexpected indented line after a complete value.")
        return end

    def plain_segment(self, index: int, text: str) -> tuple[str, bool]:
        for position, char in enumerate(text):
            following = text[position + 1 : position + 2]
            if char == ":" and following in ("", " ", "\t"):
                self.add(
                    "SYNTAX",
                    index,
                    "An unquoted ': ' (or a trailing ':') makes YAML read a nested mapping; "
                    "quote the value.",
                )
                return text[:position].rstrip(" \t"), True
            if char == "#" and position and text[position - 1] in " \t":
                self.add(
                    "COMMENT_IN_VALUE",
                    index,
                    "' #' starts a YAML comment, so the rest of the line is dropped from the "
                    "value; quote the value.",
                )
                return text[:position].rstrip(" \t"), True
        return text.rstrip(" \t"), False

    def plain(self, index: int, text: str, indent: int) -> tuple[Node, int]:
        value, stopped = self.plain_segment(index, text)
        end = index + 1
        continued = False
        if not stopped:
            blank_run = 0
            cursor = index + 1
            while cursor < len(self.lines):
                line = self.lines[cursor]
                if _is_blank(line):
                    blank_run += 1
                    cursor += 1
                    continue
                spaces = _leading_spaces(line)
                if spaces <= indent or line[spaces] == "\t":
                    break
                content = line[spaces:]
                if content.startswith("#"):
                    break
                segment, stopped = self.plain_segment(cursor, content)
                value += "\n" * blank_run if blank_run else " "
                value += segment
                blank_run = 0
                continued = True
                cursor += 1
                end = cursor
                if stopped:
                    break
        if continued:
            self.add(
                "MULTILINE_SCALAR",
                index,
                "The value continues on the next line; keep it on one line.",
            )
        return Scalar(value, "plain", self.lineno(index), resolve_plain(value)), end

    def block_breaks(self, index: int, indent: int) -> tuple[list[str], int, bool]:
        breaks: list[str] = []
        while index < len(self.lines):
            line = self.lines[index]
            consumed = min(_leading_spaces(line), indent)
            if consumed == len(line):
                if not self.has_break(index):
                    return breaks, index + 1, False
                breaks.append("\n")
                index += 1
                continue
            return breaks, index, consumed == indent
        return breaks, index, False

    def block_scalar(self, index: int, header: str, indent: int) -> tuple[Node, int]:
        """Parse a literal or folded block scalar as PyYAML's scanner does."""
        line = self.lineno(index)
        match = _HEADER_RE.fullmatch(header)
        if not match:
            self.add("SYNTAX", index, "Invalid block scalar header.")
            return Opaque("invalid", line), self.skip_deeper(index + 1, indent)
        folded = match.group(1) == ">"
        chomping: bool | None = None
        increment: int | None = None
        for char in match.group(2) or "":
            if char == "+":
                chomping = True
            elif char == "-":
                chomping = False
            else:
                increment = int(char)
        min_indent = indent + 1
        cursor = index + 1
        breaks: list[str] = []
        if increment is None:
            max_indent = 0
            while cursor < len(self.lines):
                spaces = _leading_spaces(self.lines[cursor])
                max_indent = max(max_indent, spaces)
                if spaces < len(self.lines[cursor]):
                    break
                if self.has_break(cursor):
                    breaks.append("\n")
                cursor += 1
            block_indent = max(min_indent, max_indent)
            at_content = (
                cursor < len(self.lines)
                and _leading_spaces(self.lines[cursor]) == block_indent
                and block_indent < len(self.lines[cursor])
            )
        else:
            block_indent = min_indent + increment - 1
            breaks, cursor, at_content = self.block_breaks(cursor, block_indent)
        chunks: list[str] = []
        line_break = ""
        while at_content:
            chunks.extend(breaks)
            text = self.lines[cursor][block_indent:]
            leading_non_space = text[:1] not in (" ", "\t")
            chunks.append(text)
            line_break = "\n" if self.has_break(cursor) else ""
            cursor += 1
            if not line_break:
                breaks = []
                break
            breaks, cursor, at_content = self.block_breaks(cursor, block_indent)
            if not at_content:
                break
            following = self.lines[cursor][block_indent:]
            if folded and leading_non_space and following[:1] not in (" ", "\t"):
                if not breaks:
                    chunks.append(" ")
            else:
                chunks.append(line_break)
        if chomping is not False:
            chunks.append(line_break)
        if chomping is True:
            chunks.extend(breaks)
        style = "folded" if folded else "literal"
        return Scalar("".join(chunks), style, line), cursor

    def sequence(self, index: int, indent: int, parent: int, depth: int) -> tuple[Node, int]:
        items: list[Node] = []
        start = self.lineno(index)
        compact = indent == parent
        while index < len(self.lines):
            line = self.lines[index]
            if _is_blank(line) or _is_comment(line):
                index += 1
                continue
            spaces = _leading_spaces(line)
            if spaces < indent:
                if spaces > parent:
                    self.add("SYNTAX", index, "Indentation does not match any enclosing collection.")
                    index += 1
                    continue
                break
            content = line[spaces:]
            if spaces > indent or not _is_dash(content):
                if compact and spaces == indent:
                    break
                self.add("SYNTAX", index, "Expected a sequence entry ('- value').")
                index += 1
                continue
            rest = content[1:]
            text = rest.lstrip(" \t")
            if "\t" in rest[: len(rest) - len(text)]:
                self.add("TAB", index, "A tab follows a sequence dash; use a space.")
            if not text or text.startswith("#"):
                deeper = self.next_content(index + 1)
                if deeper is not None and _leading_spaces(self.lines[deeper]) > indent:
                    self.add(
                        "UNSUPPORTED",
                        index,
                        "Nested collections inside a sequence are outside the supported subset.",
                    )
                    items.append(Opaque("nested", self.lineno(index)))
                    index = self.skip_deeper(index + 1, indent)
                    continue
                items.append(Scalar("", "plain", self.lineno(index), "null"))
                index += 1
                continue
            if self.key_match(text):
                self.add(
                    "UNSUPPORTED",
                    index,
                    "Mappings inside a sequence are outside the supported subset.",
                )
                items.append(Opaque("nested", self.lineno(index)))
                index = self.skip_deeper(index + 1, indent)
                continue
            node, index = self.inline(index, text, indent, depth)
            items.append(node)
        return Sequence(items, start), index


def _check_characters(lines: list[str], first_line: int, add) -> None:
    found: dict[str, list[int]] = {}
    for offset, line in enumerate(lines):
        for char in line:
            point = ord(char)
            if char == "\t":
                code = "TAB"
            elif char in "\x85\u2028\u2029":
                code = "UNICODE_LINE_BREAK"
            elif char == "\ufeff":
                code = "BOM"
            elif point < 0x20 or point == 0x7F or 0x80 <= point <= 0x9F or char in "\ufffe\uffff":
                code = "CONTROL_CHARACTER"
            else:
                continue
            lines_for_code = found.setdefault(code, [])
            if not lines_for_code or lines_for_code[-1] != first_line + offset:
                lines_for_code.append(first_line + offset)
    messages = {
        "TAB": (
            "Tab characters are not portable in frontmatter; PyYAML rejects them "
            "outside quoted and block values. Use spaces."
        ),
        "UNICODE_LINE_BREAK": (
            "U+0085, U+2028, or U+2029 inside frontmatter; YAML 1.1 parsers read "
            "them as line breaks."
        ),
        "BOM": "A U+FEFF byte-order mark appears inside the frontmatter.",
        "CONTROL_CHARACTER": "Control characters are not allowed in YAML.",
    }
    for code, numbers in found.items():
        detail = "" if len(numbers) == 1 else f" ({len(numbers)} lines)"
        add(code, numbers[0], messages[code] + detail)


def _string(node: Node | None) -> str | None:
    if isinstance(node, Scalar) and node.kind == "string":
        return node.value
    return None


# Opaque kinds whose problem the parser has already reported.
_REPORTED_KINDS = frozenset({"invalid", "unsupported", "unterminated quote", "flow mapping"})
_COLLECTION_KINDS = frozenset({"flow sequence", "flow mapping", "nested"})


def _already_reported(node: Node) -> bool:
    return isinstance(node, Opaque) and node.kind in _REPORTED_KINDS


def _describe(node: Node) -> str:
    if isinstance(node, Scalar):
        if node.kind == "null":
            return "an empty (null) value"
        return f"the plain value {node.value!r} as a {node.kind}"
    if isinstance(node, Mapping):
        return "a mapping"
    if isinstance(node, Sequence):
        return "a sequence"
    if node.kind in ("flow sequence", "flow mapping"):
        return f"a {node.kind}"
    if node.kind == "nested":
        return "a nested collection"
    return "an unparsed value"


def _check_fields(values: dict[str, tuple[int, Node]], folder: str | None, add) -> None:
    for key, (line, node) in values.items():
        if key in REQUIRED_KEYS or key in PORTABLE_OPTIONAL_KEYS:
            continue
        if key == "compatibility":
            add(
                "COMPATIBILITY_KEY",
                line,
                "The spec's 'compatibility' key is not portable: Codex's validator rejects it.",
            )
        elif key == "allowed-tools":
            add(
                "ALLOWED_TOOLS_KEY",
                line,
                "'allowed-tools' grants tool permissions; it is not part of the portable schema.",
            )
        elif key in CLAUDE_ONLY_KEYS:
            add(
                "CLAUDE_ONLY_KEY",
                line,
                f"'{key}' is a Claude Code-only key; other hosts and Codex's validator reject it.",
            )
        else:
            add("UNKNOWN_KEY", line, f"Unknown frontmatter key '{key}'.")

    def check_string(key: str, line: int, node: Node, code: str = "NON_STRING") -> str | None:
        text = _string(node)
        if text is None and not _already_reported(node):
            add(code, line, f"'{key}' must be a string, but YAML reads {_describe(node)}. Quote it.")
        return text

    if "name" not in values:
        add("NAME_MISSING", None, "Frontmatter has no 'name'.")
    else:
        line, node = values["name"]
        name = check_string("name", line, node)
        if name is not None:
            if len(name) > NAME_MAX_LENGTH:
                add(
                    "NAME_LENGTH",
                    line,
                    f"Name has {len(name)} characters; the maximum is {NAME_MAX_LENGTH}.",
                )
            if not NAME_PATTERN.fullmatch(name):
                add(
                    "NAME_FORMAT",
                    line,
                    f"Name {name!r} must use lowercase letters, digits, and single hyphens, "
                    "and must not start or end with a hyphen.",
                )
            if folder is not None and name != folder:
                add(
                    "NAME_FOLDER",
                    line,
                    f"Name {name!r} does not match its folder {folder!r}.",
                )

    if "description" not in values:
        add("DESCRIPTION_MISSING", None, "Frontmatter has no 'description'.")
    else:
        line, node = values["description"]
        description = check_string("description", line, node)
        if description is not None:
            stripped = description.strip()
            if not stripped:
                add("DESCRIPTION_EMPTY", line, "Description is empty.")
            elif len(stripped) > DESCRIPTION_MAX_LENGTH:
                add(
                    "DESCRIPTION_LENGTH",
                    line,
                    f"Description has {len(stripped)} characters; "
                    f"the maximum is {DESCRIPTION_MAX_LENGTH}.",
                )
            if "\n" in stripped or "\r" in stripped:
                add(
                    "MULTILINE_SCALAR",
                    line,
                    "The description contains a line break; keep it on one line.",
                )
            if "<" in stripped or ">" in stripped:
                add(
                    "DESCRIPTION_ANGLE_BRACKETS",
                    line,
                    "Description contains '<' or '>', which Codex's validator rejects.",
                )
            if stripped.startswith("[TODO:"):
                add(
                    "TODO_PLACEHOLDER",
                    line,
                    "Description is an unfinished [TODO: ...] placeholder.",
                )

    if "license" in values:
        line, node = values["license"]
        check_string("license", line, node)

    if "compatibility" in values:
        line, node = values["compatibility"]
        text = check_string("compatibility", line, node, code="COMPATIBILITY_LENGTH")
        length = len(text.strip()) if text is not None else 0
        if text is not None and not 1 <= length <= COMPATIBILITY_MAX_LENGTH:
            add(
                "COMPATIBILITY_LENGTH",
                line,
                f"'compatibility' must have 1-{COMPATIBILITY_MAX_LENGTH} characters; "
                f"it has {length}.",
            )

    if "allowed-tools" in values:
        line, node = values["allowed-tools"]
        if _string(node) is None:
            add(
                "ALLOWED_TOOLS_FORMAT",
                line,
                "The spec defines 'allowed-tools' as a space-separated string; "
                f"YAML reads {_describe(node)}.",
            )

    if "metadata" in values:
        line, node = values["metadata"]
        if isinstance(node, Mapping):
            for key, (entry_line, entry) in node.entries.items():
                if resolve_plain(key) != "string":
                    add("NON_STRING", entry_line, f"Metadata key {key!r} is not a string in YAML.")
                if isinstance(entry, (Mapping, Sequence)) or (
                    isinstance(entry, Opaque) and entry.kind in _COLLECTION_KINDS
                ):
                    add(
                        "METADATA_NESTED",
                        entry_line,
                        f"metadata.{key} must be a string, not a collection.",
                    )
                else:
                    check_string(f"metadata.{key}", entry_line, entry)
        elif not _already_reported(node):
            add(
                "METADATA_TYPE",
                line,
                "'metadata' must be a mapping of string keys to string values, "
                f"but YAML reads {_describe(node)}.",
            )


def _body_todo(lines: list[str], first_line: int) -> int | None:
    """Mirror Codex's validator: a [TODO: ...] line outside code fences."""
    fence_marker: str | None = None
    fence_length = 0
    for offset, line in enumerate(lines):
        fence = _FENCE_RE.match(line)
        if fence:
            marker = fence.group(1)
            if fence_marker is None:
                fence_marker = marker[0]
                fence_length = len(marker)
            elif (
                marker[0] == fence_marker
                and len(marker) >= fence_length
                and not fence.group(2).strip()
            ):
                fence_marker = None
                fence_length = 0
            continue
        if fence_marker is None and _TODO_LINE_RE.fullmatch(line):
            return first_line + offset
    return None


def _plain_python(node: Node) -> object:
    if isinstance(node, Scalar):
        return node.value
    if isinstance(node, Mapping):
        return {key: _plain_python(value) for key, (_, value) in node.entries.items()}
    if isinstance(node, Sequence):
        return [_plain_python(item) for item in node.items]
    return None


def validate_text(
    data: bytes,
    folder: str | None = None,
    level: str = "portable",
    path: str = "SKILL.md",
) -> Report:
    """Validate SKILL.md bytes. ``folder`` is the skill folder's name, if known."""
    _check_level(level)
    raw: list[tuple[str, int | None, str]] = []

    def add(code: str, line: int | None, message: str) -> None:
        raw.append((code, line, message))

    report = Report(path=path, level=level)
    if data.startswith(b"\xef\xbb\xbf"):
        add(
            "BOM",
            1,
            "SKILL.md starts with a UTF-8 byte-order mark; Codex then finds no "
            "frontmatter. Save it as UTF-8 without BOM.",
        )
        data = data[3:]
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        line = data[: error.start].count(b"\n") + 1
        add("ENCODING", line, f"SKILL.md is not valid UTF-8 (byte {error.start}).")
        return _finish(report, raw)
    if "\r" in text:
        line = text[: text.index("\r")].count("\n") + 1
        add("CRLF", line, "SKILL.md has CR or CRLF line endings; use LF.")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    first = lines[0]
    if first.rstrip(" \t") != "---":
        add("FRONTMATTER_MISSING", 1, "SKILL.md must start with a '---' frontmatter line.")
        return _finish(report, raw)
    if first != "---":
        add("DELIMITER_SPACING", 1, "Remove trailing whitespace from the '---' delimiter.")
    closing = next(
        (index for index in range(1, len(lines)) if lines[index].rstrip(" \t") == "---"),
        None,
    )
    if closing is None:
        add("FRONTMATTER_UNTERMINATED", 1, "Frontmatter has no closing '---' line.")
        return _finish(report, raw)
    if lines[closing] != "---":
        add("DELIMITER_SPACING", closing + 1, "Remove trailing whitespace from the '---' delimiter.")
    frontmatter_lines = lines[1:closing]
    _check_characters(frontmatter_lines, 2, add)
    parser = _Parser(frontmatter_lines, 2)
    values = parser.parse()
    raw.extend(parser.raw)
    _check_fields(values, folder, add)
    todo_line = _body_todo(lines[closing + 1 :], closing + 2)
    if todo_line is not None:
        add("TODO_PLACEHOLDER", todo_line, "The body contains an unfinished [TODO: ...] line.")
    report.frontmatter = {key: _plain_python(node) for key, (_, node) in values.items()}
    return _finish(report, raw)


def _check_level(level: str) -> None:
    if level not in LEVELS:
        raise ValueError(f"Unknown level {level!r}; expected one of {LEVELS}.")


def _finish(report: Report, raw: list[tuple[str, int | None, str]]) -> Report:
    level_index = LEVELS.index(report.level)
    findings = []
    for code, line, message in raw:
        severity = RULES[code][level_index]
        if severity is not None:
            findings.append(Finding(severity, code, message, line))
    findings.sort(key=lambda item: (item.line or 0, item.code))
    report.findings = findings
    return report


def validate_skill_dir(path: str | os.PathLike[str], level: str = "portable") -> Report:
    """Validate the SKILL.md inside a skill folder."""
    _check_level(level)
    skill_dir = Path(path)
    display = str(path)
    if not skill_dir.is_dir():
        return _finish(
            Report(path=display, level=level),
            [("PATH", None, "Skill path is not a directory.")],
        )
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return _finish(
            Report(path=display, level=level),
            [("SKILL_MD_MISSING", None, "SKILL.md not found.")],
        )
    try:
        data = skill_md.read_bytes()
    except OSError as error:
        return _finish(
            Report(path=display, level=level),
            [("READ_ERROR", None, f"Cannot read SKILL.md: {error}")],
        )
    folder = Path(os.path.abspath(skill_dir)).name
    return validate_text(data, folder=folder, level=level, path=display)
