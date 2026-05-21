# OpenContext Runtime Makefile
# Common development tasks

.PHONY: help install dev test lint format type-check clean docs e2e validate

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
	@echo "  make clean      Clean build artifacts"
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

ci-check:
	opencontext ci-check run

clean:
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	rm -rf **/__pycache__
	rm -rf packages/**/build
	rm -rf packages/**/dist
	rm -rf packages/**/*.egg-info
	find . -name "*.pyc" -delete
	find . -name ".DS_Store" -delete
