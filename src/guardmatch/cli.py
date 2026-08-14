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
from guardmatch.data.storage import save_dataset

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

    typer.echo(f"Drawing protected attributes (inject_bias={resolved_bias})...")
    protected = generate_protected_attributes(
        candidates, resolved_seed, inject_bias=resolved_bias
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


if __name__ == "__main__":  # pragma: no cover
    app()
