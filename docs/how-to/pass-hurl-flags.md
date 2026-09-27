# Give flags to Hurl

Use this procedure to give Hurl options to all nodes or to one node.

## Give flags to all nodes

1. Put the flags after a `--` separator:

   ```bash
   hurl-orchestra ./tests -- --variable host=localhost --retry 3
   ```

2. Put the hurl-orchestra options before the `--` separator:

   ```bash
   hurl-orchestra --report-zip ci.zip ./tests -- --connect-timeout 10
   ```

hurl-orchestra gives all words after `--` to each Hurl call, with no change.

A flag without a value can also go before `--`, for example `--verbose`. A flag with a value must go after `--`.

## Give flags to one node

1. Add an `args` list to the frontmatter of the file:

   <<< @/snippets/args/slow_report.hurl{hurl}

2. Write each flag without the dashes. hurl-orchestra adds `-` to a name with one letter and `--` to a longer name.
3. For a flag with a value, write a map with one key.

## Result

hurl-orchestra adds the `args` of the node after the flags from the command line. If the two places set the same flag, Hurl uses the last value. Thus the value of the node wins.
