# Makefile for cronjob-scheduler - Development and build tasks
# Prerequisites:
#   - uv: for Python dependency management
#   - Docker: for container builds and testing

.PHONY: help
# 📖 Show available commands
help:
	@printf "\nCronjob Scheduler Development Commands:\n\n"
	@awk '/^#/{c=substr($$0,3);next}c&&/^[[:alpha:]][[:alnum:]_-]+:/{printf "  \033[36m%-20s\033[0m %s\n", substr($$1,1,index($$1,":")-1),c}1{c=0}' $(MAKEFILE_LIST)
	@printf "\nRun 'make install' to get started!\n\n"

###############
# Setup Tasks #
###############

.PHONY: install
# 🚀 Install all dependencies (including dev dependencies)
install:
	@command -v uv >/dev/null 2>&1 || { echo "uv is required. See https://docs.astral.sh/uv/getting-started/installation/"; exit 1; }
	uv sync --all-extras

.PHONY: install-hooks
# 🪝 Install pre-commit hooks for automated checks
install-hooks:
	@command -v uvx >/dev/null 2>&1 || { echo "uv is required. See https://docs.astral.sh/uv/getting-started/installation/"; exit 1; }
	uvx pre-commit install
	@echo "✅ Pre-commit hooks installed! They'll run automatically on git commit."
	@echo "   Run 'uvx pre-commit run --all-files' to test them now."

######################
# Development Tasks #
######################

.PHONY: dev
# 🔧 Start development environment with docker-compose
dev:
	docker compose up --build

.PHONY: dev-bg
# 🔧 Start development environment in background
dev-bg:
	docker compose up --build -d

.PHONY: logs
# 📋 Show logs from running containers
logs:
	docker compose logs -f

.PHONY: down
# 🛑 Stop and remove development containers
down:
	docker compose down -v

#############
# Testing   #
#############

.PHONY: test
# 🧪 Run all tests with coverage
test:
	uv run pytest --cov=cronjob_scheduler --cov-report=term --cov-report=html

.PHONY: test-verbose
# 🧪 Run tests with verbose output and duration tracking
test-verbose:
	uv run pytest -v --durations=10 --cov=cronjob_scheduler --cov-report=term

.PHONY: test-fast
# ⚡ Run tests without coverage (faster)
test-fast:
	uv run pytest

.PHONY: test-watch
# 👀 Run tests in watch mode (requires pytest-watch)
test-watch:
	uv run ptw

#####################
# Code Quality      #
#####################

.PHONY: check
# 🧹 Run all checks (lint, format, typecheck)
check: lint format-check typecheck typos

.PHONY: lint
# 🔍 Lint code with ruff
lint:
	uv run ruff check

.PHONY: lint-fix
# 🔧 Lint and auto-fix issues
lint-fix:
	uv run ruff check --fix

.PHONY: format
# ✨ Format code with ruff
format:
	uv run ruff format

.PHONY: format-check
# 🔍 Check code formatting without changes
format-check:
	uv run ruff format --check

.PHONY: typecheck
# 🔍 Run type checking with pyright
typecheck:
	uv run pyright

.PHONY: typos
# 🔤 Check for typos in codebase
typos:
	@command -v uvx >/dev/null 2>&1 || { echo "uv is required."; exit 1; }
	uvx typos

.PHONY: typos-fix
# 🔧 Fix typos automatically
typos-fix:
	@command -v uvx >/dev/null 2>&1 || { echo "uv is required."; exit 1; }
	uvx typos --write-changes

##############
# Docker     #
##############

.PHONY: build
# 🐳 Build production Docker image
build:
	docker build -t cronjob-scheduler:latest --target production .

.PHONY: build-test
# 🐳 Build test Docker image
build-test:
	docker build -t cronjob-scheduler:test --target test .

.PHONY: docker-test
# 🧪 Run tests inside Docker container
docker-test: build-test
	docker run --rm cronjob-scheduler:test uv run pytest

.PHONY: docker-check
# 🧹 Run all checks inside Docker container
docker-check: build-test
	@echo "Running ruff check..."
	docker run --rm cronjob-scheduler:test uv run ruff check
	@echo "Running ruff format check..."
	docker run --rm cronjob-scheduler:test uv run ruff format --check
	@echo "Running pyright..."
	docker run --rm cronjob-scheduler:test uv run pyright
	@echo "✅ All Docker checks passed!"

.PHONY: security-scan
# 🔒 Scan Docker image for vulnerabilities
security-scan: build
	@command -v docker >/dev/null 2>&1 || { echo "Docker is required."; exit 1; }
	docker scout cves cronjob-scheduler:latest

##############
# Cleanup    #
##############

.PHONY: clean
# 🧹 Clean up generated files and caches
clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache .coverage htmlcov
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

.PHONY: clean-all
# 🧹 Clean everything including venv
clean-all: clean
	rm -rf .venv uv.lock
