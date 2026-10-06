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
            '    "bound_hash": "sha256:9b2e4c7a1f05d38e6c94a2b71e05f38d9a41c6b82e7d3f05a1c9e47b3d8206f5",\n',
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


if __name__ == "__main__":
    unittest.main()
