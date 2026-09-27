# Troubleshooting

Find the error in the list. Then do the steps of the solution in sequence.

## `ERROR: 'hurl' not found on PATH`

hurl-orchestra calls the `hurl` command.

Solution:

1. Install [Hurl](https://hurl.dev/docs/installation.html).
2. Run `hurl --version` in the same shell.

A dry run does not need Hurl.

## `ERROR: deps for 'foo' must be a list`

The frontmatter of the file has an incorrect type. Similar errors are for `id`, `outputs`, `priority` and `args`.

Solution:

1. Open the file that the error names.
2. Correct the field. For the types, read [Frontmatter](/reference/frontmatter).
3. Run `hurl-orchestra --dry-run` to validate the change.

## `ERROR: 'foo' depends on 'bar' but no .hurl file or alias defines id: bar`

No node has the ID in `deps`.

Solution:

1. Make sure that a file has `id: bar`, or the name `bar.hurl`.
2. Put that file in the same directory as `foo`.
3. If you use `--no-deps`, give the file on the command line.

## `ERROR: alias template 'X' not found (used as 'Y')`

An alias names a template that the run did not load.

Solution:

1. Make sure that the template file is in the same directory.
2. Make sure that the template name is the ID of that file.

## `Circular dependency detected`

The `deps` make a cycle.

Solution:

1. Read the node IDs in the message.
2. Remove one of the `deps` in the cycle.

## `ERROR: env file not found`

The file of `--env-file` does not exist.

Solution:

1. Examine the path. A relative path starts at the current directory.

## Hurl cannot find a variable

Hurl shows an error for a variable without a value, for example `base_url`.

Solution:

1. Read the `Variables file` line at the start of the run. If it is not there, no variables file applies.
2. If you gave files, read the `NOTE` line. Add `--env-file` with the path that it shows.
3. For a variable from a dependency, make sure that the producer is in `deps` and the output is in its `outputs`.

## `FAILED: foo, Missing expected outputs`

The node declared an output, and the Hurl report has no capture with that name.

Solution:

1. Make sure that the `[Captures]` section defines each name in `outputs`.
2. Make sure that the response contains the value at that path.

## `SKIPPED: foo (failed dependency: bar)`

The node did not run because `bar` failed.

Solution:

1. Correct the failure of `bar`. The node runs again when its inputs exist.

## `FAILED: foo, Hurl timed out after 300 seconds`

One Hurl call took more than 5 minutes.

Solution:

1. Run the file with Hurl alone to find the slow request.
2. Add a timeout to the request, for example with `args` and `max-time`.

## `FAILED: foo, known failure 'name' expired on date`

The failure matched an entry, but its `until` date is in the past.

Solution:

1. Examine if the cause still exists.
2. If it exists, set a new `until` date and update the `reason`.
3. If it does not exist, remove the entry.

## `ERROR: known_failures[0] for 'foo' …`

An entry in `known_failures` is not valid.

Solution:

1. Make sure that the entry has a `name` and a `reason`.
2. Make sure that the entry has one or more signature fields.
3. Make sure that each regular expression is valid and each name is unique.

## `Diagram output already exists`

`--diagram` does not replace a file.

Solution:

1. Add `--diagram-overwrite`, or give a different `--diagram-output`.
