# Hurl Orchestrator

A dependency-aware task runner for [Hurl](https://hurl.dev). It allows you to treat API requests as a Directed Acyclic Graph (DAG), managing complex authentication flows and resource creation without redundant executions or manual variable passing.

## Core Philosophy

* **Explicit over Implicit**: Every dependency must be declared. This ensures that if a test fails, you know exactly which parent requirement was not met.
* **Namespaced Variables**: Outputs are tied to the ID of the node that produced them (`auth.token`), preventing variable collisions in large suites.
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

List the `id` of the producer in `deps`. Access the variable using the `id.variable` syntax.

```yaml
---
id: get_profile
deps: [auth]
---
GET https://api.com/profile
Authorization: Bearer {{auth.token}}
HTTP 200
```

---

## 3. Running

```bash
hurl-orchestra              # runs against the current directory
hurl-orchestra ./tests      # runs against a specific directory
```

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
Authorization: {{admin_login.token}}
```

### Global Environment (`.env`)

The orchestrator automatically detects a `.env` file in the test directory. Variables defined here are available to **all** Hurl files without being declared in the frontmatter.

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
   * Runs tests in the exact order required.
   * Captures output variables into a shared pool.
   * Injects required variables into downstream tests via Hurl's `--variable` flag.
   * **Stops immediately** if any test fails to prevent cascade failures.

---

## 6. Troubleshooting

### "Circular dependency detected"

Your `deps` create an infinite loop. Check your frontmatter to ensure you aren't accidentally requiring a file that eventually requires the current file.

### "FAILED: node_id"

The orchestrator will output the `stderr` from the Hurl binary. This usually means an assertion failed within the `.hurl` file itself or a network error occurred.

### "Node depends on missing node"

Ensure the `id` in your `deps` matches the `id` defined in the target Hurl file's frontmatter (or its filename stem if no `id` is provided).
