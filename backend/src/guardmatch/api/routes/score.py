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
from typing import Literal

import numpy as np
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from guardmatch.api.dependencies import ServiceState, get_ready_service
from guardmatch.core.config import get_settings
from guardmatch.core.exceptions import ParsingError
from guardmatch.core.logging import get_logger, get_request_id
from guardmatch.core.metrics import rank_batch_size
from guardmatch.data.candidates import generate_candidates
from guardmatch.explain.reasons import build_reasons
from guardmatch.explain.shap_explainer import Explainer, ShapExplanation
from guardmatch.features.builder import build_features
from guardmatch.features.registry import to_vector
from guardmatch.parsing.documents import MAX_UPLOAD_BYTES, extension_of, extract_text
from guardmatch.parsing.extractor import parse_cv
from guardmatch.ranking.predict import RankedCandidate
from guardmatch.schemas.candidate import Candidate, ParsedProfile
from guardmatch.schemas.enums import CertificationCode, ShiftType, SiteType
from guardmatch.schemas.job import Job
from guardmatch.schemas.scoring import (
    Explanation,
    ExtractResponse,
    FeatureContribution,
    FeatureImportance,
    FeatureImportanceResponse,
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


#: Enough for a stable mean without making the first request slow. Parsing is the
#: cost here, not SHAP.
IMPORTANCE_SAMPLE = 200

#: A middle-of-the-road posting. Importance is measured against *a* job because
#: every feature in this model is pairwise — there is no candidate-only view — so
#: the reference posting is part of the measurement and is stated, not hidden.
_REFERENCE_JOB = Job(
    job_id="reference",
    required_certifications=frozenset(
        {CertificationCode.SECURITY_LICENCE, CertificationCode.FIRST_AID}
    ),
    min_years_experience=3.0,
    shift_pattern=ShiftType.NIGHT,
    site_type=SiteType.RETAIL,
    driving_required=True,
)


@router.get(
    "/feature-importance",
    response_model=FeatureImportanceResponse,
    summary="Global SHAP feature importance",
)
def feature_importance(
    service: ServiceState = Depends(get_ready_service),
) -> FeatureImportanceResponse:
    """Return each feature's share of the model's total effect.

    Global importance is the view a single explanation cannot give. One candidate's
    contributions say why that candidate placed where they did; this says what the
    model leans on in general — which is how `shift_match` was found to dominate,
    and `shift_match` is the feature carrying the largest fairness exposure.

    Measured against a fixed reference posting, because every feature here is
    pairwise: there is no candidate-only feature vector to average over. The
    posting used is part of the answer, so it is stated in the docstring rather
    than buried.

    Cached after the first call. Building the sample means parsing CVs, which costs
    around a second — acceptable once, not per request.
    """
    _, explainer = service.require_scoring()

    if service.importance is None:
        rows = [
            to_vector(build_features(parse_cv(candidate), _REFERENCE_JOB))
            for candidate in generate_candidates(IMPORTANCE_SAMPLE, seed=get_settings().random_seed)
        ]
        service.importance = explainer.global_importance(np.asarray(rows, dtype=float))
        logger.info("feature_importance_computed", sample=IMPORTANCE_SAMPLE)

    total = sum(service.importance.values()) or 1.0
    ranked = sorted(service.importance.items(), key=lambda item: -item[1])

    return FeatureImportanceResponse(
        model_version=service.model_version,
        sample_size=IMPORTANCE_SAMPLE,
        features=tuple(
            FeatureImportance(feature=name, mean_absolute_contribution=value, share=value / total)
            for name, value in ranked
        ),
    )


@router.post("/extract", response_model=ExtractResponse, summary="Extract CV text from a file")
async def extract(file: UploadFile = File(...)) -> ExtractResponse:
    """Pull CV text out of one uploaded document.

    One file per request, deliberately. A reviewer dropping twenty files needs to
    know **which** ones failed while they are still holding them, and a batch
    endpoint either fails wholesale or returns a mixed result the client has to
    unpick anyway. Per-file requests make each outcome its own answer.

    Refuses rather than guesses. A scanned PDF has no text layer, so `pypdf`
    returns an empty string with no error — passing that on would produce an empty
    CV, which ranks last. See `parsing/documents.py` for the full argument and for
    why OCR was rejected.

    No model needed: this reads a file. It stays available while the model is
    still verifying, so a reviewer can prepare a batch before it can be scored.

    Raises:
        ParsingError: Handled by the application's exception handler as a 422 with
            a string `detail` naming the file's problem and, where there is one,
            the way out.
    """
    filename = file.filename or "upload"
    payload = await file.read()

    # Size is checked inside `extract_text` too, but reading the whole body first
    # is unavoidable with UploadFile — this is the belt, not the braces.
    if len(payload) > MAX_UPLOAD_BYTES:
        msg = (
            f"{len(payload) / (1024 * 1024):.1f} MB is too large for a CV — the limit is "
            f"{MAX_UPLOAD_BYTES // (1024 * 1024)} MB."
        )
        raise ParsingError(msg)

    text = extract_text(filename, payload)
    extension = extension_of(filename)
    source: Literal["text", "pdf", "docx"] = (
        "pdf" if extension == ".pdf" else "docx" if extension == ".docx" else "text"
    )

    logger.info(
        "document_extracted", source=source, characters=len(text), filename_length=len(filename)
    )

    return ExtractResponse(filename=filename, cv_text=text, characters=len(text), source=source)


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
