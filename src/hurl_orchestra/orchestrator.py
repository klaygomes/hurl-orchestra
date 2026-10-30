"""Core orchestration logic for hurl-orchestra."""

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from functools import lru_cache
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
DEFAULT_TIMEOUT_SECONDS = 300
TIMEOUT_GRACE_SECONDS = 5
MIN_HURL_VERSION = (7, 1, 0)
TESTED_HURL_VERSION = (8, 1, 0)
HURL_CONFIG_MIN_VERSION = (8, 1, 0)
EXIT_COMMANDLINE = 1
EXIT_PARSING = 2
EXIT_RUNTIME = 3

# Options that hurl-orchestra owns. Hurl rejects most of them when they appear
# twice, so a user-supplied copy must become a clear error instead.
RESERVED_HURL_FLAGS = {
    "--test": "hurl-orchestra always runs Hurl in test mode; remove it",
    "--report-json": "use --report-zip or --report-ctrf instead",
    "--secrets-file": "use the hurl-orchestra --secrets-file option instead",
}

_SAFE_NODE_ID = re.compile(r"^[A-Za-z0-9_.-]+$")
_FRONTMATTER_KEYS = {
    "id",
    "deps",
    "outputs",
    "priority",
    "args",
    "known_failures",
    "retry",
}

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
    return str(value)


def _validate_node_id(value: Any, description: str) -> str:
    """Validate an ID that is also used as a directory name."""
    value = _validate_identifier(value, description)
    if value in {".", ".."} or not _SAFE_NODE_ID.fullmatch(value):
        raise GraphError(
            f"ERROR: {description} must contain only letters, digits, '.', '_' "
            f"or '-', and must not be '.' or '..'; got {value!r}"
        )
    return str(value)


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
                _validate_node_id(
                    template_name,
                    f"alias template name for node '{t_id}'",
                )
                _validate_node_id(
                    instance_name,
                    f"alias instance name for node '{t_id}'",
                )
        elif isinstance(dep, str):
            _validate_node_id(dep, f"dependency id for node '{t_id}'")
        else:
            raise GraphError(
                f"ERROR: deps for '{t_id}' must contain strings or dicts; "
                f"got {type(dep).__name__}"
            )
        validated.append(dep)
    return validated


def _parse_priority(priority_value: Any, t_id: str) -> int:
    if isinstance(priority_value, bool) or not isinstance(priority_value, int):
        raise GraphError(
            f"ERROR: priority for '{t_id}' must be an integer; got {priority_value!r}"
        )
    return priority_value


def format_version(version: tuple[int, int, int]) -> str:
    """Return a version tuple as ``major.minor.patch``."""
    return ".".join(str(part) for part in version)


def _read_hurl_version() -> tuple[int, int, int] | None:
    """Run ``hurl --version`` and return the version, or None."""
    try:
        result = subprocess.run(
            ["hurl", "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = re.search(r"\bhurl (\d+)\.(\d+)\.(\d+)", result.stdout or "")
    if match is None:
        return None
    major, minor, patch = (int(part) for part in match.groups())
    return major, minor, patch


@lru_cache(maxsize=1)
def detect_hurl_version() -> tuple[int, int, int] | None:
    """Return the Hurl version on PATH, or None when it cannot be read."""
    return _read_hurl_version()


def check_hurl_version() -> tuple[bool, tuple[int, int, int] | None]:
    """Check the Hurl binary and return ``(usable, version)``."""
    if shutil.which("hurl") is None:
        print("ERROR: 'hurl' not found on PATH. Install it from https://hurl.dev")
        return False, None
    version = detect_hurl_version()
    if version is None:
        print(
            "WARNING: cannot read the hurl version. hurl-orchestra needs "
            f"Hurl {format_version(MIN_HURL_VERSION)} or later."
        )
        return True, None
    if version < MIN_HURL_VERSION:
        print(
            f"ERROR: hurl {format_version(version)} is too old; "
            f"hurl-orchestra needs {format_version(MIN_HURL_VERSION)} or "
            f"later ({format_version(TESTED_HURL_VERSION)} is tested)."
        )
        return False, version
    return True, version


def hurl_config_path(environ: Mapping[str, str] | None = None) -> Path | None:
    """Return the Hurl 8.1+ config file that applies to each call, if any."""
    env = os.environ if environ is None else environ
    if env.get("XDG_CONFIG_HOME"):
        base = Path(env["XDG_CONFIG_HOME"])
    else:
        home = env.get("HOME")
        base = Path(home) / ".config" if home else Path.home() / ".config"
    candidate = base / "hurl" / "config"
    return candidate if candidate.is_file() else None


def _flag_name(part: str) -> str:
    return part.split("=", 1)[0]


def reject_reserved_hurl_flags(args: list[str], where: str) -> None:
    """Raise GraphError when *args* contain an option hurl-orchestra owns."""
    for part in args:
        flag = _flag_name(part)
        if flag in RESERVED_HURL_FLAGS:
            raise GraphError(
                f"ERROR: {where}: {flag} is managed by hurl-orchestra; "
                f"{RESERVED_HURL_FLAGS[flag]}"
            )


def _has_max_time(args: list[str]) -> bool:
    """Whether the user passes Hurl's own ``--max-time`` option."""
    for part in args:
        if part in ("--max-time", "-m") or part.startswith("--max-time="):
            return True
        if part.startswith("-m") and not part.startswith("--") and len(part) > 2:
            return True
    return False


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
                _validate_identifier(key, f"argument name for node '{t_id}'")
                prefix = "-" if len(key) == 1 else "--"
                flat.extend([f"{prefix}{key}", str(value)])
        else:
            raise GraphError(
                f"ERROR: args for '{t_id}' must contain strings or dicts; "
                f"got {type(item).__name__}"
            )
    return flat


def _parse_hurl_args(args: Any, t_id: str) -> list[str]:
    """Parse the ``args`` field and reject flags that hurl-orchestra owns."""
    parsed = _parse_args(args, t_id)
    reject_reserved_hurl_flags(parsed, f"args for '{t_id}'")
    return parsed


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


def find_env_file(test_dir: Path, env_file: str | None = None) -> Path | None:
    """Return the variables file that every hurl call receives, if any.

    An explicit *env_file* wins. Otherwise it is ``.env`` in *test_dir*: the
    directory given on the command line, or the current directory when files
    are given.
    """
    if env_file is not None:
        return Path(env_file).expanduser().absolute()
    candidate = test_dir / ".env"
    return candidate.absolute() if candidate.exists() else None


def find_secrets_file(secrets_file: str | None = None) -> Path | None:
    """Return the secrets file that every hurl call receives, if any."""
    if secrets_file is None:
        return None
    return Path(secrets_file).expanduser().absolute()


def unused_env_files(files: list[str], chosen: Path | None) -> list[Path]:
    """Return ``.env`` files next to *files* that the run will not read."""
    parents = sorted({Path(f).parent for f in files})
    chosen_path = chosen.resolve() if chosen is not None else None
    return [
        parent / ".env"
        for parent in parents
        if (parent / ".env").exists() and (parent / ".env").resolve() != chosen_path
    ]


def get_global_args(test_dir: Path, env_file: str | None = None) -> list[str]:
    """Return hurl CLI arguments derived from global config in *test_dir*.

    Passes the variables file from :func:`find_env_file` via
    ``--variables-file``.
    """
    found = find_env_file(test_dir, env_file)
    return ["--variables-file", str(found)] if found is not None else []


def _collect_injected_variables(
    node_id: str, shared_vars: dict[str, dict[str, Any]], graph: Graph
) -> dict[str, Any]:
    injected: dict[str, Any] = {}
    for dep_id in graph.get(node_id, set()):
        for var_key, value in shared_vars.get(dep_id, {}).items():
            injected[_hurl_variable_name(dep_id, var_key)] = value
    return injected


def _property_line(name: str, value: Any) -> str:
    """Return one ``name=value`` line, rejecting line-breaking values."""
    text = str(value)
    if any(char in text for char in ("\n", "\r", "\x00")):
        raise ValueError(
            f"captured value for '{name}' contains a line break or NUL byte"
        )
    return f"{name}={text}\n"


def _write_variables_file(path: Path, variables: dict[str, Any]) -> None:
    """Write a Hurl variables file, rejecting line-breaking values."""
    path.write_text(
        "".join(_property_line(name, value) for name, value in variables.items()),
        encoding="utf-8",
    )


def _properties_entries(path: Path) -> list[tuple[str | None, str]]:
    """Return ``(name, line)`` pairs of a Hurl variables or secrets file."""
    entries: list[tuple[str | None, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            entries.append((None, line))
            continue
        name, separator, _ = line.partition("=")
        entries.append((name.strip() if separator else None, line))
    return entries


def _write_secrets_file(
    path: Path, global_path: Path | None, variables: dict[str, Any]
) -> None:
    """Write a secrets file where injected values override global secrets.

    Hurl rejects a secret name defined twice, so the global file and the
    captured values must become one file when both are present.
    """
    lines: list[str] = []
    if global_path is not None:
        for name, line in _properties_entries(global_path):
            if name is not None and name in variables:
                continue
            lines.append(f"{line}\n")
    lines.extend(_property_line(name, value) for name, value in variables.items())
    path.write_text("".join(lines), encoding="utf-8")


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
        link = f" ({known.failure.link})" if known.failure.link else ""
        return StepResult(
            "known_failure",
            f"KNOWN FAILURE: {node_id} [{known.failure.name}] "
            f"{known.failure.reason}{link}\n{detail}",
            known=known,
        )
    for failure in expired:
        until = failure.until.isoformat() if failure.until else ""
        message += f"known failure '{failure.name}' expired on {until}\n"
    return StepResult("failed", message)


def _run_hurl(
    node: dict[str, Any],
    cmd: list[str],
    timeout_seconds: int,
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
            timeout=timeout_seconds + TIMEOUT_GRACE_SECONDS,
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
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
    secrets_path: Path | None = None,
    inject_as_secrets: bool = True,
) -> StepResult:
    """Execute a single hurl node, injecting upstream variables and capturing outputs.

    A failure that matches one of the node's ``known_failures`` is reported as
    ``known_failure`` unless *strict* is set. A failure that matches the node's
    ``retry`` policy is attempted again after an exponential backoff. Captured
    values travel as Hurl secrets by default, so Hurl redacts them from its
    logs and reports. Set *inject_as_secrets* to false to send them through a
    variables file instead.
    """
    injected = _collect_injected_variables(node_id, shared_vars, graph)
    report_file = node_report_dir / "report.json"
    policy: RetryPolicy = node.get("retry") or RetryPolicy()
    node_args = node.get("hurl_args", [])
    user_args = [*extra_hurl_args, *node_args]
    cmd = ["hurl", "--test", *global_args]
    if not _has_max_time(user_args):
        cmd.extend(["--max-time", str(timeout_seconds)])
    cmd.extend([*user_args, "--report-json", str(node_report_dir)])

    notes: list[str] = []
    attempt = 1

    while True:
        # Injected values travel through a private file so captured secrets
        # never appear in the process list.
        with tempfile.TemporaryDirectory() as private_dir:
            attempt_cmd = list(cmd)
            if inject_as_secrets and injected:
                secrets_file = Path(private_dir) / "secrets.env"
                _write_secrets_file(secrets_file, secrets_path, injected)
                attempt_cmd.extend(["--secrets-file", str(secrets_file)])
            elif injected:
                variables_file = Path(private_dir) / "variables.env"
                _write_variables_file(variables_file, injected)
                attempt_cmd.extend(["--variables-file", str(variables_file)])
            if secrets_path is not None and not (inject_as_secrets and injected):
                attempt_cmd.extend(["--secrets-file", str(secrets_path)])

            outcome = _run_hurl(node, attempt_cmd, timeout_seconds)

        if outcome is None:
            detail = f"Hurl timed out after {timeout_seconds} seconds\n"
            returncode, stderr = EXIT_RUNTIME, detail
        else:
            returncode, stderr = outcome
            detail = stderr

        if returncode == 0:
            break

        if returncode == EXIT_COMMANDLINE:
            detail = "Hurl rejected the command line (exit code 1).\n" + detail
        elif returncode == EXIT_PARSING:
            detail = "Hurl could not parse the file (exit code 2).\n" + detail

        response = response_for(node_report_dir)
        retryable = returncode not in (EXIT_COMMANDLINE, EXIT_PARSING)
        if not retryable or not policy.should_retry(
            attempt, response, node_report_dir, stderr
        ):
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


def _node_report_dir(reports_path: Path, node_id: str) -> Path:
    """Return a per-node report directory inside *reports_path*."""
    root = reports_path.resolve()
    candidate = (root / node_id).resolve()
    if not candidate.is_relative_to(root):
        raise GraphError(
            f"ERROR: node id '{node_id}' resolves outside the report directory"
        )
    return candidate


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
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    max_workers: int = MAX_WORKERS,
    *,
    secrets_path: Path | None = None,
    inject_as_secrets: bool = True,
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
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
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

            report_dirs = {
                node_id: _node_report_dir(reports_path, node_id) for node_id in to_run
            }
            for report_dir in report_dirs.values():
                report_dir.mkdir(parents=True, exist_ok=True)

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
                        report_dirs[node_id],
                        strict,
                        timeout_seconds,
                        secrets_path=secrets_path,
                        inject_as_secrets=inject_as_secrets,
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
        existing_template = nodes[instance_name].get("template", instance_name)
        if existing_template != template_name:
            raise GraphError(
                f"ERROR: alias '{instance_name}' from template '{template_name}' "
                f"collides with a node from template '{existing_template}'"
            )
        return

    data = templates[template_name].copy()
    data["template"] = template_name
    nodes[instance_name] = data
    graph[instance_name] = set()
    for dep in data["deps"]:
        if isinstance(dep, dict):
            for dep_template_name, dep_instance_name in dep.items():
                _instantiate_template(
                    dep_template_name,
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
        try:
            with path.open() as f:
                post = frontmatter.load(f)
        except Exception as exc:
            raise GraphError(f"ERROR: cannot parse {path}: {exc}") from exc

        unknown = {str(key) for key in set(post.metadata) - _FRONTMATTER_KEYS}
        if unknown:
            raise GraphError(
                f"ERROR: {path.name} has unknown frontmatter keys: "
                f"{', '.join(sorted(unknown))}"
            )

        t_id = _validate_node_id(
            post.get("id", path.stem),
            f"node id for {path.name}",
        )
        if t_id in templates:
            existing = templates[t_id]["path"]
            raise GraphError(
                f"ERROR: duplicate node id '{t_id}' in {existing} and {path}"
            )
        templates[t_id] = {
            "path": str(path),
            "template": t_id,
            "content": post.content,
            "outputs": _parse_outputs(post.get("outputs", []), t_id),
            "deps": _parse_deps(post.get("deps", []), t_id),
            "priority": _parse_priority(post.get("priority", 0), t_id),
            "hurl_args": _parse_hurl_args(post.get("args"), t_id),
            "known_failures": _parse_known_failures(post.get("known_failures"), t_id),
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


def plan_waves(nodes: Nodes, graph: Graph) -> list[list[str]]:
    """Return the node ids of each wave, in execution order."""
    sorter = TopologicalSorter(graph)
    sorter.prepare()
    waves: list[list[str]] = []
    while sorter.is_active():
        ready = _ready_by_priority(sorter, nodes)
        waves.append(ready)
        sorter.done(*ready)
    return waves


def plan_document(
    nodes: Nodes,
    graph: Graph,
    resolved: list[str] | None = None,
    env_file: Path | None = None,
    secrets_file: Path | None = None,
    hurl_config: Path | None = None,
) -> dict[str, Any]:
    """Describe the execution plan as a JSON-serialisable document."""
    return {
        "ok": True,
        "env_file": str(env_file) if env_file is not None else None,
        "secrets_file": str(secrets_file) if secrets_file is not None else None,
        "hurl_config": str(hurl_config) if hurl_config is not None else None,
        "resolved": resolved or [],
        "waves": plan_waves(nodes, graph),
        "nodes": [
            {
                "id": node_id,
                "file": node["path"],
                "deps": sorted(graph.get(node_id, set())),
                "outputs": node.get("outputs", []),
                "variables": sorted(
                    _hurl_variable_name(dep_id, output)
                    for dep_id in graph.get(node_id, set())
                    for output in nodes[dep_id].get("outputs", [])
                ),
                "priority": node["priority"],
                "known_failures": [f.name for f in node.get("known_failures", [])],
                "retry_attempts": (node.get("retry") or RetryPolicy()).attempts,
            }
            for node_id, node in sorted(nodes.items())
        ],
    }


def _print_plan(nodes: Nodes, graph: Graph) -> None:
    print(f"Plan: {len(nodes)} node(s)")
    for index, ready in enumerate(plan_waves(nodes, graph), start=1):
        print(f"  wave {index}: {', '.join(ready)}")


def resolve_files(
    requested: list[Path], resolve_deps: bool = True
) -> tuple[Nodes, Graph, list[str]]:
    """Build the graph of *requested* files and return the ids pulled in as deps.

    With *resolve_deps* the declared ``deps`` are located among sibling
    ``.hurl`` files; otherwise every dependency must be in *requested*.
    """
    missing = [str(path) for path in requested if not path.is_file()]
    if missing:
        raise GraphError(f"ERROR: .hurl file not found: {', '.join(missing)}")
    if not resolve_deps:
        nodes, graph = build_graph(requested)
        return nodes, graph, []

    templates = load_templates(_discover_siblings(requested))
    nodes, graph = link_templates(templates)
    roots = _requested_ids(templates, requested)
    nodes, graph = select_closure(nodes, graph, roots)
    return nodes, graph, sorted(set(nodes) - roots)


def _resolve_nodes(
    test_dir: Path, files: list[str] | None, resolve_deps: bool
) -> tuple[Nodes, Graph, list[str]]:
    if files is None:
        nodes, graph = build_graph(sorted(test_dir.glob("*.hurl")))
        return nodes, graph, []
    return resolve_files([Path(f) for f in files], resolve_deps)


def _write_reports(
    nodes: Nodes,
    reports_root: Path,
    test_dir: Path,
    report_ctrf: str | None,
    report_zip: str,
    start_ms: int,
    stop_ms: int,
    outcome: RunOutcome,
) -> bool:
    """Write the CTRF report and the zip archive. Return False on a zip error."""
    if report_ctrf is not None:
        ctrf_path = (
            Path(report_ctrf)
            if Path(report_ctrf).is_absolute()
            else test_dir / Path(report_ctrf)
        )
        try:
            write_ctrf(
                list(nodes.keys()),
                reports_root,
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
    try:
        archive = shutil.make_archive(zip_base, "zip", reports_root)
    except OSError as exc:
        print(f"ERROR: Failed to write report archive: {exc}")
        return False
    print(f"Report saved to {archive}")
    return True


def _print_run_error(message: str, json_plan: bool) -> None:
    if json_plan:
        print(json.dumps({"ok": False, "error": message}, indent=2))
    else:
        print(message)


def _print_run_context(
    variables_file: Path | None,
    files: list[str] | None,
    env_file: str | None,
    pulled: list[str],
    secrets_file: Path | None = None,
    hurl_config: Path | None = None,
) -> None:
    if variables_file is not None:
        print(f"Variables file: {variables_file}")
    if secrets_file is not None:
        print(f"Secrets file: {secrets_file}")
    if hurl_config is not None:
        print(f"Hurl config: {hurl_config}")
    if files is not None and env_file is None:
        for unused in unused_env_files(files, variables_file):
            print(
                f"NOTE: hurl-orchestra does not read {unused} when you give "
                "files. It reads .env from the current directory. Add "
                f"--env-file {unused} to read it."
            )
    if pulled:
        print(f"Resolved dependencies: {', '.join(pulled)}")


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
    json_plan: bool = False,
    env_file: str | None = None,
    secrets_file: str | None = None,
    inject_as_variables: bool = False,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    jobs: int | None = None,
) -> bool:
    """Discover, order, and execute ``.hurl`` files in dependency order.

    When *files* is provided those specific files are run.  With *resolve_deps*
    enabled (the default) their declared ``deps`` are located among sibling
    ``.hurl`` files and executed first; otherwise every dependency must be
    listed explicitly.  Any *extra_hurl_args* are forwarded verbatim to every
    hurl invocation, allowing flags like ``--verbose`` or ``--variable key=val``.
    With *dry_run* the execution plan is printed and nothing is executed; with
    *json_plan* as well, the plan (or the graph error) is printed as JSON.
    Every hurl call receives *env_file*, or else ``.env`` from *test_dir*, as
    ``--variables-file``. Values captured by upstream nodes reach Hurl as
    secrets, so Hurl redacts them from its logs and reports; set
    *inject_as_variables* to send them through a variables file instead.
    *secrets_file* gives user-defined secrets to every call.
    With *strict* a failure matching a node's ``known_failures`` still fails the
    run.  After execution a zip archive of all hurl reports is written to
    *report_zip* relative to *test_dir*.  *timeout_seconds* limits each Hurl
    process, and *jobs* limits parallel Hurl processes.

    Returns ``True`` if every step succeeded or was a tolerated known failure,
    ``False`` otherwise.
    """
    if timeout_seconds < 1:
        print("ERROR: timeout must be at least 1 second")
        return False
    if jobs is not None and jobs < 1:
        print("ERROR: jobs must be at least 1")
        return False

    hurl_version: tuple[int, int, int] | None = None
    if not dry_run:
        usable, hurl_version = check_hurl_version()
        if not usable:
            return False

    test_dir = Path(test_dir_str)
    shared_vars: dict[str, dict[str, Any]] = {}
    extra = extra_hurl_args or []
    variables_file = find_env_file(test_dir, env_file)
    secrets_path = find_secrets_file(secrets_file)
    hurl_config = hurl_config_path()
    if (
        not dry_run
        and hurl_config is not None
        and (hurl_version is None or hurl_version < HURL_CONFIG_MIN_VERSION)
    ):
        hurl_config = None
    global_args = get_global_args(test_dir, env_file)

    try:
        reject_reserved_hurl_flags(extra, "the Hurl flags after --")
        if variables_file is not None and not variables_file.is_file():
            raise GraphError(f"ERROR: env file not found: {variables_file}")
        if secrets_path is not None and not secrets_path.is_file():
            raise GraphError(f"ERROR: secrets file not found: {secrets_path}")
        nodes, graph, pulled = _resolve_nodes(test_dir, files, resolve_deps)
    except GraphError as exc:
        _print_run_error(str(exc), dry_run and json_plan)
        return False

    if not nodes:
        _print_run_error(
            f"ERROR: no .hurl files found in {test_dir}", dry_run and json_plan
        )
        return False

    if dry_run and json_plan:
        document = plan_document(
            nodes, graph, pulled, variables_file, secrets_path, hurl_config
        )
        print(json.dumps(document, indent=2))
        return True

    _print_run_context(
        variables_file, files, env_file, pulled, secrets_path, hurl_config
    )

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
                timeout_seconds,
                jobs or MAX_WORKERS,
                secrets_path=secrets_path,
                inject_as_secrets=not inject_as_variables,
            )
        except CycleError as exc:
            print(f"Circular dependency: {exc}")
            return False
        except GraphError as exc:
            print(exc)
            return False
        stop_ms = int(time.time() * 1000)
        _print_tolerated_summary(outcome.tolerated)
        if not _write_reports(
            nodes,
            Path(reports_root),
            test_dir,
            report_ctrf,
            report_zip,
            start_ms,
            stop_ms,
            outcome,
        ):
            return False

    return outcome.success
