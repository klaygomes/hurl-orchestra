# Upgrade hurl-orchestra

Use this procedure to move a current suite to hurl-orchestra 0.13.0 and Hurl 8.1. The steps show each behavior that changed and the command to check it.

## Before you start

You need:

- Python 3.11 or a later version.
- Hurl 7.1.0 or a later version on your `PATH`.
- A copy of the current suite and its report.

hurl-orchestra 0.13.0 uses features of Hurl 7.1.0 and later. The project tests it with Hurl 8.1.0. A run stops with a clear error when Hurl is older than 7.1.0.

## 1. Install the new versions

```bash
pip install --upgrade hurl-orchestra
brew upgrade hurl
hurl --version
```

The last command must show `8.1.0` or a later version. For other systems, read the [Hurl installation guide](https://hurl.dev/docs/installation.html).

## 2. Move the Hurl options that Hurl 8 renamed

Hurl 8.0 changed these names:

| Old name | New name |
|---|---|
| `--ignore-asserts` | `--no-assert` |
| `--noproxy` | `--no-proxy` |
| `--interactive` | Removed |
| `HURL_foo` environment variable | `HURL_VARIABLE_foo` |

1. Search the suite and the CI files for the old names.
2. Replace each old name with the new name.
3. Search for environment variables that start with `HURL_`. Replace each one with `HURL_VARIABLE_` or `HURL_SECRET_`.

Hurl 8.0 also uses the RFC 9535 JSONPath module. Some queries can select a different result. Run the suite and compare the captures with the current report.

## 3. Learn the new secret transport

Before 0.13.0, hurl-orchestra gave each captured value to Hurl with `--variables-file`. Hurl wrote the value in its report.

From 0.13.0, hurl-orchestra gives each captured value to Hurl with `--secrets-file`. Hurl replaces the value with `***` in its standard error and in `report.json`. The value does not show in the process list.

::: warning
Hurl redacts request headers and log lines only. The response body files in `report.zip` can contain a credential that the API returned. Do not publish a report from a suite with real credentials.
:::

To keep the old behavior, add `--inject-as-variables`. Do not use this flag with real credentials.

## 4. Add a secrets file for global values (optional)

Use `--secrets-file` for a password or an API key that all nodes need:

```bash
hurl-orchestra ./tests --secrets-file ci-secrets.env
```

The file uses the same `name=value` format as `.env`. Hurl redacts each value.

## 5. Check the timeout behavior

`--timeout` now also gives `--max-time` to each Hurl call. Hurl writes a report when a request reaches the limit. The process gets 5 more seconds to write that report.

A `max-time` in the `args` frontmatter or after `--` replaces the value from `--timeout`. hurl-orchestra then uses `--timeout` only to stop a process that does not exit.

## 6. Check the retry behavior

hurl-orchestra reads the Hurl exit code before it starts a retry:

| Hurl exit code | Description | Retry |
|---|---|---|
| `1` | Command line error | Never |
| `2` | Parse error | Never |
| `3` | Runtime error | Follows `retry` |
| `4` | Failed assertion | Follows `retry` |

A retry cannot repair a bad option or a syntax error. Remove those failures from the file or from the `args` list.

## 7. Check the Hurl config file

Hurl 8.1 reads a config file at `$XDG_CONFIG_HOME/hurl/config` or `~/.config/hurl/config`. hurl-orchestra shows the file in the first lines of the run:

```text
Hurl config: /home/you/.config/hurl/config
```

The config file supplies defaults. A command line option wins. The config file cannot set `--report-json`, `--variables-file` or `--secrets-file`.

## 8. Verify the upgrade

1. Run `hurl --version` and make sure that it shows 8.1.0 or later.
2. Run `hurl-orchestra --dry-run --json tests`. The document must show `"ok": true`.
3. Run `hurl-orchestra tests --report-ctrf results.json`.
4. Read the first lines. They show each file that the run uses.
5. Open `report.zip` and examine one request header with a captured value. The value must be `***`.
6. Compare the CTRF `passed`, `failed` and `skipped` counts with the current report.

## Roll back

To return to the earlier behavior:

```bash
pip install hurl-orchestra==0.12.0
```

Then install Hurl 7.1.0 or later. Read [Hurl compatibility](/reference/hurl-compatibility) for the details of each version.
