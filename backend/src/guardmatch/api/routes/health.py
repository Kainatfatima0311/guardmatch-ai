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

from fastapi import APIRouter, Depends, HTTPException, Response, status

from guardmatch.api.dependencies import ServiceState, get_service
from guardmatch.core.metrics import render_metrics
from guardmatch.schemas.scoring import (
    FairnessResponse,
    HealthResponse,
    ModelInfoResponse,
    ReadyResponse,
)

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


@router.get("/fairness", response_model=FairnessResponse, summary="Fairness audit")
def fairness(service: ServiceState = Depends(get_service)) -> FairnessResponse:
    """Return the fairness audit for the model currently being served.

    The audit is computed offline by `guardmatch audit`, written into the artifact
    directory, and enforced as a CI gate. Until now it was readable only by opening
    a JSON file or the report — which means the project's most consequential claim
    was the one least likely to be looked at.

    Aggregate throughout. The smallest group in the released audit has 319
    appearances and groups below `MIN_GROUP_SIZE` are suppressed rather than
    reported, so nothing here describes an individual.

    Returns 503 rather than 404 when the artifact has not loaded: the audit is part
    of the artifact bundle, so its absence means the service is not ready rather
    than that fairness data does not exist.

    Raises:
        HTTPException: The artifact loaded but carries no audit, which happens
            only for a model trained before `guardmatch audit` was run against it.
    """
    if service.loaded is None:
        # Raised rather than returned with a partial body. `/ready` and
        # `/model-info` answer with a shape on 503 because a caller polling them
        # wants the model version either way; there is no useful partial audit.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="the model has not finished loading, so its audit is not available",
        )

    audit = service.loaded.fairness
    if not audit:
        # An artifact can legitimately exist without an audit — `train` writes the
        # model, `audit` fills this in afterwards. Saying so plainly beats
        # returning an empty shape that reads like a clean bill of health.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"model {service.loaded.version} carries no fairness audit. "
                f"Run `guardmatch audit --version {service.loaded.version}`."
            ),
        )

    return FairnessResponse.model_validate(audit)


@router.get("/metrics", summary="Prometheus metrics", include_in_schema=False)
def metrics() -> Response:
    """Prometheus exposition."""
    return Response(content=render_metrics(), media_type="text/plain; version=0.0.4")
