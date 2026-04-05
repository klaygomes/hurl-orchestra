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


def main() -> None:
    """Entry point for the ``hurl-orchestra`` CLI command."""
    parser = argparse.ArgumentParser(
        prog="hurl-orchestra",
        description="Run hurl test files in dependency order.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        default=["."],
        help=(
            "Directory containing .hurl files, or one or more .hurl files to run"
            " (default: current directory)"
        ),
    )
    parser.add_argument(
        "--report-zip",
        default="report.zip",
        metavar="FILE",
        help="Save all hurl reports to this zip file (default: report.zip)",
    )
    parser.add_argument(
        "--diagram",
        action="store_true",
        help=(
            "Generate a Mermaid diagram of the dependency graph"
            " instead of running tests."
        ),
    )
    parser.add_argument(
        "--diagram-output",
        default="diagram.md",
        metavar="FILE",
        help="Output file for the diagram (default: diagram.md). Use '-' for stdout.",
    )
    parser.add_argument(
        "--diagram-overwrite",
        action="store_true",
        help="Overwrite diagram output if it already exists.",
    )
    args, extra_hurl_args = parser.parse_known_args()

    paths: list[str] = args.paths

    if args.diagram:
        ok = write_diagram(
            _resolve_hurl_paths(paths),
            output=args.diagram_output,
            overwrite=args.diagram_overwrite,
        )
    elif len(paths) == 1 and not paths[0].endswith(".hurl"):
        ok = run_hurl_orchestrator(
            paths[0], extra_hurl_args=extra_hurl_args, report_zip=args.report_zip
        )
    else:
        ok = run_hurl_orchestrator(
            files=paths, extra_hurl_args=extra_hurl_args, report_zip=args.report_zip
        )

    if not ok:
        sys.exit(1)


if __name__ == "__main__":  # pragma: no cover
    main()
