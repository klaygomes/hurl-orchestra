# Reports

Each run writes a zip file. You can also write a CTRF report for CI.

## The zip file

The zip file contains the Hurl JSON report of each node that ran. Each node has a directory with its ID as the name:

```text
report.zip
├── auth/
│   ├── report.json
│   └── store/
└── create_user/
    ├── report.json
    └── store/
```

hurl-orchestra writes the zip file after each run, also when a node fails. Thus you keep the evidence of the failure.

| Command | Report |
|---|---|
| `hurl-orchestra ./tests` | `tests/report.zip` |
| `hurl-orchestra` | `report.zip` in the current directory |
| `hurl-orchestra ./tests --report-zip ci.zip` | `tests/ci.zip` |

A relative path goes into the directory that you gave. An absolute path stays the same.

## The CTRF report

[CTRF](https://ctrf.io) is a JSON format for test results. Add `--report-ctrf` to write it:

```bash
hurl-orchestra ./tests --report-ctrf results.json
```

Each Hurl entry becomes one test. Skipped nodes and known failures also show in the report. For the full rules, read the [CTRF reference](/reference/ctrf).

## The execution plan as JSON

A dry run with `--json` writes the plan as JSON. Scripts and AI agents can read the waves, the dependencies and the variables of each node:

```bash
hurl-orchestra --dry-run --json ./tests
```

For the fields, read [Command line](/reference/cli#json-plan).
