# Console output

Each node writes one result line when it is complete. A failure also writes the error output of Hurl.

## Result lines

| Line | Description |
|---|---|
| `SUCCESS: <id> [injected: … \| captured: … \| N attempts]` | The node passed. The brackets show the variables that it got and gave. |
| `FAILED: <id>` | The node failed. The error output of Hurl follows. |
| `KNOWN FAILURE: <id> [<name>] <reason> (<link>)` | The failure matched a `known_failures` entry. The run stays green. The link shows when the entry has one. |
| `SKIPPED: <id> (failed dependency: <ids>)` | A dependency failed. The node did not run. |
| `SKIPPED: <id> (known failure upstream: <ids>)` | A dependency was a known failure. The node did not run. |
| `RETRY: <id> attempt N/M failed (<status>), waiting <ms>ms` | A retry policy runs the node again. |

## Other lines

| Line | When |
|---|---|
| `Variables file: <path>` | A variables file applies to the run. |
| `Secrets file: <path>` | A secrets file applies to the run. Hurl redacts the values. |
| `Hurl config: <path>` | Hurl 8.1 reads this config file for each call. |
| `NOTE: hurl-orchestra does not read <path> …` | In file mode, a `.env` file next to the files is not the variables file. |
| `Resolved dependencies: <ids>` | File mode added dependencies. |
| `Plan: N node(s)` and `wave N: …` | A dry run. |
| `Known failures tolerated: N (<name>: <ids>)` | The last line when a known failure occurred. |
| `CTRF report saved to <path>` | `--report-ctrf` wrote the report. |
| `Report saved to <path>` | The zip file is complete. |
| `WARNING: cannot read the hurl version` | The output of `hurl --version` is not in the usual format. The run continues. |

## Error lines

A line that starts with `ERROR:` stops the run before a node runs. A failure line can also start with `Hurl rejected the command line (exit code 1).` or `Hurl could not parse the file (exit code 2).`. For the causes, read [Troubleshooting](/troubleshooting).
