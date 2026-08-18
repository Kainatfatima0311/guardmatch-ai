"""Running the fairness audit against a trained model.

This is the only place in the codebase where protected attributes and model
predictions meet. It sits deliberately outside the scoring path: nothing here is
importable from `features`, `ranking`, `explain` or `api`, and
`tests/test_leakage.py` enforces that.

The audit ranks the held-out postings with the model, joins demographics **by
candidate id at evaluation time only**, and measures outcomes by group. The
model never sees the join.

One design choice is worth stating. The audit reports a failure rather than
raising, and the *test* is what fails the build. Keeping the two separate means
the full report is always produced — an audit that aborted on the first breach
would hide every other finding behind it, which is precisely the information
needed to decide what to do about the first.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import lightgbm as lgb

from guardmatch.core.config import Settings, get_settings
from guardmatch.core.logging import get_logger
from guardmatch.data.protected import ProtectedAttributes
from guardmatch.data.storage import Dataset
from guardmatch.fairness.metrics import AttributeAudit, RankedGroup, audit_attribute
from guardmatch.ranking.dataset import RankingDataset
from guardmatch.ranking.train import predict_scores

logger = get_logger(__name__)

# The attributes measured. Each maps to a field on ProtectedAttributes.
AUDITED_ATTRIBUTES: tuple[str, ...] = ("gender", "age_band", "nationality")


@dataclass(frozen=True)
class FairnessReport:
    """The complete audit for one model."""

    model_version: str
    top_k: int
    adverse_impact_threshold: float
    max_gap: float
    min_group_size: int
    attributes: tuple[AttributeAudit, ...]
    n_postings: int
    n_rows: int

    @property
    def passes(self) -> bool:
        """Whether every audited attribute cleared every threshold."""
        return all(audit.passes for audit in self.attributes)

    @property
    def failures(self) -> tuple[str, ...]:
        """Every statistically significant threshold breach."""
        return tuple(failure for audit in self.attributes for failure in audit.failures)

    @property
    def inconclusive(self) -> tuple[str, ...]:
        """Breaches that could not be distinguished from sampling noise.

        Reported but not blocking. These are a prompt to gather more data for the
        affected group, not evidence of discrimination — and not something to
        leave out of the report either.
        """
        return tuple(note for audit in self.attributes for note in audit.inconclusive)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_version": self.model_version,
            "top_k": self.top_k,
            "adverse_impact_threshold": self.adverse_impact_threshold,
            "max_gap": self.max_gap,
            "min_group_size": self.min_group_size,
            "n_postings": self.n_postings,
            "n_rows": self.n_rows,
            "passes": self.passes,
            "failures": list(self.failures),
            "inconclusive": list(self.inconclusive),
            "attributes": [audit.to_dict() for audit in self.attributes],
        }


def rank_validation_groups(
    booster: lgb.Booster, ranking_dataset: RankingDataset
) -> list[RankedGroup]:
    """Rank each held-out posting with the model.

    Rows arrive grouped and contiguous, so the group sizes slice them back into
    postings. Within each posting, candidates are sorted by predicted score,
    which is exactly what a reviewer would see.
    """
    split = ranking_dataset.valid
    scores = predict_scores(booster, split)

    ranked: list[RankedGroup] = []
    offset = 0

    for job_id, size in zip(split.job_ids, split.group_sizes, strict=True):
        indices = range(offset, offset + size)
        # Same tiebreak as the serving Ranker, so the audit measures the
        # ordering the service would actually produce.
        order = sorted(indices, key=lambda i: (-scores[i], split.candidate_ids[i]))

        ranked.append(
            RankedGroup(
                job_id=job_id,
                candidate_ids=[split.candidate_ids[i] for i in order],
                grades=[split.labels[i] for i in order],
            )
        )
        offset += size

    return ranked


def run_audit(
    booster: lgb.Booster,
    ranking_dataset: RankingDataset,
    protected: dict[str, ProtectedAttributes],
    *,
    model_version: str,
    settings: Settings | None = None,
) -> FairnessReport:
    """Audit a model's held-out rankings for group fairness.

    Args:
        booster: The trained model.
        ranking_dataset: Train and validation splits. Only validation is used.
        protected: Demographics keyed by candidate id, loaded separately.
        model_version: Recorded in the report.
        settings: Thresholds. Defaults to application settings.

    Returns:
        The full report, including any threshold breaches. Does not raise on
        failure — see the module docstring.
    """
    resolved = settings or get_settings()
    ranked_groups = rank_validation_groups(booster, ranking_dataset)

    audits: list[AttributeAudit] = []
    for attribute in AUDITED_ATTRIBUTES:
        group_of = {
            candidate_id: str(getattr(attrs, attribute))
            for candidate_id, attrs in protected.items()
        }
        audits.append(
            audit_attribute(
                attribute,
                ranked_groups,
                group_of,
                top_k=resolved.fairness_top_k,
                min_group_size=resolved.min_group_size,
                adverse_impact_threshold=resolved.adverse_impact_threshold,
                max_gap=resolved.max_fairness_gap,
            )
        )

    report = FairnessReport(
        model_version=model_version,
        top_k=resolved.fairness_top_k,
        adverse_impact_threshold=resolved.adverse_impact_threshold,
        max_gap=resolved.max_fairness_gap,
        min_group_size=resolved.min_group_size,
        attributes=tuple(audits),
        n_postings=len(ranked_groups),
        n_rows=sum(len(group.candidate_ids) for group in ranked_groups),
    )

    if report.passes:
        logger.info(
            "fairness_audit_passed",
            model_version=model_version,
            attributes=len(audits),
            postings=report.n_postings,
        )
    else:
        # Warning rather than info: a breach means the model discriminates by
        # the project's own stated standard, and that should be visible in any
        # log search for problems.
        logger.warning(
            "fairness_audit_failed",
            model_version=model_version,
            failures=list(report.failures),
        )

    return report


def load_protected(data_dir: Path) -> dict[str, ProtectedAttributes]:
    """Load demographics.

    A thin wrapper that exists to keep the explicit `with_protected=True` in one
    place, so loading demographics is always a deliberate act rather than
    something a caller can do by accident.
    """
    from guardmatch.data.storage import load_dataset

    dataset: Dataset = load_dataset(data_dir, with_protected=True)
    if dataset.protected is None:  # pragma: no cover - defensive
        msg = f"no protected attributes found in {data_dir}"
        raise ValueError(msg)
    return dataset.protected
