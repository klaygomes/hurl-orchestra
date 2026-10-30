# Reference

The reference gives the names, types and default values of each option and field.

## Parts of the reference

- [Command line](/reference/cli) shows each option of `hurl-orchestra` and the JSON plan.
- [Frontmatter](/reference/frontmatter) shows each field that a `.hurl` file can declare.
- [Console output](/reference/console-output) shows each line that a run can write.
- [CTRF report](/reference/ctrf) shows how a run becomes CTRF tests.
- [Hurl compatibility](/reference/hurl-compatibility) shows the supported versions and the Hurl options that hurl-orchestra uses.

## Requirements

| Item | Version |
|---|---|
| Python | 3.11 or later |
| Hurl | 7.1.0 or later on the `PATH`. The tests run with 7.1.0 and 8.1.0. |
| System | Linux, macOS or Windows |

## Exit codes

| Code | Description |
|---|---|
| `0` | All nodes passed, or the failures matched `known_failures`. |
| `1` | A node failed, the graph is not valid, or Hurl is not on the `PATH`. |
| `2` | The command line is not valid. |
