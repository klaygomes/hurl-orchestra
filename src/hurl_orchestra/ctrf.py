"""CTRF JSON report generation for hurl-orchestra."""

from __future__ import annotations

import json
from pathlib import Path

from .known_failures import KnownFailureMatch

SPEC_VERSION = "1.0.0"


def _placeholder(node_id: str, status: str, message: str | None = None) -> dict:
    test: dict = {
        "name": f"node {node_id}",
        "status": status,
        "duration": 0,
        "suite": [node_id],
    }
    if message:
        test["message"] = message
    return test


def _load_entries(report_path: Path) -> list[dict] | None:
    try:
        with report_path.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None
    file_results = data if isinstance(data, list) else [data]
    return [entry for file_obj in file_results for entry in file_obj.get("entries", [])]


def _assert_message(entry: dict) -> str | None:
    failed_asserts = [a for a in entry.get("asserts", []) if not a.get("success", True)]
    if not failed_asserts:
        return None
    return " | ".join(
        f"type={a.get('type', '')} actual={a.get('actual', '')}"
        f" expected={a.get('expected', '')}"
        for a in failed_asserts
    )


def _tolerate(test: dict, known: KnownFailureMatch) -> None:
    test["status"] = "other"
    test["flaky"] = True
    test["tags"] = [known.failure.name]
    test["message"] = known.describe()


def _build_tests(
    node_id: str,
    reports_path: Path,
    known: KnownFailureMatch | None,
    skipped_for: str | None,
) -> list[dict]:
    node_dir = reports_path / node_id
    report_path = node_dir / "report.json"

    if skipped_for is not None:
        return [
            _placeholder(node_id, "skipped", f"known failure upstream: {skipped_for}")
        ]
    if not node_dir.exists():
        return [_placeholder(node_id, "skipped")]
    if not report_path.exists():
        missing = _placeholder(
            node_id,
            "failed",
            "Execution failed - no hurl report generated (subprocess error or timeout)",
        )
        if known is not None:
            _tolerate(missing, known)
        return [missing]

    entries = _load_entries(report_path)
    if entries is None:
        return [
            _placeholder(
                node_id,
                "failed",
                "Execution failed - could not read or parse report.json",
            )
        ]

    tests: list[dict] = []
    for idx, entry in enumerate(entries, start=1):
        line = entry.get("line", 0)
        name = (
            f"{node_id}: entry {idx} (line {line})"
            if line
            else f"{node_id}: entry {idx}"
        )
        status = "passed" if entry.get("success", True) else "failed"
        test: dict = {
            "name": name,
            "status": status,
            "duration": entry.get("time", 0),
            "suite": [node_id],
        }
        if status == "failed":
            message = _assert_message(entry)
            if message:
                test["message"] = message
            if known is not None:
                _tolerate(test, known)
        tests.append(test)
    return tests


def build_ctrf(
    node_ids: list[str],
    reports_path: Path,
    start_ms: int,
    stop_ms: int,
    tolerated: dict[str, KnownFailureMatch] | None = None,
    skipped_known: dict[str, str] | None = None,
) -> dict:
    """Build a CTRF report dict from all node reports.

    Args:
        node_ids: List of all node IDs that were scheduled.
        reports_path: Directory containing per-node report subdirectories.
        start_ms: Wall-clock epoch milliseconds when execution started.
        stop_ms: Wall-clock epoch milliseconds when execution ended.
        tolerated: Nodes whose failure matched a declared known failure, by id.
        skipped_known: Nodes skipped because a tolerated node upstream produced
            no outputs, mapped to the ids of those upstream nodes.

    Returns:
        A dict conforming to the CTRF 1.0.0 schema.
    """
    tolerated = tolerated or {}
    skipped_known = skipped_known or {}
    all_tests: list[dict] = []
    for node_id in sorted(node_ids):
        all_tests.extend(
            _build_tests(
                node_id,
                reports_path,
                tolerated.get(node_id),
                skipped_known.get(node_id),
            )
        )

    counts = dict.fromkeys(("passed", "failed", "skipped", "other"), 0)
    for test in all_tests:
        counts[test["status"]] = counts.get(test["status"], 0) + 1

    return {
        "reportFormat": "CTRF",
        "specVersion": SPEC_VERSION,
        "results": {
            "tool": {"name": "hurl-orchestra"},
            "summary": {
                "tests": len(all_tests),
                "passed": counts["passed"],
                "failed": counts["failed"],
                "skipped": counts["skipped"],
                "pending": 0,
                "other": counts["other"],
                "start": start_ms,
                "stop": stop_ms,
                "duration": stop_ms - start_ms,
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
    tolerated: dict[str, KnownFailureMatch] | None = None,
    skipped_known: dict[str, str] | None = None,
) -> None:
    """Write the CTRF JSON report to *output_path*.

    Raises OSError on write failure.
    """
    report = build_ctrf(
        node_ids, reports_path, start_ms, stop_ms, tolerated, skipped_known
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
        fh.write("\n")
