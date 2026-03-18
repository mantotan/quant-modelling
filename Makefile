.PHONY: install dev test lint type-check format docker-up docker-down clean benchmark

install:
	uv sync

dev:
	uv sync --extra dev

test:
	uv run pytest tests/unit -v

test-all:
	uv run pytest -v

test-integration:
	uv run pytest tests/integration -v -m integration

benchmark:
	uv run pytest tests/benchmark -v -m benchmark --benchmark-only

lint:
	uv run ruff check src/ tests/

lint-fix:
	uv run ruff check --fix src/ tests/

type-check:
	uv run mypy src/qm/

format:
	uv run ruff format src/ tests/

docker-up:
	docker compose up -d

docker-down:
	docker compose down

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true

# Rust fast path
rust-build:
	cd crates/qm-fast && maturin develop --release

rust-test:
	cd crates/qm-fast && cargo test

rust-bench:
	cd crates/qm-fast && cargo bench
