"""Regression tests for the replacement audit itself, not the product runtime."""

import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("societas_audit", ROOT / "audit-spec.py")
assert SPEC and SPEC.loader
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class AuditTests(unittest.TestCase):
    def run_fixture(self, before: str = "", after: str = "") -> dict:
        with tempfile.TemporaryDirectory(prefix="societas-audit-test-") as directory:
            root = Path(directory)
            canonical = (ROOT / "10-contracts-mvp-roadmap.md").read_text(encoding="utf-8")
            if before:
                self.assertIn(before, canonical)
                canonical = canonical.replace(before, after, 1)
            (root / "10-contracts-mvp-roadmap.md").write_text(canonical, encoding="utf-8")
            return AUDIT.audit(root, None)

    def assert_failed(self, report: dict, prefix: str) -> None:
        self.assertFalse(report["passed"])
        self.assertTrue(any(
            not check["passed"] and check["name"].startswith(prefix)
            for check in report["checks"]
        ), prefix)

    def test_current_contracts_pass(self) -> None:
        self.assertTrue(self.run_fixture()["passed"])

    def test_missing_pause_schema_is_detected(self) -> None:
        report = self.run_fixture(
            '"$id": "urn:societas:1:task_paused"',
            '"$id": "urn:societas:1:missing_pause"',
        )
        self.assert_failed(report, "registry:task.paused")

    def test_duplicate_schema_id_is_detected(self) -> None:
        report = self.run_fixture(
            '"$id": "urn:societas:1:task_paused"',
            '"$id": "urn:societas:1:task_resumed"',
        )
        self.assert_failed(report, "unique_schema_id:")

    def test_dangling_ref_is_detected(self) -> None:
        report = self.run_fixture(
            '"$ref": "urn:societas:1:common#/$defs/evt_id"',
            '"$ref": "urn:societas:1:common#/$defs/nonexistent"',
        )
        self.assert_failed(report, "ref:")

    def test_missing_approval_hash_is_detected(self) -> None:
        report = self.run_fixture(
            '    "bound_hash": "sha256:9db02ed91537c1ca63d6d09f9895d669ec210a1cab9859b9362592553510d8a3",\n',
            "",
        )
        self.assert_failed(report, "example:approval.requested")

    def test_meta_schema_error_is_reported(self) -> None:
        report = self.run_fixture('"title": "Budget",', '"title": "Budget", "type": 42,')
        self.assert_failed(report, "parse:")
        report = self.run_fixture('"title": "Budget",', '"title": 42,')
        self.assert_failed(report, "meta_schema:")

    def test_unknown_event_example_is_detected(self) -> None:
        report = self.run_fixture('"type": "run.created",', '"type": "run.nonexistent",')
        self.assert_failed(report, "example:run.created")

    def test_missing_snapshot_context_is_detected(self) -> None:
        report = self.run_fixture(
            '"workspace_id": "ws_acme", "run_id": "RUN-001", "task_id": null,',
            '"workspace_id": "ws_acme", "task_id": null,',
        )
        self.assert_failed(report, "fixture_schema:approval_budget")

    def test_hash_vector_drift_is_detected(self) -> None:
        report = self.run_fixture(
            '"approval_budget": "sha256:9db02ed91537c1ca63d6d09f9895d669ec210a1cab9859b9362592553510d8a3"',
            '"approval_budget": "sha256:' + "a" * 64 + '"',
        )
        self.assert_failed(report, "fixture_digest:approval_budget")

    def test_evidence_candidate_drift_is_detected(self) -> None:
        report = self.run_fixture(
            '"candidate_commit": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"',
            '"candidate_commit": "ffffffffffffffffffffffffffffffffffffffff"',
        )
        self.assert_failed(report, "probe:approval_example_git.merge")

    def test_lost_snapshot_fixture_is_detected(self) -> None:
        report = self.run_fixture("<!-- fixture:approval_budget -->", "<!-- untagged -->")
        self.assert_failed(report, "approval_fixtures_present")

    def test_reordered_merge_gate_is_detected(self) -> None:
        report = self.run_fixture("5. Gate build/lint/test", "5. Skip build/lint/test")
        self.assert_failed(report, "documented_merge_order")

    def test_cas_without_expected_base_is_detected(self) -> None:
        report = self.run_fixture(
            "git update-ref --no-deref <target_ref> <candidate_commit> <expected_base>",
            "git update-ref --no-deref <target_ref> <candidate_commit>",
        )
        self.assert_failed(report, "documented_expected_base_cas")

    def test_duplicate_snapshot_key_is_detected(self) -> None:
        report = self.run_fixture(
            '"current_limits": { "max_cost_usd": 1.0 },',
            '"current_limits": {}, "current_limits": { "max_cost_usd": 1.0 },',
        )
        self.assert_failed(report, "parse:")

    def test_relaxed_snapshot_required_fields_are_detected(self) -> None:
        report = self.run_fixture(
            '"policy_hash", "contract_hash", "inputs"],',
            '"policy_hash", "inputs"],',
        )
        self.assert_failed(report, "probe:snapshot_approval_budget_missing_contract_hash")


if __name__ == "__main__":
    unittest.main()
