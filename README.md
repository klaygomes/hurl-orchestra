# Hurl Orchestrator

A dependency-aware task runner for [Hurl](https://hurl.dev). It allows you to treat API requests as a Directed Acyclic Graph (DAG), managing complex authentication flows and resource creation without redundant executions or manual variable passing.

## Getting Started

Install the package and verify that `hurl` is available on your `PATH`.

```bash
pip install hurl-orchestra
hurl --version
```

Run the orchestrator from the current directory:

```bash
hurl-orchestra
```

Or point it at a specific test folder:

```bash
hurl-orchestra ./tests
```

For a quick diagram of your DAG instead of execution, use:

```bash
hurl-orchestra --diagram ./tests
```

## Core Philosophy

* **Explicit over Implicit**: Every dependency must be declared. This ensures that if a test fails, you know exactly which parent requirement was not met.
* **Namespaced Variables**: Outputs are tied to the ID of the node that produced them (`auth_token`), preventing variable collisions in large suites.
* **Reusable Logic**: Run the same Hurl file multiple times with different identities (e.g., `admin_login` vs `user_login`) using the alias syntax.

---

## 1. Setup

### Requirements

* **Python 3.11+**
* **Hurl** installed and available on your `PATH`

### Install

```bash
pip install hurl-orchestra
```

### Project Structure

Place your `.hurl` files in a directory. You can optionally include a `.env` file for global variables.

```text
tests/
├── .env                # Global variables (base_url, etc.)
├── auth.hurl           # Reusable auth logic
└── create_user.hurl    # Depends on auth
```

---

## 2. Defining Hurl Files

Each `.hurl` file uses YAML frontmatter to define its place in the graph.

### Creating and formatting a `.hurl` file

A `.hurl` file consists of:

* Optional YAML frontmatter wrapped in `---` markers
* The Hurl request and assertions body

Common frontmatter fields:

* `id` — unique node name for this test; defaults to the file stem when omitted
* `outputs` — list of capture names this test publishes; optional
* `deps` — list of upstream node IDs or alias definitions; optional
* `priority` — optional integer that influences ordering within a ready wave
* `args` — optional list of Hurl CLI flags specific to this file; strings are auto-prefixed (`verbose` → `--verbose`, `v` → `-v`), while single-key dicts become a flag/value pair (`connect-timeout: 30` → `--connect-timeout 30`)
* `known_failures`: optional list of failure signatures this node may tolerate; see [Known failures](#known-failures)

Example file structure:

```yaml
---
id: my_test
outputs: [token, session_id]
deps: [auth]
priority: 1
---
GET https://api.example.com/resource
Authorization: Bearer {{auth_token}}
HTTP 200
```

Aliases let you reuse the same template under multiple names and run each alias separately:

```yaml
---
id: admin_flow
deps:
  - auth: admin_login
  - auth: user_login
---
GET https://api.example.com/admin
Authorization: Bearer {{admin_login_token}}
```

### The Producer (`auth.hurl`)

Define an `id` and a list of `outputs` you want to share with other tests.

```yaml
---
id: auth
outputs: [token]
---
POST https://api.com/login
[Captures]
token: jsonpath "$.token"
HTTP 200
```

### The Consumer (`profile.hurl`)

List the `id` of the producer in `deps`. Access the variable using the `{id}_{variable}` syntax.

```yaml
---
id: get_profile
deps: [auth]
---
GET https://api.com/profile
Authorization: Bearer {{auth_token}}
HTTP 200
```

---

## 3. Running

```bash
hurl-orchestra                          # runs against the current directory
hurl-orchestra ./tests                  # runs against a specific directory
hurl-orchestra profile.hurl             # runs profile.hurl and its dependencies
hurl-orchestra --dry-run ./tests        # prints the execution plan only
hurl-orchestra --strict ./tests         # known_failures fail the run like any other failure
```

### Passing Hurl Flags

Simple boolean flags (no value) can be passed directly:

```bash
hurl-orchestra ./tests --verbose
```

For flags that take a value (`--variable`, `--connect-timeout`, `--header`, etc.), place them after a `--` separator so they are forwarded correctly:

```bash
hurl-orchestra ./tests -- --variable host=localhost --retry 3
hurl-orchestra auth.hurl profile.hurl -- --variable env=staging
hurl-orchestra --report-zip r.zip ./tests -- --variable k=v --connect-timeout 10
```

Everything after `--` is passed through verbatim to every `hurl` invocation.

You can also specify per-file Hurl flags in frontmatter using `args`:

```yaml
---
id: slow_endpoint
args:
  - verbose
  - connect-timeout: 30
  - variable: env=staging
---
GET https://slow.example.com/data
HTTP 200
```

Per-file `args` are appended after any global CLI flags, so last-value-wins behavior applies when the same flag is specified in both places.

### Running Specific Files

When you pass `.hurl` files directly, the orchestrator loads every `.hurl` file in the same directory as the ones you listed, resolves the full dependency graph, and then runs only the files you asked for plus everything they transitively depend on. Unrelated files in the directory are not executed.

```bash
# Runs auth.hurl first (because profile.hurl depends on it), then profile.hurl
hurl-orchestra profile.hurl
```

Nodes that were pulled in this way are listed before execution starts:

```
Resolved dependencies: auth
SUCCESS: auth [captured: token]
SUCCESS: profile [injected: auth_token]
```

Use `--dry-run` to see the plan without running anything. It prints each execution wave in order, which is the quickest way to check what a single file will pull in:

```bash
hurl-orchestra --dry-run checkout.hurl
```

```
Resolved dependencies: add_item, auth, create_cart
Plan: 4 node(s)
  wave 1: auth
  wave 2: create_cart
  wave 3: add_item
  wave 4: checkout
```

Pass `--no-deps` to disable resolution. In that mode only the listed files are loaded, so every dependency must also be on the command line:

```bash
hurl-orchestra --no-deps auth.hurl profile.hurl
```

### Console Output

Each node prints exactly one line as it finishes:

* `SUCCESS: <id> [injected: ... | captured: ...]`
* `FAILED: <id>` followed by the Hurl error output
* `KNOWN FAILURE: <id> [<name>] <reason>` followed by the Hurl error output, for a failure that matched one of the node's `known_failures`
* `SKIPPED: <id> (failed dependency: <ids>)` for nodes that never ran because an upstream node failed
* `SKIPPED: <id> (known failure upstream: <ids>)` for nodes that never ran because an upstream node was tolerated and produced no outputs

When anything was tolerated, one summary line closes the run: `Known failures tolerated: 2 (db_pool_exhausted: create_order, update_order)`.

Upstream outputs are handed to Hurl through a private, per-run `--variables-file` rather than `--variable` flags, so captured values such as tokens never appear in the process list.

### Reports

After every run, the orchestrator writes a zip archive containing the raw hurl JSON reports for every node that executed. Each node gets its own subdirectory inside the zip, named after its ID.

```
report.zip
├── auth/
│   ├── report.json
│   └── store/
└── create_user/
    ├── report.json
    └── store/
```

The zip is written even if the run fails, so partial results are preserved for debugging. The report is placed inside the test directory when one is explicitly passed, or in the current working directory otherwise. Use `--report-zip` to change the filename:

```bash
hurl-orchestra ./tests                        # → ./tests/report.zip
hurl-orchestra                                # → ./report.zip (CWD)
hurl-orchestra ./tests --report-zip ci-run.zip  # → ./tests/ci-run.zip
```

#### GitHub CI report (CTRF)

Use `--report-ctrf` to also generate a [CTRF](https://github.com/ctrf-io/ctrf) JSON report alongside the zip. CTRF is the format consumed by [ctrf-io/github-test-reporter](https://github.com/ctrf-io/github-test-reporter), which displays test results as a GitHub Actions job summary and PR comment.

```bash
hurl-orchestra ./tests --report-ctrf results.json
```

Each hurl entry becomes one test in the report. Nodes that were skipped because an upstream dependency failed appear with `status: skipped`; nodes that errored at the subprocess level appear with `status: failed`. A tolerated known failure appears with `status: other`, `flaky: true`, its declaration name in `tags` and the matched signature in `message`, and `summary.other` counts it, so the reporter's flaky view groups occurrences by name without inflating the failed count. Nodes skipped behind it are `status: skipped` with `known failure upstream: <id>` as the message.

Add the reporter step to your GitHub Actions workflow after running the orchestrator:

```yaml
- name: Run tests
  run: hurl-orchestra ./tests --report-ctrf results.json

- name: Publish test report
  uses: ctrf-io/github-test-reporter@v1
  with:
    report-path: 'results.json'
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
  if: always()
```

### Visualising the DAG

Pass `--diagram` to generate a Markdown file with a Mermaid flowchart instead of running tests:

```bash
hurl-orchestra --diagram ./tests                      # writes diagram.md
hurl-orchestra --diagram ./tests --diagram-output pipeline.md
hurl-orchestra --diagram auth.hurl profile.hurl --diagram-output -  # stdout
hurl-orchestra --diagram ./tests --diagram-output diagram.md --diagram-overwrite
```

The output file contains:

- **Flowchart** — all nodes with edges showing dependency direction. Node labels include the output count and, when non-zero, the priority.

---

## 4. Advanced Features

### Rerunning Dependencies (Aliasing)

If you need to run the same logic twice (e.g., to get two different tokens), use the `template: alias` syntax in your `deps`.

```yaml
---
id: admin_test
deps:
  - auth: admin_login  # Runs auth.hurl as "admin_login"
  - auth: user_login   # Runs auth.hurl as "user_login"
---
GET /admin
Authorization: {{admin_login_token}}
```

### Execution Priority

By default, nodes at the same dependency level run in an unspecified order. Use `priority` to control that order without adding artificial dependencies.

| Value | Effect |
|-------|--------|
| positive (e.g. `2`) | runs **earlier** than nodes with lower or no priority |
| `0` (default) | neutral |
| negative (e.g. `-1`) | runs **later** than neutral nodes |

**Example**: you have a `create`, a `search`, and a `delete` that are all independent. Without priority they could run in any order — if `delete` runs first it breaks `search`.

```yaml
---
id: create
priority: 1   # runs first
---
```

```yaml
---
id: search
# priority defaults to 0
---
```

```yaml
---
id: delete
priority: -1  # runs last
---
```

Priority only affects ordering **within** the same wave. It never overrides actual `deps` — a node always waits for its dependencies regardless of its priority value.

### Known failures

Some failures are understood, documented, and not worth a red run: a shared test database that hits its connection limit under load, a third-party sandbox that times out on Mondays. `known_failures` lets a node declare such a signature. When the node fails and the failure matches, it is reported as `KNOWN FAILURE` instead of `FAILED`, the run stays green, and its dependents are skipped because they have no inputs.

```yaml
---
id: create_order
outputs: [order_id]
known_failures:
  - name: db_pool_exhausted
    reason: Shared test database at its connection limit
    until: 2026-12-31
    link: https://example.com/runbooks/test-db-pool
    status: 500
    header:
      name: X-Error-Code
      pattern: '^ERR-DB-\d+$'
---
POST https://api.example.com/orders
HTTP 200
```

Each entry needs a `name` (used in the console, the summary and the CTRF `tags`) and a `reason`, plus at least one signature field. Every signature field that is set must match:

| Field | Matches against |
|-------|-----------------|
| `status` | the status code of the last response Hurl recorded for the node |
| `header` | a response header on that last response: `name` is compared case-insensitively, `pattern` is a regex searched in its value |
| `body` | a regex searched in that last response's body |
| `stderr` | a regex searched in Hurl's error output, the only field that can match when no response was received |

With `[Options] retry: N` Hurl records one call per attempt; the last one is the failure, so that is the one inspected.

`until` is optional. After that date the entry stops matching, the failure is reported normally, and the output says `known failure '<name>' expired on <date>`, so a tolerance carries its own review date. `link` is free text for wherever the failure is documented.

Pass `--strict` to make every known failure fail the run again. That is how you find out whether a flake has actually gone away.

Entries are validated when files are discovered. A missing `name` or `reason`, an entry with no signature field, an invalid regex, an unparseable `until`, or two entries with the same name in one node stop the run before anything executes.

### Global Environment (`.env`)

The orchestrator looks for a `.env` file in the directory passed as argument (or the current working directory when none is given). Variables defined here are available to **all** Hurl files without being declared in the frontmatter.

```properties
# .env
base_url=https://staging.api.com
```

---

## 5. Execution Flow

When you run `hurl-orchestra`, the tool performs the following steps:

1. **Discovery**: Scans for all `.hurl` files and reads their metadata.
2. **Graph Construction**: Builds an execution map. If you used an alias, it "clones" that template into a unique node.
3. **Validation**: Ensures there are no circular dependencies (e.g., A depends on B, and B depends on A).
4. **Execution**:
   * Processes nodes wave by wave — each wave contains all nodes whose dependencies are satisfied.
   * Within each wave, nodes are sorted by `priority` (highest first).
   * Captures output variables into a shared pool.
   * Injects required variables into downstream tests via Hurl's `--variable` flag.
   * Skips the dependents of any node that failed or was tolerated as a known failure, since they have no inputs to run with. Unrelated nodes keep running.

---

## 6. Troubleshooting

### "ERROR: 'hurl' not found on PATH. Install it from https://hurl.dev"

The tool requires the Hurl binary to be installed and available in your shell `PATH`. Install Hurl and verify with `hurl --version`.

### Frontmatter validation errors

Messages like:

* `ERROR: node id for foo must be a non-empty string`
* `ERROR: output name for node 'foo' must be a non-empty string`
* `ERROR: deps for 'foo' must be a list`
* `ERROR: deps for 'foo' must contain strings or dicts`
* `ERROR: priority for 'foo' must be an integer`

mean your YAML frontmatter is malformed or one of the fields has the wrong type. Fix the `id`, `outputs`, `deps`, or `priority` fields in the `.hurl` file.

### "ERROR: alias template 'X' not found (used as 'Y')"

An alias refers to a template that was not loaded from the provided files. Make sure the aliased `.hurl` file is included in the same run and that the template name matches the source file's `id` or stem.

### "ERROR: 'foo' depends on 'bar' but no .hurl file or alias defines id: bar"

Your declared dependency does not exist in the directories that were scanned. Either add the missing `.hurl` file next to the one that declares the dependency, or correct the dependency name. If you ran with `--no-deps`, the dependency file must also be listed on the command line.

### "ERROR: .hurl file not found: ..."

One of the paths passed on the command line does not point to an existing file. Check the spelling and the working directory.

### "SKIPPED: <node_id> (failed dependency: ...)"

The node was not executed because one of its upstream dependencies failed. Fix the listed dependency first; the skipped node will run once its inputs are available.

### "Circular dependency detected"

Your `deps` create an infinite loop. Check your frontmatter to ensure you aren't accidentally requiring a file that eventually requires the current file.

### "FAILED: <node_id>\nHurl timed out after 300 seconds"

A single Hurl execution took longer than the built-in 5-minute timeout. Either optimize that test, remove long-running steps, or run it manually in Hurl to diagnose why it hangs.

### "FAILED: <node_id>\n<stderr from hurl>"

The Hurl command itself failed. This is usually a failed assertion, invalid request, or runtime error inside the `.hurl` file. Use the Hurl error output to fix the failing test.

### "KNOWN FAILURE: <node_id> [<name>] ..."

The node failed, and the failure matched one of its declared `known_failures`. The run is not marked failed. Hurl's error output follows the line so the evidence stays in the log; the CTRF report carries the entry name in `tags`. Run with `--strict` to make it fail again, or remove the entry once the underlying cause is fixed.

### "SKIPPED: <node_id> (known failure upstream: ...)"

An upstream node was tolerated as a known failure and produced no outputs, so this node had nothing to run with. It does not fail the run. Fix or wait out the upstream flake.

### "FAILED: <node_id>\nknown failure '<name>' expired on <date>"

The failure would have matched a declared entry, but that entry's `until` date has passed. Either the flake is still real and the date needs moving with a fresh justification, or the tolerance should be removed.

### "ERROR: known_failures[<i>] for '<node_id>' ..."

A `known_failures` entry is malformed: missing `name` or `reason`, no signature field, an invalid regex, a non-date `until`, or a duplicated name. Nothing runs until it is fixed.

### "FAILED: <node_id>\nMissing expected outputs: ..."

Your node declared `outputs`, but the report did not contain those capture names. Check that the `Captures` section in the `.hurl` file defines all expected variables and that the response includes the expected JSON or text path.

### "ERROR: <node_id>: report not found; [...] not captured"

Hurl did not produce a report for that node, usually because the command failed or the report directory was not written. Inspect the earlier failure message and confirm Hurl was invoked with `--report-json` correctly.

### "ERROR: <node_id>: invalid report JSON; [...] not captured"

The generated report could not be parsed as JSON. This usually indicates a corrupted or incomplete Hurl report file. Re-run the node to see if the failure is reproducible.

### Diagram generation errors

* `Diagram output already exists and overwrite is disabled` — use `--diagram-overwrite` to replace the file.
* `Diagram output is a directory` — provide a file path, not a directory.

If you pipe diagram output to another tool using `--diagram-output -`, a broken pipe may happen when the receiver closes early; this is not a failure in the orchestrator itself.
