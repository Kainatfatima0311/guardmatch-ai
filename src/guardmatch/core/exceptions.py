"""Exception hierarchy for GuardMatch.

Every failure mode in the system has a named exception. The point is not
ceremony: a bare ``ValueError`` propagating out of the feature builder tells an
operator nothing, whereas ``ProtectedAttributeError`` says exactly what went
wrong and how serious it is.

Two of these are deliberately fatal rather than recoverable.
``ProtectedAttributeError`` and ``FairnessThresholdError`` represent conditions
where continuing would mean scoring candidates using information the system is
forbidden to use, or shipping a model that discriminates. Catching and
continuing past either of those would defeat the safeguards they exist to
enforce, so callers should let them propagate.
"""

from __future__ import annotations


class GuardMatchError(Exception):
    """Base class for every error raised by this package."""


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class ConfigurationError(GuardMatchError):
    """Settings are missing, malformed, or mutually inconsistent."""


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


class ParsingError(GuardMatchError):
    """CV text could not be parsed at all.

    A field that simply could not be extracted is *not* an error — it becomes
    ``None`` on the profile and a note in ``parse_warnings``. This exception is
    for input that is unusable, such as empty or non-text content.
    """


# ---------------------------------------------------------------------------
# Features
# ---------------------------------------------------------------------------


class FeatureError(GuardMatchError):
    """A feature could not be computed."""


class ProtectedAttributeError(FeatureError):
    """A protected attribute reached the feature layer.

    Fatal by design. Reaching this point means the system was about to score a
    candidate using an attribute it is forbidden to consider, so the correct
    response is to stop rather than to degrade gracefully.
    """


class FeatureContractError(FeatureError):
    """Feature names or ordering disagree with the loaded model.

    This is the train/serve skew guard. A model trained on one column order and
    served on another produces confident, plausible, entirely wrong scores — a
    failure that is invisible without this check.
    """


# ---------------------------------------------------------------------------
# Model and artifacts
# ---------------------------------------------------------------------------


class ModelError(GuardMatchError):
    """The model could not be trained, loaded, or used for inference."""


class ArtifactError(ModelError):
    """A versioned artifact directory is missing or incomplete."""


class ChecksumMismatchError(ArtifactError):
    """A model artifact does not match its recorded checksum.

    Either the artifact was modified after it was written, or the wrong file is
    present. Both mean the model being served is not the model that was
    evaluated and audited, so startup must fail.
    """


class ModelNotLoadedError(ModelError):
    """Inference was attempted before the model finished loading."""


# ---------------------------------------------------------------------------
# Fairness
# ---------------------------------------------------------------------------


class FairnessThresholdError(GuardMatchError):
    """A fairness metric breached its configured threshold.

    Raised by the audit and surfaced by the fairness gate in CI. The intended
    response is to investigate and fix the model, never to relax the threshold.
    """
