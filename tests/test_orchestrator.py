"""Functional tests for hurl-orchestra."""

from __future__ import annotations

import json
import subprocess
from graphlib import CycleError
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

import pytest

from hurl_orchestra import run_hurl_orchestrator
from hurl_orchestra.cli import _package_version, main


def hurl_file(
    path: Path,
    *,
    id: str | None = None,
    outputs: list[str] | None = None,
    deps: list | None = None,
    priority: int | None = None,
    args: list | None = None,
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
    if args is not None:
        lines.append("args:")
        for arg in args:
            if isinstance(arg, dict):
                for k, v in arg.items():
                    lines.append(f"  - {k}: {v}")
            else:
                lines.append(f"  - {arg}")
    content = ("---\n" + "\n".join(lines) + "\n---\n") if lines else ""
    path.write_text(content)


def ok(stderr: str = "") -> CompletedProcess[str]:
    return CompletedProcess([], 0, "", stderr)


def fail(stderr: str = "assertion failed") -> CompletedProcess[str]:
    return CompletedProcess([], 4, "", stderr)


def writing_report(data: dict) -> object:
    """Return a side_effect that writes *data* to the report directory."""

    def _run(cmd: list[str], **kwargs: object) -> CompletedProcess[str]:
        for i, part in enumerate(cmd):
            if part == "--report-json":
                (Path(cmd[i + 1]) / "report.json").write_text(json.dumps(data))
        return ok()

    return _run


def injected_variables(cmd: list[str]) -> str:
    """Return the content of every injected properties file in *cmd*."""
    return "".join(
        Path(cmd[i + 1]).read_text()
        for i, part in enumerate(cmd)
        if part in ("--variables-file", "--secrets-file")
    )


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


def test_single_step_success(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
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


def test_empty_directory_fails_without_subprocess_calls(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with patch("subprocess.run") as mock:
        result = run_hurl_orchestrator(str(tmp_path))
    mock.assert_not_called()
    assert result is False
    assert "no .hurl files found" in capsys.readouterr().out


def test_missing_directory_error_names_the_path_and_the_current_directory(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    with patch("subprocess.run") as mock:
        result = run_hurl_orchestrator("e2e/desk")

    out = capsys.readouterr().out
    assert result is False
    assert "ERROR: path does not exist: e2e/desk" in out
    assert f"Current directory: {Path.cwd()}" in out
    assert "HINT:" in out
    mock.assert_not_called()


def test_path_that_is_not_a_directory_prints_a_clear_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "README"
    target.write_text("not a suite\n")

    with patch("subprocess.run") as mock:
        result = run_hurl_orchestrator(str(target))

    out = capsys.readouterr().out
    assert result is False
    assert f"ERROR: path is not a directory: {target}" in out
    assert "HINT:" in out
    mock.assert_not_called()


def test_dependency_executes_before_dependent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "auth.hurl", id="auth")
    hurl_file(tmp_path / "profile.hurl", id="profile", deps=["auth"])

    with patch("subprocess.run", return_value=ok()):
        run_hurl_orchestrator(str(tmp_path))

    out = capsys.readouterr().out
    assert out.index("SUCCESS: auth") < out.index("SUCCESS: profile")


def test_failure_stops_downstream_execution(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "auth.hurl", id="auth")
    hurl_file(tmp_path / "profile.hurl", id="profile", deps=["auth"])

    with patch("subprocess.run", return_value=fail()):
        run_hurl_orchestrator(str(tmp_path))

    out = capsys.readouterr().out
    assert "FAILED: auth" in out
    assert "SKIPPED: profile (failed dependency: auth)" in out
    assert "SUCCESS: profile" not in out


def test_circular_dependency_prints_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "a.hurl", id="a", deps=["b"])
    hurl_file(tmp_path / "b.hurl", id="b", deps=["a"])

    with patch("subprocess.run", return_value=ok()):
        run_hurl_orchestrator(str(tmp_path))

    assert "Circular dependency" in capsys.readouterr().out


def test_missing_string_dep_prints_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "a.hurl", id="a", deps=["nonexistent"])

    with patch("subprocess.run", return_value=ok()):
        result = run_hurl_orchestrator(str(tmp_path))

    out = capsys.readouterr().out
    assert result is False
    assert "ERROR" in out
    assert "nonexistent" in out


def test_missing_alias_template_prints_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "a.hurl", id="a", deps=[{"nonexistent_template": "my_alias"}])

    with patch("subprocess.run", return_value=ok()):
        result = run_hurl_orchestrator(str(tmp_path))

    out = capsys.readouterr().out
    assert result is False
    assert "ERROR" in out
    assert "nonexistent_template" in out


def test_null_outputs_are_treated_as_empty(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "auth.hurl").write_text(
        "---\nid: auth\noutputs: null\n---\nGET https://example.com\n"
    )

    with patch("subprocess.run", return_value=ok()):
        result = run_hurl_orchestrator(str(tmp_path))

    out = capsys.readouterr().out
    assert result is True
    assert "SUCCESS: auth" in out


def test_null_deps_are_treated_as_empty(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "auth.hurl").write_text(
        "---\nid: auth\ndeps: null\n---\nGET https://example.com\n"
    )

    with patch("subprocess.run", return_value=ok()):
        result = run_hurl_orchestrator(str(tmp_path))

    out = capsys.readouterr().out
    assert result is True
    assert "SUCCESS: auth" in out


def test_invalid_dep_dict_length_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "a.hurl").write_text(
        "---\nid: a\ndeps:\n  - {x: y, z: w}\n---\nGET https://example.com\n"
    )

    with patch("subprocess.run", return_value=ok()):
        result = run_hurl_orchestrator(str(tmp_path))

    out = capsys.readouterr().out
    assert result is False
    assert "single-key dicts" in out


def test_invalid_dep_type_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "a.hurl").write_text(
        "---\nid: a\ndeps:\n  - 123\n---\nGET https://example.com\n"
    )

    with patch("subprocess.run", return_value=ok()):
        result = run_hurl_orchestrator(str(tmp_path))

    out = capsys.readouterr().out
    assert result is False
    assert "must contain strings or dicts" in out


def test_invalid_priority_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "a.hurl").write_text(
        "---\nid: a\npriority: high\n---\nGET https://example.com\n"
    )

    with patch("subprocess.run", return_value=ok()):
        result = run_hurl_orchestrator(str(tmp_path))

    out = capsys.readouterr().out
    assert result is False
    assert "must be an integer" in out


def test_args_string_flag_is_auto_prefixed(tmp_path: Path) -> None:
    hurl_file(tmp_path / "a.hurl", id="a", args=["verbose"])
    cmds: list[list[str]] = []

    def fake_run(cmd: list[str], **kw: object) -> CompletedProcess[str]:
        cmds.append(list(cmd))
        return ok()

    with patch("subprocess.run", side_effect=fake_run):
        run_hurl_orchestrator(str(tmp_path))

    assert "--verbose" in cmds[0]


def test_args_dict_expands_to_flag_and_value(tmp_path: Path) -> None:
    hurl_file(tmp_path / "a.hurl", id="a", args=[{"connect-timeout": 30}])
    cmds: list[list[str]] = []

    def fake_run(cmd: list[str], **kw: object) -> CompletedProcess[str]:
        cmds.append(list(cmd))
        return ok()

    with patch("subprocess.run", side_effect=fake_run):
        run_hurl_orchestrator(str(tmp_path))

    assert "--connect-timeout" in cmds[0]
    idx = cmds[0].index("--connect-timeout")
    assert cmds[0][idx + 1] == "30"


def test_args_single_char_uses_single_dash(tmp_path: Path) -> None:
    hurl_file(tmp_path / "a.hurl", id="a", args=["v"])
    cmds: list[list[str]] = []

    def fake_run(cmd: list[str], **kw: object) -> CompletedProcess[str]:
        cmds.append(list(cmd))
        return ok()

    with patch("subprocess.run", side_effect=fake_run):
        run_hurl_orchestrator(str(tmp_path))

    assert "-v" in cmds[0]
    assert "--v" not in cmds[0]


def test_args_single_char_dict_key_uses_single_dash(tmp_path: Path) -> None:
    hurl_file(tmp_path / "a.hurl", id="a", args=[{"k": "mykey"}])
    cmds: list[list[str]] = []

    def fake_run(cmd: list[str], **kw: object) -> CompletedProcess[str]:
        cmds.append(list(cmd))
        return ok()

    with patch("subprocess.run", side_effect=fake_run):
        run_hurl_orchestrator(str(tmp_path))

    assert "-k" in cmds[0]
    idx = cmds[0].index("-k")
    assert cmds[0][idx + 1] == "mykey"


def test_args_per_file_comes_after_extra_hurl_args(tmp_path: Path) -> None:
    hurl_file(tmp_path / "a.hurl", id="a", args=[{"connect-timeout": 30}])
    cmds: list[list[str]] = []

    def fake_run(cmd: list[str], **kw: object) -> CompletedProcess[str]:
        cmds.append(list(cmd))
        return ok()

    with patch("subprocess.run", side_effect=fake_run):
        run_hurl_orchestrator(str(tmp_path), extra_hurl_args=["--connect-timeout", "5"])

    cmd = cmds[0]
    indices = [i for i, x in enumerate(cmd) if x == "--connect-timeout"]
    assert len(indices) == 2
    assert cmd[indices[0] + 1] == "5"
    assert cmd[indices[1] + 1] == "30"


def test_invalid_args_type_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "a.hurl").write_text(
        "---\nid: a\nargs: not-a-list\n---\nGET https://example.com\nHTTP 200\n"
    )

    with patch("subprocess.run", return_value=ok()):
        result = run_hurl_orchestrator(str(tmp_path))

    out = capsys.readouterr().out
    assert result is False
    assert "args for 'a' must be a list" in out


def test_invalid_args_item_type_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "a.hurl").write_text(
        "---\nid: a\nargs:\n  - 123\n---\nGET https://example.com\nHTTP 200\n"
    )

    with patch("subprocess.run", return_value=ok()):
        result = run_hurl_orchestrator(str(tmp_path))

    out = capsys.readouterr().out
    assert result is False
    assert "args for 'a' must contain strings or dicts" in out


def test_no_args_field_does_not_break(tmp_path: Path) -> None:
    hurl_file(tmp_path / "a.hurl", id="a")
    cmds: list[list[str]] = []

    def fake_run(cmd: list[str], **kw: object) -> CompletedProcess[str]:
        cmds.append(list(cmd))
        return ok()

    with patch("subprocess.run", side_effect=fake_run):
        result = run_hurl_orchestrator(str(tmp_path))

    assert result is True
    assert (
        cmds[0][:3] == ["hurl", "--test", "--report-json"] or "--report-json" in cmds[0]
    )


def test_invalid_outputs_type_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "a.hurl").write_text(
        "---\nid: a\noutputs: 123\n---\nGET https://example.com\n"
    )

    with patch("subprocess.run", return_value=ok()):
        result = run_hurl_orchestrator(str(tmp_path))

    out = capsys.readouterr().out
    assert result is False
    assert "outputs for 'a' must be a list" in out


def test_invalid_deps_not_list_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "a.hurl").write_text(
        "---\nid: a\ndeps: 123\n---\nGET https://example.com\n"
    )

    with patch("subprocess.run", return_value=ok()):
        result = run_hurl_orchestrator(str(tmp_path))

    out = capsys.readouterr().out
    assert result is False
    assert "deps for 'a' must be a list" in out


def test_empty_node_id_fails_validation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "ping.hurl").write_text("---\nid: ''\n---\nGET https://example.com\n")

    with patch("subprocess.run", return_value=ok()):
        result = run_hurl_orchestrator(str(tmp_path))

    out = capsys.readouterr().out
    assert result is False
    assert "must be a non-empty string" in out


def test_direct_capture_report_structure_is_supported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "auth.hurl", id="auth", outputs=["token"])
    hurl_file(tmp_path / "profile.hurl", id="profile", deps=["auth"])

    def fake_run(cmd: list[str], **kw: object) -> CompletedProcess[str]:
        for i, part in enumerate(cmd):
            if part == "--report-json":
                (Path(cmd[i + 1]) / "report.json").write_text(
                    json.dumps({"captures": [{"name": "token", "value": "abc"}]})
                )
        return ok()

    with patch("subprocess.run", side_effect=fake_run):
        run_hurl_orchestrator(str(tmp_path))

    out = capsys.readouterr().out
    assert "captured: token" in out
    assert "SUCCESS: profile" in out


def test_duplicate_capture_warnings_are_printed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "auth.hurl", id="auth", outputs=["token"])

    def fake_run(cmd: list[str], **kw: object) -> CompletedProcess[str]:
        for i, part in enumerate(cmd):
            if part == "--report-json":
                (Path(cmd[i + 1]) / "report.json").write_text(
                    json.dumps(
                        {
                            "entries": [
                                {"captures": [{"name": "token", "value": "first"}]},
                                {"captures": [{"name": "token", "value": "second"}]},
                            ]
                        }
                    )
                )
        return ok()

    with patch("subprocess.run", side_effect=fake_run):
        run_hurl_orchestrator(str(tmp_path))

    out = capsys.readouterr().out
    assert "WARNING: auth: output 'token' overwritten by entry 0" in out
    assert "SUCCESS: auth" in out


def test_timeout_during_execution_is_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")
    seen_timeouts: list[object] = []

    def fake_run(cmd: list[str], **kw: object) -> CompletedProcess[str]:
        seen_timeouts.append(kw.get("timeout"))
        raise subprocess.TimeoutExpired(cmd="hurl", timeout=12)

    with patch("subprocess.run", side_effect=fake_run):
        result = run_hurl_orchestrator(str(tmp_path), timeout_seconds=12)

    out = capsys.readouterr().out
    assert result is False
    assert seen_timeouts == [17]
    assert "Hurl timed out after 12 seconds" in out


def test_internal_execution_exception_is_handled(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")

    def fake_run(cmd: list[str], **kw: object) -> CompletedProcess[str]:
        raise RuntimeError("boom")

    with patch("subprocess.run", side_effect=fake_run):
        result = run_hurl_orchestrator(str(tmp_path))

    out = capsys.readouterr().out
    assert result is False
    assert "FAILED: ping" in out
    assert "boom" in out


def test_alias_template_string_deps_are_instantiated(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "producer.hurl", id="producer")
    hurl_file(tmp_path / "base.hurl", id="base", deps=["producer"])
    hurl_file(tmp_path / "auth.hurl", id="auth", deps=[{"base": "shared_base"}])

    with patch("subprocess.run", return_value=ok()):
        run_hurl_orchestrator(str(tmp_path))

    out = capsys.readouterr().out
    assert "SUCCESS: producer" in out
    assert "SUCCESS: shared_base" in out
    assert "SUCCESS: auth" in out


def test_execute_cycle_error_is_caught(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")

    with (
        patch("shutil.which", return_value="/usr/bin/hurl"),
        patch(
            "hurl_orchestra.orchestrator._execute",
            side_effect=CycleError("cycle detected"),
        ),
    ):
        result = run_hurl_orchestrator(str(tmp_path))

    out = capsys.readouterr().out
    assert result is False
    assert "Circular dependency" in out


def test_captured_output_injected_into_downstream(tmp_path: Path) -> None:
    hurl_file(tmp_path / "auth.hurl", id="auth", outputs=["token"])
    hurl_file(tmp_path / "profile.hurl", id="profile", deps=["auth"])

    report = [{"entries": [{"captures": [{"name": "token", "value": "abc123"}]}]}]
    cmds: list[list[str]] = []
    variables: list[str] = []

    def fake_run(cmd: list[str], **kw: object) -> CompletedProcess[str]:
        cmds.append(list(cmd))
        variables.append(injected_variables(cmd))
        for i, part in enumerate(cmd):
            if part == "--report-json":
                (Path(cmd[i + 1]) / "report.json").write_text(json.dumps(report))
        return ok()

    with patch("subprocess.run", side_effect=fake_run):
        run_hurl_orchestrator(str(tmp_path))

    assert "auth_token=abc123\n" in variables[1]
    assert "abc123" not in " ".join(cmds[1])


def test_capture_not_declared_in_outputs_is_not_forwarded(tmp_path: Path) -> None:
    hurl_file(tmp_path / "auth.hurl", id="auth", outputs=[])  # token not declared
    hurl_file(tmp_path / "profile.hurl", id="profile", deps=["auth"])

    report = [{"entries": [{"captures": [{"name": "token", "value": "secret"}]}]}]
    cmds: list[list[str]] = []
    variables: list[str] = []

    def fake_run(cmd: list[str], **kw: object) -> CompletedProcess[str]:
        cmds.append(list(cmd))
        variables.append(injected_variables(cmd))
        for i, part in enumerate(cmd):
            if part == "--report-json":
                (Path(cmd[i + 1]) / "report.json").write_text(json.dumps(report))
        return ok()

    with patch("subprocess.run", side_effect=fake_run):
        run_hurl_orchestrator(str(tmp_path))

    assert "--variables-file" not in cmds[1]
    assert "--secrets-file" not in cmds[1]
    assert "secret" not in variables[1]


def test_corrupted_report_json_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "auth.hurl", id="auth", outputs=["token"])

    def fake_run(cmd: list[str], **kw: object) -> CompletedProcess[str]:
        for i, part in enumerate(cmd):
            if part == "--report-json":
                (Path(cmd[i + 1]) / "report.json").write_text("{not valid json")
        return ok()

    with patch("subprocess.run", side_effect=fake_run):
        result = run_hurl_orchestrator(str(tmp_path))

    out = capsys.readouterr().out
    assert result is False
    assert "FAILED: auth" in out
    assert "ERROR" in out
    assert "token" in out


def test_missing_report_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "auth.hurl", id="auth", outputs=["token"])

    with patch("subprocess.run", return_value=ok()):
        result = run_hurl_orchestrator(str(tmp_path))

    out = capsys.readouterr().out
    assert result is False
    assert "FAILED: auth" in out
    assert "ERROR" in out
    assert "token" in out


def test_independent_failures_do_not_stop_other_ready_nodes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "a.hurl", id="a")
    hurl_file(tmp_path / "b.hurl", id="b")

    def fake_run(cmd: list[str], **kw: object) -> CompletedProcess[str]:
        for i, part in enumerate(cmd):
            if part == "--report-json":
                report_dir = Path(cmd[i + 1])
                if report_dir.name == "a":
                    return fail("broken")
                return ok()
        return ok()

    with patch("subprocess.run", side_effect=fake_run):
        result = run_hurl_orchestrator(str(tmp_path))

    out = capsys.readouterr().out
    assert result is False
    assert "FAILED: a" in out
    assert "SUCCESS: b" in out


def test_success_shows_captured_variables(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "auth.hurl", id="auth", outputs=["token"])
    report = [{"entries": [{"captures": [{"name": "token", "value": "abc"}]}]}]

    with patch("subprocess.run", side_effect=writing_report(report)):
        run_hurl_orchestrator(str(tmp_path))

    assert "captured: token" in capsys.readouterr().out


def test_success_shows_injected_variables(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "auth.hurl", id="auth", outputs=["token"])
    hurl_file(tmp_path / "profile.hurl", id="profile", deps=["auth"])
    report = [{"entries": [{"captures": [{"name": "token", "value": "abc"}]}]}]

    call_count = 0

    def fake_run(cmd: list[str], **kw: object) -> CompletedProcess[str]:
        nonlocal call_count
        call_count += 1
        for i, part in enumerate(cmd):
            if part == "--report-json" and call_count == 1:
                (Path(cmd[i + 1]) / "report.json").write_text(json.dumps(report))
        return ok()

    with patch("subprocess.run", side_effect=fake_run):
        run_hurl_orchestrator(str(tmp_path))

    assert "injected: auth_token" in capsys.readouterr().out


def test_subprocess_cwd_set_to_test_directory(tmp_path: Path) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")
    captured_kwargs: list[dict] = []

    def fake_run(cmd: list[str], **kw: object) -> CompletedProcess[str]:
        captured_kwargs.append(dict(kw))
        return ok()

    with patch("subprocess.run", side_effect=fake_run):
        run_hurl_orchestrator(str(tmp_path))

    assert captured_kwargs[0]["cwd"] == str(tmp_path)


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


def test_alias_runs_same_template_under_different_names(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "auth.hurl", id="auth")
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


def test_build_graph_rejects_invalid_node_identifiers(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "a.hurl", id="bad id")

    with patch("subprocess.run", return_value=ok()):
        result = run_hurl_orchestrator(str(tmp_path))

    out = capsys.readouterr().out
    assert result is False
    assert "ERROR" in out
    assert "bad id" in out


def test_alias_nested_template_dependencies_are_instantiated(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "base.hurl", id="base")
    hurl_file(
        tmp_path / "auth.hurl",
        id="auth",
        deps=[{"base": "shared_base"}],
    )
    hurl_file(
        tmp_path / "consumer.hurl",
        id="consumer",
        deps=[{"auth": "auth_alias"}],
    )

    with patch("subprocess.run", return_value=ok()):
        run_hurl_orchestrator(str(tmp_path))

    out = capsys.readouterr().out
    assert "SUCCESS: shared_base" in out
    assert "SUCCESS: auth_alias" in out
    assert "SUCCESS: consumer" in out


def test_shared_alias_referenced_by_two_consumers_runs_once(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Same alias used by two files must be instantiated and executed only once."""
    # Sorted glob order: a_svc → auth → b_svc.
    # a_svc registers shared_auth; b_svc finds it already present.
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


def test_cli_version_prints_the_package_version(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        patch("hurl_orchestra.cli._package_version", return_value="9.9.9"),
        patch("sys.argv", ["hurl-orchestra", "--version"]),
        pytest.raises(SystemExit) as exc,
    ):
        main()

    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == "hurl-orchestra 9.9.9"


def test_package_version_falls_back_when_metadata_is_missing() -> None:
    with patch(
        "hurl_orchestra.cli.version",
        side_effect=PackageNotFoundError("hurl-orchestra"),
    ):
        assert _package_version() == "unknown"


def test_cli_defaults_to_current_directory() -> None:
    with (
        patch("hurl_orchestra.cli.run_hurl_orchestrator", return_value=True) as mock,
        patch("sys.argv", ["hurl-orchestra"]),
    ):
        main()
    mock.assert_called_once_with(
        ".",
        extra_hurl_args=[],
        report_zip="report.zip",
        report_ctrf=None,
        resolve_deps=True,
        dry_run=False,
        strict=False,
        json_plan=False,
        env_file=None,
        secrets_file=None,
        inject_as_variables=False,
        timeout_seconds=300,
        jobs=None,
    )


def test_cli_passes_custom_directory_argument() -> None:
    with (
        patch("hurl_orchestra.cli.run_hurl_orchestrator", return_value=True) as mock,
        patch("sys.argv", ["hurl-orchestra", "/tmp/tests"]),
    ):
        main()
    mock.assert_called_once_with(
        "/tmp/tests",
        extra_hurl_args=[],
        report_zip="report.zip",
        report_ctrf=None,
        resolve_deps=True,
        dry_run=False,
        strict=False,
        json_plan=False,
        env_file=None,
        secrets_file=None,
        inject_as_variables=False,
        timeout_seconds=300,
        jobs=None,
    )


def test_cli_passes_specific_hurl_files() -> None:
    with (
        patch("hurl_orchestra.cli.run_hurl_orchestrator", return_value=True) as mock,
        patch("sys.argv", ["hurl-orchestra", "a.hurl", "b.hurl"]),
    ):
        main()
    mock.assert_called_once_with(
        files=["a.hurl", "b.hurl"],
        extra_hurl_args=[],
        report_zip="report.zip",
        report_ctrf=None,
        resolve_deps=True,
        dry_run=False,
        strict=False,
        json_plan=False,
        env_file=None,
        secrets_file=None,
        inject_as_variables=False,
        timeout_seconds=300,
        jobs=None,
    )


def test_cli_forwards_extra_hurl_args_with_directory() -> None:
    with (
        patch("hurl_orchestra.cli.run_hurl_orchestrator", return_value=True) as mock,
        patch("sys.argv", ["hurl-orchestra", "./tests", "--verbose"]),
    ):
        main()
    mock.assert_called_once_with(
        "./tests",
        extra_hurl_args=["--verbose"],
        report_zip="report.zip",
        report_ctrf=None,
        resolve_deps=True,
        dry_run=False,
        strict=False,
        json_plan=False,
        env_file=None,
        secrets_file=None,
        inject_as_variables=False,
        timeout_seconds=300,
        jobs=None,
    )


def test_cli_forwards_extra_hurl_args_with_files() -> None:
    with (
        patch("hurl_orchestra.cli.run_hurl_orchestrator", return_value=True) as mock,
        patch("sys.argv", ["hurl-orchestra", "test.hurl", "--", "--variable", "x=y"]),
    ):
        main()
    mock.assert_called_once_with(
        files=["test.hurl"],
        extra_hurl_args=["--variable", "x=y"],
        report_zip="report.zip",
        report_ctrf=None,
        resolve_deps=True,
        dry_run=False,
        strict=False,
        json_plan=False,
        env_file=None,
        secrets_file=None,
        inject_as_variables=False,
        timeout_seconds=300,
        jobs=None,
    )


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
        run_hurl_orchestrator(
            str(tmp_path), extra_hurl_args=["--verbose", "--variable", "x=y"]
        )

    assert "--verbose" in cmds[0]
    assert "--variable" in cmds[0]
    assert "x=y" in cmds[0]


def test_specific_files_env_file_resolved_from_test_dir(tmp_path: Path) -> None:
    """When files are passed, .env is looked up in test_dir, not the file parent."""
    sub = tmp_path / "sub"
    sub.mkdir()
    hurl_file(sub / "ping.hurl", id="ping")
    # .env in CWD (tmp_path), NOT in file parent (sub)
    (tmp_path / ".env").write_text("base_url=https://example.com")

    captured: list[str] = []

    def fake_run(cmd: list[str], **kw: object) -> CompletedProcess[str]:
        captured.extend(cmd)
        return ok()

    with patch("subprocess.run", side_effect=fake_run):
        run_hurl_orchestrator(str(tmp_path), files=[str(sub / "ping.hurl")])

    assert "--variables-file" in captured
    assert str(tmp_path / ".env") in captured


def test_specific_files_env_file_uses_cwd_when_no_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When files passed without explicit dir, .env is resolved from CWD."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("base_url=https://example.com")
    hurl_file(tmp_path / "ping.hurl", id="ping")

    captured: list[str] = []

    def fake_run(cmd: list[str], **kw: object) -> CompletedProcess[str]:
        captured.extend(cmd)
        return ok()

    with patch("subprocess.run", side_effect=fake_run):
        run_hurl_orchestrator(files=[str(tmp_path / "ping.hurl")])

    assert "--variables-file" in captured


def test_report_zip_created_with_default_name(tmp_path: Path) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")
    with (
        patch("subprocess.run", return_value=ok()),
        patch("shutil.make_archive") as mock_archive,
    ):
        run_hurl_orchestrator(str(tmp_path))
    mock_archive.assert_called_once()
    base, fmt = mock_archive.call_args.args[:2]
    assert base == str(tmp_path / "report")
    assert fmt == "zip"


def test_report_zip_custom_name(tmp_path: Path) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")
    with (
        patch("subprocess.run", return_value=ok()),
        patch("shutil.make_archive") as mock_archive,
    ):
        run_hurl_orchestrator(str(tmp_path), report_zip="my_run.zip")
    base, fmt = mock_archive.call_args.args[:2]
    assert base == str(tmp_path / "my_run")
    assert fmt == "zip"


def test_report_zip_created_on_failure(tmp_path: Path) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")
    with (
        patch("subprocess.run", return_value=fail()),
        patch("shutil.make_archive") as mock_archive,
    ):
        run_hurl_orchestrator(str(tmp_path))
    mock_archive.assert_called_once()


def test_cli_report_zip_custom_name() -> None:
    with (
        patch("hurl_orchestra.cli.run_hurl_orchestrator", return_value=True) as mock,
        patch("sys.argv", ["hurl-orchestra", "--report-zip", "run.zip"]),
    ):
        main()
    assert mock.call_args.kwargs["report_zip"] == "run.zip"


def test_cli_double_dash_splits_hurl_args() -> None:
    """Args after -- are forwarded verbatim to hurl."""
    with (
        patch("hurl_orchestra.cli.run_hurl_orchestrator", return_value=True) as mock,
        patch(
            "sys.argv",
            [
                "hurl-orchestra",
                "./tests",
                "--",
                "--variable",
                "k=v",
                "--connect-timeout",
                "10",
            ],
        ),
    ):
        main()
    mock.assert_called_once_with(
        "./tests",
        extra_hurl_args=["--variable", "k=v", "--connect-timeout", "10"],
        report_zip="report.zip",
        report_ctrf=None,
        resolve_deps=True,
        dry_run=False,
        strict=False,
        json_plan=False,
        env_file=None,
        secrets_file=None,
        inject_as_variables=False,
        timeout_seconds=300,
        jobs=None,
    )


def test_cli_mixed_known_flags_and_double_dash() -> None:
    """Known flags before --, hurl value-flags after --."""
    with (
        patch("hurl_orchestra.cli.run_hurl_orchestrator", return_value=True) as mock,
        patch(
            "sys.argv",
            [
                "hurl-orchestra",
                "--report-zip",
                "r.zip",
                "./tests",
                "--",
                "--variable",
                "x=1",
            ],
        ),
    ):
        main()
    mock.assert_called_once_with(
        "./tests",
        extra_hurl_args=["--variable", "x=1"],
        report_zip="r.zip",
        report_ctrf=None,
        resolve_deps=True,
        dry_run=False,
        strict=False,
        json_plan=False,
        env_file=None,
        secrets_file=None,
        inject_as_variables=False,
        timeout_seconds=300,
        jobs=None,
    )


def test_cli_boolean_passthrough_without_double_dash() -> None:
    """Simple boolean flags like --verbose still work without --."""
    with (
        patch("hurl_orchestra.cli.run_hurl_orchestrator", return_value=True) as mock,
        patch("sys.argv", ["hurl-orchestra", "./tests", "--verbose", "--very-verbose"]),
    ):
        main()
    mock.assert_called_once_with(
        "./tests",
        extra_hurl_args=["--verbose", "--very-verbose"],
        report_zip="report.zip",
        report_ctrf=None,
        resolve_deps=True,
        dry_run=False,
        strict=False,
        json_plan=False,
        env_file=None,
        secrets_file=None,
        inject_as_variables=False,
        timeout_seconds=300,
        jobs=None,
    )


def test_cli_order_independent_known_flags() -> None:
    """--report-zip works regardless of position before --."""
    with (
        patch("hurl_orchestra.cli.run_hurl_orchestrator", return_value=True) as mock,
        patch("sys.argv", ["hurl-orchestra", "--report-zip", "r.zip", "./tests"]),
    ):
        main()
    mock.assert_called_once_with(
        "./tests",
        extra_hurl_args=[],
        report_zip="r.zip",
        report_ctrf=None,
        resolve_deps=True,
        dry_run=False,
        strict=False,
        json_plan=False,
        env_file=None,
        secrets_file=None,
        inject_as_variables=False,
        timeout_seconds=300,
        jobs=None,
    )


def test_report_zip_in_cwd_when_no_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When no directory is passed, report goes to CWD."""
    monkeypatch.chdir(tmp_path)
    hurl_file(tmp_path / "ping.hurl", id="ping")
    with (
        patch("subprocess.run", return_value=ok()),
        patch("shutil.make_archive") as mock_archive,
    ):
        run_hurl_orchestrator()
    base, fmt = mock_archive.call_args.args[:2]
    assert base == str(Path(".") / "report")
    assert fmt == "zip"


def test_cli_diagram_flag_calls_write_diagram(tmp_path: Path) -> None:
    with (
        patch("hurl_orchestra.cli.write_diagram", return_value=True) as mock,
        patch("sys.argv", ["hurl-orchestra", "--diagram", str(tmp_path)]),
    ):
        main()
    mock.assert_called_once()


def test_cli_diagram_custom_output(tmp_path: Path) -> None:
    with (
        patch("hurl_orchestra.cli.write_diagram", return_value=True) as mock,
        patch(
            "sys.argv",
            [
                "hurl-orchestra",
                "--diagram",
                "--diagram-output",
                "out.md",
                str(tmp_path),
            ],
        ),
    ):
        main()
    assert mock.call_args.kwargs["output"] == "out.md"


def test_cli_diagram_does_not_call_run_orchestrator(tmp_path: Path) -> None:
    with (
        patch("hurl_orchestra.cli.write_diagram", return_value=True),
        patch("hurl_orchestra.cli.run_hurl_orchestrator") as mock_run,
        patch("sys.argv", ["hurl-orchestra", "--diagram", str(tmp_path)]),
    ):
        main()
    mock_run.assert_not_called()


def test_single_file_resolves_deps_from_siblings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "auth.hurl", id="auth")
    hurl_file(tmp_path / "profile.hurl", id="profile", deps=["auth"])
    hurl_file(tmp_path / "unrelated.hurl", id="unrelated")

    with patch("subprocess.run", return_value=ok()):
        result = run_hurl_orchestrator(files=[str(tmp_path / "profile.hurl")])

    out = capsys.readouterr().out
    assert result is True
    assert "Resolved dependencies: auth" in out
    assert out.index("SUCCESS: auth") < out.index("SUCCESS: profile")
    assert "unrelated" not in out


def test_single_file_resolves_transitive_deps(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "a.hurl", id="a")
    hurl_file(tmp_path / "b.hurl", id="b", deps=["a"])
    hurl_file(tmp_path / "c.hurl", id="c", deps=["b"])
    hurl_file(tmp_path / "d.hurl", id="d", deps=["c"])

    with patch("subprocess.run", return_value=ok()):
        run_hurl_orchestrator(files=[str(tmp_path / "c.hurl")])

    out = capsys.readouterr().out
    assert "Resolved dependencies: a, b" in out
    assert out.index("SUCCESS: a") < out.index("SUCCESS: b") < out.index("SUCCESS: c")
    assert "SUCCESS: d" not in out


def test_single_file_resolves_alias_deps_from_siblings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "auth.hurl", id="auth")
    hurl_file(tmp_path / "admin.hurl", id="admin", deps=[{"auth": "admin_login"}])

    with patch("subprocess.run", return_value=ok()):
        result = run_hurl_orchestrator(files=[str(tmp_path / "admin.hurl")])

    out = capsys.readouterr().out
    assert result is True
    assert "Resolved dependencies: admin_login" in out
    assert "SUCCESS: admin_login" in out
    assert "SUCCESS: auth" not in out


def test_requested_files_across_directories_share_one_graph(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    shared = tmp_path / "shared"
    api = tmp_path / "api"
    shared.mkdir()
    api.mkdir()
    hurl_file(shared / "auth.hurl", id="auth")
    hurl_file(api / "profile.hurl", id="profile", deps=["auth"])

    with patch("subprocess.run", return_value=ok()):
        result = run_hurl_orchestrator(
            files=[str(api / "profile.hurl"), str(shared / "auth.hurl")]
        )

    out = capsys.readouterr().out
    assert result is True
    assert "Resolved dependencies" not in out
    assert out.index("SUCCESS: auth") < out.index("SUCCESS: profile")


def test_no_deps_requires_explicit_dependency_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "auth.hurl", id="auth")
    hurl_file(tmp_path / "profile.hurl", id="profile", deps=["auth"])

    with patch("subprocess.run", return_value=ok()) as mock:
        result = run_hurl_orchestrator(
            files=[str(tmp_path / "profile.hurl")], resolve_deps=False
        )

    out = capsys.readouterr().out
    assert result is False
    assert "no .hurl file or alias defines id: auth" in out
    assert "HINT: --no-deps runs only the files that you list" in out
    assert "remove --no-deps" in out
    mock.assert_not_called()


def test_missing_requested_file_prints_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with patch("subprocess.run", return_value=ok()) as mock:
        result = run_hurl_orchestrator(files=[str(tmp_path / "nope.hurl")])

    out = capsys.readouterr().out
    assert result is False
    assert "ERROR: .hurl file not found" in out
    assert "nope.hurl" in out
    mock.assert_not_called()


def test_dry_run_prints_plan_without_running(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "auth.hurl", id="auth")
    hurl_file(tmp_path / "config.hurl", id="config")
    hurl_file(tmp_path / "profile.hurl", id="profile", deps=["auth", "config"])

    with (
        patch("shutil.which", return_value=None),
        patch("subprocess.run") as mock_run,
        patch("shutil.make_archive") as mock_archive,
    ):
        result = run_hurl_orchestrator(str(tmp_path), dry_run=True)

    out = capsys.readouterr().out
    assert result is True
    assert "Plan: 3 node(s)" in out
    assert "wave 1: auth, config" in out
    assert "wave 2: profile" in out
    mock_run.assert_not_called()
    mock_archive.assert_not_called()


def test_dry_run_shows_resolved_dependencies_for_single_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "auth.hurl", id="auth")
    hurl_file(tmp_path / "profile.hurl", id="profile", deps=["auth"])

    with patch("subprocess.run") as mock_run:
        run_hurl_orchestrator(files=[str(tmp_path / "profile.hurl")], dry_run=True)

    out = capsys.readouterr().out
    assert "Resolved dependencies: auth" in out
    assert "wave 1: auth" in out
    assert "wave 2: profile" in out
    mock_run.assert_not_called()


def test_dry_run_reports_graph_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "profile.hurl", id="profile", deps=["auth"])

    result = run_hurl_orchestrator(str(tmp_path), dry_run=True)

    assert result is False
    assert "no .hurl file or alias defines id: auth" in capsys.readouterr().out


def test_skipped_lists_every_failed_dependency(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "a.hurl", id="a")
    hurl_file(tmp_path / "b.hurl", id="b")
    hurl_file(tmp_path / "c.hurl", id="c", deps=["a", "b"])

    with patch("subprocess.run", return_value=fail()):
        run_hurl_orchestrator(str(tmp_path))

    assert "SKIPPED: c (failed dependency: a, b)" in capsys.readouterr().out


def test_skip_cascades_through_transitive_dependents(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "a.hurl", id="a")
    hurl_file(tmp_path / "b.hurl", id="b", deps=["a"])
    hurl_file(tmp_path / "c.hurl", id="c", deps=["b"])

    with patch("subprocess.run", return_value=fail()):
        run_hurl_orchestrator(str(tmp_path))

    out = capsys.readouterr().out
    assert "SKIPPED: b (failed dependency: a)" in out
    assert "SKIPPED: c (failed dependency: b)" in out


def test_injected_variables_file_is_removed_after_step(tmp_path: Path) -> None:
    hurl_file(tmp_path / "auth.hurl", id="auth", outputs=["token"])
    hurl_file(tmp_path / "profile.hurl", id="profile", deps=["auth"])

    report = [{"entries": [{"captures": [{"name": "token", "value": "abc123"}]}]}]
    variables_files: list[Path] = []

    def fake_run(cmd: list[str], **kw: object) -> CompletedProcess[str]:
        for i, part in enumerate(cmd):
            if part == "--secrets-file":
                variables_files.append(Path(cmd[i + 1]))
            if part == "--report-json":
                (Path(cmd[i + 1]) / "report.json").write_text(json.dumps(report))
        return ok()

    with patch("subprocess.run", side_effect=fake_run):
        run_hurl_orchestrator(str(tmp_path))

    assert len(variables_files) == 1
    assert not variables_files[0].exists()


def test_cli_no_deps_flag() -> None:
    with (
        patch("hurl_orchestra.cli.run_hurl_orchestrator", return_value=True) as mock,
        patch("sys.argv", ["hurl-orchestra", "--no-deps", "a.hurl"]),
    ):
        main()
    assert mock.call_args.kwargs["resolve_deps"] is False


def test_cli_dry_run_flag() -> None:
    with (
        patch("hurl_orchestra.cli.run_hurl_orchestrator", return_value=True) as mock,
        patch("sys.argv", ["hurl-orchestra", "--dry-run", "./tests"]),
    ):
        main()
    assert mock.call_args.kwargs["dry_run"] is True


def test_cli_diagram_of_files_resolves_deps(tmp_path: Path) -> None:
    target = str(tmp_path / "profile.hurl")
    with (
        patch("hurl_orchestra.cli.write_diagram", return_value=True) as mock,
        patch("sys.argv", ["hurl-orchestra", "--diagram", target]),
    ):
        main()
    assert mock.call_args.kwargs["resolve_deps"] is True


def test_cli_diagram_of_files_respects_no_deps(tmp_path: Path) -> None:
    target = str(tmp_path / "profile.hurl")
    with (
        patch("hurl_orchestra.cli.write_diagram", return_value=True) as mock,
        patch("sys.argv", ["hurl-orchestra", "--diagram", "--no-deps", target]),
    ):
        main()
    assert mock.call_args.kwargs["resolve_deps"] is False


def test_cli_diagram_of_directory_does_not_resolve(tmp_path: Path) -> None:
    with (
        patch("hurl_orchestra.cli.write_diagram", return_value=True) as mock,
        patch("sys.argv", ["hurl-orchestra", "--diagram", str(tmp_path)]),
    ):
        main()
    assert mock.call_args.kwargs["resolve_deps"] is False


def test_dry_run_json_prints_the_plan_as_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "auth.hurl", id="auth", outputs=["token"])
    hurl_file(tmp_path / "config.hurl", id="config", priority=2)
    hurl_file(tmp_path / "profile.hurl", id="profile", deps=["auth", "config"])

    with (
        patch("shutil.which", return_value=None),
        patch("subprocess.run") as mock_run,
    ):
        result = run_hurl_orchestrator(str(tmp_path), dry_run=True, json_plan=True)

    plan = json.loads(capsys.readouterr().out)
    assert result is True
    assert plan["ok"] is True
    assert plan["waves"] == [["config", "auth"], ["profile"]]
    profile = next(node for node in plan["nodes"] if node["id"] == "profile")
    assert profile["deps"] == ["auth", "config"]
    assert profile["variables"] == ["auth_token"]
    assert profile["file"] == str(tmp_path / "profile.hurl")
    mock_run.assert_not_called()


def test_dry_run_json_keeps_stdout_pure_when_deps_resolve(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "auth.hurl", id="auth")
    hurl_file(tmp_path / "profile.hurl", id="profile", deps=["auth"])

    result = run_hurl_orchestrator(
        files=[str(tmp_path / "profile.hurl")], dry_run=True, json_plan=True
    )

    plan = json.loads(capsys.readouterr().out)
    assert result is True
    assert plan["resolved"] == ["auth"]
    assert plan["waves"] == [["auth"], ["profile"]]


def test_dry_run_json_reports_graph_errors_as_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "profile.hurl", id="profile", deps=["missing"])

    result = run_hurl_orchestrator(str(tmp_path), dry_run=True, json_plan=True)

    document = json.loads(capsys.readouterr().out)
    assert result is False
    assert document["ok"] is False
    assert "missing" in document["error"]


def test_dry_run_json_lists_known_failures_and_retry(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "order.hurl").write_text(
        "---\n"
        "id: order\n"
        "retry:\n  attempts: 3\n"
        "known_failures:\n"
        "  - name: pool\n    reason: shared db\n    status: 500\n"
        "---\n"
    )

    run_hurl_orchestrator(str(tmp_path), dry_run=True, json_plan=True)

    node = json.loads(capsys.readouterr().out)["nodes"][0]
    assert node["known_failures"] == ["pool"]
    assert node["retry_attempts"] == 3


def test_cli_json_without_dry_run_is_an_error(tmp_path: Path) -> None:
    with (
        patch("sys.argv", ["hurl-orchestra", "--json", str(tmp_path)]),
        pytest.raises(SystemExit) as exit_info,
    ):
        main()
    assert exit_info.value.code == 2


def test_cli_passes_json_plan_to_the_orchestrator(tmp_path: Path) -> None:
    with (
        patch("hurl_orchestra.cli.run_hurl_orchestrator", return_value=True) as mock,
        patch("sys.argv", ["hurl-orchestra", "--dry-run", "--json", str(tmp_path)]),
    ):
        main()
    assert mock.call_args.kwargs["json_plan"] is True


def test_run_prints_the_variables_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / ".env").write_text("base_url=https://example.com")
    hurl_file(tmp_path / "ping.hurl", id="ping")

    with patch("subprocess.run", return_value=ok()):
        run_hurl_orchestrator(str(tmp_path))

    assert f"Variables file: {tmp_path / '.env'}" in capsys.readouterr().out


def test_files_mode_notes_an_unread_env_next_to_the_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    sub = tmp_path / "tests"
    sub.mkdir()
    (sub / ".env").write_text("base_url=https://example.com")
    hurl_file(sub / "ping.hurl", id="ping")
    captured: list[str] = []

    def fake_run(cmd: list[str], **kw: object) -> CompletedProcess[str]:
        captured.extend(cmd)
        return ok()

    with patch("subprocess.run", side_effect=fake_run):
        run_hurl_orchestrator(files=[str(sub / "ping.hurl")])

    out = capsys.readouterr().out
    assert "--variables-file" not in captured
    assert f"NOTE: hurl-orchestra does not read {sub / '.env'}" in out
    assert f"--env-file {sub / '.env'}" in out


def test_explicit_env_file_wins_and_silences_the_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("base_url=https://cwd.example.com")
    sub = tmp_path / "tests"
    sub.mkdir()
    (sub / ".env").write_text("base_url=https://tests.example.com")
    hurl_file(sub / "ping.hurl", id="ping")
    captured: list[str] = []

    def fake_run(cmd: list[str], **kw: object) -> CompletedProcess[str]:
        captured.extend(cmd)
        return ok()

    with patch("subprocess.run", side_effect=fake_run):
        run_hurl_orchestrator(
            files=[str(sub / "ping.hurl")], env_file=str(sub / ".env")
        )

    out = capsys.readouterr().out
    assert str(sub / ".env") in captured
    assert str(tmp_path / ".env") not in captured
    assert "NOTE:" not in out


def test_missing_explicit_env_file_stops_the_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")

    with patch("subprocess.run") as mock_run:
        result = run_hurl_orchestrator(
            str(tmp_path), env_file=str(tmp_path / "nope.env")
        )

    assert result is False
    assert "ERROR: env file not found" in capsys.readouterr().out
    mock_run.assert_not_called()


def test_dry_run_json_names_the_env_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / ".env").write_text("base_url=https://example.com")
    hurl_file(tmp_path / "ping.hurl", id="ping")

    run_hurl_orchestrator(str(tmp_path), dry_run=True, json_plan=True)

    plan = json.loads(capsys.readouterr().out)
    assert plan["env_file"] == str(tmp_path / ".env")


def test_cli_passes_env_file(tmp_path: Path) -> None:
    with (
        patch("hurl_orchestra.cli.run_hurl_orchestrator", return_value=True) as mock,
        patch("sys.argv", ["hurl-orchestra", "--env-file", "ci.env", str(tmp_path)]),
    ):
        main()
    assert mock.call_args.kwargs["env_file"] == "ci.env"


@pytest.mark.parametrize("node_id", ["../escape", "a/b", "a\\b", ".", ".."])
def test_unsafe_node_ids_fail(
    tmp_path: Path,
    node_id: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    hurl_file(tmp_path / "evil.hurl", id=node_id)

    result = run_hurl_orchestrator(str(tmp_path), dry_run=True)

    assert result is False
    assert "must contain only letters, digits" in capsys.readouterr().out


def test_duplicate_node_ids_fail(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "a.hurl", id="same")
    hurl_file(tmp_path / "b.hurl", id="same")

    result = run_hurl_orchestrator(str(tmp_path), dry_run=True)

    out = capsys.readouterr().out
    assert result is False
    assert "duplicate node id 'same'" in out
    assert "a.hurl" in out and "b.hurl" in out


def test_alias_instance_name_collision_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "a.hurl", id="a")
    hurl_file(tmp_path / "b.hurl", id="b")
    hurl_file(tmp_path / "c1.hurl", id="c1", deps=[{"a": "shared"}])
    hurl_file(tmp_path / "c2.hurl", id="c2", deps=[{"b": "shared"}])

    result = run_hurl_orchestrator(str(tmp_path), dry_run=True)

    out = capsys.readouterr().out
    assert result is False
    assert "collides with a node from template" in out


def test_unknown_frontmatter_keys_fail(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "a.hurl").write_text(
        "---\nid: a\ndep: [b]\n---\nGET https://example.com\n"
    )

    result = run_hurl_orchestrator(str(tmp_path), dry_run=True)

    out = capsys.readouterr().out
    assert result is False
    assert "unknown frontmatter keys: dep" in out


def test_malformed_frontmatter_is_a_clean_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "a.hurl").write_text("---\nid: [\n---\nGET https://example.com\n")

    result = run_hurl_orchestrator(str(tmp_path), dry_run=True)

    out = capsys.readouterr().out
    assert result is False
    assert "cannot parse" in out


def test_boolean_priority_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "a.hurl").write_text(
        "---\nid: a\npriority: true\n---\nGET https://example.com\n"
    )

    result = run_hurl_orchestrator(str(tmp_path), dry_run=True)

    assert result is False
    assert "priority for 'a' must be an integer" in capsys.readouterr().out


def test_relative_env_path_is_resolved_for_the_hurl_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    suite = tmp_path / "tests"
    suite.mkdir()
    (suite / ".env").write_text("base_url=https://example.com")
    hurl_file(suite / "ping.hurl", id="ping")
    captured: list[str] = []

    def fake_run(cmd: list[str], **kw: object) -> CompletedProcess[str]:
        captured.extend(cmd)
        return ok()

    with patch("subprocess.run", side_effect=fake_run):
        result = run_hurl_orchestrator("tests")

    assert result is True
    assert str((suite / ".env").absolute()) in captured


def test_captured_value_with_newline_fails_before_injection(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "auth.hurl", id="auth", outputs=["token"])
    hurl_file(tmp_path / "profile.hurl", id="profile", deps=["auth"])
    report = [{"entries": [{"captures": [{"name": "token", "value": "a\nb"}]}]}]
    calls = 0

    def fake_run(cmd: list[str], **kw: object) -> CompletedProcess[str]:
        nonlocal calls
        calls += 1
        for index, part in enumerate(cmd):
            if part == "--report-json" and calls == 1:
                (Path(cmd[index + 1]) / "report.json").write_text(json.dumps(report))
        return ok()

    with patch("subprocess.run", side_effect=fake_run):
        result = run_hurl_orchestrator(str(tmp_path))

    out = capsys.readouterr().out
    assert result is False
    assert "line break" in out
    assert calls == 1


def test_cli_passes_timeout_and_jobs(tmp_path: Path) -> None:
    with (
        patch("hurl_orchestra.cli.run_hurl_orchestrator", return_value=True) as mock,
        patch(
            "sys.argv",
            ["hurl-orchestra", "--timeout", "7", "--jobs", "2", str(tmp_path)],
        ),
    ):
        main()
    assert mock.call_args.kwargs["timeout_seconds"] == 7
    assert mock.call_args.kwargs["jobs"] == 2


def test_report_archive_failure_fails_the_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")

    with (
        patch("subprocess.run", return_value=ok()),
        patch("shutil.make_archive", side_effect=OSError("disk full")),
    ):
        result = run_hurl_orchestrator(str(tmp_path))

    assert result is False
    assert "Failed to write report archive" in capsys.readouterr().out


def test_invalid_timeout_and_jobs_are_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")

    assert run_hurl_orchestrator(str(tmp_path), timeout_seconds=0) is False
    assert "timeout must be at least 1" in capsys.readouterr().out

    assert run_hurl_orchestrator(str(tmp_path), jobs=0) is False
    assert "jobs must be at least 1" in capsys.readouterr().out


def test_hurl_older_than_the_minimum_is_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")
    with (
        patch(
            "hurl_orchestra.orchestrator.detect_hurl_version",
            return_value=(7, 0, 0),
        ),
        patch("subprocess.run") as mock,
    ):
        result = run_hurl_orchestrator(str(tmp_path))

    out = capsys.readouterr().out
    assert result is False
    assert "hurl 7.0.0 is too old" in out
    assert "7.1.0" in out
    mock.assert_not_called()


def test_unreadable_hurl_version_warns_and_runs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")
    with (
        patch("hurl_orchestra.orchestrator.detect_hurl_version", return_value=None),
        patch("subprocess.run", return_value=ok()),
    ):
        result = run_hurl_orchestrator(str(tmp_path))

    out = capsys.readouterr().out
    assert result is True
    assert "cannot read the hurl version" in out


def test_captured_output_is_injected_as_a_secret(tmp_path: Path) -> None:
    hurl_file(tmp_path / "auth.hurl", id="auth", outputs=["token"])
    hurl_file(tmp_path / "profile.hurl", id="profile", deps=["auth"])
    report = [{"entries": [{"captures": [{"name": "token", "value": "abc123"}]}]}]
    cmds: list[list[str]] = []
    secrets: list[str] = []

    def fake_run(cmd: list[str], **kw: object) -> CompletedProcess[str]:
        cmds.append(list(cmd))
        if "--secrets-file" in cmd:
            secrets.append(Path(cmd[cmd.index("--secrets-file") + 1]).read_text())
        for i, part in enumerate(cmd):
            if part == "--report-json":
                (Path(cmd[i + 1]) / "report.json").write_text(json.dumps(report))
        return ok()

    with patch("subprocess.run", side_effect=fake_run):
        run_hurl_orchestrator(str(tmp_path))

    assert "--secrets-file" in cmds[1]
    assert "--variables-file" not in cmds[1]
    assert secrets[-1] == "auth_token=abc123\n"
    assert "abc123" not in " ".join(cmds[1])


def test_inject_as_variables_keeps_the_old_transport(tmp_path: Path) -> None:
    hurl_file(tmp_path / "auth.hurl", id="auth", outputs=["token"])
    hurl_file(tmp_path / "profile.hurl", id="profile", deps=["auth"])
    report = [{"entries": [{"captures": [{"name": "token", "value": "abc"}]}]}]
    cmds: list[list[str]] = []

    def fake_run(cmd: list[str], **kw: object) -> CompletedProcess[str]:
        cmds.append(list(cmd))
        for i, part in enumerate(cmd):
            if part == "--report-json":
                (Path(cmd[i + 1]) / "report.json").write_text(json.dumps(report))
        return ok()

    with patch("subprocess.run", side_effect=fake_run):
        run_hurl_orchestrator(str(tmp_path), inject_as_variables=True)

    assert "--variables-file" in cmds[1]
    assert "--secrets-file" not in cmds[1]


def test_global_secrets_file_is_passed_to_every_call(tmp_path: Path) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")
    secrets = tmp_path / "secrets.env"
    secrets.write_text("api_key=abc\n")
    cmds: list[list[str]] = []

    def fake_run(cmd: list[str], **kw: object) -> CompletedProcess[str]:
        cmds.append(list(cmd))
        return ok()

    with patch("subprocess.run", side_effect=fake_run):
        result = run_hurl_orchestrator(str(tmp_path), secrets_file=str(secrets))

    assert result is True
    assert "--secrets-file" in cmds[0]
    assert str(secrets) in cmds[0]


def test_missing_global_secrets_file_stops_the_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")

    with patch("subprocess.run") as mock:
        result = run_hurl_orchestrator(
            str(tmp_path), secrets_file=str(tmp_path / "missing.env")
        )

    assert result is False
    assert "secrets file not found" in capsys.readouterr().out
    mock.assert_not_called()


def test_global_and_injected_secrets_are_merged(tmp_path: Path) -> None:
    hurl_file(tmp_path / "auth.hurl", id="auth", outputs=["token"])
    hurl_file(tmp_path / "profile.hurl", id="profile", deps=["auth"])
    secrets = tmp_path / "secrets.env"
    secrets.write_text("other=keep\nauth_token=old\n")
    report = [{"entries": [{"captures": [{"name": "token", "value": "new"}]}]}]
    merged: list[str] = []

    def fake_run(cmd: list[str], **kw: object) -> CompletedProcess[str]:
        if "--secrets-file" in cmd:
            merged.append(Path(cmd[cmd.index("--secrets-file") + 1]).read_text())
        for i, part in enumerate(cmd):
            if part == "--report-json":
                (Path(cmd[i + 1]) / "report.json").write_text(json.dumps(report))
        return ok()

    with patch("subprocess.run", side_effect=fake_run):
        run_hurl_orchestrator(str(tmp_path), secrets_file=str(secrets))

    content = merged[-1]
    assert content.count("auth_token=") == 1
    assert "auth_token=new\n" in content
    assert "other=keep\n" in content


def test_reserved_hurl_flag_in_extra_args_is_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")
    with patch("subprocess.run") as mock:
        result = run_hurl_orchestrator(str(tmp_path), extra_hurl_args=["--test"])

    out = capsys.readouterr().out
    assert result is False
    assert "--test is managed by hurl-orchestra" in out
    mock.assert_not_called()


def test_reserved_hurl_flag_in_node_args_is_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping", args=["report-json", "/tmp/out"])
    result = run_hurl_orchestrator(str(tmp_path), dry_run=True)

    out = capsys.readouterr().out
    assert result is False
    assert "--report-json is managed by hurl-orchestra" in out


def test_user_max_time_replaces_the_injected_one(tmp_path: Path) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")
    cmds: list[list[str]] = []

    def fake_run(cmd: list[str], **kw: object) -> CompletedProcess[str]:
        cmds.append(list(cmd))
        return ok()

    with patch("subprocess.run", side_effect=fake_run):
        run_hurl_orchestrator(
            str(tmp_path),
            extra_hurl_args=["--max-time", "5"],
            timeout_seconds=30,
        )

    cmd = cmds[0]
    assert cmd.count("--max-time") == 1
    assert cmd[cmd.index("--max-time") + 1] == "5"


def test_node_max_time_replaces_the_injected_one(tmp_path: Path) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping", args=[{"max-time": 4}])
    cmds: list[list[str]] = []

    def fake_run(cmd: list[str], **kw: object) -> CompletedProcess[str]:
        cmds.append(list(cmd))
        return ok()

    with patch("subprocess.run", side_effect=fake_run):
        run_hurl_orchestrator(str(tmp_path), timeout_seconds=30)

    cmd = cmds[0]
    assert cmd.count("--max-time") == 1
    assert cmd[cmd.index("--max-time") + 1] == "4"


def test_timeout_is_sent_to_hurl_with_a_process_grace(tmp_path: Path) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")
    seen: list[dict[str, object]] = []

    def fake_run(cmd: list[str], **kw: object) -> CompletedProcess[str]:
        seen.append({"cmd": cmd, "timeout": kw.get("timeout")})
        return ok()

    with patch("subprocess.run", side_effect=fake_run):
        run_hurl_orchestrator(str(tmp_path), timeout_seconds=9)

    cmd = seen[0]["cmd"]
    assert isinstance(cmd, list)
    assert cmd[cmd.index("--max-time") + 1] == "9"
    assert seen[0]["timeout"] == 14


def test_parse_error_is_not_retried(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "broken.hurl").write_text(
        "---\nid: broken\nretry:\n  attempts: 3\n---\nGET\n"
    )
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **kw: object) -> CompletedProcess[str]:
        calls.append(list(cmd))
        return CompletedProcess(cmd, 2, "", "error: unexpected token")

    with patch("subprocess.run", side_effect=fake_run):
        result = run_hurl_orchestrator(str(tmp_path))

    out = capsys.readouterr().out
    assert result is False
    assert len(calls) == 1
    assert "could not parse the file" in out
    assert "unexpected token" in out


def test_dry_run_json_names_the_secrets_file_and_hurl_config(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")
    secrets = tmp_path / "secrets.env"
    secrets.write_text("api_key=abc\n")
    config_home = tmp_path / "xdg"
    (config_home / "hurl").mkdir(parents=True)
    (config_home / "hurl" / "config").write_text("--verbose\n")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))

    run_hurl_orchestrator(
        str(tmp_path),
        secrets_file=str(secrets),
        dry_run=True,
        json_plan=True,
    )

    plan = json.loads(capsys.readouterr().out)
    assert plan["secrets_file"] == str(secrets)
    assert plan["hurl_config"] == str(config_home / "hurl" / "config")


def test_hurl_config_is_printed_on_a_real_run(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")
    config_home = tmp_path / "xdg"
    (config_home / "hurl").mkdir(parents=True)
    config = config_home / "hurl" / "config"
    config.write_text("--verbose\n")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))

    with patch("subprocess.run", return_value=ok()):
        result = run_hurl_orchestrator(str(tmp_path))

    out = capsys.readouterr().out
    assert result is True
    assert f"Hurl config: {config}" in out


def test_cli_passes_secrets_file_and_injection_mode(tmp_path: Path) -> None:
    with (
        patch("hurl_orchestra.cli.run_hurl_orchestrator", return_value=True) as mock,
        patch(
            "sys.argv",
            [
                "hurl-orchestra",
                "--secrets-file",
                "s.env",
                "--inject-as-variables",
                str(tmp_path),
            ],
        ),
    ):
        main()

    assert mock.call_args.kwargs["secrets_file"] == "s.env"
    assert mock.call_args.kwargs["inject_as_variables"] is True


def test_short_max_time_flag_skips_injection(tmp_path: Path) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")
    cmds: list[list[str]] = []

    def fake_run(cmd: list[str], **kw: object) -> CompletedProcess[str]:
        cmds.append(list(cmd))
        return ok()

    with patch("subprocess.run", side_effect=fake_run):
        run_hurl_orchestrator(str(tmp_path), extra_hurl_args=["-m5"])

    assert "-m5" in cmds[0]
    assert "--max-time" not in cmds[0]


def test_hurl_config_is_ignored_before_hurl_8_1(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")
    config_home = tmp_path / "xdg"
    (config_home / "hurl").mkdir(parents=True)
    (config_home / "hurl" / "config").write_text("--verbose\n")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))

    with (
        patch(
            "hurl_orchestra.orchestrator.detect_hurl_version",
            return_value=(7, 1, 0),
        ),
        patch("subprocess.run", return_value=ok()),
    ):
        result = run_hurl_orchestrator(str(tmp_path))

    out = capsys.readouterr().out
    assert result is True
    assert "Hurl config:" not in out


def test_read_hurl_version_returns_none_when_the_binary_fails() -> None:
    from hurl_orchestra.orchestrator import _read_hurl_version

    with patch("subprocess.run", side_effect=OSError("boom")):
        assert _read_hurl_version() is None


def test_read_hurl_version_returns_none_for_unknown_output() -> None:
    from hurl_orchestra.orchestrator import _read_hurl_version

    result = CompletedProcess([], 0, "hurl unknown", "")
    with patch("subprocess.run", return_value=result):
        assert _read_hurl_version() is None


def test_read_hurl_version_parses_the_output() -> None:
    from hurl_orchestra.orchestrator import _read_hurl_version

    result = CompletedProcess([], 0, "hurl 8.1.0 (x86_64)", "")
    with patch("subprocess.run", return_value=result):
        assert _read_hurl_version() == (8, 1, 0)


def test_empty_variable_part_is_rejected() -> None:
    from hurl_orchestra.orchestrator import _hurl_variable_name

    with pytest.raises(ValueError, match="non-empty"):
        _hurl_variable_name("", "x")


def test_node_args_with_a_leading_dash_are_kept(tmp_path: Path) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping", args=["--insecure"])
    cmds: list[list[str]] = []

    def fake_run(cmd: list[str], **kw: object) -> CompletedProcess[str]:
        cmds.append(list(cmd))
        return ok()

    with patch("subprocess.run", side_effect=fake_run):
        run_hurl_orchestrator(str(tmp_path))

    assert cmds[0].count("--insecure") == 1


def test_multi_key_args_mapping_is_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "a.hurl").write_text(
        "---\nid: a\nargs:\n  - insecure: true\n    verbose: true\n---\n"
    )
    result = run_hurl_orchestrator(str(tmp_path), dry_run=True)

    assert result is False
    assert "single-key dicts" in capsys.readouterr().out


def test_invalid_retry_frontmatter_is_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "a.hurl").write_text(
        "---\nid: a\nretry:\n  attempts: 0\n---\nGET https://example.com\n"
    )
    result = run_hurl_orchestrator(str(tmp_path), dry_run=True)

    assert result is False
    assert "retry.attempts" in capsys.readouterr().out


def test_secrets_file_keeps_comments_and_blank_lines(tmp_path: Path) -> None:
    hurl_file(tmp_path / "auth.hurl", id="auth", outputs=["token"])
    hurl_file(tmp_path / "profile.hurl", id="profile", deps=["auth"])
    secrets = tmp_path / "secrets.env"
    secrets.write_text("# global secrets\n\nother=keep\n")
    report = [{"entries": [{"captures": [{"name": "token", "value": "new"}]}]}]
    merged: list[str] = []

    def fake_run(cmd: list[str], **kw: object) -> CompletedProcess[str]:
        if "--secrets-file" in cmd:
            merged.append(Path(cmd[cmd.index("--secrets-file") + 1]).read_text())
        for i, part in enumerate(cmd):
            if part == "--report-json":
                (Path(cmd[i + 1]) / "report.json").write_text(json.dumps(report))
        return ok()

    with patch("subprocess.run", side_effect=fake_run):
        run_hurl_orchestrator(str(tmp_path), secrets_file=str(secrets))

    assert "# global secrets" in merged[-1]
    assert "other=keep\n" in merged[-1]


def test_no_deps_with_existing_files_runs_them(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")
    with patch("subprocess.run", return_value=ok()):
        result = run_hurl_orchestrator(
            files=[str(tmp_path / "ping.hurl")], resolve_deps=False
        )

    assert result is True
    assert "SUCCESS: ping" in capsys.readouterr().out


def test_absolute_report_zip_path_is_used(tmp_path: Path) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")
    absolute = tmp_path / "reports" / "ci.zip"

    with (
        patch("subprocess.run", return_value=ok()),
        patch("shutil.make_archive", return_value=str(absolute)) as archive,
    ):
        result = run_hurl_orchestrator(str(tmp_path), report_zip=str(absolute))

    assert result is True
    assert archive.call_args.args[0] == str(absolute.with_suffix(""))


def test_ctrf_write_error_is_a_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")
    with (
        patch("subprocess.run", return_value=ok()),
        patch(
            "hurl_orchestra.orchestrator.write_ctrf",
            side_effect=OSError("disk full"),
        ),
    ):
        result = run_hurl_orchestrator(
            str(tmp_path), report_ctrf=str(tmp_path / "results.json")
        )

    out = capsys.readouterr().out
    assert result is True
    assert "Failed to write CTRF report" in out


def test_graph_error_during_execution_is_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from hurl_orchestra.orchestrator import GraphError

    hurl_file(tmp_path / "ping.hurl", id="ping")
    with patch(
        "hurl_orchestra.orchestrator._execute",
        side_effect=GraphError("ERROR: late graph problem"),
    ):
        result = run_hurl_orchestrator(str(tmp_path))

    out = capsys.readouterr().out
    assert result is False
    assert "late graph problem" in out


@pytest.mark.parametrize("value", ["nope", "0"])
def test_cli_rejects_an_invalid_timeout(value: str) -> None:
    with (
        patch("sys.argv", ["hurl-orchestra", "--timeout", value]),
        pytest.raises(SystemExit),
    ):
        main()
