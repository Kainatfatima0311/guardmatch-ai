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
from fastapi import APIRouter, Depends, HTTPException, Query

from guardmatch.api.dependencies import ServiceState, get_ready_service
from guardmatch.core.config import get_settings
from guardmatch.core.logging import get_logger, get_request_id
from guardmatch.core.metrics import rank_batch_size
from guardmatch.data.candidates import generate_candidates
from guardmatch.explain.reasons import build_reasons
from guardmatch.explain.shap_explainer import Explainer, ShapExplanation
from guardmatch.features.registry import to_vector
from guardmatch.parsing.extractor import parse_cv
from guardmatch.ranking.predict import RankedCandidate
from guardmatch.schemas.candidate import Candidate, ParsedProfile
from guardmatch.schemas.scoring import (
    Explanation,
    FeatureContribution,
    ParseRequest,
    ParseResponse,
    RankRequest,
    RankResponse,
    SampleCandidatesResponse,
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


@router.get(
    "/sample-candidates",
    response_model=SampleCandidatesResponse,
    summary="Generate synthetic candidates for trying the service at volume",
)
def sample_candidates(
    count: int = Query(10, ge=1, description="How many candidates to generate."),
    seed: int | None = Query(
        None, description="Defaults to the configured RANDOM_SEED, so results repeat."
    ),
) -> SampleCandidatesResponse:
    """Synthetic applications, generated on demand.

    The brief opens with SAJCO's hiring volume, and there is no way to see that in
    an interface where every CV has to be pasted by hand. This produces as many
    applications as asked for, so the ranking path can be exercised at a realistic
    size.

    **Generated rather than read from disk.** The obvious implementation reads
    ``data/candidates.json``, and it would fail in the container: `data/` is
    excluded from the image by `.dockerignore`, deliberately, because a service
    that scores what it is sent has no use for the training set. The generator
    itself ships inside the package, so generating costs nothing at build time and
    works identically locally, in the container and in CI. Measured at roughly
    80 ms for 250 candidates.

    **No model needed.** This deliberately does not depend on
    ``get_ready_service``: it produces text and touches nothing the model owns, so
    it stays available while the model is still loading or has failed
    verification. A caller can prepare a batch before the service can score it.

    **Ground truth is stripped.** The generator returns ``GeneratedCandidate``,
    which carries the ``true_*`` values the CV text was written from. Only the
    plain ``Candidate`` fields are returned, because handing a caller the answers
    the model is meant to infer from the text would make any demo meaningless.

    Raises:
        HTTPException: ``count`` exceeds the batch limit the ranking endpoint
            enforces, so a caller cannot be handed more candidates than it is
            allowed to submit.
    """
    settings = get_settings()

    if count > settings.max_rank_batch:
        msg = (
            f"count exceeds MAX_RANK_BATCH ({count} > {settings.max_rank_batch}). "
            f"Requesting more candidates than /rank accepts would only fail later."
        )
        raise HTTPException(status_code=422, detail=msg)

    resolved_seed = settings.random_seed if seed is None else seed
    generated = generate_candidates(count, seed=resolved_seed)

    logger.info("sample_candidates_generated", count=count, seed=resolved_seed)

    return SampleCandidatesResponse(
        candidates=tuple(
            Candidate(candidate_id=candidate.candidate_id, cv_text=candidate.cv_text)
            for candidate in generated
        ),
        count=len(generated),
        seed=resolved_seed,
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
def rank(payload: RankRequest, service: ServiceState = Depends(get_ready_service)) -> RankResponse:
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


def _explain_ranked(explainer: Explainer, ranked: Sequence[RankedCandidate]) -> list[Explanation]:
    """Explain a ranked batch in one SHAP call.

    Batched rather than looped: TreeSHAP is vectorised, and a per-candidate call
    would dominate the latency budget on a large shortlist.

    The features come from the ranker rather than being recomputed here, so the
    explanation describes exactly the values the model scored.
    """
    matrix = np.array([to_vector(entry.features) for entry in ranked], dtype=np.float64)
    return [_to_explanation(shap) for shap in explainer.explain_matrix(matrix)]
