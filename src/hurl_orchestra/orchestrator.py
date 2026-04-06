"""Core orchestration logic for hurl-orchestra."""

import json
import os
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from graphlib import CycleError, TopologicalSorter
from pathlib import Path
from typing import Any

import frontmatter


class GraphError(Exception):
    """Raised when graph construction or validation fails."""


MAX_WORKERS = min(32, (os.cpu_count() or 1) + 4)


def _validate_identifier(value: Any, description: str) -> str:
    if not isinstance(value, str) or not value:
        raise GraphError(
            f"ERROR: {description} must be a non-empty string; got {value!r}"
        )
    if any(ch.isspace() for ch in value):
        raise GraphError(
            f"ERROR: {description} must not contain whitespace; got {value!r}"
        )
    return value


def _sanitize_hurl_variable_part(value: str) -> str:
    if not value:
        raise ValueError("Hurl variable part must be a non-empty string")
    return "".join(
        ch if ch.isalnum() or ch == "_" else f"_{ord(ch):02x}_" for ch in value
    )


def _hurl_variable_name(dep_id: str, output_name: str) -> str:
    return (
        f"{_sanitize_hurl_variable_part(dep_id)}_"
        f"{_sanitize_hurl_variable_part(output_name)}"
    )


def _parse_outputs(outputs: Any, t_id: str) -> list[str]:
    if outputs is None:
        return []
    if not isinstance(outputs, list):
        raise GraphError(
            f"ERROR: outputs for '{t_id}' must be a list; got {type(outputs).__name__}"
        )
    for output_name in outputs:
        _validate_identifier(output_name, f"output name for node '{t_id}'")
    return outputs


def _parse_deps(deps: Any, t_id: str) -> list[Any]:
    if deps is None:
        return []
    if not isinstance(deps, list):
        raise GraphError(
            f"ERROR: deps for '{t_id}' must be a list; got {type(deps).__name__}"
        )

    validated: list[Any] = []
    for dep in deps:
        if isinstance(dep, dict):
            if len(dep) != 1:
                raise GraphError(
                    "ERROR: deps for "
                    f"'{t_id}' must be a list of strings or single-key dicts"
                )
            for template_name, instance_name in dep.items():
                _validate_identifier(
                    template_name,
                    f"alias template name for node '{t_id}'",
                )
                _validate_identifier(
                    instance_name,
                    f"alias instance name for node '{t_id}'",
                )
        elif isinstance(dep, str):
            _validate_identifier(dep, f"dependency id for node '{t_id}'")
        else:
            raise GraphError(
                f"ERROR: deps for '{t_id}' must contain strings or dicts; "
                f"got {type(dep).__name__}"
            )
        validated.append(dep)
    return validated


def _parse_priority(priority_value: Any, t_id: str) -> int:
    try:
        return int(priority_value)
    except (TypeError, ValueError) as err:
        raise GraphError(
            f"ERROR: priority for '{t_id}' must be an integer; got {priority_value!r}"
        ) from err


def _parse_args(args: Any, t_id: str) -> list[str]:
    if args is None:
        return []
    if not isinstance(args, list):
        raise GraphError(
            f"ERROR: args for '{t_id}' must be a list; got {type(args).__name__}"
        )

    flat: list[str] = []
    for item in args:
        if isinstance(item, str):
            if item.startswith("-"):
                flat.append(item)
            else:
                prefix = "-" if len(item) == 1 else "--"
                flat.append(f"{prefix}{item}")
        elif isinstance(item, dict):
            if len(item) != 1:
                raise GraphError(
                    f"ERROR: args for '{t_id}' must contain strings or single-key dicts"
                )
            for key, value in item.items():
                prefix = "-" if len(key) == 1 else "--"
                flat.extend([f"{prefix}{key}", str(value)])
        else:
            raise GraphError(
                f"ERROR: args for '{t_id}' must contain strings or dicts; "
                f"got {type(item).__name__}"
            )
    return flat


def extract_captures(
    report_path: Path, target_outputs: list[str], node_id: str = ""
) -> dict[str, Any]:
    """Return captured values from a Hurl JSON report.

    Only names present in *target_outputs* are returned.
    """
    if not report_path.exists():
        if target_outputs:
            outputs = ", ".join(target_outputs)
            print(f"ERROR: {node_id}: report not found; [{outputs}] not captured")
        return {}
    with report_path.open() as rf:
        try:
            report_data = json.load(rf)
        except json.JSONDecodeError:
            outputs = ", ".join(target_outputs)
            print(f"ERROR: {node_id}: invalid report JSON; [{outputs}] not captured")
            return {}
    file_results = report_data if isinstance(report_data, list) else [report_data]
    captures: dict[str, Any] = {}
    for entry_index, entry in enumerate(file_results):
        entries = entry.get("entries")
        if isinstance(entries, list):
            search_targets = entries
        else:
            search_targets = [entry]

        for target in search_targets:
            for cap in target.get("captures", []):
                name = cap.get("name")
                if name in target_outputs:
                    if name in captures:
                        message = (
                            f"WARNING: {node_id}: output '{name}' "
                            f"overwritten by entry {entry_index}"
                        )
                        print(message)
                    captures[name] = cap.get("value")
    return captures


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
    shared_vars: dict[str, dict[str, Any]],
    graph: dict[str, set[str]],
    global_args: list[str],
    extra_hurl_args: list[str],
    node_report_dir: Path,
) -> tuple[bool, str, dict[str, Any]]:
    """Execute a single hurl node, injecting upstream variables and capturing outputs.

    Returns ``(success, message, captured_outputs)`` where the caller can
    update shared state.
    """
    injected: list[str] = []
    report_file = node_report_dir / "report.json"
    cmd = [
        "hurl",
        "--test",
        *global_args,
        *extra_hurl_args,
        *node.get("hurl_args", []),
        "--report-json",
        str(node_report_dir),
    ]

    for dep_id in graph.get(node_id, set()):
        for var_key, value in shared_vars.get(dep_id, {}).items():
            hurl_name = _hurl_variable_name(dep_id, var_key)
            cmd.extend(["--variable", f"{hurl_name}={value}"])
            injected.append(hurl_name)

    try:
        result = subprocess.run(
            cmd,
            input=node["content"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=300,
            cwd=str(Path(node["path"]).parent),
        )
    except subprocess.TimeoutExpired:
        return (
            False,
            f"FAILED: {node_id}\nHurl timed out after 300 seconds\n",
            {},
        )

    if result.returncode != 0:
        return (False, f"FAILED: {node_id}\n{result.stderr}", {})

    captures = extract_captures(report_file, node.get("outputs", []), node_id)
    outputs: list[str] = node.get("outputs") or []
    missed = [o for o in outputs if o not in captures]
    if missed:
        actual = ", ".join(sorted(captures.keys())) or "none"
        return (
            False,
            (
                f"FAILED: {node_id}\nMissing expected outputs: {', '.join(missed)}; "
                f"reported outputs: {actual}\n"
            ),
            {},
        )

    parts: list[str] = []
    if injected:
        parts.append(f"injected: {', '.join(injected)}")
    if captures:
        parts.append(f"captured: {', '.join(captures)}")
    suffix = f" [{' | '.join(parts)}]" if parts else ""
    return (True, f"SUCCESS: {node_id}{suffix}\n", captures)


def _execute(
    nodes: dict[str, dict[str, Any]],
    graph: dict[str, set[str]],
    shared_vars: dict[str, dict[str, Any]],
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
    failed_nodes: set[str] = set()
    overall_success = True
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        while sorter.is_active():
            ready = sorted(
                sorter.get_ready(),
                key=lambda nid: nodes[nid]["priority"],
                reverse=True,
            )
            to_run: list[str] = []
            for node_id in ready:
                if any(dep in failed_nodes for dep in graph.get(node_id, set())):
                    failed_nodes.add(node_id)
                    sorter.done(node_id)
                else:
                    to_run.append(node_id)

            if not to_run:
                continue

            for node_id in to_run:
                (reports_path / node_id).mkdir(parents=True, exist_ok=True)

            priorities = sorted(
                {nodes[nid]["priority"] for nid in to_run}, reverse=True
            )
            for priority in priorities:
                group = [nid for nid in to_run if nodes[nid]["priority"] == priority]
                futures = {
                    executor.submit(
                        run_step,
                        node_id,
                        nodes[node_id],
                        shared_vars,
                        graph,
                        global_args,
                        extra,
                        reports_path / node_id,
                    ): node_id
                    for node_id in group
                }
                results: dict[str, tuple[bool, str, dict[str, Any]]] = {}
                for future in futures:
                    node_id = futures[future]
                    try:
                        results[node_id] = future.result()
                    except Exception as exc:
                        results[node_id] = (
                            False,
                            f"FAILED: {node_id}\n{exc}\n",
                            {},
                        )

                for node_id in group:
                    success, message, captured = results[node_id]
                    print(message, end="")
                    if not success:
                        overall_success = False
                        failed_nodes.add(node_id)
                    else:
                        if captured:
                            shared_vars[node_id] = captured
                    sorter.done(node_id)
    return overall_success


def _validate_graph(
    nodes: dict[str, dict[str, Any]], graph: dict[str, set[str]]
) -> None:
    """Validate the built graph and raise GraphError on invalid structure."""
    for t_id, deps in graph.items():
        for dep_id in deps:
            if dep_id not in nodes:
                raise GraphError(
                    f"ERROR: '{t_id}' depends on '{dep_id}'"
                    f" but no .hurl file or alias defines id: {dep_id}"
                )

    try:
        sorter = TopologicalSorter(graph)
        sorter.prepare()
    except CycleError as exc:
        raise GraphError(f"Circular dependency detected: {exc}") from exc


def _instantiate_template(
    template_name: str,
    instance_name: str,
    templates: dict[str, dict[str, Any]],
    nodes: dict[str, dict[str, Any]],
    graph: dict[str, set[str]],
) -> None:
    if template_name not in templates:
        raise GraphError(
            "ERROR: alias template '"
            f"{template_name}' not found (used as '{instance_name}')"
        )
    if instance_name in nodes:
        return

    data = templates[template_name].copy()
    nodes[instance_name] = data
    graph[instance_name] = set()
    for dep in data["deps"]:
        if isinstance(dep, dict):
            for template_name, dep_instance_name in dep.items():
                _instantiate_template(
                    template_name,
                    dep_instance_name,
                    templates,
                    nodes,
                    graph,
                )
                graph[instance_name].add(dep_instance_name)
        else:
            graph[instance_name].add(dep)


def build_graph(
    hurl_paths: list[Path],
) -> tuple[dict[str, dict[str, Any]], dict[str, set[str]]]:
    """Parse .hurl frontmatter and build (nodes, graph)."""
    templates: dict[str, dict[str, Any]] = {}
    nodes: dict[str, dict[str, Any]] = {}
    graph: dict[str, set[str]] = {}

    for path in hurl_paths:
        with path.open() as f:
            post = frontmatter.load(f)
            t_id = _validate_identifier(
                post.get("id", path.stem),
                f"node id for {path.name}",
            )
            outputs = _parse_outputs(post.get("outputs", []), t_id)
            deps = _parse_deps(post.get("deps", []), t_id)
            priority = _parse_priority(post.get("priority", 0), t_id)
            hurl_args = _parse_args(post.get("args"), t_id)

            templates[t_id] = {
                "path": str(path),
                "content": post.content,
                "outputs": outputs,
                "deps": deps,
                "priority": priority,
                "hurl_args": hurl_args,
            }

    for t_id, data in templates.items():
        if t_id not in nodes:
            nodes[t_id] = data.copy()
            graph[t_id] = set()
        for dep in data["deps"]:
            if isinstance(dep, dict):
                for template_name, instance_name in dep.items():
                    _instantiate_template(
                        template_name,
                        instance_name,
                        templates,
                        nodes,
                        graph,
                    )
                    graph[t_id].add(instance_name)
            else:
                graph[t_id].add(dep)

    _validate_graph(nodes, graph)
    return nodes, graph


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
    shared_vars: dict[str, dict[str, Any]] = {}
    extra = extra_hurl_args or []

    if files is not None:
        hurl_paths: list[Path] = [Path(f) for f in files]
        if hurl_paths:
            test_dir = hurl_paths[0].parent
    else:
        hurl_paths = sorted(test_dir.glob("*.hurl"))

    global_args = get_global_args(test_dir)

    try:
        nodes, graph = build_graph(hurl_paths)
    except GraphError as exc:
        print(exc)
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
