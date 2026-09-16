"""CTRF JSON report generation for hurl-orchestra."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .known_failures import KnownFailureMatch

SPEC_VERSION = "1.0.0"

_SOURCE_LINE = re.compile(r"^\s*\d+\s*\|\s*(\S.*)$")
_DETAIL_PREFIXES = ("actual:", "expected:")


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


def _load_files(report_path: Path) -> list[dict] | None:
    try:
        with report_path.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, list) else [data]


def _final_attempts(entries: list[dict]) -> list[dict]:
    """Collapse hurl retry attempts, keeping the last attempt per entry index.

    hurl emits one entry per attempt and reuses the entry index across the
    retries of a single request, so the last attempt carries the outcome.
    """
    final: dict[object, dict] = {}
    for position, entry in enumerate(entries):
        final[entry.get("index", position)] = entry
    return list(final.values())


def _entry_failed(entry: dict) -> bool:
    """Whether an entry failed.

    hurl reports success per assert and per file, never per entry, so the
    entry-level key is only honoured when a producer supplies one.
    """
    if "success" in entry:
        return not bool(entry["success"])
    return any(not a.get("success", True) for a in entry.get("asserts", []))


def _condense(message: str) -> str:
    """Flatten hurl's multi-line assert diagnostic into one reportable line."""
    lines = message.splitlines()
    visible = [line.strip() for line in lines if line.strip()]
    if not visible:
        return ""

    headline = visible[0]
    source = ""
    details: list[str] = []
    for line in lines:
        match = _SOURCE_LINE.match(line)
        if match is not None and not source:
            source = " ".join(match.group(1).split())
            continue
        body = " ".join(line.strip().lstrip("|").strip().lstrip("^").strip().split())
        if body.startswith(_DETAIL_PREFIXES) or "actual value is" in body:
            details.append(body)

    detail = ", ".join(details)
    if source and detail:
        return f"{headline}: {source} ({detail})"
    if source:
        return f"{headline}: {source}"
    if detail:
        return f"{headline}: {detail}"
    return headline


def _describe_assert(assertion: dict) -> str:
    message = assertion.get("message")
    if message:
        return _condense(str(message))
    return (
        f"type={assertion.get('type', '')} actual={assertion.get('actual', '')}"
        f" expected={assertion.get('expected', '')}"
    )


def _assert_message(entry: dict) -> str | None:
    failed_asserts = [a for a in entry.get("asserts", []) if not a.get("success", True)]
    if not failed_asserts:
        return None
    return " | ".join(_describe_assert(a) for a in failed_asserts)


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

    files = _load_files(report_path)
    if files is None:
        return [
            _placeholder(
                node_id,
                "failed",
                "Execution failed - could not read or parse report.json",
            )
        ]

    entries = _final_attempts(
        [entry for file_obj in files for entry in file_obj.get("entries", [])]
    )

    tests: list[dict] = []
    saw_failure = False
    for idx, entry in enumerate(entries, start=1):
        line = entry.get("line", 0)
        name = (
            f"{node_id}: entry {idx} (line {line})"
            if line
            else f"{node_id}: entry {idx}"
        )
        failed = _entry_failed(entry)
        saw_failure = saw_failure or failed
        test: dict = {
            "name": name,
            "status": "failed" if failed else "passed",
            "duration": entry.get("time", 0),
            "suite": [node_id],
        }
        if failed:
            message = _assert_message(entry)
            if message:
                test["message"] = message
            if known is not None:
                _tolerate(test, known)
        tests.append(test)

    # A file hurl failed without a failing assert (a runtime error, or a body
    # that never reached an assertion) must never be reported as all green.
    if not saw_failure and any(f.get("success") is False for f in files):
        unexplained = _placeholder(
            node_id, "failed", "hurl reported the file as failed"
        )
        if known is not None:
            _tolerate(unexplained, known)
        tests.append(unexplained)

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
