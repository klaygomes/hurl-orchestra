| Option | Default | Description |
|---|---|---|
| `paths` | `.` | A directory with .hurl files, or one or more .hurl files. The default is the current directory. |
| `--report-zip` `FILE` | `report.zip` | Write the hurl reports of all nodes to this zip file. |
| `--report-ctrf` `FILE` | - | Also write a CTRF JSON report to this file. |
| `--env-file` `FILE` | - | Give this variables file to each hurl call. The default is .env in the given directory, or in the current directory for files. |
| `--no-deps` | - | Run only the listed .hurl files. Do not add their declared deps from the same directory. |
| `--dry-run` | - | Show the execution plan. Do not run hurl. |
| `--json` | - | With --dry-run, write the plan as JSON for scripts and AI agents. |
| `--strict` | - | Make a failure that matches known_failures fail the run. |
| `--diagram` | - | Write a Mermaid diagram of the graph. Do not run the tests. |
| `--diagram-output` `FILE` | `diagram.md` | Write the diagram to this file. Use '-' for stdout. |
| `--diagram-overwrite` | - | Replace the diagram file if it exists. |
