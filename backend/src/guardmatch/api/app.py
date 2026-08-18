"""FastAPI application.

The model is loaded once during lifespan startup, with its checksums verified
and its feature contract checked against the code. **Startup fails loudly** when
any of that goes wrong, rather than starting an instance that returns confident
answers from an unverified model. A crash gets noticed and restarted; a
silently-degraded service does not.

The spaCy pipeline is warmed at startup too. Left cold, the first request after
every deploy would pay several seconds of model loading — a latency spike that
looks like a mystery in production and is entirely avoidable.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.requests import Request

from guardmatch.api.dependencies import ServiceState
from guardmatch.api.middleware import ObservabilityMiddleware
from guardmatch.api.routes import health, score
from guardmatch.core.config import get_settings
from guardmatch.core.exceptions import (
    GuardMatchError,
    ModelNotLoadedError,
    ParsingError,
    ProtectedAttributeError,
)
from guardmatch.core.logging import configure_logging, get_logger
from guardmatch.core.metrics import initialise_metrics, set_model_info
from guardmatch.explain.shap_explainer import Explainer
from guardmatch.parsing.extractor import get_nlp
from guardmatch.ranking.predict import Ranker
from guardmatch.registry.artifacts import load_model

logger = get_logger(__name__)

DESCRIPTION = """
Ranks security guard applicants against a job posting's requirements, with a
per-candidate explanation of the result.

**This is a shortlisting aid, not a hiring decision.** Scores are relative to a
single posting and are not probabilities. A human reviewer remains responsible
for every outcome.
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Load and verify the model, then warm the NLP pipeline."""
    configure_logging()
    initialise_metrics()

    settings = get_settings()
    state = ServiceState(model_version=settings.model_version)
    app.state.service = state

    logger.info(
        "startup_loading_model",
        model_version=settings.model_version,
        model_dir=str(settings.model_dir),
    )

    try:
        loaded = load_model(settings.model_dir, settings.model_version)
    except GuardMatchError as exc:
        state.detail = str(exc)
        set_model_info(settings.model_version, loaded=False)
        logger.error("startup_model_load_failed", error=str(exc))
        # Re-raised deliberately. An instance that cannot verify its own model
        # must not accept traffic, and a hard failure is what makes that
        # visible to whatever supervises the process.
        raise

    state.loaded = loaded
    state.ranker = Ranker(loaded.booster, loaded.feature_names)
    state.explainer = Explainer(loaded.booster, loaded.feature_names)

    # Warm the tokeniser so the first real request does not pay for it.
    get_nlp()

    state.ready = True
    state.detail = None
    set_model_info(settings.model_version, loaded=True)

    logger.info(
        "startup_complete",
        model_version=loaded.version,
        git_sha=loaded.metadata.git_sha,
        features=len(loaded.feature_names),
    )

    yield

    logger.info("shutdown", model_version=loaded.version)


def create_app() -> FastAPI:
    """Build the application."""
    app = FastAPI(
        title="GuardMatch AI — Scoring API",
        description=DESCRIPTION,
        version="0.1.0",
        lifespan=lifespan,
    )

    # Set before startup so /health and /ready answer correctly even if the
    # lifespan has not run, which is the case in unit tests.
    app.state.service = ServiceState(model_version=get_settings().model_version)

    app.add_middleware(ObservabilityMiddleware)

    app.include_router(health.router, tags=["operations"])
    app.include_router(score.router, tags=["scoring"])

    @app.exception_handler(ModelNotLoadedError)
    async def handle_not_loaded(_: Request, exc: ModelNotLoadedError) -> JSONResponse:
        # Retryable: the caller did nothing wrong.
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(ParsingError)
    async def handle_parsing(_: Request, exc: ParsingError) -> JSONResponse:
        # The input is unusable, which is a client error rather than a fault.
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(ProtectedAttributeError)
    async def handle_protected(_: Request, exc: ProtectedAttributeError) -> JSONResponse:
        # Logged at error level rather than returned quietly: a protected
        # attribute reaching the feature layer is a defect in the system, not a
        # bad request, and it must be investigated rather than retried.
        logger.error("protected_attribute_rejected", error=str(exc))
        return JSONResponse(
            status_code=500,
            content={"detail": "request rejected by the protected attribute guard"},
        )

    return app


app = create_app()
