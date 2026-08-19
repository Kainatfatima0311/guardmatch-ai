# Data Card — GuardMatch AI Synthetic Dataset

**Generator version:** 1.0.0
**Default seed:** 42
**Generated:** 2026-08-15
**Command:** `guardmatch generate-data`

---

## 1. What this dataset is

A fully synthetic dataset of security guard applications, job postings, and graded
relevance labels, used to train and evaluate the GuardMatch ranker.

**No real person appears in this data.** Every CV, name, employer and demographic value is
generated. Nothing here derives from a real applicant, a real posting, or a real hiring
decision.

## 2. Why it is synthetic

Three reasons, in order of weight.

**Privacy.** Real CVs contain names, addresses, dates of birth and employment history.
Committing them to a public repository would be a data breach regardless of intent.

**No labels exist.** SAJCO's historical hiring outcomes are not available in a form that
could be joined to applications.

**Inherited bias.** Even if historical labels were available, training on them would teach
the model whatever patterns were present in past decisions — including any discrimination —
and present the result as objective. Generating labels from an explicit, inspectable rule is
the more honest starting point for a system whose purpose includes fairness auditing.

The cost of this choice is realism, and it is a real cost. See Section 8.

## 3. Contents

| File | Rows | Size | Contents |
|---|---|---|---|
| `candidates.json` | 5,000 | 3.9 MB | CV text plus the ground truth it was written from |
| `jobs.json` | 200 | 90 KB | Job postings; each is one ranking query group |
| `labels.json` | 12,040 | 988 KB | Graded (job, candidate) relevance pairs |
| `protected.json` | 5,000 | 603 KB | Demographics — **evaluation only** |
| `manifest.json` | — | 283 B | Seed, version, counts, grade distribution |

### Candidates

| Field | Distribution |
|---|---|
| `years_experience` | Skewed low: 18% under 1yr, 30% 1–3yr, 26% 3–6yr, 16% 6–10yr, 10% 10–25yr |
| `certifications` | 9 types. Security licence 78%; specialist certifications 7–9% |
| `shift_availability` | Day 86%, weekend 58%, night 47%, rotating 39% |
| `driving_licence` | 62% |
| `previous_role_count` | Derived from experience — 0 to 6 |
| `cv_text` | 90–820 characters, median 315 |

`cv_text` is assembled from templates with randomised section order, randomised section
headings, and a randomly chosen surface form for every stated fact. Some facts are
deliberately omitted — experience is stated 92% of the time, availability 85%, driving
status 70% — so the parser encounters genuinely missing information rather than only
information it failed to find.

**All 47 certification phrasing variants appear in the corpus.** This is checked, because a
parser evaluated only against the phrasing it was written for demonstrates nothing.

### Job postings

Requirements are correlated with site type rather than drawn independently: construction
sites ask for health and safety and a driver, events ask for conflict management, industrial
sites skew to night shifts. Independent draws would produce postings no employer would write,
and a model trained on those learns associations that do not exist.

12% of postings are specialist — close protection or dog handling — where almost every
candidate is a partial match. Those are the postings where ranking actually earns its keep.

### Labels

| Grade | Meaning | Count | Share |
|---|---|---|---|
| 3 | Strong fit — interview first | 1,903 | 15.8% |
| 2 | Good fit — would interview | 2,470 | 20.5% |
| 1 | Marginal — only if the shortlist is thin | 3,284 | 27.3% |
| 0 | Not suitable | 4,383 | 36.4% |

Query groups hold 40–80 candidates each. The median posting has **8 grade-3 candidates**
against a top-10 shortlist, so filling the shortlist correctly requires ranking grade-2
candidates well rather than just identifying the obvious few.

**78% of candidates who appear in three or more postings receive different grades across
them.** This is the check that the labels are genuinely pairwise. Were that figure near zero,
the labels would encode a single global "candidate quality" ordering and the job-matching
premise would be fiction.

## 4. Anti-circularity design

The central risk in a synthetic ranking dataset is that the label function and the feature
set are built from the same variables. When that happens the model does not learn about
hiring — it reverse-engineers the generator's arithmetic, NDCG lands near 0.99, and every
downstream number is meaningless.

Four mitigations are built into `data/labels.py`.

**Hidden factors — 20% of the label.** `interview_score` and `reference_check` are drawn per
candidate and never exposed as features. In real hiring these matter and are invisible at
CV-screening time, so their absence from the feature set is realistic rather than
contrived. They impose a hard ceiling on achievable NDCG, which is the intent.

They are held per candidate rather than per pair because they model stable traits — someone
who interviews well interviews well everywhere. Drawn per pair they would be pure noise;
drawn per candidate they are a genuine latent variable.

**Label noise — 12%.** Roughly one label in eight is shifted by a grade. Real reviewers
disagree with each other and with themselves.

**Three non-linear interactions.**

1. A missing gating certification multiplies the score by 0.25 rather than zeroing it — an
   unlicensed candidate with a decade of experience remains a better prospect than an
   unlicensed novice, and collapsing both to zero would discard usable signal.
2. Holding the licence *and* meeting the experience minimum pays a bonus that neither
   condition pays alone.
3. Shift mismatch costs 0.12 on industrial and construction sites, where cover cannot lapse,
   against 0.04 elsewhere.

A purely additive rule would be recoverable by linear regression, which would make the choice
of a gradient-boosted ranker pointless.

**A sanity band on the result.** NDCG@10 above 0.95 is treated as a defect. The realistic
target band is 0.75–0.85. See `ranking/evaluate.py`.

## 5. Deliberate bias injection

`--inject-bias` correlates gender with night-shift availability. It is **off by default**.

| Setting | Female night availability | Male | Gap |
|---|---|---|---|
| `inject_bias=false` | 0.456 | 0.459 | **0.003** |
| `inject_bias=true` | 0.229 | 0.631 | **0.402** |

**The label function does not change.** What changes is that `shift_match` — a legitimate,
job-relevant, entirely neutral-looking feature — becomes a proxy for a protected attribute.
Any model trained on the biased variant will disadvantage one group through it.

This is how discrimination normally enters a hiring model: not because someone added a gender
feature, but because a defensible feature quietly carries demographic information.

The switch exists to prove the fairness audit works. A bias detector that has only ever run
on clean data has never been shown to detect anything. `backend/tests/test_fairness.py` asserts that
the audit catches this injected bias.

## 6. Protected attributes

`gender`, `age_band` and `nationality` are generated, because fairness cannot be measured
without them.

They are written to **their own file** and loaded by their own module. `load_dataset()`
requires an explicit `with_protected=True`, and `guardmatch.features` does not import
`guardmatch.data.protected` at all. A static test asserts that absence.

The design intent: using a protected attribute should require someone to *add* an import that
is not there, not merely to *forget* a filter that is.

## 7. Reproducibility

The same seed and generator version always produce byte-identical files. Verified across
three separate processes.

This required one non-obvious fix. Set-valued fields are serialised **sorted**, because
frozenset iteration order follows string hashes and Python randomises those per process. Left
unsorted, the same data written twice produced two different files — and a metric that cannot
be traced to a dataset by checksum is not reproducible in any useful sense.

```bash
guardmatch generate-data --seed 42
guardmatch generate-data --seed 42 --inject-bias   # for the fairness demonstration
```

The dataset is **not committed** — `data/` is gitignored. It is regenerable from the seed, so
committing 5.6 MB would add weight without adding information. Model artifacts under
`models/` *are* committed, since those are a deliverable.

## 8. Limitations

**This dataset does not resemble SAJCO's real applicant pool.** Distributions were chosen to
be plausible, not measured. Any metric reported against this data describes performance on
generated data and nothing more.

**Fairness results here prove the machinery, not the outcome.** The audit demonstrates that
bias is detectable and that thresholds are enforced. It does not certify that the model is
fair on real applicants, whose demographic structure and correlations differ.

**The parser is evaluated against generated phrasing.** Coverage of the 47 variants is
verified, but real CVs contain formatting, spelling and structure this generator does not
produce.

**Labels come from a rule, not from people.** Even with hidden factors and noise, the
underlying structure is more consistent than real hiring decisions are.

Before any production use: retrain and re-audit on real, held-out data, and have the fairness
results reviewed by someone with employment-law expertise for the relevant jurisdiction.
