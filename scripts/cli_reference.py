"""Write the CLI option table of the documentation from the argument parser."""

import argparse
from pathlib import Path

from hurl_orchestra.cli import build_parser

OUTPUT = Path(__file__).resolve().parent.parent / "docs/reference/cli.generated.md"


def _name(action: argparse.Action) -> str:
    if not action.option_strings:
        return f"`{action.dest}`"
    flags = ", ".join(f"`{flag}`" for flag in action.option_strings)
    return f"{flags} `{action.metavar}`" if action.metavar else flags


def _default(action: argparse.Action) -> str:
    if action.nargs == 0 or action.default is None:
        return "-"
    if isinstance(action.default, list):
        return ", ".join(f"`{value}`" for value in action.default)
    return f"`{action.default}`"


def render(parser: argparse.ArgumentParser) -> str:
    rows = [
        "| Option | Default | Description |",
        "|---|---|---|",
    ]
    for action in parser._actions:
        if isinstance(action, argparse._HelpAction):
            continue
        rows.append(f"| {_name(action)} | {_default(action)} | {action.help} |")
    return "\n".join(rows) + "\n"


def main() -> None:
    OUTPUT.write_text(render(build_parser()))


if __name__ == "__main__":
    main()
