# Reference

The reference gives the names, types and default values of each option and field.

## Parts of the reference

- [Command line](/reference/cli) shows each option of `hurl-orchestra` and the JSON plan.
- [Frontmatter](/reference/frontmatter) shows each field that a `.hurl` file can declare.
- [Console output](/reference/console-output) shows each line that a run can write.
- [CTRF report](/reference/ctrf) shows how a run becomes CTRF tests.

## Requirements

| Item | Version |
|---|---|
| Python | 3.11 or later |
| Hurl | A version with `--report-json` and `--variables-file` on the `PATH` |
| System | Linux, macOS or Windows |

## Exit codes

| Code | Description |
|---|---|
| `0` | All nodes passed, or the failures matched `known_failures`. |
| `1` | A node failed, the graph is not valid, or Hurl is not on the `PATH`. |
| `2` | The command line is not valid. |
