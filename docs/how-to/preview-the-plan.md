# Preview the plan

Use this procedure to examine the order of the nodes before a run. A dry run does not call Hurl, so you do not need Hurl on the `PATH`.

## Procedure

1. Add `--dry-run` to the command:

   ```bash
   hurl-orchestra --dry-run tests/checkout.hurl
   ```

2. Read the waves:

   ```text
   Resolved dependencies: add_item, auth, create_cart
   Plan: 4 node(s)
     wave 1: auth
     wave 2: create_cart
     wave 3: add_item
     wave 4: checkout
   ```

3. If the command shows an error, correct the frontmatter. Then do step 1 again.

## Get the plan as JSON

Add `--json` for a result that a script or an AI agent can read:

```bash
hurl-orchestra --dry-run --json tests/checkout.hurl
```

The JSON contains the waves and, for each node, the file, the dependencies and the variables that the node gets. If the graph has an error, the JSON contains `"ok": false` and the message. For the fields, read [Command line](/reference/cli#json-plan).

## Use the dry run in CI

A dry run is fast and needs no network. Add it as the first step of a CI job. Then a broken graph fails the job before a request goes to the server.
