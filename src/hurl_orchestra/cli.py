import argparse
import sys

from .orchestrator import run_hurl_orchestrator


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
    args, extra_hurl_args = parser.parse_known_args()

    paths: list[str] = args.paths
    if len(paths) == 1 and not paths[0].endswith(".hurl"):
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
