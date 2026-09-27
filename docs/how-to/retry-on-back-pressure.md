# Retry on back pressure

Use this procedure when a server can refuse requests under load, for example with `429 Too Many Requests` or `503 Service Unavailable`.

## Procedure

1. Add a `retry` policy to the frontmatter of the node:

   <<< @/snippets/retry/create_order.hurl{hurl}

2. In `when`, list only the failures that show back pressure. Without `when`, hurl-orchestra retries each failure, also a failed assertion.
3. Use `stderr` to match a connection error. It is the only field that can match when no response arrived.
4. Set `max_backoff_ms` to the longest wait that your CI accepts.

## Result

After a failure that matches `when`, hurl-orchestra waits and runs the full node again. The wait after attempt *n* is:

```text
min(max_backoff_ms, backoff_ms × multiplier^(n − 1))
```

With `jitter: full`, the wait is a random value from 0 to that limit. Thus nodes that fail together do not retry together.

If the response has a `Retry-After` header, hurl-orchestra uses it. It accepts seconds and HTTP dates. `max_backoff_ms` still limits the value.

The console shows each attempt, and the result line shows the number of attempts:

```text
RETRY: create_order attempt 1/4 failed (status 503), waiting 412ms
SUCCESS: create_order [2 attempts]
```

::: warning
The Hurl option `[Options] retry` also retries a request. If you use the two options together, the numbers of attempts multiply.
:::

For all fields, read [Frontmatter](/reference/frontmatter#retry).
