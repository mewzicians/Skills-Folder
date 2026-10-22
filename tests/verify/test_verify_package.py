#!/usr/bin/env python3
"""Plant package problems in temporary copies and check tools/verify_package.py.

    python -B tests/verify/test_verify_package.py
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERIFIER = ROOT / "tools" / "verify_package.py"
CHILD_FLAGS = ["-B", "-X", "warn_default_encoding", "-W", "error::EncodingWarning"]
# Built from fragments so this file never contains the term it plants.
PRIVATE_TERM = "Office" + "Wars"


def package_files() -> list[str]:
    """The files a fresh checkout would contain."""
    listed = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        capture_output=True,
        check=False,
    )
    if listed.returncode == 0:
        names = listed.stdout.decode("utf-8", "surrogateescape").split("\0")
        return sorted(name for name in names if name and (ROOT / name).is_file())
    return sorted(
        path.relative_to(ROOT).as_posix()
        for path in ROOT.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(ROOT).parts
    )


def copy_package(destination: Path) -> Path:
    for name in package_files():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    return destination


def run_verifier(root: Path, *extra: str) -> tuple[int, dict]:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    completed = subprocess.run(
        [sys.executable, *CHILD_FLAGS, str(VERIFIER), "--root", str(root), "--json", *extra],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )
    if completed.returncode not in (0, 1):
        raise AssertionError(f"verifier failed: {completed.returncode}\n{completed.stderr}")
    return completed.returncode, json.loads(completed.stdout)


def codes_by_path(payload: dict) -> set[tuple[str, str]]:
    return {(item["code"], item["path"]) for item in payload["problems"]}


def symlinks_supported() -> bool:
    """Windows creates symbolic links only with Developer Mode or elevation."""
    with tempfile.TemporaryDirectory(prefix="verify-symlink-probe-") as temp:
        try:
            os.symlink(Path(temp) / "target", Path(temp) / "link")
        except (OSError, NotImplementedError):
            return False
    return True


SYMLINKS = symlinks_supported()
DANGLING = "templates/dangling.md"


def plant_dangling_symlinks(root: Path) -> None:
    """A dangling link outside the skills and one standing in for a skill's metadata."""
    os.symlink("missing-target.md", root / DANGLING)
    metadata = root / "skills" / "game-debug" / "agents" / "openai.yaml"
    metadata.unlink()
    os.symlink("missing-openai.yaml", metadata)


BROKEN_LINK_PROBLEMS = {
    ("BROKEN_SYMLINK", DANGLING),
    ("BROKEN_SYMLINK", "skills/game-debug/agents/openai.yaml"),
    ("OPENAI_YAML_MISSING", "skills/game-debug"),
}


class FilesystemInventoryTest(unittest.TestCase):
    """An extracted archive: no .git, so every file is checked."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="verify-package-")
        self.root = copy_package(Path(self.temp.name) / "package")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_clean_copy_passes(self) -> None:
        returncode, payload = run_verifier(self.root)
        self.assertEqual(payload["problems"], [])
        self.assertEqual(returncode, 0)
        self.assertEqual(payload["inventory"], "filesystem")

    def test_every_planted_problem_is_reported_in_one_run(self) -> None:
        reference = self.root / "skills" / "game-plan" / "references" / "project-profile.md"
        reference.write_bytes(reference.read_bytes().replace(b"\n", b"\r\n"))
        notice = self.root / "NOTICE"
        notice.write_bytes(b"\xef\xbb\xbf" + notice.read_bytes())
        skill = self.root / "skills" / "game-debug" / "SKILL.md"
        skill.write_bytes(skill.read_bytes().replace(b"name: game-debug", b"name: Game-Debug", 1))
        cache = self.root / "skills" / "game-implement" / "scripts" / "__pycache__"
        cache.mkdir(parents=True)
        (cache / "helper.cpython-313.pyc").write_bytes(b"\x00\x01")
        readme = self.root / "README.md"
        readme.write_bytes(readme.read_bytes() + f"Built for {PRIVATE_TERM}.\n".encode("utf-8"))

        returncode, payload = run_verifier(self.root)
        found = codes_by_path(payload)
        expected = {
            ("CRLF", "skills/game-plan/references/project-profile.md"),
            # The CRLF copy no longer matches the other routing references.
            ("IDENTICAL_DRIFT", "skills/game-plan/references/project-profile.md"),
            ("BOM", "NOTICE"),
            ("FRONTMATTER_NAME_FORMAT", "skills/game-debug/SKILL.md"),
            ("FRONTMATTER_NAME_FOLDER", "skills/game-debug/SKILL.md"),
            ("DEBRIS", "skills/game-implement/scripts/__pycache__/helper.cpython-313.pyc"),
            ("FORBIDDEN_TERM", "README.md"),
        }
        self.assertEqual(returncode, 1)
        self.assertEqual(found, expected, payload["problems"])
        messages = [item["message"] for item in payload["problems"]]
        self.assertEqual(len(messages), len(set(messages)), "each problem needs its own message")

    def test_product_name_slugs_are_forbidden(self) -> None:
        # Built from fragments so this file never contains a form it plants.
        first, second = "office", "wars"
        other_first, other_second = "off" + "ie", "war"
        forms = {
            "spaced": first.title() + " " + second.title(),
            "joined": first + second,
            "kebab": first + "-" + second,
            "snake": first + "_" + second,
            "upper-kebab": (first + "-" + second).upper(),
            "no-break-space": first.title() + "\u00a0" + second.title(),
            "other-spaced": other_first + " " + other_second,
            "other-kebab": other_first + "-" + other_second,
            "other-snake": other_first.title() + "_" + other_second.title(),
        }
        docs = self.root / "docs"
        for label, form in forms.items():
            (docs / f"slug-{label}.md").write_text(f"Built for {form}.\n", encoding="utf-8", newline="\n")
        slug_folder = docs / (first + "-" + second)
        slug_folder.mkdir()
        (slug_folder / "notes.md").write_text("Notes.\n", encoding="utf-8", newline="\n")
        (docs / "near-misses.md").write_text(
            "A box office hit, office work, and war games.\n", encoding="utf-8", newline="\n"
        )
        returncode, payload = run_verifier(self.root)
        expected = {("FORBIDDEN_TERM", f"docs/slug-{label}.md") for label in forms}
        expected.add(("FORBIDDEN_TERM", f"docs/{first}-{second}/notes.md"))
        self.assertEqual(returncode, 1)
        self.assertEqual(codes_by_path(payload), expected, payload["problems"])

    def test_git_metadata_is_excluded_by_path_part(self) -> None:
        # A worktree or submodule has a .git file; nested .git folders also occur.
        (self.root / ".git").write_text("gitdir: /nowhere\n", encoding="utf-8", newline="\n")
        nested = self.root / "templates" / ".git"
        nested.mkdir()
        (nested / "config").write_bytes(f"[remote]\r\n\turl = {PRIVATE_TERM}\r\n".encode("utf-8"))
        returncode, payload = run_verifier(self.root)
        self.assertEqual(payload["problems"], [])
        self.assertEqual(returncode, 0)

    def test_text_policy_and_missing_prompt(self) -> None:
        template = self.root / "templates" / "GAME_PROJECT_PROFILE.template.md"
        template.write_bytes(template.read_bytes() + "Café notes.\n".encode("cp1252"))
        license_file = self.root / "LICENSE"
        license_file.write_bytes(license_file.read_bytes().rstrip(b"\n"))
        prompt = self.root / "skills" / "game-debug" / "agents" / "openai.yaml"
        kept = [
            line
            for line in prompt.read_text(encoding="utf-8").splitlines(keepends=True)
            if "default_prompt" not in line
        ]
        prompt.write_text("".join(kept), encoding="utf-8", newline="\n")
        returncode, payload = run_verifier(self.root)
        self.assertEqual(returncode, 1)
        self.assertEqual(
            codes_by_path(payload),
            {
                ("NOT_UTF8", "templates/GAME_PROJECT_PROFILE.template.md"),
                ("NO_FINAL_NEWLINE", "LICENSE"),
                ("DEFAULT_PROMPT_MISSING", "skills/game-debug/agents/openai.yaml"),
            },
            payload["problems"],
        )

    def test_a_package_without_skills(self) -> None:
        shutil.rmtree(self.root / "skills")
        returncode, payload = run_verifier(self.root)
        self.assertEqual(returncode, 1)
        self.assertEqual(
            codes_by_path(payload),
            {
                ("NO_SKILLS", "skills"),
                # The auditor's generated copy went with the skills.
                ("COPY_MISSING", "skills/skill-auditor/scripts/skill_frontmatter.py"),
                # So did the skills the verifier knows are explicit-only.
                ("EXPLICIT_ONLY_MISSING", "skills/game-full-verification"),
                ("EXPLICIT_ONLY_MISSING", "skills/game-qa-cleanup"),
                ("EXPLICIT_ONLY_MISSING", "skills/game-release"),
                # So did the skill pages that README.md links to.
                ("LINK_MISSING", "README.md"),
            },
        )

    def test_an_internal_error_exits_3(self) -> None:
        # Break the inventory walk; the verifier must not report a failed check.
        program = (
            "import os, runpy, sys\n"
            "def broken_walk(*args, **kwargs):\n"
            "    raise RuntimeError('walk failed')\n"
            "os.walk = broken_walk\n"
            f"sys.argv = ['verify_package.py', '--root', {str(self.root)!r}]\n"
            f"runpy.run_path({str(VERIFIER)!r}, run_name='__main__')\n"
        )
        completed = subprocess.run(
            [sys.executable, *CHILD_FLAGS, "-c", program],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
            check=False,
        )
        self.assertEqual(completed.returncode, 3, completed.stdout + completed.stderr)
        self.assertIn("internal error", completed.stderr)
        self.assertIn("walk failed", completed.stderr)
        self.assertEqual(completed.stdout, "")

    @unittest.skipUnless(SYMLINKS, "symbolic links need extra privileges here")
    def test_dangling_symlinks_are_problems_not_internal_errors(self) -> None:
        plant_dangling_symlinks(self.root)
        returncode, payload = run_verifier(self.root)
        self.assertEqual(payload["inventory"], "filesystem")
        self.assertEqual(codes_by_path(payload), BROKEN_LINK_PROBLEMS, payload["problems"])
        self.assertEqual(returncode, 1)

    def test_generated_copies_must_match_their_source(self) -> None:
        copy = self.root / "skills" / "skill-auditor" / "scripts" / "skill_frontmatter.py"
        lines = copy.read_bytes().split(b"\n")
        lines[5] += b" # drift"
        copy.write_bytes(b"\n".join(lines))
        returncode, payload = run_verifier(self.root)
        self.assertEqual(returncode, 1)
        self.assertEqual(
            [(item["code"], item["path"], item["line"]) for item in payload["problems"]],
            [("COPY_DRIFT", "skills/skill-auditor/scripts/skill_frontmatter.py", 6)],
        )
        copy.write_bytes(b"\n".join(lines[1:]))
        returncode, payload = run_verifier(self.root)
        self.assertEqual(returncode, 1)
        self.assertEqual(
            codes_by_path(payload),
            {("COPY_HEADER", "skills/skill-auditor/scripts/skill_frontmatter.py")},
        )
        (self.root / "tools" / "lib" / "skill_frontmatter.py").unlink()
        copy.unlink()
        returncode, payload = run_verifier(self.root)
        self.assertEqual(returncode, 1)
        self.assertEqual(
            {(code, path) for code, path in codes_by_path(payload) if code == "COPY_MISSING"},
            {
                ("COPY_MISSING", "tools/lib/skill_frontmatter.py"),
                ("COPY_MISSING", "skills/skill-auditor/scripts/skill_frontmatter.py"),
            },
        )

    def test_identical_copies_must_stay_identical(self) -> None:
        drifted = self.root / "skills" / "game-debug" / "references" / "project-profile.md"
        lines = drifted.read_bytes().split(b"\n")
        lines[2] += b" Extra words."
        drifted.write_bytes(b"\n".join(lines))
        returncode, payload = run_verifier(self.root)
        self.assertEqual(returncode, 1)
        self.assertEqual(
            [(item["code"], item["path"], item["line"]) for item in payload["problems"]],
            [("IDENTICAL_DRIFT", "skills/game-debug/references/project-profile.md", 3)],
        )
        self.assertIn("skills/context-continuity/references/project-profile.md", payload["problems"][0]["message"])

    def test_every_skill_but_the_auditor_carries_the_router(self) -> None:
        router = "references/project-profile.md"
        (self.root / "skills" / "game-ux-audit" / router).unlink()
        shutil.copyfile(
            self.root / "skills" / "game-plan" / router, self.root / "skills" / "skill-auditor" / router
        )
        newcomer = self.root / "skills" / "game-newcomer"
        shutil.copytree(self.root / "skills" / "game-plan", newcomer)
        (newcomer / router).unlink()
        returncode, payload = run_verifier(self.root)
        self.assertEqual(returncode, 1)
        found = {(code, path) for code, path in codes_by_path(payload) if code.startswith("IDENTICAL_")}
        self.assertEqual(
            found,
            {
                ("IDENTICAL_MISSING", f"skills/game-ux-audit/{router}"),
                ("IDENTICAL_MISSING", f"skills/game-newcomer/{router}"),
                ("IDENTICAL_UNEXPECTED", f"skills/skill-auditor/{router}"),
            },
        )

    def test_explicit_only_skills_keep_their_policy_and_wording(self) -> None:
        skills = self.root / "skills"
        release = skills / "game-release" / "agents" / "openai.yaml"
        release.write_text(
            release.read_text(encoding="utf-8").replace(
                "allow_implicit_invocation: false", "allow_implicit_invocation: true"
            ),
            encoding="utf-8",
            newline="\n",
        )
        verification = skills / "game-full-verification" / "agents" / "openai.yaml"
        text = verification.read_text(encoding="utf-8")
        # A commented-out switch, or one outside the policy block, does not count.
        verification.write_text(
            text[: text.index("policy:")] + "# policy:\n#   allow_implicit_invocation: false\n"
            "extra:\n  allow_implicit_invocation: false\n",
            encoding="utf-8",
            newline="\n",
        )
        cleanup = skills / "game-qa-cleanup" / "SKILL.md"
        cleanup.write_text(
            cleanup.read_text(encoding="utf-8").replace(
                "Use when the user explicitly asks", "Use when the user asks", 1
            ),
            encoding="utf-8",
            newline="\n",
        )
        returncode, payload = run_verifier(self.root)
        self.assertEqual(returncode, 1)
        self.assertEqual(
            [(item["code"], item["path"], item["line"]) for item in payload["problems"]],
            [
                ("EXPLICIT_ONLY_POLICY", "skills/game-full-verification/agents/openai.yaml", None),
                ("EXPLICIT_ONLY_WORDING", "skills/game-qa-cleanup/SKILL.md", 3),
                ("EXPLICIT_ONLY_POLICY", "skills/game-release/agents/openai.yaml", None),
            ],
        )
        shutil.rmtree(skills / "game-release")
        returncode, payload = run_verifier(self.root)
        self.assertIn(("EXPLICIT_ONLY_MISSING", "skills/game-release"), codes_by_path(payload))

    def test_missing_files_and_prompts(self) -> None:
        (self.root / "skills" / "game-ux-audit" / "agents" / "openai.yaml").unlink()
        prompt = self.root / "skills" / "game-qa-cleanup" / "agents" / "openai.yaml"
        prompt.write_text(
            prompt.read_text(encoding="utf-8").replace("$game-qa-cleanup", "$game-qa-cleanup-extra"),
            encoding="utf-8",
            newline="\n",
        )
        (self.root / "skills" / "orphan" / "notes").mkdir(parents=True)
        (self.root / "skills" / "orphan" / "notes" / "todo.md").write_text("notes\n", encoding="utf-8", newline="\n")
        returncode, payload = run_verifier(self.root)
        found = codes_by_path(payload)
        self.assertEqual(returncode, 1)
        self.assertIn(("OPENAI_YAML_MISSING", "skills/game-ux-audit"), found)
        self.assertIn(("DEFAULT_PROMPT_NAME", "skills/game-qa-cleanup/agents/openai.yaml"), found)
        self.assertIn(("SKILL_MD_MISSING", "skills/orphan"), found)


MANIFESTS = (
    ".claude-plugin/plugin.json",
    ".claude-plugin/marketplace.json",
    "plugin.json",
    ".agents/plugins/marketplace.json",
)


def edit_json(root: Path, path: str, change) -> None:
    target = root / path
    value = json.loads(target.read_text(encoding="utf-8"))
    change(value)
    target.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8", newline="\n")


def manifest_problems(payload: dict) -> set[tuple[str, str]]:
    return {pair for pair in codes_by_path(payload) if pair[0].startswith("MANIFEST_")}


class ManifestTest(unittest.TestCase):
    """The root plugin's manifests parse, carry required keys, and agree."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="verify-manifests-")
        self.root = copy_package(Path(self.temp.name) / "package")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_the_package_manifests_pass(self) -> None:
        returncode, payload = run_verifier(self.root)
        self.assertEqual(manifest_problems(payload), set(), payload["problems"])
        self.assertEqual(returncode, 0)

    def test_every_manifest_is_required(self) -> None:
        for path in MANIFESTS:
            (self.root / path).unlink()
        returncode, payload = run_verifier(self.root)
        self.assertEqual(returncode, 1)
        self.assertEqual(manifest_problems(payload), {("MANIFEST_MISSING", path) for path in MANIFESTS})

    def test_unparseable_manifests(self) -> None:
        (self.root / ".claude-plugin/plugin.json").write_text('{"name": "x",}\n', encoding="utf-8", newline="\n")
        (self.root / "plugin.json").write_bytes(b"\xef\xbb\xbf{}\n")
        (self.root / ".agents/plugins/marketplace.json").write_text("[]\n", encoding="utf-8", newline="\n")
        returncode, payload = run_verifier(self.root)
        self.assertEqual(returncode, 1)
        self.assertEqual(
            manifest_problems(payload),
            {
                ("MANIFEST_JSON", ".claude-plugin/plugin.json"),
                ("MANIFEST_JSON", "plugin.json"),
                ("MANIFEST_JSON", ".agents/plugins/marketplace.json"),
            },
        )

    def test_required_keys(self) -> None:
        def strip_claude(value: dict) -> None:
            for key in ("version", "author", "homepage"):
                value.pop(key)
            value["license"] = "MIT"

        def strip_codex(value: dict) -> None:
            entry = value["plugins"][0]
            entry["policy"].pop("authentication")
            entry.pop("category")

        def strip_claude_marketplace(value: dict) -> None:
            value.pop("owner")
            value["plugins"][0]["source"] = "./plugins/other"

        edit_json(self.root, ".claude-plugin/plugin.json", strip_claude)
        edit_json(self.root, ".agents/plugins/marketplace.json", strip_codex)
        edit_json(self.root, ".claude-plugin/marketplace.json", strip_claude_marketplace)
        returncode, payload = run_verifier(self.root)
        self.assertEqual(returncode, 1)
        messages = {
            (item["path"], item["message"]) for item in payload["problems"] if item["code"] == "MANIFEST_KEY"
        }
        self.assertEqual(
            messages,
            {
                (".claude-plugin/plugin.json", "needs a non-empty string version."),
                (".claude-plugin/plugin.json", "needs a non-empty string homepage."),
                (".claude-plugin/plugin.json", "needs author as an object with a non-empty name."),
                (".claude-plugin/plugin.json", "license must be Apache-2.0, as in LICENSE."),
                (".agents/plugins/marketplace.json", "needs a non-empty string plugins[0].policy.authentication."),
                (".agents/plugins/marketplace.json", "needs a non-empty string plugins[0].category."),
                (".claude-plugin/marketplace.json", "needs owner as an object with a non-empty name."),
                (".claude-plugin/marketplace.json", "plugins[0].source must be './', the repository root plugin."),
            },
        )

    def test_codex_values_must_be_documented(self) -> None:
        def undocumented_marketplace(value: dict) -> None:
            entry = value["plugins"][0]
            entry["category"] = "Coding"
            entry["policy"] = {"installation": "ENABLED", "authentication": "ON_FIRST_USE"}

        edit_json(self.root, ".agents/plugins/marketplace.json", undocumented_marketplace)
        edit_json(
            self.root, "plugin.json", lambda value: value["extensions"]["com.openai"]["interface"].update(category="Games")
        )
        returncode, payload = run_verifier(self.root)
        self.assertEqual(returncode, 1)
        messages = sorted(
            (item["path"], item["message"].split(" is not ")[0])
            for item in payload["problems"]
            if item["code"] == "MANIFEST_VALUE"
        )
        self.assertEqual(
            messages,
            [
                (".agents/plugins/marketplace.json", "plugins[0].category 'Coding'"),
                (".agents/plugins/marketplace.json", "plugins[0].policy.authentication 'ON_FIRST_USE'"),
                (".agents/plugins/marketplace.json", "plugins[0].policy.installation 'ENABLED'"),
                ("plugin.json", "extensions.com.openai.interface.category 'Games'"),
            ],
        )
        hint = next(item["message"] for item in payload["problems"] if "'Coding'" in item["message"])
        self.assertIn("use one of: Developer Tools, Productivity,", hint)

    def test_other_documented_codex_values_pass(self) -> None:
        def other_marketplace(value: dict) -> None:
            entry = value["plugins"][0]
            entry["category"] = "Scientific Research"
            entry["policy"] = {"installation": "INSTALLED_BY_DEFAULT", "authentication": "ON_USE"}

        edit_json(self.root, ".agents/plugins/marketplace.json", other_marketplace)
        edit_json(
            self.root,
            "plugin.json",
            lambda value: value["extensions"]["com.openai"]["interface"].update(category="Education & Research"),
        )
        returncode, payload = run_verifier(self.root, "--metadata")
        self.assertEqual(manifest_problems(payload), set(), payload["problems"])
        self.assertEqual(returncode, 0)

    def test_listing_text_and_marketplace_titles(self) -> None:
        def long_listing(value: dict) -> None:
            interface = value["extensions"]["com.openai"]["interface"]
            interface["shortDescription"] = "Plan, build, test, and release games"
            interface.pop("longDescription")

        def untitled_codex(value: dict) -> None:
            value.pop("interface")

        def described_in_metadata(value: dict) -> None:
            value["metadata"] = {"description": value.pop("description")}

        edit_json(self.root, "plugin.json", long_listing)
        edit_json(self.root, ".agents/plugins/marketplace.json", untitled_codex)
        edit_json(self.root, ".claude-plugin/marketplace.json", described_in_metadata)
        returncode, payload = run_verifier(self.root, "--metadata")
        self.assertEqual(returncode, 1)
        self.assertEqual(
            sorted((item["code"], item["path"], item["message"]) for item in payload["problems"]),
            [
                ("MANIFEST_KEY", ".agents/plugins/marketplace.json", "needs a non-empty string interface.displayName."),
                ("MANIFEST_KEY", ".claude-plugin/marketplace.json", "needs a non-empty string description."),
                ("MANIFEST_KEY", "plugin.json", "needs a non-empty string extensions.com.openai.interface.longDescription."),
                (
                    "MANIFEST_VALUE",
                    "plugin.json",
                    "extensions.com.openai.interface.shortDescription has 36 characters; the limit is 30.",
                ),
            ],
        )

    def test_the_documented_codex_lists(self) -> None:
        spec = importlib.util.spec_from_file_location("verify_package_lists", VERIFIER)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        self.addCleanup(sys.modules.pop, spec.name, None)
        spec.loader.exec_module(module)
        self.assertEqual(
            sorted(module.CODEX_CATEGORIES),
            sorted(
                [
                    "Business & Operations", "Communication", "Creativity", "Data & Analytics", "Developer Tools",
                    "Education & Research", "Finance", "Productivity", "Scientific Research", "Security",
                ]
            ),
        )
        self.assertEqual(module.CODEX_INSTALLATION, ("AVAILABLE", "INSTALLED_BY_DEFAULT", "NOT_AVAILABLE"))
        self.assertEqual(module.CODEX_AUTHENTICATION, ("ON_INSTALL", "ON_USE"))

    def test_the_portable_manifest_follows_agent_plugins(self) -> None:
        def break_portable(value: dict) -> None:
            value["$schema"] = "https://agent-plugins.org/schemas/0.9.0/plugin.schema.json"
            value["skills"] = "./skills/"
            # A Codex key outside extensions.com.openai.
            value["interface"] = value["extensions"]["com.openai"].pop("interface")
            value["extensions"]["openai"] = {}
            value["author"]["role"] = "maintainer"

        edit_json(self.root, "plugin.json", break_portable)
        returncode, payload = run_verifier(self.root)
        self.assertEqual(returncode, 1)
        messages = sorted(item["message"] for item in payload["problems"] if item["code"] == "MANIFEST_SCHEMA")
        self.assertEqual(
            messages,
            sorted(
                [
                    "$schema must be https://agent-plugins.org/schemas/1.0.0/plugin.schema.json.",
                    "'interface' is not an Agent Plugins key; put client data under extensions.",
                    "'skills' is not an Agent Plugins key; put client data under extensions.",
                    "author.role must be one of name, email, or url, as a string.",
                    "extensions.openai must be a reverse-domain namespace holding an object.",
                ]
            ),
        )

    def test_reserved_and_disagreeing_names(self) -> None:
        edit_json(self.root, ".claude-plugin/plugin.json", lambda value: value.update(name="claude-game-tools"))
        edit_json(self.root, ".claude-plugin/marketplace.json", lambda value: value.update(name="agent-skills"))
        returncode, payload = run_verifier(self.root)
        self.assertEqual(returncode, 1)
        problems = [item for item in payload["problems"] if item["code"] == "MANIFEST_NAME"]
        self.assertEqual(
            sorted(item["path"] for item in problems),
            [".claude-plugin/marketplace.json", ".claude-plugin/plugin.json", "plugin.json"],
        )
        disagreement = next(item for item in problems if item["path"] == "plugin.json")
        self.assertIn("'claude-game-tools'", disagreement["message"])
        self.assertIn("'game-dev-skills'", disagreement["message"])

    def test_no_plugin_level_agents_folder(self) -> None:
        folder = self.root / "agents"
        folder.mkdir()
        (folder / "reviewer.md").write_text("---\nname: reviewer\n---\n", encoding="utf-8", newline="\n")
        returncode, payload = run_verifier(self.root)
        self.assertEqual(returncode, 1)
        self.assertEqual(manifest_problems(payload), {("MANIFEST_AGENTS_FOLDER", "agents/reviewer.md")})


def problem_lines(payload: dict, prefix: str) -> list[tuple[str, str, int | None, str]]:
    return sorted(
        (item["code"], item["path"], item["line"], item["message"])
        for item in payload["problems"]
        if item["code"].startswith(prefix)
    )


class VersionTest(unittest.TestCase):
    """VERSION, both plugin manifests, and the newest CHANGELOG entry agree."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="verify-version-")
        self.root = copy_package(Path(self.temp.name) / "package")
        self.version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def changelog(self, old: str, new: str) -> None:
        path = self.root / "CHANGELOG.md"
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")

    def test_the_package_versions_agree(self) -> None:
        returncode, payload = run_verifier(self.root, "--metadata")
        self.assertEqual((returncode, payload["problems"]), (0, []))
        self.assertEqual(payload["version"], self.version)
        returncode, payload = run_verifier(self.root)
        self.assertEqual(payload["version"], self.version)

    def test_a_manifest_that_disagrees(self) -> None:
        edit_json(self.root, ".claude-plugin/plugin.json", lambda value: value.update(version="1.0.9"))
        edit_json(self.root, "plugin.json", lambda value: value.pop("version"))
        returncode, payload = run_verifier(self.root, "--metadata")
        self.assertEqual(returncode, 1)
        self.assertEqual(
            problem_lines(payload, "VERSION_"),
            [
                ("VERSION_MISMATCH", ".claude-plugin/plugin.json", None,
                 f"version is '1.0.9', but VERSION says '{self.version}'."),
                ("VERSION_MISMATCH", "plugin.json", None, f"version is None, but VERSION says '{self.version}'."),
            ],
        )

    def test_the_newest_changelog_entry_must_match(self) -> None:
        heading = next(
            line for line in (self.root / "CHANGELOG.md").read_text(encoding="utf-8").split("\n")
            if line.startswith(f"## [{self.version}]")
        )
        self.changelog(heading, "## [Unreleased]\n\n" + heading)
        returncode, payload = run_verifier(self.root, "--metadata")
        self.assertEqual((returncode, payload["problems"]), (0, []), "an Unreleased section is skipped")
        self.changelog(heading, "## [9.9.9] - 2099-01-01\n\n" + heading)
        returncode, payload = run_verifier(self.root, "--metadata")
        [problem] = problem_lines(payload, "VERSION_")
        self.assertEqual(problem[:2], ("VERSION_MISMATCH", "CHANGELOG.md"))
        self.assertIn("'## [9.9.9] - 2099-01-01'", problem[3])

    def test_a_release_entry_needs_a_date(self) -> None:
        self.changelog(f"## [{self.version}] - ", f"## [{self.version}]\n\nDated ")
        returncode, payload = run_verifier(self.root, "--metadata")
        self.assertEqual([item[:2] for item in problem_lines(payload, "VERSION_")], [("VERSION_MISMATCH", "CHANGELOG.md")])

    def test_the_version_file_holds_one_version(self) -> None:
        for content in (f"v{self.version}\n", self.version, f"{self.version}\n\n", "1.1\n"):
            with self.subTest(content=content):
                (self.root / "VERSION").write_bytes(content.encode("utf-8"))
                returncode, payload = run_verifier(self.root, "--metadata")
                self.assertEqual(returncode, 1)
                self.assertEqual([item[:2] for item in problem_lines(payload, "VERSION_")], [("VERSION_FORMAT", "VERSION")])

    def test_missing_version_files(self) -> None:
        (self.root / "CHANGELOG.md").unlink()
        returncode, payload = run_verifier(self.root, "--metadata")
        self.assertEqual([item[:2] for item in problem_lines(payload, "VERSION_")], [("VERSION_MISSING", "CHANGELOG.md")])
        (self.root / "VERSION").unlink()
        returncode, payload = run_verifier(self.root, "--metadata")
        self.assertEqual([item[:2] for item in problem_lines(payload, "VERSION_")], [("VERSION_MISSING", "VERSION")])


# Planted README lines: (text, expected problem code or None for a clean line).
PLANTED_LINKS = [
    ("[gone](docs/GONE.md)", "LINK_MISSING"),
    ("![art](.github/assets/missing.svg)", "LINK_MISSING"),
    ('<p><img src="missing.png" alt=""></p>', "LINK_MISSING"),
    ("[no heading](#no-such-heading)", "LINK_ANCHOR"),
    ("[no section](docs/COMPATIBILITY.md#no-such-section)", "LINK_ANCHOR"),
    ("[outside](../outside.md)", "LINK_MISSING"),
    ("[ref]: docs/NOPE.md", "LINK_MISSING"),
    ("[folder](skills/) and [heading](#install) and [encoded](docs/COMPATIBILITY.md#known-limits)", None),
    ("[site](https://example.com/x.md) and <a href=\"mailto:probe@example.com\">mail</a>", None),
    ("Inline code is not a link: `[x](docs/GONE.md)`.", None),
]


class LinkTest(unittest.TestCase):
    """Relative links and images resolve, and fragments name a heading or anchor."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="verify-links-")
        self.root = copy_package(Path(self.temp.name) / "package")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_the_package_links_resolve(self) -> None:
        returncode, payload = run_verifier(self.root, "--metadata")
        self.assertEqual((returncode, payload["problems"]), (0, []))
        self.assertGreater(payload["links_checked"], 20)

    def test_planted_links(self) -> None:
        readme = self.root / "README.md"
        text = readme.read_text(encoding="utf-8")
        start = text.count("\n") + 1
        planted = "\n".join(line for line, _ in PLANTED_LINKS)
        fenced = "\n```text\n[fenced](docs/GONE.md)\n```\n"
        readme.write_text(text + planted + "\n" + fenced, encoding="utf-8", newline="\n")
        returncode, payload = run_verifier(self.root, "--metadata")
        self.assertEqual(returncode, 1)
        expected = [
            (code, "README.md", start + index)
            for index, (_, code) in enumerate(PLANTED_LINKS)
            if code is not None
        ]
        self.assertEqual(sorted(item[:3] for item in problem_lines(payload, "LINK_")), sorted(expected))

    def test_docs_links_and_duplicate_headings(self) -> None:
        doc = self.root / "docs" / "planted.md"
        doc.write_text(
            "# Planted\n\n## Same\n\n## Same\n\n"
            "[first](#same) [second](#same-1) [third](#same-2)\n"
            "[schema](SKILL_SCHEMA.md#keys) [up](../MISSING.md) [readme](../README.md#validation)\n",
            encoding="utf-8",
            newline="\n",
        )
        returncode, payload = run_verifier(self.root, "--metadata")
        self.assertEqual(
            [item[:3] for item in problem_lines(payload, "LINK_")],
            [("LINK_ANCHOR", "docs/planted.md", 7), ("LINK_MISSING", "docs/planted.md", 8)],
        )


def set_description(root: Path, name: str, description: str) -> None:
    skill = root / "skills" / name / "SKILL.md"
    lines = skill.read_text(encoding="utf-8").split("\n")
    assert lines[2].startswith("description: "), lines[2]
    lines[2] = "description: " + description
    skill.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def description_of_length(length: int) -> str:
    text = "Use when a budget test needs a description of an exact length. "
    return text + "x" * (length - len(text))


class BudgetTest(unittest.TestCase):
    """Descriptions, their total, and body token estimates are capped."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="verify-budgets-")
        self.root = copy_package(Path(self.temp.name) / "package")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_the_package_is_within_budget(self) -> None:
        returncode, payload = run_verifier(self.root)
        self.assertEqual(returncode, 0, payload["problems"])
        budgets = payload["budgets"]
        self.assertEqual(sorted(budgets["skills"]), payload["skills"])
        self.assertLessEqual(budgets["description_total"], budgets["description_total_cap"])
        for name, row in budgets["skills"].items():
            with self.subTest(skill=name):
                self.assertLessEqual(row["description_characters"], budgets["description_cap"])
                self.assertLessEqual(row["body_estimated_tokens"], row["body_token_cap"])

    def test_a_301_character_description_fails(self) -> None:
        set_description(self.root, "game-debug", description_of_length(301))
        returncode, payload = run_verifier(self.root)
        self.assertEqual(returncode, 1)
        self.assertEqual(
            [(item["code"], item["path"], item["line"]) for item in payload["problems"]],
            [("DESCRIPTION_BUDGET", "skills/game-debug/SKILL.md", 3)],
        )
        set_description(self.root, "game-debug", description_of_length(300))
        returncode, payload = run_verifier(self.root)
        self.assertEqual(payload["problems"], [])
        self.assertEqual(returncode, 0)

    def test_the_suite_total_and_body_caps(self) -> None:
        _, payload = run_verifier(self.root)
        budgets = payload["budgets"]
        room = budgets["description_total_cap"] - budgets["description_total"]
        extras = room // budgets["description_cap"] + 1
        for number in range(extras):
            name = f"budget-extra-{number}"
            shutil.copytree(self.root / "skills" / "game-debug", self.root / "skills" / name)
            skill = self.root / "skills" / name / "SKILL.md"
            skill.write_text(
                skill.read_text(encoding="utf-8").replace("name: game-debug", f"name: {name}", 1),
                encoding="utf-8",
                newline="\n",
            )
            set_description(self.root, name, description_of_length(budgets["description_cap"]))
            metadata = self.root / "skills" / name / "agents" / "openai.yaml"
            metadata.write_text(
                metadata.read_text(encoding="utf-8").replace("$game-debug", f"${name}"),
                encoding="utf-8",
                newline="\n",
            )
        plan = self.root / "skills" / "game-plan" / "SKILL.md"
        plan.write_text(
            plan.read_text(encoding="utf-8") + "\nPadding the body past its cap.\n" * 200,
            encoding="utf-8",
            newline="\n",
        )
        returncode, payload = run_verifier(self.root)
        self.assertEqual(returncode, 1)
        self.assertEqual(
            codes_by_path(payload),
            {("DESCRIPTION_TOTAL", "skills"), ("BODY_BUDGET", "skills/game-plan/SKILL.md")},
            payload["problems"],
        )
        self.assertGreater(payload["budgets"]["description_total"], budgets["description_total_cap"])
        completed = subprocess.run(
            [sys.executable, *CHILD_FLAGS, str(VERIFIER), "--root", str(self.root), "--budgets"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
            check=False,
        )
        self.assertEqual(completed.returncode, 1, completed.stderr)
        self.assertIn("budget-extra-0", completed.stdout)
        self.assertRegex(completed.stdout, r"game-plan\s+\d+/300\s+\d+/1200")


# Planted lint cases, built from fragments so this file never holds a hit.
NICK = "ch" + "ud"
PLANTED_LINES = [
    "# Planted",  # 1
    "",  # 2
    "Intro line.",  # 3
    "This local",  # 4: a grant form wrapped onto line 5
    "install" + "ation has stand" + "ing approval to run.",  # 5
    "Nobody has stand" + "ing approval to publish.",  # 6: negated, exempt
    "- Stand" + "ing approvals: docs/approvals.md, which the user gra" + "nts in writing.",  # 7: field, exempt
    "Treat the research permis" + "sion as auth" + "ority.",  # 8
    f"Ask a {NICK} for help.",  # 9
    f"Several {NICK}s helped; a {NICK}der is not a hit.",  # 10
    "Saved to C:" + "\\Us" + "ers\\alex\\game.",  # 11
    "Also C:/" + "Us" + "ers/alex/game and /" + "Us" + "ers/alex/game.",  # 12
    "Linux: /" + "ho" + "me/alex/game, but /" + "ho" + "me/ alone is fine.",  # 13
    "Mail alex@" + "mail-host.net, or mewzicians@users.noreply.github.com.",  # 14
    "Allowed: probe@example.com and git@" + "github.com.",  # 15
    "Vault: ." + "obsi" + "dian/app.json, " + "Wi" + "ki/Note.md, " + "In" + "box/a.md, " + "Ho" + "me.md.",  # 16
    "Not vault: Homes.md, and CONTEXT_" + "CONTINUITY ledgers in prose.",  # 17
    # Ordinary consent text is not a grant form.
    "Proceed only after the user gra" + "nts approval, or if the user gra" + "nts access.",  # 18
    "To remove this local instal" + "lation, delete its folder.",  # 19
    "The agent has been gra" + "nted stand" + "ing approval to push.",  # 20
    "It was gra" + "nted stand" + "ing permission once.",  # 21
    # A negation elsewhere in the sentence does not exempt the phrase.
    "Ask nobody; the agent has stand" + "ing approval to push.",  # 22
    "Nobody has stand" + "ing approval, and this skill never gra" + "nts stand" + "ing approval.",  # 23: exempt
    "Icons: sprite@2x.png and icon@1.5x.webp; remote git@" + "gitlab.com:team/repo.git.",  # 24
    "CI: /" + "ho" + "me/runner/work, C:" + "\\Us" + "ers\\Public\\Desktop, C:" + "\\Us"
    + "ers\\Default\\AppData, C:" + "\\Us" + "ers\\All Users\\x, and C:" + "\\Us" + "ers\\runneradmin\\y.",  # 25
    "Git Bash: /c/" + "Us" + "ers/alex/game; WSL: /mnt/c/" + "Us" + "ers/alex/game.",  # 26
    "Bare: /" + "Us" + "ers/alex and /" + "ho" + "me/alex",  # 27
    "A GitHub wiki page: " + "Ho" + "me.md.",  # 28
    # Normalization: full-width and lookalike letters, and a zero-width space.
    "Full-width and lookalike: \uff23" + "hud, \u0421" + "hud, and c\u200b" + "hud.",  # 29
    "You have stand" + "ing appro" + "val; the user gr\u0430nts stand" + "ing permis" + "sion.",  # 30
    # Conditions and placeholders are not hits.
    "If the user has stand" + "ing appro" + "val, go on; ask whether it holds stand" + "ing permis" + "sion.",  # 31
    "Placeholders: C:" + "\\Us" + "ers\\%USERNAME%\\x, /" + "ho" + "me/user/x, /" + "Us" + "ers/Shared/x; "
    + "ssh deploy@" + "build.internal.net.",  # 32
]
# Weak vault markers: one kind alone is ordinary, two kinds in a file are a vault.
PLANTED_CLEAN = [
    "See the " + "wi" + "ki/ folder of your engine, and its " + "wi" + "ki/ index.",  # 1
    "Use ." + "obsi" + "dian-theme files.",  # 2
]
PLANTED_PAIR = "Notes go to " + "wi" + "ki/ and " + "in" + "box/."


class NeutralityLintTest(unittest.TestCase):
    """The default gate and --lint both report planted lint cases."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="verify-lint-")
        self.root = copy_package(Path(self.temp.name) / "package")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def lint(self) -> list[dict]:
        returncode, payload = run_verifier(self.root, "--lint")
        self.assertEqual(returncode, 1 if payload["problems"] else 0)
        return payload["problems"]

    def test_the_package_holds_no_hits(self) -> None:
        self.assertEqual(self.lint(), [])

    def test_planted_cases(self) -> None:
        doc = "docs/planted.md"
        ledger = "CONTEXT_" + "CONTINUITY.task.md"
        vault_note = "Wi" + "ki/note.md"
        wiki_home = "Ho" + "me.md"
        clean = "docs/planted-clean.md"
        pair = "docs/planted-pair.md"
        planted = (
            (doc, "\n".join(PLANTED_LINES) + "\n"),
            (clean, "\n".join(PLANTED_CLEAN) + "\n"),
            (pair, PLANTED_PAIR + "\n"),
            (ledger, "ledger\n"),
            (vault_note, "note\n"),
            (wiki_home, "Welcome.\n"),
        )
        for name, text in planted:
            (self.root / name).parent.mkdir(parents=True, exist_ok=True)
            (self.root / name).write_text(text, encoding="utf-8", newline="\n")
        problems = [item for item in self.lint() if item["path"] in {name for name, _ in planted}]
        self.assertEqual(
            {(item["code"], item["path"], item["line"]) for item in problems},
            {
                ("LINT_GRANT_FORM", doc, 4),
                ("LINT_GRANT_FORM", doc, 8),
                ("LINT_AGENT_NICKNAME", doc, 9),
                ("LINT_AGENT_NICKNAME", doc, 10),
                ("LINT_USER_PATH", doc, 11),
                ("LINT_USER_PATH", doc, 12),
                ("LINT_USER_PATH", doc, 13),
                ("LINT_PERSONAL_EMAIL", doc, 14),
                ("LINT_VAULT_NAME", doc, 16),
                ("LINT_GRANT_FORM", doc, 20),
                ("LINT_GRANT_FORM", doc, 21),
                ("LINT_GRANT_FORM", doc, 22),
                ("LINT_USER_PATH", doc, 26),
                ("LINT_USER_PATH", doc, 27),
                ("LINT_AGENT_NICKNAME", doc, 29),
                ("LINT_GRANT_FORM", doc, 30),
                ("LINT_VAULT_NAME", pair, 1),
                ("LINT_CONTINUITY_LEDGER", ledger, None),
                ("LINT_VAULT_NAME", vault_note, None),
            },
        )
        wrapped = next(item for item in problems if item["line"] == 4)
        self.assertIn("lines 4-5", wrapped["message"])
        returncode, payload = run_verifier(self.root)
        self.assertEqual(returncode, 1)
        self.assertEqual(
            [item for item in payload["problems"] if item["code"].startswith("LINT_")],
            problems,
        )


# Fragments for the rule cases below, so this file never holds a hit.
ST = "stand" + "ing"
APPROVAL = "appro" + "val"
PERMISSION = "permis" + "sion"
GRANTS = "gra" + "nts"
GRANTED = "gra" + "nted"
USERS = "Us" + "ers"
HOME = "ho" + "me"


def load_verifier():
    """Import tools/verify_package.py by path, without writing bytecode."""
    spec = importlib.util.spec_from_file_location("verify_package_under_test", VERIFIER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class LintRulesTest(unittest.TestCase):
    """Each lint rule's hits and passes, checked through lint_text."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.verifier = load_verifier()

    def codes(self, text: str) -> set[str]:
        problems: list = []
        self.verifier.lint_text("docs/case.md", text, problems)
        return {problem.code for problem in problems}

    def assert_cases(self, code: str, hits: dict[str, str], passes: dict[str, str]) -> None:
        for label, text in hits.items():
            with self.subTest(hit=label):
                self.assertIn(code, self.codes(text), text)
        for label, text in passes.items():
            with self.subTest(passes=label):
                self.assertEqual(self.codes(text), set(), text)

    def test_grant_forms(self) -> None:
        has = f"has {ST} {APPROVAL}"
        hits = {
            "has": f"This skill {has} to push.",
            "have": f"You have {ST} {APPROVAL} to edit the guide.",
            "holds": f"This skill holds {ST} {APPROVAL} for ledger writes.",
            "carries": f"The agent carries {ST} {PERMISSION} to edit.",
            "assumes": f"You may assume {ST} {APPROVAL} for continuity.",
            "is granted": f"{ST.title()} {PERMISSION} is {GRANTED} to edit the guide.",
            "gives": f"The profile gives the agent {ST} {APPROVAL}.",
            "grants": f"The user {GRANTS} {ST} {PERMISSION} to edit.",
            "upper case": f"The user {GRANTS} {ST} {PERMISSION} to edit.".upper(),
            "wrapped": f"The user {GRANTS}\n   {ST} {PERMISSION} to edit.",
            "tab": f"The agent has\t{ST} {APPROVAL}.",
            "hyphen": f"The user {GRANTS} {ST}-{PERMISSION}.",
            "bold": f"The user **{GRANTS}** {ST} {PERMISSION}.",
            "emphasis": f"The user {GRANTS} *{ST}* {PERMISSION}.",
            "code span": f"The agent `{has}`.",
            "link": f"The user [{GRANTS} {ST} {APPROVAL}](x.md).",
            "no-break space": f"The user {GRANTS}\u00a0{ST} {PERMISSION}.",
            "zero-width space": f"The user gr\u200bants {ST} {PERMISSION}.",
            "lookalike letter": f"The user gr\u0430nts {ST} {PERMISSION}.",
            "pre-approved": "This skill is pre-" + "appro" + "ved to write ledgers.",
            "without asking": "Edit the guide with" + "out ask" + f"ing for {APPROVAL}.",
            "field bypass": f"- {ST.title()} {APPROVAL}s: this skill {GRANTS} {ST} {APPROVAL} for every push.",
            "conjunction ends a negation": f"The agent asks no questions and {has} to push.",
            "negator too far": "With" + f"out exception the agent {has}.",
            "clause break": f"Do not stop; the user {has}.",
            "because": f"Don't ask because the user {has}.",
            "not only": f"Not only does the user grant {ST} {APPROVAL}, it lasts.",
            "quoted": f"Write 'the user {GRANTS} {ST} {PERMISSION}' in every skill.",
            "written assertion": f"The user has {GRANTED} {ST} {APPROVAL} in writing.",
        }
        passes = {
            "consent": f"Proceed after the user {GRANTS} approval.",
            "if": f"If the user {has}, continue.",
            "whether": f"Ask whether the user {has} for this.",
            "unless": f"Stop unless the user {has}.",
            "written condition": f"Continue only once the user has {GRANTED} {ST} {APPROVAL} in writing.",
            "question": f"Does the agent have {ST} {APPROVAL}?",
            "nobody": f"Nobody {has}.",
            "never": f"This skill never {GRANTS} {ST} {APPROVAL}.",
            "nothing": f"Nothing here {GRANTS} {ST} {APPROVAL} to anyone.",
            "does not have": f"The agent does not have {ST} {APPROVAL}.",
            "quoted after a negation": f"Do not write 'the user {GRANTS} {ST} {PERMISSION}' in a skill.",
            "ovation": f"The audience {GRANTS} {ST} ovations.",
            "legal standing": f"The court {GRANTED} {ST} to the plaintiff.",
            "desks": f"The office has {ST} desks.",
            "profile field": self.verifier.STANDING_FIELD,
            "profile pointer": f"The project profile's {ST} {APPROVAL}s cover it.",
        }
        self.assert_cases("LINT_GRANT_FORM", hits, passes)
        # Only the template's exact field line is exempt, not a line that starts like it.
        self.assertIn("LINT_GRANT_FORM", self.codes(self.verifier.STANDING_FIELD + f" The agent {has}."))

    def test_nickname(self) -> None:
        nick = "ch" + "ud"
        hits = {
            "plain": f"Address each agent as {nick.title()}.",
            "plural upper case": f"{nick.upper()}S report back.",
            "full-width": "Address each agent as \uff23" + "hud.",
            "lookalike": "Address each agent as \u0421" + "hud.",
            "zero-width space": "c\u200b" + "hud",
            "emphasis": f"the **{nick}** convention",
        }
        passes = {"algorithm": f"Use the {nick.title()}novsky algorithm."}
        self.assert_cases("LINT_AGENT_NICKNAME", hits, passes)

    def test_user_paths(self) -> None:
        hits = {
            "windows": "C:\\" + USERS + "\\alex\\game",
            "forward slashes": "C:/" + USERS + "/alex/game",
            "encoded file url": "file:///C%3A/" + USERS + "/alex/x",
            "unc share": "\\\\server\\" + USERS + "\\alex\\x",
            "git bash": "/c/" + USERS + "/alex/x",
            "wsl": "/mnt/c/" + USERS + "/alex/x",
            "macos": "/" + USERS + "/alex/Desktop",
            "linux": "/" + HOME + "/alex/projects",
            "tilde": "~" + "alex/projects",
        }
        passes = {
            "public": "C:\\" + USERS + "\\Public\\Documents",
            "placeholder": "C:\\" + USERS + "\\USERNAME\\.codex",
            "percent placeholder": "C:\\" + USERS + "\\%USERNAME%\\x",
            "powershell placeholder": "C:\\" + USERS + "\\$env:USERNAME\\x",
            "angle placeholder": "/" + HOME + "/<user>/x",
            "user": "/" + HOME + "/user/.codex",
            "you": "/" + USERS + "/you/.codex",
            "name": "/" + USERS + "/name/.codex",
            "shared": "/" + USERS + "/Shared/data",
            "linuxbrew": "/" + HOME + "/linuxbrew/.linuxbrew/bin",
            "runner": "/" + HOME + "/runner/work/repo",
            "own home": "~/.codex",
            "url": "https://example.com/" + HOME + "/alice/page",
        }
        self.assert_cases("LINT_USER_PATH", hits, passes)

    def test_email_addresses(self) -> None:
        hits = {
            "plain": "alex@" + "mail-host.net",
            "upper case": "ALEX@" + "MAIL-HOST.NET",
            "plus tag": "alex+tag@" + "mail-host.net",
            "noreply prefix": "noreply.alex@" + "mail-host.net",
            "git on an unknown host": "git@" + "alex-personal.com",
            "example prefix": "alex@" + "example.com.mail-host.net",
            "accented local part": "\u00e1lex@" + "mail-host.net",
            "accented domain": "alex@" + "b\u00fccher.de",
            "full-width at": "alex\uff20" + "mail-host.net",
        }
        passes = {
            "example": "dev@" + "example.com",
            "noreply": "12345+someone@" + "users.noreply.github.com",
            "web flow": "noreply@" + "github.com",
            "git remote": "git@" + "github.com:owner/repo.git",
            "ssh host": "ssh deploy@" + "build.internal.net",
            "ssh option": "ssh -p 2222 deploy@" + "build-host.net",
            "reserved top-level domain": "uses: actions/checkout@" + "v4.example",
            "scaled asset": "icon@" + "2x.png",
            "version pin": "package@" + "1.0.0",
        }
        self.assert_cases("LINT_PERSONAL_EMAIL", hits, passes)

    def test_vault_names(self) -> None:
        hits = {
            "settings folder": "Store notes in ." + "obsi" + "dian/ only.",
            "capitalized wiki": "See " + "Wi" + "ki/Note.md.",
            "backslash": "Wi" + "ki\\Operations\\Public Boundary.md",
            "two weak markers": "store in " + "wi" + "ki/ and " + "in" + "box/",
        }
        passes = {
            "theme file": "Use ." + "obsi" + "dian-theme files.",
            "mineral": "Obsi" + "dian is a mineral.",
            "inbox alone": "Check the " + "In" + "box/ for messages.",
            "wiki alone": "See the " + "wi" + "ki/ folder of your engine docs.",
            "home page": "Ho" + "me.md in the docs.",
        }
        self.assert_cases("LINT_VAULT_NAME", hits, passes)
        inbox, wiki, lower_wiki = "docs/" + "In" + "box/a.md", "Wi" + "ki/b.md", "notes/" + "wi" + "ki/c.md"
        self.assertEqual(self.verifier.vault_paths([inbox]), set())
        self.assertEqual(self.verifier.vault_paths([inbox, wiki]), {inbox, wiki})
        self.assertEqual(self.verifier.vault_paths([inbox, lower_wiki]), {inbox, lower_wiki})

    def test_forbidden_terms_are_normalized(self) -> None:
        for label, text in {
            "lookalike": "Off\u0456ce" + "Wars",
            "full-width": "\uff2f" + "ffice" + "Wars",
            "zero-width space": "Office\u200b" + "Wars",
        }.items():
            with self.subTest(label):
                problems: list = []
                self.verifier.check_forbidden("docs/x.md", text.encode("utf-8"), problems)
                self.assertEqual([problem.code for problem in problems], ["FORBIDDEN_TERM"])


@unittest.skipUnless(shutil.which("git"), "git is not installed")
class GitInventoryTest(unittest.TestCase):
    """A git checkout: ignored files are skipped, untracked files are checked."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="verify-package-git-")
        self.root = copy_package(Path(self.temp.name) / "package")
        for arguments in (["init", "-q"], ["add", "-A"]):
            subprocess.run(
                ["git", "-c", "core.autocrlf=false", "-C", str(self.root), *arguments],
                capture_output=True,
                check=True,
            )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_ignored_debris_is_skipped_and_untracked_debris_is_reported(self) -> None:
        cache = self.root / "skills" / "game-implement" / "scripts" / "__pycache__"
        cache.mkdir(parents=True)
        (cache / "helper.cpython-313.pyc").write_bytes(b"\x00\x01")
        (self.root / "skills" / "game-plan" / ".DS_Store").write_bytes(b"\x00\x00\x00\x01Bud1")
        returncode, payload = run_verifier(self.root)
        self.assertEqual(payload["inventory"], "git")
        self.assertEqual(codes_by_path(payload), {("DEBRIS", "skills/game-plan/.DS_Store")})
        self.assertEqual(returncode, 1)

    @unittest.skipUnless(SYMLINKS, "symbolic links need extra privileges here")
    def test_tracked_dangling_symlinks_are_reported(self) -> None:
        plant_dangling_symlinks(self.root)
        # core.symlinks=true makes Git for Windows record the links as links.
        subprocess.run(
            ["git", "-c", "core.autocrlf=false", "-c", "core.symlinks=true", "-C", str(self.root), "add", "-A"],
            capture_output=True,
            check=True,
        )
        tracked = subprocess.run(
            ["git", "-C", str(self.root), "ls-files", "--", DANGLING],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        self.assertEqual(tracked.stdout.strip(), DANGLING)
        returncode, payload = run_verifier(self.root)
        self.assertEqual(payload["inventory"], "git")
        self.assertEqual(codes_by_path(payload), BROKEN_LINK_PROBLEMS, payload["problems"])
        self.assertEqual(returncode, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
