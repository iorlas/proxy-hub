test:
	uv run pytest tests/

lint:
	uv run ruff check proxy_scanner tests
	uv run ruff format --check proxy_scanner tests
	uvx ty check proxy_scanner tests

coverage-diff:
	uv run diff-cover coverage.xml --compare-branch=origin/main --fail-under=95
