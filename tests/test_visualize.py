"""Tests for hurl_orchestra.visualize."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hurl_orchestra.visualize import (
    _csv_val,
    _node_label,
    _render_flowchart,
    _render_sankey,
    _safe_id_map,
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
    assert m["auth-v2"] == "auth_v2"


def test_safe_id_preserves_alphanumeric_and_underscore() -> None:
    m = _safe_id_map(["my_node"])
    assert m["my_node"] == "my_node"


def test_safe_id_collision_gets_suffix() -> None:
    m = _safe_id_map(["auth-v2", "auth_v2"])
    assert m["auth-v2"] == "auth_v2"
    assert m["auth_v2"] == "auth_v2_1"


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




def test_csv_val_plain_string_unchanged() -> None:
    assert _csv_val("auth") == "auth"


def test_csv_val_comma_triggers_quoting() -> None:
    assert _csv_val("a,b") == '"a,b"'


def test_csv_val_double_quote_triggers_doubling() -> None:
    assert _csv_val('a"b') == '"a""b"'




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
    assert "auth --> profile" in fc


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
    assert "auth_v2 --> profile" in diagram


def test_flowchart_preserves_original_id_in_label(tmp_path: Path) -> None:
    hurl_file(tmp_path / "auth-v2.hurl", id="auth-v2")
    diagram = build_diagram(sorted(tmp_path.glob("*.hurl")))
    assert diagram is not None
    assert "auth-v2" in diagram




def test_sankey_emits_edge_for_dependency(tmp_path: Path) -> None:
    hurl_file(tmp_path / "auth.hurl", id="auth", outputs=["token"])
    hurl_file(tmp_path / "profile.hurl", id="profile", deps=["auth"])
    diagram = build_diagram(sorted(tmp_path.glob("*.hurl")))
    assert diagram is not None
    assert "auth,profile,1" in diagram


def test_sankey_weight_equals_output_count(tmp_path: Path) -> None:
    hurl_file(tmp_path / "auth.hurl", id="auth", outputs=["a", "b", "c"])
    hurl_file(tmp_path / "profile.hurl", id="profile", deps=["auth"])
    diagram = build_diagram(sorted(tmp_path.glob("*.hurl")))
    assert diagram is not None
    assert "auth,profile,3" in diagram


def test_sankey_weight_floor_is_one_when_zero_outputs(tmp_path: Path) -> None:
    hurl_file(tmp_path / "auth.hurl", id="auth", outputs=[])
    hurl_file(tmp_path / "profile.hurl", id="profile", deps=["auth"])
    diagram = build_diagram(sorted(tmp_path.glob("*.hurl")))
    assert diagram is not None
    assert "auth,profile,1" in diagram


def test_sankey_omits_isolated_node(tmp_path: Path) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")
    nodes = {"ping": {"outputs": [], "priority": 0}}
    graph: dict[str, set[str]] = {"ping": set()}
    sankey = _render_sankey(nodes, graph)
    assert "ping" not in sankey.replace("sankey-beta", "")


def test_sankey_quotes_node_id_with_comma() -> None:
    nodes = {"a,b": {"outputs": ["x"], "priority": 0}, "c": {"outputs": [], "priority": 0}}
    graph: dict[str, set[str]] = {"a,b": set(), "c": {"a,b"}}
    sankey = _render_sankey(nodes, graph)
    assert '"a,b",c,1' in sankey




def test_markdown_contains_flowchart_heading(tmp_path: Path) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")
    diagram = build_diagram(sorted(tmp_path.glob("*.hurl")))
    assert diagram is not None
    assert "## Flowchart" in diagram


def test_markdown_contains_sankey_heading(tmp_path: Path) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")
    diagram = build_diagram(sorted(tmp_path.glob("*.hurl")))
    assert diagram is not None
    assert "## Sankey" in diagram


def test_markdown_flowchart_before_sankey(tmp_path: Path) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")
    diagram = build_diagram(sorted(tmp_path.glob("*.hurl")))
    assert diagram is not None
    assert diagram.index("## Flowchart") < diagram.index("## Sankey")


def test_markdown_contains_generator_footer(tmp_path: Path) -> None:
    hurl_file(tmp_path / "ping.hurl", id="ping")
    diagram = build_diagram(sorted(tmp_path.glob("*.hurl")))
    assert diagram is not None
    assert "Generated by hurl-orchestra" in diagram


def test_empty_hurl_path_list_produces_diagram() -> None:
    diagram = build_diagram([])
    assert diagram is not None
    assert "## Flowchart" in diagram
    assert "## Sankey" in diagram




def test_build_diagram_returns_none_on_missing_dep(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hurl_file(tmp_path / "a.hurl", id="a", deps=["nonexistent"])
    result = build_diagram(sorted(tmp_path.glob("*.hurl")))
    assert result is None
    assert "ERROR" in capsys.readouterr().out




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


def test_write_diagram_returns_false_on_error(tmp_path: Path) -> None:
    hurl_file(tmp_path / "a.hurl", id="a", deps=["missing"])
    ok = write_diagram(sorted(tmp_path.glob("*.hurl")))
    assert ok is False
