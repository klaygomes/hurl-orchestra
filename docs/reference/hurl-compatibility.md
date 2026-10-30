# Hurl compatibility

hurl-orchestra calls the `hurl` command. This page shows the supported versions, the options that hurl-orchestra sets and the options that you can change.

## Versions

| Hurl version | Result |
|---|---|
| 8.1.0 | Tested in CI. |
| 7.1.0 to 8.0.1 | Tested in CI on 7.1.0. |
| Older than 7.1.0 | The run stops with an error. |

hurl-orchestra needs the `--secrets-file` option and the Hurl exit codes. Both exist from Hurl 7.1.0. CI runs the integration tests with Hurl 7.1.0 and 8.1.0.

## Options that hurl-orchestra sets

| Hurl option | Value | Purpose |
|---|---|---|
| `--test` | Always | Run the file in test mode. |
| `--report-json` | One directory for each node | Collect the report of the node. |
| `--variables-file` | `--env-file`, or `.env` | Give the global variables to the node. |
| `--secrets-file` | `--secrets-file`, or the captured values | Give the secrets to the node. hurl-orchestra merges the global file and the captured values into one file. |
| `--max-time` | `--timeout` | Stop a request at the limit and still write a report. |

A `max-time` in the `args` frontmatter or after `--` replaces the value from `--timeout`.

## Reserved options

hurl-orchestra stops with an error when you give one of these options to Hurl:

| Option | Use this instead |
|---|---|
| `--test` | Nothing. hurl-orchestra uses test mode. |
| `--report-json` | `--report-zip` or `--report-ctrf` |
| `--secrets-file` | The hurl-orchestra `--secrets-file` option |

Hurl rejects a repeated `--max-time`, `--test`, `--report-json` or `--secrets-file`. hurl-orchestra catches each case before the first request.

## Options that you can give to Hurl

Put all other Hurl options after `--` or in the `args` frontmatter. Hurl 8.1 options work without a change, for example:

- `--tls-min` and `--tls-max`
- `--http2-prior-knowledge`
- `--proxy-header`
- `--no-header`
- `--fail-with-body`
- `--no-jsonpath-coercion`
- `--no-cookie-store`
- `--verbosity`

hurl-orchestra discards the standard output of Hurl. Thus `--fail-with-body` and `--json` change no visible output. Use the CTRF report or the zip file instead.

## Hurl config file

Hurl 8.1 reads a config file from `$XDG_CONFIG_HOME/hurl/config` or `~/.config/hurl/config`. The file supplies default options to each call. A command line option wins.

hurl-orchestra shows the path on the first lines of a run:

```text
Hurl config: /home/you/.config/hurl/config
```

The config file cannot set `--report-json`, `--variables-file` or `--secrets-file`. Hurl reports an unknown option.

## Exit codes and retry

| Hurl exit code | Description | Retry |
|---|---|---|
| `0` | Success | - |
| `1` | Command line error | Never |
| `2` | Parse error | Never |
| `3` | Runtime error | Follows `retry` |
| `4` | Failed assertion | Follows `retry` |

A retry cannot repair a bad option or a syntax error. hurl-orchestra stops after the first attempt for exit codes 1 and 2.

## Limits

- hurl-orchestra writes the Hurl JSON reports and a CTRF report. It does not merge JUnit or TAP files. Use `--report-ctrf` for CI.
- Each node runs in its own Hurl process with one file. Hurl options that control the parallel execution of files, such as `--jobs` and `--parallel`, change nothing. Use the hurl-orchestra `--jobs` option.
- Hurl redacts a secret in its standard error and in `report.json`. The response body files in the zip archive can contain the same value.
- A `stderr` signature in `known_failures` or `retry` sees `***` instead of a captured value, because Hurl redacts the value first.
- The `[Options]` section of a Hurl file can set a variable. Hurl does not accept a secret in that section. Use `--secrets-file` instead.
