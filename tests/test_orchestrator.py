"""Functional tests for hurl-orchestra."""

from __future__ import annotations

import json
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

import pytest

from hurl_orchestra import run_hurl_orchestrator
from hurl_orchestra.cli import main


# ── helpers ───────────────────────────────────────────────────────────────────


def hurl_file(
    path: Path,
    *,
    id: str | None = None,
    outputs: list[str] | None = None,
    deps: list | None = None,
    priority: int | None = None,
) -> None:
    """Write a .hurl file with optional YAML frontmatter."""
    lines: list[str] = []
    if id is not None:
        lines.append(f"id: {id}")
    if outputs is not None:
        lines.append(f"outputs: {json.dumps(outputs)}")
    if deps is not None:
        lines.append("deps:")
        for dep in deps:
            if isinstance(dep, dict):
                for k, v in dep.items():
                    lines.append(f"  - {k}: {v}")
            else:
                lines.append(f"  - {dep}")
    if priority is not None:
        lines.append(f"priority: {priority}")
    content = ("---\n" + "\n".join(lines) + "\n---\n") if lines else ""
    path.write_text(content)


def ok(stderr: str = "") -> CompletedProcess[str]:
    return CompletedProcess([], 0, "", stderr)


def fail(stderr: str = "assertion failed") -> CompletedProcess[str]:
    return CompletedProcess([], 1, "", stderr)


def writing_report(data: dict) -> object:
    """Return a subprocess.run side_effect that writes *data* to the report file."""

    def _run(cmd: list[str], **kwargs: object) -> CompletedProcess[str]:
        for i, part in enumerate(cmd):
            if part == "--report-json":
                Path(cmd[i + 1]).write_text(json.dumps(data))
        return ok()

    return _run


# ── hurl availability ─────────────────────────────────────────────────────────


def test_missing_hurl_binary_prints_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")
    with patch("shutil.which", return_value=None):
        result = run_hurl_orchestrator(str(tmp_path))
    out = capsys.readouterr().out
    assert "ERROR" in out
    assert "hurl" in out
    assert result is False


def test_missing_hurl_binary_makes_no_subprocess_calls(tmp_path: Path) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")
    with patch("shutil.which", return_value=None), patch("subprocess.run") as mock:
        run_hurl_orchestrator(str(tmp_path))
    mock.assert_not_called()


# ── basic execution ───────────────────────────────────────────────────────────


def test_single_step_success(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")
    with patch("subprocess.run", return_value=ok()):
        run_hurl_orchestrator(str(tmp_path))
    assert "SUCCESS: ping" in capsys.readouterr().out


def test_single_step_failure_prints_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")
    with patch("subprocess.run", return_value=fail("connection refused")):
        run_hurl_orchestrator(str(tmp_path))
    out = capsys.readouterr().out
    assert "FAILED: ping" in out
    assert "connection refused" in out


def test_id_falls_back_to_filename_stem(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "my_api.hurl").write_text("GET https://example.com\nHTTP 200\n")
    with patch("subprocess.run", return_value=ok()):
        run_hurl_orchestrator(str(tmp_path))
    assert "SUCCESS: my_api" in capsys.readouterr().out


def test_empty_directory_makes_no_subprocess_calls(tmp_path: Path) -> None:
    with patch("subprocess.run") as mock:
        run_hurl_orchestrator(str(tmp_path))
    mock.assert_not_called()


# ── dependency ordering ───────────────────────────────────────────────────────


def test_dependency_executes_before_dependent(tmp_path: Path) -> None:
    hurl_file(tmp_path / "auth.hurl", id="auth")
    hurl_file(tmp_path / "profile.hurl", id="profile", deps=["auth"])

    order: list[str] = []

    def track(cmd: list[str], **kw: object) -> CompletedProcess[str]:
        for i, part in enumerate(cmd):
            if part == "--report-json":
                order.append(cmd[i + 1].replace("_report.json", ""))
        return ok()

    with patch("subprocess.run", side_effect=track):
        run_hurl_orchestrator(str(tmp_path))

    assert order.index("auth") < order.index("profile")


def test_failure_stops_downstream_execution(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "auth.hurl", id="auth")
    hurl_file(tmp_path / "profile.hurl", id="profile", deps=["auth"])

    with patch("subprocess.run", return_value=fail()):
        run_hurl_orchestrator(str(tmp_path))

    out = capsys.readouterr().out
    assert "FAILED: auth" in out
    assert "profile" not in out


def test_circular_dependency_prints_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "a.hurl", id="a", deps=["b"])
    hurl_file(tmp_path / "b.hurl", id="b", deps=["a"])

    with patch("subprocess.run", return_value=ok()):
        run_hurl_orchestrator(str(tmp_path))

    assert "Circular dependency" in capsys.readouterr().out


# ── variable capture and passing ──────────────────────────────────────────────


def test_captured_output_injected_into_downstream(tmp_path: Path) -> None:
    hurl_file(tmp_path / "auth.hurl", id="auth", outputs=["token"])
    hurl_file(tmp_path / "profile.hurl", id="profile", deps=["auth"])

    report = {"entries": [{"response": {"captures": [{"name": "token", "value": "abc123"}]}}]}
    cmds: list[list[str]] = []

    def fake_run(cmd: list[str], **kw: object) -> CompletedProcess[str]:
        cmds.append(list(cmd))
        for i, part in enumerate(cmd):
            if part == "--report-json":
                Path(cmd[i + 1]).write_text(json.dumps(report))
        return ok()

    with patch("subprocess.run", side_effect=fake_run):
        run_hurl_orchestrator(str(tmp_path))

    profile_cmd = next(c for c in cmds if "profile_report.json" in str(c))
    assert "--variable" in profile_cmd
    assert "auth_token=abc123" in profile_cmd


def test_capture_not_declared_in_outputs_is_not_forwarded(tmp_path: Path) -> None:
    hurl_file(tmp_path / "auth.hurl", id="auth", outputs=[])  # token not declared
    hurl_file(tmp_path / "profile.hurl", id="profile", deps=["auth"])

    report = {"entries": [{"response": {"captures": [{"name": "token", "value": "secret"}]}}]}
    cmds: list[list[str]] = []

    def fake_run(cmd: list[str], **kw: object) -> CompletedProcess[str]:
        cmds.append(list(cmd))
        for i, part in enumerate(cmd):
            if part == "--report-json":
                Path(cmd[i + 1]).write_text(json.dumps(report))
        return ok()

    with patch("subprocess.run", side_effect=fake_run):
        run_hurl_orchestrator(str(tmp_path))

    profile_cmd = next(c for c in cmds if "profile_report.json" in str(c))
    assert "auth_token=secret" not in " ".join(profile_cmd)


def test_corrupted_report_json_is_silently_ignored(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "auth.hurl", id="auth", outputs=["token"])

    def fake_run(cmd: list[str], **kw: object) -> CompletedProcess[str]:
        for i, part in enumerate(cmd):
            if part == "--report-json":
                Path(cmd[i + 1]).write_text("{not valid json")
        return ok()

    with patch("subprocess.run", side_effect=fake_run):
        run_hurl_orchestrator(str(tmp_path))

    assert "SUCCESS: auth" in capsys.readouterr().out


# ── working directory ─────────────────────────────────────────────────────────


def test_subprocess_cwd_set_to_test_directory(tmp_path: Path) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")
    captured_kwargs: list[dict] = []

    def fake_run(cmd: list[str], **kw: object) -> CompletedProcess[str]:
        captured_kwargs.append(dict(kw))
        return ok()

    with patch("subprocess.run", side_effect=fake_run):
        run_hurl_orchestrator(str(tmp_path))

    assert captured_kwargs[0]["cwd"] == str(tmp_path)


# ── environment file ──────────────────────────────────────────────────────────


def test_env_file_passed_via_variables_file(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("base_url=https://staging.example.com")
    hurl_file(tmp_path / "test.hurl", id="test")

    captured: list[str] = []

    def fake_run(cmd: list[str], **kw: object) -> CompletedProcess[str]:
        captured.extend(cmd)
        return ok()

    with patch("subprocess.run", side_effect=fake_run):
        run_hurl_orchestrator(str(tmp_path))

    assert "--variables-file" in captured
    assert str(tmp_path / ".env") in captured


def test_no_env_file_omits_variables_file_arg(tmp_path: Path) -> None:
    hurl_file(tmp_path / "test.hurl", id="test")

    captured: list[str] = []

    def fake_run(cmd: list[str], **kw: object) -> CompletedProcess[str]:
        captured.extend(cmd)
        return ok()

    with patch("subprocess.run", side_effect=fake_run):
        run_hurl_orchestrator(str(tmp_path))

    assert "--variables-file" not in captured


# ── alias / template reuse ────────────────────────────────────────────────────


def test_alias_runs_same_template_under_different_names(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "auth.hurl", id="auth", outputs=["token"])
    hurl_file(
        tmp_path / "dual.hurl",
        id="dual",
        deps=[{"auth": "admin_login"}, {"auth": "user_login"}],
    )

    with patch("subprocess.run", return_value=ok()):
        run_hurl_orchestrator(str(tmp_path))

    out = capsys.readouterr().out
    assert "SUCCESS: admin_login" in out
    assert "SUCCESS: user_login" in out


def test_shared_alias_referenced_by_two_consumers_runs_once(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Same alias used by two files must be instantiated and executed only once."""
    # Sorted glob order: a_svc → auth → b_svc.
    # a_svc registers shared_auth; b_svc finds it already present → False branch covered.
    hurl_file(tmp_path / "auth.hurl", id="auth")
    hurl_file(tmp_path / "a_svc.hurl", id="a_svc", deps=[{"auth": "shared_auth"}])
    hurl_file(tmp_path / "b_svc.hurl", id="b_svc", deps=[{"auth": "shared_auth"}])

    with patch("subprocess.run", return_value=ok()):
        run_hurl_orchestrator(str(tmp_path))

    assert capsys.readouterr().out.count("SUCCESS: shared_auth") == 1


def test_alias_name_matching_template_id_does_not_duplicate_node(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """When an alias has the same name as a template, that node runs exactly once.

    Sorted glob order: a_consumer → auth.
    a_consumer's dep {auth: auth} registers the "auth" node before the
    outer loop reaches the auth template → ``if t_id not in nodes`` False branch.
    """
    hurl_file(tmp_path / "a_consumer.hurl", id="a_consumer", deps=[{"auth": "auth"}])
    hurl_file(tmp_path / "auth.hurl", id="auth")

    with patch("subprocess.run", return_value=ok()):
        run_hurl_orchestrator(str(tmp_path))

    assert capsys.readouterr().out.count("SUCCESS: auth") == 1


# ── priority ─────────────────────────────────────────────────────────────────


def test_positive_priority_runs_before_default_in_same_wave(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Both are independent (no deps). "low" is alphabetically first but has no
    # priority; "high" has priority=1 so it must run first.
    hurl_file(tmp_path / "aaa.hurl", id="low")
    hurl_file(tmp_path / "zzz.hurl", id="high", priority=1)

    with patch("subprocess.run", return_value=ok()):
        run_hurl_orchestrator(str(tmp_path))

    out = capsys.readouterr().out
    assert out.index("SUCCESS: high") < out.index("SUCCESS: low")


def test_negative_priority_runs_after_default_in_same_wave(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # "last" is alphabetically first but priority=-1 so it must run last.
    hurl_file(tmp_path / "aaa.hurl", id="last", priority=-1)
    hurl_file(tmp_path / "zzz.hurl", id="first")

    with patch("subprocess.run", return_value=ok()):
        run_hurl_orchestrator(str(tmp_path))

    out = capsys.readouterr().out
    assert out.index("SUCCESS: first") < out.index("SUCCESS: last")


def test_priority_does_not_override_deps(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # "consumer" has priority=10 but still must wait for "producer" (its dep).
    hurl_file(tmp_path / "producer.hurl", id="producer")
    hurl_file(tmp_path / "consumer.hurl", id="consumer", deps=["producer"], priority=10)

    with patch("subprocess.run", return_value=ok()):
        run_hurl_orchestrator(str(tmp_path))

    out = capsys.readouterr().out
    assert out.index("SUCCESS: producer") < out.index("SUCCESS: consumer")


# ── CLI ───────────────────────────────────────────────────────────────────────


def test_cli_defaults_to_current_directory() -> None:
    with (
        patch("hurl_orchestra.cli.run_hurl_orchestrator", return_value=True) as mock,
        patch("sys.argv", ["hurl-orchestra"]),
    ):
        main()
    mock.assert_called_once_with(".", extra_hurl_args=[])


def test_cli_passes_custom_directory_argument() -> None:
    with (
        patch("hurl_orchestra.cli.run_hurl_orchestrator", return_value=True) as mock,
        patch("sys.argv", ["hurl-orchestra", "/tmp/tests"]),
    ):
        main()
    mock.assert_called_once_with("/tmp/tests", extra_hurl_args=[])


def test_cli_passes_specific_hurl_files() -> None:
    with (
        patch("hurl_orchestra.cli.run_hurl_orchestrator", return_value=True) as mock,
        patch("sys.argv", ["hurl-orchestra", "a.hurl", "b.hurl"]),
    ):
        main()
    mock.assert_called_once_with(files=["a.hurl", "b.hurl"], extra_hurl_args=[])


def test_cli_forwards_extra_hurl_args_with_directory() -> None:
    with (
        patch("hurl_orchestra.cli.run_hurl_orchestrator", return_value=True) as mock,
        patch("sys.argv", ["hurl-orchestra", "./tests", "--verbose"]),
    ):
        main()
    mock.assert_called_once_with("./tests", extra_hurl_args=["--verbose"])


def test_cli_forwards_extra_hurl_args_with_files() -> None:
    with (
        patch("hurl_orchestra.cli.run_hurl_orchestrator", return_value=True) as mock,
        patch("sys.argv", ["hurl-orchestra", "test.hurl", "--variable", "x=y"]),
    ):
        main()
    mock.assert_called_once_with(files=["test.hurl"], extra_hurl_args=["--variable", "x=y"])


def test_cli_exits_with_code_1_on_failure() -> None:
    with (
        patch("hurl_orchestra.cli.run_hurl_orchestrator", return_value=False),
        patch("sys.argv", ["hurl-orchestra"]),
        pytest.raises(SystemExit) as exc,
    ):
        main()
    assert exc.value.code == 1


def test_cli_exits_with_code_0_on_success(tmp_path: Path) -> None:
    with (
        patch("hurl_orchestra.cli.run_hurl_orchestrator", return_value=True),
        patch("sys.argv", ["hurl-orchestra"]),
    ):
        main()  # must not raise


# ── specific files mode ───────────────────────────────────────────────────────


def test_specific_files_only_runs_given_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")
    hurl_file(tmp_path / "pong.hurl", id="pong")
    with patch("subprocess.run", return_value=ok()):
        run_hurl_orchestrator(files=[str(tmp_path / "ping.hurl")])
    out = capsys.readouterr().out
    assert "SUCCESS: ping" in out
    assert "pong" not in out


def test_extra_hurl_args_forwarded_to_subprocess(tmp_path: Path) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")
    cmds: list[list[str]] = []

    def fake_run(cmd: list[str], **kw: object) -> CompletedProcess[str]:
        cmds.append(list(cmd))
        return ok()

    with patch("subprocess.run", side_effect=fake_run):
        run_hurl_orchestrator(str(tmp_path), extra_hurl_args=["--verbose", "--variable", "x=y"])

    assert "--verbose" in cmds[0]
    assert "--variable" in cmds[0]
    assert "x=y" in cmds[0]


def test_specific_files_env_file_resolved_from_parent(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("base_url=https://example.com")
    hurl_file(tmp_path / "ping.hurl", id="ping")

    captured: list[str] = []

    def fake_run(cmd: list[str], **kw: object) -> CompletedProcess[str]:
        captured.extend(cmd)
        return ok()

    with patch("subprocess.run", side_effect=fake_run):
        run_hurl_orchestrator(files=[str(tmp_path / "ping.hurl")])

    assert "--variables-file" in captured
    assert str(tmp_path / ".env") in captured
