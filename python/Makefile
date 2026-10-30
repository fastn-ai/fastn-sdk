# fastn SDK: development commands
#
# Quick reference:
#   make test          Run all tests
#   make test-sdk      Run SDK tests only
#   make test-cli      Run CLI tests only
#   make test-fast     Run CLI tests (fastest subset)
#   make test-file F=tests/cli/test_cli_commands.py   Run a single file
#   make lint          Run ruff linter
#   make typecheck     Run mypy type checker
#   make install-dev   Install package in dev mode with all extras

.PHONY: test test-sdk test-cli test-fast test-file lint typecheck install-dev clean

# Run all tests
test:
	python3 -m pytest tests/ -q

# Run SDK tests only (client, config, connector, exceptions, auth, oauth)
test-sdk:
	python3 -m pytest tests/sdk/ -q

# Run CLI tests only (commands, helpers, agent)
test-cli:
	python3 -m pytest tests/cli/ -q

# Run the fastest subset (CLI tests are pure unit tests, <1s)
test-fast:
	python3 -m pytest tests/cli/ -q --tb=short

# Run a single test file: make test-file F=tests/cli/test_cli_commands.py
test-file:
	python3 -m pytest $(F) -q -v

# Run tests with verbose output
test-verbose:
	python3 -m pytest tests/ -v

# Run ruff linter
lint:
	python3 -m ruff check fastn/ tests/

# Run mypy type checker
typecheck:
	python3 -m mypy fastn/

# Install in development mode
install-dev:
	pip install -e ".[dev]"

# Clean build artifacts and caches
clean:
	rm -rf build/ dist/ *.egg-info .pytest_cache .mypy_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
