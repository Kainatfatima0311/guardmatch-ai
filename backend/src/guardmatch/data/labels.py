"""Graded relevance labels, designed so the model cannot simply relearn them.

This is the module the honesty of the whole project rests on.

The naive way to label synthetic data is to score each pair with a formula built
from the same variables the model will later receive as features. Do that and
the ranker does not learn anything about hiring — it reverse-engineers our own
arithmetic. NDCG lands near 0.99, the evaluation measures the generator rather
than the learner, and every downstream number is meaningless.

Four mitigations are built in.

**Hidden factors.** ``interview_score`` and ``reference_check`` contribute a
fifth of the label and are never exposed as features. In real hiring these
matter and are invisible at CV-screening time, so their absence is realistic
rather than a contrivance. They impose a hard ceiling on achievable NDCG, which
is precisely the point.

**Label noise.** Roughly one label in eight is shifted by a grade. Real
reviewers disagree with each other and with themselves; a noiseless dataset is
not a model of hiring.

**Non-linear interactions.** A licence gates eligibility multiplicatively, the
licence-plus-experience combination pays a bonus neither pays alone, and shift
mismatch is penalised harder on sites where cover cannot lapse. A purely
additive rule would be recoverable by linear regression, which would make the
choice of a gradient-boosted ranker meaningless.

**A sanity band on the result.** NDCG@10 above 0.95 is treated as a defect, not
a success. See ``ranking.evaluate``.

Note that labels here are *not* biased. The deliberate bias lives in
``data.protected``, where a protected attribute is correlated with night
availability — so unfairness arrives the way it does in reality, through an
apparently neutral feature, rather than by being written into the target.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from guardmatch.schemas.candidate import GeneratedCandidate
from guardmatch.schemas.enums import CertificationCode, SiteType
from guardmatch.schemas.job import Job

# Share of the label explained by factors the model can never see. High enough
# to impose a real ceiling, low enough that the visible features still carry
# most of the signal.
HIDDEN_FACTOR_WEIGHT = 0.20

# Probability that a label is shifted by one grade.
LABEL_NOISE_RATE = 0.12

# Sites where a shift gap cannot be tolerated, so mismatch is penalised harder.
_CRITICAL_COVER_SITES: frozenset[SiteType] = frozenset({SiteType.INDUSTRIAL, SiteType.CONSTRUCTION})

# Multiplier applied when a required gating certification is absent. Not zero —
# an unlicensed candidate with a decade of experience is still a better prospect
# than an unlicensed novice, and collapsing both to zero would throw away signal
# the ranker can legitimately use.
_MISSING_GATE_MULTIPLIER = 0.25

# Grade thresholds on the continuous fit score.
#
# Tuned so that grade 3 stays scarce — around one candidate in ten. An earlier,
# looser set produced 31% top-grade labels, which meant roughly eighteen
# "strong fit" candidates in a sixty-candidate group. Filling a top-10 shortlist
# from eighteen equally-ideal candidates is nearly impossible to get wrong, so
# NDCG@10 would have been high for reasons having nothing to do with the model.
# Scarcity at the top is what makes the metric discriminative.
_GRADE_THRESHOLDS: tuple[tuple[float, int], ...] = (
    (0.82, 3),
    (0.68, 2),
    (0.50, 1),
)


@dataclass(frozen=True)
class HiddenFactors:
    """Per-candidate traits that influence hiring but never become features.

    Held per candidate rather than per pair because they model stable traits —
    someone who interviews well interviews well everywhere. Drawing them per
    pair would make them pure noise; drawing them per candidate makes them a
    latent variable the model genuinely cannot observe.
    """

    interview_score: float
    reference_check: float


@dataclass(frozen=True)
class LabelledPair:
    """One (job, candidate) pair with its graded relevance."""

    job_id: str
    candidate_id: str
    grade: int


def generate_hidden_factors(candidate_ids: list[str], seed: int) -> dict[str, HiddenFactors]:
    """Draw the unobservable traits for each candidate."""
    rng = random.Random(seed + 20_000)
    return {
        candidate_id: HiddenFactors(
            interview_score=rng.betavariate(5, 3),
            reference_check=rng.betavariate(6, 2),
        )
        for candidate_id in candidate_ids
    }


def _fit_score(candidate: GeneratedCandidate, job: Job, hidden: HiddenFactors) -> float:
    """Continuous fit score in roughly [0, 1] for one pair."""
    required = job.required_certifications
    held = candidate.true_certifications

    cert_overlap = len(required & held) / len(required) if required else 1.0

    min_years = max(job.min_years_experience, 1.0)
    exp_ratio = min(candidate.true_years_experience / min_years, 1.5) / 1.5

    shift_ok = job.shift_pattern in candidate.true_shift_availability
    site_ok = job.site_type in candidate.true_site_experience
    driving_ok = (not job.driving_required) or candidate.true_driving_licence

    # Additive component. Weights sum to 1.0, with the hidden factors taking
    # HIDDEN_FACTOR_WEIGHT of that total.
    score = (
        0.30 * cert_overlap
        + 0.20 * exp_ratio
        + 0.15 * float(shift_ok)
        + 0.08 * float(site_ok)
        + 0.07 * float(driving_ok)
        + 0.12 * hidden.interview_score
        + 0.08 * hidden.reference_check
    )

    # -- Interaction 1: the licence gates eligibility, multiplicatively -----
    needs_licence = CertificationCode.SECURITY_LICENCE in required
    has_licence = CertificationCode.SECURITY_LICENCE in held
    if needs_licence and not has_licence:
        score *= _MISSING_GATE_MULTIPLIER

    # -- Interaction 2: licence and experience together pay a bonus ---------
    # Neither alone earns this. A licensed novice and an experienced unlicensed
    # applicant are both weaker than someone holding both, by more than the sum
    # of their individual contributions.
    if has_licence and candidate.true_years_experience >= job.min_years_experience:
        score += 0.10

    # -- Interaction 3: shift mismatch scales with how critical cover is ----
    if not shift_ok:
        score -= 0.12 if job.site_type in _CRITICAL_COVER_SITES else 0.04

    return max(0.0, min(1.0, score))


def _to_grade(score: float) -> int:
    """Bucket a continuous fit score into a 0-3 relevance grade."""
    for threshold, grade in _GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return 0


def _apply_noise(grade: int, rng: random.Random) -> int:
    """Shift a grade by one, occasionally, to model reviewer inconsistency."""
    if rng.random() >= LABEL_NOISE_RATE:
        return grade
    return max(0, min(3, grade + rng.choice((-1, 1))))


def relevance_grade(
    candidate: GeneratedCandidate,
    job: Job,
    hidden: HiddenFactors,
    rng: random.Random,
) -> int:
    """Return the graded relevance of ``candidate`` for ``job``."""
    return _apply_noise(_to_grade(_fit_score(candidate, job, hidden)), rng)


def generate_labels(
    candidates: list[GeneratedCandidate],
    jobs: list[Job],
    hidden_factors: dict[str, HiddenFactors],
    seed: int,
    *,
    min_per_job: int = 40,
    max_per_job: int = 80,
) -> list[LabelledPair]:
    """Build labelled query groups, one group per job posting.

    Each posting is scored against a sampled subset of candidates rather than
    all of them. Scoring every candidate against every posting would produce a
    million pairs dominated by obvious non-matches, which teaches the ranker
    almost nothing while making training slow.

    Args:
        candidates: The candidate pool.
        jobs: The postings, each becoming one query group.
        hidden_factors: Per-candidate unobservable traits.
        seed: Seed for sampling and noise.
        min_per_job: Smallest candidate pool per posting.
        max_per_job: Largest candidate pool per posting.

    Returns:
        Labelled pairs, grouped contiguously by ``job_id``.
    """
    rng = random.Random(seed + 30_000)
    pairs: list[LabelledPair] = []

    for job in jobs:
        pool_size = min(len(candidates), rng.randint(min_per_job, max_per_job))
        pool = rng.sample(candidates, k=pool_size)

        for candidate in pool:
            hidden = hidden_factors[candidate.candidate_id]
            pairs.append(
                LabelledPair(
                    job_id=job.job_id,
                    candidate_id=candidate.candidate_id,
                    grade=relevance_grade(candidate, job, hidden, rng),
                )
            )

    return pairs


def grade_distribution(pairs: list[LabelledPair]) -> dict[int, int]:
    """Count labels by grade. Recorded in the data card."""
    counts = dict.fromkeys(range(4), 0)
    for pair in pairs:
        counts[pair.grade] += 1
    return counts
