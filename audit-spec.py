#!/usr/bin/env python3
"""Static audit of the Markdown contracts; not a Societas runtime harness."""

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Iterator

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012
import rfc8785
import yaml

PREFIX = "urn:societas:1:"
FENCE = re.compile(r"^```(json|yaml)\s*\n(.*?)^```\s*$", re.M | re.S)
TAG = re.compile(r"<!-- (schema|schemas|example|fixture):([\w.]+) -->\s*$")
ROW = re.compile(r"^\| `([\w.]+)` \| `(\w+)` \|", re.M)
NUMBER = re.compile(r"^#{1,6} (\d+[A-Z]?(?:\.\d+)*)\.? ", re.M)
TASK_EVENTS = {
    "task.paused", "task.resumed", "task.interrupted",
    "task.rebase_conflict", "task.contract_changed",
}


def objects(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from objects(child)


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def invalid_constant(value: str) -> None:
    raise ValueError(f"non-JSON numeric constant: {value}")


def boundary_errors(
    event: dict[str, Any],
    schemas: dict[str, dict[str, Any]],
    mapping: dict[str, str],
    registry: Registry,
) -> list[str]:
    """Reference checks for documented wire rules only (no auth/SQLite)."""
    errors = [
        f"envelope: {error.message}"
        for error in Draft202012Validator(
            schemas[PREFIX + "envelope"], registry=registry,
            format_checker=FormatChecker(),
        ).iter_errors(event)
    ]
    event_type = event.get("type", "")
    if event_type not in mapping:
        return errors + ["unknown event type"]
    payload = event.get("payload")
    errors.extend(
        f"payload: {error.message}"
        for error in Draft202012Validator(
            schemas[PREFIX + mapping[event_type]], registry=registry,
            format_checker=FormatChecker(),
        ).iter_errors(payload)
    )
    if not isinstance(payload, dict):
        return errors
    if event_type != "run.created" and "causation_id" not in event:
        errors.append("non-root event missing causation_id (I8)")
    if event_type in TASK_EVENTS and "task_id" not in event:
        errors.append("task lifecycle event missing task_id")
    if event_type == "task.paused":
        requested = payload.get("phase") == "requested"
        expected_sender = "human:user" if requested else "system:orchestrator"
        expected_target = "system:orchestrator" if requested else "topic:all"
        if event.get("from") != expected_sender or event.get("to") != expected_target:
            errors.append("pause phase/sender/target mismatch")
    if event_type == "task.resumed":
        if event.get("from") != "system:orchestrator":
            errors.append("resume sender must be orchestrator")
        if not str(event.get("to", "")).startswith("agent:"):
            errors.append("resume must target an agent (owner requires runtime check)")
    if event_type == "approval.requested":
        reference = payload.get("snapshot_ref")
        if isinstance(reference, dict) and reference.get("checksum") != payload.get("bound_hash"):
            errors.append("snapshot checksum must equal bound_hash")
    if event_type == "approval.invalidated":
        if event.get("from") != "system:orchestrator" or event.get("to") != "human:user":
            errors.append("invalidation sender/target mismatch (not an auth check)")
    try:
        limit = 16000 if event_type == "tool.call_completed" else 8000
        if len(rfc8785.dumps(payload)) > limit:
            errors.append(f"aggregate payload exceeds {limit} UTF-8 bytes")
    except (ValueError, TypeError) as error:
        errors.append(f"payload serialization: {error}")
    return errors


def snapshot_digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(rfc8785.dumps(value)).hexdigest()


def approval_errors(
    request: dict[str, Any],
    artifacts: dict[tuple[str, int], bytes],
    schemas: dict[str, dict[str, Any]],
    registry: Registry,
    *,
    current_snapshot: dict[str, Any] | None = None,
    grant: dict[str, Any] | None = None,
    status: str = "pending",
    now: str | None = None,
    contract_current: bool = True,
) -> list[str]:
    """Reference snapshot predicate over fixtures, not an execution/CAS engine."""
    errors = boundary_errors(request, schemas, {"approval.requested": "approval_requested"}, registry)
    if errors:
        return errors
    payload = request["payload"]
    reference = payload["snapshot_ref"]
    content = artifacts.get((reference["artifact_id"], reference["version"]))
    if content is None:
        return ["snapshot artifact version unavailable"]
    try:
        snapshot = json.loads(content, object_pairs_hook=unique_object, parse_constant=invalid_constant)
        snapshot_errors = list(Draft202012Validator(
            schemas[PREFIX + "approval_snapshot"], registry=registry,
            format_checker=FormatChecker(),
        ).iter_errors(snapshot))
        if snapshot_errors:
            return [f"snapshot: {error.message}" for error in snapshot_errors]
        if content != rfc8785.dumps(snapshot) or snapshot_digest(snapshot) != payload["bound_hash"]:
            errors.append("snapshot bytes/digest mismatch")
        if current_snapshot is not None:
            current_errors = list(Draft202012Validator(
                schemas[PREFIX + "approval_snapshot"], registry=registry,
                format_checker=FormatChecker(),
            ).iter_errors(current_snapshot))
            if current_errors or snapshot_digest(current_snapshot) != payload["bound_hash"]:
                errors.append("live bound input changed")
        for field in ("workspace_id", "run_id", "task_id"):
            if snapshot[field] != request.get(field):
                errors.append(f"snapshot envelope mismatch: {field}")
        if snapshot["action"] != payload["action"]:
            errors.append("snapshot action mismatch")
        if status not in {"pending", "granted"}:
            errors.append("approval no longer valid")
        if not contract_current:
            errors.append("task contract stale")
        if now and payload.get("expires_at"):
            if datetime.fromisoformat(now.replace("Z", "+00:00")) >= datetime.fromisoformat(
                payload["expires_at"].replace("Z", "+00:00"),
            ):
                errors.append("approval expired")
        if grant is not None:
            errors.extend(
                f"grant: {error.message}" for error in Draft202012Validator(
                    schemas[PREFIX + "approval_granted"], registry=registry,
                    format_checker=FormatChecker(),
                ).iter_errors(grant)
            )
            for field in ("approval_id", "bound_hash"):
                if grant.get(field) != payload[field]:
                    errors.append(f"grant request mismatch: {field}")
            if "budget_override" in grant:
                if snapshot["action"] != "budget.increase" or (
                    rfc8785.dumps(grant["budget_override"]) !=
                    rfc8785.dumps(snapshot["inputs"]["proposed_limits"])
                ):
                    errors.append("unbound budget override")
        if snapshot["action"] == "budget.increase":
            scope = snapshot["inputs"]["scope"]
            scope_field = {"workspace": "workspace_id", "run": "run_id", "task": "task_id"}.get(scope)
            if scope_field and snapshot["inputs"]["target_id"] != snapshot[scope_field]:
                errors.append("budget scope/target identity mismatch")
        if snapshot["action"] == "tool.execute":
            resource_ids = [resource["resource_id"] for resource in snapshot["inputs"]["resources"]]
            if len(set(resource_ids)) != len(resource_ids) or resource_ids != sorted(
                resource_ids, key=lambda value: value.encode("utf-16-be"),
            ):
                errors.append("resource IDs must be unique and sorted by UTF-16 code units")
        if snapshot["action"] == "git.merge":
            candidate = snapshot["inputs"]["candidate"]
            oid_lengths = {len(candidate[field]) for field in ("expected_base", "candidate_commit", "candidate_tree")}
            if len(oid_lengths) != 1:
                errors.append("mixed Git object formats")
            binding = {field: snapshot[field] for field in (
                "workspace_id", "run_id", "task_id", "policy_hash", "contract_hash",
            )}
            binding["candidate"] = candidate
            for kind, result in (("gate", "pass"), ("review", "approve")):
                evidence_ref = snapshot["inputs"][kind + "_evidence"]
                evidence_bytes = artifacts.get((evidence_ref["artifact_id"], evidence_ref["version"]))
                if evidence_bytes is None:
                    errors.append(f"{kind} artifact version unavailable")
                    continue
                evidence = json.loads(evidence_bytes, object_pairs_hook=unique_object, parse_constant=invalid_constant)
                evidence_errors = list(Draft202012Validator(
                    schemas[PREFIX + "merge_evidence"], registry=registry,
                    format_checker=FormatChecker(),
                ).iter_errors(evidence))
                if evidence_errors:
                    errors.extend(f"{kind}: {error.message}" for error in evidence_errors)
                    continue
                checksum = "sha256:" + hashlib.sha256(evidence_bytes).hexdigest()
                if checksum != evidence_ref["checksum"]:
                    errors.append(f"{kind} artifact checksum mismatch")
                if rfc8785.dumps(evidence["binding"]) != rfc8785.dumps(binding):
                    errors.append(f"{kind} candidate/context mismatch")
                if evidence["kind"] != kind or evidence["result"] != result:
                    errors.append(f"{kind} evidence not accepted")
    except (ValueError, TypeError, UnicodeError) as error:
        errors.append(f"approval serialization: {error}")
    return errors


def audit(root: Path, baseline_ref: str | None) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: Any = "") -> None:
        checks.append({"name": name, "passed": passed, "detail": detail})

    texts = {path.name: path.read_text(encoding="utf-8") for path in root.glob("*.md")}
    canonical = texts.get("10-contracts-mvp-roadmap.md", "")
    check("canonical_document_present", bool(canonical))
    schemas: dict[str, dict[str, Any]] = {}
    examples: list[tuple[str, dict[str, Any]]] = []
    fixtures: dict[str, dict[str, Any]] = {}
    counts: Counter = Counter()
    for filename, text in sorted(texts.items()):
        for match in FENCE.finditer(text):
            language, body = match.groups()
            counts[language] += 1
            location = f"{filename}:{text[:match.start()].count(chr(10)) + 1}"
            try:
                value = (
                    json.loads(body, object_pairs_hook=unique_object, parse_constant=invalid_constant)
                    if language == "json" else yaml.safe_load(body)
                )
                check(f"parse:{language}:{location}", True)
            except (ValueError, yaml.YAMLError) as error:
                check(f"parse:{language}:{location}", False, str(error))
                continue
            tag = TAG.search(text[:match.start()])
            if language != "json" or not tag or filename != "10-contracts-mvp-roadmap.md":
                continue
            kind, name = tag.groups()
            if kind == "fixture":
                check(f"fixture_is_object:{name}", isinstance(value, dict))
                check(f"fixture_unique:{name}", name not in fixtures)
                if isinstance(value, dict):
                    fixtures[name] = value
                continue
            if kind == "example":
                check(f"example_is_object:{location}", isinstance(value, dict))
                if isinstance(value, dict):
                    examples.append((name, value))
                continue
            definitions = value if kind == "schemas" else [value]
            check(f"schema_collection:{location}", isinstance(definitions, list))
            if not isinstance(definitions, list):
                continue
            for definition in definitions:
                valid = isinstance(definition, dict) and "$id" in definition
                check(f"schema_has_id:{location}", valid)
                if not valid:
                    continue
                schema_id = definition["$id"]
                check(f"unique_schema_id:{schema_id}", schema_id not in schemas)
                schemas[schema_id] = definition
                try:
                    Draft202012Validator.check_schema(definition)
                    check(f"meta_schema:{schema_id}", True)
                except SchemaError as error:
                    check(f"meta_schema:{schema_id}", False, str(error))

    check("schema_markers_not_lost", len(schemas) >= 47, len(schemas))
    check("example_markers_not_lost", len(examples) >= 14, len(examples))
    registry: Registry = Registry().with_resources(
        (schema_id, Resource.from_contents(schema, default_specification=DRAFT202012))
        for schema_id, schema in schemas.items()
    )
    refs = 0
    for schema_id, schema in schemas.items():
        for node in objects(schema):
            if "$ref" not in node:
                continue
            refs += 1
            try:
                registry.resolver(schema_id).lookup(node["$ref"])
                check(f"ref:{schema_id}:{refs}", True)
            except Exception as error:
                check(f"ref:{schema_id}:{refs}", False, str(error))

    registry_section = canonical.split("## 72A.7 Event Registry")[-1].split("## 72A.8")[0]
    rows = ROW.findall(registry_section)
    mapping = dict(rows)
    check("registry_types_unique", len(mapping) == len(rows))
    check("registry_rows_not_lost", len(mapping) >= 42, len(mapping))
    for event_type, schema_name in mapping.items():
        check(f"registry:{event_type}", PREFIX + schema_name in schemas)
    reachable = {PREFIX + "envelope"} | {PREFIX + name for name in mapping.values()}
    while True:
        expanded = reachable | {
            node["$ref"].split("#")[0] or schema_id
            for schema_id in reachable if schema_id in schemas
            for node in objects(schemas[schema_id]) if "$ref" in node
        }
        if expanded == reachable:
            break
        reachable = expanded
    check("no_orphan_schemas", not (set(schemas) - reachable), sorted(set(schemas) - reachable))
    dependencies_ok = all(schema_id in schemas for schema_id in reachable) and not any(
        not entry["passed"] and entry["name"].startswith(
            ("parse:", "meta_schema:", "ref:", "unique_schema_id:")
        )
        for entry in checks
    )
    for name, event in examples:
        check(f"example_type:{name}", event.get("type") == name)
        try:
            errors = boundary_errors(event, schemas, mapping, registry)
            check(f"example:{name}", not errors, errors)
        except Exception as error:
            check(f"example:{name}", False, str(error))
    probe_examples = {"approval.requested", "task.created"}
    if dependencies_ok and probe_examples <= {name for name, _ in examples}:
        probes(schemas, mapping, registry, examples, check)
    else:
        check("probes_runnable", False, "missing schema dependencies or fixture examples")
    approval_fixtures = {
        "approval_budget", "approval_merge", "approval_tool",
        "approval_hash_vectors", "merge_gate", "merge_review",
    }
    check("approval_fixtures_present", approval_fixtures <= fixtures.keys())
    if dependencies_ok and approval_fixtures <= fixtures.keys():
        try:
            approval_probes(schemas, registry, examples, fixtures, check)
        except (ValueError, TypeError, UnicodeError, KeyError) as error:
            check("approval_probes_runnable", False, str(error))
    else:
        check("approval_probes_runnable", False, "missing schema dependencies or approval fixtures")
    merge_flow = canonical.split("### Serial Merge: Final Candidate Binding")[-1].split("### Output besar")[0]
    markers = [
        "2. Rebase branch task", "4. Freeze candidate", "5. Gate build/lint/test",
        "6. review.requested/completed", "7. Persist snapshot JCS",
        "8. Tepat sebelum integrasi", "9. Verifikasi candidate_commit",
    ]
    positions = [merge_flow.find(marker) for marker in markers]
    check("documented_merge_order", all(position >= 0 for position in positions) and positions == sorted(positions))
    conflict = merge_flow.find("conflict -> task.rebase_conflict -> Engineer")
    approval = merge_flow.find("approval.requested")
    check("documented_conflict_before_approval", 0 <= conflict < approval)
    check("documented_expected_base_cas", "git update-ref --no-deref <target_ref> <candidate_commit> <expected_base>" in merge_flow)

    state_section = canonical.split("## 72A.6 Task State Machine")[-1].split("## 72A.7")[0]
    transitions = re.findall(
        r"^\| `(\w+)` \| `(\w+)` \| .*? \| `([\w.]+)` \|$", state_section, re.M
    )
    task_schema = schemas.get(PREFIX + "task", {})
    states = set(task_schema.get("properties", {}).get("status", {}).get("enum", []))
    for before, after, event_type in transitions:
        check(f"transition:{before}:{after}", before in states and after in states and event_type in mapping)
    check("terminal_states_have_no_exit", not any(
        before in {"completed", "failed", "cancelled"} for before, _, _ in transitions
    ))
    pairs = {(before, after) for before, after, _ in transitions}
    recovery_pairs = {
        ("running", "interrupted"), ("pausing", "interrupted"),
        ("pausing", "failed"), ("pausing", "cancelled"), ("interrupted", "cancelled"),
    }
    check("pause_recovery_transitions", recovery_pairs <= pairs)
    for error_code in ("SEARCH_BLOCK_NOT_FOUND", "SEARCH_BLOCK_AMBIGUOUS", "REBASE_CONFLICT", "APPROVAL_BINDING_INVALID"):
        catalog = canonical.split("## 72A.9")[-1].split("## 72A.10")[0]
        check(f"error_catalog:{error_code}", f"| `{error_code}` |" in catalog)

    if baseline_ref:
        for filename, text in sorted(texts.items()):
            if not re.match(r"^\d\d-", filename):
                continue
            previous = subprocess.run(
                ["git", "show", f"{baseline_ref}:{filename}"], cwd=root,
                text=True, capture_output=True, check=False,
            )
            if previous.returncode:
                check(f"numbering_baseline:{filename}", False, previous.stderr.strip())
                continue
            original = NUMBER.findall(previous.stdout)
            current = NUMBER.findall(text)
            iterator = iter(current)
            check(f"numbering_preserved:{filename}", all(
                any(candidate == number for candidate in iterator) for number in original
            ), {"baseline": original, "current": current})

    failures = [entry for entry in checks if not entry["passed"]]
    return {
        "audit_kind": "replacement-static-contract-audit",
        "counts": {
            **counts, "schemas": len(schemas), "refs": refs, "registry": len(mapping),
            "examples": len(examples), "fixtures": len(fixtures), "checks": len(checks), "failures": len(failures),
        },
        "passed": not failures,
        "checks": checks,
        "limitations": [
            "Original review audit assets were not supplied; counts/probes may differ.",
            "YAML syntax only; no workspace config schema was supplied.",
            "Reference boundary probes are not runtime integration tests.",
            "Approval fixture predicates/document-order checks do not execute rebase, gates, "
            "review, Git-ref CAS, scope consumption, or live resource-version checks.",
            "No authentication, ownership, SQLite CAS/outbox/ledger, crash injection, "
            "provider/tool reconciliation, memory GC, Git broker, or OS sandbox tested.",
            "Audit pass does not close pending design findings or prove MVP acceptance.",
        ],
    }


def probes(schemas: dict, mapping: dict, registry: Registry, examples: list, check: Any) -> None:
    template = deepcopy(examples[0][1])
    template.update({
        "task_id": "TASK-001", "causation_id": template["id"],
        "from": "system:orchestrator", "to": "agent:engineer",
    })

    def event_probe(name: str, event_type: str, payload: dict, accepted: bool, **fields: Any) -> None:
        event = {**template, "type": event_type, "payload": payload, **fields}
        errors = boundary_errors(event, schemas, mapping, registry)
        check(f"probe:{name}", (not errors) == accepted, {"expected_accept": accepted, "errors": errors})

    def schema_probe(name: str, schema_name: str, value: dict, accepted: bool) -> None:
        valid = Draft202012Validator(
            schemas[PREFIX + schema_name], registry=registry, format_checker=FormatChecker(),
        ).is_valid(value)
        check(f"probe:{name}", valid == accepted, {"expected_accept": accepted, "schema_accept": valid})

    event_probe("unknown_type", "task.nonexistent", {}, False)
    event_probe("extra_payload_field", "task.started", {"attempt": 1, "extra": True}, False)
    event_probe("missing_envelope_field", "task.started", {"attempt": 1}, False, run_id=None)
    pause = {"phase": "requested", "initiated_by": "human:user", "pause_deadline": "2026-10-06T18:00:00Z"}
    event_probe("pause_requested", "task.paused", pause, True, **{"from": "human:user", "to": "system:orchestrator"})
    event_probe("pause_wrong_sender", "task.paused", pause, False)
    event_probe("pause_completed", "task.paused", {**pause, "phase": "completed"}, True, to="topic:all")
    event_probe("pause_missing_deadline", "task.paused", {"phase": "completed", "initiated_by": "human:user"}, False)
    resume = {"initiated_by": "human:user", "from_status": "paused"}
    event_probe("resume", "task.resumed", resume, True)
    event_probe("resume_wrong_sender", "task.resumed", resume, False, **{"from": "human:user"})
    event_probe("interrupted_pausing", "task.interrupted", {"previous_status": "pausing", "reason": "restart"}, True)
    hashes = {"old_hash": "sha256:" + "a" * 64, "new_hash": "sha256:" + "b" * 64}
    event_probe("contract_invalidated", "task.contract_changed", {**hashes, "phase": "invalidated", "required_actions": ["recodegen", "rereview"]}, True)
    event_probe("contract_missing_codegen", "task.contract_changed", {**hashes, "phase": "invalidated", "required_actions": ["rereview"]}, False)
    event_probe("contract_repinned", "task.contract_changed", {**hashes, "phase": "repinned"}, True)
    event_probe("rebase_conflict", "task.rebase_conflict", {"base_ref": "a" * 40, "conflict_files": ["src/main.go"]}, True)
    event_probe("empty_conflict", "task.rebase_conflict", {"base_ref": "a" * 40, "conflict_files": []}, False)
    schema_probe("budget_rebuttals", "budget", {"max_rebuttals": 2}, True)
    schema_probe("negative_rebuttals", "budget", {"max_rebuttals": -1}, False)
    approval = next(event["payload"] for name, event in examples if name == "approval.requested")
    schema_probe("approval_missing_hash", "approval_requested", {key: value for key, value in approval.items() if key != "bound_hash"}, False)
    schema_probe("raw_git_sha_not_bound_hash", "approval_requested", {**approval, "bound_hash": "a" * 40}, False)
    task = next(event["payload"]["task"] for name, event in examples if name == "task.created")
    schema_probe("paused_task_without_deadline", "task", {**task, "status": "paused"}, False)
    schema_probe("paused_task_with_deadline", "task", {**task, "status": "paused", "pause_deadline": pause["pause_deadline"]}, True)
    schema_probe("pinned_task_missing_freshness", "task", {**task, "contract_hash": hashes["new_hash"]}, False)
    tool_id = "tc_01J9ZB75QCACYADGWFKD86P7W1"
    error = {"code": "TOOL_TIMEOUT", "category": "TIMEOUT", "message": "response lost", "retryable": False}
    failed = {"tool_call_id": tool_id, "error": error}
    event_probe("tool_unknown_outcome", "tool.call_failed", {**failed, "outcome": "outcome_unknown"}, True)
    event_probe("tool_not_started", "tool.call_failed", {**failed, "outcome": "not_started"}, True)
    event_probe("tool_missing_outcome", "tool.call_failed", failed, False)
    request: dict[str, Any] = {"tool_call_id": tool_id, "tool": "filesystem.read", "arguments": {"note": ""}}
    request_size = len(rfc8785.dumps(request))
    for size, accepted in ((8000, True), (8001, False)):
        event_probe(
            f"default_exact_size_{size}", "tool.call_requested",
            {**request, "arguments": {"note": "x" * (size - request_size)}}, accepted,
        )
    completed: dict[str, Any] = {"tool_call_id": tool_id, "status": "ok", "duration_ms": 1}
    empty_size = len(rfc8785.dumps({**completed, "output": ""}))
    for size, accepted in ((16000, True), (16001, False)):
        event_probe(f"tool_exact_size_{size}", "tool.call_completed", {**completed, "output": "x" * (size - empty_size)}, accepted)
    event_probe("large_nested_object", "tool.call_completed", {**completed, "output": {"nested": {"text": "x" * 17000}}}, False)
    schema_probe(
        "schema_only_does_not_bound_objects", "tool_call_completed",
        {**completed, "output": {"nested": {"text": "x" * 17000}}}, True,
    )
    event_probe("aggregate_short_strings", "tool.call_completed", {**completed, "output": {"a": "x" * 9000, "b": "x" * 9000}}, False)
    event_probe("multibyte_output", "tool.call_completed", {**completed, "output": "界" * 6000}, False)


def approval_probes(
    schemas: dict, registry: Registry, examples: list,
    fixtures: dict[str, dict[str, Any]], check: Any,
) -> None:
    valid_fixtures = True
    vector_names = {"approval_budget", "approval_merge", "approval_tool", "merge_gate", "merge_review"}
    check("fixture_hash_vectors_complete", fixtures["approval_hash_vectors"].keys() == vector_names)
    for name in sorted(vector_names):
        schema_name = "approval_snapshot" if name.startswith("approval_") else "merge_evidence"
        valid = Draft202012Validator(
            schemas[PREFIX + schema_name], registry=registry,
            format_checker=FormatChecker(),
        ).is_valid(fixtures[name])
        check(f"fixture_schema:{name}", valid)
        check(f"fixture_digest:{name}", snapshot_digest(fixtures[name]) == fixtures["approval_hash_vectors"].get(name))
        valid_fixtures = valid_fixtures and valid
    if not valid_fixtures:
        check("approval_profiles_runnable", False, "invalid snapshot/evidence fixture")
        return
    snapshot_validator = Draft202012Validator(
        schemas[PREFIX + "approval_snapshot"], registry=registry, format_checker=FormatChecker(),
    )
    for name in ("approval_budget", "approval_merge", "approval_tool"):
        snapshot = fixtures[name]
        for field in snapshot:
            missing = {key: value for key, value in snapshot.items() if key != field}
            check(f"probe:snapshot_{name}_missing_{field}", not snapshot_validator.is_valid(missing))
        check(f"probe:snapshot_{name}_extra_field", not snapshot_validator.is_valid({**snapshot, "unexpected": True}))
        for field in snapshot["inputs"]:
            missing = {**snapshot, "inputs": {key: value for key, value in snapshot["inputs"].items() if key != field}}
            check(f"probe:snapshot_{name}_missing_input_{field}", not snapshot_validator.is_valid(missing))
    unknown_profile = {**fixtures["approval_merge"], "action": "unregistered.action"}
    check("probe:snapshot_unknown_profile", not snapshot_validator.is_valid(unknown_profile))
    requests = {
        event["payload"]["action"]: event
        for name, event in examples if name == "approval.requested"
    }
    grants = [event["payload"] for name, event in examples if name == "approval.granted"]
    check("approval_examples_present", {"budget.increase", "git.merge"} <= requests.keys() and bool(grants))
    if not {"budget.increase", "git.merge"} <= requests.keys() or not grants:
        return
    artifacts: dict[tuple[str, int], bytes] = {}
    for action, name in (("budget.increase", "approval_budget"), ("git.merge", "approval_merge")):
        reference = requests[action]["payload"]["snapshot_ref"]
        artifacts[(reference["artifact_id"], reference["version"])] = rfc8785.dumps(fixtures[name])
    merge = fixtures["approval_merge"]
    for kind in ("gate", "review"):
        reference = merge["inputs"][kind + "_evidence"]
        artifacts[(reference["artifact_id"], reference["version"])] = rfc8785.dumps(fixtures["merge_" + kind])

    def request_for(snapshot: dict, template: dict, artifact_id: str) -> dict:
        request = deepcopy(template)
        for field in ("workspace_id", "run_id", "task_id"):
            if snapshot[field] is None:
                request.pop(field, None)
            else:
                request[field] = snapshot[field]
        bound_hash = snapshot_digest(snapshot)
        request["payload"].update({
            "action": snapshot["action"], "bound_hash": bound_hash,
            "snapshot_ref": {"artifact_id": artifact_id, "version": 1, "checksum": bound_hash},
            "reason": "Reference fixture request for " + snapshot["action"],
        })
        return request

    def probe(name: str, accepted: bool, request: dict | None = None, **fields: Any) -> None:
        errors = approval_errors(request or requests["git.merge"], artifacts, schemas, registry, **fields)
        check(f"probe:approval_{name}", (not errors) == accepted, {"expected_accept": accepted, "errors": errors})

    for action, request in requests.items():
        probe("example_" + action, True, request)
    tool = fixtures["approval_tool"]
    tool_request = request_for(tool, requests["git.merge"], "art_01J9ZB6W9B4V3CGZKBZ01PDVKT")
    artifacts[("art_01J9ZB6W9B4V3CGZKBZ01PDVKT", 1)] = rfc8785.dumps(tool)
    probe("tool_snapshot", True, tool_request)
    probe("valid_grant", True, grant=grants[0], status="granted", now="2026-10-06T10:29:59Z")
    probe("expired_at_boundary", False, grant=grants[0], now="2026-10-06T10:30:00Z")
    for state in ("invalidated", "rejected", "expired"):
        probe("late_grant_" + state, False, grant=grants[0], status=state)
    probe("contract_stale", False, grant=grants[0], contract_current=False)
    probe("wrong_grant_hash", False, grant={**grants[0], "bound_hash": "sha256:" + "a" * 64})
    probe("wrong_grant_id", False, grant={**grants[0], "approval_id": "apr_01J9ZB6W9B4V3CGZKBZ01PDVKL"})
    probe("merge_budget_override", False, grant={**grants[0], "budget_override": {"max_cost_usd": 1.3}})
    budget_grant = {**grants[0], **{
        field: requests["budget.increase"]["payload"][field] for field in ("approval_id", "bound_hash")
    }}
    probe("budget_grant", True, requests["budget.increase"], grant=budget_grant)
    probe("budget_matching_override", True, requests["budget.increase"], grant={
        **budget_grant, "budget_override": {"max_cost_usd": 1.3},
    })
    probe("budget_changed_override", False, requests["budget.increase"], grant={
        **budget_grant, "budget_override": {"max_cost_usd": 2.0},
    })
    for field in ("workspace_id", "run_id", "task_id"):
        changed_request = deepcopy(requests["git.merge"])
        changed_request[field] = {"workspace_id": "ws_other", "run_id": "RUN-002", "task_id": "TASK-002"}[field]
        probe("wrong_" + field, False, changed_request)
    changed_request = deepcopy(requests["git.merge"])
    changed_request["payload"]["snapshot_ref"]["version"] = 2
    probe("snapshot_wrong_version", False, changed_request)
    changed_request = deepcopy(requests["git.merge"])
    changed_request["payload"]["snapshot_ref"]["checksum"] = "sha256:" + "a" * 64
    probe("snapshot_wrong_checksum", False, changed_request)
    changed_request["payload"]["bound_hash"] = "sha256:" + "a" * 64
    probe("prefixed_git_oid_is_not_snapshot_hash", False, changed_request)
    check("probe:approval_missing_artifact", bool(approval_errors(
        requests["git.merge"], {}, schemas, registry,
    )))
    for field in ("expected_base", "candidate_commit", "candidate_tree", "gate_recipe_hash"):
        changed = deepcopy(merge)
        changed["inputs"]["candidate"][field] = ("sha256:" if field == "gate_recipe_hash" else "") + "f" * (
            64 if field == "gate_recipe_hash" else 40
        )
        probe("changed_" + field, False, grant=grants[0], current_snapshot=changed)
    for field in ("policy_hash", "contract_hash"):
        probe("changed_" + field, False, grant=grants[0], current_snapshot={**merge, field: "sha256:" + "f" * 64})
    changed = deepcopy(merge)
    changed["inputs"]["candidate"]["expected_base"] = changed["inputs"]["candidate"]["candidate_commit"]
    probe("base_moved_before_cas", False, grant={**grants[0], "scope": "run"}, current_snapshot=changed)
    changed_tool = deepcopy(tool)
    changed_tool["inputs"]["arguments"]["label"] = "changed"
    probe("changed_tool_arguments", False, tool_request, current_snapshot=changed_tool)
    changed_tool = deepcopy(tool)
    changed_tool["inputs"]["resources"][0]["version"] = "sha256:" + "f" * 64
    probe("changed_resource_version", False, tool_request, current_snapshot=changed_tool)
    check("probe:approval_jcs_key_order", snapshot_digest(dict(reversed(list(merge.items())))) == snapshot_digest(merge))
    check("probe:approval_unicode_not_normalized", snapshot_digest({"label": "é"}) != snapshot_digest({"label": "e\u0301"}))
    check("probe:approval_utf8_vector", "界".encode() in artifacts[("art_01J9ZB6W9B4V3CGZKBZ01PDVKT", 1)])
    for resource_ids, accepted in (
        (["\U00010000", "\uffff"], True), (["\uffff", "\U00010000"], False), (["same", "same"], False),
    ):
        changed_tool = deepcopy(tool)
        changed_tool["inputs"]["resources"] = [
            {"resource_id": value, "version": str(index)} for index, value in enumerate(resource_ids)
        ]
        changed_request = request_for(changed_tool, tool_request, "art_01J9ZB6W9B4V3CGZKBZ01PDVKT")
        errors = approval_errors(changed_request, {
            ("art_01J9ZB6W9B4V3CGZKBZ01PDVKT", 1): rfc8785.dumps(changed_tool),
        }, schemas, registry)
        check(f"probe:approval_resource_order:{repr(resource_ids)}", (not errors) == accepted, errors)
    for value in (float("nan"), float("inf"), 2**64, "\ud800"):
        try:
            snapshot_digest({"invalid": value})
            rejected = False
        except (ValueError, TypeError, UnicodeError):
            rejected = True
        check(f"probe:approval_unsafe_value:{repr(value)}", rejected)
    for kind, result in (("gate", "fail"), ("review", "request_changes")):
        for mutation in ("result", "candidate", "contract_hash"):
            bad_evidence = deepcopy(fixtures["merge_" + kind])
            if mutation == "result":
                bad_evidence["result"] = result
            elif mutation == "candidate":
                bad_evidence["binding"]["candidate"]["candidate_commit"] = "f" * 40
            else:
                bad_evidence["binding"]["contract_hash"] = "sha256:" + "f" * 64
            changed = deepcopy(merge)
            reference = changed["inputs"][kind + "_evidence"]
            reference["checksum"] = snapshot_digest(bad_evidence)
            changed_request = request_for(changed, requests["git.merge"], "art_01J9ZB6W9B4V3CGZKBZ01PDVKR")
            changed_artifacts = {
                **artifacts,
                ("art_01J9ZB6W9B4V3CGZKBZ01PDVKR", 1): rfc8785.dumps(changed),
                (reference["artifact_id"], reference["version"]): rfc8785.dumps(bad_evidence),
            }
            errors = approval_errors(changed_request, changed_artifacts, schemas, registry)
            check(f"probe:approval_rehashed_{kind}_{mutation}", bool(errors), errors)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--baseline-ref", help="Git ref used to check preservation of existing numbered headings")
    args = parser.parse_args()
    report = audit(args.root, args.baseline_ref)
    if args.output:
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], **report["counts"]}, indent=2))
    for entry in report["checks"]:
        if not entry["passed"]:
            print(f"FAIL {entry['name']}: {entry['detail']}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
