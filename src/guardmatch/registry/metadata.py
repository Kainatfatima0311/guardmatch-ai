"""Provenance for a trained model.

Six months after a model ships, the question that gets asked is not "how good is
it" but "what produced this score". Answering that needs the code revision, the
data version and seed, the library versions, and the hyperparameters — all
recorded at training time, because none of them can be reconstructed afterwards.

The dirty-tree check is the part people push back on. Training from uncommitted
code produces an artifact whose recorded git SHA describes something that never
existed: the commit is real, but the code that ran was the commit plus whatever
was in the working tree. Every later attempt to reproduce the model silently
fails. Refusing to write is inconvenient once; an unreproducible model in
production is inconvenient permanently.
"""

from __future__ import annotations

import platform
import subprocess
from dataclasses import asdict, dataclass, field
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from guardmatch.core.exceptions import ArtifactError
from guardmatch.core.logging import get_logger

logger = get_logger(__name__)

# Libraries whose version can change a model's behaviour or its ability to load.
TRACKED_PACKAGES: tuple[str, ...] = ("lightgbm", "shap", "spacy", "numpy", "scikit-learn")


def _run_git(*args: str) -> str | None:
    """Run a git command, returning None when git or the repository is absent."""
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return None
    return result.stdout.strip()


def git_sha() -> str | None:
    """Current commit hash, or None outside a repository."""
    return _run_git("rev-parse", "HEAD")


def git_is_dirty() -> bool:
    """Whether the working tree has uncommitted changes.

    Returns False when git is unavailable, since there is nothing to verify.
    """
    status = _run_git("status", "--porcelain")
    return bool(status)


def library_versions() -> dict[str, str]:
    """Installed versions of the libraries that affect model behaviour."""
    versions: dict[str, str] = {"python": platform.python_version()}
    for package in TRACKED_PACKAGES:
        try:
            versions[package] = version(package)
        except PackageNotFoundError:  # pragma: no cover - all are hard dependencies
            versions[package] = "not installed"
    return versions


@dataclass(frozen=True)
class ModelMetadata:
    """Everything needed to explain where a model came from."""

    model_version: str
    trained_at: str
    generator_version: str
    data_seed: int
    n_candidates: int
    n_jobs: int
    n_pairs: int
    n_train_groups: int
    n_valid_groups: int
    feature_names: list[str]
    hyperparameters: dict[str, Any]
    best_iteration: int
    git_sha: str | None
    git_dirty: bool
    libraries: dict[str, str] = field(default_factory=library_versions)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ModelMetadata:
        return cls(**payload)


def assert_clean_tree(*, allow_dirty: bool) -> None:
    """Refuse to write an artifact from uncommitted code.

    Args:
        allow_dirty: Bypass the check. Intended for local experiments, never for
            a release.

    Raises:
        ArtifactError: The working tree is dirty and the bypass was not set.
    """
    if not git_is_dirty():
        return

    if allow_dirty:
        logger.warning(
            "training_from_dirty_tree",
            detail="recorded git SHA will not describe the code that ran",
        )
        return

    msg = (
        "refusing to write a model artifact from a dirty working tree. The recorded "
        "git SHA would not describe the code that produced the model, making it "
        "unreproducible. Commit the changes, or pass allow_dirty=True for a throwaway "
        "experiment."
    )
    raise ArtifactError(msg)
