# Model Card — GuardMatch AI v0.1.0

**Model:** LightGBM LambdaRank candidate ranker
**Version:** v0.1.0
**Released:** 2026-08-17
**Git SHA:** `32db2090e8a160caf2ccbf10a728ae721a3d3b0c`
**Artifact:** `backend/models/v0.1.0/`
**Owner:** Kainat Fatima

---

## 1. What this model does

Given one job posting and a set of applications, it orders the applicants by fit and explains
each placement.

It reads a CV, extracts the job-relevant facts, compares them against what the posting asks
for, and produces a score that is meaningful **only as an ordering within that posting**.

## 2. Intended use

**Intended:** producing a shortlist for a human reviewer to work through, in place of reading
several hundred applications in an arbitrary order.

**The output is an ordering, not a decision.** No endpoint returns an accept or reject verdict,
and none should be built on top of one without revisiting everything in section 6.

### Out of scope

| Not for | Why |
|---|---|
| Automated rejection | The model orders candidates; it has no concept of a threshold, and section 6 explains why one should not be inferred |
| Final hiring decisions | It sees a CV. Interviews, references and judgement are outside its input entirely |
| Comparing candidates across postings | Scores are relative to one posting. A 2.9 here and a 2.9 there are unrelated numbers |
| Ranking for roles other than security guard | The vocabulary, features and label design are specific to this domain |
| Any use without human review | Stated as a condition of use, not as a disclaimer |

## 3. Performance

Measured on 50 held-out job postings and 3,041 candidate appearances, split at the **posting**
level so no posting appears in both training and validation.

| Metric | Rule-based baseline | LambdaRank | Delta |
|---|---|---|---|
| NDCG@10 | 0.804 | **0.904** | +0.100 |
| NDCG@5 | 0.817 | 0.922 | +0.105 |
| MAP | 0.804 | 0.899 | +0.095 |
| MRR | 0.964 | 1.000 | +0.036 |

**The baseline matters more than the headline number.** It is a twenty-line rule-based scorer
with no learned parameters, and it is included because an NDCG of 0.904 is uninterpretable on
its own. The model beats it by 12.4%, so machine learning earned its place here — that is a
finding, not an assumption.

### What these numbers do not mean

The design doc estimated NDCG@10 between 0.75 and 0.85 before any data existed. The measured
0.904 **exceeds that band**. The target was left unchanged and the result recorded beside it,
because moving a target after seeing the number removes the ability to tell whether a project
succeeded.

The honest reading is not that the model is excellent. It is that **the synthetic task is
easier than real hiring**. An MRR of exactly 1.000 — the top-ranked candidate genuinely
relevant in all fifty postings, without a single miss — is not a plausible result on real
applicants.

A circularity check runs automatically: NDCG@10 above 0.95 is treated as a defect indicating
label leakage rather than as success. 0.904 sits below it.

## 4. Training data

Entirely synthetic. **No real person appears in this model's training data.**

| | |
|---|---|
| Candidates | 5,000 |
| Job postings | 200 (each one ranking query group) |
| Labelled pairs | 12,040 |
| Grades | 3: 15.8% · 2: 20.5% · 1: 27.3% · 0: 36.4% |
| Seed | 42, generator version 1.0.0 |

Real CVs were not used: they contain personal data, no hiring labels were available, and any
historical labels would have carried whatever bias existed in past decisions while presenting
the result as objective.

Full detail, including the anti-circularity design, is in [data-card.md](data-card.md).

## 5. Features

Twelve features, all describing a **(candidate, job) pair** rather than a candidate alone.

Global SHAP importance across the validation set:

| Feature | Share |
|---|---|
| `shift_match` | 26.8% |
| `licence_match` | 15.8% |
| `cert_overlap_ratio` | 15.7% |
| `exp_ratio` | 13.3% |
| `cert_overlap_count` | 7.3% |
| `exp_gap` | 7.2% |
| `site_type_match` | 5.6% |
| `role_count` | 4.5% |
| `missing_critical_cert` | 2.5% |
| `driving_required_match` | 0.9% |
| `extra_cert_count` | 0.4% |
| `recency_months` | 0.0% |

### Never used

Gender, age, date of birth, graduation year, name, nationality, ethnicity, marital status,
photograph, postcode and religion have no field on the type the pipeline is built on. They are
not filtered out downstream; they are absent from the start. A static test fails the build if
any module on the scoring path so much as imports the module where demographics live.

## 6. Limitations and failure modes

**Trained on synthetic data.** This is the largest limitation and it qualifies every other
number here. Distributions were chosen to be plausible, not measured against SAJCO's real
applicants. Performance on real applications is unknown.

**Scores are not probabilities.** A LambdaRank output is uncalibrated and comparable only
within one posting. Reading 2.97 as "97% suitable" is the most likely way this model gets
misused, which is why the API field is named `relative_ranking_score` and every response
repeats the constraint.

**The most influential feature is also the largest fairness exposure.** `shift_match` accounts
for 26.8% of the model's effect, and availability correlates with caring responsibilities and
therefore with gender. Nothing is wrong with the feature — night cover genuinely requires
people who can work nights — but it is the route through which proxy discrimination would
arrive, and removing it would cost real ranking quality. This trade-off is documented rather
than discovered later.

**A feature that only carries risk.** `recency_months` contributes 0.0% while proxying for
career breaks, which correlate with parental leave. It is a free removal in v0.2.0.

**A stated shortcoming is penalised harder than an unstated one, so the model mildly rewards a
vague CV.** Missing values reach LightGBM as NaN and are routed down a default branch, which is
gentler than the branch a known-bad value takes. Measured on the sample set: `site_type_match`
contributes **-0.0850** when the site type is known not to match, against **-0.0192** when the CV
never said; `exp_gap` contributes **-0.2716** at a year below the minimum, against **-0.0609**
when experience is unstated. A candidate who documents a genuine mismatch can therefore rank
below one who documents almost nothing.

Mechanically this is ordinary gradient-boosting behaviour and nothing is broken. As a property
of a hiring aid it points an incentive the wrong way, and CV completeness is not evenly
distributed across groups — fluency, education and access to CV-writing help all bear on it, and
each correlates with characteristics the audit watches. It was found by building the interface
rather than by any test: the ordering looked wrong, and the contribution table said why in one
glance. Not yet reflected in the fairness metrics, which measure outcomes by group rather than by
how much a CV happened to state. Candidate for explicit missing-value handling in v0.2.0.

**Extraction limits what the model can see.** A certification the parser missed cannot
influence a score or appear in an explanation. Parse warnings travel through to every API
response so a reviewer can tell when the system was unsure. Accuracy on generated CVs is 100%
for every stated fact, but real CVs contain formatting the generator does not produce.

**Cold start.** Postings unlike anything in training — unusual certification combinations,
site types not represented — will be ranked with less reliability, and nothing in the output
signals that.

**No drift detection.** Feature distributions are recorded for later comparison, but the
comparison and its review process do not exist yet. A model that is accurate and fair today
can be neither in a year as the applicant population changes.

## 7. Fairness

Audited on gender, age band and nationality at k = 10, against the four-fifths rule.

| Attribute | Adverse impact | Exposure ratio | Result |
|---|---|---|---|
| gender | 0.965 | 0.983 | **PASS** |
| age_band | 0.627 | 0.908 | **PASS** — statistically inconclusive |
| nationality | 0.956 | 0.973 | **PASS** |

The `age_band` figure looks alarming and is not. Age is assigned at random in this dataset and
cannot influence a score; a 319-member group landed low by chance. After correcting for the
fact that the ratio compares the most extreme pair out of five groups, it is not
distinguishable from noise. It is reported rather than hidden.

### What the audit failed to catch

**Bias at realistic strength passed undetected.** A gender–night-availability correlation of
0.40 — roughly what a real caring-responsibilities gap looks like — produced an adverse impact
ratio of 0.875, comfortably above the 0.80 threshold. The audit caught the same bias only at
roughly double that strength.

The four-fifths rule detects gross disparity. It does not detect proxy bias of the strength
that realistically occurs. **A model that passes it has not been shown to be fair, only shown
not to be obviously unfair.**

Full analysis, including both statistical errors made while building the audit, is in
[fairness-report.md](fairness-report.md).

## 8. Explainability

Every ranked candidate carries per-feature SHAP contributions and plain-language reasons.
There is no flag to turn this off.

Contributions are exact and additive: base value plus contributions reconstructs the raw score
to within 1e-6, asserted in tests against the released artifact.

The reasons deliberately avoid probability language and never quote raw contribution figures,
because showing "+0.94" to a non-technical reader invites reading it as a percentage. Details
in [explainability.md](explainability.md).

## 9. Provenance and reproducibility

```
model.txt            LightGBM native text format — not pickle
feature_names.json   canonical feature order
metadata.json        train date, seed, git SHA, library versions, hyperparameters
metrics.json         performance including the baseline comparison
fairness.json        full audit output
checksums.json       SHA-256 of every file above
```

Checksums are verified on load and the service **refuses to start** on mismatch, because an
artifact that does not match its recorded hash is not the one that was evaluated and audited.

**The checksums were platform-dependent when v0.1.0 was first released, and the artifact did
not load on Linux.** The files were written on Windows, where Python's `write_text` and
LightGBM's serialiser both emit CRLF. Git — with `core.autocrlf` and no `.gitattributes` —
normalised those to LF on the way into the repository, so the committed bytes hashed
differently from the recorded checksums. Verification therefore failed on every non-Windows
checkout, including CI and the container, and because startup re-raises on artifact failure the
service refused to serve at all. It passed only on the machine that produced the bytes.

Found on 2026-08-19 by a CI run, and worth stating plainly: a checksum taken over
platform-dependent bytes verifies the machine that wrote the file, not the artifact.

Corrected rather than reissued. The two byte variants were first proven to be the same model —
78 trees, 12 features, identical feature names, and bit-identical predictions across 2,000
random inputs — so the recorded hashes were re-taken against the canonical LF form without
touching the model that was evaluated and audited. Artifacts are now written with LF on every
platform, `.gitattributes` marks `backend/models/**` as `-text` so git cannot rewrite them
again, and two tests assert that no artifact file contains CRLF. No metric in this document
changed.

The artifact was written from a clean working tree, so its recorded git SHA genuinely describes
the code that produced it. Training refuses to write an artifact from uncommitted code.

Rollback is a change to `MODEL_VERSION`, not a rebuild.

```bash
guardmatch generate-data --seed 42
guardmatch train --version v0.1.0
guardmatch audit --version v0.1.0
```

**Hyperparameters:** `num_leaves=15`, `learning_rate=0.05`, `min_data_in_leaf=50`,
`lambdarank_truncation_level=10`, 78 boosting rounds selected by early stopping from a
12-point grid.

**Environment:** Python 3.12.13, LightGBM 4.7.0, SHAP 0.52.0, spaCy 3.8.15, NumPy 2.5.2,
scikit-learn 1.9.0.

## 10. Conditions of use

1. **A human reviews every shortlist.** The model orders candidates; it does not select them.
2. **No automated rejection.** Nothing in the output supports a reject threshold, and section 6
   explains why one should not be inferred.
3. **Do not compare scores across postings.**
4. **Re-audit before production.** Every fairness figure here was measured on synthetic
   demographics. Real data must be re-audited, and the results reviewed by someone with
   employment-law expertise for the operating jurisdiction.
5. **Treat 0.80 as a floor, not a target.** An adverse impact ratio of 0.85 warrants
   investigation, not celebration.
6. **Monitor over time.** The drift hook exists; the review process does not.
7. **The reviewer must be able to see the reasoning.** Condition 1 is only meaningful if the
   human doing the reviewing can read why a candidate placed where they did. The API returns the
   explanation on every response and the [Rank workspace](frontend.md) renders it — reasons
   first, then all twelve contributions with the additivity check. An integration that consumes
   the ranking and discards the explanation satisfies condition 1 in form and not in substance:
   it produces a human who is approving an order they cannot interrogate.

## 11. Version history

| Version | Date | Notes |
|---|---|---|
| v0.1.0 | 2026-08-17 | First release. NDCG@10 0.904 vs baseline 0.804. Fairness audit passes on all three attributes. |
| v0.1.0 | 2026-08-19 | Checksums re-recorded against the canonical LF form; see section 9. The model is unchanged and was proven bit-identical before the record was corrected. Not a new version, because nothing about the model is new. |

### Proposed for v0.2.0

- Remove `recency_months` — 0.0% contribution, non-zero proxy risk
- Investigate reducing dependence on `shift_match`, and measure the ranking cost
- Real-data validation before any production consideration
- Exposure-based post-processing, if a re-audit on real data shows a gap

---

**Contact:** raise an issue at
<https://github.com/Kainatfatima0311/guardmatch-ai>
