"""Node level retry with exponential backoff, for back pressure.

hurl's own ``--retry-interval`` is a fixed delay between attempts at a single
request. A service shedding load needs the opposite: a delay that grows, is
spread out across concurrent callers, and yields to an explicit ``Retry-After``.
That is a property of the whole node, so it lives here rather than in hurl.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

from .response import body_text, header_value, last_response

DEFAULT_BACKOFF_MS = 1000
DEFAULT_MAX_BACKOFF_MS = 30000
DEFAULT_MULTIPLIER = 2.0


class RetryError(ValueError):
    """Raised when a ``retry`` declaration is malformed."""


@dataclass(frozen=True)
class RetryCondition:
    """A signature a failure must match for the node to be retried."""

    status: int | None = None
    header_name: str | None = None
    header_pattern: re.Pattern[str] | None = None
    body_pattern: re.Pattern[str] | None = None
    stderr_pattern: re.Pattern[str] | None = None

    def describe(self) -> str:
        parts = []
        if self.status is not None:
            parts.append(f"status {self.status}")
        if self.header_name is not None and self.header_pattern is not None:
            parts.append(f"header {self.header_name} ~ /{self.header_pattern.pattern}/")
        if self.body_pattern is not None:
            parts.append(f"body ~ /{self.body_pattern.pattern}/")
        if self.stderr_pattern is not None:
            parts.append(f"stderr ~ /{self.stderr_pattern.pattern}/")
        return ", ".join(parts)

    def matches(
        self, response: dict[str, Any] | None, report_dir: Path, stderr: str
    ) -> bool:
        if self.status is not None:
            if response is None or response.get("status") != self.status:
                return False
        if self.header_name is not None and self.header_pattern is not None:
            value = (
                None if response is None else header_value(response, self.header_name)
            )
            if value is None or not self.header_pattern.search(value):
                return False
        if self.body_pattern is not None:
            text = None if response is None else body_text(response, report_dir)
            if text is None or not self.body_pattern.search(text):
                return False
        if self.stderr_pattern is not None:
            if not self.stderr_pattern.search(stderr):
                return False
        return True


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 1
    backoff_ms: int = DEFAULT_BACKOFF_MS
    max_backoff_ms: int = DEFAULT_MAX_BACKOFF_MS
    multiplier: float = DEFAULT_MULTIPLIER
    jitter: bool = True
    respect_retry_after: bool = True
    when: tuple[RetryCondition, ...] = ()

    @property
    def enabled(self) -> bool:
        return self.attempts > 1

    def should_retry(
        self,
        attempt: int,
        response: dict[str, Any] | None,
        report_dir: Path,
        stderr: str,
    ) -> bool:
        """Whether a node that failed on its *attempt*-th try gets another one."""
        if attempt >= self.attempts:
            return False
        if not self.when:
            return True
        return any(
            condition.matches(response, report_dir, stderr) for condition in self.when
        )

    def delay_ms(self, attempt: int, response: dict[str, Any] | None) -> int:
        """How long to wait after a failed *attempt* (1-based).

        An explicit ``Retry-After`` wins over the computed backoff, because the
        server has said what it wants; it is still capped, so a hostile or
        mistaken header cannot stall the suite.
        """
        if self.respect_retry_after:
            requested = retry_after_ms(response)
            if requested is not None:
                return min(requested, self.max_backoff_ms)

        window = min(
            float(self.max_backoff_ms),
            self.backoff_ms * self.multiplier ** (attempt - 1),
        )
        # Full jitter: without it, nodes that backed off together retry together.
        return int(random.uniform(0, window)) if self.jitter else int(window)


def retry_after_ms(response: dict[str, Any] | None) -> int | None:
    """``Retry-After`` in milliseconds, accepting both delta-seconds and HTTP-date."""
    if response is None:
        return None
    raw = header_value(response, "Retry-After")
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None
    if value.isdigit():
        return int(value) * 1000
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    delta = (when - datetime.now(UTC)).total_seconds()
    return max(0, int(delta * 1000))


def _positive_int(raw: dict[str, Any], key: str, node_id: str, default: int) -> int:
    value = raw.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RetryError(
            f"ERROR: retry.{key} for '{node_id}' must be a non-negative integer; "
            f"got {value!r}"
        )
    return int(value)


def _compile(pattern: str | None, key: str, node_id: str) -> re.Pattern[str] | None:
    if pattern is None:
        return None
    if not isinstance(pattern, str):
        raise RetryError(f"ERROR: retry.when.{key} for '{node_id}' must be a string")
    try:
        return re.compile(pattern)
    except re.error as err:
        raise RetryError(
            f"ERROR: retry.when.{key} for '{node_id}' is not a valid regex: {err}"
        ) from err


def _parse_condition(entry: Any, node_id: str, index: int) -> RetryCondition:
    if not isinstance(entry, dict):
        raise RetryError(
            f"ERROR: retry.when[{index}] for '{node_id}' must be a mapping; "
            f"got {type(entry).__name__}"
        )

    status = entry.get("status")
    if status is not None and (isinstance(status, bool) or not isinstance(status, int)):
        raise RetryError(
            f"ERROR: retry.when[{index}].status for '{node_id}' must be an integer; "
            f"got {status!r}"
        )

    header = entry.get("header")
    header_name: str | None = None
    header_pattern: re.Pattern[str] | None = None
    if header is not None:
        if not isinstance(header, dict) or "name" not in header:
            raise RetryError(
                f"ERROR: retry.when[{index}].header for '{node_id}' must be a mapping "
                "with 'name' and 'pattern'"
            )
        header_name = str(header["name"])
        header_pattern = _compile(
            header.get("pattern", ".*"), "header.pattern", node_id
        )

    condition = RetryCondition(
        status=status,
        header_name=header_name,
        header_pattern=header_pattern,
        body_pattern=_compile(entry.get("body"), "body", node_id),
        stderr_pattern=_compile(entry.get("stderr"), "stderr", node_id),
    )
    if (
        condition.status is None
        and condition.header_pattern is None
        and condition.body_pattern is None
        and condition.stderr_pattern is None
    ):
        raise RetryError(
            f"ERROR: retry.when[{index}] for '{node_id}' must set at least one of "
            "'status', 'header', 'body', 'stderr'"
        )
    return condition


def parse_retry(raw: Any, node_id: str) -> RetryPolicy:
    """Validate the ``retry`` frontmatter field of *node_id*."""
    if raw is None:
        return RetryPolicy()
    if not isinstance(raw, dict):
        raise RetryError(
            f"ERROR: retry for '{node_id}' must be a mapping; got {type(raw).__name__}"
        )

    attempts = _positive_int(raw, "attempts", node_id, 1)
    if attempts < 1:
        raise RetryError(f"ERROR: retry.attempts for '{node_id}' must be at least 1")

    multiplier = raw.get("multiplier", DEFAULT_MULTIPLIER)
    if isinstance(multiplier, bool) or not isinstance(multiplier, (int, float)):
        raise RetryError(
            f"ERROR: retry.multiplier for '{node_id}' must be a number; "
            f"got {multiplier!r}"
        )
    if multiplier < 1:
        raise RetryError(f"ERROR: retry.multiplier for '{node_id}' must be at least 1")

    jitter = raw.get("jitter", True)
    if isinstance(jitter, str):
        if jitter not in ("full", "none"):
            raise RetryError(
                f"ERROR: retry.jitter for '{node_id}' must be 'full', 'none' or a "
                f"boolean; got {jitter!r}"
            )
        jitter = jitter == "full"
    if not isinstance(jitter, bool):
        raise RetryError(
            f"ERROR: retry.jitter for '{node_id}' must be 'full', 'none' or a boolean"
        )

    respect = raw.get("respect_retry_after", True)
    if not isinstance(respect, bool):
        raise RetryError(
            f"ERROR: retry.respect_retry_after for '{node_id}' must be a boolean"
        )

    when_raw = raw.get("when")
    if when_raw is None:
        when: tuple[RetryCondition, ...] = ()
    elif isinstance(when_raw, list):
        when = tuple(
            _parse_condition(entry, node_id, index)
            for index, entry in enumerate(when_raw)
        )
    elif isinstance(when_raw, dict):
        when = (_parse_condition(when_raw, node_id, 0),)
    else:
        raise RetryError(
            f"ERROR: retry.when for '{node_id}' must be a mapping or a list of mappings"
        )

    unknown = set(raw) - {
        "attempts",
        "backoff_ms",
        "max_backoff_ms",
        "multiplier",
        "jitter",
        "respect_retry_after",
        "when",
    }
    if unknown:
        raise RetryError(
            f"ERROR: retry for '{node_id}' has unknown keys: "
            f"{', '.join(sorted(unknown))}"
        )

    return RetryPolicy(
        attempts=attempts,
        backoff_ms=_positive_int(raw, "backoff_ms", node_id, DEFAULT_BACKOFF_MS),
        max_backoff_ms=_positive_int(
            raw, "max_backoff_ms", node_id, DEFAULT_MAX_BACKOFF_MS
        ),
        multiplier=float(multiplier),
        jitter=jitter,
        respect_retry_after=respect,
        when=when,
    )


def response_for(report_dir: Path) -> dict[str, Any] | None:
    return last_response(report_dir / "report.json")
