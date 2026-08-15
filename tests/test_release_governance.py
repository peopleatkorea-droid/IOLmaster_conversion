import unittest

from deployment.check_release_governance import validate_governance


APPROVED_RECORD = """# Public model-release governance record

## Release under preparation

- Proposed release: `biometry-ood-v3.2.1`
- Approval authority: Example institutional office
- Approval identifier: TEST-APPROVAL-001
- Approval date: 2026-08-15
- Zenodo GitHub integration: Enabled for test fixture
"""


class ReleaseGovernanceTests(unittest.TestCase):
    def test_approved_matching_release_passes(self):
        self.assertEqual(validate_governance("v3.2.1", APPROVED_RECORD), [])

    def test_pending_record_blocks_release(self):
        pending = APPROVED_RECORD.replace(
            "Example institutional office",
            "PENDING AUTHOR CONFIRMATION",
        )
        errors = validate_governance("v3.2.1", pending)
        self.assertTrue(any("Approval authority" in error for error in errors))

    def test_mismatched_release_blocks_release(self):
        errors = validate_governance("v3.2.2", APPROVED_RECORD)
        self.assertTrue(any("biometry-ood-v3.2.2" in error for error in errors))

    def test_missing_zenodo_integration_blocks_release(self):
        disabled = APPROVED_RECORD.replace(
            "Enabled for test fixture", "Not enabled"
        )
        errors = validate_governance("v3.2.1", disabled)
        self.assertTrue(any("Zenodo" in error for error in errors))

    def test_legacy_release_remains_reproducible(self):
        self.assertEqual(validate_governance("v3.2.0", ""), [])

    def test_allow_pending_is_dry_run_escape_hatch(self):
        self.assertEqual(validate_governance("v3.2.1", "", allow_pending=True), [])


if __name__ == "__main__":
    unittest.main()
