"""Core orchestration logic for hurl-orchestra."""

import json
import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from graphlib import CycleError, TopologicalSorter
from pathlib import Path
from typing import Any, Literal

import frontmatter

from .ctrf import write_ctrf
from .known_failures import (
    KnownFailure,
    KnownFailureError,
    KnownFailureMatch,
    match_known_failure,
    parse_known_failures,
)
from .retry import RetryError, RetryPolicy, parse_retry, response_for


class GraphError(Exception):
    """Raised when graph construction or validation fails."""


MAX_WORKERS = min(32, (os.cpu_count() or 1) + 4)

Nodes = dict[str, dict[str, Any]]
Graph = dict[str, set[str]]

StepStatus = Literal["passed", "failed", "known_failure"]


@dataclass
class StepResult:
    status: StepStatus
    message: str
    captures: dict[str, Any] = field(default_factory=dict)
    known: KnownFailureMatch | None = None


@dataclass
class RunOutcome:
    success: bool
    tolerated: dict[str, KnownFailureMatch]
    skipped_known: dict[str, str]


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


def _parse_known_failures(raw: Any, t_id: str) -> list[KnownFailure]:
    try:
        return parse_known_failures(raw, t_id)
    except KnownFailureError as err:
        raise GraphError(str(err)) from err


def _parse_retry(raw: Any, t_id: str) -> RetryPolicy:
    try:
        return parse_retry(raw, t_id)
    except RetryError as err:
        raise GraphError(str(err)) from err


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


def _collect_injected_variables(
    node_id: str, shared_vars: dict[str, dict[str, Any]], graph: Graph
) -> dict[str, Any]:
    injected: dict[str, Any] = {}
    for dep_id in graph.get(node_id, set()):
        for var_key, value in shared_vars.get(dep_id, {}).items():
            injected[_hurl_variable_name(dep_id, var_key)] = value
    return injected


def _failure(
    node_id: str,
    node: dict[str, Any],
    detail: str,
    node_report_dir: Path,
    strict: bool,
) -> StepResult:
    message = f"FAILED: {node_id}\n{detail}"
    if strict:
        return StepResult("failed", message)
    known, expired = match_known_failure(
        node.get("known_failures", []), node_report_dir, detail
    )
    if known is not None:
        return StepResult(
            "known_failure",
            f"KNOWN FAILURE: {node_id} [{known.failure.name}] "
            f"{known.failure.reason}\n{detail}",
            known=known,
        )
    for failure in expired:
        until = failure.until.isoformat() if failure.until else ""
        message += f"known failure '{failure.name}' expired on {until}\n"
    return StepResult("failed", message)


def _run_hurl(
    node: dict[str, Any],
    cmd: list[str],
) -> tuple[int, str] | None:
    """Run hurl once. Returns (returncode, stderr), or None on timeout."""
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
        return None
    return result.returncode, result.stderr


def _reset_report_dir(node_report_dir: Path) -> None:
    """Leave only the final attempt's report behind.

    hurl appends to report.json, so without this a retried node would carry its
    earlier attempts into the CTRF report and show failures it recovered from.
    """
    shutil.rmtree(node_report_dir, ignore_errors=True)
    node_report_dir.mkdir(parents=True, exist_ok=True)


def run_step(
    node_id: str,
    node: dict[str, Any],
    shared_vars: dict[str, dict[str, Any]],
    graph: Graph,
    global_args: list[str],
    extra_hurl_args: list[str],
    node_report_dir: Path,
    strict: bool = False,
    sleep: Callable[[float], None] = time.sleep,
) -> StepResult:
    """Execute a single hurl node, injecting upstream variables and capturing outputs.

    A failure that matches one of the node's ``known_failures`` is reported as
    ``known_failure`` unless *strict* is set. A failure that matches the node's
    ``retry`` policy is attempted again after an exponential backoff.
    """
    injected = _collect_injected_variables(node_id, shared_vars, graph)
    report_file = node_report_dir / "report.json"
    policy: RetryPolicy = node.get("retry") or RetryPolicy()
    cmd = [
        "hurl",
        "--test",
        *global_args,
        *extra_hurl_args,
        *node.get("hurl_args", []),
        "--report-json",
        str(node_report_dir),
    ]

    notes: list[str] = []
    attempt = 1

    while True:
        # Injected values travel through a private file so captured secrets
        # never appear in the process list.
        with tempfile.TemporaryDirectory() as private_dir:
            attempt_cmd = list(cmd)
            if injected:
                variables_file = Path(private_dir) / "variables.env"
                variables_file.write_text(
                    "".join(f"{name}={value}\n" for name, value in injected.items())
                )
                attempt_cmd.extend(["--variables-file", str(variables_file)])

            outcome = _run_hurl(node, attempt_cmd)

        if outcome is None:
            detail = "Hurl timed out after 300 seconds\n"
            returncode, stderr = 1, detail
        else:
            returncode, stderr = outcome
            detail = stderr

        if returncode == 0:
            break

        response = response_for(node_report_dir)
        if not policy.should_retry(attempt, response, node_report_dir, stderr):
            return _failure(
                node_id, node, "".join(notes) + detail, node_report_dir, strict
            )

        delay_ms = policy.delay_ms(attempt, response)
        status = (
            "no response" if response is None else f"status {response.get('status')}"
        )
        notes.append(
            f"RETRY: {node_id} attempt {attempt}/{policy.attempts} failed "
            f"({status}), waiting {delay_ms}ms\n"
        )
        sleep(delay_ms / 1000)
        attempt += 1
        _reset_report_dir(node_report_dir)

    captures = extract_captures(report_file, node.get("outputs", []), node_id)
    outputs: list[str] = node.get("outputs") or []
    missed = [o for o in outputs if o not in captures]
    if missed:
        actual = ", ".join(sorted(captures.keys())) or "none"
        return StepResult(
            "failed",
            (
                f"FAILED: {node_id}\nMissing expected outputs: {', '.join(missed)}; "
                f"reported outputs: {actual}\n"
            ),
        )

    parts: list[str] = []
    if injected:
        parts.append(f"injected: {', '.join(injected)}")
    if captures:
        parts.append(f"captured: {', '.join(captures)}")
    if attempt > 1:
        parts.append(f"{attempt} attempts")
    suffix = f" [{' | '.join(parts)}]" if parts else ""
    return StepResult(
        "passed", "".join(notes) + f"SUCCESS: {node_id}{suffix}\n", captures
    )


def _ready_by_priority(sorter: TopologicalSorter[str], nodes: Nodes) -> list[str]:
    return sorted(
        sorter.get_ready(),
        key=lambda nid: nodes[nid]["priority"],
        reverse=True,
    )


def _skip_unrunnable(
    node_id: str,
    graph: Graph,
    failed_nodes: set[str],
    tolerated_nodes: set[str],
    skipped_known: dict[str, str],
) -> bool:
    deps = graph.get(node_id, set())
    failed_deps = sorted(dep for dep in deps if dep in failed_nodes)
    if failed_deps:
        failed_nodes.add(node_id)
        print(f"SKIPPED: {node_id} (failed dependency: {', '.join(failed_deps)})")
        return True
    known_deps = sorted(dep for dep in deps if dep in tolerated_nodes)
    if known_deps:
        tolerated_nodes.add(node_id)
        skipped_known[node_id] = ", ".join(known_deps)
        print(f"SKIPPED: {node_id} (known failure upstream: {', '.join(known_deps)})")
        return True
    return False


def _execute(
    nodes: Nodes,
    graph: Graph,
    shared_vars: dict[str, dict[str, Any]],
    global_args: list[str],
    extra: list[str],
    reports_path: Path,
    strict: bool = False,
) -> RunOutcome:
    """Run nodes in topological order, writing each report to *reports_path*.

    Raises ``CycleError`` if a dependency cycle is detected. A node whose
    failure matches one of its ``known_failures`` does not fail the run; its
    dependents are skipped without failing it either.
    """
    sorter = TopologicalSorter(graph)
    sorter.prepare()
    failed_nodes: set[str] = set()
    tolerated_nodes: set[str] = set()
    tolerated: dict[str, KnownFailureMatch] = {}
    skipped_known: dict[str, str] = {}
    overall_success = True
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        while sorter.is_active():
            to_run: list[str] = []
            for node_id in _ready_by_priority(sorter, nodes):
                if _skip_unrunnable(
                    node_id, graph, failed_nodes, tolerated_nodes, skipped_known
                ):
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
                        strict,
                    ): node_id
                    for node_id in group
                }
                results: dict[str, StepResult] = {}
                for future in futures:
                    node_id = futures[future]
                    try:
                        results[node_id] = future.result()
                    except Exception as exc:
                        results[node_id] = StepResult(
                            "failed", f"FAILED: {node_id}\n{exc}\n"
                        )

                for node_id in group:
                    step = results[node_id]
                    print(step.message, end="")
                    if step.status == "failed":
                        overall_success = False
                        failed_nodes.add(node_id)
                    elif step.status == "known_failure" and step.known is not None:
                        tolerated_nodes.add(node_id)
                        tolerated[node_id] = step.known
                    elif step.captures:
                        shared_vars[node_id] = step.captures
                    sorter.done(node_id)
    return RunOutcome(overall_success, tolerated, skipped_known)


def _print_tolerated_summary(tolerated: dict[str, KnownFailureMatch]) -> None:
    if not tolerated:
        return
    by_name: dict[str, list[str]] = {}
    for node_id in sorted(tolerated):
        by_name.setdefault(tolerated[node_id].failure.name, []).append(node_id)
    groups = "; ".join(f"{name}: {', '.join(ids)}" for name, ids in by_name.items())
    print(f"Known failures tolerated: {len(tolerated)} ({groups})")


def _validate_graph(nodes: Nodes, graph: Graph) -> None:
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
    templates: Nodes,
    nodes: Nodes,
    graph: Graph,
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


def load_templates(hurl_paths: list[Path]) -> Nodes:
    """Parse .hurl frontmatter into templates keyed by node id."""
    templates: Nodes = {}
    for path in hurl_paths:
        with path.open() as f:
            post = frontmatter.load(f)
            t_id = _validate_identifier(
                post.get("id", path.stem),
                f"node id for {path.name}",
            )
            templates[t_id] = {
                "path": str(path),
                "content": post.content,
                "outputs": _parse_outputs(post.get("outputs", []), t_id),
                "deps": _parse_deps(post.get("deps", []), t_id),
                "priority": _parse_priority(post.get("priority", 0), t_id),
                "hurl_args": _parse_args(post.get("args"), t_id),
                "known_failures": _parse_known_failures(
                    post.get("known_failures"), t_id
                ),
                "retry": _parse_retry(post.get("retry"), t_id),
            }
    return templates


def link_templates(templates: Nodes) -> tuple[Nodes, Graph]:
    """Instantiate aliases and build the validated (nodes, graph) pair."""
    nodes: Nodes = {}
    graph: Graph = {}

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


def build_graph(hurl_paths: list[Path]) -> tuple[Nodes, Graph]:
    """Parse .hurl frontmatter and build (nodes, graph)."""
    return link_templates(load_templates(hurl_paths))


def select_closure(nodes: Nodes, graph: Graph, roots: set[str]) -> tuple[Nodes, Graph]:
    """Restrict (nodes, graph) to *roots* and everything they transitively depend on."""
    selected: set[str] = set()
    pending = list(roots)
    while pending:
        node_id = pending.pop()
        if node_id in selected:
            continue
        selected.add(node_id)
        pending.extend(graph[node_id])
    return (
        {nid: data for nid, data in nodes.items() if nid in selected},
        {nid: deps for nid, deps in graph.items() if nid in selected},
    )


def _discover_siblings(requested: list[Path]) -> list[Path]:
    parents = {path.parent for path in requested}
    return sorted({path for parent in parents for path in parent.glob("*.hurl")})


def _requested_ids(templates: Nodes, requested: list[Path]) -> set[str]:
    wanted = {path.resolve() for path in requested}
    return {
        t_id
        for t_id, data in templates.items()
        if Path(data["path"]).resolve() in wanted
    }


def _print_plan(nodes: Nodes, graph: Graph) -> None:
    sorter = TopologicalSorter(graph)
    sorter.prepare()
    print(f"Plan: {len(nodes)} node(s)")
    wave = 0
    while sorter.is_active():
        wave += 1
        ready = _ready_by_priority(sorter, nodes)
        print(f"  wave {wave}: {', '.join(ready)}")
        sorter.done(*ready)


def _resolve_nodes(
    test_dir: Path, files: list[str] | None, resolve_deps: bool
) -> tuple[Nodes, Graph]:
    if files is None:
        return build_graph(sorted(test_dir.glob("*.hurl")))

    requested = [Path(f) for f in files]
    missing = [str(path) for path in requested if not path.is_file()]
    if missing:
        raise GraphError(f"ERROR: .hurl file not found: {', '.join(missing)}")
    if not resolve_deps:
        return build_graph(requested)

    templates = load_templates(_discover_siblings(requested))
    nodes, graph = link_templates(templates)
    roots = _requested_ids(templates, requested)
    nodes, graph = select_closure(nodes, graph, roots)
    pulled = sorted(set(nodes) - roots)
    if pulled:
        print(f"Resolved dependencies: {', '.join(pulled)}")
    return nodes, graph


def run_hurl_orchestrator(
    test_dir_str: str = ".",
    *,
    files: list[str] | None = None,
    extra_hurl_args: list[str] | None = None,
    report_zip: str = "report.zip",
    report_ctrf: str | None = None,
    resolve_deps: bool = True,
    dry_run: bool = False,
    strict: bool = False,
) -> bool:
    """Discover, order, and execute ``.hurl`` files in dependency order.

    When *files* is provided those specific files are run.  With *resolve_deps*
    enabled (the default) their declared ``deps`` are located among sibling
    ``.hurl`` files and executed first; otherwise every dependency must be
    listed explicitly.  Any *extra_hurl_args* are forwarded verbatim to every
    hurl invocation, allowing flags like ``--verbose`` or ``--variable key=val``.
    With *dry_run* the execution plan is printed and nothing is executed.
    With *strict* a failure matching a node's ``known_failures`` still fails the
    run.  After execution a zip archive of all hurl reports is written to
    *report_zip* in the current working directory.

    Returns ``True`` if every step succeeded or was a tolerated known failure,
    ``False`` otherwise.
    """
    if not dry_run and shutil.which("hurl") is None:
        print("ERROR: 'hurl' not found on PATH. Install it from https://hurl.dev")
        return False

    test_dir = Path(test_dir_str)
    shared_vars: dict[str, dict[str, Any]] = {}
    extra = extra_hurl_args or []
    global_args = get_global_args(test_dir)

    try:
        nodes, graph = _resolve_nodes(test_dir, files, resolve_deps)
    except GraphError as exc:
        print(exc)
        return False

    if dry_run:
        _print_plan(nodes, graph)
        return True

    with tempfile.TemporaryDirectory() as reports_root:
        start_ms = int(time.time() * 1000)
        try:
            outcome = _execute(
                nodes,
                graph,
                shared_vars,
                global_args,
                extra,
                Path(reports_root),
                strict,
            )
        except CycleError as e:
            print(f"Circular dependency: {e}")
            return False
        stop_ms = int(time.time() * 1000)
        _print_tolerated_summary(outcome.tolerated)

        if report_ctrf is not None:
            ctrf_path = (
                Path(report_ctrf)
                if Path(report_ctrf).is_absolute()
                else test_dir / Path(report_ctrf)
            )
            try:
                write_ctrf(
                    list(nodes.keys()),
                    Path(reports_root),
                    ctrf_path,
                    start_ms,
                    stop_ms,
                    tolerated=outcome.tolerated,
                    skipped_known=outcome.skipped_known,
                )
                print(f"CTRF report saved to {ctrf_path}")
            except OSError as exc:
                print(f"WARNING: Failed to write CTRF report: {exc}")

        report_path = Path(report_zip)
        if report_path.is_absolute():
            zip_base = str(report_path.with_suffix(""))
        else:
            zip_base = str(test_dir / report_path.with_suffix(""))
        archive = shutil.make_archive(zip_base, "zip", reports_root)
        print(f"Report saved to {archive}")

    return outcome.success
