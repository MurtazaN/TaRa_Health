.PHONY: install lint typecheck test eval run up down logs clean

BACKEND := backend
COMPOSE := docker compose -f deployment/docker/compose.yaml

install:  ## Install the backend with dev tooling
	uv pip install -e "./$(BACKEND)[dev]"

lint:  ## Static lint
	ruff check $(BACKEND)/src $(BACKEND)/tests

typecheck:  ## Static type check
	cd $(BACKEND) && mypy

test:  ## Unit and integration tests (excludes behavior_evals)
	cd $(BACKEND) && python -m pytest -q --ignore=tests/behavior_evals

eval:  ## DeepEval quality gate. LOCAL ONLY - needs LM Studio running.
	cd $(BACKEND) && python -m pytest tests/behavior_evals -v

run:  ## Run the local server on the host
	cd $(BACKEND) && python -m tara.web_app

up:  ## Start the containerized stack
	$(COMPOSE) up -d

down:  ## Stop the containerized stack
	$(COMPOSE) down

logs:  ## Tail container logs
	$(COMPOSE) logs -f

clean:  ## Remove caches
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	rm -rf .pytest_cache .mypy_cache .ruff_cache
