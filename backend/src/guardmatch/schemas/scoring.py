"""Scoring and ranking API contracts.

One naming decision here carries real weight. The score field is called
``relative_ranking_score`` and every response repeats ``score_type``, because a
LambdaRank output is **not a probability**. It is only meaningful as an ordering
within a single job posting, and it is not comparable across postings.

Reading a ranking score as "87% likely to be hired" is the most plausible way
this system gets misused, so the contract is written to make that reading
awkward rather than relying on the documentation being read.

Explanations are returned in two layers: ``contributions`` is the exact numeric
record for auditing, and ``reasons`` is the plain-language rendering a reviewer
actually acts on. Both ship on every ranked candidate.
"""

from __future__ import annotations

from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from guardmatch.core.config import get_settings
from guardmatch.schemas.candidate import Candidate, ParsedProfile
from guardmatch.schemas.job import Job

# Final rather than a bare assignment so the inferred type is the literal itself,
# which lets it serve as the default for the Literal-typed score_type fields
# below instead of widening them to str.
SCORE_TYPE: Final = "relative_ranking_score"


class FeatureContribution(BaseModel):
    """One feature's SHAP contribution to a candidate's raw score."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    feature: str
    value: float | None = Field(description="The feature value. None when it was missing.")
    contribution: float = Field(
        description="Signed contribution to the raw ranking score. Additive on that score, "
        "not on a probability."
    )


class Explanation(BaseModel):
    """Why a candidate scored what they did."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    base_value: float = Field(description="The model's expected output before any feature.")
    contributions: tuple[FeatureContribution, ...] = Field(
        description="Exact per-feature contributions, ordered by absolute magnitude."
    )
    reasons: tuple[str, ...] = Field(
        description="Plain-language rendering of the leading contributions. Contains no "
        "percentage or probability claims."
    )


class ScoredCandidate(BaseModel):
    """A candidate's position and score for one job."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: str
    rank: int = Field(ge=1, description="1 is the strongest fit for this posting.")
    relative_ranking_score: float = Field(
        description="Uncalibrated. Meaningful only as an ordering within this posting."
    )
    score_type: Literal["relative_ranking_score"] = SCORE_TYPE
    explanation: Explanation
    parse_warnings: tuple[str, ...] = Field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


class ParseRequest(BaseModel):
    """Parse CV text without scoring it. Useful for debugging extraction."""

    model_config = ConfigDict(extra="forbid")

    candidate: Candidate


class ParseResponse(BaseModel):
    """The structured profile extracted from a CV."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    profile: ParsedProfile
    model_version: str


class ScoreRequest(BaseModel):
    """Score a single candidate against a single job."""

    model_config = ConfigDict(extra="forbid")

    job: Job
    candidate: Candidate


class ScoreResponse(BaseModel):
    """A single candidate's score with its explanation.

    Carries no rank: a rank of 1 out of 1 would imply a comparison that was never
    made. Ordering only exists within a set, which is what ``/rank`` returns.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    job_id: str
    candidate_id: str
    relative_ranking_score: float
    score_type: Literal["relative_ranking_score"] = SCORE_TYPE
    explanation: Explanation
    parse_warnings: tuple[str, ...] = Field(default_factory=tuple)
    model_version: str
    request_id: str | None = None


class RankRequest(BaseModel):
    """Rank many candidates against one job. The primary endpoint."""

    model_config = ConfigDict(extra="forbid")

    job: Job
    candidates: list[Candidate] = Field(min_length=1)

    @model_validator(mode="after")
    def _enforce_batch_limit(self) -> RankRequest:
        # Checked against configuration rather than a literal so the limit can be
        # tuned per deployment. Unbounded batches are an availability risk: one
        # request with fifty thousand candidates would monopolise the worker.
        limit = get_settings().max_rank_batch
        if len(self.candidates) > limit:
            msg = f"candidates exceeds MAX_RANK_BATCH ({len(self.candidates)} > {limit})"
            raise ValueError(msg)

        seen = {candidate.candidate_id for candidate in self.candidates}
        if len(seen) != len(self.candidates):
            msg = "candidate_id values must be unique within a request"
            raise ValueError(msg)

        return self


class RankResponse(BaseModel):
    """Candidates ordered by fit, each with an explanation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    job_id: str
    candidates: tuple[ScoredCandidate, ...] = Field(description="Ordered best fit first.")
    score_type: Literal["relative_ranking_score"] = SCORE_TYPE
    model_version: str
    request_id: str | None = None

    disclaimer: str = Field(
        default=(
            "Scores are relative to this job posting only and are not probabilities. "
            "This ranking is a shortlisting aid and is not a hiring decision; a human "
            "reviewer remains responsible for the outcome."
        ),
        description="Returned on every response so the constraint travels with the data "
        "rather than living only in documentation.",
    )


# ---------------------------------------------------------------------------
# Operational
# ---------------------------------------------------------------------------


class SampleCandidatesResponse(BaseModel):
    """Synthetic candidates, for trying the service at volume.

    The brief opens with SAJCO's hiring volume, and pasting three hundred CVs by
    hand is not a way to see that. This returns generated applications instead.

    **Ground truth is deliberately absent.** The generator produces
    ``GeneratedCandidate``, which carries the ``true_*`` fields the CV text was
    written from — years, certifications, availability. Returning those would hand
    a caller the answers the model is supposed to infer from the text, so only the
    plain ``Candidate`` shape crosses the boundary.

    ``source`` exists so a caller cannot mistake this for real applicants. It is
    stated in the payload rather than only in documentation, for the same reason
    ``RankResponse`` carries its disclaimer: a constraint that travels with the
    data cannot be left behind.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidates: tuple[Candidate, ...]
    count: int
    seed: int
    source: Literal["synthetic"] = "synthetic"


class GroupOutcome(BaseModel):
    """How one demographic group fared in the shortlists.

    Every figure is an aggregate over held-out rankings. The smallest group in the
    released audit has 319 appearances, and groups below `MIN_GROUP_SIZE` are
    suppressed rather than reported, because a ratio of two proportions is
    unstable on small numbers — a lesson this project learned the hard way when a
    319-member group produced a false adverse-impact alarm.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    group: str
    n_appearances: int
    n_in_top_k: int
    n_qualified: int
    n_qualified_in_top_k: int
    selection_rate: float
    qualified_selection_rate: float
    mean_exposure: float


class AttributeAudit(BaseModel):
    """The audit for one protected attribute.

    `passes` is not simply `adverse_impact_ratio >= threshold`. A ratio below the
    four-fifths line that is **not distinguishable from noise** after correcting
    for the number of possible group comparisons is reported as *inconclusive*
    rather than as a failure — and the released `age_band` audit is exactly that
    case, at 0.627. Any consumer that renders `passes` as a green tick and ignores
    `inconclusive` will state something this audit does not.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    attribute: str
    top_k: int
    groups: tuple[GroupOutcome, ...]
    suppressed_groups: tuple[str, ...]
    adverse_impact_ratio: float
    demographic_parity_gap: float
    equal_opportunity_gap: float
    exposure_ratio: float
    selection_p_value: float
    qualified_p_value: float
    significance_threshold: float
    n_comparisons: int
    passes: bool
    failures: tuple[str, ...]
    inconclusive: tuple[str, ...]


class FairnessResponse(BaseModel):
    """The fairness audit for the model currently being served.

    Exposed because the audit is enforced in CI and then read by nobody: it lived
    in a JSON file beside the artifact and in a report. Aggregate throughout — no
    field here describes an individual — which is what makes it publishable at all.

    `exposure_ratio` is the metric worth knowing about: it catches a group being
    admitted to the shortlist at an equal rate but placed consistently lower
    within it, which every selection-rate metric reads as perfectly fair.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", protected_namespaces=())

    model_version: str
    top_k: int
    adverse_impact_threshold: float
    max_gap: float
    min_group_size: int
    n_postings: int
    n_rows: int
    passes: bool
    failures: tuple[str, ...]
    inconclusive: tuple[str, ...]
    attributes: tuple[AttributeAudit, ...]


class HealthResponse(BaseModel):
    """Liveness. Deliberately does not touch the model."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["ok"] = "ok"


class ReadyResponse(BaseModel):
    """Readiness. Reports whether the model is loaded and checksum-verified."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ready: bool
    model_version: str
    detail: str | None = None


class ExtractResponse(BaseModel):
    """Text pulled out of one uploaded document.

    `cv_text` is guaranteed non-empty. A document that yields nothing is refused
    rather than returned blank, because a blank CV ranks last — the service would
    place a candidate at the bottom of a shortlist because their file could not be
    read, and a reviewer would see a weak candidate rather than an unreadable file.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    filename: str
    cv_text: str
    characters: int
    #: How the text was obtained, so a reviewer knows whether to expect layout
    #: damage. A PDF's reading order is a reconstruction; a .txt is exactly itself.
    source: Literal["text", "pdf", "docx"]


class FeatureImportance(BaseModel):
    """One feature's share of the model's total effect."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    feature: str
    mean_absolute_contribution: float
    #: Share of the total, so the twelve sum to 1.0. The model card quotes these
    #: as percentages, and a share is what makes "26.8% of the model's effect"
    #: a statement rather than a raw magnitude nobody can scale.
    share: float


class FeatureImportanceResponse(BaseModel):
    """Global SHAP importance for the active model.

    Mean absolute SHAP contribution per feature over a sample, which is what
    catches a feature being far more influential than anyone intended. It is how
    `shift_match` was found to carry roughly a quarter of this model's effect —
    and `shift_match` is also the feature the fairness work watches most closely.

    Computed from generated candidates rather than from live traffic, so the answer
    does not depend on who happened to be scored today.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", protected_namespaces=())

    model_version: str
    sample_size: int
    features: tuple[FeatureImportance, ...]


class ModelInfoResponse(BaseModel):
    """Metadata for the active model."""

    model_config = ConfigDict(frozen=True, extra="forbid", protected_namespaces=())

    model_version: str
    trained_at: str | None = None
    data_version: str | None = None
    git_sha: str | None = None
    feature_names: tuple[str, ...] = Field(default_factory=tuple)
    metrics: dict[str, float] = Field(default_factory=dict)
