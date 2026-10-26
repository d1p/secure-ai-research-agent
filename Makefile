PY ?= .venv/bin/python
RUFF ?= .venv/bin/ruff

.PHONY: install-dev test lint fmt format-check privacy bench bench-live up down verify docs-lint compose-config

install-dev:
	$(PY) -m pip install -r requirements-dev.txt

test:
	$(PY) -m pytest -q

lint:
	$(RUFF) check .

fmt:
	$(RUFF) format .

format-check:
	$(RUFF) format --check .

privacy:
	$(PY) scripts/check_privacy.py

bench:
	$(PY) scripts/bench_reader.py

bench-live:
	$(PY) scripts/bench_reader.py --grade

up:
	docker compose up -d

down:
	docker compose down

compose-config:
	@if command -v docker >/dev/null 2>&1; then \
		docker compose --env-file .env.example config -q; \
	else \
		echo "docker not installed; skipping compose config"; \
	fi

docs-lint:
	@if command -v npx >/dev/null 2>&1; then \
		npx --yes markdownlint-cli2 "**/*.md" "#node_modules" "#.venv/**" "#tests/fixtures/**"; \
	else \
		echo "npx not installed; skipping markdownlint"; \
	fi

verify: lint format-check privacy test compose-config
