"""Tests for declared known failures: parsing, matching, execution and CTRF."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

import pytest

from hurl_orchestra import build_ctrf, run_hurl_orchestrator
from hurl_orchestra.cli import main
from hurl_orchestra.known_failures import (
    KnownFailureError,
    match_known_failure,
    parse_known_failures,
)

TODAY = date(2026, 6, 1)

DB_POOL = {
    "name": "db_pool_exhausted",
    "reason": "Shared test database at its connection limit",
    "status": 500,
    "header": {"name": "X-Error-Code", "pattern": r"^ERR-DB-\d+$"},
}


def hurl_file(
    path: Path,
    *,
    id: str,
    deps: list[str] | None = None,
    known: list[dict] | None = None,
) -> None:
    lines = [f"id: {id}"]
    if deps:
        lines.append(f"deps: {json.dumps(deps)}")
    if known is not None:
        lines.append(f"known_failures: {json.dumps(known)}")
    path.write_text(
        "---\n" + "\n".join(lines) + "\n---\nGET https://example.test\nHTTP 200\n"
    )


def report(*calls: dict, success: bool = False) -> list[dict]:
    return [
        {
            "filename": "-",
            "entries": [
                {
                    "index": 1,
                    "line": 1,
                    "calls": list(calls),
                    "captures": [],
                    "asserts": [
                        {
                            "success": success,
                            "type": "status",
                            "actual": "500",
                            "expected": "200",
                            "line": 2,
                        }
                    ],
                    "time": 12,
                    "success": success,
                }
            ],
            "success": success,
            "time": 12,
        }
    ]


def call(
    status: int, headers: dict[str, str] | None = None, body: str | None = None
) -> dict:
    response: dict = {
        "status": status,
        "headers": [{"name": k, "value": v} for k, v in (headers or {}).items()],
    }
    if body is not None:
        response["body"] = body
    return {
        "request": {"method": "GET", "url": "https://example.test"},
        "response": response,
    }


def write_report(
    report_dir: Path, data: list[dict], bodies: dict[str, str] | None = None
) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "report.json").write_text(json.dumps(data))
    for rel, text in (bodies or {}).items():
        target = report_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)


def runner(outcomes: dict[str, tuple[int, str, list[dict] | None]]) -> object:
    def _run(cmd: list[str], **kwargs: object) -> CompletedProcess[str]:
        report_dir = Path(cmd[cmd.index("--report-json") + 1])
        returncode, stderr, data = outcomes[report_dir.name]
        if data is not None:
            write_report(report_dir, data)
        return CompletedProcess(cmd, returncode, "", stderr)

    return _run


FAILING_500 = (
    1,
    "error: Assert status code\n   actual value is <500>\n",
    report(call(500, {"X-Error-Code": "ERR-DB-53300"})),
)
PASSING = (0, "", report(call(200), success=True))


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def test_parse_accepts_full_entry() -> None:
    [failure] = parse_known_failures(
        [
            {
                **DB_POOL,
                "until": "2026-12-31",
                "link": "https://example.test/runbook",
                "body": "too many",
                "stderr": "500",
            }
        ],
        "node",
    )
    assert failure.name == "db_pool_exhausted"
    assert failure.status == 500
    assert failure.header_name == "X-Error-Code"
    assert failure.until == date(2026, 12, 31)
    assert failure.link == "https://example.test/runbook"
    assert failure.body_pattern is not None and failure.stderr_pattern is not None


def test_parse_accepts_yaml_date_object() -> None:
    [failure] = parse_known_failures([{**DB_POOL, "until": date(2026, 12, 31)}], "node")
    assert failure.until == date(2026, 12, 31)


def test_parse_none_is_empty() -> None:
    assert parse_known_failures(None, "node") == []


@pytest.mark.parametrize(
    ("raw", "fragment"),
    [
        ("nope", "must be a list"),
        (["nope"], "must be a mapping"),
        ([{"reason": "r", "status": 500}], "needs a non-empty string 'name'"),
        (
            [{"name": "n", "reason": " ", "status": 500}],
            "needs a non-empty string 'reason'",
        ),
        ([{"name": "n", "reason": "r"}], "must set at least one of"),
        (
            [{"name": "n", "reason": "r", "header": "X-Error-Code"}],
            "'header' must be a mapping",
        ),
        (
            [{"name": "n", "reason": "r", "header": {"name": "X"}}],
            "needs a non-empty string 'pattern'",
        ),
        (
            [{"name": "n", "reason": "r", "header": {"name": "X", "pattern": "("}}],
            "not a valid regex",
        ),
        ([{"name": "n", "reason": "r", "body": "["}], "'body' is not a valid regex"),
        (
            [{"name": "n", "reason": "r", "status": "500"}],
            "'status' must be an integer",
        ),
        ([{"name": "n", "reason": "r", "status": True}], "'status' must be an integer"),
        (
            [{"name": "n", "reason": "r", "status": 500, "until": "soon"}],
            "'until' must be a YYYY-MM-DD date",
        ),
        (
            [{"name": "n", "reason": "r", "status": 500, "until": 20261231}],
            "'until' must be a YYYY-MM-DD date",
        ),
        (
            [{"name": "n", "reason": "r", "status": 500, "link": 3}],
            "'link' must be a string",
        ),
        ([{**DB_POOL}, {**DB_POOL}], "declares 'db_pool_exhausted' twice"),
    ],
)
def test_parse_rejects_malformed_entries(raw: object, fragment: str) -> None:
    with pytest.raises(KnownFailureError, match=fragment):
        parse_known_failures(raw, "node")


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------


def test_match_on_status_alone(tmp_path: Path) -> None:
    write_report(tmp_path, report(call(500)))
    failures = parse_known_failures(
        [{"name": "n", "reason": "r", "status": 500}], "node"
    )
    match, expired = match_known_failure(failures, tmp_path, "", TODAY)
    assert match is not None and match.matched == ("status 500",)
    assert expired == []


def test_status_mismatch_does_not_match(tmp_path: Path) -> None:
    write_report(tmp_path, report(call(502)))
    failures = parse_known_failures(
        [{"name": "n", "reason": "r", "status": 500}], "node"
    )
    assert match_known_failure(failures, tmp_path, "", TODAY) == (None, [])


def test_header_name_is_case_insensitive(tmp_path: Path) -> None:
    write_report(tmp_path, report(call(500, {"x-error-code": "ERR-DB-1"})))
    match, _ = match_known_failure(
        parse_known_failures([DB_POOL], "node"), tmp_path, "", TODAY
    )
    assert match is not None
    assert match.matched == ("status 500", "header X-Error-Code=ERR-DB-1")


def test_header_value_outside_pattern_does_not_match(tmp_path: Path) -> None:
    write_report(tmp_path, report(call(500, {"X-Error-Code": "ERR-AUTH-1"})))
    assert (
        match_known_failure(
            parse_known_failures([DB_POOL], "node"), tmp_path, "", TODAY
        )[0]
        is None
    )


def test_all_declared_fields_must_match(tmp_path: Path) -> None:
    write_report(tmp_path, report(call(503, {"X-Error-Code": "ERR-DB-1"})))
    assert (
        match_known_failure(
            parse_known_failures([DB_POOL], "node"), tmp_path, "", TODAY
        )[0]
        is None
    )


def test_body_is_read_from_store_file(tmp_path: Path) -> None:
    write_report(
        tmp_path,
        report(call(500, body="store/abc_response.json")),
        {"store/abc_response.json": '{"detail":"too many connections for role"}'},
    )
    failures = parse_known_failures(
        [{"name": "n", "reason": "r", "body": "too many connections"}], "node"
    )
    match, _ = match_known_failure(failures, tmp_path, "", TODAY)
    assert match is not None and match.matched == ("body ~ /too many connections/",)


def test_body_without_store_file_does_not_match(tmp_path: Path) -> None:
    write_report(tmp_path, report(call(500, body="store/missing.json")))
    failures = parse_known_failures(
        [{"name": "n", "reason": "r", "body": "anything"}], "node"
    )
    assert match_known_failure(failures, tmp_path, "", TODAY)[0] is None


def test_stderr_matches_without_any_report(tmp_path: Path) -> None:
    failures = parse_known_failures(
        [{"name": "n", "reason": "r", "stderr": "connection refused"}], "node"
    )
    match, _ = match_known_failure(
        failures, tmp_path, "error: connection refused\n", TODAY
    )
    assert match is not None and match.matched == ("stderr ~ /connection refused/",)


def test_status_without_report_does_not_match(tmp_path: Path) -> None:
    failures = parse_known_failures(
        [{"name": "n", "reason": "r", "status": 500}], "node"
    )
    assert match_known_failure(failures, tmp_path, "boom", TODAY)[0] is None


def test_last_call_is_the_one_inspected(tmp_path: Path) -> None:
    write_report(
        tmp_path, report(call(200), call(200), call(500, {"X-Error-Code": "ERR-DB-9"}))
    )
    match, _ = match_known_failure(
        parse_known_failures([DB_POOL], "node"), tmp_path, "", TODAY
    )
    assert match is not None and "ERR-DB-9" in match.matched[1]


def test_expired_entry_is_skipped_and_reported(tmp_path: Path) -> None:
    write_report(tmp_path, report(call(500)))
    failures = parse_known_failures(
        [{"name": "old", "reason": "r", "status": 500, "until": "2026-01-01"}], "node"
    )
    match, expired = match_known_failure(failures, tmp_path, "", TODAY)
    assert match is None
    assert [f.name for f in expired] == ["old"]


def test_entry_valid_until_today_still_matches(tmp_path: Path) -> None:
    write_report(tmp_path, report(call(500)))
    failures = parse_known_failures(
        [{"name": "n", "reason": "r", "status": 500, "until": TODAY.isoformat()}],
        "node",
    )
    assert match_known_failure(failures, tmp_path, "", TODAY)[0] is not None


def test_first_matching_entry_wins(tmp_path: Path) -> None:
    write_report(tmp_path, report(call(500)))
    failures = parse_known_failures(
        [
            {"name": "first", "reason": "r", "status": 500},
            {"name": "second", "reason": "r", "status": 500},
        ],
        "node",
    )
    match, _ = match_known_failure(failures, tmp_path, "", TODAY)
    assert match is not None and match.failure.name == "first"


def test_corrupt_report_only_allows_stderr(tmp_path: Path) -> None:
    (tmp_path / "report.json").write_text("{not json")
    by_status = parse_known_failures(
        [{"name": "s", "reason": "r", "status": 500}], "node"
    )
    by_stderr = parse_known_failures(
        [{"name": "e", "reason": "r", "stderr": "500"}], "node"
    )
    assert match_known_failure(by_status, tmp_path, "<500>", TODAY)[0] is None
    assert match_known_failure(by_stderr, tmp_path, "<500>", TODAY)[0] is not None


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def test_tolerated_node_is_reported_and_run_succeeds(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "create.hurl", id="create", known=[DB_POOL])
    with patch("subprocess.run", side_effect=runner({"create": FAILING_500})):
        ok = run_hurl_orchestrator(str(tmp_path))
    out = capsys.readouterr().out
    assert ok is True
    assert "KNOWN FAILURE: create [db_pool_exhausted] Shared test database" in out
    assert "actual value is <500>" in out
    assert "FAILED: create" not in out
    assert "Known failures tolerated: 1 (db_pool_exhausted: create)" in out


def test_dependents_of_tolerated_node_are_skipped_without_failing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "create.hurl", id="create", known=[DB_POOL])
    hurl_file(tmp_path / "update.hurl", id="update", deps=["create"])
    hurl_file(tmp_path / "delete.hurl", id="delete", deps=["update"])
    with patch("subprocess.run", side_effect=runner({"create": FAILING_500})) as run:
        ok = run_hurl_orchestrator(str(tmp_path))
    out = capsys.readouterr().out
    assert ok is True
    assert "SKIPPED: update (known failure upstream: create)" in out
    assert "SKIPPED: delete (known failure upstream: update)" in out
    assert run.call_count == 1


def test_unmatched_failure_still_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "create.hurl", id="create", known=[DB_POOL])
    other = (1, "actual value is <404>", report(call(404)))
    with patch("subprocess.run", side_effect=runner({"create": other})):
        ok = run_hurl_orchestrator(str(tmp_path))
    out = capsys.readouterr().out
    assert ok is False
    assert "FAILED: create" in out
    assert "KNOWN FAILURE" not in out


def test_strict_turns_tolerance_off(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "create.hurl", id="create", known=[DB_POOL])
    with patch("subprocess.run", side_effect=runner({"create": FAILING_500})):
        ok = run_hurl_orchestrator(str(tmp_path), strict=True)
    out = capsys.readouterr().out
    assert ok is False
    assert "FAILED: create" in out
    assert "KNOWN FAILURE" not in out


def test_expired_entry_fails_and_says_so(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(
        tmp_path / "create.hurl",
        id="create",
        known=[{**DB_POOL, "until": "2000-01-01"}],
    )
    with patch("subprocess.run", side_effect=runner({"create": FAILING_500})):
        ok = run_hurl_orchestrator(str(tmp_path))
    out = capsys.readouterr().out
    assert ok is False
    assert "FAILED: create" in out
    assert "known failure 'db_pool_exhausted' expired on 2000-01-01" in out


def test_real_failure_upstream_outranks_tolerated_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "tolerated.hurl", id="tolerated", known=[DB_POOL])
    hurl_file(tmp_path / "broken.hurl", id="broken")
    hurl_file(tmp_path / "leaf.hurl", id="leaf", deps=["tolerated", "broken"])
    outcomes = {"tolerated": FAILING_500, "broken": (1, "boom", None)}
    with patch("subprocess.run", side_effect=runner(outcomes)):
        ok = run_hurl_orchestrator(str(tmp_path))
    out = capsys.readouterr().out
    assert ok is False
    assert "SKIPPED: leaf (failed dependency: broken)" in out


def test_summary_groups_nodes_by_failure_name(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "a.hurl", id="a", known=[DB_POOL])
    hurl_file(tmp_path / "b.hurl", id="b", known=[DB_POOL])
    hurl_file(
        tmp_path / "c.hurl",
        id="c",
        known=[{"name": "flaky_dns", "reason": "resolver", "stderr": "resolve"}],
    )
    outcomes = {
        "a": FAILING_500,
        "b": FAILING_500,
        "c": (1, "could not resolve host", None),
    }
    with patch("subprocess.run", side_effect=runner(outcomes)):
        assert run_hurl_orchestrator(str(tmp_path)) is True
    assert (
        "Known failures tolerated: 3 (db_pool_exhausted: a, b; flaky_dns: c)"
        in capsys.readouterr().out
    )


def test_malformed_declaration_fails_discovery(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(
        tmp_path / "create.hurl", id="create", known=[{"name": "n", "reason": "r"}]
    )
    with patch("subprocess.run") as run:
        ok = run_hurl_orchestrator(str(tmp_path))
    assert ok is False
    assert (
        "known_failures[0] for 'create' must set at least one of"
        in capsys.readouterr().out
    )
    run.assert_not_called()


def test_cli_strict_flag_is_forwarded() -> None:
    with (
        patch("hurl_orchestra.cli.run_hurl_orchestrator", return_value=True) as run,
        patch.object(sys, "argv", ["hurl-orchestra", "--strict", "./tests"]),
    ):
        main()
    assert run.call_args.kwargs["strict"] is True


def test_cli_exits_zero_when_only_known_failures_occur(tmp_path: Path) -> None:
    hurl_file(tmp_path / "create.hurl", id="create", known=[DB_POOL])
    with (
        patch("subprocess.run", side_effect=runner({"create": FAILING_500})),
        patch.object(sys, "argv", ["hurl-orchestra", str(tmp_path)]),
    ):
        main()


def test_cli_exits_one_with_strict(tmp_path: Path) -> None:
    hurl_file(tmp_path / "create.hurl", id="create", known=[DB_POOL])
    with (
        patch("subprocess.run", side_effect=runner({"create": FAILING_500})),
        patch.object(sys, "argv", ["hurl-orchestra", "--strict", str(tmp_path)]),
        pytest.raises(SystemExit) as exc,
    ):
        main()
    assert exc.value.code == 1


# ---------------------------------------------------------------------------
# CTRF
# ---------------------------------------------------------------------------


def test_ctrf_marks_tolerated_entry_as_flaky_other(tmp_path: Path) -> None:
    hurl_file(tmp_path / "create.hurl", id="create", known=[DB_POOL])
    hurl_file(tmp_path / "update.hurl", id="update", deps=["create"])
    ctrf_path = tmp_path / "ctrf.json"
    with patch("subprocess.run", side_effect=runner({"create": FAILING_500})):
        run_hurl_orchestrator(str(tmp_path), report_ctrf=str(ctrf_path))
    results = json.loads(ctrf_path.read_text())["results"]
    by_suite = {t["suite"][0]: t for t in results["tests"]}

    create = by_suite["create"]
    assert create["status"] == "other"
    assert create["flaky"] is True
    assert create["tags"] == ["db_pool_exhausted"]
    assert (
        create["message"]
        == "Shared test database at its connection limit (matched: status 500, header X-Error-Code=ERR-DB-53300)"
    )

    update = by_suite["update"]
    assert update["status"] == "skipped"
    assert update["message"] == "known failure upstream: create"

    assert results["summary"] == {
        **results["summary"],
        "tests": 2,
        "passed": 0,
        "failed": 0,
        "skipped": 1,
        "other": 1,
    }


def test_ctrf_tolerated_node_without_report_is_still_other(tmp_path: Path) -> None:
    (tmp_path / "create").mkdir()
    failures = parse_known_failures(
        [{"name": "n", "reason": "timeout", "stderr": "timed out"}], "create"
    )
    match, _ = match_known_failure(
        failures, tmp_path / "create", "Hurl timed out", TODAY
    )
    assert match is not None
    ctrf = build_ctrf(["create"], tmp_path, 0, 1, tolerated={"create": match})
    [test] = ctrf["results"]["tests"]
    assert test["status"] == "other" and test["flaky"] is True and test["tags"] == ["n"]
    assert ctrf["results"]["summary"]["other"] == 1


def test_ctrf_without_known_failures_is_unchanged(tmp_path: Path) -> None:
    (tmp_path / "ping").mkdir()
    ctrf = build_ctrf(["ping", "ghost"], tmp_path, 0, 1)
    statuses = sorted(t["status"] for t in ctrf["results"]["tests"])
    assert statuses == ["failed", "skipped"]
    assert ctrf["results"]["summary"]["other"] == 0
