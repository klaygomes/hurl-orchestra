# The graph

hurl-orchestra reads the frontmatter of each `.hurl` file. It then makes a directed acyclic graph (DAG). Each file is a node, and each entry in `deps` is an edge.

<ScorePlayer :terminal="false" autoplay="view" />

## Nodes

The ID of a node is the `id` field. If a file has no `id`, the ID is the file name without `.hurl`. An ID must not contain spaces, because hurl-orchestra uses it in variable names.

A file without frontmatter is also a node. It has no dependencies and no outputs.

## Waves

A wave is a set of nodes that have all of their dependencies done. hurl-orchestra runs the nodes of one wave in parallel. It starts the next wave when the current wave is complete.

| Wave | Nodes | Why |
|---|---|---|
| 1 | `auth`, `catalog` | These nodes have no `deps`. |
| 2 | `create_cart` | It needs `auth`. |
| 3 | `add_item` | It needs `auth` and `create_cart`. |
| 4 | `checkout` | It needs `add_item`. |

The maximum number of parallel Hurl processes is the number of CPUs plus 4, with a limit of 32.

## Priority in a wave

The `priority` field sorts the nodes in a wave. hurl-orchestra runs each priority group in sequence, from the highest value to the lowest value. The nodes in one group run in parallel. For a procedure, read [Order the nodes in a wave](/how-to/order-a-wave).

Priority never overrides `deps`. A node with a high priority still waits for its dependencies.

## Validation

hurl-orchestra validates the full graph before it runs a node. The run stops with an error if:

- A dependency has no node with that ID.
- The `deps` make a cycle, for example `a` needs `b` and `b` needs `a`.
- A frontmatter field has an incorrect type.

Thus a broken graph never runs half of a suite.

## Discovery

When you give a directory, hurl-orchestra loads all `.hurl` files in that directory. It does not go into subdirectories.

When you give one or more files, hurl-orchestra loads all `.hurl` files in the same directories. It then runs the files that you gave and their dependencies. For a procedure, read [Run specific files](/how-to/run-specific-files).
