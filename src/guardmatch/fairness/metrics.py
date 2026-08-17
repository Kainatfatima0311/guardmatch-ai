"""Fairness metrics for a ranking system.

Standard classification fairness metrics do not fit here, and the reason
matters. They ask "was this person selected". A ranking asks something finer:
being placed eleventh instead of second is a real harm even though both
candidates are technically "in the list", because nobody reads to position
eleven. A system can admit every group to the shortlist at equal rates and still
systematically bury one of them inside it.

So four metrics are computed, and the last one is the ranking-specific one.

**Adverse impact ratio** — the four-fifths rule. The lowest group's top-k
selection rate divided by the highest. A long-standing benchmark in employment
discrimination assessment, and the one with legal precedent behind it.

**Demographic parity gap** — the raw spread in top-k selection rates.

**Equal opportunity gap** — the same spread, restricted to candidates who are
genuinely qualified. This separates "the model is unfair" from "the groups
differ in qualification", which are different problems with different remedies.

**Exposure ratio** — position-weighted, using the standard `1/log2(rank+1)`
discount. This is what catches a model that lets a group in and then places them
consistently lower.

Small groups are **suppressed rather than reported**. A selection rate computed
from eleven people is noise, and publishing it as a fairness finding invites
either false alarm or false comfort.

**Failures require statistical significance, corrected for multiple
comparisons.** This is not a refinement, it is load-bearing, and getting it right
took two attempts.

The first run of this audit against deliberately unbiased data reported an
adverse impact ratio of 0.627 on age — apparently a serious breach, in a dataset
where age is assigned at random and cannot influence anything. The cause was a
319-member group whose selection rate happened to land low. A ratio of two
proportions is an unstable statistic, and the four-fifths rule assumes sample
sizes that make it stable.

Adding a two-proportion z-test was not sufficient on its own: it returned
p = 0.0069, apparently significant. The remaining error was subtler. The ratio
compares the **lowest against the highest** of several groups, and those two are
selected precisely *because* they are extreme. Testing a post-hoc extreme pair as
though it had been chosen in advance inflates the false positive rate — with five
groups there are ten possible pairs, so the most extreme one clears p < 0.05
routinely on pure noise.

A Bonferroni correction over the number of implied pairwise comparisons fixes it.
With five groups the effective threshold becomes 0.005, and p = 0.0069 correctly
falls back to *inconclusive*. With two groups there is one comparison and nothing
changes.

Without this, the gate fails on noise more often than it fires on substance, and
a gate that cries wolf gets switched off — a slower route to the same
discrimination it was built to prevent.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

# A candidate counts as genuinely qualified at grade 2 or above — "would
# interview". Grade 1 means "only if the shortlist is thin", which is not a
# hiring signal and would inflate the qualified pool with marginal cases.
QUALIFIED_GRADE = 2

# Significance level for the two-proportion test, before correction. A breach
# with a p-value above the corrected threshold is reported as inconclusive rather
# than as a violation.
SIGNIFICANCE_LEVEL = 0.05


def bonferroni_threshold(n_groups: int, alpha: float = SIGNIFICANCE_LEVEL) -> float:
    """Significance threshold corrected for post-hoc extreme-pair selection.

    The adverse impact ratio compares the lowest group against the highest, and
    those two are chosen *because* they are extreme. Testing them as a
    pre-specified pair inflates the false positive rate in proportion to how many
    pairs could have been chosen — ``n_groups * (n_groups - 1) / 2`` of them.

    Bonferroni divides the level by that count. Conservative, but the cost of a
    missed finding here is a fairness regression reaching production, while the
    cost of a false alarm is a gate people stop trusting.
    """
    comparisons = max(1, n_groups * (n_groups - 1) // 2)
    return alpha / comparisons


def two_proportion_p_value(
    successes_a: int, total_a: int, successes_b: int, total_b: int
) -> float | None:
    """Two-sided p-value for the difference between two proportions.

    A pooled two-proportion z-test. Implemented with ``math.erf`` rather than
    pulled from scipy: it is six lines, and the dependency would be carried into
    the serving image for one function.

    Returns ``None`` when the test is undefined — an empty group, or two groups
    that are both entirely selected or entirely rejected, where there is no
    variance to test against.
    """
    if total_a <= 0 or total_b <= 0:
        return None

    rate_a = successes_a / total_a
    rate_b = successes_b / total_b

    pooled = (successes_a + successes_b) / (total_a + total_b)
    if pooled in (0.0, 1.0):
        return None

    standard_error = math.sqrt(pooled * (1.0 - pooled) * (1.0 / total_a + 1.0 / total_b))
    if standard_error == 0.0:  # pragma: no cover - guarded by the pooled check
        return None

    z = (rate_a - rate_b) / standard_error
    # Two-sided tail of the standard normal.
    return math.erfc(abs(z) / math.sqrt(2.0))


@dataclass(frozen=True)
class RankedGroup:
    """One posting's candidates in ranked order, with their true grades."""

    job_id: str
    candidate_ids: Sequence[str]
    grades: Sequence[int]

    def __post_init__(self) -> None:
        if len(self.candidate_ids) != len(self.grades):
            msg = "candidate_ids and grades must be the same length"
            raise ValueError(msg)


@dataclass(frozen=True)
class GroupOutcome:
    """How one demographic group fared across all postings."""

    group: str
    n_appearances: int
    n_in_top_k: int
    selection_rate: float
    n_qualified: int
    n_qualified_in_top_k: int
    qualified_selection_rate: float | None
    mean_exposure: float

    def to_dict(self) -> dict[str, float | int | str | None]:
        return {
            "group": self.group,
            "n_appearances": self.n_appearances,
            "n_in_top_k": self.n_in_top_k,
            "selection_rate": self.selection_rate,
            "n_qualified": self.n_qualified,
            "n_qualified_in_top_k": self.n_qualified_in_top_k,
            "qualified_selection_rate": self.qualified_selection_rate,
            "mean_exposure": self.mean_exposure,
        }


@dataclass(frozen=True)
class AttributeAudit:
    """Fairness results for one protected attribute."""

    attribute: str
    top_k: int
    groups: tuple[GroupOutcome, ...]
    suppressed_groups: tuple[str, ...]
    adverse_impact_ratio: float | None
    demographic_parity_gap: float | None
    equal_opportunity_gap: float | None
    exposure_ratio: float | None
    selection_p_value: float | None = None
    qualified_p_value: float | None = None
    significance_threshold: float = SIGNIFICANCE_LEVEL
    n_comparisons: int = 1
    failures: tuple[str, ...] = field(default_factory=tuple)
    inconclusive: tuple[str, ...] = field(default_factory=tuple)

    @property
    def passes(self) -> bool:
        """Whether no statistically significant breach was found.

        Inconclusive findings do not fail the build, but they are reported. A
        breach that cannot be distinguished from noise is a reason to gather more
        data, not a reason to block a release — and not a reason to stay silent
        either.
        """
        return not self.failures

    def to_dict(self) -> dict[str, object]:
        return {
            "attribute": self.attribute,
            "top_k": self.top_k,
            "groups": [group.to_dict() for group in self.groups],
            "suppressed_groups": list(self.suppressed_groups),
            "adverse_impact_ratio": self.adverse_impact_ratio,
            "demographic_parity_gap": self.demographic_parity_gap,
            "equal_opportunity_gap": self.equal_opportunity_gap,
            "exposure_ratio": self.exposure_ratio,
            "selection_p_value": self.selection_p_value,
            "qualified_p_value": self.qualified_p_value,
            "significance_threshold": self.significance_threshold,
            "n_comparisons": self.n_comparisons,
            "passes": self.passes,
            "failures": list(self.failures),
            "inconclusive": list(self.inconclusive),
        }


def position_exposure(rank: int) -> float:
    """Attention a candidate receives at a given 1-indexed rank.

    The standard logarithmic discount. Rank 1 is worth roughly 2.6 times rank
    10, which reflects how shortlists are actually read: the top entry gets
    considered, the tenth gets skimmed.
    """
    return 1.0 / math.log2(rank + 1)


def _accumulate(
    ranked_groups: Sequence[RankedGroup],
    group_of: Mapping[str, str],
    top_k: int,
) -> dict[str, dict[str, float]]:
    """Tally per-demographic-group counts across every posting."""
    totals: dict[str, dict[str, float]] = {}

    for posting in ranked_groups:
        for position, (candidate_id, grade) in enumerate(
            zip(posting.candidate_ids, posting.grades, strict=True), start=1
        ):
            group = group_of.get(candidate_id)
            if group is None:
                continue

            bucket = totals.setdefault(
                group,
                {
                    "appearances": 0.0,
                    "in_top_k": 0.0,
                    "qualified": 0.0,
                    "qualified_in_top_k": 0.0,
                    "exposure": 0.0,
                },
            )

            bucket["appearances"] += 1
            bucket["exposure"] += position_exposure(position)

            in_top_k = position <= top_k
            if in_top_k:
                bucket["in_top_k"] += 1

            if grade >= QUALIFIED_GRADE:
                bucket["qualified"] += 1
                if in_top_k:
                    bucket["qualified_in_top_k"] += 1

    return totals


def _ratio(values: Sequence[float]) -> float | None:
    """Lowest over highest. None when the highest is zero."""
    if not values:
        return None
    highest = max(values)
    if highest == 0.0:
        return None
    return min(values) / highest


def _gap(values: Sequence[float]) -> float | None:
    """Spread between the highest and lowest value."""
    return max(values) - min(values) if values else None


def audit_attribute(
    attribute: str,
    ranked_groups: Sequence[RankedGroup],
    group_of: Mapping[str, str],
    *,
    top_k: int,
    min_group_size: int,
    adverse_impact_threshold: float,
    max_gap: float,
) -> AttributeAudit:
    """Compute every fairness metric for one protected attribute.

    Args:
        attribute: Attribute name, for reporting.
        ranked_groups: Each posting's candidates in ranked order.
        group_of: Candidate id to demographic group.
        top_k: Shortlist depth. Every top-k metric uses this value.
        min_group_size: Groups with fewer appearances are suppressed.
        adverse_impact_threshold: Minimum acceptable four-fifths ratio.
        max_gap: Maximum acceptable parity and opportunity gap.

    Returns:
        Metrics and any threshold failures.
    """
    totals = _accumulate(ranked_groups, group_of, top_k)

    outcomes: list[GroupOutcome] = []
    suppressed: list[str] = []

    for group, bucket in sorted(totals.items()):
        appearances = int(bucket["appearances"])

        # Below this size the rate is noise. Reporting it would produce either a
        # false alarm or false reassurance, both worse than an honest omission.
        if appearances < min_group_size:
            suppressed.append(group)
            continue

        qualified = int(bucket["qualified"])
        outcomes.append(
            GroupOutcome(
                group=group,
                n_appearances=appearances,
                n_in_top_k=int(bucket["in_top_k"]),
                selection_rate=bucket["in_top_k"] / appearances,
                n_qualified=qualified,
                n_qualified_in_top_k=int(bucket["qualified_in_top_k"]),
                qualified_selection_rate=(
                    bucket["qualified_in_top_k"] / qualified if qualified else None
                ),
                mean_exposure=bucket["exposure"] / appearances,
            )
        )

    selection_rates = [outcome.selection_rate for outcome in outcomes]
    exposures = [outcome.mean_exposure for outcome in outcomes]
    qualified_rates = [
        outcome.qualified_selection_rate
        for outcome in outcomes
        if outcome.qualified_selection_rate is not None
    ]

    adverse_impact = _ratio(selection_rates)
    parity_gap = _gap(selection_rates)
    opportunity_gap = _gap(qualified_rates)
    exposure_ratio = _ratio(exposures)

    failures: list[str] = []

    if len(outcomes) < 2:
        # Not a pass. With one group there is nothing to compare, and reporting
        # a pass would imply a check that never ran.
        failures.append(
            f"{attribute}: fewer than two groups met the minimum size of "
            f"{min_group_size}; no comparison was possible"
        )
        return AttributeAudit(
            attribute=attribute,
            top_k=top_k,
            groups=tuple(outcomes),
            suppressed_groups=tuple(suppressed),
            adverse_impact_ratio=adverse_impact,
            demographic_parity_gap=parity_gap,
            equal_opportunity_gap=opportunity_gap,
            exposure_ratio=exposure_ratio,
            failures=tuple(failures),
        )

    inconclusive: list[str] = []

    # Significance of the widest selection-rate difference. This drives both the
    # adverse impact ratio and the parity gap, so it is tested once.
    lowest = min(outcomes, key=lambda o: o.selection_rate)
    highest = max(outcomes, key=lambda o: o.selection_rate)
    selection_p = two_proportion_p_value(
        lowest.n_in_top_k, lowest.n_appearances, highest.n_in_top_k, highest.n_appearances
    )

    # Corrected because `lowest` and `highest` were chosen for being extreme.
    threshold = bonferroni_threshold(len(outcomes))
    n_comparisons = max(1, len(outcomes) * (len(outcomes) - 1) // 2)
    selection_significant = selection_p is not None and selection_p < threshold

    def _note(message: str, *, significant: bool, p_value: float | None) -> None:
        """File a breach as a failure or as inconclusive, depending on the test."""
        if significant:
            failures.append(f"{message} (p={p_value:.4f} < {threshold:.4f})")
        else:
            suffix = f"p={p_value:.4f}" if p_value is not None else "test undefined"
            inconclusive.append(
                f"{message} — but not distinguishable from noise once corrected for "
                f"{n_comparisons} possible group comparisons ({suffix}, threshold "
                f"{threshold:.4f}); smallest group n={lowest.n_appearances}"
            )

    if adverse_impact is not None and adverse_impact < adverse_impact_threshold:
        _note(
            f"{attribute}: adverse impact ratio {adverse_impact:.3f} is below the "
            f"four-fifths threshold of {adverse_impact_threshold:.2f}",
            significant=selection_significant,
            p_value=selection_p,
        )

    if parity_gap is not None and parity_gap > max_gap:
        _note(
            f"{attribute}: demographic parity gap {parity_gap:.3f} exceeds {max_gap:.2f}",
            significant=selection_significant,
            p_value=selection_p,
        )

    # Significance of the widest qualified-rate difference, which drives the
    # equal opportunity gap. Tested separately because the qualified subsets are
    # smaller and can behave differently from the full groups.
    with_qualified = [o for o in outcomes if o.qualified_selection_rate is not None]
    qualified_p: float | None = None
    if len(with_qualified) >= 2:
        q_low = min(with_qualified, key=lambda o: o.qualified_selection_rate or 0.0)
        q_high = max(with_qualified, key=lambda o: o.qualified_selection_rate or 0.0)
        qualified_p = two_proportion_p_value(
            q_low.n_qualified_in_top_k,
            q_low.n_qualified,
            q_high.n_qualified_in_top_k,
            q_high.n_qualified,
        )

    if opportunity_gap is not None and opportunity_gap > max_gap:
        _note(
            f"{attribute}: equal opportunity gap {opportunity_gap:.3f} exceeds {max_gap:.2f} "
            f"— qualified candidates are being shortlisted at materially different rates",
            significant=qualified_p is not None and qualified_p < threshold,
            p_value=qualified_p,
        )

    if exposure_ratio is not None and exposure_ratio < adverse_impact_threshold:
        # Exposure is a mean rather than a proportion, so the z-test above does
        # not apply to it. It is also far more stable than a ratio of small
        # proportions, since every candidate contributes a value rather than a
        # 0 or 1. Reported as a failure directly, and flagged as not
        # significance-tested in the fairness report.
        failures.append(
            f"{attribute}: exposure ratio {exposure_ratio:.3f} is below "
            f"{adverse_impact_threshold:.2f} — one group is admitted to the shortlist but "
            f"placed consistently lower within it (not significance-tested)"
        )

    return AttributeAudit(
        attribute=attribute,
        top_k=top_k,
        groups=tuple(outcomes),
        suppressed_groups=tuple(suppressed),
        adverse_impact_ratio=adverse_impact,
        demographic_parity_gap=parity_gap,
        equal_opportunity_gap=opportunity_gap,
        exposure_ratio=exposure_ratio,
        selection_p_value=selection_p,
        qualified_p_value=qualified_p,
        significance_threshold=threshold,
        n_comparisons=n_comparisons,
        failures=tuple(failures),
        inconclusive=tuple(inconclusive),
    )
