# Frontmatter

The frontmatter is a YAML block between two `---` lines at the start of a `.hurl` file. All fields are optional.

## Fields

| Field | Type | Default | Description |
|---|---|---|---|
| `id` | string | The file name without `.hurl` | The ID of the node. It must not contain spaces. |
| `deps` | list | `[]` | The IDs of the nodes that must pass first. An item `template: alias` makes an [alias](/concepts/aliases). |
| `outputs` | list of strings | `[]` | The captures that the node gives to its dependents. |
| `priority` | integer | `0` | The sequence in a wave. A higher value runs first. |
| `args` | list | `[]` | Hurl flags for this node. |
| `known_failures` | list | `[]` | The failures that the node can tolerate. |
| `retry` | map | No retry | The retry policy of the node. |

## `args` {#args}

| Item | Hurl flag |
|---|---|
| `verbose` | `--verbose` |
| `v` | `-v` |
| `connect-timeout: 30` | `--connect-timeout 30` |
| `--insecure` | `--insecure`, with no change |

## `known_failures` {#known-failures}

Each entry needs `name`, `reason` and one or more signature fields. All signature fields that you set must match.

| Field | Type | Description |
|---|---|---|
| `name` | string | The name in the console, the summary and the CTRF `tags`. It must be unique in the node. |
| `reason` | string | Why the failure is acceptable. |
| `until` | date | After this date, the entry does not match. Optional. |
| `link` | string | Where the failure has documentation. Optional. |
| `status` | integer | The status code of the last response. |
| `header` | map | `name` and `pattern`. The name is not case-sensitive. The pattern is a regular expression. |
| `body` | string | A regular expression for the body of the last response. |
| `stderr` | string | A regular expression for the error output of Hurl. It can match when no response arrived. |

The last response is the last call that Hurl recorded for the node. With the Hurl option `[Options] retry`, it is the last attempt.

## `retry` {#retry}

| Field | Type | Default | Description |
|---|---|---|---|
| `attempts` | integer | `1` | The total number of attempts, with the first attempt. `1` disables the retry. |
| `backoff_ms` | integer | `1000` | The base wait in milliseconds. |
| `max_backoff_ms` | integer | `30000` | The maximum wait, also for `Retry-After`. |
| `multiplier` | number | `2` | The growth of the wait after each attempt. It must be 1 or more. |
| `jitter` | `full` or `none` | `full` | `full` selects a random wait from 0 to the limit. `none` waits the full limit. |
| `respect_retry_after` | boolean | `true` | Use the `Retry-After` header of the response. |
| `when` | map or list | Each failure | The signatures that start a retry. Each item takes `status`, `header`, `body` and `stderr`. |

hurl-orchestra validates all fields before the run. An unknown key in `retry` stops the run.
