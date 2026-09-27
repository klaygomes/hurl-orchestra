.DEFAULT_GOAL := check

VENV := .venv
BIN  := $(VENV)/bin

.PHONY: lint format typecheck test check build publish publish-test docs docs-cli docs-check

lint:
	$(BIN)/ruff check src

format:
	$(BIN)/ruff format src

typecheck:
	$(BIN)/mypy src

test:
	$(BIN)/pytest --cov=hurl_orchestra --cov-report=term-missing --cov-report=html tests/ && \
	$(BIN)/python scripts/serve.py htmlcov

check: lint format typecheck test

build: check
	$(BIN)/python -m build

publish-test: build
	$(BIN)/twine upload --repository testpypi dist/*

publish: build
	$(BIN)/twine upload dist/*

docs:
	pnpm docs:dev

docs-cli:
	$(BIN)/python scripts/cli_reference.py

docs-check: docs-cli
	for dir in docs/snippets/*/; do \
		case $$dir in *ci/|*agents/) continue;; esac; \
		$(BIN)/hurl-orchestra --dry-run $$dir > /dev/null || exit 1; \
	done
	node_modules/.bin/vale CONTRIBUTING.md docs
	pnpm docs:build
