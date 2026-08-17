# Fairness Report — GuardMatch AI

**Model version:** v0.1.0
**Shortlist depth:** k = 10
**Threshold:** four-fifths rule, adverse impact ratio ≥ 0.80
**Date:** 2026-08-17

---

## 1. Verdict

**The shipped model passes on every audited attribute.**

| Attribute | Adverse impact | Parity gap | Opportunity gap | Exposure ratio | Result |
|---|---|---|---|---|---|
| gender | 0.965 | 0.006 | 0.039 | 0.983 | **PASS** |
| age_band | 0.627 | 0.071 | 0.096 | 0.908 | **PASS** (inconclusive — see §6) |
| nationality | 0.956 | 0.007 | 0.022 | 0.973 | **PASS** |

Measured over 50 held-out job postings and 3,041 candidate appearances.

Section 5 is the more important part of this report: it records what the audit **failed to
catch**.

## 2. What is measured, and why these four

Classification fairness metrics do not fit a ranking system. They ask "was this person
selected". A ranking raises a finer question, because being placed eleventh instead of second
is a real harm even though both candidates are technically in the list. A system can admit
every group to the shortlist at equal rates and still bury one of them inside it.

| Metric | Question | Threshold |
|---|---|---|
| Adverse impact ratio | Does the lowest group reach the top 10 at ≥ 80% of the highest group's rate? | ≥ 0.80 |
| Demographic parity gap | How wide is the raw spread in top-10 rates? | ≤ 0.10 |
| Equal opportunity gap | Among *qualified* candidates, how wide is the spread? | ≤ 0.10 |
| **Exposure ratio** | Weighted by rank position, does one group sit systematically lower? | ≥ 0.80 |

Exposure is the ranking-specific one, using the standard `1/log2(rank+1)` discount so that
rank 1 counts for roughly 2.6 times rank 10.

`tests/test_fairness.py` contains a case built to prove exposure earns its place: two groups
shortlisted at *exactly* equal rates, one always at positions 1–5 and the other always at
6–10. Adverse impact reads 1.000 and the parity gap reads 0.000 — perfect fairness by every
selection-based measure. Only exposure catches it, and the audit fails as it should.

Equal opportunity is reported separately from demographic parity because the two answer
different questions. A group with fewer qualified applicants will show a lower overall
selection rate without the model treating anyone unfairly. Conflating them blames the model
for the composition of the applicant pool.

## 3. Three-layer defence

**Prevention.** Protected attributes have no field on `ParsedProfile`, the type the entire
scoring pipeline is built on. They are not filtered out later; they are absent from the
beginning. A runtime guard re-checks every input to the feature builder, and a static test
asserts that no module in `features`, `parsing`, `ranking`, `explain`, `registry` or `api`
imports the module where demographics live.

That last barrier is the strongest, and the reasoning is worth stating: using a protected
attribute must require someone to *add* an import that does not exist, rather than to *forget*
a filter that does. An addition shows up in every code review; an omission does not.

**Proxy monitoring.** Blocking direct attributes is insufficient, because a permitted feature
can carry demographic information. Four are registered and watched:

| Feature | Leaks | Mitigation |
|---|---|---|
| `shift_match` | Availability correlates with caring responsibilities, therefore with gender | Watched closely — this is the known worst case, see §7 |
| `recency_months` | Career breaks correlate with parental leave | Capped at 240 months. Contributes 0.0% — removal proposed for v0.2.0 |
| `role_count` | Correlates with age | Capped at 6 |
| `exp_gap` | Correlates with age | Retained; directly job-relevant and legally defensible |

**Measurement.** This report. Protected attributes are joined by candidate id at evaluation
time only, in a module unreachable from the scoring path.

The three are deliberately redundant. Prevention cannot see proxies; measurement only detects
harm after it has been learned.

## 4. Proving the audit works

A bias detector that has only ever run on clean data has never been shown to detect anything.

The generator can inject a correlation between gender and night-shift availability. **The
label function is untouched.** What changes is that `shift_match` — a legitimate,
job-relevant, entirely neutral-looking feature — becomes a proxy for a protected attribute.
This is how discrimination normally enters a hiring model: not because someone added a gender
feature, but because a defensible feature quietly carries demographic information.

| Scenario | Night-availability gap | Adverse impact | p-value | Audit result |
|---|---|---|---|---|
| Unbiased (shipped model) | 0.003 | 0.965 | 0.6652 | **pass** — correct |
| Injected, realistic strength | 0.402 | 0.875 | 0.1084 | **pass** — ⚠️ **missed** |
| Injected, strength 2.0 | 0.795 | 0.678 | < 0.0001 | **FAIL** — correctly caught |

Two tests enforce the ends of this table: the audit must pass on clean data, and must fail on
strongly biased data. A gate that fires on everything is as useless as one that fires on
nothing, and considerably more likely to be switched off.

## 5. What the audit failed to catch

**At realistic bias strength, the four-fifths rule does not fire.**

A night-availability gap of 0.40 between genders is not an extreme scenario — it is roughly
what a caring-responsibilities correlation looks like in practice. It produces an adverse
impact ratio of **0.875**: real, directional harm to one group, sitting comfortably above the
0.80 threshold and therefore passing the audit.

The reason is dilution. The bias reaches the model through a single feature, and that feature
only bites on the subset of postings whose shift pattern the candidate must cover. Two stages
of dilution separate a strong demographic correlation from a measurable selection-rate gap.

**This is a finding about the threshold, not about this generator.** The four-fifths rule is a
blunt instrument that detects gross disparity. It will not catch proxy bias of the strength
that realistically occurs, and a system that passes it has not been shown to be fair — only
shown not to be obviously unfair.

Practical implications, recorded rather than resolved:

- The 0.80 threshold should be treated as a floor, not a target. A ratio of 0.85 deserves
  investigation, not celebration.
- Exposure ratio and the proxy register carry more of the real weight here than adverse impact
  does.
- Directional monitoring over time would catch drift that a single-point threshold check
  cannot.

## 6. Two statistical corrections, and why both were needed

Getting the gate to fire on real findings and stay quiet on noise took two attempts. Both are
recorded because the intermediate state was wrong in a way that would have been easy to ship.

**First run: a false alarm.** The audit reported an adverse impact ratio of 0.627 on
`age_band` — apparently a serious breach, in a dataset where age is assigned at random and
cannot influence any score. The cause was a 319-member group whose selection rate happened to
land low. A ratio of two proportions is an unstable statistic, and the four-fifths rule
assumes sample sizes that make it stable.

**Second attempt: still wrong.** Adding a two-proportion z-test returned p = 0.0069 —
apparently significant, so the false alarm survived. The remaining error was subtler: the
ratio compares the **lowest against the highest** group, and those two are selected precisely
*because* they are extreme. Testing a post-hoc extreme pair as though it had been chosen in
advance inflates the false positive rate. With five age bands there are ten possible pairs, so
the most extreme one clears p < 0.05 routinely on pure noise.

**Fix: Bonferroni correction** over the implied pairwise comparisons. With five groups the
threshold becomes 0.005, and p = 0.0069 correctly falls back to *inconclusive*. With two
groups there is one comparison and nothing changes.

The `age_band` finding is therefore reported but not treated as a violation, and it is **not
hidden** — `fairness.json` records it under `inconclusive`, with the p-value, the corrected
threshold and the group sizes. The honest reading is "we do not have enough 55+ candidates to
tell", which is a prompt to collect more data rather than either an accusation or an all-clear.

Exposure ratio is **not** significance-tested, because it is a mean rather than a proportion.
It is also considerably more stable, since every candidate contributes a graded value instead
of a 0 or 1. This limitation is flagged in the failure message itself.

## 7. The feature that carries the most risk

SHAP global importance puts `shift_match` at **26.8%** of total effect — larger than the
security licence or certification coverage individually.

It is also the feature the proxy register flags as most likely to carry demographic
information, and the exact route the bias injection exploits.

Nothing has gone wrong. Shift availability is job-relevant and legitimately predictive: a site
that needs night cover needs candidates who can work nights. But the consequence is that the
model's single largest input is its largest fairness exposure, and removing the feature if it
ever fails would cost real ranking quality.

That trade-off is documented in advance rather than discovered under pressure. By contrast,
`recency_months` carries career-break proxy risk while contributing **0.0%** — a free removal,
proposed for v0.2.0.

## 8. What this report does not establish

**It does not certify that the model is fair.** Every number here was measured on synthetic
demographics, drawn from distributions chosen to be plausible rather than measured. Real
applicant populations have different group sizes, different correlations, and different
qualification distributions.

**It demonstrates that the machinery works.** Bias of sufficient strength is detected, noise
is not mistaken for bias, thresholds are enforced in CI, and the ranking-specific metric
catches a harm the selection-based ones miss.

**Before any production use:**

1. Re-run the audit against real, held-out applicant data.
2. Confirm the applicable legal standard for the operating jurisdiction. The four-fifths rule
   originates in US employment law and is retained here as a conservative default; it is a
   configuration value, not a constant.
3. Have the results reviewed by someone with employment-law expertise.
4. Establish ongoing monitoring. A model that is fair at release can stop being fair as the
   applicant population shifts — the drift hook in `core/metrics.py` exists to make that
   measurable, but the review process is not built.

## 9. If a threshold is breached

In order of preference:

1. Investigate the responsible feature via SHAP, and remove or bucket it.
2. Reweight training examples to balance group representation.
3. Apply post-processing re-ranking to equalise exposure.
4. Escalate to human review and document the model as unfit for automated shortlisting.

**Loosening the threshold is not an option.** The threshold is a commitment, and a commitment
that moves when it becomes inconvenient was never one.

## 10. Reproducing this

```bash
guardmatch generate-data --seed 42                          # clean
guardmatch train --version v0.1.0
guardmatch audit --version v0.1.0                           # -> models/v0.1.0/fairness.json

guardmatch generate-data --seed 42 --inject-bias -o data-biased --bias-strength 2.0
guardmatch train --data data-biased --models models-biased --version v0.1.0-biased
guardmatch audit --data data-biased --models models-biased --version v0.1.0-biased
```

The second run must fail. If it passes, the audit is broken and no result from it should be
trusted.

```bash
pytest -m gate -v          # fairness and leakage gates only
```

| Concern | Location |
|---|---|
| Metric implementations | `src/guardmatch/fairness/metrics.py` |
| Audit runner | `src/guardmatch/fairness/audit.py` |
| Gate tests | `tests/test_fairness.py` |
| Leakage barrier tests | `tests/test_leakage.py` |
| Per-model record | `models/v0.1.0/fairness.json` |
