.DEFAULT_GOAL := check

VENV := .venv
BIN  := $(VENV)/bin

.PHONY: lint format typecheck test check build publish publish-test

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
