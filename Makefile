.PHONY: check lint fix test bootstrap coverage-diff

check: lint test

lint:
	@yamllint -c .yamllint.yml . || (echo "Run 'make fix'" && exit 1)
	@conftest test docker-compose.prod.yml -p .harness/policy/compose/ --all-namespaces --data .harness/conftest-data.json || (echo "Compose policy violation (prod)" && exit 1)
	@conftest test docker-compose.yml -p .harness/policy/compose/ -n compose.services -n compose.escaping || (echo "Compose policy violation (dev)" && exit 1)
	@conftest test g3proxy/Dockerfile --parser dockerfile -p .harness/policy/dockerfile/ --all-namespaces || (echo "Dockerfile policy violation (g3proxy)" && exit 1)
	@conftest test health-checker/Dockerfile --parser dockerfile -p .harness/policy/dockerfile/ --all-namespaces || (echo "Dockerfile policy violation (health-checker)" && exit 1)
	@conftest test proxy-scanner/Dockerfile --parser dockerfile -p .harness/policy/dockerfile/ --all-namespaces || (echo "Dockerfile policy violation (proxy-scanner)" && exit 1)
	@conftest test .gitignore -p .harness/policy/gitignore/ --all-namespaces || (echo "Gitignore policy violation" && exit 1)
	@$(MAKE) -C proxy-scanner lint

fix:
	@$(MAKE) -C proxy-scanner fix
	@$(MAKE) lint

test:
	@$(MAKE) -C proxy-scanner test

bootstrap:
	@command -v conftest >/dev/null || (echo "Install conftest: brew install conftest" && exit 1)
	@command -v yamllint >/dev/null || (echo "Install yamllint: brew install yamllint" && exit 1)
	@command -v hadolint >/dev/null || (echo "Install hadolint: brew install hadolint" && exit 1)
	@$(MAKE) -C proxy-scanner bootstrap
	@if command -v prek >/dev/null; then prek install; \
	elif command -v pre-commit >/dev/null; then pre-commit install; \
	else echo "Install prek: brew install prek"; exit 1; fi
	@echo "Bootstrap complete"

coverage-diff:
	@$(MAKE) -C proxy-scanner coverage-diff
