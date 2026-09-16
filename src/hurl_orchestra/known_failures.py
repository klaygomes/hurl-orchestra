"""Declared failure signatures that a node may tolerate."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from .response import body_text, header_value, last_response


class KnownFailureError(ValueError):
    """Raised when a ``known_failures`` declaration is malformed."""


@dataclass(frozen=True)
class KnownFailure:
    name: str
    reason: str
    status: int | None = None
    header_name: str | None = None
    header_pattern: re.Pattern[str] | None = None
    body_pattern: re.Pattern[str] | None = None
    stderr_pattern: re.Pattern[str] | None = None
    until: date | None = None
    link: str | None = None

    def is_expired(self, today: date) -> bool:
        return self.until is not None and today > self.until


@dataclass(frozen=True)
class KnownFailureMatch:
    failure: KnownFailure
    matched: tuple[str, ...]

    def describe(self) -> str:
        return f"{self.failure.reason} (matched: {', '.join(self.matched)})"


def _require_text(entry: dict[str, Any], key: str, node_id: str, index: int) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value.strip():
        raise KnownFailureError(
            f"ERROR: known_failures[{index}] for '{node_id}' needs a non-empty "
            f"string '{key}'"
        )
    return value


def _optional_text(
    entry: dict[str, Any], key: str, node_id: str, index: int
) -> str | None:
    value = entry.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise KnownFailureError(
            f"ERROR: known_failures[{index}] for '{node_id}': '{key}' must be a string"
        )
    return value


def _compile(
    pattern: str | None, key: str, node_id: str, index: int
) -> re.Pattern[str] | None:
    if pattern is None:
        return None
    try:
        return re.compile(pattern)
    except re.error as err:
        raise KnownFailureError(
            f"ERROR: known_failures[{index}] for '{node_id}': '{key}' is not a "
            f"valid regex: {err}"
        ) from err


def _parse_status(entry: dict[str, Any], node_id: str, index: int) -> int | None:
    value = entry.get("status")
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise KnownFailureError(
            f"ERROR: known_failures[{index}] for '{node_id}': 'status' must be an "
            f"integer; got {value!r}"
        )
    return int(value)


def _parse_header(
    entry: dict[str, Any], node_id: str, index: int
) -> tuple[str | None, re.Pattern[str] | None]:
    header = entry.get("header")
    if header is None:
        return None, None
    if not isinstance(header, dict):
        raise KnownFailureError(
            f"ERROR: known_failures[{index}] for '{node_id}': 'header' must be a "
            "mapping with 'name' and 'pattern'"
        )
    name = _require_text(header, "name", node_id, index)
    pattern = _compile(
        _require_text(header, "pattern", node_id, index),
        "header.pattern",
        node_id,
        index,
    )
    return name, pattern


def _parse_until(entry: dict[str, Any], node_id: str, index: int) -> date | None:
    value = entry.get("until")
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as err:
            raise KnownFailureError(
                f"ERROR: known_failures[{index}] for '{node_id}': 'until' must be a "
                f"YYYY-MM-DD date; got {value!r}"
            ) from err
    raise KnownFailureError(
        f"ERROR: known_failures[{index}] for '{node_id}': 'until' must be a "
        f"YYYY-MM-DD date; got {value!r}"
    )


def _parse_entry(entry: Any, node_id: str, index: int) -> KnownFailure:
    if not isinstance(entry, dict):
        raise KnownFailureError(
            f"ERROR: known_failures[{index}] for '{node_id}' must be a mapping; "
            f"got {type(entry).__name__}"
        )
    header_name, header_pattern = _parse_header(entry, node_id, index)
    failure = KnownFailure(
        name=_require_text(entry, "name", node_id, index),
        reason=_require_text(entry, "reason", node_id, index),
        status=_parse_status(entry, node_id, index),
        header_name=header_name,
        header_pattern=header_pattern,
        body_pattern=_compile(
            _optional_text(entry, "body", node_id, index), "body", node_id, index
        ),
        stderr_pattern=_compile(
            _optional_text(entry, "stderr", node_id, index), "stderr", node_id, index
        ),
        until=_parse_until(entry, node_id, index),
        link=_optional_text(entry, "link", node_id, index),
    )
    if (
        failure.status is None
        and failure.header_pattern is None
        and failure.body_pattern is None
        and failure.stderr_pattern is None
    ):
        raise KnownFailureError(
            f"ERROR: known_failures[{index}] for '{node_id}' must set at least one of "
            "'status', 'header', 'body', 'stderr'"
        )
    return failure


def parse_known_failures(raw: Any, node_id: str) -> list[KnownFailure]:
    """Validate the ``known_failures`` frontmatter field of *node_id*."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise KnownFailureError(
            f"ERROR: known_failures for '{node_id}' must be a list; "
            f"got {type(raw).__name__}"
        )
    failures = [_parse_entry(entry, node_id, index) for index, entry in enumerate(raw)]
    seen: set[str] = set()
    for failure in failures:
        if failure.name in seen:
            raise KnownFailureError(
                f"ERROR: known_failures for '{node_id}' declares '{failure.name}' twice"
            )
        seen.add(failure.name)
    return failures


def _matches(
    failure: KnownFailure,
    response: dict[str, Any] | None,
    report_dir: Path,
    stderr: str,
) -> tuple[str, ...] | None:
    matched: list[str] = []
    if failure.status is not None:
        if response is None or response.get("status") != failure.status:
            return None
        matched.append(f"status {failure.status}")
    if failure.header_pattern is not None and failure.header_name is not None:
        value = (
            None if response is None else header_value(response, failure.header_name)
        )
        if value is None or not failure.header_pattern.search(value):
            return None
        matched.append(f"header {failure.header_name}={value}")
    if failure.body_pattern is not None:
        text = None if response is None else body_text(response, report_dir)
        if text is None or not failure.body_pattern.search(text):
            return None
        matched.append(f"body ~ /{failure.body_pattern.pattern}/")
    if failure.stderr_pattern is not None:
        if not failure.stderr_pattern.search(stderr):
            return None
        matched.append(f"stderr ~ /{failure.stderr_pattern.pattern}/")
    return tuple(matched)


def match_known_failure(
    failures: list[KnownFailure],
    report_dir: Path,
    stderr: str,
    today: date | None = None,
) -> tuple[KnownFailureMatch | None, list[KnownFailure]]:
    """Return the first matching declaration and the ones skipped for being expired.

    The signature is checked against the last response hurl recorded in
    ``report_dir/report.json`` and against hurl's *stderr*.
    """
    if not failures:
        return None, []
    today = today or date.today()
    response = last_response(report_dir / "report.json")
    expired: list[KnownFailure] = []
    for failure in failures:
        if failure.is_expired(today):
            expired.append(failure)
            continue
        matched = _matches(failure, response, report_dir, stderr)
        if matched is not None:
            return KnownFailureMatch(failure, matched), expired
    return None, expired
