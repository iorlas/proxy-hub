# ── Full quality gate ──
check: lint test

# ── Lint: check only — safe for AI, CI, pre-commit. Never modifies files. ──
lint:
	@uv run ruff format --check || (echo "Formatting issues found. Run 'make fix' to auto-fix." && exit 1)
	@uv run ruff check || (echo "Lint issues found. Fixable ones can be resolved with 'make fix'." && exit 1)
	@uv run ty check
	@uv run yamllint -s ../.yamllint.yml .
	@uv run python scripts/check-json.py
	@uv run python scripts/check-file-length.py
	@uv run pip-audit || (echo "Dependency vulnerabilities found. Review with 'uv run pip-audit' and update affected packages." && exit 1)

# ── Fix: auto-fix, then verify with lint. ──
fix:
	uv run ruff check --fix
	uv run ruff format
	$(MAKE) lint

# ── Tests ──
test:
	uv run pytest tests/

coverage-diff:
	uv run diff-cover coverage.xml --compare-branch=origin/main --fail-under=95

# ── Bootstrap (idempotent) ──
bootstrap:
	uv sync
	@command -v prek >/dev/null 2>&1 && prek install || (command -v pre-commit >/dev/null 2>&1 && pre-commit install || echo "⚠ Install prek: brew install prek")
	@echo "✓ Dev environment ready. Run 'make lint' to verify."
