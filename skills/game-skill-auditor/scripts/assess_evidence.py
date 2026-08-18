#!/usr/bin/env python3
"""Validate a skill-audit evidence manifest and calibrate readiness."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


READINESS_LEVELS = [
    "Structurally Valid",
    "Behaviorally Tested",
    "Adversarially Tested",
    "Independently Cross-Checked",
    "User Validated",
]
STATUS_LABELS = ["Not Validated", *READINESS_LEVELS]
EVIDENCE_COMPLETENESS_LABELS = [
    "No Complete Evidence Gate",
    "Structural Evidence Complete",
    "Behavioral Evidence Complete",
    "Adversarial Evidence Complete",
    "Independent Review Evidence Complete",
    "User Validation Evidence Complete",
]
BEHAVIOR_CASE_MINIMUMS = {
    "canonical": 3,
    "paraphrase": 2,
    "edge": 1,
    "negative-control": 2,
    "regression": 1,
    "metamorphic": 3,
}
MUTATION_CATEGORIES = {"trigger", "context", "boundary", "evidence", "metadata"}
SEVERITIES = {"critical", "high", "medium", "low"}
MATERIAL_SEVERITIES = {"critical", "high"}
STRUCTURAL_TEST_IDS = {"official-validator", "bundled-audit"}
BUNDLED_OFFICIAL_VALIDATOR_SHA256 = (
    "6cc9dc3199c935916cf6f73fcbbbb0e3bb1b58c8f5109fefa499978908164f51"
)
CONTRACT_CLAUSES = {
    "trigger",
    "read",
    "decide",
    "do",
    "do-not",
    "evidence",
    "stop",
}
PROVENANCE_CATEGORIES = {
    "user",
    "higher-level",
    "project",
    "target",
    "observed",
    "inferred",
}
REQUIRED_ROLES = {"contract", "test-design", "execution", "adversarial-review"}
EXTERNAL_ROLES = {"contract", "test-design", "judgment", "adversarial-review"}
ALLOWED_ROLES = REQUIRED_ROLES | {"judgment"}
JUDGMENT_LENSES = {"contract-criteria", "adversarial-user"}
PROVENANCE_FIELDS = {
    "source",
    "actor",
    "artifact",
    "artifact_sha256",
    "created_at",
    "custodian",
}
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
PLACEHOLDER_PATTERN = re.compile(
    r"(?:^\W*replace\W*$|"
    r"\breplace(?:[\W_]+(?:with|me|this))\b|"
    r"\b(?:placeholder|todo|tbd|unset)\b)",
    re.IGNORECASE,
)
SKILL_NAME_PATTERN = re.compile(
    r"\A---\r?\n.*?^name:\s*(.+?)\s*$.*?^---\s*$",
    re.MULTILINE | re.DOTALL,
)


def normalized(value: object) -> str:
    return value.strip().casefold() if isinstance(value, str) else ""


def normalized_behavior_case(value: object) -> str:
    case_type = normalized(value)
    return "edge" if case_type == "boundary" else case_type


def normalized_string_set(value: object) -> set[str] | None:
    if not isinstance(value, list) or not all(
        isinstance(item, str) for item in value
    ):
        return None
    return {normalized(item) for item in value}


def normalized_path_set(value: object) -> set[str] | None:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        return None
    return {item.strip().replace("\\", "/") for item in value}


def substantive(value: object, minimum: int = 3) -> bool:
    return isinstance(value, str) and len(value.strip()) >= minimum


def resolved_identity(value: object, minimum: int = 3) -> bool:
    return substantive(value, minimum) and PLACEHOLDER_PATTERN.search(
        str(value).strip()
    ) is None


def parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def timestamp_not_future(value: object) -> bool:
    parsed = parse_timestamp(value)
    return (
        parsed is not None
        and parsed <= datetime.now(timezone.utc) + timedelta(minutes=5)
    )


def timestamp_at_or_after(value: object, floor: datetime | None) -> bool:
    parsed = parse_timestamp(value)
    return parsed is not None and floor is not None and parsed >= floor


def provenance_time(value: object) -> datetime | None:
    if not isinstance(value, dict):
        return None
    return parse_timestamp(value.get("created_at"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package_digest(path: Path) -> str:
    digest = hashlib.sha256()
    if path.is_file():
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        return digest.hexdigest()
    for item in sorted(
        (candidate for candidate in path.rglob("*") if candidate.is_file()),
        key=lambda candidate: candidate.relative_to(path).as_posix(),
    ):
        digest.update(item.relative_to(path).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(item.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def package_files(path: Path) -> dict[str, str]:
    return {
        item.relative_to(path).as_posix(): sha256_file(item)
        for item in path.rglob("*")
        if item.is_file()
    }


def package_has_lineage(target: Path, mutated: Path) -> bool:
    target_files = package_files(target)
    mutated_files = package_files(mutated)
    if not target_files or not mutated_files:
        return False
    unchanged = sum(
        mutated_files.get(relative) == digest
        for relative, digest in target_files.items()
    )
    allowed_changes = max(1, len(target_files) // 4)
    return (
        skill_package_name(target) == skill_package_name(mutated)
        and unchanged >= len(target_files) - allowed_changes
        and len(mutated_files) >= len(target_files) - allowed_changes
    )


def resolve_file(reference: object, root: Path | None) -> Path | None:
    resolved = resolve_path(reference, root)
    return resolved if resolved is not None and resolved.is_file() else None


def resolve_path(reference: object, root: Path | None) -> Path | None:
    if not substantive(reference) or root is None:
        return None
    candidate = Path(str(reference).strip())
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        resolved = candidate.resolve()
    except OSError:
        return None
    return resolved if resolved.exists() else None


def valid_hashed_file(
    reference: object,
    expected_hash: object,
    root: Path | None,
) -> Path | None:
    path = resolve_file(reference, root)
    digest = normalized(expected_hash)
    if path is None or not SHA256_PATTERN.fullmatch(digest):
        return None
    try:
        return path if sha256_file(path) == digest else None
    except OSError:
        return None


def valid_package_artifact(
    reference: object,
    expected_hash: object,
    root: Path | None,
) -> Path | None:
    path = resolve_path(reference, root)
    digest = normalized(expected_hash)
    if (
        path is None
        or not path.is_dir()
        or not (path / "SKILL.md").is_file()
        or not SHA256_PATTERN.fullmatch(digest)
    ):
        return None
    try:
        return path if package_digest(path) == digest else None
    except OSError:
        return None


def skill_package_name(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        text = (path / "SKILL.md").read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return ""
    match = SKILL_NAME_PATTERN.search(text)
    if not match:
        return ""
    value = match.group(1).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1]
    return normalized(value)


def valid_provenance(value: object, evidence_root: Path | None) -> bool:
    if not isinstance(value, dict) or not PROVENANCE_FIELDS.issubset(value):
        return False
    if not all(
        resolved_identity(value.get(field))
        for field in ("source", "actor", "custodian")
    ):
        return False
    if not timestamp_not_future(value.get("created_at")):
        return False
    return (
        valid_hashed_file(
            value.get("artifact"),
            value.get("artifact_sha256"),
            evidence_root,
        )
        is not None
    )


def provenance_artifact(
    value: object,
    evidence_root: Path | None,
) -> Path | None:
    if not valid_provenance(value, evidence_root):
        return None
    return resolve_file(value.get("artifact"), evidence_root)


def completed_pass(item: dict) -> bool:
    return normalized(item.get("status")) == "completed" and normalized(
        item.get("result")
    ) == "pass"


def valid_role(
    role: dict,
    evidence_root: Path | None,
    target_digest: str,
    contract_frozen_at: datetime | None = None,
    *,
    require_external_output: bool = True,
) -> bool:
    if not all(
        resolved_identity(role.get(field))
        for field in ("role", "actor", "context_id", "prompt_ref")
    ):
        return False
    if not isinstance(role.get("governed_by_target"), bool):
        return False
    if (
        valid_hashed_file(
            role.get("prompt_ref"),
            role.get("prompt_sha256"),
            evidence_root,
        )
        is None
    ):
        return False
    attestation = role.get("attestation")
    attestation_path = provenance_artifact(attestation, evidence_root)
    attestation_payload = load_json_object(attestation_path)
    role_name = normalized(role.get("role"))
    actor = normalized(role.get("actor"))
    context_id = normalized(role.get("context_id"))
    prompt_sha256 = normalized(role.get("prompt_sha256"))
    review_lens = normalized(role.get("review_lens"))
    if role_name == "judgment" and review_lens not in JUDGMENT_LENSES:
        return False
    if not (
        attestation_path is not None
        and isinstance(attestation_payload, dict)
        and normalized(attestation.get("actor")) == actor
        and normalized(attestation_payload.get("kind")) == "role-attestation"
        and normalized(attestation_payload.get("role")) == role_name
        and normalized(attestation_payload.get("actor")) == actor
        and normalized(attestation_payload.get("context_id")) == context_id
        and normalized(attestation_payload.get("prompt_sha256"))
        == prompt_sha256
        and normalized(attestation_payload.get("target_sha256"))
        == target_digest
        and attestation_payload.get("governed_by_target")
        is role.get("governed_by_target")
        and normalized(attestation_payload.get("review_lens")) == review_lens
        and timestamp_not_future(attestation_payload.get("created_at"))
        and (
            contract_frozen_at is None
            or timestamp_at_or_after(
                attestation_payload.get("created_at"),
                contract_frozen_at,
            )
        )
        and parse_timestamp(attestation_payload.get("created_at"))
        <= provenance_time(attestation)
    ):
        return False
    if require_external_output and role_name in EXTERNAL_ROLES:
        output = role.get("output")
        output_path = provenance_artifact(output, evidence_root)
        output_payload = load_json_object(output_path)
        return (
            output_path is not None
            and isinstance(output_payload, dict)
            and normalized(output.get("actor")) == actor
            and normalized(output_payload.get("kind")) == "role-output"
            and normalized(output_payload.get("role")) == role_name
            and normalized(output_payload.get("actor")) == actor
            and normalized(output_payload.get("context_id")) == context_id
            and normalized(output_payload.get("target_sha256")) == target_digest
            and normalized(output_payload.get("status")) == "completed"
            and timestamp_not_future(output_payload.get("created_at"))
            and (
                contract_frozen_at is None
                or timestamp_at_or_after(
                    output_payload.get("created_at"),
                    contract_frozen_at,
                )
            )
            and parse_timestamp(output_payload.get("created_at"))
            <= provenance_time(output)
        )
    return True


def valid_behavior_prompt(item: dict, evidence_root: Path | None) -> bool:
    return (
        valid_hashed_file(
            item.get("prompt_ref"),
            item.get("prompt_sha256"),
            evidence_root,
        )
        is not None
    )


def valid_behavior_result(
    item: dict,
    evidence_root: Path | None,
    target_digest: str,
    target_skill_name: str,
    contract_frozen_at: datetime | None,
    provenance_field: str = "provenance",
) -> bool:
    output_path = valid_hashed_file(
        item.get("output_ref"),
        item.get("output_sha256"),
        evidence_root,
    )
    result_provenance = item.get(provenance_field)
    result_path = provenance_artifact(result_provenance, evidence_root)
    payload = load_json_object(result_path)
    requirement_ids = normalized_string_set(item.get("requirement_ids"))
    payload_requirement_ids = normalized_string_set(
        payload.get("requirement_ids") if isinstance(payload, dict) else None
    )
    executor_actor = normalized(
        payload.get("executor_actor") if isinstance(payload, dict) else None
    )
    judge_actor = normalized(
        payload.get("judge_actor") if isinstance(payload, dict) else None
    )
    executor_context_id = normalized(
        payload.get("executor_context_id")
        if isinstance(payload, dict)
        else None
    )
    judge_context_id = normalized(
        payload.get("judge_context_id")
        if isinstance(payload, dict)
        else None
    )
    criterion_results = (
        payload.get("criterion_results") if isinstance(payload, dict) else None
    )
    criterion_ids = (
        [normalized(value.get("requirement_id")) for value in criterion_results]
        if isinstance(criterion_results, list)
        and all(isinstance(value, dict) for value in criterion_results)
        else []
    )
    criterion_results_valid = (
        isinstance(criterion_results, list)
        and bool(criterion_results)
        and len(criterion_ids) == len(set(criterion_ids))
        and set(criterion_ids) == requirement_ids
        and all(
            normalized(value.get("result")) == "pass"
            and substantive(value.get("observation"), 20)
            and PLACEHOLDER_PATTERN.search(
                str(value.get("observation")).strip()
            )
            is None
            for value in criterion_results
        )
    )
    activation = item.get("activation")
    payload_activation = (
        payload.get("activation") if isinstance(payload, dict) else None
    )
    activation_valid = (
        isinstance(activation, dict)
        and isinstance(payload_activation, dict)
        and normalized(activation.get("invocation_mode")) == "auto-dispatch"
        and normalized(payload_activation.get("invocation_mode"))
        == "auto-dispatch"
        and isinstance(activation.get("expected"), bool)
        and isinstance(activation.get("observed"), bool)
        and activation.get("observed") is activation.get("expected")
        and payload_activation.get("expected") is activation.get("expected")
        and payload_activation.get("observed") is activation.get("observed")
        and normalized(payload_activation.get("selected_skill"))
        == normalized(activation.get("selected_skill"))
        and (
            (
                activation.get("expected") is True
                and normalized(activation.get("selected_skill"))
                == target_skill_name
            )
            or (
                activation.get("expected") is False
                and normalized(activation.get("selected_skill"))
                != target_skill_name
            )
        )
    )
    return (
        output_path is not None
        and isinstance(payload, dict)
        and normalized(payload.get("kind")) == "behavioral-result"
        and normalized(payload.get("test_id")) == normalized(item.get("id"))
        and normalized(payload.get("target_sha256")) == target_digest
        and normalized(payload.get("prompt_sha256"))
        == normalized(item.get("prompt_sha256"))
        and normalized(payload.get("output_sha256"))
        == normalized(item.get("output_sha256"))
        and requirement_ids is not None
        and payload_requirement_ids == requirement_ids
        and normalized(payload.get("result")) == "pass"
        and resolved_identity(executor_actor)
        and resolved_identity(judge_actor)
        and resolved_identity(executor_context_id)
        and resolved_identity(judge_context_id)
        and SHA256_PATTERN.fullmatch(
            normalized(payload.get("executor_prompt_sha256"))
        )
        is not None
        and SHA256_PATTERN.fullmatch(
            normalized(payload.get("judge_prompt_sha256"))
        )
        is not None
        and executor_actor != judge_actor
        and normalized(payload.get("review_lens")) in JUDGMENT_LENSES
        and substantive(payload.get("rationale"), 40)
        and PLACEHOLDER_PATTERN.search(str(payload.get("rationale")).strip())
        is None
        and criterion_results_valid
        and activation_valid
        and normalized(
            result_provenance.get("actor")
            if isinstance(result_provenance, dict)
            else None
        )
        == judge_actor
        and timestamp_not_future(payload.get("created_at"))
        and timestamp_at_or_after(
            payload.get("created_at"),
            contract_frozen_at,
        )
        and parse_timestamp(payload.get("created_at"))
        <= provenance_time(result_provenance)
    )


def behavior_judge_actor(
    item: dict,
    provenance_field: str,
    evidence_root: Path | None,
) -> str:
    payload = load_json_object(
        provenance_artifact(item.get(provenance_field), evidence_root)
    )
    return normalized(
        payload.get("judge_actor") if isinstance(payload, dict) else None
    )


def behavior_judge_lens(
    item: dict,
    provenance_field: str,
    evidence_root: Path | None,
) -> str:
    payload = load_json_object(
        provenance_artifact(item.get(provenance_field), evidence_root)
    )
    return normalized(
        payload.get("review_lens") if isinstance(payload, dict) else None
    )


def valid_mutation_result(
    item: dict,
    evidence_root: Path | None,
    target_path: Path,
    target_digest: str,
    contract_frozen_at: datetime | None = None,
) -> bool:
    mutated_package = valid_package_artifact(
        item.get("mutated_target"),
        item.get("mutated_sha256"),
        evidence_root,
    )
    output_path = valid_hashed_file(
        item.get("output_ref"),
        item.get("output_sha256"),
        evidence_root,
    )
    result_path = provenance_artifact(item.get("provenance"), evidence_root)
    payload = load_json_object(result_path)
    requirement_ids = normalized_string_set(item.get("requirement_ids"))
    payload_requirement_ids = normalized_string_set(
        payload.get("requirement_ids") if isinstance(payload, dict) else None
    )
    executor_actor = normalized(
        payload.get("executor_actor") if isinstance(payload, dict) else None
    )
    judge_actor = normalized(
        payload.get("judge_actor") if isinstance(payload, dict) else None
    )
    executor_context_id = normalized(
        payload.get("executor_context_id")
        if isinstance(payload, dict)
        else None
    )
    judge_context_id = normalized(
        payload.get("judge_context_id")
        if isinstance(payload, dict)
        else None
    )
    design = item.get("mutation_design")
    changed_paths = (
        normalized_path_set(design.get("changed_paths"))
        if isinstance(design, dict)
        else None
    )
    payload_changed_paths = normalized_path_set(
        payload.get("changed_paths") if isinstance(payload, dict) else None
    )
    target_files = package_files(target_path)
    mutated_files = (
        package_files(mutated_package)
        if mutated_package is not None
        else {}
    )
    actual_changed_paths = {
        relative
        for relative in set(target_files) | set(mutated_files)
        if target_files.get(relative) != mutated_files.get(relative)
    }
    mutation_design_valid = (
        isinstance(design, dict)
        and changed_paths is not None
        and bool(changed_paths)
        and changed_paths == actual_changed_paths
        and payload_changed_paths == changed_paths
        and substantive(design.get("defect_description"), 20)
        and substantive(design.get("expected_failure"), 20)
        and PLACEHOLDER_PATTERN.search(
            str(design.get("defect_description")).strip()
        )
        is None
        and PLACEHOLDER_PATTERN.search(
            str(design.get("expected_failure")).strip()
        )
        is None
    )
    return (
        mutated_package is not None
        and mutated_package != target_path
        and normalized(item.get("mutated_sha256")) != target_digest
        and skill_package_name(mutated_package) == skill_package_name(target_path)
        and package_has_lineage(target_path, mutated_package)
        and output_path is not None
        and isinstance(payload, dict)
        and normalized(payload.get("kind")) == "mutation-result"
        and normalized(payload.get("mutation_id")) == normalized(item.get("id"))
        and normalized(payload.get("target_sha256")) == target_digest
        and normalized(payload.get("mutated_sha256"))
        == normalized(item.get("mutated_sha256"))
        and normalized(payload.get("output_sha256"))
        == normalized(item.get("output_sha256"))
        and requirement_ids is not None
        and payload_requirement_ids == requirement_ids
        and payload.get("detected") is item.get("detected")
        and normalized(payload.get("finding")) == normalized(item.get("finding"))
        and normalized(payload.get("repair")) == normalized(item.get("repair"))
        and resolved_identity(executor_actor)
        and resolved_identity(judge_actor)
        and resolved_identity(executor_context_id)
        and resolved_identity(judge_context_id)
        and SHA256_PATTERN.fullmatch(
            normalized(payload.get("executor_prompt_sha256"))
        )
        is not None
        and SHA256_PATTERN.fullmatch(
            normalized(payload.get("judge_prompt_sha256"))
        )
        is not None
        and executor_actor != judge_actor
        and normalized(payload.get("category"))
        == normalized(item.get("category"))
        and normalized(payload.get("review_lens")) in JUDGMENT_LENSES
        and substantive(payload.get("rationale"), 40)
        and PLACEHOLDER_PATTERN.search(str(payload.get("rationale")).strip())
        is None
        and mutation_design_valid
        and normalized(item.get("provenance", {}).get("actor")) == judge_actor
        and timestamp_not_future(payload.get("created_at"))
        and (
            contract_frozen_at is None
            or timestamp_at_or_after(
                payload.get("created_at"),
                contract_frozen_at,
            )
        )
        and parse_timestamp(payload.get("created_at"))
        <= provenance_time(item.get("provenance"))
    )


def invocation_target(
    arguments: object,
    manifest_path: Path,
) -> Path | None:
    if not isinstance(arguments, list) or not all(
        isinstance(item, str) for item in arguments
    ):
        return None
    positional = [item for item in arguments if not item.startswith("--")]
    if len(positional) != 1:
        return None
    candidate = Path(positional[0])
    if not candidate.is_absolute():
        candidate = manifest_path.parent / candidate
    try:
        return candidate.resolve()
    except OSError:
        return None


def path_ends_with(path: Path, parts: tuple[str, ...]) -> bool:
    path_parts = tuple(part.casefold() for part in path.parts)
    expected = tuple(part.casefold() for part in parts)
    return len(path_parts) >= len(expected) and path_parts[-len(expected):] == expected


def replay_validator(
    script_path: Path,
    arguments: list[str],
    target_path: Path,
) -> subprocess.CompletedProcess[str] | None:
    replay_arguments = [
        argument if argument.startswith("--") else str(target_path)
        for argument in arguments
    ]
    try:
        return subprocess.run(
            [
                sys.executable,
                "-B",
                str(script_path),
                *replay_arguments,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
            env=os.environ.copy(),
        )
    except (OSError, subprocess.SubprocessError):
        return None


def valid_structural_test(
    item: dict,
    test_id: str,
    evidence_root: Path | None,
    target_path: Path,
    target_digest: str,
    manifest_path: Path,
) -> bool:
    invocation = item.get("invocation")
    if not isinstance(invocation, dict):
        return False
    executable_value = str(invocation.get("executable", "")).strip()
    executable_path = Path(executable_value).expanduser()
    executable_name = executable_path.name.casefold()
    if re.fullmatch(
        r"(?:python(?:\d+(?:\.\d+)*)?|py)(?:\.exe)?",
        executable_name,
    ) is None:
        return False
    try:
        if executable_path.resolve() != Path(sys.executable).resolve():
            return False
    except OSError:
        return False
    script_path = valid_hashed_file(
        invocation.get("script_ref"),
        invocation.get("script_sha256"),
        evidence_root,
    )
    arguments = invocation.get("arguments")
    tested_target = invocation_target(arguments, manifest_path)
    common = (
        completed_pass(item)
        and valid_provenance(item.get("provenance"), evidence_root)
        and item.get("exit_code") == 0
        and normalized(item.get("target_sha256")) == target_digest
        and script_path is not None
        and tested_target == target_path
    )
    if not common:
        return False
    output_path = provenance_artifact(item.get("provenance"), evidence_root)
    if output_path is None:
        return False
    if test_id == "official-validator":
        codex_home = Path(
            os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))
        ).expanduser()
        expected_official = (
            codex_home
            / "skills"
            / ".system"
            / "skill-creator"
            / "scripts"
            / "quick_validate.py"
        ).resolve()
        expected_bundled = (
            Path(__file__).resolve().parents[2]
            / "game-skill-creator"
            / "scripts"
            / "quick_validate.py"
        ).resolve()
        trusted_validator = script_path == expected_official
        if script_path == expected_bundled:
            trusted_validator = (
                sha256_file(script_path)
                == BUNDLED_OFFICIAL_VALIDATOR_SHA256
            )
        try:
            output_text = output_path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError):
            return False
        replay = replay_validator(script_path, arguments, target_path)
        return (
            trusted_validator
            and len(arguments) == 1
            and "Skill is valid!" in output_text
            and replay is not None
            and replay.returncode == 0
            and "Skill is valid!" in replay.stdout
        )
    if test_id == "bundled-audit":
        flags = [argument for argument in arguments if argument.startswith("--")]
        payload = load_json_object(output_path)
        summary = payload.get("summary", {}) if isinstance(payload, dict) else {}
        payload_target = (
            Path(str(payload.get("skill_path", "")).strip()).resolve()
            if isinstance(payload, dict) and substantive(payload.get("skill_path"))
            else None
        )
        expected_bundled = Path(__file__).resolve().with_name("audit_skill.py")
        replay = replay_validator(script_path, arguments, target_path)
        try:
            replay_payload = (
                json.loads(replay.stdout)
                if replay is not None and replay.stdout.strip()
                else None
            )
        except json.JSONDecodeError:
            replay_payload = None
        replay_summary = (
            replay_payload.get("summary", {})
            if isinstance(replay_payload, dict)
            else {}
        )
        return (
            script_path == expected_bundled
            and set(flags).issubset({"--strict", "--json"})
            and "--strict" in flags
            and item.get("strict") is True
            and isinstance(payload, dict)
            and payload_target == target_path
            and summary.get("errors") == 0
            and summary.get("warnings") == 0
            and replay is not None
            and replay.returncode == 0
            and isinstance(replay_payload, dict)
            and Path(str(replay_payload.get("skill_path", ""))).resolve()
            == target_path
            and replay_summary.get("errors") == 0
            and replay_summary.get("warnings") == 0
        )
    return True


def mutation_detected(
    item: dict,
    evidence_root: Path | None = None,
    target_path: Path | None = None,
    target_digest: str = "",
    contract_frozen_at: datetime | None = None,
) -> bool:
    return (
        item.get("detected") is True
        and substantive(item.get("finding"), 20)
        and PLACEHOLDER_PATTERN.search(str(item.get("finding")).strip()) is None
        and substantive(item.get("repair"), 20)
        and PLACEHOLDER_PATTERN.search(str(item.get("repair")).strip()) is None
        and (
            evidence_root is None
            or (
                target_path is not None
                and valid_mutation_result(
                    item,
                    evidence_root,
                    target_path,
                    target_digest,
                    contract_frozen_at,
                )
            )
        )
    )


def load_manifest(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Cannot read valid JSON from {path}: {error}") from error
    if not isinstance(data, dict):
        raise ValueError("The evidence manifest root must be a JSON object.")
    return data


def resolve_evidence_root(data: dict, manifest_path: Path) -> Path | None:
    reference = data.get("evidence_root")
    if not substantive(reference):
        return None
    candidate = Path(str(reference).strip())
    if not candidate.is_absolute():
        candidate = manifest_path.parent / candidate
    try:
        resolved = candidate.resolve()
    except OSError:
        return None
    return resolved if resolved.is_dir() else None


def artifact_outside_target(
    provenance: dict,
    evidence_root: Path | None,
    target: object,
    manifest_path: Path,
) -> bool:
    artifact = resolve_file(provenance.get("artifact"), evidence_root)
    if artifact is None or not substantive(target):
        return False
    target_path = Path(str(target).strip())
    if not target_path.is_absolute():
        target_path = manifest_path.parent / target_path
    try:
        target_path = target_path.resolve()
        artifact.relative_to(target_path)
    except ValueError:
        return True
    except OSError:
        return False
    return False


def resolve_target(data: dict, manifest_path: Path) -> Path | None:
    target = data.get("target")
    if not substantive(target):
        return None
    candidate = Path(str(target).strip())
    if not candidate.is_absolute():
        candidate = manifest_path.parent / candidate
    try:
        resolved = candidate.resolve()
    except OSError:
        return None
    return resolved if resolved.exists() else None


def load_json_object(path: Path | None) -> dict | None:
    if path is None or not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def assess(
    data: dict,
    manifest_path: Path,
    external_review_file: Path | None = None,
    user_acceptance_file: Path | None = None,
) -> tuple[int, list[str], dict]:
    blockers: list[str] = []
    details: dict[str, object] = {}
    evidence_root = resolve_evidence_root(data, manifest_path)
    if evidence_root is None:
        blockers.append("The evidence root is missing or inaccessible.")

    tests = [item for item in data.get("tests", []) if isinstance(item, dict)]
    roles = [item for item in data.get("roles", []) if isinstance(item, dict)]
    mutations = [
        item for item in data.get("mutations", []) if isinstance(item, dict)
    ]
    disagreements = [
        item for item in data.get("disagreements", []) if isinstance(item, dict)
    ]
    blinding = data.get("blinding", {})
    target_path = resolve_target(data, manifest_path)
    target_digest = package_digest(target_path) if target_path is not None else ""

    requirements = [
        item for item in data.get("requirements", []) if isinstance(item, dict)
    ]
    mode = normalized(data.get("mode"))
    mode_ready = mode in {"audit", "repair"}
    contract_frozen_at = parse_timestamp(data.get("contract_frozen_at"))
    contract_freeze_valid = (
        contract_frozen_at is not None
        and timestamp_not_future(data.get("contract_frozen_at"))
    )
    requirement_ids = [normalized(item.get("id")) for item in requirements]
    test_ids = [normalized(item.get("id")) for item in tests]
    mutation_ids = [normalized(item.get("id")) for item in mutations]
    evidence_records = [*tests, *mutations]
    evidence_ids = [*test_ids, *mutation_ids]
    evidence_by_id = {
        normalized(item.get("id")): item for item in evidence_records
    }
    test_by_id = {
        normalized(item.get("id")): item for item in tests
    }
    requirement_by_id = {
        normalized(item.get("id")): item for item in requirements
    }
    requirement_identities_valid = all(
        resolved_identity(item.get("id"))
        and normalized(item.get("contract_clause")) in CONTRACT_CLAUSES
        and normalized(item.get("provenance_category"))
        in PROVENANCE_CATEGORIES
        and substantive(item.get("acceptance_criterion"), 20)
        and PLACEHOLDER_PATTERN.search(
            str(item.get("acceptance_criterion")).strip()
        )
        is None
        for item in requirements
    )
    evidence_identities_valid = all(
        resolved_identity(item.get("id")) for item in [*tests, *mutations]
    )
    role_keys = [
        (
            normalized(item.get("role")),
            normalized(item.get("actor")),
            normalized(item.get("context_id")),
        )
        for item in roles
    ]
    disagreement_ids = [
        normalized(item.get("id")) for item in disagreements
    ]
    list_fields_valid = all(
        isinstance(data.get(field, []), list)
        and len(data.get(field, []))
        == len(
            [
                item
                for item in data.get(field, [])
                if isinstance(item, dict)
            ]
        )
        for field in (
            "requirements",
            "tests",
            "roles",
            "mutations",
            "disagreements",
        )
    )
    supplied_roles_valid = all(
        normalized(item.get("role")) in ALLOWED_ROLES
        and resolved_identity(item.get("actor"))
        and resolved_identity(item.get("context_id"))
        and valid_role(
            item,
            evidence_root,
            target_digest,
            contract_frozen_at,
            require_external_output=False,
        )
        for item in roles
    )
    supplied_disagreements_valid = (
        len(disagreement_ids) == len(set(disagreement_ids))
        and all(resolved_identity(item.get("id")) for item in disagreements)
        and all(
            normalized(item.get("severity")) in SEVERITIES
            and normalized(item.get("status")) in {"resolved", "unresolved"}
            for item in disagreements
        )
    )
    repair = data.get("repair", {})
    repair_identity_valid = (
        mode != "repair"
        or (
            isinstance(repair, dict)
            and isinstance(repair.get("finding_ids"), list)
            and bool(repair["finding_ids"])
            and all(
                resolved_identity(item) for item in repair["finding_ids"]
            )
        )
    )
    provenance_candidates = [
        *[item.get("provenance") for item in requirements if "provenance" in item],
        *[item.get("provenance") for item in tests if "provenance" in item],
        *[
            item.get("secondary_judgment")
            for item in tests
            if "secondary_judgment" in item
        ],
        *[item.get("provenance") for item in mutations if "provenance" in item],
        *[
            item.get(field)
            for item in roles
            for field in ("attestation", "output")
            if field in item
        ],
        *[
            value.get("provenance")
            for value in (
                data.get("preservation"),
                repair,
                data.get("external_review"),
                data.get("holdout"),
                data.get("user_acceptance"),
            )
            if isinstance(value, dict) and "provenance" in value
        ],
    ]
    supplied_provenance_valid = all(
        valid_provenance(item, evidence_root)
        for item in provenance_candidates
    )
    manifest_schema_valid = (
        list_fields_valid
        and resolved_identity(data.get("audit_id"))
        and resolved_identity(data.get("contract_version"), 1)
        and contract_freeze_valid
        and resolved_identity(data.get("target_actor_id"))
        and target_path is not None
        and requirement_identities_valid
        and evidence_identities_valid
        and repair_identity_valid
        and supplied_provenance_valid
        and len(role_keys) == len(set(role_keys))
        and supplied_roles_valid
        and supplied_disagreements_valid
    )
    contract_ready = (
        resolved_identity(data.get("contract_version"), 1)
        and contract_freeze_valid
        and bool(requirements)
        and requirement_identities_valid
        and {
            normalized(item.get("contract_clause")) for item in requirements
        }
        == CONTRACT_CLAUSES
        and any(
            normalized(item.get("provenance_category"))
            in {"user", "higher-level", "project"}
            for item in requirements
        )
        and len(requirement_ids) == len(set(requirement_ids))
        and all(
            valid_provenance(item.get("provenance"), evidence_root)
            and provenance_time(item.get("provenance")) <= contract_frozen_at
            for item in requirements
        )
    )
    evidence_chronology_ready = (
        contract_freeze_valid
        and all(
            timestamp_at_or_after(
                item.get("provenance", {}).get("created_at"),
                contract_frozen_at,
            )
            for item in [*tests, *mutations]
        )
    )
    traceability_ready = (
        contract_ready
        and len(evidence_ids) == len(set(evidence_ids))
        and all(evidence_ids)
        and all(
            isinstance(item.get("test_ids"), list)
            and bool(item["test_ids"])
            and all(
                normalized(test_id) in evidence_by_id
                and normalized(item.get("id"))
                in {
                    normalized(requirement_id)
                    for requirement_id in evidence_by_id[
                        normalized(test_id)
                    ].get("requirement_ids", [])
                }
                for test_id in item["test_ids"]
            )
            for item in requirements
        )
        and all(
            isinstance(item.get("requirement_ids"), list)
            and bool(item["requirement_ids"])
            and all(
                normalized(requirement_id) in requirement_by_id
                and normalized(item.get("id"))
                in {
                    normalized(test_id)
                    for test_id in requirement_by_id[
                        normalized(requirement_id)
                    ].get("test_ids", [])
                }
                for requirement_id in item["requirement_ids"]
            )
            for item in evidence_records
        )
    )

    tests_schema_valid = (
        len(test_ids) == len(set(test_ids))
        and all(resolved_identity(item.get("id")) for item in tests)
        and all(isinstance(item.get("required"), bool) for item in tests)
        and all(
            normalized(item.get("category")) in {"structural", "behavioral"}
            for item in tests
        )
        and all(
            normalized_behavior_case(item.get("case_type"))
            in BEHAVIOR_CASE_MINIMUMS
            for item in tests
            if normalized(item.get("category")) == "behavioral"
        )
    )
    structural_tests = [
        item for item in tests if normalized(item.get("category")) == "structural"
    ]
    structural_by_id = {
        normalized(item.get("id")): item for item in structural_tests
    }
    missing_structural = sorted(STRUCTURAL_TEST_IDS - set(structural_by_id))
    required_structural = [
        item for item in structural_tests if item.get("required") is True
    ]
    structural = (
        evidence_root is not None
        and manifest_schema_valid
        and tests_schema_valid
        and not missing_structural
        and all(
            structural_by_id[test_id].get("required") is True
            for test_id in STRUCTURAL_TEST_IDS
        )
        and all(
            valid_structural_test(
                item,
                normalized(item.get("id")),
                evidence_root,
                target_path,
                target_digest,
                manifest_path,
            )
            for item in required_structural
        )
    )
    if not structural:
        if not manifest_schema_valid:
            blockers.append(
                "Manifest identity and record integrity failed: resolve "
                "placeholders, malformed supplied roles, duplicate role "
                "identities, duplicate disagreement IDs, or an inaccessible "
                "target."
            )
        if not tests_schema_valid:
            blockers.append(
                "Test IDs must be unique and every test requires a strict "
                "boolean `required` field."
            )
        if missing_structural:
            blockers.append(
                "Missing named structural checks: "
                + ", ".join(missing_structural)
                + "."
            )
        if tests_schema_valid and not missing_structural:
            blockers.append(
                "Required structural checks failed, were not completed, or "
                "lack verified provenance."
            )

    preservation = data.get("preservation", {})
    preservation_before = (
        valid_package_artifact(
            preservation.get("before_artifact"),
            preservation.get("before_sha256"),
            evidence_root,
        )
        if isinstance(preservation, dict)
        else None
    )
    preservation_after = (
        valid_package_artifact(
            preservation.get("after_artifact"),
            preservation.get("after_sha256"),
            evidence_root,
        )
        if isinstance(preservation, dict)
        else None
    )
    preservation_ready = (
        isinstance(preservation, dict)
        and preservation.get("unchanged") is True
        and preservation_before is not None
        and preservation_after is not None
        and preservation_before != preservation_after
        and preservation_before != target_path
        and preservation_after != target_path
        and normalized(preservation.get("before_sha256"))
        == normalized(preservation.get("after_sha256"))
        and normalized(preservation.get("after_sha256")) == target_digest
        and valid_provenance(preservation.get("provenance"), evidence_root)
        and timestamp_at_or_after(
            preservation.get("provenance", {}).get("created_at"),
            contract_frozen_at,
        )
    )

    behavior_groups: dict[str, list[dict]] = {
        case_type: [
            item
            for item in tests
            if normalized(item.get("category")) == "behavioral"
            and normalized_behavior_case(item.get("case_type")) == case_type
        ]
        for case_type in BEHAVIOR_CASE_MINIMUMS
    }
    behavioral_tests = [
        item
        for item in tests
        if normalized(item.get("category")) == "behavioral"
    ]
    behavioral_prompt_hashes = [
        normalized(item.get("prompt_sha256")) for item in behavioral_tests
    ]
    behavioral_output_hashes = [
        normalized(item.get("output_sha256")) for item in behavioral_tests
    ]
    behavioral_output_paths = [
        resolve_file(item.get("output_ref"), evidence_root)
        for item in behavioral_tests
    ]
    behavioral_result_payloads = [
        load_json_object(
            provenance_artifact(item.get("provenance"), evidence_root)
        )
        for item in behavioral_tests
    ]
    secondary_behavior_payloads = [
        load_json_object(
            provenance_artifact(item.get("secondary_judgment"), evidence_root)
        )
        for item in behavioral_tests
    ]
    behavior_coverage_ready = all(
        len(behavior_groups[case_type]) >= minimum
        for case_type, minimum in BEHAVIOR_CASE_MINIMUMS.items()
    )
    behavior_prompts_ready = (
        all(
            valid_behavior_prompt(item, evidence_root)
            for item in behavioral_tests
        )
        and len(behavioral_prompt_hashes)
        == len(set(behavioral_prompt_hashes))
        and all(behavioral_output_paths)
        and len(behavioral_output_paths)
        == len(set(behavioral_output_paths))
        and all(behavioral_output_hashes)
        and len(behavioral_output_hashes)
        == len(set(behavioral_output_hashes))
    )
    activation_expectations_ready = all(
        isinstance(item.get("activation"), dict)
        and (
            (
                normalized_behavior_case(item.get("case_type"))
                in {"canonical", "paraphrase", "regression", "metamorphic"}
                and item["activation"].get("expected") is True
            )
            or (
                normalized_behavior_case(item.get("case_type"))
                == "negative-control"
                and item["activation"].get("expected") is False
            )
            or normalized_behavior_case(item.get("case_type")) == "edge"
        )
        for item in behavioral_tests
    )
    behavioral = (
        structural
        and contract_ready
        and traceability_ready
        and mode_ready
        and (mode != "audit" or preservation_ready)
        and behavior_coverage_ready
        and behavior_prompts_ready
        and activation_expectations_ready
        and evidence_chronology_ready
        and all(
            item.get("required") is True
            and completed_pass(item)
            and normalized(item.get("target_sha256")) == target_digest
            and valid_behavior_result(
                item,
                evidence_root,
                target_digest,
                skill_package_name(target_path),
                contract_frozen_at,
            )
            for item in behavioral_tests
        )
    )
    if structural and not behavioral:
        if not contract_ready:
            blockers.append(
                "A frozen contract, substantive unique requirements, "
                "acceptance criteria, and verified provenance are required."
            )
        if contract_ready and not traceability_ready:
            blockers.append(
                "Requirements and evidence must provide matching forward and "
                "reverse traceability."
            )
        if not mode_ready:
            blockers.append("Audit mode must be exactly `audit` or `repair`.")
        if not contract_freeze_valid:
            blockers.append(
                "The contract requires a valid, non-future `contract_frozen_at`."
            )
        elif not evidence_chronology_ready:
            blockers.append(
                "Behavioral and mutation evidence must not predate the frozen "
                "contract."
            )
        if mode == "audit" and not preservation_ready:
            blockers.append(
                "Audit mode requires distinct before/after preservation "
                "artifacts with identical verified hashes."
            )
        missing_coverage = sorted(
            f"{case_type} ({len(behavior_groups[case_type])}/{minimum})"
            for case_type, minimum in BEHAVIOR_CASE_MINIMUMS.items()
            if len(behavior_groups[case_type]) < minimum
        )
        if missing_coverage:
            blockers.append(
                "Behavioral coverage is incomplete: "
                + ", ".join(missing_coverage)
                + "."
            )
        if behavioral_tests and not behavior_prompts_ready:
            blockers.append(
                "Behavioral cases require distinct, verified prompt and "
                "output artifacts."
            )
        if behavioral_tests and not activation_expectations_ready:
            blockers.append(
                "Behavioral cases require auto-dispatch activation evidence: "
                "canonical, paraphrase, regression, and metamorphic prompts "
                "must activate the target, while negative controls must not."
            )
        elif contract_ready:
            blockers.append(
                "One or more behavioral cases failed, were optional, or lack "
                "verified provenance."
            )

    mutations_schema_valid = (
        len(mutation_ids) == len(set(mutation_ids))
        and all(resolved_identity(item.get("id")) for item in mutations)
        and all(
            normalized(item.get("category")) in MUTATION_CATEGORIES
            and normalized(item.get("severity")) in SEVERITIES
            and normalized(item.get("status")) in {"completed", "not-run"}
            and isinstance(item.get("detected"), bool)
            and (
                (
                    normalized(item.get("status")) == "completed"
                    and valid_mutation_result(
                        item,
                        evidence_root,
                        target_path,
                        target_digest,
                        contract_frozen_at,
                    )
                    and (
                        item.get("detected") is False
                        or mutation_detected(
                            item,
                            evidence_root,
                            target_path,
                            target_digest,
                            contract_frozen_at,
                        )
                    )
                )
                or (
                    normalized(item.get("status")) == "not-run"
                    and item.get("detected") is False
                )
            )
            and normalized(item.get("target_sha256")) == target_digest
            and valid_provenance(item.get("provenance"), evidence_root)
            for item in mutations
        )
    )
    completed_mutation_records = [
        item
        for item in mutations
        if normalized(item.get("status")) == "completed"
    ]
    completed_mutation_digests = [
        normalized(item.get("mutated_sha256"))
        for item in completed_mutation_records
    ]
    completed_mutation_outputs = [
        normalized(item.get("output_sha256"))
        for item in completed_mutation_records
    ]
    completed_mutation_judgments = [
        normalized(item.get("provenance", {}).get("artifact_sha256"))
        for item in completed_mutation_records
    ]
    mutation_artifacts_distinct = (
        all(completed_mutation_digests)
        and len(completed_mutation_digests)
        == len(set(completed_mutation_digests))
        and all(completed_mutation_outputs)
        and len(completed_mutation_outputs)
        == len(set(completed_mutation_outputs))
        and all(completed_mutation_judgments)
        and len(completed_mutation_judgments)
        == len(set(completed_mutation_judgments))
    )
    mutation_categories = {
        normalized(item.get("category")) for item in completed_mutation_records
    }
    category_detection = {
        category: bool(
            [
                item
                for item in completed_mutation_records
                if normalized(item.get("category")) == category
            ]
        )
        and all(
            mutation_detected(
                item,
                evidence_root,
                target_path,
                target_digest,
                contract_frozen_at,
            )
            for item in completed_mutation_records
            if normalized(item.get("category")) == category
        )
        for category in MUTATION_CATEGORIES
    }
    mutation_score = (
        sum(category_detection.values()) / len(MUTATION_CATEGORIES)
    )
    material_misses = [
        item
        for item in mutations
        if normalized(item.get("severity")) in MATERIAL_SEVERITIES
        and (
            normalized(item.get("status")) != "completed"
            or not mutation_detected(
                item,
                evidence_root,
                target_path,
                target_digest,
                contract_frozen_at,
            )
        )
    ]
    adversarial = (
        behavioral
        and mutations_schema_valid
        and len(completed_mutation_records) >= 5
        and MUTATION_CATEGORIES.issubset(mutation_categories)
        and mutation_artifacts_distinct
        and not material_misses
        and mutation_score >= 0.8
    )
    if behavioral and not adversarial:
        if not mutations_schema_valid:
            blockers.append(
                "Every declared mutation must be uniquely identified, "
                "strictly typed, target-bound, and backed by verified "
                "provenance; unrun Critical or High cases remain blockers."
            )
        missing_categories = sorted(MUTATION_CATEGORIES - mutation_categories)
        if missing_categories:
            blockers.append(
                "Missing mutation categories: " + ", ".join(missing_categories) + "."
            )
        if material_misses:
            blockers.append("At least one Critical or High mutation was missed.")
        if not mutation_artifacts_distinct:
            blockers.append(
                "Completed mutation categories require distinct mutated "
                "packages, raw outputs, and judgment artifacts."
            )
        if mutation_score < 0.8:
            blockers.append(f"Mutation detection is {mutation_score:.0%}; 80% is required.")

    repair_ready = True
    if mode == "repair":
        verification_ids = (
            repair.get("verification_test_ids")
            if isinstance(repair, dict)
            else None
        )
        normalized_verification_ids = (
            [normalized(item) for item in verification_ids]
            if isinstance(verification_ids, list)
            else []
        )
        verification_tests = [
            test_by_id[test_id]
            for test_id in normalized_verification_ids
            if test_id in test_by_id
        ]
        repair_provenance = (
            repair.get("provenance")
            if isinstance(repair, dict)
            else None
        )
        repair_time = (
            parse_timestamp(repair_provenance.get("created_at"))
            if isinstance(repair_provenance, dict)
            else None
        )
        before_package = (
            valid_package_artifact(
                repair.get("before_artifact"),
                repair.get("before_sha256"),
                evidence_root,
            )
            if isinstance(repair, dict)
            else None
        )
        after_package = (
            valid_package_artifact(
                repair.get("after_artifact"),
                repair.get("after_sha256"),
                evidence_root,
            )
            if isinstance(repair, dict)
            else None
        )
        target_skill_name = skill_package_name(target_path)
        before_skill_name = skill_package_name(before_package)
        after_skill_name = skill_package_name(after_package)
        repair_ready = (
            isinstance(repair, dict)
            and isinstance(repair.get("finding_ids"), list)
            and bool(repair["finding_ids"])
            and all(resolved_identity(item) for item in repair["finding_ids"])
            and SHA256_PATTERN.fullmatch(normalized(repair.get("before_sha256")))
            is not None
            and SHA256_PATTERN.fullmatch(normalized(repair.get("after_sha256")))
            is not None
            and normalized(repair.get("before_sha256"))
            != normalized(repair.get("after_sha256"))
            and before_package is not None
            and after_package is not None
            and before_package != after_package
            and before_package != target_path
            and after_package != target_path
            and bool(target_skill_name)
            and before_skill_name == target_skill_name
            and after_skill_name == target_skill_name
            and normalized(repair.get("after_sha256")) == target_digest
            and isinstance(verification_ids, list)
            and bool(verification_ids)
            and len(normalized_verification_ids)
            == len(set(normalized_verification_ids))
            and len(verification_tests) == len(normalized_verification_ids)
            and STRUCTURAL_TEST_IDS.issubset(normalized_verification_ids)
            and any(
                normalized(item.get("category")) == "behavioral"
                and normalized_behavior_case(item.get("case_type"))
                == "regression"
                for item in verification_tests
            )
            and all(
                completed_pass(item)
                and normalized(item.get("target_sha256")) == target_digest
                and parse_timestamp(
                    item.get("provenance", {}).get("created_at")
                )
                is not None
                and repair_time is not None
                and parse_timestamp(
                    item.get("provenance", {}).get("created_at")
                )
                >= repair_time
                for item in verification_tests
            )
            and valid_provenance(repair_provenance, evidence_root)
        )
        if not repair_ready:
            blockers.append(
                "Repair mode requires finding IDs, distinct full-package "
                "snapshots, an after snapshot matching the target digest, "
                "verified provenance, both structural validators, and a "
                "post-repair regression."
            )
            structural = False
            behavioral = False
    adversarial = adversarial and repair_ready

    roles_by_name: dict[str, list[dict]] = {}
    for role in roles:
        roles_by_name.setdefault(normalized(role.get("role")), []).append(role)
    core_roles_present = all(
        len(roles_by_name.get(role_name, [])) == 1
        for role_name in REQUIRED_ROLES
    )
    judges = roles_by_name.get("judgment", [])
    execution_actors = {
        normalized(role.get("actor"))
        for role in roles_by_name.get("execution", [])
    }
    judgment_actors = {
        normalized(role.get("actor")) for role in judges
    }
    judgment_lenses = {
        normalized(role.get("review_lens")) for role in judges
    }
    relevant_roles = [
        *[
            roles_by_name[role_name][0]
            for role_name in REQUIRED_ROLES
            if len(roles_by_name.get(role_name, [])) == 1
        ],
        *judges,
    ]
    role_records_valid = bool(relevant_roles) and all(
        valid_role(
            role,
            evidence_root,
            target_digest,
            contract_frozen_at,
        )
        for role in relevant_roles
    )
    context_ids = [normalized(role.get("context_id")) for role in relevant_roles]
    actor_ids = [normalized(role.get("actor")) for role in relevant_roles]
    prompt_paths = [
        valid_hashed_file(
            role.get("prompt_ref"),
            role.get("prompt_sha256"),
            evidence_root,
        )
        for role in relevant_roles
    ]
    prompt_hashes = [
        normalized(role.get("prompt_sha256")) for role in relevant_roles
    ]
    external_output_paths = [
        resolve_file(role.get("output", {}).get("artifact"), evidence_root)
        for role_name in EXTERNAL_ROLES
        for role in roles_by_name.get(role_name, [])
    ]
    attestation_paths = [
        resolve_file(role.get("attestation", {}).get("artifact"), evidence_root)
        for role in relevant_roles
    ]
    external_output_hashes = [
        normalized(role.get("output", {}).get("artifact_sha256"))
        for role_name in EXTERNAL_ROLES
        for role in roles_by_name.get(role_name, [])
    ]
    attestation_hashes = [
        normalized(role.get("attestation", {}).get("artifact_sha256"))
        for role in relevant_roles
    ]
    distinct_contexts = (
        all(context_ids) and len(context_ids) == len(set(context_ids))
    )
    distinct_actors = all(actor_ids) and len(actor_ids) == len(set(actor_ids))
    distinct_prompts = (
        all(prompt_paths)
        and all(prompt_hashes)
        and len(prompt_paths) == len(set(prompt_paths))
        and len(prompt_hashes) == len(set(prompt_hashes))
    )
    distinct_external_outputs = (
        all(external_output_paths)
        and len(external_output_paths) == len(set(external_output_paths))
        and all(external_output_hashes)
        and len(external_output_hashes) == len(set(external_output_hashes))
    )
    distinct_attestations = (
        all(attestation_paths)
        and len(attestation_paths) == len(set(attestation_paths))
        and all(attestation_hashes)
        and len(attestation_hashes) == len(set(attestation_hashes))
    )
    blind = (
        isinstance(blinding, dict)
        and blinding.get("test_designer_saw_target") is False
        and blinding.get("executors_saw_expected_results") is False
        and blinding.get("judges_saw_author_rationale") is False
    )
    role_chronology_ready = (
        contract_freeze_valid
        and all(
            timestamp_at_or_after(
                role.get("attestation", {}).get("created_at"),
                contract_frozen_at,
            )
            and (
                normalized(role.get("role")) == "execution"
                or timestamp_at_or_after(
                    role.get("output", {}).get("created_at"),
                    contract_frozen_at,
                )
            )
            for role in relevant_roles
        )
    )
    secondary_behavior_ready = (
        len(judges) == 2
        and judgment_lenses == JUDGMENT_LENSES
        and all(
            valid_behavior_result(
                item,
                evidence_root,
                target_digest,
                skill_package_name(target_path),
                contract_frozen_at,
                "secondary_judgment",
            )
            for item in behavioral_tests
        )
        and all(
            {
                behavior_judge_actor(
                    item,
                    "provenance",
                    evidence_root,
                ),
                behavior_judge_actor(
                    item,
                    "secondary_judgment",
                    evidence_root,
                ),
            }
            == judgment_actors
            for item in behavioral_tests
        )
        and all(
            {
                behavior_judge_lens(
                    item,
                    "provenance",
                    evidence_root,
                ),
                behavior_judge_lens(
                    item,
                    "secondary_judgment",
                    evidence_root,
                ),
            }
            == JUDGMENT_LENSES
            for item in behavioral_tests
        )
    )
    disagreements_schema_valid = all(
        substantive(item.get("id"))
        and normalized(item.get("severity")) in SEVERITIES
        and normalized(item.get("status")) in {"resolved", "unresolved"}
        for item in disagreements
    )
    unresolved = [
        item
        for item in disagreements
        if normalized(item.get("status")) != "resolved"
        and normalized(item.get("severity")) in MATERIAL_SEVERITIES
    ]
    target_actor = normalized(data.get("target_actor_id"))
    external_evaluators = (
        substantive(data.get("target_actor_id"))
        and all(roles_by_name.get(role_name) for role_name in EXTERNAL_ROLES)
        and all(
            role.get("governed_by_target") is False
            and normalized(role.get("actor")) != target_actor
            for role_name in EXTERNAL_ROLES
            for role in roles_by_name.get(role_name, [])
        )
    )
    role_bindings = {
        normalized(role.get("actor")): {
            "context_id": normalized(role.get("context_id")),
            "prompt_sha256": normalized(role.get("prompt_sha256")),
            "review_lens": normalized(role.get("review_lens")),
        }
        for role in relevant_roles
    }
    result_payloads = [
        *behavioral_result_payloads,
        *secondary_behavior_payloads,
        *[
            load_json_object(
                provenance_artifact(item.get("provenance"), evidence_root)
            )
            for item in completed_mutation_records
        ],
    ]
    result_role_bindings = (
        all(isinstance(payload, dict) for payload in result_payloads)
        and all(
            (
                normalized(payload.get("executor_actor")) in execution_actors
                and normalized(payload.get("judge_actor")) in judgment_actors
                and normalized(payload.get("executor_context_id"))
                == role_bindings[
                    normalized(payload.get("executor_actor"))
                ]["context_id"]
                and normalized(payload.get("judge_context_id"))
                == role_bindings[
                    normalized(payload.get("judge_actor"))
                ]["context_id"]
                and normalized(payload.get("executor_prompt_sha256"))
                == role_bindings[
                    normalized(payload.get("executor_actor"))
                ]["prompt_sha256"]
                and normalized(payload.get("judge_prompt_sha256"))
                == role_bindings[
                    normalized(payload.get("judge_actor"))
                ]["prompt_sha256"]
                and normalized(payload.get("review_lens"))
                == role_bindings[
                    normalized(payload.get("judge_actor"))
                ]["review_lens"]
            )
            for payload in result_payloads
            if isinstance(payload, dict)
        )
    )
    contract_role_binding = (
        len(roles_by_name.get("contract", [])) == 1
        and all(
            normalized(requirement.get("provenance", {}).get("actor"))
            == normalized(roles_by_name["contract"][0].get("actor"))
            for requirement in requirements
        )
    )
    independent_base = (
        adversarial
        and core_roles_present
        and len(judges) >= 2
        and role_records_valid
        and distinct_contexts
        and distinct_actors
        and distinct_prompts
        and distinct_external_outputs
        and distinct_attestations
        and blind
        and role_chronology_ready
        and secondary_behavior_ready
        and disagreements_schema_valid
        and external_evaluators
        and result_role_bindings
        and contract_role_binding
        and not unresolved
    )
    external_review = data.get("external_review", {})
    supplied_external_review = (
        external_review_file.resolve()
        if external_review_file is not None and external_review_file.is_file()
        else None
    )
    external_review_provenance = (
        external_review.get("provenance")
        if isinstance(external_review, dict)
        else None
    )
    external_review_artifact = (
        resolve_file(external_review_provenance.get("artifact"), evidence_root)
        if isinstance(external_review_provenance, dict)
        else None
    )
    external_review_payload = load_json_object(supplied_external_review)
    external_review_actor = normalized(
        external_review_payload.get("review_actor_id")
        if isinstance(external_review_payload, dict)
        else None
    )
    chronology_times = [
        *[
            provenance_time(item.get("provenance"))
            for item in [*tests, *mutations]
        ],
        *[
            provenance_time(item.get("secondary_judgment"))
            for item in behavioral_tests
            if "secondary_judgment" in item
        ],
        *[
            provenance_time(role.get("attestation"))
            for role in relevant_roles
        ],
        *[
            provenance_time(role.get("output"))
            for role in relevant_roles
            if "output" in role
        ],
    ]
    latest_public_evidence = (
        max(value for value in chronology_times if value is not None)
        if any(value is not None for value in chronology_times)
        else None
    )
    external_review_created = (
        parse_timestamp(external_review_payload.get("created_at"))
        if isinstance(external_review_payload, dict)
        else None
    )
    expected_external_actors = {
        normalized(role.get("actor"))
        for role_name in EXTERNAL_ROLES
        for role in roles_by_name.get(role_name, [])
    }
    supplied_reviewer_actors = {
        normalized(actor)
        for actor in (
            external_review_payload.get("reviewer_actor_ids", [])
            if isinstance(external_review_payload, dict)
            else []
        )
    }
    external_review_pass = (
        independent_base
        and target_path is not None
        and isinstance(external_review, dict)
        and completed_pass(external_review)
        and valid_provenance(external_review_provenance, evidence_root)
        and supplied_external_review is not None
        and external_review_artifact == supplied_external_review
        and artifact_outside_target(
            external_review_provenance,
            evidence_root,
            data.get("target"),
            manifest_path,
        )
        and isinstance(external_review_payload, dict)
        and normalized(external_review_payload.get("verdict")) == "pass"
        and normalized(external_review_payload.get("target_sha256"))
        == target_digest
        and supplied_reviewer_actors == expected_external_actors
        and resolved_identity(external_review_actor)
        and external_review_actor
        == normalized(external_review_provenance.get("actor"))
        and external_review_actor != target_actor
        and external_review_actor not in expected_external_actors
        and timestamp_not_future(external_review_payload.get("created_at"))
        and timestamp_at_or_after(
            external_review_provenance.get("created_at"),
            latest_public_evidence,
        )
        and external_review_created is not None
        and latest_public_evidence is not None
        and external_review_created >= latest_public_evidence
        and external_review_created
        <= provenance_time(external_review_provenance)
    )
    independence_evidence_ready = independent_base and external_review_pass
    if adversarial and not independence_evidence_ready:
        if not core_roles_present or len(judges) != 2:
            blockers.append(
                "Exactly one contract, test-design, execution, and adversarial "
                "role plus two judgment roles are required."
            )
        if not role_records_valid:
            blockers.append(
                "Roles require verified prompts, matching attestations, actor "
                "IDs, context IDs, and target-governance booleans."
            )
        if not distinct_contexts:
            blockers.append("Evaluation context identifiers are not distinct.")
        if not distinct_actors:
            blockers.append("Evaluation actor identifiers are not distinct.")
        if not distinct_prompts:
            blockers.append("Evaluation prompt artifacts are not distinct.")
        if not distinct_external_outputs:
            blockers.append("External evaluator output artifacts are not distinct.")
        if not distinct_attestations:
            blockers.append("Evaluation role attestation artifacts are not distinct.")
        if not blind:
            blockers.append("One or more required blinding conditions failed.")
        if not role_chronology_ready:
            blockers.append(
                "Role attestations and outputs must not predate the frozen "
                "contract."
            )
        if not secondary_behavior_ready:
            blockers.append(
                "Every behavioral case requires both distinct judgment lenses "
                "bound to the same prompt, output, requirements, and target."
            )
        if not disagreements_schema_valid:
            blockers.append("Disagreement records are malformed.")
        if not external_evaluators:
            blockers.append(
                "External evaluators are missing, target-governed, or share "
                "the target actor identity."
            )
        if not result_role_bindings:
            blockers.append(
                "Behavioral and mutation results are not bound to the recorded "
                "execution and judgment actors, contexts, prompts, and lenses."
            )
        if not contract_role_binding:
            blockers.append(
                "Frozen requirement provenance is not bound to the independent "
                "contract role."
            )
        if unresolved:
            blockers.append("A material reviewer disagreement remains unresolved.")
        if independent_base and not external_review_pass:
            blockers.append(
                "Level 4 requires a separate verified external-review JSON "
                "tied to the exact target package digest and external actors."
            )

    role_actor_set = set(actor_ids)
    holdout = data.get("holdout", {})
    acceptance = data.get("user_acceptance", {})
    holdout_provenance = (
        holdout.get("provenance") if isinstance(holdout, dict) else None
    )
    holdout_frozen = (
        parse_timestamp(holdout.get("holdout_frozen_at"))
        if isinstance(holdout, dict)
        else None
    )
    holdout_revealed = (
        parse_timestamp(holdout.get("revealed_at"))
        if isinstance(holdout, dict)
        else None
    )
    holdout_artifact = (
        provenance_artifact(holdout_provenance, evidence_root)
        if isinstance(holdout_provenance, dict)
        else None
    )
    holdout_payload = load_json_object(holdout_artifact)
    holdout_pass = (
        isinstance(holdout, dict)
        and holdout.get("external_to_target") is True
        and holdout.get("frozen_before_reveal") is True
        and completed_pass(holdout)
        and valid_provenance(holdout_provenance, evidence_root)
        and holdout_frozen is not None
        and holdout_revealed is not None
        and timestamp_not_future(holdout.get("holdout_frozen_at"))
        and timestamp_not_future(holdout.get("revealed_at"))
        and holdout_revealed >= holdout_frozen
        and external_review_created is not None
        and holdout_frozen >= external_review_created
        and isinstance(holdout_payload, dict)
        and normalized(holdout_payload.get("kind")) == "holdout-result"
        and normalized(holdout_payload.get("verdict")) == "pass"
        and normalized(holdout_payload.get("target_sha256")) == target_digest
        and normalized(holdout_payload.get("actor_id"))
        == normalized(holdout_provenance.get("actor"))
        and parse_timestamp(holdout_payload.get("holdout_frozen_at"))
        == holdout_frozen
        and parse_timestamp(holdout_payload.get("revealed_at"))
        == holdout_revealed
        and timestamp_not_future(holdout_payload.get("created_at"))
        and timestamp_at_or_after(
            holdout_provenance.get("created_at"),
            holdout_revealed,
        )
        and timestamp_at_or_after(
            holdout_payload.get("created_at"),
            holdout_revealed,
        )
        and parse_timestamp(holdout_payload.get("created_at"))
        <= provenance_time(holdout_provenance)
        and normalized(holdout_provenance.get("actor")) not in role_actor_set
        and normalized(holdout_provenance.get("actor")) != target_actor
        and artifact_outside_target(
            holdout_provenance,
            evidence_root,
            data.get("target"),
            manifest_path,
        )
        and isinstance(blinding, dict)
        and blinding.get("holdout_revealed_before_freeze") is False
    )
    acceptance_provenance = (
        acceptance.get("provenance") if isinstance(acceptance, dict) else None
    )
    supplied_acceptance = (
        user_acceptance_file.resolve()
        if user_acceptance_file is not None and user_acceptance_file.is_file()
        else None
    )
    acceptance_artifact = (
        resolve_file(acceptance_provenance.get("artifact"), evidence_root)
        if isinstance(acceptance_provenance, dict)
        else None
    )
    acceptance_payload = load_json_object(supplied_acceptance)
    acceptance_pass = (
        isinstance(acceptance, dict)
        and acceptance.get("confirmed_by_user") is True
        and completed_pass(acceptance)
        and valid_provenance(acceptance_provenance, evidence_root)
        and supplied_acceptance is not None
        and acceptance_artifact == supplied_acceptance
        and isinstance(acceptance_payload, dict)
        and normalized(acceptance_payload.get("kind")) == "user-acceptance"
        and normalized(acceptance_payload.get("verdict")) == "accept"
        and normalized(acceptance_payload.get("target_sha256")) == target_digest
        and normalized(acceptance_payload.get("accepted_level"))
        == normalized("User Validated")
        and normalized(acceptance_payload.get("actor_id"))
        == normalized(acceptance_provenance.get("actor"))
        and timestamp_not_future(acceptance_payload.get("created_at"))
        and timestamp_at_or_after(
            acceptance_provenance.get("created_at"),
            holdout_revealed,
        )
        and timestamp_at_or_after(
            acceptance_payload.get("created_at"),
            holdout_revealed,
        )
        and parse_timestamp(acceptance_payload.get("created_at"))
        <= provenance_time(acceptance_provenance)
        and substantive(acceptance_payload.get("statement"), 20)
        and artifact_outside_target(
            acceptance_provenance,
            evidence_root,
            data.get("target"),
            manifest_path,
        )
        and (
            not holdout_pass
            or acceptance_artifact
            != resolve_file(holdout_provenance.get("artifact"), evidence_root)
        )
        and normalized(acceptance_provenance.get("actor")) not in role_actor_set
        and normalized(acceptance_provenance.get("actor")) != target_actor
        and "user" in normalized(acceptance_provenance.get("source"))
    )
    user_validation_evidence_ready = (
        independence_evidence_ready and holdout_pass and acceptance_pass
    )
    if independence_evidence_ready and not user_validation_evidence_ready:
        if not holdout_pass:
            blockers.append(
                "A verified external post-freeze holdout has not passed."
            )
        if not acceptance_pass:
            blockers.append(
                "Explicit user acceptance was not supplied as a separate "
                "verified artifact."
            )

    if structural:
        blockers.append(
            "Automated readiness is capped at Structurally Valid because local "
            "artifacts cannot authenticate target execution, semantic "
            "judgment, evaluator identity, or user identity. Levels 2-5 "
            "require manual adjudication of the actual interactions."
        )

    evidence_package_gates = [
        structural,
        behavioral,
        adversarial,
        independence_evidence_ready,
        user_validation_evidence_ready,
    ]
    evidence_package_index = 0
    for index, passed in enumerate(evidence_package_gates, start=1):
        if not passed:
            break
        evidence_package_index = index

    gates = [structural, False, False, False, False]
    level_index = 0
    for index, passed in enumerate(gates, start=1):
        if not passed:
            break
        level_index = index

    model_families = {
        normalized(role.get("model_family"))
        for role in relevant_roles
        if normalized(role.get("model_family")) not in {"", "unknown"}
    }
    details.update(
        {
            "readiness": STATUS_LABELS[level_index],
            "manifest_schema_valid": manifest_schema_valid,
            "contract_ready": contract_ready,
            "traceability_ready": traceability_ready,
            "repair_ready": repair_ready,
            "preservation_ready": preservation_ready,
            "behavioral_evidence_complete": behavioral,
            "adversarial_evidence_complete": adversarial,
            "external_review_ready": external_review_pass,
            "independence_evidence_ready": independence_evidence_ready,
            "user_validation_evidence_ready": user_validation_evidence_ready,
            "evidence_package_completeness": EVIDENCE_COMPLETENESS_LABELS[
                evidence_package_index
            ],
            "automated_readiness_cap": "Structurally Valid",
            "target_sha256": target_digest,
            "mutation_score": round(mutation_score, 4),
            "mutation_category_detection": category_detection,
            "completed_mutations": sum(
                normalized(item.get("status")) == "completed" for item in mutations
            ),
            "distinct_evaluation_contexts": len(set(context_ids)),
            "distinct_evaluation_actors": len(set(actor_ids)),
            "known_model_families": sorted(model_families),
            "model_diverse": len(model_families) >= 2,
            "identity_authenticated": False,
            "execution_authenticated": False,
            "semantic_judgment_authenticated": False,
            "readiness_basis": (
                "replayed structural checks only; higher evidence-package "
                "levels describe internally consistent, hash-bound records "
                "that still require manual review of the actual interactions"
            ),
        }
    )
    return level_index, blockers, details


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--require-level", choices=READINESS_LEVELS)
    parser.add_argument(
        "--external-review-file",
        type=Path,
        help="External review JSON required for Level 4 and above.",
    )
    parser.add_argument(
        "--user-acceptance-file",
        type=Path,
        help="External user-supplied acceptance artifact required for Level 5.",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Return success after reporting even when readiness is Not Validated.",
    )
    args = parser.parse_args()

    try:
        manifest_path = args.manifest.resolve()
        data = load_manifest(manifest_path)
        level_index, blockers, details = assess(
            data,
            manifest_path,
            args.external_review_file,
            args.user_acceptance_file,
        )
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    output = {**details, "blockers": blockers}
    if args.as_json:
        print(json.dumps(output, indent=2))
    else:
        print(f"Readiness: {details['readiness']}")
        print(f"Mutation detection: {details['mutation_score']:.0%}")
        print(
            "Independent contexts: "
            f"{details['distinct_evaluation_contexts']}"
        )
        print(
            "Independent actors: "
            f"{details['distinct_evaluation_actors']}"
        )
        print(
            "Model diversity: "
            f"{'yes' if details['model_diverse'] else 'not demonstrated'}"
        )
        for blocker in blockers:
            print(f"BLOCKER: {blocker}")

    if args.require_level:
        required_index = STATUS_LABELS.index(args.require_level)
        if level_index < required_index:
            return 1
    if level_index == 0 and not args.report_only:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
