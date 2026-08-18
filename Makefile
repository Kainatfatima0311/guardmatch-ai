# GuardMatch AI — canonical task list for the whole repository.
#
# The repository holds two runtimes. Rather than a task runner per directory,
# every target lives here and changes directory itself, so a contributor never
# has to know which half of the repo a command belongs to. This is also the file
# CI mirrors, which is what makes a passing `make check` mean a passing pipeline.

.DEFAULT_GOAL := help
.PHONY: help install lint format typecheck test test-fast gates check \
        generate-data train audit serve \
        web-install web-dev web-lint web-typecheck web-test web-build \
        docker-build docker-up clean

CONDA_ENV := guardmatch
BACKEND   := backend
FRONTEND  := frontend

RUN  := conda run -n $(CONDA_ENV) --no-capture-output
BRUN := cd $(BACKEND) && $(RUN)
WRUN := cd $(FRONTEND) &&

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------------

install:  ## Install the backend with dev extras and the spaCy model
	$(BRUN) pip install -e ".[dev]"
	$(BRUN) python -m spacy download en_core_web_sm

lint:  ## Run ruff checks on the backend
	$(BRUN) ruff check .

format:  ## Apply ruff formatting and fix what is auto-fixable
	$(BRUN) ruff format .
	$(BRUN) ruff check --fix .

typecheck:  ## Run mypy in strict mode
	$(BRUN) mypy src

test:  ## Run the full backend suite with coverage
	$(BRUN) pytest

test-fast:  ## Run the backend suite without slow tests
	$(BRUN) pytest -m "not slow"

gates:  ## Run only the fairness and leakage gates
	$(BRUN) pytest -m gate -v

generate-data:  ## Generate the synthetic dataset from the configured seed
	$(BRUN) guardmatch generate-data

train:  ## Train the ranker and write versioned artifacts
	$(BRUN) guardmatch train

audit:  ## Run the fairness audit against the active model
	$(BRUN) guardmatch audit

serve:  ## Run the API locally with reload
	$(BRUN) uvicorn guardmatch.api.app:app --reload --host 0.0.0.0 --port 8000

# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------

web-install:  ## Install frontend dependencies from the lockfile
	$(WRUN) npm ci

web-dev:  ## Run the frontend dev server against a local API on :8000
	$(WRUN) npm run dev

web-lint:  ## Run eslint on the frontend
	$(WRUN) npm run lint

web-typecheck:  ## Type check the frontend without emitting
	$(WRUN) npx tsc --noEmit

web-test:  ## Run the frontend unit tests
	$(WRUN) npm test

web-build:  ## Produce the standalone production build
	$(WRUN) npm run build

# ---------------------------------------------------------------------------
# Everything
# ---------------------------------------------------------------------------

check: lint typecheck test web-lint web-typecheck web-test web-build  ## Everything CI runs, locally

docker-build:  ## Build both container images
	docker build -t guardmatch-ai:0.1.0 $(BACKEND)
	docker build -t guardmatch-web:0.1.0 $(FRONTEND)

docker-up:  ## Run the full stack via docker compose
	docker compose up --build

clean:  ## Remove caches and build artifacts from both runtimes
	rm -rf $(BACKEND)/.pytest_cache $(BACKEND)/.mypy_cache $(BACKEND)/.ruff_cache \
	       $(BACKEND)/htmlcov $(BACKEND)/.coverage $(BACKEND)/coverage.xml \
	       $(BACKEND)/build $(BACKEND)/dist
	rm -rf $(FRONTEND)/.next $(FRONTEND)/out $(FRONTEND)/coverage \
	       $(FRONTEND)/*.tsbuildinfo
	find $(BACKEND) -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
