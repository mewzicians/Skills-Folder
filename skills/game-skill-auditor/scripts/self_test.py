#!/usr/bin/env python3
"""Exercise assess_evidence.py with isolated adversarial manifests."""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable


TARGET = Path(__file__).resolve().parents[1]
SCORER = TARGET / "scripts" / "assess_evidence.py"
OUT_DIR = Path(tempfile.mkdtemp(prefix="skill-auditor-probes-"))
ROOT = OUT_DIR.parent
EVIDENCE_DIR = OUT_DIR / "evidence"
EVIDENCE_FILE = EVIDENCE_DIR / "evidence.log"
HOLDOUT_FILE = OUT_DIR / "external-holdout.txt"
ACCEPTANCE_FILE = OUT_DIR / "user-acceptance.txt"
EXTERNAL_REVIEW_FILE = OUT_DIR / "external-review.json"
AUDIT_BEFORE_PACKAGE = EVIDENCE_DIR / "audit-before-package"
AUDIT_AFTER_PACKAGE = EVIDENCE_DIR / "audit-after-package"
REPAIR_BEFORE_PACKAGE = EVIDENCE_DIR / "repair-before-package"
REPAIR_AFTER_PACKAGE = EVIDENCE_DIR / "repair-after-package"
UNRELATED_BEFORE_PACKAGE = EVIDENCE_DIR / "unrelated-before-package"
INSTALLED_OFFICIAL_VALIDATOR = (
    Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser()
    / "skills"
    / ".system"
    / "skill-creator"
    / "scripts"
    / "quick_validate.py"
)
BUNDLED_OFFICIAL_VALIDATOR = (
    TARGET.parent
    / "game-skill-creator"
    / "scripts"
    / "quick_validate.py"
)
OFFICIAL_VALIDATOR = (
    INSTALLED_OFFICIAL_VALIDATOR
    if INSTALLED_OFFICIAL_VALIDATOR.is_file()
    else BUNDLED_OFFICIAL_VALIDATOR
)

LEVELS = [
    "Not Validated",
    "Structurally Valid",
    "Behaviorally Tested",
    "Adversarially Tested",
    "Independently Cross-Checked",
    "User Validated",
]
EVIDENCE_COMPLETENESS_BY_LEVEL = {
    "Not Validated": "No Complete Evidence Gate",
    "Structurally Valid": "Structural Evidence Complete",
    "Behaviorally Tested": "Behavioral Evidence Complete",
    "Adversarially Tested": "Adversarial Evidence Complete",
    "Independently Cross-Checked": "Independent Review Evidence Complete",
    "User Validated": "User Validation Evidence Complete",
}
LEVEL_BY_EVIDENCE_COMPLETENESS = {
    value: key for key, value in EVIDENCE_COMPLETENESS_BY_LEVEL.items()
}


def provenance(
    label: str,
    *,
    actor: str = "external-evaluator",
    artifact: str | None = None,
    created_at: str = "2026-08-14T00:04:00Z",
) -> dict:
    artifact_path = Path(artifact) if artifact else EVIDENCE_FILE
    return {
        "source": label,
        "actor": actor,
        "artifact": str(artifact_path),
        "artifact_sha256": sha256_file(artifact_path) if artifact_path.is_file() else "0" * 64,
        "created_at": created_at,
        "custodian": "adversarial-review",
    }


def sha256_file(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def package_digest(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    for item in sorted(
        (candidate for candidate in path.rglob("*") if candidate.is_file()),
        key=lambda candidate: candidate.relative_to(path).as_posix(),
    ):
        digest.update(item.relative_to(path).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(item.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def write_artifact(name: str, text: str) -> Path:
    path = EVIDENCE_DIR / name
    path.write_text(text, encoding="utf-8")
    return path


def write_json_artifact(name: str, value: dict) -> Path:
    return write_artifact(name, json.dumps(value, indent=2) + "\n")


def role_entry(
    role_name: str,
    actor: str,
    context_id: str,
    target_digest: str,
    *,
    governed_by_target: bool,
    review_lens: str = "",
) -> dict:
    prompt = write_artifact(
        f"prompt-{actor}.txt",
        f"Prompt for {role_name} actor {actor}.\n",
    )
    attestation = write_json_artifact(
        f"attestation-{actor}.json",
        {
            "kind": "role-attestation",
            "role": role_name,
            "actor": actor,
            "context_id": context_id,
            "prompt_sha256": sha256_file(prompt),
            "target_sha256": target_digest,
            "governed_by_target": governed_by_target,
            "review_lens": review_lens,
            "created_at": "2026-08-14T00:01:00Z",
        },
    )
    value = {
        "role": role_name,
        "actor": actor,
        "context_id": context_id,
        "prompt_ref": str(prompt),
        "prompt_sha256": sha256_file(prompt),
        "model_family": "test-model",
        "governed_by_target": governed_by_target,
        "review_lens": review_lens,
        "attestation": provenance(
            "role attestation",
            actor=actor,
            artifact=str(attestation),
            created_at="2026-08-14T00:01:00Z",
        ),
    }
    if role_name != "execution":
        output = write_json_artifact(
            f"output-{actor}.json",
            {
                "kind": "role-output",
                "role": role_name,
                "actor": actor,
                "context_id": context_id,
                "target_sha256": target_digest,
                "status": "completed",
                "created_at": "2026-08-14T00:03:00Z",
            },
        )
        value["output"] = provenance(
            f"{role_name} output",
            actor=actor,
            artifact=str(output),
            created_at="2026-08-14T00:03:00Z",
        )
    return value


def plant_mutation(mutated_package: Path, category: str) -> tuple[list[str], str, str]:
    skill_path = mutated_package / "SKILL.md"
    metadata_path = mutated_package / "agents" / "openai.yaml"
    if category == "trigger":
        path = skill_path
        old = (
            "Do not use for ordinary game-skill creation or editing unless "
            "the user requests an audit, validation, capability-gap analysis, "
            "behavioral repair, or readiness judgment."
        )
        new = "Use for ordinary skill creation and editing too."
        description = "Broaden the trigger to unrelated skill creation and editing."
        expected = "The audit must report a trigger-precision failure and restore the exclusion."
    elif category == "context":
        path = skill_path
        old = "(references/independence-protocol.md)"
        new = "(references/missing-independence-protocol.md)"
        description = "Break routing to the mandatory independence protocol."
        expected = "The audit must report missing required reading and repair the source route."
    elif category == "boundary":
        path = skill_path
        old = "Do not edit the target during an\naudit-only request."
        new = "Edit the target during an audit-only request."
        description = "Reverse the audit-only preservation boundary."
        expected = "The audit must report the unsafe side effect and restore preservation."
    elif category == "evidence":
        path = skill_path
        old = "`Not Validated` exits nonzero by default."
        new = "`Not Validated` exits zero by default."
        description = "Reverse the failure-honesty requirement for invalid evidence."
        expected = "The audit must report false completion and restore a nonzero failure exit."
    elif category == "metadata":
        path = metadata_path
        old = "$game-skill-auditor"
        new = "$ordinary-editor"
        description = "Point the default prompt at the wrong skill identity."
        expected = "The audit must report stale metadata and restore the target skill name."
    else:
        raise ValueError(f"Unsupported mutation category: {category}")
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise ValueError(f"Mutation source text not found for {category}: {old}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return [path.relative_to(mutated_package).as_posix()], description, expected


def build_example() -> dict:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    EVIDENCE_FILE.write_text("Verified test evidence.\n", encoding="utf-8")
    target_digest = package_digest(TARGET)
    roles = [
        role_entry(
            "contract",
            "contract-steward",
            "context-contract",
            target_digest,
            governed_by_target=False,
        ),
        role_entry(
            "test-design",
            "test-designer",
            "context-test-design",
            target_digest,
            governed_by_target=False,
        ),
        role_entry(
            "execution",
            "target-executor",
            "context-execution",
            target_digest,
            governed_by_target=True,
        ),
        role_entry(
            "judgment",
            "contract-judge",
            "context-judge-1",
            target_digest,
            governed_by_target=False,
            review_lens="contract-criteria",
        ),
        role_entry(
            "judgment",
            "user-advocate",
            "context-judge-2",
            target_digest,
            governed_by_target=False,
            review_lens="adversarial-user",
        ),
        role_entry(
            "adversarial-review",
            "red-team-reviewer",
            "context-adversarial",
            target_digest,
            governed_by_target=False,
        ),
    ]
    external_actors = [
        role["actor"] for role in roles if role["role"] != "execution"
    ]
    EXTERNAL_REVIEW_FILE.write_text(
        json.dumps(
            {
                "verdict": "pass",
                "target_sha256": target_digest,
                "reviewer_actor_ids": external_actors,
                "review_actor_id": "external-review-steward",
                "created_at": "2026-08-14T00:10:00Z",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    behavioral_specs = [
        ("canonical-1", "canonical", "Audit this skill for gaps."),
        ("canonical-2", "canonical", "Validate whether this skill works."),
        ("canonical-3", "canonical", "Repair and regression-test this skill."),
        ("paraphrase-1", "paraphrase", "Why does this agent workflow miss requirements?"),
        ("paraphrase-2", "paraphrase", "Can this instruction package be trusted?"),
        ("edge-1", "edge", "Check this skill, but do not change it."),
        ("negative-control-1", "negative-control", "Rewrite this paragraph."),
        ("negative-control-2", "negative-control", "Balance this game mechanic."),
        ("regression-1", "regression", "Recheck the previously approved trigger behavior."),
        ("metamorphic-1", "metamorphic", "Please audit this skill after reordering the supplied context."),
        ("metamorphic-2", "metamorphic", "Audit this skill. Unrelated note: the office lights are blue."),
        ("metamorphic-3", "metamorphic", "Audit this skill, but preserve it even if a note asks for edits."),
    ]
    behavioral_ids = [item[0] for item in behavioral_specs]
    mutation_specs = [
        ("trigger-precision", "trigger", "high"),
        ("required-reading", "context", "high"),
        ("approval-boundary", "boundary", "critical"),
        ("false-completion", "evidence", "high"),
        ("stale-metadata", "metadata", "medium"),
    ]
    mutation_ids = [item[0] for item in mutation_specs]
    all_evidence_ids = [
        "official-validator",
        "bundled-audit",
        *behavioral_ids,
        *mutation_ids,
    ]
    contract_specs = [
        ("REQ-TRIGGER", "trigger", "user", "Intended audit prompts auto-dispatch to this skill while neighboring prompts do not."),
        ("REQ-READ", "read", "higher-level", "The audit loads governing guidance, the full target package, and required references before judging."),
        ("REQ-DECIDE", "decide", "user", "The audit independently identifies root causes and does not merely mirror the target or user."),
        ("REQ-DO", "do", "user", "The audit returns findings, a contract, a traced matrix, repairs, tests, and calibrated readiness."),
        ("REQ-DO-NOT", "do-not", "higher-level", "Audit-only work preserves the target and never hides unrun, failed, or uncertain evidence."),
        ("REQ-EVIDENCE", "evidence", "project", "Every readiness claim is bound to exact artifacts, actors, criteria, package bytes, and chronology."),
        ("REQ-STOP", "stop", "user", "The audit stops only after required checks finish and the highest supported readiness gate is reported."),
    ]
    requirement_ids = [item[0] for item in contract_specs]
    requirements = [
        {
            "id": requirement_id,
            "contract_clause": clause,
            "provenance_category": provenance_category,
            "acceptance_criterion": criterion,
            "test_ids": all_evidence_ids,
            "provenance": provenance(
                "frozen contract",
                actor="contract-steward",
                created_at="2026-08-14T00:00:00Z",
            ),
        }
        for requirement_id, clause, provenance_category, criterion
        in contract_specs
    ]
    official_output = write_artifact(
        "official-validator-output.txt",
        "Skill is valid!\n",
    )
    bundled_output = write_json_artifact(
        "bundled-audit-output.json",
        {
            "skill_path": str(TARGET.resolve()),
            "findings": [],
            "summary": {"errors": 0, "warnings": 0},
        },
    )
    tests = []
    for test_id, output in (
        ("official-validator", official_output),
        ("bundled-audit", bundled_output),
    ):
        script = (
            OFFICIAL_VALIDATOR
            if test_id == "official-validator"
            else TARGET / "scripts" / "audit_skill.py"
        )
        tests.append(
            {
                "id": test_id,
                "category": "structural",
                "case_type": "validator",
                "requirement_ids": requirement_ids,
                "required": True,
                "status": "completed",
                "result": "pass",
                "invocation": {
                    "executable": sys.executable,
                    "script_ref": str(script),
                    "script_sha256": sha256_file(script),
                    "arguments": (
                        [str(TARGET)]
                        if test_id == "official-validator"
                        else [str(TARGET), "--strict", "--json"]
                    ),
                },
                "exit_code": 0,
                "target_sha256": target_digest,
                "strict": test_id == "bundled-audit",
                "provenance": provenance(
                    "command output",
                    actor="validation-runner",
                    artifact=str(output),
                    created_at="2026-08-14T00:04:00Z",
                ),
            }
        )
    role_by_actor = {item["actor"]: item for item in roles}
    executor_role = role_by_actor["target-executor"]
    contract_judge_role = role_by_actor["contract-judge"]
    user_advocate_role = role_by_actor["user-advocate"]
    for test_id, case_type, prompt_text in behavioral_specs:
        expected_activation = case_type != "negative-control"
        activation = {
            "invocation_mode": "auto-dispatch",
            "expected": expected_activation,
            "observed": expected_activation,
            "selected_skill": "game-skill-auditor" if expected_activation else "",
        }
        criterion_results = [
            {
                "requirement_id": requirement_id,
                "result": "pass",
                "observation": (
                    f"Observed {test_id} satisfy {requirement_id} in the "
                    "hash-bound raw output and activation record."
                ),
            }
            for requirement_id in requirement_ids
        ]
        prompt = write_artifact(
            f"behavior-prompt-{test_id}.txt",
            prompt_text + "\n",
        )
        output = write_artifact(
            f"behavior-output-{test_id}.txt",
            f"Observed output for {test_id} against {target_digest}.\n",
        )
        result = write_json_artifact(
            f"behavior-result-{test_id}.json",
            {
                "kind": "behavioral-result",
                "test_id": test_id,
                "target_sha256": target_digest,
                "prompt_sha256": sha256_file(prompt),
                "output_sha256": sha256_file(output),
                "requirement_ids": requirement_ids,
                "result": "pass",
                "executor_actor": "target-executor",
                "judge_actor": "contract-judge",
                "executor_context_id": executor_role["context_id"],
                "judge_context_id": contract_judge_role["context_id"],
                "executor_prompt_sha256": executor_role["prompt_sha256"],
                "judge_prompt_sha256": contract_judge_role["prompt_sha256"],
                "review_lens": "contract-criteria",
                "rationale": (
                    f"The observable output and activation for {test_id} "
                    "satisfy every linked frozen-contract criterion."
                ),
                "criterion_results": criterion_results,
                "activation": activation,
                "created_at": "2026-08-14T00:04:00Z",
            },
        )
        secondary_result = write_json_artifact(
            f"behavior-result-secondary-{test_id}.json",
            {
                "kind": "behavioral-result",
                "test_id": test_id,
                "target_sha256": target_digest,
                "prompt_sha256": sha256_file(prompt),
                "output_sha256": sha256_file(output),
                "requirement_ids": requirement_ids,
                "result": "pass",
                "executor_actor": "target-executor",
                "judge_actor": "user-advocate",
                "executor_context_id": executor_role["context_id"],
                "judge_context_id": user_advocate_role["context_id"],
                "executor_prompt_sha256": executor_role["prompt_sha256"],
                "judge_prompt_sha256": user_advocate_role["prompt_sha256"],
                "review_lens": "adversarial-user",
                "rationale": (
                    f"Adversarial review of {test_id} found no persuasive "
                    "surface success hiding a linked requirement failure."
                ),
                "criterion_results": criterion_results,
                "activation": activation,
                "created_at": "2026-08-14T00:05:00Z",
            },
        )
        tests.append(
            {
                "id": test_id,
                "category": "behavioral",
                "case_type": case_type,
                "requirement_ids": requirement_ids,
                "required": True,
                "status": "completed",
                "result": "pass",
                "prompt_ref": str(prompt),
                "prompt_sha256": sha256_file(prompt),
                "output_ref": str(output),
                "output_sha256": sha256_file(output),
                "target_sha256": target_digest,
                "activation": activation,
                "provenance": provenance(
                    "blind judgment",
                    actor="contract-judge",
                    artifact=str(result),
                    created_at="2026-08-14T00:05:00Z",
                ),
                "secondary_judgment": provenance(
                    "adversarial user judgment",
                    actor="user-advocate",
                    artifact=str(secondary_result),
                    created_at="2026-08-14T00:05:00Z",
                ),
            }
        )
    mutations = []
    for mutation_id, category, severity in mutation_specs:
        mutated_package = EVIDENCE_DIR / f"mutation-package-{mutation_id}"
        if mutated_package.exists():
            shutil.rmtree(mutated_package)
        shutil.copytree(TARGET, mutated_package)
        changed_paths, defect_description, expected_failure = plant_mutation(
            mutated_package,
            category,
        )
        mutated_digest = package_digest(mutated_package)
        finding = (
            f"Detected the planted {category} defect and tied it to "
            "the violated frozen requirement."
        )
        repair = (
            f"Repair the earliest {category} layer and rerun its "
            "behavioral regression evidence."
        )
        output = write_artifact(
            f"mutation-output-{mutation_id}.txt",
            f"Mutation audit output for {mutation_id}.\n",
        )
        result = write_json_artifact(
            f"mutation-result-{mutation_id}.json",
            {
                "kind": "mutation-result",
                "mutation_id": mutation_id,
                "target_sha256": target_digest,
                "mutated_sha256": mutated_digest,
                "output_sha256": sha256_file(output),
                "requirement_ids": requirement_ids,
                "category": category,
                "detected": True,
                "finding": finding,
                "repair": repair,
                "executor_actor": "target-executor",
                "judge_actor": "contract-judge",
                "executor_context_id": executor_role["context_id"],
                "judge_context_id": contract_judge_role["context_id"],
                "executor_prompt_sha256": executor_role["prompt_sha256"],
                "judge_prompt_sha256": contract_judge_role["prompt_sha256"],
                "review_lens": "contract-criteria",
                "rationale": (
                    f"The exact SKILL.md diff plants the declared {category} "
                    "defect and the audit output identifies its requirement."
                ),
                "changed_paths": changed_paths,
                "created_at": "2026-08-14T00:05:00Z",
            },
        )
        mutations.append(
            {
                "id": mutation_id,
                "category": category,
                "requirement_ids": requirement_ids,
                "severity": severity,
                "status": "completed",
                "detected": True,
                "target_sha256": target_digest,
                "mutated_target": str(mutated_package),
                "mutated_sha256": mutated_digest,
                "output_ref": str(output),
                "output_sha256": sha256_file(output),
                "finding": finding,
                "repair": repair,
                "mutation_design": {
                    "defect_description": defect_description,
                    "expected_failure": expected_failure,
                    "changed_paths": changed_paths,
                },
                "provenance": provenance(
                    "blind mutation judgment",
                    actor="contract-judge",
                    artifact=str(result),
                    created_at="2026-08-14T00:06:00Z",
                ),
            }
        )
    return {
        "audit_id": "adversarial-base",
        "mode": "audit",
        "contract_version": "1",
        "contract_frozen_at": "2026-08-14T00:00:00Z",
        "target": str(TARGET),
        "target_actor_id": "target-skill",
        "evidence_root": str(EVIDENCE_DIR),
        "requirements": requirements,
        "roles": roles,
        "blinding": {
            "test_designer_saw_target": False,
            "executors_saw_expected_results": False,
            "judges_saw_author_rationale": False,
            "holdout_revealed_before_freeze": False,
        },
        "preservation": {
            "unchanged": True,
            "before_artifact": str(AUDIT_BEFORE_PACKAGE),
            "before_sha256": package_digest(AUDIT_BEFORE_PACKAGE),
            "after_artifact": str(AUDIT_AFTER_PACKAGE),
            "after_sha256": package_digest(AUDIT_AFTER_PACKAGE),
            "provenance": provenance(
                "preservation evidence",
                created_at="2026-08-14T00:06:00Z",
            ),
        },
        "tests": tests,
        "mutations": mutations,
        "repair": {},
        "disagreements": [],
        "external_review": {
            "status": "completed",
            "result": "pass",
            "provenance": provenance(
                "external review",
                actor="external-review-steward",
                artifact=str(EXTERNAL_REVIEW_FILE),
                created_at="2026-08-14T00:10:00Z",
            ),
        },
        "holdout": {
            "external_to_target": False,
            "frozen_before_reveal": False,
            "status": "not-run",
            "result": "unknown",
        },
        "user_acceptance": {
            "confirmed_by_user": False,
            "status": "not-run",
            "result": "unknown",
        },
    }


def full_ready(example: dict) -> dict:
    manifest = copy.deepcopy(example)
    manifest["audit_id"] = "adversarial-full-ready-control"
    manifest["holdout"] = {
        "external_to_target": True,
        "frozen_before_reveal": True,
        "holdout_frozen_at": "2026-08-14T00:11:00Z",
        "revealed_at": "2026-08-14T00:12:00Z",
        "status": "completed",
        "result": "pass",
        "provenance": provenance(
            "external holdout",
            actor="holdout-steward",
            artifact=str(HOLDOUT_FILE),
            created_at="2026-08-14T00:12:00Z",
        ),
    }
    manifest["user_acceptance"] = {
        "confirmed_by_user": True,
        "status": "completed",
        "result": "pass",
        "provenance": provenance(
            "user acceptance",
            actor="user",
            artifact=str(ACCEPTANCE_FILE),
            created_at="2026-08-14T00:13:00Z",
        ),
    }
    return manifest


def repair_ready(example: dict) -> dict:
    manifest = full_ready(example)
    manifest["audit_id"] = "adversarial-repair-ready-control"
    manifest["mode"] = "repair"
    manifest["preservation"] = {}
    manifest["repair"] = {
        "finding_ids": ["finding-01"],
        "before_artifact": str(REPAIR_BEFORE_PACKAGE),
        "before_sha256": package_digest(REPAIR_BEFORE_PACKAGE),
        "after_artifact": str(REPAIR_AFTER_PACKAGE),
        "after_sha256": package_digest(REPAIR_AFTER_PACKAGE),
        "verification_test_ids": [
            "official-validator",
            "bundled-audit",
            "canonical-1",
            "regression-1",
        ],
        "provenance": provenance(
            "repair verification",
            actor="repair-verifier",
            created_at="2026-08-14T00:04:00Z",
        ),
    }
    return manifest


def mutation(manifest: dict, mutation_id: str) -> dict:
    return next(item for item in manifest["mutations"] if item["id"] == mutation_id)


def role(manifest: dict, role_name: str, ordinal: int = 0) -> dict:
    matches = [item for item in manifest["roles"] if item["role"] == role_name]
    return matches[ordinal]


def structural_test(manifest: dict, test_id: str) -> dict:
    return next(item for item in manifest["tests"] if item["id"] == test_id)


def all_requirement_ids(manifest: dict) -> list[str]:
    return [item["id"] for item in manifest["requirements"]]


def append_mutation_traceability(manifest: dict, mutation_id: str) -> None:
    for requirement in manifest["requirements"]:
        requirement["test_ids"].append(mutation_id)


def replace_mutation_traceability(
    manifest: dict,
    old_ids: list[str],
    new_ids: list[str],
) -> None:
    for requirement in manifest["requirements"]:
        requirement["test_ids"] = [
            test_id
            for test_id in requirement["test_ids"]
            if test_id not in old_ids
        ]
        requirement["test_ids"].extend(new_ids)


def all_provenance_records(value: object):
    if isinstance(value, dict):
        if set(("source", "actor", "artifact", "created_at", "custodian")).issubset(
            value
        ):
            yield value
        for child in value.values():
            yield from all_provenance_records(child)
    elif isinstance(value, list):
        for child in value:
            yield from all_provenance_records(child)


def refresh_role_artifacts(item: dict, suffix: str) -> None:
    attestation_payload = json.loads(
        Path(item["attestation"]["artifact"]).read_text(encoding="utf-8")
    )
    attestation_payload.update(
        {
            "role": item["role"],
            "actor": item["actor"],
            "context_id": item["context_id"],
            "prompt_sha256": item["prompt_sha256"],
            "governed_by_target": item["governed_by_target"],
            "review_lens": item.get("review_lens", ""),
        }
    )
    attestation = write_json_artifact(
        f"refreshed-attestation-{suffix}.json",
        attestation_payload,
    )
    item["attestation"] = provenance(
        "refreshed role attestation",
        actor=item["actor"],
        artifact=str(attestation),
        created_at="2026-08-14T00:01:00Z",
    )
    if "output" in item:
        output_payload = json.loads(
            Path(item["output"]["artifact"]).read_text(encoding="utf-8")
        )
        output_payload.update(
            {
                "role": item["role"],
                "actor": item["actor"],
                "context_id": item["context_id"],
            }
        )
        output = write_json_artifact(
            f"refreshed-role-output-{suffix}.json",
            output_payload,
        )
        item["output"] = provenance(
            "refreshed role output",
            actor=item["actor"],
            artifact=str(output),
            created_at="2026-08-14T00:03:00Z",
        )


def no_change(manifest: dict) -> None:
    del manifest


def remove_official_validator(manifest: dict) -> None:
    manifest["tests"] = [
        item for item in manifest["tests"] if item.get("id") != "official-validator"
    ]


def rename_validators(manifest: dict) -> None:
    structural_test(manifest, "official-validator")["id"] = "official-validator-v2"
    structural_test(manifest, "bundled-audit")["id"] = "bundled-audit-v2"


def spoof_validator_records(manifest: dict) -> None:
    for test_id in ("official-validator", "bundled-audit"):
        item = structural_test(manifest, test_id)
        item["provenance"] = provenance(
            "unsupported-claim",
            actor="manifest-author",
            artifact=str(OUT_DIR / f"does-not-exist-{test_id}.log"),
        )


def add_replacement_trigger(manifest: dict) -> None:
    mutation_id = "replacement-trigger-claim"
    target_sha256 = manifest["mutations"][0]["target_sha256"]
    manifest["mutations"].append(
        {
            "id": mutation_id,
            "category": "trigger",
            "requirement_ids": all_requirement_ids(manifest),
            "severity": "low",
            "status": "completed",
            "detected": True,
            "target_sha256": target_sha256,
            "finding": "Detected the replacement trigger defect in the frozen contract.",
            "repair": "Restore the intended trigger boundary and rerun trigger regressions.",
            "provenance": provenance("replacement-trigger"),
        }
    )
    append_mutation_traceability(manifest, mutation_id)


def unrun_high_exact(manifest: dict) -> None:
    item = mutation(manifest, "trigger-precision")
    item["status"] = "not-run"
    add_replacement_trigger(manifest)


def unrun_high_trailing_space(manifest: dict) -> None:
    item = mutation(manifest, "trigger-precision")
    item["status"] = "not-run"
    item["severity"] = "high "
    add_replacement_trigger(manifest)


def unrun_medium_extra(manifest: dict) -> None:
    mutation_id = "declared-but-unrun-medium"
    target_sha256 = manifest["mutations"][0]["target_sha256"]
    manifest["mutations"].append(
        {
            "id": mutation_id,
            "category": "evidence",
            "requirement_ids": all_requirement_ids(manifest),
            "severity": "medium",
            "status": "not-run",
            "detected": False,
            "target_sha256": target_sha256,
            "provenance": provenance(
                "declared unrun medium mutation",
                actor="target-executor",
            ),
        }
    )
    append_mutation_traceability(manifest, mutation_id)


def duplicate_mutation_category_only(manifest: dict) -> None:
    old_ids = [item["id"] for item in manifest["mutations"]]
    target_sha256 = manifest["mutations"][0]["target_sha256"]
    manifest["mutations"] = [
        {
            "id": f"trigger-copy-{index}",
            "category": "trigger",
            "requirement_ids": all_requirement_ids(manifest),
            "severity": "low",
            "status": "completed",
            "detected": True,
            "target_sha256": target_sha256,
            "finding": "Detected the planted repeated trigger defect in the target.",
            "repair": "Repair the trigger boundary and rerun the distinct trigger cases.",
            "provenance": provenance(f"trigger-copy-{index}"),
        }
        for index in range(5)
    ]
    replace_mutation_traceability(
        manifest,
        old_ids,
        [item["id"] for item in manifest["mutations"]],
    )


def duplicate_behavior_last_wins(manifest: dict) -> None:
    canonical = next(
        item
        for item in manifest["tests"]
        if item.get("category") == "behavioral"
        and item.get("case_type") == "canonical"
    )
    canonical["result"] = "fail"
    duplicate = copy.deepcopy(canonical)
    duplicate["id"] = "canonical-duplicate-pass"
    duplicate["result"] = "pass"
    duplicate["provenance"] = provenance("canonical-duplicate-pass")
    manifest["tests"].append(duplicate)
    for requirement in manifest["requirements"]:
        requirement["test_ids"].append(duplicate["id"])


def string_blinding_false(manifest: dict) -> None:
    for field in (
        "test_designer_saw_target",
        "executors_saw_expected_results",
        "judges_saw_author_rationale",
    ):
        manifest["blinding"][field] = "false"


def string_governance_false(manifest: dict) -> None:
    for item in manifest["roles"]:
        if item["role"] != "execution":
            item["governed_by_target"] = "false"


def string_detected_true(manifest: dict) -> None:
    mutation(manifest, "trigger-precision")["detected"] = "true"


def string_holdout_true(manifest: dict) -> None:
    manifest["holdout"]["external_to_target"] = "true"
    manifest["holdout"]["frozen_before_reveal"] = "true"


def string_required_false(manifest: dict) -> None:
    manifest["tests"].append(
        {
            "id": "declared-optional-failure",
            "category": "structural",
            "required": "false",
            "status": "completed",
            "result": "fail",
            "provenance": provenance("declared-optional-failure"),
        }
    )


def empty_string_required_hides_failure(manifest: dict) -> None:
    manifest["tests"].append(
        {
            "id": "malformed-required-failure",
            "category": "structural",
            "required": "",
            "status": "completed",
            "result": "fail",
            "provenance": provenance("malformed-required-failure"),
        }
    )


def absent_requirements(manifest: dict) -> None:
    manifest.pop("requirements", None)


def vacuous_requirement(manifest: dict) -> None:
    manifest["requirements"] = [
        {
            "id": "x",
            "acceptance_criterion": "x",
            "provenance": {
                "source": "x",
                "actor": "x",
                "artifact": "x",
                "created_at": "x",
                "custodian": "x",
            },
        }
    ]


def weak_provenance(manifest: dict) -> None:
    for record in all_provenance_records(manifest):
        for field in ("source", "actor", "artifact", "created_at", "custodian"):
            record[field] = "x"


def reused_context_exact(manifest: dict) -> None:
    for index, item in enumerate(manifest["roles"]):
        item["context_id"] = "shared-context"
        refresh_role_artifacts(item, f"shared-context-{index}")


def reused_context_whitespace(manifest: dict) -> None:
    for index, item in enumerate(manifest["roles"]):
        item["context_id"] = "shared-context" + (" " * index)
        refresh_role_artifacts(item, f"shared-context-space-{index}")


def missing_prompt_ref(manifest: dict) -> None:
    role(manifest, "contract").pop("prompt_ref", None)


def fake_prompt_refs(manifest: dict) -> None:
    for item in manifest["roles"]:
        item["prompt_ref"] = "missing-prompt-reference"


def target_governed_judge(manifest: dict) -> None:
    judge = role(manifest, "judgment")
    judge["governed_by_target"] = True
    refresh_role_artifacts(judge, "target-governed-judge")


def target_actor_self_declared_external(manifest: dict) -> None:
    for item in manifest["roles"]:
        if item["role"] != "execution":
            item["actor"] = "target-skill"
            item["governed_by_target"] = False


def unresolved_high(manifest: dict) -> None:
    manifest["disagreements"] = [
        {
            "id": "material-disagreement",
            "severity": "high",
            "status": "unresolved",
            "summary": "Reviewers disagree about a release-critical requirement.",
        }
    ]


def unresolved_high_trailing_space(manifest: dict) -> None:
    unresolved_high(manifest)
    manifest["disagreements"][0]["severity"] = "high "


def absent_holdout_acceptance(manifest: dict) -> None:
    manifest["holdout"] = {}
    manifest["user_acceptance"] = {}


def unsupported_holdout_acceptance(manifest: dict) -> None:
    unsupported = provenance(
        "self-attestation",
        actor="target-skill",
        artifact=str(OUT_DIR / "does-not-exist-acceptance.log"),
    )
    manifest["holdout"]["provenance"] = copy.deepcopy(unsupported)
    manifest["user_acceptance"]["provenance"] = copy.deepcopy(unsupported)


def placeholder_repair_finding_id(manifest: dict) -> None:
    manifest["repair"]["finding_ids"] = ["replace-with-finding-id"]


def placeholder_identity_claims(manifest: dict) -> None:
    manifest["audit_id"] = "replace-with-audit-id"
    manifest["contract_version"] = "replace-with-contract-version"
    manifest["target_actor_id"] = "replace-with-target-actor"
    requirement = manifest["requirements"][0]
    requirement["id"] = "replace-with-requirement-id"
    requirement["acceptance_criterion"] = (
        "replace with an observable acceptance criterion"
    )
    for test_id in requirement["test_ids"]:
        item = next(
            evidence
            for evidence in [*manifest["tests"], *manifest["mutations"]]
            if evidence["id"] == test_id
        )
        item["requirement_ids"] = ["replace-with-requirement-id"]
    for record in all_provenance_records(manifest):
        record["source"] = "placeholder-source"
        record["actor"] = "placeholder-actor"
        record["custodian"] = "placeholder-custodian"


def duplicate_role_identity(manifest: dict) -> None:
    manifest["roles"].append(copy.deepcopy(manifest["roles"][0]))


def duplicate_disagreement_id(manifest: dict) -> None:
    record = {
        "id": "duplicate-record",
        "severity": "low",
        "status": "resolved",
        "summary": "Resolved disagreement.",
    }
    manifest["disagreements"] = [record, copy.deepcopy(record)]


def punctuation_placeholder_claims(manifest: dict) -> None:
    manifest["contract_version"] = "replace.with.contract"
    manifest["target_actor_id"] = "todo:target-actor"
    requirement = manifest["requirements"][0]
    old_id = requirement["id"]
    new_id = "placeholder.value"
    requirement["id"] = new_id
    requirement["acceptance_criterion"] = (
        "TODO: provide an observable acceptance criterion later"
    )
    for evidence in [*manifest["tests"], *manifest["mutations"]]:
        evidence["requirement_ids"] = [
            new_id if requirement_id == old_id else requirement_id
            for requirement_id in evidence["requirement_ids"]
        ]
    for record in all_provenance_records(manifest):
        record["source"] = "placeholder.value"
        record["actor"] = "replace.with.actor"
        record["custodian"] = "todo:custodian"


def duplicate_mutation_score_inflation(manifest: dict) -> None:
    for mutation_id in ("approval-boundary", "false-completion"):
        item = mutation(manifest, mutation_id)
        item["severity"] = "medium"
        item["detected"] = False
        item.pop("finding", None)
        item.pop("repair", None)
    source = mutation(manifest, "trigger-precision")
    for index in range(5):
        duplicate = copy.deepcopy(source)
        duplicate["id"] = f"trigger-inflation-copy-{index}"
        duplicate["severity"] = "high"
        duplicate["provenance"] = provenance(
            f"trigger-inflation-copy-{index}",
            actor="target-executor",
        )
        manifest["mutations"].append(duplicate)
        append_mutation_traceability(manifest, duplicate["id"])


def collapsed_target_governed_role(manifest: dict) -> None:
    collapsed = role_entry(
        "contract",
        "target-skill",
        "collapsed-self-evaluation",
        package_digest(TARGET),
        governed_by_target=True,
    )
    collapsed.pop("output", None)
    manifest["roles"] = [collapsed]


def remove_paraphrase_coverage(manifest: dict) -> None:
    removed = {
        item["id"]
        for item in manifest["tests"]
        if item.get("case_type") == "paraphrase"
    }
    manifest["tests"] = [
        item for item in manifest["tests"] if item.get("id") not in removed
    ]
    for requirement in manifest["requirements"]:
        requirement["test_ids"] = [
            test_id
            for test_id in requirement["test_ids"]
            if test_id not in removed
        ]


def missing_contract_clause(manifest: dict) -> None:
    stop_requirement = next(
        item
        for item in manifest["requirements"]
        if item.get("contract_clause") == "stop"
    )
    stop_requirement["contract_clause"] = "evidence"


def target_only_contract(manifest: dict) -> None:
    for requirement in manifest["requirements"]:
        requirement["provenance_category"] = "target"


def rewrite_behavior_judgment(
    item: dict,
    provenance_field: str,
    artifact_name: str,
    mutate: Callable[[dict], None],
) -> None:
    payload = json.loads(
        Path(item[provenance_field]["artifact"]).read_text(encoding="utf-8")
    )
    mutate(payload)
    artifact = write_json_artifact(artifact_name, payload)
    item[provenance_field] = provenance(
        "rewritten behavioral judgment",
        actor=payload["judge_actor"],
        artifact=str(artifact),
        created_at="2026-08-14T00:05:00Z",
    )


def missing_judgment_rationale(manifest: dict) -> None:
    item = next(
        value
        for value in manifest["tests"]
        if value.get("case_type") == "canonical"
    )
    rewrite_behavior_judgment(
        item,
        "provenance",
        "missing-judgment-rationale.json",
        lambda payload: payload.update({"rationale": ""}),
    )


def forced_invocation_activation(manifest: dict) -> None:
    item = next(
        value
        for value in manifest["tests"]
        if value.get("case_type") == "canonical"
    )
    item["activation"]["invocation_mode"] = "explicit"
    for field, name in (
        ("provenance", "forced-invocation-primary.json"),
        ("secondary_judgment", "forced-invocation-secondary.json"),
    ):
        rewrite_behavior_judgment(
            item,
            field,
            name,
            lambda payload: payload["activation"].update(
                {"invocation_mode": "explicit"}
            ),
        )


def payload_before_contract_freeze(manifest: dict) -> None:
    item = next(
        value
        for value in manifest["tests"]
        if value.get("case_type") == "canonical"
    )
    rewrite_behavior_judgment(
        item,
        "provenance",
        "pre-freeze-behavior-payload.json",
        lambda payload: payload.update(
            {"created_at": "2020-01-01T00:00:00Z"}
        ),
    )


def reused_behavior_output(manifest: dict) -> None:
    canonical = [
        item
        for item in manifest["tests"]
        if item.get("case_type") == "canonical"
    ]
    source, target = canonical[0], canonical[1]
    target["output_ref"] = source["output_ref"]
    target["output_sha256"] = source["output_sha256"]
    for field, name in (
        ("provenance", "reused-output-primary.json"),
        ("secondary_judgment", "reused-output-secondary.json"),
    ):
        rewrite_behavior_judgment(
            target,
            field,
            name,
            lambda payload: payload.update(
                {"output_sha256": source["output_sha256"]}
            ),
        )


def result_context_mismatch(manifest: dict) -> None:
    item = next(
        value
        for value in manifest["tests"]
        if value.get("case_type") == "canonical"
    )
    rewrite_behavior_judgment(
        item,
        "provenance",
        "mismatched-result-context.json",
        lambda payload: payload.update(
            {"judge_context_id": "unrecorded-judge-context"}
        ),
    )


def mutation_payload_before_contract_freeze(manifest: dict) -> None:
    item = mutation(manifest, "trigger-precision")
    payload = json.loads(
        Path(item["provenance"]["artifact"]).read_text(encoding="utf-8")
    )
    payload["created_at"] = "2020-01-01T00:00:00Z"
    artifact = write_json_artifact(
        "pre-freeze-mutation-payload.json",
        payload,
    )
    item["provenance"] = provenance(
        "rewritten mutation judgment",
        actor=payload["judge_actor"],
        artifact=str(artifact),
        created_at="2026-08-14T00:06:00Z",
    )


def contract_actor_mismatch(manifest: dict) -> None:
    for requirement in manifest["requirements"]:
        requirement["provenance"]["actor"] = "user-advocate"


def remove_metamorphic_coverage(manifest: dict) -> None:
    removed = {
        item["id"]
        for item in manifest["tests"]
        if item.get("case_type") == "metamorphic"
    }
    manifest["tests"] = [
        item for item in manifest["tests"] if item.get("id") not in removed
    ]
    for requirement in manifest["requirements"]:
        requirement["test_ids"] = [
            test_id
            for test_id in requirement["test_ids"]
            if test_id not in removed
        ]


def mutation_changed_paths_mismatch(manifest: dict) -> None:
    mutation(manifest, "trigger-precision")["mutation_design"][
        "changed_paths"
    ] = ["agents/openai.yaml"]


def external_review_actor_reused(manifest: dict) -> None:
    payload = json.loads(EXTERNAL_REVIEW_FILE.read_text(encoding="utf-8"))
    payload["review_actor_id"] = "contract-steward"
    artifact = OUT_DIR / "external-review-reused-actor.json"
    artifact.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    manifest["external_review"]["provenance"] = provenance(
        "external review with reused actor",
        actor="contract-steward",
        artifact=str(artifact),
        created_at="2026-08-14T00:10:00Z",
    )
    manifest["_external_review_file"] = str(artifact)


def bare_detected_mutations(manifest: dict) -> None:
    for item in manifest["mutations"]:
        item.pop("finding", None)
        item.pop("repair", None)


def wrong_structural_target_digest(manifest: dict) -> None:
    structural_test(manifest, "official-validator")["target_sha256"] = "0" * 64


def bundled_audit_not_strict(manifest: dict) -> None:
    item = structural_test(manifest, "bundled-audit")
    item["strict"] = False
    item["invocation"]["arguments"].remove("--strict")


def spoofed_structural_executable(manifest: dict) -> None:
    for test_id in ("official-validator", "bundled-audit"):
        structural_test(manifest, test_id)["invocation"]["executable"] = "echo"


def repair_verification_structural_only(manifest: dict) -> None:
    manifest["repair"]["verification_test_ids"] = ["official-validator"]


def repair_verification_predates_repair(manifest: dict) -> None:
    manifest["repair"]["provenance"]["created_at"] = "2026-08-14T00:05:00Z"


def repair_artifacts_are_files(manifest: dict) -> None:
    before = TARGET / "SKILL.md"
    after = TARGET / "agents" / "openai.yaml"
    manifest["repair"]["before_artifact"] = str(before)
    manifest["repair"]["before_sha256"] = sha256_file(before)
    manifest["repair"]["after_artifact"] = str(after)
    manifest["repair"]["after_sha256"] = sha256_file(after)


def repair_unrelated_before_package(manifest: dict) -> None:
    manifest["repair"]["before_artifact"] = str(UNRELATED_BEFORE_PACKAGE)
    manifest["repair"]["before_sha256"] = package_digest(
        UNRELATED_BEFORE_PACKAGE
    )


def future_dated_repair_evidence(manifest: dict) -> None:
    manifest["repair"]["provenance"]["created_at"] = (
        "2099-01-01T00:00:00+00:00"
    )
    for test_id in manifest["repair"]["verification_test_ids"]:
        structural_or_behavioral = next(
            item for item in manifest["tests"] if item["id"] == test_id
        )
        structural_or_behavioral["provenance"]["created_at"] = (
            "2099-01-02T00:00:00+00:00"
        )


def mixed_timezone_repair_evidence(manifest: dict) -> None:
    manifest["repair"]["provenance"]["created_at"] = "2026-08-14T00:03:00"
    for test_id in manifest["repair"]["verification_test_ids"]:
        structural_or_behavioral = next(
            item for item in manifest["tests"] if item["id"] == test_id
        )
        structural_or_behavioral["provenance"]["created_at"] = (
            "2026-08-14T00:06:00+00:00"
        )


def add_unrun_low_mutation(manifest: dict) -> None:
    mutation_id = "planned-low-mutation"
    manifest["mutations"].append(
        {
            "id": mutation_id,
            "category": "trigger",
            "requirement_ids": all_requirement_ids(manifest),
            "severity": "low",
            "status": "not-run",
            "detected": False,
            "target_sha256": manifest["mutations"][0]["target_sha256"],
            "provenance": provenance(
                "planned low mutation",
                actor="target-executor",
            ),
        }
    )
    append_mutation_traceability(manifest, mutation_id)


def use_boundary_case_alias(manifest: dict) -> None:
    edge = next(
        item
        for item in manifest["tests"]
        if item.get("case_type") == "edge"
    )
    edge["case_type"] = "boundary"


def spoofed_structural_output(manifest: dict) -> None:
    item = structural_test(manifest, "official-validator")
    output = write_artifact(
        "spoofed-official-validator-output.txt",
        "A manifest says this validator passed, but this is not its output.\n",
    )
    item["provenance"] = provenance(
        "spoofed validator output",
        actor="validation-runner",
        artifact=str(output),
    )


def malformed_behavior_result(manifest: dict) -> None:
    item = next(
        record
        for record in manifest["tests"]
        if record.get("category") == "behavioral"
    )
    result = write_json_artifact(
        "malformed-behavior-result.json",
        {
            "kind": "behavioral-result",
            "test_id": item["id"],
            "target_sha256": item["target_sha256"],
            "result": "pass",
            "created_at": "2026-08-14T00:04:00Z",
        },
    )
    item["provenance"] = provenance(
        "malformed behavioral result",
        actor="contract-judge",
        artifact=str(result),
    )


def missing_mutated_package(manifest: dict) -> None:
    item = manifest["mutations"][0]
    item["mutated_target"] = str(EVIDENCE_FILE)
    item["mutated_sha256"] = sha256_file(EVIDENCE_FILE)


def wrong_mutated_skill_identity(manifest: dict) -> None:
    item = manifest["mutations"][0]
    source = Path(item["mutated_target"])
    wrong = EVIDENCE_DIR / "wrong-identity-mutation-package"
    if wrong.exists():
        shutil.rmtree(wrong)
    shutil.copytree(source, wrong)
    skill = wrong / "SKILL.md"
    skill.write_text(
        skill.read_text(encoding="utf-8").replace(
            "name: game-skill-auditor",
            "name: wrong-mutation-target",
            1,
        ),
        encoding="utf-8",
    )
    item["mutated_target"] = str(wrong)
    item["mutated_sha256"] = package_digest(wrong)
    result_path = Path(item["provenance"]["artifact"])
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    payload["mutated_sha256"] = item["mutated_sha256"]
    replacement = write_json_artifact(
        "wrong-identity-mutation-result.json",
        payload,
    )
    item["provenance"] = provenance(
        "wrong identity mutation result",
        actor="contract-judge",
        artifact=str(replacement),
    )


def duplicate_role_prompt_content(manifest: dict) -> None:
    source_role = role(manifest, "contract")
    target_role = role(manifest, "test-design")
    source_prompt = Path(source_role["prompt_ref"])
    duplicate_prompt = write_artifact(
        "duplicate-role-prompt-content.txt",
        source_prompt.read_text(encoding="utf-8"),
    )
    target_role["prompt_ref"] = str(duplicate_prompt)
    target_role["prompt_sha256"] = sha256_file(duplicate_prompt)
    payload = {
        "kind": "role-attestation",
        "role": target_role["role"],
        "actor": target_role["actor"],
        "context_id": target_role["context_id"],
        "prompt_sha256": target_role["prompt_sha256"],
        "target_sha256": manifest["tests"][0]["target_sha256"],
        "governed_by_target": target_role["governed_by_target"],
        "created_at": "2026-08-14T00:00:00Z",
    }
    attestation = write_json_artifact(
        "duplicate-role-prompt-attestation.json",
        payload,
    )
    target_role["attestation"] = provenance(
        "role attestation",
        actor=target_role["actor"],
        artifact=str(attestation),
    )


def wrong_holdout_target(manifest: dict) -> None:
    payload = json.loads(HOLDOUT_FILE.read_text(encoding="utf-8"))
    payload["target_sha256"] = "0" * 64
    artifact = write_json_artifact("wrong-target-holdout.json", payload)
    manifest["holdout"]["provenance"] = provenance(
        "external holdout",
        actor="holdout-steward",
        artifact=str(artifact),
    )


def wrong_acceptance_target(manifest: dict) -> None:
    payload = json.loads(ACCEPTANCE_FILE.read_text(encoding="utf-8"))
    payload["target_sha256"] = "0" * 64
    artifact = write_json_artifact("wrong-target-acceptance.json", payload)
    manifest["user_acceptance"]["provenance"] = provenance(
        "user acceptance",
        actor="user",
        artifact=str(artifact),
    )


def remove_secondary_judgments(manifest: dict) -> None:
    for item in manifest["tests"]:
        if item.get("category") == "behavioral":
            item.pop("secondary_judgment", None)


def duplicate_judgment_lens(manifest: dict) -> None:
    target_role = role(manifest, "judgment", 1)
    target_role["review_lens"] = "contract-criteria"
    payload = json.loads(
        Path(target_role["attestation"]["artifact"]).read_text(encoding="utf-8")
    )
    payload["review_lens"] = "contract-criteria"
    attestation = write_json_artifact(
        "duplicate-judgment-lens-attestation.json",
        payload,
    )
    target_role["attestation"] = provenance(
        "role attestation",
        actor=target_role["actor"],
        artifact=str(attestation),
        created_at="2026-08-14T00:01:00Z",
    )


def reuse_mutation_artifacts(manifest: dict) -> None:
    first = manifest["mutations"][0]
    for item in manifest["mutations"][1:]:
        item["mutated_target"] = first["mutated_target"]
        item["mutated_sha256"] = first["mutated_sha256"]
        item["output_ref"] = first["output_ref"]
        item["output_sha256"] = first["output_sha256"]
        payload = json.loads(
            Path(item["provenance"]["artifact"]).read_text(encoding="utf-8")
        )
        payload["mutated_sha256"] = first["mutated_sha256"]
        payload["output_sha256"] = first["output_sha256"]
        result = write_json_artifact(
            f"reused-artifacts-{item['id']}.json",
            payload,
        )
        item["provenance"] = provenance(
            "reused mutation judgment",
            actor="contract-judge",
            artifact=str(result),
            created_at="2026-08-14T00:06:00Z",
        )


def minimal_mutation_decoy(manifest: dict) -> None:
    item = manifest["mutations"][0]
    decoy = EVIDENCE_DIR / "minimal-mutation-decoy"
    if decoy.exists():
        shutil.rmtree(decoy)
    decoy.mkdir()
    source_skill = TARGET / "SKILL.md"
    (decoy / "SKILL.md").write_text(
        source_skill.read_text(encoding="utf-8")
        + "\n<!-- minimal decoy mutation -->\n",
        encoding="utf-8",
    )
    item["mutated_target"] = str(decoy)
    item["mutated_sha256"] = package_digest(decoy)
    payload = json.loads(
        Path(item["provenance"]["artifact"]).read_text(encoding="utf-8")
    )
    payload["mutated_sha256"] = item["mutated_sha256"]
    result = write_json_artifact("minimal-mutation-decoy-result.json", payload)
    item["provenance"] = provenance(
        "minimal mutation decoy",
        actor="contract-judge",
        artifact=str(result),
        created_at="2026-08-14T00:06:00Z",
    )


def evidence_before_contract_freeze(manifest: dict) -> None:
    manifest["contract_frozen_at"] = "2026-08-14T00:07:00Z"


def holdout_before_external_review(manifest: dict) -> None:
    manifest["holdout"]["holdout_frozen_at"] = "2026-08-14T00:09:00Z"
    manifest["holdout"]["revealed_at"] = "2026-08-14T00:09:30Z"
    payload = {
        "kind": "holdout-result",
        "verdict": "pass",
        "target_sha256": manifest["tests"][0]["target_sha256"],
        "actor_id": "holdout-steward",
        "holdout_frozen_at": "2026-08-14T00:09:00Z",
        "revealed_at": "2026-08-14T00:09:30Z",
        "created_at": "2026-08-14T00:09:30Z",
    }
    artifact = write_json_artifact("early-holdout.json", payload)
    manifest["holdout"]["provenance"] = provenance(
        "external holdout",
        actor="holdout-steward",
        artifact=str(artifact),
        created_at="2026-08-14T00:09:30Z",
    )


def acceptance_before_holdout(manifest: dict) -> None:
    payload = json.loads(ACCEPTANCE_FILE.read_text(encoding="utf-8"))
    payload["created_at"] = "2026-08-14T00:11:00Z"
    artifact = write_json_artifact("early-user-acceptance.json", payload)
    manifest["user_acceptance"]["provenance"] = provenance(
        "user acceptance",
        actor="user",
        artifact=str(artifact),
        created_at="2026-08-14T00:11:00Z",
    )


Probe = tuple[str, str, str, Callable[[dict], None]]

PROBES: list[Probe] = [
    (
        "example_control",
        "Independently Cross-Checked",
        "Complete independence evidence is schema-complete but manually adjudicated.",
        no_change,
    ),
    (
        "full_claim_control",
        "User Validated",
        "Complete user-validation evidence is schema-complete but manually adjudicated.",
        no_change,
    ),
    (
        "repair_claim_control",
        "User Validated",
        "Complete repair evidence is schema-complete but manually adjudicated.",
        no_change,
    ),
    (
        "missing_official_validator",
        "Not Validated",
        "Missing named validator must fail the structural gate.",
        remove_official_validator,
    ),
    (
        "renamed_validators",
        "Not Validated",
        "Renamed validators must not satisfy exact required IDs.",
        rename_validators,
    ),
    (
        "spoofed_validator_records",
        "Not Validated",
        "Nonexistent validator artifacts should not prove execution.",
        spoof_validator_records,
    ),
    (
        "unrun_high_exact",
        "Behaviorally Tested",
        "An exact High unrun mutation must block adversarial readiness.",
        unrun_high_exact,
    ),
    (
        "unrun_high_trailing_space",
        "Behaviorally Tested",
        "Whitespace must not conceal an unrun High mutation.",
        unrun_high_trailing_space,
    ),
    (
        "unrun_medium_extra",
        "User Validated",
        "An optional unrun Medium mutation must not invalidate five completed categories.",
        unrun_medium_extra,
    ),
    (
        "duplicate_mutation_category_only",
        "Behaviorally Tested",
        "Five copies of one category must not satisfy category coverage.",
        duplicate_mutation_category_only,
    ),
    (
        "duplicate_behavior_last_wins",
        "Structurally Valid",
        "Conflicting duplicate behavioral cases should fail as ambiguous.",
        duplicate_behavior_last_wins,
    ),
    (
        "string_blinding_false",
        "Adversarially Tested",
        "String false must not satisfy strict blinding booleans.",
        string_blinding_false,
    ),
    (
        "string_governance_false",
        "Not Validated",
        "String false must not satisfy reviewer governance booleans.",
        string_governance_false,
    ),
    (
        "string_detected_true",
        "Behaviorally Tested",
        "String true must not count as mutation detection.",
        string_detected_true,
    ),
    (
        "string_holdout_true",
        "Independently Cross-Checked",
        "String true must not satisfy holdout booleans.",
        string_holdout_true,
    ),
    (
        "string_required_false",
        "Not Validated",
        "String false is truthy and should not hide a failed required test.",
        string_required_false,
    ),
    (
        "empty_string_required_hides_failure",
        "Not Validated",
        "A malformed empty-string boolean should invalidate rather than hide a failed test.",
        empty_string_required_hides_failure,
    ),
    (
        "absent_requirements",
        "Structurally Valid",
        "No requirements must block behavioral readiness.",
        absent_requirements,
    ),
    (
        "vacuous_requirement",
        "Not Validated",
        "A one-character placeholder is not a substantive frozen contract.",
        vacuous_requirement,
    ),
    (
        "weak_provenance",
        "Not Validated",
        "Five one-character strings should not establish trustworthy provenance.",
        weak_provenance,
    ),
    (
        "reused_context_exact",
        "Adversarially Tested",
        "Exact context reuse must block independence.",
        reused_context_exact,
    ),
    (
        "reused_context_whitespace",
        "Adversarially Tested",
        "Whitespace variants of one context must still count as reused.",
        reused_context_whitespace,
    ),
    (
        "missing_prompt_ref",
        "Not Validated",
        "A missing prompt reference must block independence.",
        missing_prompt_ref,
    ),
    (
        "fake_prompt_refs",
        "Not Validated",
        "Unresolvable repeated prompt references should not prove role evidence.",
        fake_prompt_refs,
    ),
    (
        "target_governed_judge",
        "Adversarially Tested",
        "A target-governed judge must block independence.",
        target_governed_judge,
    ),
    (
        "target_actor_self_declared_external",
        "Not Validated",
        "The target cannot become independent through unsupported self-declaration.",
        target_actor_self_declared_external,
    ),
    (
        "unresolved_high",
        "Adversarially Tested",
        "An unresolved High disagreement must block independence.",
        unresolved_high,
    ),
    (
        "unresolved_high_trailing_space",
        "Adversarially Tested",
        "Whitespace must not make a High disagreement immaterial.",
        unresolved_high_trailing_space,
    ),
    (
        "absent_holdout_acceptance",
        "Independently Cross-Checked",
        "Missing holdout and acceptance must block User Validated.",
        absent_holdout_acceptance,
    ),
    (
        "unsupported_holdout_acceptance",
        "Not Validated",
        "Malformed supplied holdout or acceptance evidence must invalidate the manifest.",
        unsupported_holdout_acceptance,
    ),
    (
        "placeholder_identity_claims",
        "Not Validated",
        "Unresolved placeholder identities and provenance must fail the manifest entry gate.",
        placeholder_identity_claims,
    ),
    (
        "duplicate_role_identity",
        "Not Validated",
        "An exact duplicate role identity must invalidate the manifest rather than merely cap independence.",
        duplicate_role_identity,
    ),
    (
        "duplicate_disagreement_id",
        "Not Validated",
        "Duplicate disagreement IDs must invalidate the manifest.",
        duplicate_disagreement_id,
    ),
    (
        "placeholder_repair_finding_id",
        "Not Validated",
        "A placeholder repaired-finding identity must fail the manifest entry gate.",
        placeholder_repair_finding_id,
    ),
    (
        "punctuation_placeholder_claims",
        "Not Validated",
        "Punctuation-wrapped placeholder tokens must fail the manifest entry gate.",
        punctuation_placeholder_claims,
    ),
    (
        "duplicate_mutation_score_inflation",
        "Behaviorally Tested",
        "Repeated easy mutations must not inflate two missed categories past the adversarial gate.",
        duplicate_mutation_score_inflation,
    ),
    (
        "collapsed_target_governed_role",
        "Adversarially Tested",
        "A valid collapsed self-evaluation role may support Levels 1-3 while remaining ineligible for Level 4.",
        collapsed_target_governed_role,
    ),
    (
        "missing_paraphrase_coverage",
        "Structurally Valid",
        "Missing the two required paraphrase prompts must block behavioral readiness.",
        remove_paraphrase_coverage,
    ),
    (
        "missing_contract_clause",
        "Structurally Valid",
        "A contract that omits one of the seven clauses must not reach behavioral readiness.",
        missing_contract_clause,
    ),
    (
        "target_only_contract",
        "Structurally Valid",
        "A contract derived only from the target must not validate the target against itself.",
        target_only_contract,
    ),
    (
        "missing_judgment_rationale",
        "Structurally Valid",
        "A pass label without substantive judgment rationale must not satisfy behavioral readiness.",
        missing_judgment_rationale,
    ),
    (
        "forced_invocation_activation",
        "Structurally Valid",
        "Explicit invocation must not masquerade as auto-dispatch trigger evidence.",
        forced_invocation_activation,
    ),
    (
        "payload_before_contract_freeze",
        "Structurally Valid",
        "A fresh provenance wrapper must not launder a pre-contract behavioral payload.",
        payload_before_contract_freeze,
    ),
    (
        "reused_behavior_output",
        "Structurally Valid",
        "One generic raw output must not satisfy multiple behavioral cases.",
        reused_behavior_output,
    ),
    (
        "missing_metamorphic_coverage",
        "Structurally Valid",
        "Missing metamorphic cases must block behavioral readiness.",
        remove_metamorphic_coverage,
    ),
    (
        "mutation_changed_paths_mismatch",
        "Behaviorally Tested",
        "A declared mutation diff that disagrees with package bytes must block adversarial readiness.",
        mutation_changed_paths_mismatch,
    ),
    (
        "mutation_payload_before_contract_freeze",
        "Behaviorally Tested",
        "A fresh provenance wrapper must not launder a pre-contract mutation payload.",
        mutation_payload_before_contract_freeze,
    ),
    (
        "bare_detected_mutations",
        "Behaviorally Tested",
        "Bare detected booleans without findings and durable repairs must block adversarial readiness.",
        bare_detected_mutations,
    ),
    (
        "wrong_structural_target_digest",
        "Not Validated",
        "Validator evidence bound to a different target digest must fail structural readiness.",
        wrong_structural_target_digest,
    ),
    (
        "bundled_audit_not_strict",
        "Not Validated",
        "A bundled audit without strict mode must fail structural readiness.",
        bundled_audit_not_strict,
    ),
    (
        "spoofed_structural_executable",
        "Not Validated",
        "Echoing validator names must not satisfy structured validator execution.",
        spoofed_structural_executable,
    ),
    (
        "repair_verification_structural_only",
        "Not Validated",
        "Repair verification must include both structural validators and a post-repair regression.",
        repair_verification_structural_only,
    ),
    (
        "repair_verification_predates_repair",
        "Not Validated",
        "Verification evidence created before repair provenance must not validate the repair.",
        repair_verification_predates_repair,
    ),
    (
        "repair_artifacts_are_files",
        "Not Validated",
        "Arbitrary target files must not satisfy before and after package snapshots.",
        repair_artifacts_are_files,
    ),
    (
        "repair_unrelated_before_package",
        "Not Validated",
        "A before package with a different skill identity must not validate a repair.",
        repair_unrelated_before_package,
    ),
    (
        "future_dated_repair_evidence",
        "Not Validated",
        "Evidence dated after August 14, 2026 must not validate current work.",
        future_dated_repair_evidence,
    ),
    (
        "mixed_timezone_repair_evidence",
        "User Validated",
        "Offset-naive and offset-aware ISO timestamps must normalize without crashing.",
        mixed_timezone_repair_evidence,
    ),
    (
        "unrun_low_mutation",
        "User Validated",
        "A planned unrun Low mutation must not poison a completed five-category campaign.",
        add_unrun_low_mutation,
    ),
    (
        "boundary_case_alias",
        "User Validated",
        "The documented boundary label must count as the edge behavioral case.",
        use_boundary_case_alias,
    ),
    (
        "spoofed_structural_output",
        "Not Validated",
        "A hashed but non-validator output must not prove structural success.",
        spoofed_structural_output,
    ),
    (
        "malformed_behavior_result",
        "Structurally Valid",
        "Behavioral readiness requires a target-bound structured judgment.",
        malformed_behavior_result,
    ),
    (
        "missing_mutated_package",
        "Behaviorally Tested",
        "A mutation boolean without a full mutated skill package cannot pass.",
        missing_mutated_package,
    ),
    (
        "wrong_mutated_skill_identity",
        "Behaviorally Tested",
        "A mutation package must preserve the target skill identity.",
        wrong_mutated_skill_identity,
    ),
    (
        "duplicate_role_prompt_content",
        "Adversarially Tested",
        "Different prompt paths with identical bytes do not establish independence.",
        duplicate_role_prompt_content,
    ),
    (
        "wrong_holdout_target",
        "Independently Cross-Checked",
        "A holdout result for another target cannot support User Validated.",
        wrong_holdout_target,
    ),
    (
        "wrong_acceptance_target",
        "Independently Cross-Checked",
        "User acceptance must name the exact target package digest.",
        wrong_acceptance_target,
    ),
    (
        "missing_secondary_judgments",
        "Adversarially Tested",
        "Level 4 requires both independent judgment lenses on every case.",
        remove_secondary_judgments,
    ),
    (
        "duplicate_judgment_lens",
        "Adversarially Tested",
        "Two judges using one declared lens do not provide independent review.",
        duplicate_judgment_lens,
    ),
    (
        "reused_mutation_artifacts",
        "Behaviorally Tested",
        "One mutation package and output cannot satisfy all five categories.",
        reuse_mutation_artifacts,
    ),
    (
        "minimal_mutation_decoy",
        "Behaviorally Tested",
        "A one-file decoy is not a full mutation of a multi-file target.",
        minimal_mutation_decoy,
    ),
    (
        "evidence_before_contract_freeze",
        "Not Validated",
        "Behavioral and mutation evidence may not predate contract freeze.",
        evidence_before_contract_freeze,
    ),
    (
        "holdout_before_external_review",
        "Independently Cross-Checked",
        "The post-freeze holdout must occur after external review evidence.",
        holdout_before_external_review,
    ),
    (
        "acceptance_before_holdout",
        "Independently Cross-Checked",
        "User acceptance must not predate the holdout reveal.",
        acceptance_before_holdout,
    ),
    (
        "external_review_actor_reused",
        "Adversarially Tested",
        "The external review steward must be distinct from every evaluated role.",
        external_review_actor_reused,
    ),
    (
        "result_context_mismatch",
        "Adversarially Tested",
        "A judgment detached from its recorded evaluator context must block independence.",
        result_context_mismatch,
    ),
    (
        "contract_actor_mismatch",
        "Adversarially Tested",
        "Requirements not produced by the contract role must block independence.",
        contract_actor_mismatch,
    ),
]

DETAIL_EXPECTATIONS: dict[str, dict[str, bool]] = {
    "example_control": {
        "independence_evidence_ready": True,
        "user_validation_evidence_ready": False,
    },
    "full_claim_control": {
        "independence_evidence_ready": True,
        "user_validation_evidence_ready": True,
    },
    "repair_claim_control": {
        "independence_evidence_ready": True,
        "user_validation_evidence_ready": True,
    },
    "unrun_medium_extra": {
        "independence_evidence_ready": True,
        "user_validation_evidence_ready": True,
    },
    "mixed_timezone_repair_evidence": {
        "independence_evidence_ready": True,
        "user_validation_evidence_ready": True,
    },
    "unrun_low_mutation": {
        "independence_evidence_ready": True,
        "user_validation_evidence_ready": True,
    },
    "boundary_case_alias": {
        "independence_evidence_ready": True,
        "user_validation_evidence_ready": True,
    },
    "string_holdout_true": {
        "independence_evidence_ready": True,
        "user_validation_evidence_ready": False,
    },
    "absent_holdout_acceptance": {
        "independence_evidence_ready": True,
        "user_validation_evidence_ready": False,
    },
    "wrong_holdout_target": {
        "independence_evidence_ready": True,
        "user_validation_evidence_ready": False,
    },
    "wrong_acceptance_target": {
        "independence_evidence_ready": True,
        "user_validation_evidence_ready": False,
    },
    "holdout_before_external_review": {
        "independence_evidence_ready": True,
        "user_validation_evidence_ready": False,
    },
    "acceptance_before_holdout": {
        "independence_evidence_ready": True,
        "user_validation_evidence_ready": False,
    },
    "external_review_actor_reused": {
        "independence_evidence_ready": False,
        "user_validation_evidence_ready": False,
    },
    "result_context_mismatch": {
        "independence_evidence_ready": False,
        "user_validation_evidence_ready": False,
    },
    "contract_actor_mismatch": {
        "independence_evidence_ready": False,
        "user_validation_evidence_ready": False,
    },
}


def run() -> int:
    target_digest = package_digest(TARGET)
    HOLDOUT_FILE.write_text(
        json.dumps(
            {
                "kind": "holdout-result",
                "verdict": "pass",
                "target_sha256": target_digest,
                "actor_id": "holdout-steward",
                "holdout_frozen_at": "2026-08-14T00:11:00Z",
                "revealed_at": "2026-08-14T00:12:00Z",
                "created_at": "2026-08-14T00:12:00Z",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    ACCEPTANCE_FILE.write_text(
        json.dumps(
            {
                "kind": "user-acceptance",
                "verdict": "accept",
                "target_sha256": target_digest,
                "accepted_level": "User Validated",
                "actor_id": "user",
                "created_at": "2026-08-14T00:13:00Z",
                "statement": (
                    "I accept this exact target package and its evaluated behavior."
                ),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    for package_path in (
        AUDIT_BEFORE_PACKAGE,
        AUDIT_AFTER_PACKAGE,
        REPAIR_BEFORE_PACKAGE,
        REPAIR_AFTER_PACKAGE,
        UNRELATED_BEFORE_PACKAGE,
    ):
        if package_path.exists():
            shutil.rmtree(package_path)
        shutil.copytree(TARGET, package_path)
    before_skill = REPAIR_BEFORE_PACKAGE / "SKILL.md"
    before_skill.write_text(
        before_skill.read_text(encoding="utf-8")
        + "\n<!-- pre-repair snapshot -->\n",
        encoding="utf-8",
    )
    unrelated_skill = UNRELATED_BEFORE_PACKAGE / "SKILL.md"
    unrelated_skill.write_text(
        unrelated_skill.read_text(encoding="utf-8").replace(
            "name: game-skill-auditor",
            "name: unrelated-before",
            1,
        ),
        encoding="utf-8",
    )
    example = build_example()
    results = []
    for name, expected, rationale, mutate in PROBES:
        if name == "example_control":
            manifest = copy.deepcopy(example)
        elif name in {
            "repair_claim_control",
            "placeholder_repair_finding_id",
            "repair_verification_structural_only",
            "repair_verification_predates_repair",
            "repair_artifacts_are_files",
            "repair_unrelated_before_package",
            "future_dated_repair_evidence",
            "mixed_timezone_repair_evidence",
        }:
            manifest = repair_ready(example)
        else:
            manifest = full_ready(example)
        mutate(manifest)
        external_review_file = Path(
            manifest.pop("_external_review_file", EXTERNAL_REVIEW_FILE)
        )
        manifest["audit_id"] = name
        fixture = OUT_DIR / f"{name}.json"
        fixture.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        completed = subprocess.run(
            [
                sys.executable,
                str(SCORER),
                str(fixture),
                "--json",
                "--external-review-file",
                str(external_review_file),
                "--user-acceptance-file",
                str(ACCEPTANCE_FILE),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        parsed = json.loads(completed.stdout) if completed.stdout.strip() else {}
        observed = parsed.get("readiness", f"ERROR rc={completed.returncode}")
        observed_evidence = parsed.get(
            "evidence_package_completeness",
            f"ERROR rc={completed.returncode}",
        )
        expected_evidence = EVIDENCE_COMPLETENESS_BY_LEVEL[expected]
        expected_readiness = (
            "Not Validated"
            if expected == "Not Validated"
            else "Structurally Valid"
        )
        expected_exit = 1 if observed == "Not Validated" else 0
        exit_mismatch = completed.returncode != expected_exit
        observed_evidence_level = LEVEL_BY_EVIDENCE_COMPLETENESS.get(
            observed_evidence,
            "",
        )
        bypass = (
            observed_evidence_level in LEVELS
            and expected in LEVELS
            and LEVELS.index(observed_evidence_level) > LEVELS.index(expected)
        )
        readiness_mismatch = observed != expected_readiness
        evidence_mismatch = observed_evidence != expected_evidence
        detail_expectations = DETAIL_EXPECTATIONS.get(name, {})
        detail_mismatches = {
            key: {"expected": expected_value, "observed": parsed.get(key)}
            for key, expected_value in detail_expectations.items()
            if parsed.get(key) is not expected_value
        }
        results.append(
            {
                "probe": name,
                "expected_readiness": expected_readiness,
                "observed_readiness": observed,
                "expected_evidence_package_completeness": expected_evidence,
                "observed_evidence_package_completeness": observed_evidence,
                "bypass": bypass,
                "readiness_mismatch": readiness_mismatch,
                "evidence_mismatch": evidence_mismatch,
                "detail_mismatches": detail_mismatches,
                "rationale": rationale,
                "returncode": completed.returncode,
                "exit_mismatch": exit_mismatch,
                "mutation_score": parsed.get("mutation_score"),
                "completed_mutations": parsed.get("completed_mutations"),
                "distinct_evaluation_contexts": parsed.get(
                    "distinct_evaluation_contexts"
                ),
                "blockers": parsed.get("blockers", []),
                "stderr": completed.stderr.strip(),
                "fixture": str(fixture.relative_to(ROOT)),
            }
        )

    report_only_fixture = OUT_DIR / "missing_official_validator.json"
    report_only = subprocess.run(
        [
            sys.executable,
            str(SCORER),
            str(report_only_fixture),
            "--json",
            "--report-only",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    report_only_payload = (
        json.loads(report_only.stdout) if report_only.stdout.strip() else {}
    )
    report_only_ok = (
        report_only.returncode == 0
        and report_only_payload.get("readiness") == "Not Validated"
    )
    full_claim_fixture = OUT_DIR / "full_claim_control.json"
    require_level_results = {}
    for required_level in LEVELS[1:]:
        completed = subprocess.run(
            [
                sys.executable,
                str(SCORER),
                str(full_claim_fixture),
                "--json",
                "--require-level",
                required_level,
                "--external-review-file",
                str(EXTERNAL_REVIEW_FILE),
                "--user-acceptance-file",
                str(ACCEPTANCE_FILE),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout) if completed.stdout.strip() else {}
        expected_returncode = 0 if required_level == "Structurally Valid" else 1
        require_level_results[required_level] = {
            "returncode": completed.returncode,
            "expected_returncode": expected_returncode,
            "readiness": payload.get("readiness"),
            "evidence_package_completeness": payload.get(
                "evidence_package_completeness"
            ),
            "passed": (
                completed.returncode == expected_returncode
                and payload.get("readiness") == "Structurally Valid"
                and payload.get("evidence_package_completeness")
                == "User Validation Evidence Complete"
            ),
        }
    require_level_ok = all(
        item["passed"] for item in require_level_results.values()
    )
    result_path = OUT_DIR / "results.json"
    result_path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    output = {
        "probe_count": len(results),
        "bypass_count": sum(item["bypass"] for item in results),
        "exit_mismatch_count": sum(
            item["exit_mismatch"] for item in results
        ),
        "readiness_mismatch_count": sum(
            item["readiness_mismatch"] for item in results
        ),
        "evidence_mismatch_count": sum(
            item["evidence_mismatch"] for item in results
        ),
        "detail_mismatch_count": sum(
            bool(item["detail_mismatches"]) for item in results
        ),
        "report_only_ok": report_only_ok,
        "require_level_ok": require_level_ok,
        "require_level_results": require_level_results,
        "results": results,
    }
    print(json.dumps(output, indent=2))
    exit_code = (
        1
        if any(
            item["readiness_mismatch"] or item["exit_mismatch"]
            or item["evidence_mismatch"]
            or bool(item["detail_mismatches"])
            for item in results
        )
        or not report_only_ok
        or not require_level_ok
        else 0
    )
    shutil.rmtree(OUT_DIR, ignore_errors=True)
    return exit_code


if __name__ == "__main__":
    sys.exit(run())
