import argparse
import re
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
GOVERNANCE_RECORD = REPOSITORY_ROOT / "GOVERNANCE.md"
LEGACY_RELEASES = {"v3.2.0"}


def normalized_version(version):
    value = version.strip()
    if value.startswith("biometry-ood-"):
        value = value.removeprefix("biometry-ood-")
    if not value.startswith("v"):
        value = f"v{value}"
    return value


def validate_governance(version, record_text, allow_pending=False):
    version = normalized_version(version)
    if version in LEGACY_RELEASES:
        return []

    errors = []
    expected_tag = f"biometry-ood-{version}"
    proposed = re.search(r"^- Proposed release:\s*`([^`]+)`\s*$", record_text, re.M)
    if not proposed or proposed.group(1) != expected_tag:
        errors.append(f"GOVERNANCE.md must name proposed release `{expected_tag}`.")

    for label in ("Approval authority", "Approval identifier", "Approval date"):
        match = re.search(rf"^- {re.escape(label)}:\s*(.+?)\s*$", record_text, re.M)
        if not match:
            errors.append(f"GOVERNANCE.md is missing `{label}`.")
            continue
        value = match.group(1).strip()
        if not value or "PENDING" in value.upper():
            errors.append(f"GOVERNANCE.md `{label}` is still pending.")

    zenodo = re.search(
        r"^- Zenodo GitHub integration:\s*(.+?)\s*$", record_text, re.M
    )
    if not zenodo or not zenodo.group(1).strip().lower().startswith("enabled"):
        errors.append("GOVERNANCE.md must record Zenodo GitHub integration as enabled.")

    if errors and allow_pending:
        return []
    return errors


def main():
    parser = argparse.ArgumentParser(
        description="Block public releases until institutional authorization is recorded."
    )
    parser.add_argument("--version", required=True)
    parser.add_argument("--record", type=Path, default=GOVERNANCE_RECORD)
    parser.add_argument(
        "--allow-pending",
        action="store_true",
        help="Permit a pending record for a dry-run build only.",
    )
    args = parser.parse_args()
    record_text = args.record.read_text(encoding="utf-8")
    errors = validate_governance(args.version, record_text, args.allow_pending)
    if errors:
        for error in errors:
            print(f"release governance check failed: {error}", file=sys.stderr)
        return 1
    if args.allow_pending and "PENDING" in record_text.upper():
        print("warning: pending release governance allowed for dry-run build only")
    else:
        print(f"release governance verified for {normalized_version(args.version)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
