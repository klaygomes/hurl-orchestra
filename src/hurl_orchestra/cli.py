import argparse
import sys
from pathlib import Path

from .orchestrator import run_hurl_orchestrator
from .visualize import write_diagram


def _resolve_hurl_paths(paths: list[str]) -> list[Path]:
    """Resolve CLI paths to a sorted list of .hurl files."""
    if len(paths) == 1 and not paths[0].endswith(".hurl"):
        return sorted(Path(paths[0]).glob("*.hurl"))
    return [Path(p) for p in paths]


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser of the ``hurl-orchestra`` CLI command."""
    parser = argparse.ArgumentParser(
        prog="hurl-orchestra",
        description="Run hurl test files in dependency order.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        default=["."],
        help=(
            "A directory with .hurl files, or one or more .hurl files."
            " The default is the current directory."
        ),
    )
    parser.add_argument(
        "--report-zip",
        default="report.zip",
        metavar="FILE",
        help="Write the hurl reports of all nodes to this zip file.",
    )
    parser.add_argument(
        "--report-ctrf",
        default=None,
        metavar="FILE",
        help="Also write a CTRF JSON report to this file.",
    )
    parser.add_argument(
        "--env-file",
        default=None,
        metavar="FILE",
        help=(
            "Give this variables file to each hurl call. The default is .env in"
            " the given directory, or in the current directory for files."
        ),
    )
    parser.add_argument(
        "--no-deps",
        dest="resolve_deps",
        action="store_false",
        help=(
            "Run only the listed .hurl files. Do not add their declared deps"
            " from the same directory."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the execution plan. Do not run hurl.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="With --dry-run, write the plan as JSON for scripts and AI agents.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Make a failure that matches known_failures fail the run.",
    )
    parser.add_argument(
        "--diagram",
        action="store_true",
        help="Write a Mermaid diagram of the graph. Do not run the tests.",
    )
    parser.add_argument(
        "--diagram-output",
        default="diagram.md",
        metavar="FILE",
        help="Write the diagram to this file. Use '-' for stdout.",
    )
    parser.add_argument(
        "--diagram-overwrite",
        action="store_true",
        help="Replace the diagram file if it exists.",
    )
    return parser


def main() -> None:
    """Entry point for the ``hurl-orchestra`` CLI command."""
    parser = build_parser()
    raw = sys.argv[1:]
    if "--" in raw:
        idx = raw.index("--")
        own_args, passthrough = raw[:idx], raw[idx + 1 :]
    else:
        own_args, passthrough = raw, []

    args, leftover = parser.parse_known_args(own_args)
    if args.json and not args.dry_run:
        parser.error("--json needs --dry-run")
    extra_hurl_args = leftover + passthrough

    paths: list[str] = args.paths

    directory_mode = len(paths) == 1 and not paths[0].endswith(".hurl")

    if args.diagram:
        ok = write_diagram(
            _resolve_hurl_paths(paths),
            output=args.diagram_output,
            overwrite=args.diagram_overwrite,
            resolve_deps=args.resolve_deps and not directory_mode,
        )
    elif directory_mode:
        ok = run_hurl_orchestrator(
            paths[0],
            extra_hurl_args=extra_hurl_args,
            report_zip=args.report_zip,
            report_ctrf=args.report_ctrf,
            resolve_deps=args.resolve_deps,
            dry_run=args.dry_run,
            strict=args.strict,
            json_plan=args.json,
            env_file=args.env_file,
        )
    else:
        ok = run_hurl_orchestrator(
            files=paths,
            extra_hurl_args=extra_hurl_args,
            report_zip=args.report_zip,
            report_ctrf=args.report_ctrf,
            resolve_deps=args.resolve_deps,
            dry_run=args.dry_run,
            strict=args.strict,
            json_plan=args.json,
            env_file=args.env_file,
        )

    if not ok:
        sys.exit(1)


if __name__ == "__main__":  # pragma: no cover
    main()
