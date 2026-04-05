"""Core orchestration logic for hurl-orchestra."""

import json
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from graphlib import CycleError, TopologicalSorter
from pathlib import Path
from typing import Any

import frontmatter


def extract_captures(
    report_path: Path, target_outputs: list[str], node_id: str = ""
) -> Iterator[tuple[str, Any]]:
    """Yield ``(name, value)`` pairs captured in a Hurl JSON report.

    Only names present in *target_outputs* are yielded.
    """
    if not report_path.exists():
        if target_outputs:
            outputs = ", ".join(target_outputs)
            print(f"WARNING: {node_id}: report not found; [{outputs}] not captured")
        return
    with report_path.open() as rf:
        try:
            report_data = json.load(rf)
        except json.JSONDecodeError:
            outputs = ", ".join(target_outputs)
            print(f"WARNING: {node_id}: invalid report JSON; [{outputs}] not captured")
            return
    file_results = report_data if isinstance(report_data, list) else [report_data]
    for file_result in file_results:
        for entry in file_result.get("entries", []):
            for cap in entry.get("captures", []):
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
    extra_hurl_args: list[str],
    node_report_dir: Path,
) -> bool:
    """Execute a single hurl node, injecting upstream variables and capturing outputs.

    Returns ``True`` on success, ``False`` if the hurl process exits non-zero.
    """
    injected: list[str] = []
    report_file = node_report_dir / "report.json"
    cmd = [
        "hurl",
        "--test",
        *global_args,
        *extra_hurl_args,
        "--report-json",
        str(node_report_dir),
    ]

    for dep_id in graph.get(node_id, set()):
        for var_key, value in shared_vars.items():
            if var_key.startswith(f"{dep_id}."):
                hurl_name = var_key.replace(".", "_")
                cmd.extend(["--variable", f"{hurl_name}={value}"])
                injected.append(hurl_name)

    result = subprocess.run(
        cmd,
        input=node["content"],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(Path(node["path"]).parent),
    )
    if result.returncode != 0:
        print(f"FAILED: {node_id}\n{result.stderr}")
        return False

    captured: list[str] = []
    for name, value in extract_captures(report_file, node["outputs"], node_id):
        shared_vars[f"{node_id}.{name}"] = value
        captured.append(name)

    missed = [o for o in node["outputs"] if o not in captured]
    parts: list[str] = []
    if injected:
        parts.append(f"injected: {', '.join(injected)}")
    if captured:
        parts.append(f"captured: {', '.join(captured)}")
    if missed:
        parts.append(f"NOT captured: {', '.join(missed)}")
    suffix = f" [{' | '.join(parts)}]" if parts else ""
    print(f"SUCCESS: {node_id}{suffix}")
    return True


def _execute(
    nodes: dict[str, dict[str, Any]],
    graph: dict[str, set[str]],
    shared_vars: dict[str, Any],
    global_args: list[str],
    extra: list[str],
    reports_path: Path,
) -> bool:
    """Run nodes in topological order, writing each report to *reports_path*.

    Raises ``CycleError`` if a dependency cycle is detected.
    Returns ``False`` as soon as a node fails, ``True`` if all succeed.
    """
    sorter = TopologicalSorter(graph)
    sorter.prepare()
    while sorter.is_active():
        wave = sorted(
            sorter.get_ready(),
            key=lambda nid: nodes[nid]["priority"],
            reverse=True,
        )
        for node_id in wave:
            node_report_dir = reports_path / node_id
            node_report_dir.mkdir()
            success = run_step(
                node_id,
                nodes[node_id],
                shared_vars,
                graph,
                global_args,
                extra,
                node_report_dir,
            )
            sorter.done(node_id)
            if not success:
                return False
    return True


def _validate_graph(
    nodes: dict[str, dict[str, Any]], graph: dict[str, set[str]]
) -> str | None:
    """Return an error message if any dependency is missing from *nodes*, else None."""
    for t_id, deps in graph.items():
        for dep_id in deps:
            if dep_id not in nodes:
                return (
                    f"ERROR: '{t_id}' depends on '{dep_id}'"
                    f" but no .hurl file or alias defines id: {dep_id}"
                )
    return None


def run_hurl_orchestrator(
    test_dir_str: str = ".",
    *,
    files: list[str] | None = None,
    extra_hurl_args: list[str] | None = None,
    report_zip: str = "report.zip",
) -> bool:
    """Discover, order, and execute ``.hurl`` files in dependency order.

    When *files* is provided those specific files are used instead of scanning
    *test_dir_str*.  Any *extra_hurl_args* are forwarded verbatim to every hurl
    invocation, allowing flags like ``--verbose`` or ``--variable key=val``.
    After execution a zip archive of all hurl reports is written to *report_zip*
    in the current working directory.

    Returns ``True`` if all steps succeeded, ``False`` otherwise.
    """
    if shutil.which("hurl") is None:
        print("ERROR: 'hurl' not found on PATH. Install it from https://hurl.dev")
        return False

    test_dir = Path(test_dir_str)
    templates: dict[str, dict[str, Any]] = {}
    nodes: dict[str, dict[str, Any]] = {}
    graph: dict[str, set[str]] = {}
    shared_vars: dict[str, Any] = {}
    extra = extra_hurl_args or []

    if files is not None:
        hurl_paths: list[Path] = [Path(f) for f in files]
        if hurl_paths:
            test_dir = hurl_paths[0].parent
    else:
        hurl_paths = sorted(test_dir.glob("*.hurl"))

    global_args = get_global_args(test_dir)

    for path in hurl_paths:
        with path.open() as f:
            post = frontmatter.load(f)
            t_id: str = post.get("id", path.stem)
            templates[t_id] = {
                "path": str(path),
                "content": post.content,
                "outputs": post.get("outputs", []),
                "deps": post.get("deps", []),
                "priority": int(post.get("priority", 0)),
            }

    for t_id, data in templates.items():
        if t_id not in nodes:
            nodes[t_id] = data.copy()
            graph[t_id] = set()
        for dep in data["deps"]:
            if isinstance(dep, dict):
                for template_name, instance_name in dep.items():
                    if template_name not in templates:
                        print(
                            f"ERROR: '{t_id}': alias template '{template_name}'"
                            f" not found (used as '{instance_name}')"
                        )
                        return False
                    if instance_name not in nodes:
                        nodes[instance_name] = templates[template_name].copy()
                        graph[instance_name] = set(templates[template_name]["deps"])
                    graph[t_id].add(instance_name)
            else:
                graph[t_id].add(dep)

    error = _validate_graph(nodes, graph)
    if error:
        print(error)
        return False

    with tempfile.TemporaryDirectory() as reports_root:
        try:
            all_ok = _execute(
                nodes, graph, shared_vars, global_args, extra, Path(reports_root)
            )
        except CycleError as e:
            print(f"Circular dependency: {e}")
            return False

        zip_base = str(Path(report_zip).with_suffix(""))
        archive = shutil.make_archive(zip_base, "zip", reports_root)
        print(f"Report saved to {archive}")

    return all_ok
