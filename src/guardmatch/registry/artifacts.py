"""Versioned model artifacts.

The brief asks for versioned artifacts rather than "a pickle file floating
around", and the distinction is worth spelling out.

A loose ``model.pkl`` records nothing about when it was trained, on what, with
which code, or how it performed. It cannot be rolled back with confidence
because there is nothing to compare against, and unpickling a file executes
whatever code it contains.

What is written here instead is a directory per version, containing the model in
LightGBM's own text format, the feature contract, full provenance, the metrics,
the fairness audit, and a checksum for every one of them.

**Loading verifies before it trusts.** A checksum mismatch means the artifact is
not the one that was evaluated and audited, so the service refuses to start
rather than serving a model nobody has measured. The same applies to the feature
contract: a stored feature order that disagrees with the code would produce
confident, plausible, entirely wrong scores.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import lightgbm as lgb

from guardmatch.core.exceptions import ArtifactError, ChecksumMismatchError
from guardmatch.core.logging import get_logger
from guardmatch.features.registry import validate_against
from guardmatch.registry.metadata import ModelMetadata

logger = get_logger(__name__)

MODEL_FILE = "model.txt"
FEATURE_NAMES_FILE = "feature_names.json"
METADATA_FILE = "metadata.json"
METRICS_FILE = "metrics.json"
FAIRNESS_FILE = "fairness.json"
CHECKSUMS_FILE = "checksums.json"

# Every file whose integrity is verified on load. checksums.json is excluded for
# the obvious reason that it cannot contain its own hash.
CHECKSUMMED_FILES: tuple[str, ...] = (
    MODEL_FILE,
    FEATURE_NAMES_FILE,
    METADATA_FILE,
    METRICS_FILE,
    FAIRNESS_FILE,
)


@dataclass(frozen=True)
class LoadedModel:
    """A verified model artifact, ready to serve."""

    booster: lgb.Booster
    metadata: ModelMetadata
    metrics: dict[str, Any]
    fairness: dict[str, Any]
    feature_names: tuple[str, ...]
    version: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    # sort_keys so an unchanged payload always produces an identical file, and
    # therefore an identical checksum.
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_model(
    root: Path,
    *,
    version: str,
    booster: lgb.Booster,
    metadata: ModelMetadata,
    metrics: dict[str, Any],
    fairness: dict[str, Any],
) -> Path:
    """Write a complete, checksummed artifact directory.

    Args:
        root: Directory holding all model versions.
        version: Semantic version, used as the directory name.
        booster: The trained model.
        metadata: Provenance.
        metrics: Evaluation results, including the baseline comparison.
        fairness: Audit output. May be empty before Phase 9 has run.

    Returns:
        The directory written.

    Raises:
        ArtifactError: The version directory already exists.
    """
    directory = root / version
    if directory.exists():
        msg = (
            f"{directory} already exists. Model versions are immutable — bump the "
            f"version rather than overwriting, or a metric could silently come to "
            f"describe a different model."
        )
        raise ArtifactError(msg)

    directory.mkdir(parents=True)

    # LightGBM's native text format, not pickle: readable, portable across
    # library versions, and it cannot execute code on load.
    booster.save_model(str(directory / MODEL_FILE), num_iteration=booster.best_iteration)

    _write_json(directory / FEATURE_NAMES_FILE, list(metadata.feature_names))
    _write_json(directory / METADATA_FILE, metadata.to_dict())
    _write_json(directory / METRICS_FILE, metrics)
    _write_json(directory / FAIRNESS_FILE, fairness)

    checksums = {name: _sha256(directory / name) for name in CHECKSUMMED_FILES}
    _write_json(directory / CHECKSUMS_FILE, checksums)

    logger.info(
        "model_artifact_written",
        version=version,
        path=str(directory),
        files=len(CHECKSUMMED_FILES) + 1,
        git_sha=metadata.git_sha,
    )

    return directory


def verify_checksums(directory: Path) -> None:
    """Check every artifact against its recorded hash.

    Raises:
        ArtifactError: A file or the checksum record is missing.
        ChecksumMismatchError: A file does not match its recorded hash.
    """
    checksum_path = directory / CHECKSUMS_FILE
    if not checksum_path.exists():
        msg = f"{checksum_path} is missing; artifact integrity cannot be verified"
        raise ArtifactError(msg)

    recorded: dict[str, str] = _read_json(checksum_path)

    for name in CHECKSUMMED_FILES:
        path = directory / name
        if not path.exists():
            msg = f"artifact file {name} is missing from {directory}"
            raise ArtifactError(msg)

        if name not in recorded:
            msg = f"no checksum recorded for {name} in {checksum_path}"
            raise ArtifactError(msg)

        actual = _sha256(path)
        if actual != recorded[name]:
            msg = (
                f"checksum mismatch for {name}: recorded {recorded[name][:12]}, "
                f"found {actual[:12]}. This artifact is not the one that was evaluated "
                f"and audited."
            )
            raise ChecksumMismatchError(msg)


def load_model(root: Path, version: str) -> LoadedModel:
    """Load and verify a model artifact.

    Verification is not optional and not configurable. Serving a model whose
    artifacts do not match their checksums means serving something that was
    never measured, which defeats the purpose of measuring.

    Args:
        root: Directory holding all model versions.
        version: Which version to load.

    Returns:
        The verified model with its metadata, metrics and audit.

    Raises:
        ArtifactError: The version is missing or incomplete.
        ChecksumMismatchError: An artifact has been modified.
        FeatureContractError: The stored feature list disagrees with the code.
    """
    directory = root / version
    if not directory.is_dir():
        available = sorted(p.name for p in root.iterdir() if p.is_dir()) if root.is_dir() else []
        msg = f"model version {version!r} not found in {root}. Available: {available}"
        raise ArtifactError(msg)

    verify_checksums(directory)

    feature_names = tuple(_read_json(directory / FEATURE_NAMES_FILE))

    # Raises FeatureContractError on any difference in membership or order.
    # Order matters: LightGBM receives positional columns, so a reordered
    # contract produces plausible wrong scores with no error anywhere.
    validate_against(feature_names)

    booster = lgb.Booster(model_file=str(directory / MODEL_FILE))
    metadata = ModelMetadata.from_dict(_read_json(directory / METADATA_FILE))

    logger.info(
        "model_loaded",
        version=version,
        git_sha=metadata.git_sha,
        trained_at=metadata.trained_at,
        features=len(feature_names),
    )

    return LoadedModel(
        booster=booster,
        metadata=metadata,
        metrics=_read_json(directory / METRICS_FILE),
        fairness=_read_json(directory / FAIRNESS_FILE),
        feature_names=feature_names,
        version=version,
    )


def list_versions(root: Path) -> list[str]:
    """Available model versions, newest-looking last."""
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir() and (p / MODEL_FILE).exists())


def update_fairness(directory: Path, fairness: dict[str, Any]) -> None:
    """Rewrite the fairness record and its checksum.

    The audit runs after training, so this is the one permitted mutation of an
    otherwise immutable artifact. Everything else stays fixed, and the checksum
    file is rewritten so verification still passes.
    """
    _write_json(directory / FAIRNESS_FILE, fairness)

    checksums = {name: _sha256(directory / name) for name in CHECKSUMMED_FILES}
    _write_json(directory / CHECKSUMS_FILE, checksums)

    logger.info("fairness_record_updated", path=str(directory))
