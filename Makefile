# Sahana developer task runner.
# Backend targets run through uv; frontend targets through npm.

API_DIR := apps/api
WEB_DIR := apps/web

.DEFAULT_GOAL := help
.PHONY: help install lint format typecheck test up down logs ps clean

help: ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  %-12s %s\n", $$1, $$2}'

install: ## Install backend (uv) and frontend (npm) dependencies
	cd $(API_DIR) && uv sync --extra dev
	cd $(WEB_DIR) && npm ci

lint: ## Lint backend (ruff) and frontend (eslint)
	cd $(API_DIR) && uv run ruff check
	cd $(API_DIR) && uv run ruff format --check
	cd $(WEB_DIR) && npm run lint
	cd $(WEB_DIR) && npm run format:check

format: ## Auto-format backend (ruff) and frontend (prettier)
	cd $(API_DIR) && uv run ruff format
	cd $(API_DIR) && uv run ruff check --fix
	cd $(WEB_DIR) && npm run format

typecheck: ## Type-check backend (mypy --strict) and frontend (tsc)
	cd $(API_DIR) && uv run mypy --strict src
	cd $(WEB_DIR) && npm run build

test: ## Run the backend test suite
	cd $(API_DIR) && uv run pytest

up: ## Build and start the container stack in the background
	docker compose up --build -d

down: ## Stop and remove the container stack
	docker compose down

logs: ## Follow container logs
	docker compose logs -f

ps: ## Show container status
	docker compose ps

clean: ## Remove build artefacts and caches
	rm -rf $(API_DIR)/.venv $(API_DIR)/.pytest_cache $(API_DIR)/.mypy_cache $(API_DIR)/.ruff_cache
	rm -rf $(WEB_DIR)/dist $(WEB_DIR)/node_modules
	find $(API_DIR) -type d -name __pycache__ -prune -exec rm -rf {} +
