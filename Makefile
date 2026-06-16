# OpenContext Runtime Makefile
# Common development tasks

.PHONY: help install dev test lint format type-check clean docs e2e validate binary ci ci-clean

PYTHON ?= python3
PIP ?= $(PYTHON) -m pip
PYTEST ?= $(PYTHON) -m pytest
RUFF ?= $(PYTHON) -m ruff
MYPY ?= $(PYTHON) -m mypy

help:
	@echo "OpenContext Runtime - Development Tasks"
	@echo ""
	@echo "  make install    Install production dependencies"
	@echo "  make dev        Install development dependencies"
	@echo "  make test       Run test suite"
	@echo "  make lint       Run linter"
	@echo "  make format     Format code"
	@echo "  make type-check Run type checker"
	@echo "  make validate   Run all validation (test + lint + type-check)"
	@echo "  make docs       Build documentation"
	@echo "  make e2e        Run end-to-end tests"
	@echo "  make binary     Build single-file dist/opencontext.pyz"
	@echo "  make clean      Clean build artifacts"
	@echo "  make ci         Reproduce the GitHub test pipeline EXACTLY (pinned, fresh venv)"
	@echo "  make ci-check   Run CI checks"

install:
	$(PIP) install -e packages/opencontext_core -e packages/opencontext_cli

dev:
	$(PIP) install -e packages/opencontext_core -e packages/opencontext_cli -e packages/opencontext_api
	$(PIP) install pytest ruff mypy rich prompt-toolkit

test:
	$(PYTEST) -q

lint:
	$(RUFF) check .

format:
	$(RUFF) format .

type-check:
	$(MYPY) packages/opencontext_core

validate: lint type-check test
	@echo ""
	@echo "All validation passed!"

docs:
	@echo "Documentation is in docs/"
	@echo "Read docs/README.md for navigation"

e2e:
	bash scripts/e2e-validate.sh

binary:
	$(PYTHON) scripts/build_binary.py

CI_VENV ?= .ci-venv

# Reproduce the GitHub `test` job byte-for-byte: a fresh venv with the pinned
# toolchain (requirements-ci.txt — the same file CI installs) and the same steps,
# in the same order. If `make ci` is green, the pipeline is green. Requires `uv`.
ci:
	uv venv $(CI_VENV)
	uv pip install --python $(CI_VENV)/bin/python -q -r requirements-ci.txt
	uv pip install --python $(CI_VENV)/bin/python -q \
		-e packages/opencontext_core \
		-e packages/opencontext_profiles \
		-e packages/opencontext_providers \
		-e packages/opencontext_cli \
		-e packages/opencontext_api
	$(CI_VENV)/bin/ruff check .
	$(CI_VENV)/bin/ruff format --check .
	$(CI_VENV)/bin/mypy packages/opencontext_core
	$(CI_VENV)/bin/python -m pytest
	$(CI_VENV)/bin/python -m build packages/opencontext_core
	$(CI_VENV)/bin/python -m build packages/opencontext_profiles
	$(CI_VENV)/bin/python -m build packages/opencontext_providers
	$(CI_VENV)/bin/python -m build packages/opencontext_cli
	$(CI_VENV)/bin/python -m build packages/opencontext_api
	@echo ""
	@echo "make ci passed — matches the GitHub test pipeline."

ci-clean:
	rm -rf $(CI_VENV)

ci-check:
	opencontext ci-check run

clean:
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	rm -rf **/__pycache__
	rm -rf packages/**/build
	rm -rf dist
	rm -rf packages/**/dist
	rm -rf packages/**/*.egg-info
	find . -name "*.pyc" -delete
	find . -name ".DS_Store" -delete
