"""CTRF JSON report generation for hurl-orchestra."""

from __future__ import annotations

import json
from pathlib import Path

SPEC_VERSION = "1.0.0"


def _build_tests(node_id: str, reports_path: Path) -> list[dict]:
    node_dir = reports_path / node_id
    report_path = node_dir / "report.json"

    if not node_dir.exists():
        return [
            {
                "name": f"node {node_id}",
                "status": "skipped",
                "duration": 0,
                "suite": [node_id],
            }
        ]

    if not report_path.exists():
        return [
            {
                "name": f"node {node_id}",
                "status": "failed",
                "duration": 0,
                "suite": [node_id],
                "message": (
                    "Execution failed - no hurl report generated"
                    " (subprocess error or timeout)"
                ),
            }
        ]

    try:
        with report_path.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return [
            {
                "name": f"node {node_id}",
                "status": "failed",
                "duration": 0,
                "suite": [node_id],
                "message": "Execution failed - could not read or parse report.json",
            }
        ]

    file_results = data if isinstance(data, list) else [data]
    tests: list[dict] = []

    for file_obj in file_results:
        for idx, entry in enumerate(file_obj.get("entries", []), start=1):
            line = entry.get("line", 0)
            name = (
                f"{node_id}: entry {idx} (line {line})"
                if line
                else f"{node_id}: entry {idx}"
            )
            status = "passed" if entry.get("success", True) else "failed"
            duration = entry.get("time", 0)

            test: dict = {
                "name": name,
                "status": status,
                "duration": duration,
                "suite": [node_id],
            }

            if status == "failed":
                failed_asserts = [
                    a for a in entry.get("asserts", []) if not a.get("success", True)
                ]
                if failed_asserts:
                    test["message"] = " | ".join(
                        f"type={a.get('type', '')} actual={a.get('actual', '')}"
                        f" expected={a.get('expected', '')}"
                        for a in failed_asserts
                    )

            tests.append(test)

    return tests


def build_ctrf(
    node_ids: list[str], reports_path: Path, start_ms: int, stop_ms: int
) -> dict:
    """Build a CTRF report dict from all node reports.

    Args:
        node_ids: List of all node IDs that were scheduled.
        reports_path: Directory containing per-node report subdirectories.
        start_ms: Wall-clock epoch milliseconds when execution started.
        stop_ms: Wall-clock epoch milliseconds when execution ended.

    Returns:
        A dict conforming to the CTRF 1.0.0 schema.
    """
    all_tests: list[dict] = []
    for node_id in sorted(node_ids):
        all_tests.extend(_build_tests(node_id, reports_path))

    passed = sum(1 for t in all_tests if t["status"] == "passed")
    failed = sum(1 for t in all_tests if t["status"] == "failed")
    skipped = sum(1 for t in all_tests if t["status"] == "skipped")
    duration = stop_ms - start_ms

    return {
        "reportFormat": "CTRF",
        "specVersion": SPEC_VERSION,
        "results": {
            "tool": {"name": "hurl-orchestra"},
            "summary": {
                "tests": len(all_tests),
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "pending": 0,
                "other": 0,
                "start": start_ms,
                "stop": stop_ms,
                "duration": duration,
            },
            "tests": all_tests,
        },
    }


def write_ctrf(
    node_ids: list[str],
    reports_path: Path,
    output_path: Path,
    start_ms: int,
    stop_ms: int,
) -> None:
    """Write the CTRF JSON report to *output_path*.

    Raises OSError on write failure.
    """
    report = build_ctrf(node_ids, reports_path, start_ms, stop_ms)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
        fh.write("\n")
