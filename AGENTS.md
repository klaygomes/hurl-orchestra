# Agent guide

Read [llms.txt](llms.txt) for the documentation index and the published `llms-full.txt` link.

## Project

hurl-orchestra is a Python tool that runs Hurl files as a dependency graph. The package is in `src/hurl_orchestra/` and the tests are in `tests/`. The documentation is a VitePress site in `docs/`.

## Commands

| Command | Purpose |
|---|---|
| `make check` | Lint, format check, type check and test with a 98% coverage gate. |
| `make test` | Run the tests and write the HTML coverage report. |
| `make coverage` | Run the tests and serve the HTML coverage report. |
| `make docs-cli` | Regenerate `docs/reference/cli.generated.md` from the parser. |
| `make docs-check` | Check the snippets, the prose with Vale and the VitePress build. |

Use `.venv/bin/python`, `.venv/bin/pytest`, `.venv/bin/ruff` and `.venv/bin/mypy` when you do not use `make`.

## Code rules

- Python 3.11 or later. Keep mypy strict: type each function and each variable that needs a type.
- Line length is 88. Ruff checks `E`, `W`, `F`, `I`, `B`, `C4`, `UP` and `C90`.
- hurl-orchestra supports Hurl 7.1.0 and later and tests 7.1.0 and 8.1.0.
- hurl-orchestra owns `--test`, `--report-json` and `--secrets-file`. Reject a user copy with a clear error.
- Captured values travel as Hurl secrets. The `--inject-as-variables` flag is the only exception.
- Never retry a Hurl exit code 1 (command line) or 2 (parse).
- File mode without `--no-deps` resolves sibling deps. With `--no-deps`, every dep must be listed or validation stops the run. Test both paths.

## Test rules

- Mock `subprocess.run` with `CompletedProcess` and a real hurl exit code: 4 for a failed assertion and 3 for a runtime error.
- The autouse fixture in `tests/conftest.py` patches the Hurl version check. Override `detect_hurl_version` in a test that needs a different version.
- Add a unit test for each behavior. Add an integration test in `tests/test_integration.py` for a change that depends on the real Hurl binary.
- Keep the total coverage at 98% or more.

## Documentation rules

- Write in ASD-STE100 Simplified Technical English. Read [CONTRIBUTING.md](CONTRIBUTING.md#write-in-simplified-technical-english).
- Vale reports each error. Use the active voice, short sentences and no `-ing` form.
- Put each sample `.hurl` file in `docs/snippets/<name>/` and include it with the snippet syntax.
- Add a new page to the sidebar in `docs/.vitepress/config.ts`. The build then adds the page to `llms.txt` and `llms-full.txt`.
- Run `make docs-check` before you send a change.
