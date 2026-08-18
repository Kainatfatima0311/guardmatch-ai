"""Operational endpoints.

``/health`` and ``/ready`` answer different questions, and conflating them
breaks deployments. Liveness asks "is this process alive" — if it fails, restart
the container. Readiness asks "should this instance receive traffic" — if it
fails, route around it and wait. An instance whose model failed verification is
alive but must not be sent requests.

So ``/health`` deliberately does not touch the model. If it did, a model problem
would trigger a restart loop instead of simply removing the instance from the
pool.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from guardmatch.api.dependencies import ServiceState, get_service
from guardmatch.core.metrics import render_metrics
from guardmatch.schemas.scoring import HealthResponse, ModelInfoResponse, ReadyResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse, summary="Liveness")
def health() -> HealthResponse:
    """Report that the process is running.

    Does not consult the model. A failing model should remove this instance from
    the load balancer, not restart it in a loop.
    """
    return HealthResponse()


@router.get("/ready", response_model=ReadyResponse, summary="Readiness")
def ready(response: Response, service: ServiceState = Depends(get_service)) -> ReadyResponse:
    """Report whether the model is loaded and checksum-verified.

    Returns 503 until it is, so an orchestrator does not route traffic to an
    instance that would answer from an unverified model.
    """
    if not service.ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadyResponse(
        ready=service.ready,
        model_version=service.model_version,
        detail=service.detail,
    )


@router.get("/model-info", response_model=ModelInfoResponse, summary="Active model metadata")
def model_info(
    response: Response, service: ServiceState = Depends(get_service)
) -> ModelInfoResponse:
    """Return provenance for the model currently being served.

    The answer to "which model produced this score" has to be available from the
    running service, not only from the repository.
    """
    if service.loaded is None:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ModelInfoResponse(model_version=service.model_version)

    metadata = service.loaded.metadata
    metrics = {
        key: float(value)
        for key, value in service.loaded.metrics.items()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    }

    return ModelInfoResponse(
        model_version=service.loaded.version,
        trained_at=metadata.trained_at,
        data_version=metadata.generator_version,
        git_sha=metadata.git_sha,
        feature_names=tuple(metadata.feature_names),
        metrics=metrics,
    )


@router.get("/metrics", summary="Prometheus metrics", include_in_schema=False)
def metrics() -> Response:
    """Prometheus exposition."""
    return Response(content=render_metrics(), media_type="text/plain; version=0.0.4")
