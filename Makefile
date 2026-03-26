.PHONY: check lint fix test bootstrap coverage-diff

check: lint test

lint:
	@agent-harness lint
	@$(MAKE) -C proxy-api lint

fix:
	@agent-harness fix
	@$(MAKE) -C proxy-api fix

test:
	@$(MAKE) -C proxy-api test

bootstrap:
	@command -v agent-harness >/dev/null || (echo "Install agent-harness: uv tool install agent-harness" && exit 1)
	@$(MAKE) -C proxy-api bootstrap
	@if command -v prek >/dev/null; then prek install; \
	elif command -v pre-commit >/dev/null; then pre-commit install; \
	else echo "Install prek: brew install prek"; exit 1; fi
	@echo "Bootstrap complete"

coverage-diff:
	@$(MAKE) -C proxy-api coverage-diff
