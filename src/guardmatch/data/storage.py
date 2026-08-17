"""Dataset persistence.

Everything is written as JSON rather than a binary format. The dataset is
regenerable from a seed, so read speed matters less than being able to open a
file and see what is in it — which is the difference between debugging a
labelling bug in ten minutes and in a day.

Protected attributes are written to their **own file**. That is not tidiness:
loading demographics has to be a deliberate act by a caller that names the file,
so nothing picks them up incidentally while loading a training set.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from guardmatch.data.labels import LabelledPair, grade_distribution
from guardmatch.data.protected import AgeBand, Gender, Nationality, ProtectedAttributes
from guardmatch.schemas.candidate import GeneratedCandidate
from guardmatch.schemas.job import Job

# Bumped whenever the generation logic changes in a way that alters output for
# an unchanged seed. Recorded in the manifest so a metric can always be traced
# to the exact data that produced it.
GENERATOR_VERSION = "1.0.0"

CANDIDATES_FILE = "candidates.json"
JOBS_FILE = "jobs.json"
LABELS_FILE = "labels.json"
PROTECTED_FILE = "protected.json"
MANIFEST_FILE = "manifest.json"


@dataclass(frozen=True)
class Manifest:
    """Provenance for one generated dataset."""

    generator_version: str
    seed: int
    n_candidates: int
    n_jobs: int
    n_pairs: int
    inject_bias: bool
    grade_counts: dict[str, int]
    created_at: str


@dataclass(frozen=True)
class Dataset:
    """A complete generated dataset.

    ``protected`` is optional and defaults to empty. Training and feature code
    load a dataset without it; only the fairness audit asks for it.
    """

    candidates: list[GeneratedCandidate]
    jobs: list[Job]
    pairs: list[LabelledPair]
    manifest: Manifest
    protected: dict[str, ProtectedAttributes] | None = None


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_dataset(
    directory: Path,
    *,
    candidates: list[GeneratedCandidate],
    jobs: list[Job],
    pairs: list[LabelledPair],
    protected: dict[str, ProtectedAttributes],
    seed: int,
    inject_bias: bool,
    created_at: str,
) -> Manifest:
    """Write a dataset to ``directory`` and return its manifest."""
    manifest = Manifest(
        generator_version=GENERATOR_VERSION,
        seed=seed,
        n_candidates=len(candidates),
        n_jobs=len(jobs),
        n_pairs=len(pairs),
        inject_bias=inject_bias,
        grade_counts={str(k): v for k, v in grade_distribution(pairs).items()},
        created_at=created_at,
    )

    _write_json(directory / CANDIDATES_FILE, [c.model_dump(mode="json") for c in candidates])
    _write_json(directory / JOBS_FILE, [j.model_dump(mode="json") for j in jobs])
    _write_json(directory / LABELS_FILE, [asdict(p) for p in pairs])
    _write_json(directory / PROTECTED_FILE, [asdict(p) for p in protected.values()])
    _write_json(directory / MANIFEST_FILE, asdict(manifest))

    return manifest


def load_dataset(directory: Path, *, with_protected: bool = False) -> Dataset:
    """Read a dataset from ``directory``.

    Args:
        directory: Where the dataset was written.
        with_protected: Load demographics as well. Defaults to false, so a
            caller that does not explicitly ask never receives them.
    """
    candidates = [
        GeneratedCandidate.model_validate(row) for row in _read_json(directory / CANDIDATES_FILE)
    ]
    jobs = [Job.model_validate(row) for row in _read_json(directory / JOBS_FILE)]
    pairs = [LabelledPair(**row) for row in _read_json(directory / LABELS_FILE)]
    manifest = Manifest(**_read_json(directory / MANIFEST_FILE))

    protected: dict[str, ProtectedAttributes] | None = None
    if with_protected:
        protected = {}
        for row in _read_json(directory / PROTECTED_FILE):
            attrs = ProtectedAttributes(
                candidate_id=row["candidate_id"],
                gender=Gender(row["gender"]),
                age_band=AgeBand(row["age_band"]),
                nationality=Nationality(row["nationality"]),
            )
            protected[attrs.candidate_id] = attrs

    return Dataset(
        candidates=candidates,
        jobs=jobs,
        pairs=pairs,
        manifest=manifest,
        protected=protected,
    )
