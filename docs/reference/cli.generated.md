| Option | Default | Description |
|---|---|---|
| `paths` | `.` | A directory with .hurl files, or one or more .hurl files. The default is the current directory. |
| `--version` | - | Show the version of the package and stop. |
| `--report-zip` `FILE` | `report.zip` | Write the hurl reports of all nodes to this zip file. |
| `--report-ctrf` `FILE` | - | Also write a CTRF JSON report to this file. |
| `--env-file` `FILE` | - | Give this variables file to each hurl call. The default is .env in the given directory, or in the current directory for files. |
| `--secrets-file` `FILE` | - | Give this file of secrets to each hurl call with --secrets-file. Hurl redacts the values from its logs and reports. |
| `--inject-as-variables` | - | Give captured values to hurl as variables, not secrets. Hurl then writes them in its reports. Do not use it with real credentials. |
| `--no-deps` | - | Run only the listed .hurl files. Every declared dep must also be in the list, or the run stops with an error. Without this flag, hurl-orchestra adds the deps from the same directory. |
| `--dry-run` | - | Show the execution plan. Do not run hurl. |
| `--json` | - | With --dry-run, write the plan as JSON for scripts and AI agents. The plan lists the deps that file mode adds in 'resolved'. |
| `--strict` | - | Make a failure that matches known_failures fail the run. |
| `--timeout` `SECONDS` | `300` | Limit each Hurl process to this many seconds. The default is 300. |
| `--jobs` `N` | - | Run at most N Hurl processes at the same time. |
| `--diagram` | - | Write a Mermaid diagram of the graph. Do not run the tests. |
| `--diagram-output` `FILE` | `diagram.md` | Write the diagram to this file. Use '-' for stdout. |
| `--diagram-overwrite` | - | Replace the diagram file if it exists. |
