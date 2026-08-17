"""Command line interface.

``print`` is permitted in this module only — CLI output to stdout is the point,
and the ruff configuration carves out this file specifically. Everywhere else in
the package, structured logging is required.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import typer

from guardmatch.core.config import get_settings
from guardmatch.data.candidates import generate_candidates
from guardmatch.data.jobs import generate_jobs
from guardmatch.data.labels import generate_hidden_factors, generate_labels
from guardmatch.data.protected import (
    Gender,
    generate_protected_attributes,
    night_availability_by_gender,
)
from guardmatch.data.storage import load_dataset, save_dataset
from guardmatch.fairness.audit import load_protected, run_audit
from guardmatch.ranking.baseline import baseline_scores
from guardmatch.ranking.dataset import build_dataset
from guardmatch.ranking.evaluate import Comparison, evaluate
from guardmatch.ranking.train import predict_scores, train_model
from guardmatch.registry.artifacts import load_model, save_model, update_fairness
from guardmatch.registry.metadata import ModelMetadata, assert_clean_tree, git_is_dirty, git_sha

app = typer.Typer(
    name="guardmatch",
    help="Resume screening and guard job matching.",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def main() -> None:
    """Resume screening and guard job matching.

    Present so Typer keeps subcommand dispatch even while only one command is
    registered. Without it, a single-command app collapses into a bare command
    and `guardmatch generate-data` is read as a stray argument.
    """


@app.command("generate-data")
def generate_data(
    output: Path = typer.Option(
        Path("data"), "--output", "-o", help="Directory to write the dataset to."
    ),
    seed: int | None = typer.Option(None, "--seed", help="Override the configured seed."),
    n_candidates: int | None = typer.Option(None, "--candidates", help="Override candidate count."),
    n_jobs: int | None = typer.Option(None, "--jobs", help="Override job posting count."),
    inject_bias: bool | None = typer.Option(
        None,
        "--inject-bias/--no-inject-bias",
        help="Correlate a protected attribute with night availability, so the fairness "
        "audit has a known bias to detect.",
    ),
    bias_strength: float = typer.Option(
        1.0,
        "--bias-strength",
        min=0.0,
        max=3.0,
        help="Scales the injected correlation. 1.0 is realistic but borderline against the "
        "four-fifths threshold; 2.0 produces a breach the audit detects reliably.",
    ),
) -> None:
    """Generate the synthetic dataset.

    Fully reproducible: the same seed and generator version always produce the
    same output.
    """
    settings = get_settings()

    resolved_seed = seed if seed is not None else settings.random_seed
    resolved_candidates = n_candidates if n_candidates is not None else settings.n_candidates
    resolved_jobs = n_jobs if n_jobs is not None else settings.n_jobs
    resolved_bias = inject_bias if inject_bias is not None else settings.inject_bias

    typer.echo(f"Generating {resolved_candidates} candidates (seed {resolved_seed})...")
    candidates = generate_candidates(resolved_candidates, resolved_seed)

    typer.echo(f"Generating {resolved_jobs} job postings...")
    jobs = generate_jobs(resolved_jobs, resolved_seed)

    typer.echo("Drawing hidden factors and labelling pairs...")
    hidden = generate_hidden_factors([c.candidate_id for c in candidates], resolved_seed)
    pairs = generate_labels(candidates, jobs, hidden, resolved_seed)

    typer.echo(
        f"Drawing protected attributes (inject_bias={resolved_bias}, strength={bias_strength})..."
    )
    protected = generate_protected_attributes(
        candidates, resolved_seed, inject_bias=resolved_bias, bias_strength=bias_strength
    )

    manifest = save_dataset(
        output,
        candidates=candidates,
        jobs=jobs,
        pairs=pairs,
        protected=protected,
        seed=resolved_seed,
        inject_bias=resolved_bias,
        created_at=datetime.now(UTC).isoformat(),
    )

    night_rates = night_availability_by_gender(candidates, protected)
    gap = abs(night_rates[Gender.FEMALE] - night_rates[Gender.MALE])

    typer.echo("")
    typer.echo(f"Written to {output.resolve()}")
    typer.echo(f"  generator version : {manifest.generator_version}")
    typer.echo(f"  candidates        : {manifest.n_candidates}")
    typer.echo(f"  job postings      : {manifest.n_jobs}")
    typer.echo(f"  labelled pairs    : {manifest.n_pairs}")
    typer.echo("")
    typer.echo("  grade distribution")
    total = max(manifest.n_pairs, 1)
    for grade in ("3", "2", "1", "0"):
        count = manifest.grade_counts.get(grade, 0)
        typer.echo(f"    grade {grade}: {count:7d}  {100 * count / total:5.1f}%")
    typer.echo("")
    typer.echo("  night availability by gender (bias check)")
    typer.echo(f"    female : {night_rates[Gender.FEMALE]:.3f}")
    typer.echo(f"    male   : {night_rates[Gender.MALE]:.3f}")
    typer.echo(f"    gap    : {gap:.3f}")

    if resolved_bias and gap < 0.15:
        typer.secho(
            "  WARNING: bias injection is on but the gap is small; the audit may not "
            "detect it reliably.",
            fg=typer.colors.YELLOW,
        )
    if not resolved_bias and gap > 0.10:
        typer.secho(
            "  WARNING: bias injection is off but a sizeable gap appeared; investigate "
            "before trusting the fairness baseline.",
            fg=typer.colors.YELLOW,
        )


@app.command("train")
def train(
    data: Path = typer.Option(Path("data"), "--data", "-d", help="Dataset directory."),
    models: Path = typer.Option(Path("models"), "--models", "-m", help="Artifact root."),
    version: str = typer.Option("v0.1.0", "--version", "-v", help="Version to write."),
    seed: int | None = typer.Option(None, "--seed", help="Override the split seed."),
    allow_dirty: bool = typer.Option(
        False,
        "--allow-dirty",
        help="Write an artifact even with uncommitted changes. For throwaway experiments "
        "only — the recorded git SHA will not describe the code that ran.",
    ),
) -> None:
    """Train the ranker and write a versioned, checksummed artifact."""
    settings = get_settings()
    resolved_seed = seed if seed is not None else settings.random_seed

    # Checked before any expensive work, so a dirty tree fails in a second
    # rather than after several minutes of training.
    assert_clean_tree(allow_dirty=allow_dirty)

    typer.echo(f"Loading dataset from {data}...")
    dataset = load_dataset(data)

    typer.echo("Parsing CVs and building features...")
    ranking_dataset = build_dataset(dataset, seed=resolved_seed)
    typer.echo(
        f"  train {ranking_dataset.train.n_groups} groups / "
        f"{len(ranking_dataset.train.features)} rows"
    )
    typer.echo(
        f"  valid {ranking_dataset.valid.n_groups} groups / "
        f"{len(ranking_dataset.valid.features)} rows"
    )

    typer.echo("Training LambdaRank...")
    result = train_model(ranking_dataset)

    model_scores = predict_scores(result.booster, ranking_dataset.valid)
    base_scores = baseline_scores(ranking_dataset.valid.features, ranking_dataset.feature_names)

    comparison = Comparison(
        model=evaluate(
            ranking_dataset.valid.labels,
            model_scores,
            ranking_dataset.valid.group_sizes,
            scorer_name="lambdarank",
        ),
        baseline=evaluate(
            ranking_dataset.valid.labels,
            base_scores,
            ranking_dataset.valid.group_sizes,
            scorer_name="baseline",
        ),
    )

    typer.echo("")
    typer.echo(f"  {'metric':<12}{'baseline':>11}{'model':>11}{'delta':>10}")
    for label, attribute in (
        ("NDCG@5", "ndcg_at_5"),
        ("NDCG@10", "ndcg_at_10"),
        ("MAP", "mean_average_precision"),
        ("MRR", "mean_reciprocal_rank"),
    ):
        base_value = getattr(comparison.baseline, attribute)
        model_value = getattr(comparison.model, attribute)
        typer.echo(
            f"  {label:<12}{base_value:>11.4f}{model_value:>11.4f}"
            f"{model_value - base_value:>+10.4f}"
        )

    typer.echo("")
    if comparison.model_beats_baseline:
        typer.secho(
            f"  Model beats the rule-based baseline by {comparison.ndcg_at_10_lift:+.1%}.",
            fg=typer.colors.GREEN,
        )
    else:
        typer.secho(
            "  Model does NOT meaningfully beat the rule-based baseline. "
            "This belongs in the model card as a finding, not hidden.",
            fg=typer.colors.RED,
        )

    for warning in comparison.model.warnings:
        typer.secho(f"  WARNING: {warning}", fg=typer.colors.YELLOW)

    metadata = ModelMetadata(
        model_version=version,
        trained_at=datetime.now(UTC).isoformat(),
        generator_version=dataset.manifest.generator_version,
        data_seed=dataset.manifest.seed,
        n_candidates=dataset.manifest.n_candidates,
        n_jobs=dataset.manifest.n_jobs,
        n_pairs=dataset.manifest.n_pairs,
        n_train_groups=ranking_dataset.train.n_groups,
        n_valid_groups=ranking_dataset.valid.n_groups,
        feature_names=list(ranking_dataset.feature_names),
        hyperparameters=result.params,
        best_iteration=result.best_iteration,
        git_sha=git_sha(),
        git_dirty=allow_dirty and git_is_dirty(),
    )

    directory = save_model(
        models,
        version=version,
        booster=result.booster,
        metadata=metadata,
        metrics=comparison.to_dict(),
        # Populated by `guardmatch audit` in Phase 9. Written empty rather than
        # omitted so the artifact shape is constant and its absence is visible.
        fairness={},
    )

    typer.echo("")
    typer.echo(f"Artifact written to {directory.resolve()}")
    typer.echo(f"  git sha       : {metadata.git_sha}")
    typer.echo(f"  best iteration: {metadata.best_iteration}")
    typer.echo(f"  features      : {len(metadata.feature_names)}")
    typer.secho(
        "  fairness.json is empty until `guardmatch audit` has run.",
        fg=typer.colors.YELLOW,
    )


@app.command("audit")
def audit(
    data: Path = typer.Option(Path("data"), "--data", "-d", help="Dataset directory."),
    models: Path = typer.Option(Path("models"), "--models", "-m", help="Artifact root."),
    version: str | None = typer.Option(None, "--version", "-v", help="Model version."),
    seed: int | None = typer.Option(None, "--seed", help="Split seed. Must match training."),
) -> None:
    """Run the fairness audit and write the result into the model artifact."""
    settings = get_settings()
    resolved_version = version or settings.model_version
    resolved_seed = seed if seed is not None else settings.random_seed

    typer.echo(f"Loading model {resolved_version}...")
    loaded = load_model(models, resolved_version)

    typer.echo(f"Loading dataset and demographics from {data}...")
    dataset = load_dataset(data)
    protected = load_protected(data)

    typer.echo("Rebuilding the held-out split...")
    ranking_dataset = build_dataset(dataset, seed=resolved_seed)

    typer.echo("Auditing...")
    report = run_audit(
        loaded.booster,
        ranking_dataset,
        protected,
        model_version=resolved_version,
        settings=settings,
    )

    typer.echo("")
    typer.echo(
        f"  k = {report.top_k}   four-fifths threshold = {report.adverse_impact_threshold:.2f}"
        f"   max gap = {report.max_gap:.2f}"
    )
    typer.echo(f"  {report.n_postings} postings, {report.n_rows} candidate appearances")

    for attribute in report.attributes:
        typer.echo("")
        status = "PASS" if attribute.passes else "FAIL"
        colour = typer.colors.GREEN if attribute.passes else typer.colors.RED
        typer.secho(f"  {attribute.attribute}  [{status}]", fg=colour, bold=True)

        typer.echo(f"    {'group':<12}{'n':>7}{'top-k rate':>12}{'qual. rate':>12}{'exposure':>11}")
        for group in attribute.groups:
            qualified = (
                f"{group.qualified_selection_rate:.3f}"
                if group.qualified_selection_rate is not None
                else "n/a"
            )
            typer.echo(
                f"    {group.group:<12}{group.n_appearances:>7}"
                f"{group.selection_rate:>12.3f}{qualified:>12}{group.mean_exposure:>11.4f}"
            )

        if attribute.suppressed_groups:
            typer.secho(
                f"    suppressed (below {report.min_group_size}): "
                f"{', '.join(attribute.suppressed_groups)}",
                fg=typer.colors.YELLOW,
            )

        ratio = attribute.adverse_impact_ratio
        typer.echo(
            f"    adverse impact {ratio:.3f}   "
            f"parity gap {attribute.demographic_parity_gap:.3f}   "
            f"opportunity gap {attribute.equal_opportunity_gap:.3f}   "
            f"exposure ratio {attribute.exposure_ratio:.3f}"
            if ratio is not None
            else "    metrics unavailable"
        )

        if attribute.selection_p_value is not None:
            typer.echo(
                f"    widest selection-rate difference: p = {attribute.selection_p_value:.4f}"
                f"   threshold {attribute.significance_threshold:.4f}"
                f"   ({attribute.n_comparisons} comparison(s), Bonferroni)"
            )

        for failure in attribute.failures:
            typer.secho(f"    ! {failure}", fg=typer.colors.RED)

        for note in attribute.inconclusive:
            typer.secho(f"    ? {note}", fg=typer.colors.YELLOW)

    update_fairness(models / resolved_version, report.to_dict())

    typer.echo("")
    if report.passes:
        typer.secho("  AUDIT PASSED", fg=typer.colors.GREEN, bold=True)
    else:
        typer.secho(
            f"  AUDIT FAILED — {len(report.failures)} threshold breach(es)",
            fg=typer.colors.RED,
            bold=True,
        )
    typer.echo(f"  Written to {(models / resolved_version / 'fairness.json').resolve()}")


if __name__ == "__main__":  # pragma: no cover
    app()
