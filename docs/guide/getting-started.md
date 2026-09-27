# Install and run

This tutorial makes a suite of two Hurl files. The first file sends a login request and captures a token. The second file uses the token. At the end, you run the suite and read the report.

## Before you start

You need:

- Python 3.11 or a later version.
- [Hurl](https://hurl.dev/docs/installation.html) on your `PATH`.

## 1. Install hurl-orchestra

```bash
pip install hurl-orchestra
hurl --version
```

The second command must show the Hurl version. If it shows an error, install Hurl first.

## 2. Write the first file

Make a directory with the name `tests`. Put this file in it with the name `auth.hurl`:

<<< @/snippets/getting-started/auth.hurl{hurl}

The frontmatter between the two `---` lines is YAML. The `id` is the name of the node. The `outputs` list tells hurl-orchestra which captures to share.

## 3. Write the second file

Put this file in the same directory with the name `profile.hurl`:

<<< @/snippets/getting-started/profile.hurl{hurl}

The `deps` list tells hurl-orchestra to run `auth` first. The file gets the `token` capture of `auth` with the name `auth_token`.

## 4. Give the global variables

Put a `.env` file in the `tests` directory. When you run the directory, hurl-orchestra gives this file to each Hurl call:

```properties
base_url=https://staging.example.com
password=use-a-secret-store
```

::: warning
Do not commit a `.env` file with real secrets. In CI, write the file from your secret store before the run.
:::

## 5. Examine the plan

```bash
hurl-orchestra --dry-run ./tests
```

```text
Plan: 2 node(s)
  wave 1: auth
  wave 2: profile
```

The dry run does not call Hurl. Use it after each change to the frontmatter.

## 6. Run the suite

```bash
hurl-orchestra ./tests
```

```text
Variables file: tests/.env
SUCCESS: auth [captured: token]
SUCCESS: profile [injected: auth_token]
Report saved to tests/report.zip
```

The command stops with exit code 0 when all nodes pass. It stops with exit code 1 when a node fails.

## Next steps

- Learn how the waves operate in [The graph](/concepts/graph).
- Let a coding agent write the next files. Read [Work with AI agents](/how-to/work-with-ai-agents).
- Show the results in a pull request. Read [Report in GitHub Actions](/how-to/report-in-github-actions).
