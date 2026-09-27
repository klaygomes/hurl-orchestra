## API tests

The API tests are Hurl files in `tests/`. hurl-orchestra runs them as a dependency graph.
Documentation: https://www.estacouveflor.com/hurl-orchestra/llms-full.txt

Rules:

- Write one scenario in each `.hurl` file. Put the frontmatter between two `---` lines.
- Declare each dependency in `deps`. Do not copy a login request into a file.
- Declare each shared capture in `outputs`. Use it as `{producer id}_{output name}`.
- Put URLs and secrets in variables. Do not write a secret in a file.
- Do not add `known_failures` to hide a failure. Ask a human first.

Procedure after each change:

1. Run `hurl-orchestra --dry-run --json tests`. If `ok` is `false`, correct the error.
2. Run `hurl-orchestra tests --report-ctrf results.json`.
3. Read `tests/results.json`. Each failed test has the assertion and the actual value in `message`.
4. Correct the file or report the defect in the API. Then do step 1 again.
