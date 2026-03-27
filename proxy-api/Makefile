# ── Full quality gate ──
check: lint test

# ── Lint: check only — safe for AI, CI, pre-commit. Never modifies files. ──
lint:
	@agent-harness lint

# ── Fix: auto-fix, then verify with lint. ──
fix:
	@agent-harness fix

# ── Tests ──
test:
	uv run pytest tests/

coverage-diff:
	uv run diff-cover coverage.xml --compare-branch=origin/main --fail-under=95

# ── Bootstrap (idempotent) ──
bootstrap:
	uv sync
	@echo "Dev environment ready. Run 'make lint' to verify."
