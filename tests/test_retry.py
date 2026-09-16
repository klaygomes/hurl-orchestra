"""Tests for node level retry with exponential backoff."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

import pytest

from hurl_orchestra.orchestrator import run_step
from hurl_orchestra.retry import (
    RetryError,
    RetryPolicy,
    parse_retry,
    retry_after_ms,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def call(status: int, headers: dict[str, str] | None = None) -> dict:
    return {
        "request": {"method": "GET", "url": "https://example.test"},
        "response": {
            "status": status,
            "headers": [{"name": k, "value": v} for k, v in (headers or {}).items()],
        },
    }


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
                    "asserts": [{"success": success, "line": 2}],
                    "time": 12,
                }
            ],
            "success": success,
            "time": 12,
        }
    ]


def response(status: int, headers: dict[str, str] | None = None) -> dict:
    return call(status, headers)["response"]


def node(retry: dict | None = None, path: Path | None = None) -> dict:
    return {
        "path": str((path or Path.cwd()) / "n.hurl"),
        "content": "GET https://example.test\nHTTP 200\n",
        "outputs": [],
        "deps": [],
        "priority": 0,
        "hurl_args": [],
        "known_failures": [],
        "retry": parse_retry(retry, "n"),
    }


def sequence(outcomes: list[tuple[int, str, list[dict] | None]]) -> object:
    """A subprocess.run stand-in that walks *outcomes*, one per attempt."""
    remaining = list(outcomes)

    def _run(cmd: list[str], **kwargs: object) -> CompletedProcess[str]:
        report_dir = Path(cmd[cmd.index("--report-json") + 1])
        returncode, stderr, data = remaining.pop(0)
        if data is not None:
            report_dir.mkdir(parents=True, exist_ok=True)
            (report_dir / "report.json").write_text(json.dumps(data))
        return CompletedProcess(cmd, returncode, "", stderr)

    return _run


THROTTLED = (1, "error: Assert status code\n", report(call(429)))
BROKEN = (1, "error: Assert status code\n", report(call(500)))
PASSING = (0, "", report(call(200), success=True))


def step(node_data: dict, report_dir: Path, slept: list[float]) -> object:
    return run_step(
        "n",
        node_data,
        {},
        {"n": set()},
        [],
        [],
        report_dir,
        sleep=slept.append,
    )


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def test_absent_retry_means_a_single_attempt() -> None:
    policy = parse_retry(None, "n")
    assert policy.attempts == 1
    assert policy.enabled is False


def test_parse_accepts_a_full_policy() -> None:
    policy = parse_retry(
        {
            "attempts": 5,
            "backoff_ms": 250,
            "max_backoff_ms": 4000,
            "multiplier": 3,
            "jitter": "none",
            "respect_retry_after": False,
            "when": [{"status": 429}, {"header": {"name": "Retry-After"}}],
        },
        "n",
    )
    assert policy.attempts == 5
    assert policy.backoff_ms == 250
    assert policy.max_backoff_ms == 4000
    assert policy.multiplier == 3
    assert policy.jitter is False
    assert policy.respect_retry_after is False
    assert len(policy.when) == 2


def test_parse_accepts_a_single_when_mapping() -> None:
    policy = parse_retry({"attempts": 2, "when": {"status": 503}}, "n")
    assert len(policy.when) == 1
    assert policy.when[0].status == 503


@pytest.mark.parametrize(
    "raw,message",
    [
        ({"attempts": 0}, "at least 1"),
        ({"attempts": "two"}, "non-negative integer"),
        ({"multiplier": 0.5}, "at least 1"),
        ({"multiplier": "fast"}, "must be a number"),
        ({"jitter": "sometimes"}, "'full', 'none' or a boolean"),
        ({"respect_retry_after": "yes"}, "must be a boolean"),
        ({"backoff_ms": -1}, "non-negative integer"),
        ({"nope": 1}, "unknown keys"),
        ({"when": [{}]}, "at least one of"),
        ({"when": [{"body": "["}]}, "not a valid regex"),
        ({"when": "429"}, "mapping or a list"),
        ({"when": [{"status": "429"}]}, "must be an integer"),
    ],
)
def test_parse_rejects_bad_policies(raw: dict, message: str) -> None:
    with pytest.raises(RetryError, match=message):
        parse_retry(raw, "n")


def test_parse_rejects_a_non_mapping() -> None:
    with pytest.raises(RetryError, match="must be a mapping"):
        parse_retry([1], "n")


# ---------------------------------------------------------------------------
# Backoff
# ---------------------------------------------------------------------------


def test_delay_grows_exponentially() -> None:
    policy = parse_retry(
        {"attempts": 5, "backoff_ms": 100, "multiplier": 2, "jitter": "none"}, "n"
    )
    assert [policy.delay_ms(n, None) for n in (1, 2, 3, 4)] == [100, 200, 400, 800]


def test_delay_is_capped() -> None:
    policy = parse_retry(
        {
            "attempts": 9,
            "backoff_ms": 100,
            "max_backoff_ms": 500,
            "jitter": "none",
        },
        "n",
    )
    assert [policy.delay_ms(n, None) for n in (3, 4, 8)] == [400, 500, 500]


def test_full_jitter_stays_inside_the_window() -> None:
    policy = parse_retry(
        {"attempts": 5, "backoff_ms": 100, "multiplier": 2, "jitter": "full"}, "n"
    )
    samples = [policy.delay_ms(3, None) for _ in range(200)]
    assert all(0 <= sample <= 400 for sample in samples)
    assert len(set(samples)) > 1


def test_retry_after_seconds_wins_over_backoff() -> None:
    policy = parse_retry(
        {"attempts": 3, "backoff_ms": 100, "jitter": "none"}, "n"
    )
    assert policy.delay_ms(1, response(429, {"Retry-After": "7"})) == 7000


def test_retry_after_http_date_is_understood() -> None:
    when = datetime.now(UTC) + timedelta(seconds=30)
    policy = parse_retry({"attempts": 3, "max_backoff_ms": 60000}, "n")
    delay = policy.delay_ms(1, response(503, {"Retry-After": format_datetime(when)}))
    assert 25000 <= delay <= 31000


def test_retry_after_is_capped() -> None:
    policy = parse_retry({"attempts": 3, "max_backoff_ms": 2000}, "n")
    assert policy.delay_ms(1, response(429, {"Retry-After": "3600"})) == 2000


def test_retry_after_can_be_ignored() -> None:
    policy = parse_retry(
        {
            "attempts": 3,
            "backoff_ms": 100,
            "jitter": "none",
            "respect_retry_after": False,
        },
        "n",
    )
    assert policy.delay_ms(1, response(429, {"Retry-After": "7"})) == 100


def test_unparseable_retry_after_falls_back_to_backoff() -> None:
    policy = parse_retry({"attempts": 3, "backoff_ms": 100, "jitter": "none"}, "n")
    assert policy.delay_ms(1, response(429, {"Retry-After": "soon"})) == 100


def test_retry_after_absent_is_none() -> None:
    assert retry_after_ms(response(429)) is None
    assert retry_after_ms(None) is None


# ---------------------------------------------------------------------------
# should_retry
# ---------------------------------------------------------------------------


def test_no_retry_once_attempts_are_exhausted(tmp_path: Path) -> None:
    policy = parse_retry({"attempts": 2}, "n")
    assert policy.should_retry(1, response(429), tmp_path, "") is True
    assert policy.should_retry(2, response(429), tmp_path, "") is False


def test_without_when_every_failure_is_retried(tmp_path: Path) -> None:
    policy = parse_retry({"attempts": 3}, "n")
    assert policy.should_retry(1, response(500), tmp_path, "boom") is True


def test_when_limits_retries_to_the_declared_signature(tmp_path: Path) -> None:
    policy = parse_retry({"attempts": 3, "when": [{"status": 429}]}, "n")
    assert policy.should_retry(1, response(429), tmp_path, "") is True
    assert policy.should_retry(1, response(500), tmp_path, "") is False


def test_when_can_match_stderr_with_no_response(tmp_path: Path) -> None:
    policy = parse_retry({"attempts": 3, "when": [{"stderr": "Connection refused"}]}, "n")
    assert policy.should_retry(1, None, tmp_path, "error: Connection refused") is True
    assert policy.should_retry(1, None, tmp_path, "error: Assert failed") is False


def test_a_single_policy_can_list_several_signatures(tmp_path: Path) -> None:
    policy = parse_retry(
        {"attempts": 3, "when": [{"status": 429}, {"status": 503}]}, "n"
    )
    assert policy.should_retry(1, response(429), tmp_path, "") is True
    assert policy.should_retry(1, response(503), tmp_path, "") is True
    assert policy.should_retry(1, response(504), tmp_path, "") is False


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def test_a_throttled_node_is_retried_and_succeeds(tmp_path: Path) -> None:
    slept: list[float] = []
    data = node(
        {"attempts": 3, "backoff_ms": 100, "jitter": "none", "when": [{"status": 429}]},
        tmp_path,
    )
    with patch("subprocess.run", side_effect=sequence([THROTTLED, PASSING])):
        result = step(data, tmp_path / "n", slept)

    assert result.status == "passed"
    assert slept == [0.1]
    assert "RETRY: n attempt 1/3 failed (status 429)" in result.message
    assert "2 attempts" in result.message


def test_backoff_grows_across_attempts(tmp_path: Path) -> None:
    slept: list[float] = []
    data = node(
        {"attempts": 4, "backoff_ms": 100, "multiplier": 2, "jitter": "none"}, tmp_path
    )
    with patch(
        "subprocess.run",
        side_effect=sequence([THROTTLED, THROTTLED, THROTTLED, THROTTLED]),
    ):
        result = step(data, tmp_path / "n", slept)

    assert result.status == "failed"
    assert slept == [0.1, 0.2, 0.4]


def test_a_non_matching_failure_is_not_retried(tmp_path: Path) -> None:
    slept: list[float] = []
    data = node({"attempts": 3, "when": [{"status": 429}]}, tmp_path)
    with patch("subprocess.run", side_effect=sequence([BROKEN])):
        result = step(data, tmp_path / "n", slept)

    assert result.status == "failed"
    assert slept == []
    assert "RETRY" not in result.message


def test_a_node_without_a_policy_runs_once(tmp_path: Path) -> None:
    slept: list[float] = []
    with patch("subprocess.run", side_effect=sequence([BROKEN])):
        result = step(node(None, tmp_path), tmp_path / "n", slept)

    assert result.status == "failed"
    assert slept == []


def test_a_passing_node_is_not_retried(tmp_path: Path) -> None:
    slept: list[float] = []
    data = node({"attempts": 3}, tmp_path)
    with patch("subprocess.run", side_effect=sequence([PASSING])):
        result = step(data, tmp_path / "n", slept)

    assert result.status == "passed"
    assert slept == []
    assert "attempts" not in result.message


def test_only_the_final_attempt_survives_in_the_report(tmp_path: Path) -> None:
    """hurl appends to report.json, so a recovered node must not carry its failures."""
    slept: list[float] = []
    data = node({"attempts": 3, "backoff_ms": 0, "jitter": "none"}, tmp_path)
    with patch("subprocess.run", side_effect=sequence([THROTTLED, PASSING])):
        step(data, tmp_path / "n", slept)

    written = json.loads((tmp_path / "n" / "report.json").read_text())
    assert len(written) == 1
    assert written[0]["success"] is True


def test_retry_honours_a_retry_after_header(tmp_path: Path) -> None:
    slept: list[float] = []
    throttled = (
        1,
        "error\n",
        report(call(429, {"Retry-After": "2"})),
    )
    data = node({"attempts": 2, "backoff_ms": 100, "jitter": "none"}, tmp_path)
    with patch("subprocess.run", side_effect=sequence([throttled, PASSING])):
        step(data, tmp_path / "n", slept)

    assert slept == [2.0]
