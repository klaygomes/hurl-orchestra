# Tolerate a known failure

Use this procedure when a node fails for a cause that you know and cannot correct now. For example, a shared test database can reach its connection limit.

## Procedure

1. Find the signature of the failure in the Hurl report: the status, a header, the body or the error text.
2. Add an entry to `known_failures`:

   <<< @/snippets/known-failures/create_order.hurl{hurl}

3. Write a `name`. The console, the summary and the CTRF `tags` show it.
4. Write a `reason` that a different engineer can understand.
5. Set `until` to the date of the next review.
6. Add `link` to the ticket or the runbook.
7. Run the suite with `--dry-run` to validate the entry.

## Result

When the node fails and each signature field that you set matches, the console shows:

```text
KNOWN FAILURE: create_order [db_pool_exhausted] The shared test database is at its connection limit
```

The run stays green. The nodes that need `create_order` get no outputs, so hurl-orchestra skips them. The run ends with a summary:

```text
Known failures tolerated: 1 (db_pool_exhausted: create_order)
```

After the `until` date, the entry stops to match, and the failure fails the run with `known failure 'db_pool_exhausted' expired on 2026-12-31`.

## Make the known failures fail

Run with `--strict` to see if the cause still exists:

```bash
hurl-orchestra --strict ./tests
```

For all fields, read [Frontmatter](/reference/frontmatter#known-failures).
