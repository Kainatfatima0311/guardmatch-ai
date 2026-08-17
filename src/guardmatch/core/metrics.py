"""Prometheus metrics and the drift snapshot hook.

The brief asks for monitoring hooks, not just logging. Logs answer "what
happened in this request"; metrics answer "what is happening across all of
them", which is the question that catches a parser silently degrading after a
dependency upgrade.

Three of these deserve explanation.

``parse_failures`` and ``parse_warnings`` are tracked separately. A failure is
loud and obvious; a warning is the dangerous one, because a parser that quietly
stops recognising a certification produces plausible scores that are simply
wrong. A rising warning rate is the earliest available signal.

``score_distribution`` is recorded because a model that starts returning scores
in a narrower band than it did at training time is drifting, even while every
request still returns 200.

``snapshot_feature_distributions`` captures the input distribution the model was
trained and evaluated against. Full drift detection is out of scope for this
iteration, but the baseline has to be recorded now for any later comparison to
mean anything.
"""

from __future__ import annotations

import statistics
from typing import Any

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest

from guardmatch.core.config import get_settings

# A dedicated registry rather than the global default, so tests can construct an
# isolated one and metric definitions do not collide across imports.
REGISTRY = CollectorRegistry()

# ---------------------------------------------------------------------------
# Request-level metrics
# ---------------------------------------------------------------------------

requests_total = Counter(
    "guardmatch_requests_total",
    "Total API requests.",
    labelnames=("endpoint", "method", "status"),
    registry=REGISTRY,
)

request_duration_seconds = Histogram(
    "guardmatch_request_duration_seconds",
    "Request duration in seconds.",
    labelnames=("endpoint",),
    # Buckets chosen around the design doc's targets: 300ms p95 for a single
    # score and 2s for a 100-candidate rank. Default buckets would put almost
    # every request in one bucket and reveal nothing.
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.3, 0.5, 1.0, 2.0, 5.0, 10.0),
    registry=REGISTRY,
)

rank_batch_size = Histogram(
    "guardmatch_rank_batch_size",
    "Number of candidates per /rank request.",
    buckets=(1, 5, 10, 25, 50, 100, 250, 500),
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# Pipeline metrics
# ---------------------------------------------------------------------------

parse_failures_total = Counter(
    "guardmatch_parse_failures_total",
    "CV texts that could not be parsed at all.",
    labelnames=("reason",),
    registry=REGISTRY,
)

parse_warnings_total = Counter(
    "guardmatch_parse_warnings_total",
    "Fields the parser flagged as ambiguous or unextractable.",
    labelnames=("field",),
    registry=REGISTRY,
)

score_distribution = Histogram(
    "guardmatch_score_distribution",
    "Distribution of raw relative ranking scores.",
    buckets=(-5.0, -3.0, -2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0, 3.0, 5.0),
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# Service state
# ---------------------------------------------------------------------------

model_info = Gauge(
    "guardmatch_model_info",
    "Active model version. Always 1; the version is carried in the label.",
    labelnames=("version",),
    registry=REGISTRY,
)

model_loaded = Gauge(
    "guardmatch_model_loaded",
    "1 when the model is loaded and checksum-verified, 0 otherwise.",
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# Drift baseline
# ---------------------------------------------------------------------------

feature_mean = Gauge(
    "guardmatch_feature_mean",
    "Rolling mean of each input feature, for drift comparison.",
    labelnames=("feature",),
    registry=REGISTRY,
)

feature_stdev = Gauge(
    "guardmatch_feature_stdev",
    "Rolling standard deviation of each input feature, for drift comparison.",
    labelnames=("feature",),
    registry=REGISTRY,
)


def set_model_info(version: str, *, loaded: bool) -> None:
    """Record the active model version and whether it is ready to serve."""
    model_info.labels(version=version).set(1)
    model_loaded.set(1 if loaded else 0)


def observe_scores(scores: list[float]) -> None:
    """Record a batch of raw ranking scores."""
    for score in scores:
        score_distribution.observe(score)


def snapshot_feature_distributions(
    feature_names: list[str], rows: list[list[float | None]]
) -> None:
    """Record summary statistics for a batch of feature vectors.

    This is the drift baseline. Missing values are excluded rather than treated
    as zero — imputing them here would make the recorded distribution disagree
    with what the model actually saw, which defeats the purpose of recording it.
    """
    if not rows:
        return

    for index, name in enumerate(feature_names):
        values: list[float] = []
        for row in rows:
            value = row[index]
            if value is not None:
                values.append(float(value))
        if not values:
            continue
        feature_mean.labels(feature=name).set(statistics.fmean(values))
        # stdev is undefined for a single observation; report 0 rather than raise.
        feature_stdev.labels(feature=name).set(statistics.stdev(values) if len(values) > 1 else 0.0)


def render_metrics() -> bytes:
    """Return the Prometheus exposition payload for the /metrics endpoint."""
    return generate_latest(REGISTRY)


def initialise_metrics() -> None:
    """Set metrics that are known at startup.

    Called from the API lifespan so that ``/metrics`` reports a model version
    from the first scrape rather than only after the first request.
    """
    settings = get_settings()
    model_info.labels(version=settings.model_version).set(1)
    model_loaded.set(0)


def _reset_for_tests() -> Any:  # pragma: no cover - test helper
    """Clear collected values. Used by tests only."""
    for metric in (feature_mean, feature_stdev, model_info):
        metric.clear()
    return None
