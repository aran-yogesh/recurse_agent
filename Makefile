.PHONY: help install sync test lint lint-fix format typecheck check run webhook poller clean

UV ?= uv

help:
	@echo "Available targets:"
	@echo "  install     Install all dependencies (including dev group)"
	@echo "  sync        Alias for install"
	@echo "  test        Run pytest"
	@echo "  lint        Run ruff lint checks"
	@echo "  lint-fix    Run ruff with --fix"
	@echo "  format      Format code with ruff"
	@echo "  typecheck   Run mypy"
	@echo "  check       Run lint + typecheck + test"
	@echo "  run         Run CLI (pass ARGS=...)"
	@echo "  webhook     Run FastAPI webhook server with reload"
	@echo "  poller      Run GitHub poller"
	@echo "  clean       Remove caches and build artifacts"

install sync:
	$(UV) sync --group dev

test:
	$(UV) run pytest

lint:
	$(UV) run ruff check .

lint-fix:
	$(UV) run ruff check --fix .

format:
	$(UV) run ruff format .

typecheck:
	$(UV) run mypy .

check: lint typecheck test

run:
	$(UV) run python main.py $(ARGS)

webhook:
	$(UV) run uvicorn webhook:app --reload

poller:
	$(UV) run python poller.py

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache build dist *.egg-info
	find . -type d -name __pycache__ -not -path "./.venv/*" -not -path "./electron-app/*" -exec rm -rf {} + 2>/dev/null || true
