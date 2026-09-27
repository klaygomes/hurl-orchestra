# Order the nodes in a wave

Use this procedure when independent nodes must run in a specified sequence. For example, a `delete` must not run before a `search` that needs the data.

## Procedure

1. Give a positive `priority` to the node that must run first:

   <<< @/snippets/priority/create.hurl{hurl}

2. Give no `priority` to the node in the middle. The default value is `0`.

   <<< @/snippets/priority/search.hurl{hurl}

3. Give a negative `priority` to the node that must run last:

   <<< @/snippets/priority/delete.hurl{hurl}

4. Examine the plan:

   ```bash
   hurl-orchestra --dry-run ./tests
   ```

## Result

The three nodes are in the same wave. hurl-orchestra runs the priority groups in sequence: `create`, then `search`, then `delete`.

::: tip
Use `priority` only for nodes that do not share data. If a node needs the output of a different node, use `deps`.
:::
