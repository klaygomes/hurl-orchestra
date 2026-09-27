<div align="center">

<img src="https://www.estacouveflor.com/hurl-orchestra/logo-animated.svg" width="240" height="187" alt="A cauliflower conductor beats time while a dependency graph lights up one wave at a time">

# hurl-orchestra

**AI first API automation testing.**<br>
Your [Hurl](https://hurl.dev) files, played in order: a dependency graph that you and your coding agent can write, check and repair.

[![PyPI](https://img.shields.io/pypi/v/hurl-orchestra?color=7e23b3)](https://pypi.org/project/hurl-orchestra/) [![CI](https://github.com/klaygomes/hurl-orchestra/actions/workflows/ci.yml/badge.svg)](https://github.com/klaygomes/hurl-orchestra/actions/workflows/ci.yml) [![Docs](https://img.shields.io/badge/docs-estacouveflor.com-c63f75)](https://www.estacouveflor.com/hurl-orchestra/) [![License: MIT](https://img.shields.io/badge/license-MIT-fad30b)](LICENSE)

<a href="https://www.estacouveflor.com/hurl-orchestra/#the-score">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://www.estacouveflor.com/hurl-orchestra/readme/score-dark.webp">
    <img src="https://www.estacouveflor.com/hurl-orchestra/readme/score-light.webp" alt="The interactive score: create_cart fails, add_item and checkout are skipped, catalog still passes, and the terminal ends with exit code 1" width="100%">
  </picture>
</a>

<sub>Play with it on the <a href="https://www.estacouveflor.com/hurl-orchestra/#the-score">docs home page</a>: select a note, make it fail, watch the run.</sub>

</div>

## Three lines of YAML, and the order takes care of itself

```hurl
---
id: profile
deps: [auth]
---
GET {{base_url}}/profile
Authorization: Bearer {{auth_token}}
HTTP 200
```

```bash
pip install hurl-orchestra
hurl-orchestra ./tests
```

I built hurl-orchestra for the moment a Hurl suite outgrows one file. Each file says what it needs, and the tool works out the rest. It builds the graph, runs every independent file in parallel and hands each capture to the files that asked for it. A failure skips only its own branch, so one run shows every broken flow, not just the first one.

## Why teams pick it

- **AI first.** Plain-text requests, a few frontmatter fields, a JSON plan (`--dry-run --json`) and CTRF results. A coding agent can write a test, check the graph and read the failure without a human in the loop. There is no model inside and nothing to configure. [Hand it to your agent →](https://www.estacouveflor.com/hurl-orchestra/how-to/work-with-ai-agents)
- **Declared, not scripted.** `deps` replace the shell script that calls Hurl in the right order.
- **Captures that do not collide.** `auth` captures `token`, and its dependents get `auth_token`.
- **Honest about flaky failures.** `known_failures` tolerates a failure you understand, with a reason and an expiry date, and the report still shows it.
- **Polite under load.** A `retry` policy backs off exponentially, with jitter, and honours `Retry-After`.
- **Ready for CI.** A zip of every Hurl report on every run, and a CTRF file for the GitHub job summary.

## Under the hood

- **Small.** Python 3.11+, one dependency (`python-frontmatter`), and the standard library's `graphlib` and thread pool for the waves.
- **Safe with secrets.** Captured values reach Hurl through a private variables file per call, never the process list.
- **Fails early.** The whole graph is validated before the first request: unknown deps, cycles, wrong types, malformed tolerances and bad regexes.
- **Tested.** 250+ tests, with ruff and fully typed mypy checks in CI.
- **Docs written for people and agents.** Short procedures in Simplified Technical English, checked by Vale, and published as [`llms-full.txt`](https://www.estacouveflor.com/hurl-orchestra/llms-full.txt) too.

## Read the docs

[Get started](https://www.estacouveflor.com/hurl-orchestra/guide/getting-started) · [Concepts](https://www.estacouveflor.com/hurl-orchestra/concepts/graph) · [How-to](https://www.estacouveflor.com/hurl-orchestra/how-to/run-specific-files) · [Reference](https://www.estacouveflor.com/hurl-orchestra/reference/) · [Troubleshooting](https://www.estacouveflor.com/hurl-orchestra/troubleshooting)

## Say hi

If hurl-orchestra saved your suite from a pile of shell scripts, or you have a flow it cannot express yet, I would like to hear about it. Open an [issue](https://github.com/klaygomes/hurl-orchestra/issues), or read [CONTRIBUTING.md](CONTRIBUTING.md) to send a change.

<sub>[MIT License](LICENSE) · Made at [Esta couve flor](https://www.estacouveflor.com)</sub>
