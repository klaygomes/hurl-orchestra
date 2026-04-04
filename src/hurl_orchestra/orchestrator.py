"""Core orchestration logic for hurl-orchestra."""

import json
import subprocess
from collections.abc import Iterator
from graphlib import CycleError, TopologicalSorter
from pathlib import Path
from typing import Any

import frontmatter


def extract_captures(
    report_path: Path, target_outputs: list[str]
) -> Iterator[tuple[str, Any]]:
    """Yield ``(name, value)`` pairs captured in a Hurl JSON report.

    Only names present in *target_outputs* are yielded.
    Silently returns if the report file is missing or contains invalid JSON.
    """
    if not report_path.exists():
        return
    with report_path.open() as rf:
        try:
            report_data = json.load(rf)
        except json.JSONDecodeError:
            return
    for entry in report_data.get("entries", []):
        captures = entry.get("response", {}).get("captures", [])
        for cap in captures:
            name, value = cap.get("name"), cap.get("value")
            if name in target_outputs:
                yield name, value


def get_global_args(test_dir: Path) -> list[str]:
    """Return hurl CLI arguments derived from global config in *test_dir*.

    Detects a ``.env`` file and passes it via ``--variables-file``.
    """
    args: list[str] = []
    env_file = test_dir / ".env"
    if env_file.exists():
        args.extend(["--variables-file", str(env_file)])
    return args


def run_step(
    node_id: str,
    node: dict[str, Any],
    shared_vars: dict[str, Any],
    graph: dict[str, set[str]],
    global_args: list[str],
) -> bool:
    """Execute a single hurl node, injecting upstream variables and capturing outputs.

    Returns ``True`` on success, ``False`` if the hurl process exits non-zero.
    The temporary JSON report file is always cleaned up after execution.
    """
    report_path = Path(f"{node_id}_report.json")
    cmd = [
        "hurl",
        "--test",
        *global_args,
        node["path"],
        "--report-json",
        str(report_path),
    ]

    for dep_id in graph.get(node_id, set()):
        for var_key, value in shared_vars.items():
            if var_key.startswith(f"{dep_id}."):
                cmd.extend(["--variable", f"{var_key}={value}"])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            print(f"FAILED: {node_id}\n{result.stderr}")
            return False

        for name, value in extract_captures(report_path, node["outputs"]):
            shared_vars[f"{node_id}.{name}"] = value

        print(f"SUCCESS: {node_id}")
        return True
    finally:
        report_path.unlink(missing_ok=True)


def run_hurl_orchestrator(test_dir_str: str = ".") -> None:
    """Discover, order, and execute all ``.hurl`` files in *test_dir_str*.

    Files are executed in topological dependency order.  Execution halts on the
    first failure to avoid cascade failures in downstream nodes.
    """
    test_dir = Path(test_dir_str)
    templates: dict[str, dict[str, Any]] = {}
    nodes: dict[str, dict[str, Any]] = {}
    graph: dict[str, set[str]] = {}
    shared_vars: dict[str, Any] = {}

    global_args = get_global_args(test_dir)

    for path in sorted(test_dir.glob("*.hurl")):
        with path.open() as f:
            post = frontmatter.load(f)
            t_id: str = post.get("id", path.stem)
            templates[t_id] = {
                "path": str(path),
                "outputs": post.get("outputs", []),
                "deps": post.get("deps", []),
            }

    for t_id, data in templates.items():
        if t_id not in nodes:
            nodes[t_id] = data.copy()
            graph[t_id] = set()
        for dep in data["deps"]:
            if isinstance(dep, dict):
                for template_name, instance_name in dep.items():
                    if instance_name not in nodes:
                        nodes[instance_name] = templates[template_name].copy()
                        graph[instance_name] = set(templates[template_name]["deps"])
                    graph[t_id].add(instance_name)
            else:
                graph[t_id].add(dep)

    try:
        order = list(TopologicalSorter(graph).static_order())
        for node_id in order:
            if not run_step(node_id, nodes[node_id], shared_vars, graph, global_args):
                break
    except CycleError as e:
        print(f"Circular dependency: {e}")
