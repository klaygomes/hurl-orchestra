import argparse

from .orchestrator import run_hurl_orchestrator


def main() -> None:
    """Entry point for the ``hurl-orchestra`` CLI command."""
    parser = argparse.ArgumentParser(
        prog="hurl-orchestra",
        description="Run hurl test files in dependency order.",
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory containing .hurl files (default: current directory)",
    )
    args = parser.parse_args()
    run_hurl_orchestrator(args.directory)


if __name__ == "__main__":  # pragma: no cover
    main()
