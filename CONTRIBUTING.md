# Contribute to hurl-orchestra

## Prepare the project

You need Python 3.11 or later, Node.js 24 and pnpm.

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
pnpm install
```

## Check a change

| Command | Check |
|---|---|
| `make check` | Lint, format, types and tests of the Python package. |
| `make docs` | Starts the documentation site on your computer. |
| `make docs-check` | Prose, samples, the CLI table and the site build. |

## Change the command line

The options table in `docs/reference/cli.generated.md` comes from the parser. After a change to an option, run:

```bash
.venv/bin/python scripts/cli_reference.py
```

CI fails if the table and the parser do not agree.

## Write the documentation

- Put each sample `.hurl` file in `docs/snippets/<name>/`. Include it with `<<< @/snippets/<name>/<file>.hurl{hurl}`.
- Keep each sample directory a valid suite. CI runs `hurl-orchestra --dry-run` on each directory.
- Write one procedure on each how-to page.
- Describe the current behavior. Do not write the history of a change in the documentation.

## Write in Simplified Technical English

Write the documentation and this file in ASD-STE100 Simplified Technical English (STE). Vale checks these rules:

| Rule | Limit |
|---|---|
| Sentence length | A maximum of 25 words. |
| Paragraph length | A maximum of 6 sentences. |
| Voice | Active voice only. |
| Verb forms | No `-ing` forms, except in approved technical names. |
| Contractions | Write `do not`, not `don't`. |
| Phrasal verbs | Write `start`, not `set up` or `turn on`. |
| Substitutions | Write `use`, not `utilize`. Write `before`, not `prior to`. |
| Glossary | Each technical name must be in the approved list. |

The approved technical names are in `.vale/styles/config/vocabularies/STE/accept.txt`. To add a name, add it to this file in the same pull request.

The README is the sales page of the project. Vale does not check it.

## Send a pull request

1. Make a branch from `main`.
2. Make your changes and add tests.
3. Run `make check` and `make docs-check`.
4. Open the pull request.
