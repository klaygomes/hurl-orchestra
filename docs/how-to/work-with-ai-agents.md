# Work with AI agents

hurl-orchestra is AI first API automation testing. It has no model inside. Its files, its commands and its results are easy for a coding agent to write, check and read. Use this procedure to let an agent such as Claude Code or Codex write and repair your API tests.

## Why agents write good suites with it

| Property | What the agent gets |
|---|---|
| Plain-text Hurl files | A request and its assertions in one small file, with no code to compile. |
| Frontmatter with a few fields | The agent declares the order in `deps`. It does not write a script for it. |
| `--dry-run --json` | A plan that the agent can parse: the waves, the files and the variable names of each node. |
| One-line errors | Each error names the node and the field, for example `ERROR: deps for 'foo' must be a list`. |
| CTRF results | A JSON file with one test for each request and the reason for each failure. |
| `known_failures` with `reason` and `until` | A tolerance that a human reviews. An agent cannot hide a failure without a trace. |
| `llms.txt` | This documentation as plain text for the context of the agent. |

## Procedure

1. Copy these rules into the `AGENTS.md` or `CLAUDE.md` file of your repository:

   <<< @/snippets/agents/AGENTS.md{md}

2. Give the agent a task, for example: "Add a test that a customer cannot read the order of a different customer."
3. Let the agent run the dry run. The JSON plan shows the variables that each file can use:

   ```bash
   hurl-orchestra --dry-run --json tests
   ```

4. Let the agent run the suite and read `tests/results.json`.
5. Review the new files and the plan in the pull request, as you review code.

## Give the documentation to the agent

The site publishes two plain-text files:

- [llms.txt](/llms.txt) is a list of all pages with a short description.
- [llms-full.txt](/llms-full.txt) is the full documentation in one file, with the samples.

Give the URL of `llms-full.txt` to the agent, or copy the file into the context.

## Result

The agent writes each scenario as a separate file and declares its dependencies. It checks the graph before it sends a request. When a test fails, the CTRF message tells the agent the assertion and the actual value.
