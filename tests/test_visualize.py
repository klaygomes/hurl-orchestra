"""Tests for hurl_orchestra.visualize."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from hurl_orchestra.visualize import (
    _escape_label,
    _node_label,
    _render_flowchart,
    _safe_id_map,
    GraphError,
    build_diagram,
    write_diagram,
)


def hurl_file(
    path: Path,
    *,
    id: str | None = None,
    outputs: list[str] | None = None,
    deps: list | None = None,
    priority: int | None = None,
) -> None:
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




def test_safe_id_replaces_hyphens() -> None:
    m = _safe_id_map(["auth-v2"])
    assert m["auth-v2"] == "node_0"


def test_safe_id_preserves_alphanumeric_and_underscore() -> None:
    m = _safe_id_map(["my_node"])
    assert m["my_node"] == "node_0"


def test_safe_id_collision_gets_unique_nodes() -> None:
    m = _safe_id_map(["auth-v2", "auth_v2"])
    assert m["auth-v2"] == "node_0"
    assert m["auth_v2"] == "node_1"


def test_safe_id_original_id_preserved_as_key() -> None:
    m = _safe_id_map(["auth-v2"])
    assert "auth-v2" in m




def test_node_label_zero_priority_shows_out_count() -> None:
    node = {"outputs": ["token", "user_id"], "priority": 0}
    assert _node_label("auth", node) == "auth [out:2]"


def test_node_label_nonzero_priority_includes_p() -> None:
    node = {"outputs": [], "priority": 1}
    assert _node_label("create", node) == "create [p:1, out:0]"


def test_node_label_negative_priority() -> None:
    node = {"outputs": ["x"], "priority": -1}
    assert _node_label("cleanup", node) == "cleanup [p:-1, out:1]"


def test_node_label_null_outputs_is_handled() -> None:
    node = {"outputs": None, "priority": 0}
    assert _node_label("auth", node) == "auth [out:0]"


def test_node_label_null_priority_is_treated_as_zero() -> None:
    node = {"outputs": [], "priority": None}
    assert _node_label("create", node) == "create [out:0]"


def test_node_label_noniterable_outputs_is_treated_as_zero() -> None:
    node = {"outputs": 42, "priority": 0}
    assert _node_label("auth", node) == "auth [out:0]"


def test_node_label_invalid_priority_defaults_to_zero(
    caplog: pytest.LogCaptureFixture,
) -> None:
    node = {"outputs": ["token"], "priority": "high"}

    with caplog.at_level("WARNING"):
        assert _node_label("auth", node) == "auth [out:1]"

    assert "Node 'auth' has invalid priority 'high'. Defaulting to 0." in caplog.text


def test_flowchart_includes_isolated_node(tmp_path: Path) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")
    diagram = build_diagram(sorted(tmp_path.glob("*.hurl")))
    assert diagram is not None
    assert "ping" in diagram
    assert "## Flowchart" in diagram


def test_flowchart_edge_direction_dep_to_dependent(tmp_path: Path) -> None:
    hurl_file(tmp_path / "auth.hurl", id="auth")
    hurl_file(tmp_path / "profile.hurl", id="profile", deps=["auth"])
    nodes = {"auth": {"outputs": [], "priority": 0}, "profile": {"outputs": [], "priority": 0}}
    graph: dict[str, set[str]] = {"auth": set(), "profile": {"auth"}}
    safe_ids = _safe_id_map(nodes.keys())
    fc = _render_flowchart(nodes, graph, safe_ids)
    assert "node_0 --> node_1" in fc


def test_flowchart_label_includes_output_count(tmp_path: Path) -> None:
    hurl_file(tmp_path / "auth.hurl", id="auth", outputs=["token", "user_id"])
    diagram = build_diagram(sorted(tmp_path.glob("*.hurl")))
    assert diagram is not None
    assert "out:2" in diagram


def test_flowchart_label_includes_priority_when_nonzero(tmp_path: Path) -> None:
    hurl_file(tmp_path / "create.hurl", id="create", priority=1)
    diagram = build_diagram(sorted(tmp_path.glob("*.hurl")))
    assert diagram is not None
    assert "p:1" in diagram


def test_flowchart_label_omits_priority_when_zero(tmp_path: Path) -> None:
    hurl_file(tmp_path / "auth.hurl", id="auth")
    diagram = build_diagram(sorted(tmp_path.glob("*.hurl")))
    assert diagram is not None
    assert "p:0" not in diagram


def test_flowchart_uses_safe_id_in_edge(tmp_path: Path) -> None:
    hurl_file(tmp_path / "auth-v2.hurl", id="auth-v2")
    hurl_file(tmp_path / "profile.hurl", id="profile", deps=["auth-v2"])
    diagram = build_diagram(sorted(tmp_path.glob("*.hurl")))
    assert diagram is not None
    assert "node_0 --> node_1" in diagram


def test_flowchart_preserves_original_id_in_label(tmp_path: Path) -> None:
    hurl_file(tmp_path / "auth-v2.hurl", id="auth-v2")
    diagram = build_diagram(sorted(tmp_path.glob("*.hurl")))
    assert diagram is not None
    assert "auth-v2" in diagram


def test_flowchart_emits_edge_for_dependency(tmp_path: Path) -> None:
    hurl_file(tmp_path / "auth.hurl", id="auth", outputs=["token"])
    hurl_file(tmp_path / "profile.hurl", id="profile", deps=["auth"])
    diagram = build_diagram(sorted(tmp_path.glob("*.hurl")))
    assert diagram is not None
    assert "node_0 --> node_1" in diagram


def test_flowchart_includes_isolated_node_when_rendering(tmp_path: Path) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")
    nodes = {"ping": {"outputs": [], "priority": 0}}
    graph: dict[str, set[str]] = {"ping": set()}
    flowchart = _render_flowchart(nodes, graph, _safe_id_map(nodes))
    assert 'node_0["ping [out:0]"]' in flowchart


def test_flowchart_quotes_node_label_with_comma() -> None:
    nodes = {"a,b": {"outputs": ["x"], "priority": 0}, "c": {"outputs": [], "priority": 0}}
    graph: dict[str, set[str]] = {"a,b": set(), "c": {"a,b"}}
    safe_ids = _safe_id_map(nodes)
    flowchart = _render_flowchart(nodes, graph, safe_ids)
    assert f'{safe_ids["a,b"]}["a,b [out:1]"]' in flowchart
    assert f'{safe_ids["a,b"]} --> {safe_ids["c"]}' in flowchart


def test_render_flowchart_rejects_dangling_dependencies() -> None:
    nodes = {"a": {"outputs": [], "priority": 0}}
    graph: dict[str, set[str]] = {"a": {"missing"}}
    with pytest.raises(GraphError, match="Dangling dependency detected"):
        _render_flowchart(nodes, graph, _safe_id_map(nodes))


def test_markdown_contains_flowchart_heading(tmp_path: Path) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")
    diagram = build_diagram(sorted(tmp_path.glob("*.hurl")))
    assert diagram is not None
    assert "## Flowchart" in diagram




def test_markdown_contains_generator_footer(tmp_path: Path) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")
    diagram = build_diagram(sorted(tmp_path.glob("*.hurl")))
    assert diagram is not None
    assert "Generated by hurl-orchestra" in diagram


def test_empty_hurl_path_list_produces_diagram() -> None:
    diagram = build_diagram([])
    assert diagram is not None
    assert "## Flowchart" in diagram
    assert "## Dependency graph" not in diagram




def test_build_diagram_raises_graph_error_on_missing_dep(tmp_path: Path) -> None:
    hurl_file(tmp_path / "a.hurl", id="a", deps=["nonexistent"])
    with pytest.raises(GraphError, match="nonexistent"):
        build_diagram(sorted(tmp_path.glob("*.hurl")))


def test_build_diagram_raises_graph_error_on_cycle(tmp_path: Path) -> None:
    hurl_file(tmp_path / "a.hurl", id="a", deps=["b"])
    hurl_file(tmp_path / "b.hurl", id="b", deps=["a"])
    with pytest.raises(GraphError, match="Circular dependency"):
        build_diagram(sorted(tmp_path.glob("*.hurl")))


def test_escape_label_quotes_and_brackets() -> None:
    assert _escape_label('a"b[c]') == 'a&quot;b&#91;c&#93;'


def test_escape_label_escapes_angle_brackets() -> None:
    assert _escape_label("a<b>c") == "a&lt;b&gt;c"


def test_write_diagram_creates_file(tmp_path: Path) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")
    out = str(tmp_path / "out.md")
    ok = write_diagram(sorted(tmp_path.glob("*.hurl")), output=out)
    assert ok is True
    assert "## Flowchart" in Path(out).read_text()


def test_write_diagram_stdout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")
    ok = write_diagram(sorted(tmp_path.glob("*.hurl")), output="-")
    assert ok is True
    assert "## Flowchart" in capsys.readouterr().out


def test_write_diagram_handles_broken_pipe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")

    class BrokenStdout:
        def write(self, content: str) -> int:
            raise BrokenPipeError

        def flush(self) -> None:
            return None

    monkeypatch.setattr(sys, "stdout", BrokenStdout())
    assert write_diagram(sorted(tmp_path.glob("*.hurl")), output="-") is False


def test_write_diagram_returns_false_on_error(tmp_path: Path) -> None:
    hurl_file(tmp_path / "a.hurl", id="a", deps=["missing"])
    ok = write_diagram(sorted(tmp_path.glob("*.hurl")))
    assert ok is False


def test_write_diagram_returns_false_on_missing_input_file(tmp_path: Path) -> None:
    out = tmp_path / "out.md"
    ok = write_diagram([tmp_path / "missing.hurl"], output=str(out))
    assert ok is False


def test_write_diagram_returns_false_when_output_is_directory(tmp_path: Path) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")
    ok = write_diagram(sorted(tmp_path.glob("*.hurl")), output=str(tmp_path))
    assert ok is False


def test_write_diagram_refuses_existing_file_without_overwrite(tmp_path: Path) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")
    out = tmp_path / "out.md"
    out.write_text("existing")
    ok = write_diagram(sorted(tmp_path.glob("*.hurl")), output=str(out))
    assert ok is False


def test_write_diagram_allows_existing_file_with_overwrite(tmp_path: Path) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")
    out = tmp_path / "out.md"
    out.write_text("existing")
    ok = write_diagram(sorted(tmp_path.glob("*.hurl")), output=str(out), overwrite=True)
    assert ok is True
    assert "## Flowchart" in out.read_text()
