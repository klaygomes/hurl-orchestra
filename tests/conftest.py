"""Shared pytest fixtures."""

from __future__ import annotations

import shutil
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def hurl_on_path() -> pytest.FixtureRequest:
    """Use the real hurl when present, otherwise pretend it is installed."""
    with patch("shutil.which", return_value=shutil.which("hurl") or "/usr/bin/hurl"):
        yield


@pytest.fixture(autouse=True)
def no_report_zip() -> pytest.FixtureRequest:
    """Suppress zip creation for all tests that don't test it."""
    with patch("shutil.make_archive"):
        yield


@pytest.fixture(autouse=True)
def known_hurl_version() -> pytest.FixtureRequest:
    """Keep the Hurl version check deterministic and off the subprocess mock."""
    with patch(
        "hurl_orchestra.orchestrator.detect_hurl_version",
        return_value=(8, 1, 0),
    ):
        yield
