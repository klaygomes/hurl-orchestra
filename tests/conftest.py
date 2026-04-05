"""Shared pytest fixtures."""

from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def hurl_on_path() -> pytest.FixtureRequest:
    """Pretend hurl is installed for all tests that don't test its absence."""
    with patch("shutil.which", return_value="/usr/bin/hurl"):
        yield


@pytest.fixture(autouse=True)
def no_report_zip() -> pytest.FixtureRequest:
    """Suppress zip creation for all tests that don't test it."""
    with patch("shutil.make_archive"):
        yield
