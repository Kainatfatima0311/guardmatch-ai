# Explainability — GuardMatch AI

**Model version:** v0.1.0
**Method:** SHAP `TreeExplainer` (exact TreeSHAP over the LightGBM ensemble)
**Date:** 2026-08-17

---

## 1. Why this exists

A ranking without a reason is unusable in hiring.

A reviewer handed "candidate 23, score 1.29" has no basis to accept or question it. A
candidate who asks why they were not shortlisted deserves an answer that is not "the model
said so". And an auditor checking for discrimination needs to see what the system actually
weighed, not what its authors believe it weighed.

Every candidate returned by this service carries an explanation. There is no configuration
flag to turn it off.

## 2. The critical caveat

**A LambdaRank score is not a probability, and neither are its SHAP contributions.**

The model optimises the *ordering* of candidates within one job posting. Its output is an
uncalibrated real number on an internal scale, meaningful only by comparison to the other
candidates for that same posting.

| Valid reading | Invalid reading |
|---|---|
| "Ranks above candidate B for this posting" | "87% likely to be hired" |
| "The licence pushed them up the ordering" | "The licence adds 94% to their chances" |
| "Third strongest fit for this role" | "Scored 1.29 out of 10" |

Scores are **not comparable across postings**. A 1.29 for a construction night shift and a
1.29 for a retail day shift say nothing about each other.

Three mechanisms defend against the misreading rather than relying on this document being
read:

- The API field is named `relative_ranking_score`, and every response repeats
  `score_type` alongside it.
- Every `/rank` response carries a `disclaimer` field stating the constraint, so it travels
  with the data.
- `backend/tests/test_explain.py` asserts that no generated sentence contains probability language,
  and that raw contribution figures never appear in reviewer-facing text.

## 3. Method

SHAP `TreeExplainer` computes exact Shapley values for tree ensembles — exact rather than
sampled, which matters because an approximate explanation in a hiring decision is a liability
rather than an asset.

The explanation is **additive**:

```
base_value  +  Σ contributions  =  raw ranking score
```

For v0.1.0 the base value is **−2.0226**. This is the model's expected output before any
feature about a specific candidate is considered.

Additivity is asserted in tests to a tolerance of 1e-6, against both a test fixture and the
released artifact. An explanation that does not sum to the score it explains is not an
explanation; it is a plausible story printed next to a number.

The explainer is constructed once per process and evaluates a whole batch in a single call.
TreeSHAP is vectorised, so a per-candidate loop would add latency for no benefit.

## 4. What a candidate receives

Two layers, always both.

**Numeric contributions** — the auditable record. Exact, reproducible, and what an
investigator would want if a decision were ever challenged.

**Plain-language reasons** — what the person doing the shortlisting actually reads.

Publishing only the numbers means nobody reads them. Publishing only the sentences means
nobody can check them.

### Worked example

Posting `j_0000` — construction site, night shift, minimum 4 years, requires security
licence, fire safety and health & safety.

**Ranked 1 of 40 — candidate `c_00023`, score +1.2864**

```
base value          -2.0226
+ contributions     +3.3090
────────────────────────────
= raw score         +1.2864
```

> - Available for the shift pattern this role needs — counted strongly in favour
> - Has prior experience at this type of site — counted moderately in favour
> - Holds the required security licence — counted moderately in favour
> - 2 previous security roles — counted moderately in favour
> - Holds 2 of the required certifications — counted slightly in favour

**Ranked 40 of 40 — candidate `c_00006`, score −4.1212**

> - Does not hold the required security licence — counted strongly against
> - Available for the shift pattern this role needs — counted moderately in favour
> - Experience is 0.3 times the stated minimum — counted moderately against
> - Holds 0% of the certifications this role requires — counted moderately against
> - 2.7 years below the minimum experience requirement — counted slightly against

Note the second entry for the bottom-ranked candidate. Shift availability counted *in their
favour* even though they finished last. The explanation reports what the model did rather
than assembling a consistent-sounding case for the outcome, which is the difference between
an explanation and a justification.

## 5. Wording rules

**Direction comes from the contribution, not from the fact.** A positive-sounding fact can
carry a negative contribution. Rather than suppressing that, the sentence reports it — a
surprising combination is precisely what a reviewer should question. A test asserts this
behaviour explicitly.

**Magnitude is described, not quoted.** Reasons say "strongly", "moderately" or "slightly"
rather than "+0.94". Showing a raw contribution to a non-technical reader invites reading it
as a percentage. The exact figure remains in the contributions array.

**Unknowns are named.** "Shift availability was not stated in the CV" is useful. Omitting the
field is not, because a reviewer cannot then distinguish a candidate who is unavailable from
one who simply did not mention it. This mirrors the parser's `None`-not-zero rule.

## 6. Global importance

Mean absolute SHAP contribution across the 3,041-row validation set:

| Feature | Mean abs. contribution | Share |
|---|---|---|
| **`shift_match`** | 0.8957 | **26.8%** |
| `licence_match` | 0.5276 | 15.8% |
| `cert_overlap_ratio` | 0.5263 | 15.7% |
| `exp_ratio` | 0.4438 | 13.3% |
| `cert_overlap_count` | 0.2448 | 7.3% |
| `exp_gap` | 0.2407 | 7.2% |
| `site_type_match` | 0.1873 | 5.6% |
| `role_count` | 0.1512 | 4.5% |
| `missing_critical_cert` | 0.0840 | 2.5% |
| `driving_required_match` | 0.0296 | 0.9% |
| `extra_cert_count` | 0.0118 | 0.4% |
| `recency_months` | 0.0016 | 0.0% |

Two observations, both consequential.

**`shift_match` dominates at 26.8%** — more than the licence and certification coverage
individually. It is also the feature the proxy register flags as most likely to carry
demographic information, because availability correlates with caring responsibilities and
therefore with gender. The project's own bias injection exploits exactly this route.

Nothing has gone wrong: shift availability is job-relevant and legitimately predictive of
fit. But it means the fairness audit is consequential rather than ceremonial, and that
removing the feature if it fails would cost real ranking quality. That trade-off is now
documented in advance rather than discovered under pressure.

**`recency_months` contributes essentially nothing (0.0%).** It is a registered proxy for
career breaks, which correlate with parental leave. A feature that carries demographic risk
while adding no predictive value is a straightforward candidate for removal in v0.2.0 —
there is nothing to trade off.

Global importance is what surfaces both of these. Neither is visible from any individual
explanation.

### Served by the API, and why the figure moves slightly

`GET /feature-importance` reports this same measure from the running service, and the product
draws it at `/model` with the four monitored proxies in amber — so the fact that the largest
input is also the largest fairness exposure is visible in one glance rather than assembled from two
documents.

**It returns 26.3% for `shift_match` where the table above says 26.8%, and the difference is the
sample, not the model.** The table is computed over the full 3,041-row validation set during the
audit. The endpoint computes over a fixed 200-row sample against one fixed reference posting,
because it answers on request and a few hundred SHAP evaluations is the most that can be justified
inside a request. Both are stable — the endpoint's sample and posting are fixed, so a given model
version always returns the same figures — and neither is an estimate of the other.

**The ordering agrees at the ends and swaps in the middle**, and that is worth more than a
reassurance would be. `shift_match` leads in both. `recency_months` is last in both, at
effectively zero. But positions two and three trade places: over the validation set
`licence_match` and `cert_overlap_ratio` are effectively tied (15.8% against 15.7%), whereas
against the endpoint's single fixed posting `cert_overlap_ratio` is clearly ahead (20.6% against
13.5%).

The reason is the fixed posting rather than anything about the model. How far a feature can move
outputs depends on how much it varies across the candidates being compared, and that depends on
what the posting asks for. A posting requiring several certifications gives certification overlap
room to spread across applicants; `licence_match` is close to constant when nearly everyone holds
the licence. Across fifty postings those effects average out, and against one they do not.

So the two figures answer slightly different questions. **The validation-set table above is the one
to cite** — it is computed over everything, and it is what the audit used. The endpoint's value
is that it is answerable from the running service for the model actually loaded, which no document
can be.

Mean absolute SHAP contribution is deliberately not LightGBM's split gain. Gain counts how often
the trees used a feature; this counts how far it actually moved outputs. And it is absolute
because a feature pushing some candidates up as hard as it pushes others down is influential —
averaging signed values would hide it completely.

## 7. How a reviewer actually sees this

Everything above describes what the service produces. What a reviewer reads is the
[Rank workspace](frontend.md), and four of its rules exist because of properties of this
explanation layer rather than for visual reasons.

**The words come before the numbers.** The generated `reasons` are shown first, because they are
the layer a non-technical reviewer reads. The twelve-row contribution table sits underneath as
the audit trail, behind a disclosure.

**All twelve contributions are shown, including the ones that did nothing.** The response never
truncates them, and neither does the interface. Dropping the near-zero rows would turn "this did
not matter" into "this was not considered" — different claims that a reader cannot distinguish
from an absence.

**The additivity guarantee is displayed rather than asserted.** Because base value plus every
contribution reconstructs the score to 1e-6, the browser recomputes the sum and shows whether it
holds, alongside the reported score. Measured across the sample set the delta runs from 0.0e+00
to 1.8e-15, which is JSON rounding rather than disagreement. An explanation that does not add up
to the score it explains is a story printed beside a number, and the interface is able to say
which one it is holding.

**Direction never depends on colour.** Each row carries a sign and an arrow as well as its
emerald or rose fill, so the information survives greyscale printing and colour vision
deficiency. The reasons already state direction in words, which is the primary channel.

Two things the interface deliberately refuses to render. The score is never shown as a
percentage, a ring, or a progress bar — every one of those implies a proportion, and a reviewer
reads a filled ring as "83% suitable" regardless of the caption. And a `null` contribution value
renders as **"not stated"**, never as `0`, because the parser distinguishes a fact the CV omitted
from one it stated as zero and the presentation must not collapse them.

The four features registered as monitored proxies are labelled as such in the table, with their
specific exposure. `shift_match` being both the largest input and the largest fairness exposure
is a fact that previously lived only in section 6 and the fairness report; it now appears at the
moment it is acting on a candidate.

## 8. Limitations

**Explanations describe the model, not the world.** They say what drove a score. They do not
establish that the model's reasoning is correct, or that the features it weighs are the ones
that should determine a hire.

**Additivity is on the raw score.** Contributions cannot be summed into a percentage, a
probability, or a comparison across postings.

**Feature interactions are attributed, not displayed.** SHAP distributes the effect of an
interaction across the features involved. The label function contains a deliberate
licence-and-experience interaction that pays a bonus neither condition earns alone; SHAP
splits that credit between the two rather than reporting it as a joint effect.

**Explanations inherit the parser's limits.** A certification the parser missed cannot appear
in any explanation. This is why parse warnings travel through to the API response.

**Measured on synthetic data.** Importance rankings reflect this dataset. On real applicants
the ordering would differ, and the audit would need re-running.

## 9. Where this lives in the code

| Concern | Module |
|---|---|
| SHAP computation, additivity | `backend/src/guardmatch/explain/shap_explainer.py` |
| Sentence generation, wording rules | `backend/src/guardmatch/explain/reasons.py` |
| Response contract | `backend/src/guardmatch/schemas/scoring.py` |
| Tests, including the wording assertions | `backend/tests/test_explain.py` |
