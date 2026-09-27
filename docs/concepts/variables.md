# Variables

A node can give values to the nodes that need it. You declare the values in `outputs`, and you capture them in the `[Captures]` section of the Hurl file.

## Names

A dependent node gets each output with the ID of the producer as a prefix:

```text
{producer id}_{output name}
```

For example, the output `token` of the node `auth` becomes `auth_token`. Two nodes can capture a `token`, and the names do not collide.

If an ID or an output name contains a character other than a letter, a digit or `_`, hurl-orchestra changes the character to `_xx_`. The `xx` is the hexadecimal code of the character. For example, `auth-v2` becomes `auth_2d_v2`.

## Only direct dependencies

A node gets the outputs of the nodes in its own `deps` list. It does not get the outputs of the dependencies of those nodes. Add each producer that you need to `deps`. This rule keeps the source of each variable clear.

## An output without a capture

If a node declares an output and the Hurl report does not contain that capture, the node fails:

```text
FAILED: auth
Missing expected outputs: token; reported outputs: none
```

## How the values go to Hurl

hurl-orchestra writes the values to a private variables file for each call. Then it gives the file to Hurl with `--variables-file`. Thus a token does not show in the process list.

## Global variables

A variables file gives values to all nodes, for example `base_url`. hurl-orchestra gives the file to each Hurl call with `--variables-file`. It selects one file:

| Command | Variables file |
|---|---|
| `hurl-orchestra ./tests` | `tests/.env` |
| `hurl-orchestra` | `.env` in the current directory |
| `hurl-orchestra tests/profile.hurl` | `.env` in the current directory |
| `hurl-orchestra --env-file ci.env ./tests` | `ci.env` |

The run shows the file that it uses on the first line:

```text
Variables file: tests/.env
```

When you give files, hurl-orchestra does not read a `.env` file next to the files. The run tells you, and it shows the fix:

```text
NOTE: hurl-orchestra does not read tests/.env when you give files. It reads .env from the current directory. Add --env-file tests/.env to read it.
```

If the file of `--env-file` does not exist, the run stops before it calls Hurl.

## Variables from the command line

Give Hurl flags after `--`. hurl-orchestra gives them to each Hurl call:

```bash
hurl-orchestra ./tests -- --variable region=eu
```

For more information, read [Give flags to Hurl](/how-to/pass-hurl-flags).
