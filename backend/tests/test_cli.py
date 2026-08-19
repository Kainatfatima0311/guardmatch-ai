"""CLI tests.

The command line is what a person actually runs, so leaving it untested means
the most-used surface of the project is the least verified. These tests exercise
the full pipeline end to end at small scale: generate, train, audit.

The dirty-tree guard gets its own test. It is the check that keeps a model
artifact's recorded git SHA honest, and it is also the one most likely to be
quietly weakened by someone in a hurry.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from guardmatch.cli import app
from guardmatch.data.storage import MANIFEST_FILE, PROTECTED_FILE
from guardmatch.registry import metadata
from guardmatch.registry.artifacts import CHECKSUMS_FILE, FAIRNESS_FILE, MODEL_FILE

runner = CliRunner()

# Small enough to run in a test, large enough that a group-level split leaves
# usable train and validation halves.
N_CANDIDATES = 150
N_JOBS = 12


@pytest.fixture(scope="module")
def dataset_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A generated dataset, built once for the module."""
    directory = tmp_path_factory.mktemp("data")
    result = runner.invoke(
        app,
        [
            "generate-data",
            "-o",
            str(directory),
            "--candidates",
            str(N_CANDIDATES),
            "--jobs",
            str(N_JOBS),
        ],
    )
    assert result.exit_code == 0, result.output
    return directory


@pytest.fixture(scope="module")
def trained_dir(dataset_dir: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A model artifact trained from that dataset."""
    models = tmp_path_factory.mktemp("models")
    result = runner.invoke(
        app,
        [
            "train",
            "--data",
            str(dataset_dir),
            "--models",
            str(models),
            "--version",
            "v0.0.1",
            # Passed unconditionally: whether the tree is dirty depends on where
            # the suite runs, and this fixture must not.
            "--allow-dirty",
        ],
    )
    assert result.exit_code == 0, result.output
    return models


# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------


def test_help_lists_every_command() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("generate-data", "train", "audit"):
        assert command in result.output


def test_bare_invocation_shows_help() -> None:
    """`no_args_is_help` — an empty invocation should teach, not fail silently."""
    result = runner.invoke(app, [])
    assert "generate-data" in result.output


# ---------------------------------------------------------------------------
# generate-data
# ---------------------------------------------------------------------------


def test_generate_data_writes_every_file(dataset_dir: Path) -> None:
    written = {path.name for path in dataset_dir.glob("*.json")}
    assert written == {
        "candidates.json",
        "jobs.json",
        "labels.json",
        PROTECTED_FILE,
        MANIFEST_FILE,
    }


def test_manifest_records_provenance(dataset_dir: Path) -> None:
    manifest = json.loads((dataset_dir / MANIFEST_FILE).read_text(encoding="utf-8"))
    assert manifest["n_candidates"] == N_CANDIDATES
    assert manifest["n_jobs"] == N_JOBS
    assert manifest["inject_bias"] is False
    assert manifest["generator_version"]
    assert sum(manifest["grade_counts"].values()) == manifest["n_pairs"]


def test_generate_data_is_reproducible(tmp_path: Path) -> None:
    """Same seed, byte-identical output. The claim the data card makes."""
    first, second = tmp_path / "a", tmp_path / "b"
    for target in (first, second):
        result = runner.invoke(
            app,
            [
                "generate-data",
                "-o",
                str(target),
                "--candidates",
                "60",
                "--jobs",
                "4",
                "--seed",
                "5",
            ],
        )
        assert result.exit_code == 0, result.output

    for name in ("candidates.json", "jobs.json", "labels.json", PROTECTED_FILE):
        assert (first / name).read_bytes() == (second / name).read_bytes()


def test_bias_injection_changes_the_reported_gap(tmp_path: Path) -> None:
    """The CLI must surface the night-availability gap, since that is how an
    operator confirms the injection took effect."""
    clean = runner.invoke(
        app, ["generate-data", "-o", str(tmp_path / "clean"), "--candidates", "200", "--jobs", "4"]
    )
    biased = runner.invoke(
        app,
        [
            "generate-data",
            "-o",
            str(tmp_path / "biased"),
            "--candidates",
            "200",
            "--jobs",
            "4",
            "--inject-bias",
            "--bias-strength",
            "2.0",
        ],
    )
    assert clean.exit_code == 0
    assert biased.exit_code == 0
    assert "night availability by gender" in clean.output
    assert "inject_bias=True" in biased.output


# ---------------------------------------------------------------------------
# train
# ---------------------------------------------------------------------------


def test_train_writes_a_complete_artifact(trained_dir: Path) -> None:
    directory = trained_dir / "v0.0.1"
    written = {path.name for path in directory.iterdir()}
    assert MODEL_FILE in written
    assert CHECKSUMS_FILE in written
    assert FAIRNESS_FILE in written


def test_train_reports_the_baseline_comparison(dataset_dir: Path, tmp_path: Path) -> None:
    """The comparison must be visible in the output, not buried in a file.

    An NDCG figure with nothing to compare it against is uninterpretable, and
    omitting the baseline is the easiest way to make a weak model look strong.
    """
    result = runner.invoke(
        app,
        [
            "train",
            "--data",
            str(dataset_dir),
            "--models",
            str(tmp_path / "m"),
            "--version",
            "v0.0.2",
            "--allow-dirty",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "baseline" in result.output
    assert "NDCG@10" in result.output


def test_train_refuses_to_overwrite_a_version(dataset_dir: Path, trained_dir: Path) -> None:
    """Versions are immutable, so a repeat write must fail rather than replace."""
    result = runner.invoke(
        app,
        [
            "train",
            "--data",
            str(dataset_dir),
            "--models",
            str(trained_dir),
            "--version",
            "v0.0.1",
            "--allow-dirty",
        ],
    )
    assert result.exit_code != 0


def test_train_refuses_a_dirty_tree_without_the_flag(
    dataset_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The guard that keeps a recorded git SHA truthful.

    The dirty state is forced rather than assumed. An earlier version of this
    test relied on the working tree being dirty "by definition during a test
    run", which is true on a developer's machine mid-change and false in CI,
    where the checkout is pristine — so the guard never fired and the test
    failed there while passing locally for the wrong reason.

    `assert_clean_tree` resolves `git_is_dirty` from its own module globals at
    call time, so patching it there is what the code under test actually sees.
    """
    monkeypatch.setattr(metadata, "git_is_dirty", lambda: True)

    result = runner.invoke(
        app,
        [
            "train",
            "--data",
            str(dataset_dir),
            "--models",
            str(tmp_path / "m2"),
            "--version",
            "v0.0.3",
        ],
    )
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# audit
# ---------------------------------------------------------------------------


def test_audit_writes_the_fairness_record(dataset_dir: Path, trained_dir: Path) -> None:
    result = runner.invoke(
        app,
        [
            "audit",
            "--data",
            str(dataset_dir),
            "--models",
            str(trained_dir),
            "--version",
            "v0.0.1",
        ],
    )
    assert result.exit_code == 0, result.output

    record = json.loads((trained_dir / "v0.0.1" / FAIRNESS_FILE).read_text(encoding="utf-8"))
    assert {a["attribute"] for a in record["attributes"]} == {
        "gender",
        "age_band",
        "nationality",
    }
    assert record["top_k"] == 10
    assert "passes" in record


def test_audit_output_names_every_attribute(dataset_dir: Path, trained_dir: Path) -> None:
    result = runner.invoke(
        app,
        [
            "audit",
            "--data",
            str(dataset_dir),
            "--models",
            str(trained_dir),
            "--version",
            "v0.0.1",
        ],
    )
    for attribute in ("gender", "age_band", "nationality"):
        assert attribute in result.output
    assert "Bonferroni" in result.output


def test_audit_leaves_checksums_valid(dataset_dir: Path, trained_dir: Path) -> None:
    """The audit rewrites one artifact file, so verification must still pass."""
    from guardmatch.registry.artifacts import load_model

    runner.invoke(
        app,
        ["audit", "--data", str(dataset_dir), "--models", str(trained_dir), "--version", "v0.0.1"],
    )
    loaded = load_model(trained_dir, "v0.0.1")
    assert loaded.fairness["attributes"]


def test_audit_rejects_an_unknown_version(dataset_dir: Path, trained_dir: Path) -> None:
    result = runner.invoke(
        app,
        ["audit", "--data", str(dataset_dir), "--models", str(trained_dir), "--version", "v9.9.9"],
    )
    assert result.exit_code != 0
