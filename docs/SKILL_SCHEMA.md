# SKILL.md Schema

Every `SKILL.md` in this repository starts with YAML frontmatter that must load
the same way in Codex, Claude Code, the Agent Skills specification, and Codex's
own skill-creator validator. This document defines that frontmatter.
[`tools/lib/skill_frontmatter.py`](../tools/lib/skill_frontmatter.py) implements
it with the Python standard library alone: no PyYAML at run time.

```text
python -B tools/validate_skill.py
python -B tools/validate_skill.py --level portable "skills/*"
python -B tools/validate_skill.py --level spec --json path/to/someone-elses-skill
```

With no path, the validator checks every folder in this repository's
`skills/` at the portable level. It expands glob patterns itself, so these
commands work unchanged in PowerShell, cmd, and POSIX shells; quote a pattern
so that every shell passes it through as written.

Exit codes: `0` every skill is valid, `1` at least one is invalid, `2` usage
error, `3` internal error. Python 3.11 or later.

## Two Levels

| Level | Use it for | Severity |
| --- | --- | --- |
| `portable` | This suite's own skills. CI runs it on every skill. | Every rule is an error. |
| `spec` | Skills written by others. | Agent Skills specification violations and invalid YAML are errors; portability problems are warnings. |

The portable level is the intersection of what all four consumers accept, so a
skill that passes it also loads in each of them, with one exception that no
file can avoid: Codex's `quick_validate.py` reads `SKILL.md` in the locale's
default encoding. Where that is not UTF-8, such as cp1252 on many Windows
systems, it misreads non-ASCII text and can crash on it. `Á`, for example, is
UTF-8 `C3 81`, and cp1252 has no character for `81`, so the validator raises
`UnicodeDecodeError`. Run Codex's validator in UTF-8 mode:

```text
python -X utf8 path/to/quick_validate.py path/to/skill
```

## File Rules

- UTF-8, decoded strictly, with no byte-order mark. Codex keeps a BOM and then
  finds no frontmatter, so the skill silently fails to load.
- LF line endings.
- The first line is exactly `---`. The frontmatter ends at the next line that is
  exactly `---`. Neither delimiter may carry trailing whitespace.
- No tab anywhere in the frontmatter. PyYAML, which Codex's validator uses,
  rejects tabs that YAML 1.2 allows.
- No control characters. No U+0085, U+2028, or U+2029, which YAML 1.1 parsers
  read as line breaks.

## Keys

| Key | Portable | Spec | Rule |
| --- | --- | --- | --- |
| `name` | required | required | 1-64 characters: lowercase letters, digits, and single hyphens, with no hyphen at either end. Must equal the skill's folder name. |
| `description` | required | required | A string of 1-1,024 characters after trimming, on one line, with no `<` or `>`, and not a `[TODO: ...]` placeholder. |
| `license` | optional | optional | A string. |
| `metadata` | optional | optional | One level of string keys and string values. `metadata.version` is reserved for the suite version. |
| `compatibility` | rejected | optional | Codex's validator rejects it. At the spec level it must be a string of 1-500 characters. |
| `allowed-tools` | rejected | optional | A tool grant, and not portable. The spec defines it as a space-separated string, so a YAML list is a warning. |
| Claude Code-only keys | rejected | warning | `when_to_use`, `argument-hint`, `arguments`, `disable-model-invocation`, `user-invocable`, `disallowed-tools`, `model`, `effort`, `context`, `agent`, `background`, `hooks`, `paths`, `shell`. |
| Any other key | rejected | warning | |

Separately, the budget gate below caps each description at 300 characters.
The 1,024-character limit above comes from the specification.

## Values

The parser reads a deliberately small YAML subset:

- One-line plain values, single-quoted values (`''` is a quote), and
  double-quoted values with every YAML escape.
- Quote a value that contains `: ` or ` #`, ends with `:`, or starts with any of
  ``- ? : , [ ] { } # & * ! | > ' " % @ ` ``.
- Quote a value that YAML would load as something other than a string: empty or
  `~` or `null`, a boolean (including YAML 1.1's `yes`, `no`, `on`, `off`, `y`,
  and `n`), a number such as `1.1`, `0x1F`, or `1:20`, or a date such as
  `2026-10-16`.
- Full-line comments are allowed, and so is a comment after a quoted value. A
  ` #` inside a plain value is rejected, because YAML silently drops the rest of
  the line.
- Neither level supports anchors, aliases, tags, multi-line quoted values, flow
  collections that span lines, quoted or complex keys, or document markers.
  Each is reported as `UNSUPPORTED`, never accepted silently, under every key.
- A quote, `[`, or `{` that never closes is a `SYNTAX` error. A plain value
  that PyYAML's safe loader cannot construct, such as `=`, `<<`, or the
  impossible date `2026-02-30`, is an `UNLOADABLE` error wherever it appears,
  including inside a list.

The spec level also parses literal (`|`) and folded (`>`) block scalars with
every chomping and indentation indicator, plain values that continue onto later
lines, values that start on the line after their key, block sequences
(including sequences of mappings, such as Claude Code's `hooks`), and one-line
flow sequences, whose items it reads exactly as PyYAML does. Flow mappings
(`{...}`) are rejected under the keys the specification defines and accepted,
on one line, under any other key. Keys outside the specification are exempt
from portability rules only: invalid or unsupported YAML under them is still an
error, because PyYAML would reject it or read it differently.

## Body

A line made only of `[TODO: ...]` outside a code fence is an error at the
portable level and a warning at the spec level. Codex's validator applies the
same rule. Both split the body into lines with Python's `str.splitlines()`, so
a vertical tab, form feed, U+001C-U+001E, U+0085, U+2028, or U+2029 also starts
a new line.

## Finding Codes

| Code | Portable | Spec | Meaning |
| --- | --- | --- | --- |
| `PATH` | error | error | The skill path is not a directory. |
| `SKILL_MD_MISSING` | error | error | The folder has no `SKILL.md`. |
| `READ_ERROR` | error | error | `SKILL.md` cannot be read. |
| `ENCODING` | error | error | The file is not valid UTF-8. |
| `BOM` | error | warning | A UTF-8 byte-order mark, at the start or inside the frontmatter. |
| `CRLF` | error | warning | CR or CRLF line endings. |
| `CONTROL_CHARACTER` | error | error | A character YAML forbids. |
| `UNICODE_LINE_BREAK` | error | warning | U+0085, U+2028, or U+2029 in the frontmatter. |
| `FRONTMATTER_MISSING` | error | error | The first line is not `---`. |
| `FRONTMATTER_UNTERMINATED` | error | error | No closing `---` line. |
| `DELIMITER_SPACING` | error | warning | Trailing whitespace on a `---` delimiter. |
| `TAB` | error | warning | A tab inside the frontmatter. |
| `TAB_INDENT` | error | error | A tab used as indentation. |
| `SYNTAX` | error | error | Invalid YAML, such as an unquoted `: `, text after a closing quote, or a quote or bracket that never closes. |
| `UNSUPPORTED` | error | error | Valid YAML outside the supported subset. |
| `UNLOADABLE` | error | error | A plain value PyYAML's safe loader cannot construct, such as `=`, `<<`, or `2026-02-30`. |
| `DUPLICATE_KEY` | error | error | A key appears twice in one mapping. |
| `UNKNOWN_KEY` | error | warning | A key no schema defines. |
| `COMPATIBILITY_KEY` | error | not reported | The `compatibility` key. |
| `ALLOWED_TOOLS_KEY` | error | not reported | The `allowed-tools` key. |
| `CLAUDE_ONLY_KEY` | error | warning | A Claude Code-only key. |
| `BLOCK_SCALAR` | error | not reported | A literal or folded block scalar. |
| `MULTILINE_SCALAR` | error | not reported | A value that spans lines or contains a line break. |
| `COMMENT_IN_VALUE` | error | warning | ` #` inside a plain value. |
| `NON_STRING` | error | error | A value that must be a string loads as another type. |
| `METADATA_TYPE` | error | error | `metadata` is not a mapping. |
| `METADATA_NESTED` | error | error | A `metadata` value is itself a collection. |
| `NAME_MISSING` | error | error | No `name`. |
| `NAME_FORMAT` | error | error | The name breaks the character rules. |
| `NAME_LENGTH` | error | error | The name is longer than 64 characters. |
| `NAME_FOLDER` | error | error | The name differs from its folder. |
| `DESCRIPTION_MISSING` | error | error | No `description`. |
| `DESCRIPTION_EMPTY` | error | error | The description is empty. |
| `DESCRIPTION_LENGTH` | error | error | The description is longer than 1,024 characters. |
| `DESCRIPTION_ANGLE_BRACKETS` | error | warning | `<` or `>` in the description. |
| `COMPATIBILITY_LENGTH` | not reported | error | `compatibility` is not a string of 1-500 characters. |
| `ALLOWED_TOOLS_FORMAT` | not reported | warning | `allowed-tools` is not a string. |
| `TODO_PLACEHOLDER` | error | warning | An unfinished `[TODO: ...]` description or body line. |

## Explicit-Only Skills

A skill with side effects, such as publishing a package or rewriting project
documents, should run only when the user names it. One `SKILL.md` serves both
hosts, so neither host's switch can live in the frontmatter:

- **Codex:** the skill's `agents/openai.yaml` sets
  `policy.allow_implicit_invocation: false`. Codex then keeps the skill out of
  the model's context until the user invokes it as `$skill-name`.
- **Claude Code:** the description says when to use it, in the form "Use when
  the user explicitly asks to ...". Claude Code's own switch,
  `disable-model-invocation`, is a Claude-only key, which Codex's validator
  rejects and the portable level forbids. Keeping a "Use when" clause also
  satisfies the auditor's trigger-language check.

Why this split: a per-host frontmatter key would fork the canonical file, and a
generated Claude-only copy would need its own freshness checks. Neither is worth
it until trigger data shows a problem. Claude Code still lists every skill, so
its description budget counts explicit-only skills too.

The explicit-only skills are `game-release` (the packaging skill),
`game-qa-cleanup`, and `game-full-verification`. Each sets the policy, and
each description says "Use when the user explicitly asks to ..." or "Use when
the user explicitly asks for ...". Each new skill is classified when it ships.

## Budgets

Hosts list every skill's description in the agent's context, and each body
loads whenever its skill runs, so `tools/verify_package.py` fails when:

- a description is longer than 300 characters (`DESCRIPTION_BUDGET`);
- all descriptions together are longer than 3,600 characters
  (`DESCRIPTION_TOTAL`); or
- a body's estimated tokens exceed its cap (`BODY_BUDGET`): 2,500 for
  `game-skill-auditor`, 2,000 for `music-composer` and
  `game-context-continuity`, and 1,200 for every other skill.

A body is everything after the closing `---`. Its estimate is its characters
divided by 4, rounded up. That is rough for any one tokenizer, but stable
enough to compare skills with one another and with their caps. When a body
outgrows its cap, move detail into an on-demand reference linked by one
routing line. `--budgets` prints every skill's figures:

```text
python -B tools/verify_package.py --budgets
```

## Relationship To Other Checks

- `tools/validate_skill.py` is the suite's frontmatter gate.
- The auditor carries a generated copy of this module,
  `skills/game-skill-auditor/scripts/skill_frontmatter.py`, behind its own
  `scripts/validate_skill.py`, which checks one skill at the spec level and
  also fails on the findings that Codex's validator rejects but the spec
  level only warns about or allows, such as `TAB`, `UNKNOWN_KEY`,
  `CLAUDE_ONLY_KEY`, and `COMPATIBILITY_KEY`. The
  auditor's evidence check pins both files' hashes, so a machine with neither
  PyYAML nor Codex can still produce structural evidence.
  `tools/verify_package.py` fails if the copy differs from this module after
  its one header line, so edit this module and then recopy it.
- `skills/game-skill-auditor/scripts/audit_skill.py` keeps its own frontmatter
  checks until a later v1.1 step moves it onto this module.
- The schema module never imports PyYAML. PyYAML may appear only in CI, as a
  test dependency.
  [`tests/frontmatter/test_differential.py`](../tests/frontmatter/test_differential.py)
  uses the pinned PyYAML to check generated files: every portable-valid file
  loads with identical values and passes Codex's validator rules, and every
  spec-valid file loads.

## Corpus

[`tests/frontmatter/cases.json`](../tests/frontmatter/cases.json) defines each
case below. [`tests/frontmatter/test_frontmatter.py`](../tests/frontmatter/test_frontmatter.py)
writes every case at run time, so the repository holds no raw BOM, CRLF, or
cp1252 fixture, and fails if this table and the code disagree.

| Case | What it checks | Portable | Spec |
| --- | --- | --- | --- |
| `valid-minimal` | name and description only | valid | valid |
| `valid-optional-keys` | license and one-level string metadata | valid | valid |
| `quoted-colon-hash` | double quotes protect ': ' and ' #' | valid | valid |
| `single-quoted` | single quotes with an escaped quote | valid | valid |
| `curly-quotes` | curly quotes in the description | valid | valid |
| `non-ascii` | arrow, box drawing, and emoji | valid | valid |
| `bom` | UTF-8 byte-order mark | invalid: BOM | valid; warns BOM |
| `crlf` | CRLF line endings | invalid: CRLF | valid; warns CRLF |
| `not-utf8` | cp1252 bytes | invalid: ENCODING | invalid: ENCODING |
| `tab-in-value` | tab inside a value | invalid: TAB | valid; warns TAB |
| `tab-indent` | tab used as indentation | invalid: METADATA_TYPE, TAB, TAB_INDENT | invalid: METADATA_TYPE, TAB_INDENT; warns TAB |
| `duplicate-key` | the same key twice | invalid: DUPLICATE_KEY | invalid: DUPLICATE_KEY |
| `unknown-key` | a key outside every schema | invalid: UNKNOWN_KEY | valid; warns UNKNOWN_KEY |
| `compatibility` | the spec's compatibility key | invalid: COMPATIBILITY_KEY | valid |
| `compatibility-501` | compatibility with 501 characters | invalid: COMPATIBILITY_KEY | invalid: COMPATIBILITY_LENGTH |
| `allowed-tools` | allowed-tools as a string | invalid: ALLOWED_TOOLS_KEY | valid |
| `allowed-tools-list` | allowed-tools as a YAML list | invalid: ALLOWED_TOOLS_KEY | valid; warns ALLOWED_TOOLS_FORMAT |
| `claude-when-to-use` | Claude-only key when_to_use | invalid: CLAUDE_ONLY_KEY | valid; warns CLAUDE_ONLY_KEY |
| `claude-disable-model-invocation` | Claude-only key disable-model-invocation | invalid: CLAUDE_ONLY_KEY | valid; warns CLAUDE_ONLY_KEY |
| `claude-argument-hint` | Claude-only key argument-hint | invalid: CLAUDE_ONLY_KEY | valid; warns CLAUDE_ONLY_KEY |
| `claude-context` | Claude-only key context | invalid: CLAUDE_ONLY_KEY | valid; warns CLAUDE_ONLY_KEY |
| `claude-agent` | Claude-only key agent | invalid: CLAUDE_ONLY_KEY | valid; warns CLAUDE_ONLY_KEY |
| `nested-metadata` | metadata nested two levels | invalid: METADATA_NESTED | invalid: METADATA_NESTED |
| `metadata-non-string` | metadata value YAML reads as a float | invalid: NON_STRING | invalid: NON_STRING |
| `metadata-flow-mapping` | metadata written as a flow mapping | invalid: UNSUPPORTED | invalid: UNSUPPORTED |
| `description-boolean` | description YAML reads as a boolean | invalid: NON_STRING | invalid: NON_STRING |
| `description-null` | description with no value | invalid: NON_STRING | invalid: NON_STRING |
| `license-number` | license YAML reads as a float | invalid: NON_STRING | invalid: NON_STRING |
| `unquoted-colon` | unquoted ': ' in the description | invalid: SYNTAX | invalid: SYNTAX |
| `comment-in-value` | unquoted ' #' truncates the value | invalid: COMMENT_IN_VALUE | valid; warns COMMENT_IN_VALUE |
| `indicator-start` | plain value starting with '@' | invalid: SYNTAX | invalid: SYNTAX |
| `invalid-escape` | unknown double-quote escape | invalid: SYNTAX | invalid: SYNTAX |
| `text-after-quote` | text after the closing quote | invalid: SYNTAX | invalid: SYNTAX |
| `description-1024` | description with exactly 1,024 characters | valid | valid |
| `description-1025` | description with 1,025 characters | invalid: DESCRIPTION_LENGTH | invalid: DESCRIPTION_LENGTH |
| `uppercase-name` | uppercase letters in the name | invalid: NAME_FORMAT | invalid: NAME_FORMAT |
| `double-hyphen-name` | consecutive hyphens in the name | invalid: NAME_FORMAT | invalid: NAME_FORMAT |
| `name-65` | name with 65 characters | invalid: NAME_LENGTH | invalid: NAME_LENGTH |
| `folder-mismatch` | name differs from its folder | invalid: NAME_FOLDER | invalid: NAME_FOLDER |
| `missing-name` | no name key | invalid: NAME_MISSING | invalid: NAME_MISSING |
| `missing-description` | no description key | invalid: DESCRIPTION_MISSING | invalid: DESCRIPTION_MISSING |
| `empty-description` | description is an empty string | invalid: DESCRIPTION_EMPTY | invalid: DESCRIPTION_EMPTY |
| `angle-brackets` | angle brackets in the description | invalid: DESCRIPTION_ANGLE_BRACKETS | valid; warns DESCRIPTION_ANGLE_BRACKETS |
| `block-folded` | folded block scalar | invalid: BLOCK_SCALAR | valid |
| `block-literal` | literal block scalar | invalid: BLOCK_SCALAR, MULTILINE_SCALAR | valid |
| `multiline-plain` | plain value continued on the next line | invalid: MULTILINE_SCALAR | valid |
| `value-next-line` | value on the line after its key | invalid: MULTILINE_SCALAR | valid |
| `no-frontmatter` | no opening delimiter | invalid: FRONTMATTER_MISSING | invalid: FRONTMATTER_MISSING |
| `unterminated` | no closing delimiter | invalid: FRONTMATTER_UNTERMINATED | invalid: FRONTMATTER_UNTERMINATED |
| `delimiter-spacing` | trailing space after the opening delimiter | invalid: DELIMITER_SPACING | valid; warns DELIMITER_SPACING |
| `todo-description` | quoted [TODO: ...] description | invalid: TODO_PLACEHOLDER | valid; warns TODO_PLACEHOLDER |
| `todo-template-list` | unquoted [TODO: ...] reads as a list | invalid: NON_STRING | invalid: NON_STRING |
| `todo-body` | [TODO: ...] line in the body | invalid: TODO_PLACEHOLDER | valid; warns TODO_PLACEHOLDER |
| `todo-in-fence` | [TODO: ...] inside a code fence | valid | valid |
| `anchor` | YAML anchor | invalid: UNSUPPORTED | invalid: UNSUPPORTED |
| `quoted-key` | quoted key | invalid: NAME_MISSING, UNSUPPORTED | invalid: NAME_MISSING, UNSUPPORTED |
| `control-character` | BEL control character | invalid: CONTROL_CHARACTER | invalid: CONTROL_CHARACTER |
| `line-separator` | U+2028 inside a value | invalid: UNICODE_LINE_BREAK | valid; warns UNICODE_LINE_BREAK |
| `swallowing-quote` | a quote that closes lines later swallows the keys between | invalid: CLAUDE_ONLY_KEY, DESCRIPTION_MISSING, NAME_MISSING, UNSUPPORTED | invalid: DESCRIPTION_MISSING, NAME_MISSING, UNSUPPORTED; warns CLAUDE_ONLY_KEY |
| `unterminated-quote` | a quote that never closes | invalid: CLAUDE_ONLY_KEY, SYNTAX | invalid: SYNTAX; warns CLAUDE_ONLY_KEY |
| `unclosed-flow` | a flow sequence that never closes | invalid: CLAUDE_ONLY_KEY, SYNTAX | invalid: SYNTAX; warns CLAUDE_ONLY_KEY |
| `multiline-flow` | a flow sequence that spans lines | invalid: CLAUDE_ONLY_KEY, UNSUPPORTED | invalid: UNSUPPORTED; warns CLAUDE_ONLY_KEY |
| `claude-alias` | an undefined alias under a Claude-only key | invalid: CLAUDE_ONLY_KEY, UNSUPPORTED | invalid: UNSUPPORTED; warns CLAUDE_ONLY_KEY |
| `claude-tag` | a tag under a Claude-only key | invalid: CLAUDE_ONLY_KEY, UNSUPPORTED | invalid: UNSUPPORTED; warns CLAUDE_ONLY_KEY |
| `flow-alias-item` | an unquoted glob that YAML reads as an alias | invalid: CLAUDE_ONLY_KEY, UNSUPPORTED | invalid: UNSUPPORTED; warns CLAUDE_ONLY_KEY |
| `allowed-tools-equals` | allowed-tools is YAML's value indicator '=' | invalid: ALLOWED_TOOLS_KEY, UNLOADABLE | invalid: UNLOADABLE |
| `allowed-tools-list-merge` | an allowed-tools list item is YAML's merge indicator '<<' | invalid: ALLOWED_TOOLS_KEY, UNLOADABLE | invalid: UNLOADABLE; warns ALLOWED_TOOLS_FORMAT |
| `impossible-date` | a value PyYAML reads as a date that does not exist | invalid: CLAUDE_ONLY_KEY, UNLOADABLE | invalid: UNLOADABLE; warns CLAUDE_ONLY_KEY |
| `claude-hooks` | Claude-only hooks with mappings inside sequences | invalid: CLAUDE_ONLY_KEY | valid; warns CLAUDE_ONLY_KEY |
| `claude-flow-mapping` | a closed flow mapping under a Claude-only key | invalid: CLAUDE_ONLY_KEY | valid; warns CLAUDE_ONLY_KEY |
| `todo-after-line-separator` | [TODO: ...] after a U+2028 line separator in the body | invalid: TODO_PLACEHOLDER | valid; warns TODO_PLACEHOLDER |
| `todo-after-form-feed` | [TODO: ...] after a form feed in the body | invalid: TODO_PLACEHOLDER | valid; warns TODO_PLACEHOLDER |
