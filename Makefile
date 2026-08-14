.DEFAULT_GOAL := help
.PHONY: help install lint format typecheck test test-fast gates generate-data train audit serve docker-build docker-up clean

CONDA_ENV := guardmatch
RUN := conda run -n $(CONDA_ENV) --no-capture-output

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install:  ## Install the package with dev extras and the spaCy model
	$(RUN) pip install -e ".[dev]"
	$(RUN) python -m spacy download en_core_web_sm

lint:  ## Run ruff checks
	$(RUN) ruff check .

format:  ## Apply ruff formatting and fix what is auto-fixable
	$(RUN) ruff format .
	$(RUN) ruff check --fix .

typecheck:  ## Run mypy in strict mode
	$(RUN) mypy src

test:  ## Run the full test suite with coverage
	$(RUN) pytest

test-fast:  ## Run the test suite without slow tests
	$(RUN) pytest -m "not slow"

gates:  ## Run only the fairness and leakage gates
	$(RUN) pytest -m gate -v

generate-data:  ## Generate the synthetic dataset from the configured seed
	$(RUN) guardmatch generate-data

train:  ## Train the ranker and write versioned artifacts
	$(RUN) guardmatch train

audit:  ## Run the fairness audit against the active model
	$(RUN) guardmatch audit

serve:  ## Run the API locally with reload
	$(RUN) uvicorn guardmatch.api.app:app --reload --host 0.0.0.0 --port 8000

check: lint typecheck test  ## Everything CI runs, locally

docker-build:  ## Build the container image
	docker build -t guardmatch-ai:0.1.0 .

docker-up:  ## Run the service via docker compose
	docker compose up --build

clean:  ## Remove caches and build artifacts
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage coverage.xml build dist
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
