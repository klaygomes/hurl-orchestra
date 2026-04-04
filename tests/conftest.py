"""Shared pytest fixtures."""

from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def hurl_on_path() -> pytest.FixtureRequest:
    """Pretend hurl is installed for all tests that don't test its absence."""
    with patch("shutil.which", return_value="/usr/bin/hurl"):
        yield
