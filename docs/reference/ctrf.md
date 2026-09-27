# CTRF report

`--report-ctrf` writes a [CTRF](https://ctrf.io) JSON report. The [GitHub test reporter](https://github.com/ctrf-io/github-test-reporter) and other CTRF tools can read it.

## Tests

Each Hurl entry of a node becomes one test. An entry is one request with its assertions.

| Case | Test status | Message |
|---|---|---|
| All assertions of the entry pass | `passed` | None |
| An assertion fails | `failed` | The Hurl assertion on one line, for example `Assert status code: HTTP 200 (actual value is <500>)` |
| Hurl marks the file failed, and no assertion failed | `failed` | One test for the node |
| The Hurl process failed | `failed` | The error |
| A dependency failed | `skipped` | `failed dependency: <id>` |
| A known failure | `other`, with `flaky: true` | The matched signature. The entry name is in `tags`. |
| A dependency was a known failure | `skipped` | `known failure upstream: <id>` |

## Retries

With the Hurl option `[Options] retry`, Hurl writes one entry for each attempt, with the same index. The report keeps only the last attempt. Thus a request that failed two times and then passed is one passed test.

With the `retry` policy of hurl-orchestra, the report contains only the last attempt of the node.

## Summary

`summary.other` counts the known failures. They do not increase `summary.failed`.
