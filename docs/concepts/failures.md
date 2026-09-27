# Failures and skips

A node has one result. The result controls the exit code of the run and the nodes that come after it.

| Result | Console | Run fails | Dependents |
|---|---|---|---|
| Pass | `SUCCESS` | No | Run. |
| Fail | `FAILED` | Yes | Skip with `failed dependency`. |
| Known failure | `KNOWN FAILURE` | No | Skip with `known failure upstream`. |
| Skip | `SKIPPED` | Same as the upstream node | Skip. |

## A failure stops only its branch

When a node fails, hurl-orchestra skips all nodes that need it. The other nodes continue. Thus one run shows all independent failures, not only the first failure.

Try it on the score below. Select `create_cart`, then select it again for a known failure.

<ScorePlayer autoplay="none" />

## Known failures

A known failure is a failure that you expect and that you documented. You declare its signature in `known_failures`. When a failure matches the signature, the run stays green. The report still shows the failure.

Each entry has a `name`, a `reason` and an optional `until` date. After the `until` date, the entry stops to match, and the failure fails the run again. For the procedure, read [Tolerate a known failure](/how-to/tolerate-a-known-failure).

The `--strict` flag makes each known failure fail the run.

## Retries

A `retry` policy runs a failed node again before hurl-orchestra decides the result. The node gets its result from the last attempt. For the procedure, read [Retry on back pressure](/how-to/retry-on-back-pressure).

hurl-orchestra applies the retries first. Then it compares the last failure with `known_failures`.

## Time limit

Each Hurl call has a limit of 300 seconds. After the limit, hurl-orchestra stops the call, and the node fails with `Hurl timed out after 300 seconds`.
