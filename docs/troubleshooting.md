# Troubleshooting

Find the error in the list. Then do the steps of the solution in sequence.

## `ERROR: 'hurl' not found on PATH`

hurl-orchestra calls the `hurl` command.

Solution:

1. Install [Hurl](https://hurl.dev/docs/installation.html).
2. Run `hurl --version` in the same shell.

A dry run does not need Hurl.

## `ERROR: no .hurl files found in <path>`

The given directory has no `.hurl` files. This is an error, not an empty pass, so CI cannot go green with no tests.

Solution:

1. Examine the path. It must contain the `.hurl` files.
2. Use `--dry-run` to check the directory before the run.

## `ERROR: <file> has unknown frontmatter keys: <keys>`

The frontmatter has a field that hurl-orchestra does not know. A common cause is a typo such as `dep` for `deps` or `output` for `outputs`.

Solution:

1. Compare the field with the [frontmatter reference](/reference/frontmatter).
2. Correct the name. Run `--dry-run` to validate the file.

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

## `ERROR: secrets file not found`

The file of `--secrets-file` does not exist.

Solution:

1. Examine the path. A relative path starts at the current directory.

## `ERROR: hurl 7.0.0 is too old`

The `hurl` command on the `PATH` is older than 7.1.0.

Solution:

1. Install Hurl 7.1.0 or a later version. hurl-orchestra runs its tests with 8.1.0.
2. Run `hurl --version` in the same shell.

## `WARNING: cannot read the hurl version`

hurl-orchestra found the `hurl` command, but the output of `hurl --version` is not in the usual format.

Solution:

1. Run `hurl --version` and examine the output.
2. Install the official Hurl binary from the [Hurl website](https://hurl.dev/docs/installation.html).

## `ERROR: --test is managed by hurl-orchestra`

A Hurl option that the tool owns is in the flags or in the `args` frontmatter. The same error shows for `--report-json` and `--secrets-file`.

Solution:

1. Remove the option from the command or from `args`.
2. For a report, use `--report-zip` or `--report-ctrf`.
3. For a secrets file, use the hurl-orchestra `--secrets-file` option.

## `Hurl could not parse the file (exit code 2)`

Hurl rejected the syntax of the file. hurl-orchestra does not retry this failure, because a retry cannot repair the file.

Solution:

1. Read the Hurl error below the message. It shows the line and the token.
2. Correct the file.
3. Run `hurl-orchestra --dry-run` to check the frontmatter, then run the suite again.

## `Hurl rejected the command line (exit code 1)`

Hurl rejected an option. hurl-orchestra does not retry this failure.

Solution:

1. Compare each Hurl option with the [Hurl manual](https://hurl.dev/docs/manual.html).
2. Remove the reserved options that [Hurl compatibility](/reference/hurl-compatibility) lists.
3. Run `hurl --version` and make sure that the version is 8.1.0 or later for the new options.

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

One Hurl call reached the limit. hurl-orchestra gives the value of `--timeout` to Hurl as `--max-time`. Thus Hurl writes a report before the process stops.

Solution:

1. Read the report of the node. It shows the request that reached the limit.
2. Add a timeout to the request, for example with `args` and `max-time`.
3. If the whole suite needs more time, run with `--timeout SECONDS`.

## A `Hurl config:` line shows an option that you did not set

Hurl 8.1 reads a config file at `$XDG_CONFIG_HOME/hurl/config` or `~/.config/hurl/config`. The file supplies default options to each call.

Solution:

1. Read the file at the path in the line.
2. Remove the option that you do not want.
3. Or set the option on the hurl-orchestra command line. A command line option wins over the config file.

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
