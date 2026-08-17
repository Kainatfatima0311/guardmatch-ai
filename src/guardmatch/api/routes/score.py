"""Scoring endpoints — the project's primary deliverable.

Three endpoints, and the split is deliberate.

``/rank`` is the real one. Ranking is a set operation: the answer for one
candidate depends on who else applied, so a service that could only score
individually would be answering a different question.

``/score`` handles a single candidate and returns **no rank**. A rank of 1 out of
1 would imply a comparison that never happened.

``/parse`` exposes extraction alone. When a ranking looks wrong, the first
question is almost always whether the CV was read correctly, and without this
endpoint that question requires a debugger.

Every response carries the model version, the score type, and any parse
warnings, so a result can be interpreted and traced without reference to
anything else.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from fastapi import APIRouter, Depends

from guardmatch.api.dependencies import ServiceState, get_ready_service
from guardmatch.core.logging import get_logger, get_request_id
from guardmatch.core.metrics import rank_batch_size
from guardmatch.explain.reasons import build_reasons
from guardmatch.explain.shap_explainer import Explainer, ShapExplanation
from guardmatch.features.registry import to_vector
from guardmatch.parsing.extractor import parse_cv
from guardmatch.ranking.predict import RankedCandidate
from guardmatch.schemas.candidate import ParsedProfile
from guardmatch.schemas.scoring import (
    Explanation,
    FeatureContribution,
    ParseRequest,
    ParseResponse,
    RankRequest,
    RankResponse,
    ScoredCandidate,
    ScoreRequest,
    ScoreResponse,
)

logger = get_logger(__name__)

router = APIRouter()


def _to_explanation(shap: ShapExplanation) -> Explanation:
    """Convert SHAP output into the response contract.

    Contributions are ordered by absolute effect so the leading factors appear
    first, matching the order of the reasons alongside them.
    """
    ranked = shap.ranked()
    return Explanation(
        base_value=shap.base_value,
        contributions=tuple(
            FeatureContribution(
                feature=item.feature, value=item.value, contribution=item.contribution
            )
            for item in ranked
        ),
        reasons=build_reasons(shap),
    )


@router.post("/parse", response_model=ParseResponse, summary="Extract structured facts")
def parse(
    payload: ParseRequest, service: ServiceState = Depends(get_ready_service)
) -> ParseResponse:
    """Parse CV text into a structured profile without scoring it.

    Unextractable fields come back as ``null`` rather than as a default, and
    anything ambiguous appears in ``parse_warnings``.
    """
    profile = parse_cv(payload.candidate)
    return ParseResponse(profile=profile, model_version=service.model_version)


@router.post("/score", response_model=ScoreResponse, summary="Score one candidate")
def score(
    payload: ScoreRequest, service: ServiceState = Depends(get_ready_service)
) -> ScoreResponse:
    """Score a single candidate against a single job.

    Returns no rank. A rank requires a set to rank within, which is what
    ``/rank`` provides.
    """
    ranker, explainer = service.require_scoring()

    profile = parse_cv(payload.candidate)
    raw_score, features = ranker.score(profile, payload.job)
    explanation = _to_explanation(explainer.explain(features))

    logger.info(
        "candidate_scored",
        candidate_id=profile.candidate_id,
        job_id=payload.job.job_id,
        score=round(raw_score, 4),
        warnings=len(profile.parse_warnings),
    )

    return ScoreResponse(
        job_id=payload.job.job_id,
        candidate_id=profile.candidate_id,
        relative_ranking_score=raw_score,
        explanation=explanation,
        parse_warnings=profile.parse_warnings,
        model_version=service.model_version,
        request_id=get_request_id(),
    )


@router.post("/rank", response_model=RankResponse, summary="Rank candidates for one job")
def rank(
    payload: RankRequest, service: ServiceState = Depends(get_ready_service)
) -> RankResponse:
    """Rank candidates against one job posting, best fit first.

    The batch size is capped by configuration and enforced by the request schema,
    so an oversized request is rejected at the boundary rather than after the
    work has begun.
    """
    ranker, explainer = service.require_scoring()

    rank_batch_size.observe(len(payload.candidates))

    profiles: list[ParsedProfile] = [parse_cv(candidate) for candidate in payload.candidates]
    warnings_by_id = {profile.candidate_id: profile.parse_warnings for profile in profiles}

    ranked = ranker.rank(profiles, payload.job)
    explanations = _explain_ranked(explainer, ranked)

    scored = tuple(
        ScoredCandidate(
            candidate_id=entry.candidate_id,
            rank=entry.rank,
            relative_ranking_score=entry.relative_ranking_score,
            explanation=explanation,
            parse_warnings=warnings_by_id.get(entry.candidate_id, ()),
        )
        for entry, explanation in zip(ranked, explanations, strict=True)
    )

    logger.info(
        "candidates_ranked",
        job_id=payload.job.job_id,
        candidates=len(scored),
        top_score=round(scored[0].relative_ranking_score, 4) if scored else None,
        warnings=sum(len(w) for w in warnings_by_id.values()),
    )

    return RankResponse(
        job_id=payload.job.job_id,
        candidates=scored,
        model_version=service.model_version,
        request_id=get_request_id(),
    )


def _explain_ranked(
    explainer: Explainer, ranked: Sequence[RankedCandidate]
) -> list[Explanation]:
    """Explain a ranked batch in one SHAP call.

    Batched rather than looped: TreeSHAP is vectorised, and a per-candidate call
    would dominate the latency budget on a large shortlist.

    The features come from the ranker rather than being recomputed here, so the
    explanation describes exactly the values the model scored.
    """
    matrix = np.array([to_vector(entry.features) for entry in ranked], dtype=np.float64)
    return [_to_explanation(shap) for shap in explainer.explain_matrix(matrix)]
