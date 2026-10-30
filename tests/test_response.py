"""Tests for the shared Hurl report response helpers."""

from __future__ import annotations

from pathlib import Path

from hurl_orchestra.response import body_text, header_value


def test_body_text_is_none_without_a_body(tmp_path: Path) -> None:
    assert body_text({}, tmp_path) is None


def test_body_text_is_none_for_an_empty_body(tmp_path: Path) -> None:
    assert body_text({"body": ""}, tmp_path) is None


def test_body_text_is_none_for_a_non_string_body(tmp_path: Path) -> None:
    assert body_text({"body": 3}, tmp_path) is None


def test_header_value_is_case_insensitive() -> None:
    response = {"headers": [{"name": "Retry-After", "value": "2"}]}
    assert header_value(response, "retry-after") == "2"


def test_header_value_is_none_when_absent() -> None:
    assert header_value({"headers": []}, "Retry-After") is None
