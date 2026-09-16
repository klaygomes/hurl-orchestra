"""Tests for CTRF JSON report generation."""

from __future__ import annotations

import json
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

import pytest

from hurl_orchestra import build_ctrf
from hurl_orchestra.cli import main
from hurl_orchestra.ctrf import _condense, write_ctrf
from hurl_orchestra.orchestrator import run_hurl_orchestrator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

START_MS = 1_700_000_000_000
STOP_MS = 1_700_000_005_000


def _make_report(entries: list[dict], *, success: bool | None = None) -> list[dict]:
    if success is None:
        success = all(a.get("success", True) for e in entries for a in e.get("asserts", []))
    return [{"filename": "-", "entries": entries, "success": success, "time": sum(e.get("time", 0) for e in entries)}]


def _passed_entry(line: int = 1, time_ms: int = 100, index: int = 1) -> dict:
    """An entry as hurl actually emits it: success lives on asserts, not here."""
    return {"index": index, "line": line, "calls": [], "captures": [], "asserts": [{"line": line, "success": True, "type": "status", "actual": "200", "expected": "200"}], "time": time_ms}


def _failed_entry(line: int = 5, time_ms: int = 200, index: int = 1) -> dict:
    return {"index": index, "line": line, "calls": [], "captures": [], "asserts": [{"line": line, "success": False, "type": "status", "actual": "404", "expected": "200"}], "time": time_ms}


def ok() -> CompletedProcess[str]:
    return CompletedProcess([], 0, "", "")


def fail() -> CompletedProcess[str]:
    return CompletedProcess([], 1, "", "assertion failed")


def writing_report(data: list[dict]) -> object:
    def _run(cmd: list[str], **kwargs: object) -> CompletedProcess[str]:
        for i, part in enumerate(cmd):
            if part == "--report-json":
                (Path(cmd[i + 1]) / "report.json").write_text(json.dumps(data))
        return ok()

    return _run


def hurl_file(path: Path, *, id: str = "node") -> None:
    path.write_text(f"---\nid: {id}\n---\n")


# ---------------------------------------------------------------------------
# Unit tests for _build_tests / build_ctrf
# ---------------------------------------------------------------------------


def test_build_ctrf_missing_dir_produces_skipped_test(tmp_path: Path) -> None:
    report = build_ctrf(["ghost"], tmp_path, START_MS, STOP_MS)
    tests = report["results"]["tests"]
    assert len(tests) == 1
    assert tests[0]["status"] == "skipped"
    assert tests[0]["name"] == "node ghost"
    assert tests[0]["suite"] == ["ghost"]


def test_build_ctrf_missing_report_produces_failed_test(tmp_path: Path) -> None:
    (tmp_path / "ghost").mkdir()
    report = build_ctrf(["ghost"], tmp_path, START_MS, STOP_MS)
    tests = report["results"]["tests"]
    assert len(tests) == 1
    assert tests[0]["status"] == "failed"
    assert "Execution failed" in tests[0]["message"]


def test_build_ctrf_success_entry(tmp_path: Path) -> None:
    node_dir = tmp_path / "ping"
    node_dir.mkdir()
    (node_dir / "report.json").write_text(json.dumps(_make_report([_passed_entry(line=3, time_ms=150)])))

    report = build_ctrf(["ping"], tmp_path, START_MS, STOP_MS)
    tests = report["results"]["tests"]
    assert len(tests) == 1
    assert tests[0]["status"] == "passed"
    assert tests[0]["name"] == "ping: entry 1 (line 3)"
    assert tests[0]["duration"] == 150
    assert tests[0]["suite"] == ["ping"]
    assert "message" not in tests[0]


def test_build_ctrf_failed_entry_has_message(tmp_path: Path) -> None:
    node_dir = tmp_path / "ping"
    node_dir.mkdir()
    (node_dir / "report.json").write_text(json.dumps(_make_report([_failed_entry(line=5, time_ms=200)])))

    report = build_ctrf(["ping"], tmp_path, START_MS, STOP_MS)
    tests = report["results"]["tests"]
    assert tests[0]["status"] == "failed"
    assert "type=status" in tests[0]["message"]
    assert "actual=404" in tests[0]["message"]
    assert "expected=200" in tests[0]["message"]


def test_build_ctrf_honours_explicit_entry_success_when_present(tmp_path: Path) -> None:
    entry = {"index": 1, "line": 1, "calls": [], "captures": [], "asserts": [], "time": 100, "success": False}
    node_dir = tmp_path / "ping"
    node_dir.mkdir()
    (node_dir / "report.json").write_text(json.dumps(_make_report([entry])))

    report = build_ctrf(["ping"], tmp_path, START_MS, STOP_MS)
    assert "message" not in report["results"]["tests"][0]


def test_build_ctrf_timing_preserved_in_ms(tmp_path: Path) -> None:
    node_dir = tmp_path / "ping"
    node_dir.mkdir()
    (node_dir / "report.json").write_text(json.dumps(_make_report([_passed_entry(time_ms=4321)])))

    report = build_ctrf(["ping"], tmp_path, START_MS, STOP_MS)
    assert report["results"]["tests"][0]["duration"] == 4321


def test_build_ctrf_summary_totals(tmp_path: Path) -> None:
    for node_id, entries in [("a", [_passed_entry()]), ("b", [_failed_entry()]), ("c", [])]:
        d = tmp_path / node_id
        d.mkdir()
        (d / "report.json").write_text(json.dumps(_make_report(entries)))
    # "ghost" has no directory → skipped
    report = build_ctrf(["a", "b", "c", "ghost"], tmp_path, START_MS, STOP_MS)
    summary = report["results"]["summary"]
    assert summary["tests"] == 3   # a:1 passed, b:1 failed, ghost:1 skipped (c has 0 entries)
    assert summary["passed"] == 1
    assert summary["failed"] == 1
    assert summary["skipped"] == 1
    assert summary["pending"] == 0
    assert summary["other"] == 0
    assert summary["start"] == START_MS
    assert summary["stop"] == STOP_MS
    assert summary["duration"] == STOP_MS - START_MS


def test_build_ctrf_schema_fields(tmp_path: Path) -> None:
    node_dir = tmp_path / "ping"
    node_dir.mkdir()
    (node_dir / "report.json").write_text(json.dumps(_make_report([_passed_entry()])))

    report = build_ctrf(["ping"], tmp_path, START_MS, STOP_MS)
    assert report["reportFormat"] == "CTRF"
    assert report["specVersion"] == "1.0.0"
    assert report["results"]["tool"] == {"name": "hurl-orchestra"}


def test_build_ctrf_node_ids_sorted(tmp_path: Path) -> None:
    for node_id in ["z_node", "a_node"]:
        d = tmp_path / node_id
        d.mkdir()
        (d / "report.json").write_text(json.dumps(_make_report([_passed_entry()])))

    report = build_ctrf(["z_node", "a_node"], tmp_path, START_MS, STOP_MS)
    names = [t["name"] for t in report["results"]["tests"]]
    assert names[0].startswith("a_node")
    assert names[1].startswith("z_node")


def test_write_ctrf_creates_valid_json_file(tmp_path: Path) -> None:
    node_dir = tmp_path / "ping"
    node_dir.mkdir()
    (node_dir / "report.json").write_text(json.dumps(_make_report([_passed_entry()])))
    output = tmp_path / "results.json"

    write_ctrf(["ping"], tmp_path, output, START_MS, STOP_MS)

    assert output.exists()
    data = json.loads(output.read_text())
    assert data["reportFormat"] == "CTRF"


def test_write_ctrf_creates_parent_dirs(tmp_path: Path) -> None:
    node_dir = tmp_path / "ping"
    node_dir.mkdir()
    (node_dir / "report.json").write_text(json.dumps(_make_report([_passed_entry()])))
    output = tmp_path / "nested" / "deep" / "results.json"

    write_ctrf(["ping"], tmp_path, output, START_MS, STOP_MS)
    assert output.exists()


# ---------------------------------------------------------------------------
# Regression: hurl reports success per assert and per file, never per entry
# ---------------------------------------------------------------------------


def test_failed_entry_without_entry_level_success_is_reported_failed(tmp_path: Path) -> None:
    node_dir = tmp_path / "ping"
    node_dir.mkdir()
    (node_dir / "report.json").write_text(json.dumps(_make_report([_failed_entry()])))

    report = build_ctrf(["ping"], tmp_path, START_MS, STOP_MS)

    assert report["results"]["summary"]["failed"] == 1
    assert report["results"]["summary"]["passed"] == 0
    assert report["results"]["tests"][0]["status"] == "failed"


def test_retry_attempts_collapse_to_the_last_attempt(tmp_path: Path) -> None:
    node_dir = tmp_path / "flaky"
    node_dir.mkdir()
    attempts = [_failed_entry(line=3, index=1), _passed_entry(line=3, index=1)]
    (node_dir / "report.json").write_text(json.dumps(_make_report(attempts, success=True)))

    report = build_ctrf(["flaky"], tmp_path, START_MS, STOP_MS)

    assert report["results"]["summary"]["tests"] == 1
    assert report["results"]["summary"]["failed"] == 0
    assert report["results"]["tests"][0]["status"] == "passed"


def test_exhausted_retries_report_one_failure(tmp_path: Path) -> None:
    node_dir = tmp_path / "flaky"
    node_dir.mkdir()
    attempts = [_failed_entry(index=1), _failed_entry(index=1), _failed_entry(index=1)]
    (node_dir / "report.json").write_text(json.dumps(_make_report(attempts)))

    report = build_ctrf(["flaky"], tmp_path, START_MS, STOP_MS)

    assert report["results"]["summary"]["tests"] == 1
    assert report["results"]["summary"]["failed"] == 1


def test_distinct_requests_are_kept_separate(tmp_path: Path) -> None:
    node_dir = tmp_path / "chain"
    node_dir.mkdir()
    entries = [_passed_entry(line=1, index=1), _failed_entry(line=9, index=2)]
    (node_dir / "report.json").write_text(json.dumps(_make_report(entries)))

    report = build_ctrf(["chain"], tmp_path, START_MS, STOP_MS)

    summary = report["results"]["summary"]
    assert summary["tests"] == 2
    assert summary["passed"] == 1
    assert summary["failed"] == 1


def test_file_failed_without_failing_assert_is_never_all_green(tmp_path: Path) -> None:
    node_dir = tmp_path / "ping"
    node_dir.mkdir()
    entry = {"index": 1, "line": 1, "calls": [], "captures": [], "asserts": [], "time": 10}
    (node_dir / "report.json").write_text(json.dumps(_make_report([entry], success=False)))

    report = build_ctrf(["ping"], tmp_path, START_MS, STOP_MS)

    assert report["results"]["summary"]["failed"] == 1
    assert any("failed" in t.get("message", "") for t in report["results"]["tests"])


def test_file_succeeded_stays_green(tmp_path: Path) -> None:
    node_dir = tmp_path / "ping"
    node_dir.mkdir()
    (node_dir / "report.json").write_text(json.dumps(_make_report([_passed_entry()])))

    report = build_ctrf(["ping"], tmp_path, START_MS, STOP_MS)

    assert report["results"]["summary"]["failed"] == 0
    assert report["results"]["summary"]["passed"] == 1


def test_condense_status_assert_message() -> None:
    message = (
        'Assert status code\n  --> t.hurl:3:6\n   |\n'
        '   | GET https://example.invalid\n   | ...\n'
        ' 3 | HTTP 599\n   |      ^^^ actual value is <200>\n   |'
    )
    assert _condense(message) == (
        "Assert status code: HTTP 599 (actual value is <200>)"
    )


def test_condense_jsonpath_assert_message() -> None:
    message = (
        'Assert failure\n  --> t.hurl:5:0\n   |\n'
        '   | GET https://example.invalid\n   | ...\n'
        ' 5 | jsonpath "$.country" == "XX"\n'
        '   |   actual:   string <SE>\n'
        '   |   expected: string <XX>\n   |'
    )
    assert _condense(message) == (
        'Assert failure: jsonpath "$.country" == "XX" '
        "(actual: string <SE>, expected: string <XX>)"
    )


def test_real_hurl_assert_message_reaches_the_report(tmp_path: Path) -> None:
    entry = {
        "index": 1,
        "line": 3,
        "calls": [],
        "captures": [],
        "asserts": [
            {"line": 3, "success": True},
            {
                "line": 3,
                "success": False,
                "message": (
                    'Assert status code\n  --> t.hurl:3:6\n   |\n'
                    ' 3 | HTTP 200\n   |      ^^^ actual value is <500>\n   |'
                ),
            },
        ],
        "time": 10,
    }
    node_dir = tmp_path / "ping"
    node_dir.mkdir()
    (node_dir / "report.json").write_text(json.dumps(_make_report([entry])))

    report = build_ctrf(["ping"], tmp_path, START_MS, STOP_MS)

    test = report["results"]["tests"][0]
    assert test["status"] == "failed"
    assert test["message"] == "Assert status code: HTTP 200 (actual value is <500>)"


# ---------------------------------------------------------------------------
# Orchestrator integration tests
# ---------------------------------------------------------------------------


def test_orchestrator_no_ctrf_when_flag_none(tmp_path: Path) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")
    with (
        patch("subprocess.run", return_value=ok()),
        patch("shutil.make_archive"),
        patch("hurl_orchestra.orchestrator.write_ctrf") as mock_ctrf,
    ):
        run_hurl_orchestrator(str(tmp_path), report_ctrf=None)
    mock_ctrf.assert_not_called()


def test_orchestrator_ctrf_written_when_flag_set(tmp_path: Path) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")
    output = str(tmp_path / "results.json")
    with (
        patch("subprocess.run", return_value=ok()),
        patch("shutil.make_archive"),
        patch("hurl_orchestra.orchestrator.write_ctrf") as mock_ctrf,
    ):
        run_hurl_orchestrator(str(tmp_path), report_ctrf=output)
    mock_ctrf.assert_called_once()
    call_kwargs = mock_ctrf.call_args
    assert call_kwargs.args[2] == Path(output)


def test_orchestrator_ctrf_written_even_on_failure(tmp_path: Path) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")
    with (
        patch("subprocess.run", return_value=fail()),
        patch("shutil.make_archive"),
        patch("hurl_orchestra.orchestrator.write_ctrf") as mock_ctrf,
    ):
        result = run_hurl_orchestrator(str(tmp_path), report_ctrf="results.json")
    assert result is False
    mock_ctrf.assert_called_once()


def test_orchestrator_ctrf_real_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")
    output = tmp_path / "results.json"
    data = _make_report([_passed_entry()])
    with (
        patch("subprocess.run", side_effect=writing_report(data)),
        patch("shutil.make_archive"),
    ):
        run_hurl_orchestrator(str(tmp_path), report_ctrf=str(output))

    assert output.exists()
    report = json.loads(output.read_text())
    assert report["reportFormat"] == "CTRF"
    assert report["results"]["summary"]["passed"] == 1
    out = capsys.readouterr().out
    assert "CTRF report saved to" in out


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------


def test_cli_report_ctrf_default_is_none() -> None:
    with (
        patch("hurl_orchestra.cli.run_hurl_orchestrator", return_value=True) as mock,
        patch("sys.argv", ["hurl-orchestra"]),
    ):
        main()
    assert mock.call_args.kwargs["report_ctrf"] is None


def test_cli_report_ctrf_flag_passed_to_orchestrator() -> None:
    with (
        patch("hurl_orchestra.cli.run_hurl_orchestrator", return_value=True) as mock,
        patch("sys.argv", ["hurl-orchestra", "--report-ctrf", "results.json"]),
    ):
        main()
    assert mock.call_args.kwargs["report_ctrf"] == "results.json"


def test_cli_report_ctrf_with_files_mode() -> None:
    with (
        patch("hurl_orchestra.cli.run_hurl_orchestrator", return_value=True) as mock,
        patch("sys.argv", ["hurl-orchestra", "a.hurl", "--report-ctrf", "r.json"]),
    ):
        main()
    assert mock.call_args.kwargs["report_ctrf"] == "r.json"
