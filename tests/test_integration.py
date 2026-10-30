"""Integration tests that run a real hurl binary.

The normal test suite mocks subprocess. This module is skipped unless hurl is
on PATH. CI installs hurl in a dedicated job so the real CLI, stdin input,
variables file handling and report format are exercised.
"""

from __future__ import annotations

import json
import shutil
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from hurl_orchestra.orchestrator import run_hurl_orchestrator

pytestmark = pytest.mark.skipif(
    shutil.which("hurl") is None,
    reason="hurl is not installed",
)


class _ApiHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/token":
            self._json(200, {"token": "abc123"})
            return
        if self.path == "/profile":
            if self.headers.get("Authorization") != "Bearer abc123":
                self._json(401, {"error": "missing token"})
                return
            self._json(200, {"ok": True, "user": "ada"})
            return
        self._json(404, {"error": "not found"})

    def _json(self, status: int, body: dict[str, object]) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture()
def api_server() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ApiHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _write_suite(root: Path, base_url: str) -> Path:
    suite = root / "suite"
    suite.mkdir()
    (suite / ".env").write_text(f"base_url={base_url}\n")
    (suite / "auth.hurl").write_text(
        "---\n"
        "id: auth\n"
        "outputs: [token]\n"
        "---\n"
        "GET {{base_url}}/token\n"
        "HTTP 200\n"
        "[Captures]\n"
        'token: jsonpath "$.token"\n'
    )
    (suite / "profile.hurl").write_text(
        "---\n"
        "id: profile\n"
        "deps: [auth]\n"
        "---\n"
        "GET {{base_url}}/profile\n"
        "Authorization: Bearer {{auth_token}}\n"
        "HTTP 200\n"
        "[Asserts]\n"
        'jsonpath "$.ok" == true\n'
    )
    return suite


def test_real_hurl_with_relative_directory_and_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    api_server: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    suite = _write_suite(tmp_path, api_server)
    monkeypatch.chdir(tmp_path)

    result = run_hurl_orchestrator(
        "suite",
        report_ctrf="results.json",
    )

    out = capsys.readouterr().out
    assert result is True, out
    assert "SUCCESS: auth" in out
    assert "SUCCESS: profile" in out
    assert "injected: auth_token" in out
    assert f"Variables file: {suite / '.env'}" in out

    report = json.loads((suite / "results.json").read_text())
    statuses = [test["status"] for test in report["results"]["tests"]]
    assert statuses == ["passed", "passed"]
