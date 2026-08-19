"""Service state and request-scoped dependencies.

Everything expensive is built once at startup and held here: the model, the
SHAP explainer, the ranker and the spaCy pipeline. Building any of them
per request would put seconds of setup on the latency budget.

``ready`` is separate from "the object exists" on purpose. An instance whose
artifacts failed verification must not receive traffic, and an orchestrator can
only know that if readiness is reported distinctly from liveness.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import Depends, HTTPException, Request, status

from guardmatch.core.exceptions import ModelNotLoadedError
from guardmatch.explain.shap_explainer import Explainer
from guardmatch.ranking.predict import Ranker
from guardmatch.registry.artifacts import LoadedModel


@dataclass
class ServiceState:
    """Everything the service needs to answer a request."""

    model_version: str
    loaded: LoadedModel | None = None
    ranker: Ranker | None = None
    explainer: Explainer | None = None
    ready: bool = False
    #: Global SHAP importance, computed once on first request and held here.
    #: Computing it needs a representative sample of feature vectors, which means
    #: parsing CVs — around a second of work. Doing that per request would put
    #: that on the latency budget of a page a reviewer refreshes.
    importance: dict[str, float] | None = None
    detail: str | None = field(
        default="model has not finished loading",
        metadata={"note": "reason readiness is false, surfaced by /ready"},
    )

    def require_scoring(self) -> tuple[Ranker, Explainer]:
        """Return the components needed to score, or raise if unavailable.

        Deliberately does **not** require ``loaded``. The artifact bundle carries
        provenance and metrics, which ``/model-info`` needs and the scoring path
        does not. Demanding it here would couple scoring to metadata and make the
        service refuse work it is perfectly able to do.

        Raises:
            ModelNotLoadedError: Startup has not completed or verification failed.
        """
        if not self.ready or self.ranker is None or self.explainer is None:
            msg = self.detail or "model is not loaded"
            raise ModelNotLoadedError(msg)
        return self.ranker, self.explainer


def get_service(request: Request) -> ServiceState:
    """Return the process-wide service state."""
    state: ServiceState = request.app.state.service
    return state


def get_ready_service(service: ServiceState = Depends(get_service)) -> ServiceState:
    """Return the service state, rejecting the request if it is not ready.

    Returns 503 rather than 500: the caller did nothing wrong and the condition
    is expected to be transient, so a retryable status is the honest answer.
    """
    if not service.ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=service.detail or "model is not loaded",
        )
    return service
