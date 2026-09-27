# Command line

```text
hurl-orchestra [options] [paths ...] [-- hurl options ...]
```

## Options

<!--@include: ./cli.generated.md-->

A script makes this table from the parser of the command. Thus the table and `hurl-orchestra --help` always agree.

## Paths

| Paths | Mode |
|---|---|
| None | Directory mode on the current directory. |
| One path that does not end in `.hurl` | Directory mode on that directory. |
| One or more `.hurl` files | File mode. hurl-orchestra adds the dependencies from the same directories. |

## Hurl options

Put Hurl options after `--`. hurl-orchestra gives them to each Hurl call. For more information, read [Give flags to Hurl](/how-to/pass-hurl-flags).

hurl-orchestra always gives these options to Hurl: `--test`, `--report-json` and, if a variables file applies, `--variables-file`.

## JSON plan

`hurl-orchestra --dry-run --json` writes one JSON document to stdout:

```json
{
  "ok": true,
  "env_file": "tests/.env",
  "resolved": ["add_item", "auth", "create_cart"],
  "waves": [["auth"], ["create_cart"], ["add_item"], ["checkout"]],
  "nodes": [
    {
      "id": "add_item",
      "file": "tests/add_item.hurl",
      "deps": ["auth", "create_cart"],
      "outputs": [],
      "variables": ["auth_token", "create_cart_cart_id"],
      "priority": 0,
      "known_failures": [],
      "retry_attempts": 1
    }
  ]
}
```

| Field | Description |
|---|---|
| `ok` | `true` if the graph is valid. |
| `error` | The error message. It shows only when `ok` is `false`. |
| `env_file` | The variables file of the run, or `null`. |
| `resolved` | The nodes that file mode added as dependencies. |
| `waves` | The node IDs of each wave, in the sequence of execution. |
| `nodes[].file` | The file of the node. For an alias, it is the file of the template. |
| `nodes[].variables` | The variables that the node gets from its dependencies. |
| `nodes[].retry_attempts` | The value of `retry.attempts`. `1` means no retry. |
