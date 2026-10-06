# Results

Every number in this file comes from a real run. Nothing is estimated or invented.
Each entry records the date, the script that produced it, and the split. Evaluation
uses real, non-synthetic test data only; synthetic-data scores, when they exist, are
labelled **diagnostic only**.

Model results are in the **Baseline models (Phase 3)** section below.

> **Definition change (Phase 3.5).** All Phase 1-3 numbers below were produced under the *old*
> label definition, in which every UCI/India "spam" row counted as `scam`. The project now
> separates fraud from promotions (see `docs/label_rubric.md` and the Phase 3.5 section at the
> end). In UCI, roughly 30-34% of "spam" is fraud; in the India SMS set it is about 2%. Phase 3
> scores therefore measure "spam vs not spam" on those sources, not "scam vs not scam", and are
> not comparable with Phase 3.5 numbers.

---

## Data (Phases 1 and 2)

Run date: 2026-09-26. Reproduce with:

```
python -m src.preprocessing.generate_synthetic   # resumable; needs GROQ_API_KEY / GEMINI_API_KEY
python -m src.preprocessing.combine              # Phase 1 -> data/processed/combined.parquet
python -m src.preprocessing.preprocess           # Phase 2 -> train/val/test.parquet (seed 42)
```

### Sources merged (Phase 1, `combine.py`)

| Source | Loaded | Over-long dropped | Exact duplicates dropped | Kept |
|---|---:|---:|---:|---:|
| UCI SMS Spam Collection | 5,574 | 0 | 415 | 5,159 |
| HF `ealvaradob/phishing-dataset` (texts) | 20,136 | 381 | 2,029 | 17,726 |
| Kaggle `subhajournal/phishingemails` | 18,631 | 397 | 17,699 | 2 |
| Synthetic (LLM-generated) | 1,654 | 0 | 0 | 1,654 |
| **Combined** | | | | **24,541** |

- 533 rows were dropped because the same text carried both labels.
- Kaggle contributes only 2 rows because the HF dataset already contains those emails
  (18,099 of its 18,634 non-empty rows also appear there).
- "Over-long" means more than 10,000 characters (one HF row is about 17 million).

### Synthetic data generation

| Item | Value |
|---|---|
| Batches planned / completed | 195 / 195 (10 messages each) |
| Messages generated | 1,950 |
| Kept after quality filters | **1,654** (84.8%) |
| Dropped: placeholder-looking numbers (123456, 9988776655, ...) | 141 |
| Dropped: wrong script / style (e.g. "Tamil-English" that is plain English) | 155 |
| Dropped: length / duplicates | 0 / 0 |
| Kept by generator | gemini-3.5-flash-lite 882 (53.3%), groq gpt-oss-120b 753 (45.5%), gemini-3.7-flash 19 (1.1%) |
| Scam / safe (kept) | 769 / 885 |
| Scam types | 7 types, 107 to 115 rows each |
| Languages (kept) | hinglish 676, en 274, hi 174, bn_en 140, te_en 132, mr_en 131, ta_en 127 |

Scam share by generator (kept rows): Gemini 49%, Groq 44%. The gap comes from the filters
removing more Groq scam rows (they contained more placeholder-looking numbers). It is a
small provider/label correlation, noted as a limitation.

`gemini-3.8-flash` (20 requests/day free tier) supplied none of the final rows: its quota
was used up during pilot runs, and `gemini-3.7-flash` likewise supplied only 2 batches.
In effect the Gemini half of the data comes from one model.

### Preprocessing and deduplication (Phase 2, `preprocess.py`)

| Stage | Rows | Removed |
|---|---:|---:|
| Combined input | 24,541 | |
| After cleaning (whitespace / Unicode) | 24,541 | 0 |
| After exact-duplicate removal on masked text | 24,413 | **128** |
| After near-duplicate removal (TF-IDF cosine >= 0.90) | 22,826 | **1,587** |
| Removed for overlap with real_indian_test | 22,826 | 0 (set not built yet) |

- **Duplicates removed in Phase 2: 1,715** (128 exact + 1,587 near-duplicates), all of them
  real rows. None of the 1,587 near-duplicates was synthetic. There were 863 clusters; the
  largest had 137 rows (automated Enron "hourahead" notices differing only in dates).
- Adding Phase 1: **21,858 duplicate rows removed in total** (20,143 exact duplicates across
  sources in Phase 1, plus 1,715 in Phase 2), and 533 label-conflict rows.
- No cluster mixed labels at the 0.90 threshold.
- Threshold sensitivity (rows removed as near-duplicates): 0.80 -> 2,676, **0.90 -> 1,587**,
  0.95 -> 994.
- After the split, 3 validation rows and 6 test rows that were still borderline-similar to
  another split were trimmed. The final audit measures **0** near-duplicate rows across every
  split boundary (val vs train, test vs train, test vs val); the highest cosine similarity
  seen was 0.900 (val vs train) and 0.8998 (test vs train).

### Splits (stratified 70/15/15 by label and source; seed 42)

| Split | Rows | Safe | Scam | Scam rate | Synthetic rows |
|---|---:|---:|---:|---:|---:|
| train | 15,978 | 10,920 | 5,058 | 31.7% | 1,362 |
| val | 3,421 | 2,339 | 1,082 | 31.6% | 292 |
| test | 3,418 | 2,386 | 1,032 | 30.2% | **0** |

Test composition: 2,604 rows from the HF phishing texts (mostly old emails) and 814 from the UCI
SMS collection; **3,416 of 3,418 are English** (the other two are tagged `other` and
`hinglish_guess`). The test set therefore says almost nothing about Hinglish or regional
languages. See the hand-collected `real_indian_test` set below.

### Language coverage in real data

Only 0.01% of real training rows are tagged Hindi/Hinglish. The tagger is a heuristic
(Unicode script plus a romanized-Hindi word list); real Hinglish is under-detected.

### Shortcut baselines (training-split fit, validation ROC AUC; no message words used)

| Predictor | ROC AUC |
|---|---:|
| Source only | 0.619 |
| Message length only | 0.557 |
| Source + length | 0.650 |

0.5 is chance. Majority-vote accuracy (0.684) cannot expose the confound, because every
source is majority-safe. A real classifier must clearly beat these baselines to count as
having learned scam content. Scam rate by source in train: UCI SMS 11%, HF texts 36%,
synthetic 46%.

### Masking

Share of training rows containing each masked token (final training split):

| Token | Real rows | Synthetic rows |
|---|---:|---:|
| `<URL>` | 18.8% | 31.8% |
| `<PHONE>` | 3.9% | 16.7% |
| `<OTP>` | 0.03% | 10.3% |

Synthetic text is much richer in phone numbers and OTPs than the real corpora, which is
expected (the real data is mostly old email and UK SMS spam) but means these tokens partly
mark the data source. The 0.03% `<OTP>` rate in real data reflects how few OTP messages
the public corpora contain.

### Hand-collected real Indian test set

Not built yet. Template: `docs/real_indian_test_template.csv`; guidelines:
`docs/labeling_guidelines.md`; build command:
`python -m src.preprocessing.real_indian_test data/real_indian/messages.csv`. Evaluation-only.

## Baseline models (Phase 3)

Run date: 2026-09-26. Reproduce with `python -m src.training.baseline --update-results results.md`
(roughly 10 minutes on CPU). All runs, parameters and metrics are in the local MLflow store:
`mlflow ui --backend-store-uri sqlite:///mlflow.db` (64 runs: 54 tuning trials, 2 final
models, 2 mitigation runs, 6 leave-one-source-out runs).

**Protocol.** Trained on the train split; tuned on the 3,129 *real* validation rows only
(grid: features word / char / word+char, C, class weight, plus an F1-optimal decision
threshold); scored once on the 3,418-row real test set. Synthetic validation rows are scored
separately and labelled diagnostic only. Tests enforce that the tuning code never receives
test data, that flipping test or synthetic-validation labels cannot change the selected
configuration, and that `text_raw` is never read.

### What the numbers say

1. **In-distribution, both baselines are very strong and equal.** Test F1 0.970 (precision
   0.971, recall 0.969, ROC-AUC 0.998) for both models, with 30 false positives and 32 false
   negatives out of 3,418. The Logistic Regression / SVM difference is noise. Per source:
   HF texts F1 0.973, UCI SMS F1 0.937 (false-positive rate 0.7%).
2. **Do not read 0.97 as real-world accuracy.** Three independent checks say the score mostly
   reflects the corpora, not scam detection:
   - **Leave-one-source-out.** Trained without the HF texts, ROC-AUC on them falls from 0.998
     to **0.637** (F1 about 0.49, near chance). Trained without UCI SMS, ranking still
     transfers (ROC-AUC 0.949) but at the in-distribution threshold precision drops to 0.30
     and F1 to 0.45: the scores shift between sources, so a threshold does not carry over.
     Without the synthetic source, ROC-AUC on synthetic validation rows is 0.730 (diagnostic
     only).
   - **Highest-weight features are corpus fingerprints.** Safe: `enron`, `enr`, the email
     quote marker `>`. Scam: `!`, `free`, `click here`, `2005`, `£` (UK SMS spam).
   - **The test set is narrow.** 3,416 of 3,418 rows are English and 76% come from the HF
     texts (mostly old email). The per-language and per-scam-type tables on the test set are
     degenerate: real rows only have scam types `unknown` / `generic_spam`.
3. **The mitigation experiment did not help.** Source x class balanced sample weights change
   test F1 by -0.0015 (Logistic Regression) and -0.0010 (SVM), and leave-one-source-out
   ROC-AUC moves by only +0.001 to +0.004 for HF and synthetic and by -0.003 for UCI. Re-weighting
   removes the *prior* shift between sources, but the confound here is mostly vocabulary and
   style, which weights cannot remove.
4. **Threshold tuning gave nothing on test.** Test F1 at the tuned threshold (0.9699 both)
   versus the default threshold 0 (0.9707 Logistic Regression, 0.9712 SVM): within noise.
5. **Synthetic validation (diagnostic only).** F1 0.936 (Logistic Regression) / 0.932 (SVM)
   on 292 rows; by language from 0.857 (`te_en`) to 1.000 (`bn_en`, Logistic Regression),
   Hinglish 0.929. The false-positive rate on *safe* synthetic messages is 8.3% (13 of 156,
   SVM), versus 1.3% on real safe messages. Reading the false positives shows this is largely
   **label noise in the synthetic "safe" class**, not only model error: of the 10
   highest-scoring ones, about half read like real scams that the generator labelled safe
   (urgency + link, "pay now or service will be cut", "confirm your bank account details",
   "KYC ... account band ho jayega"), and most of the rest are legitimate OTP or UPI
   notifications. Fake-bank-OTP has the lowest scam recall (0.857 to 0.905). Inspected on
   the SVM's validation false positives only; a full audit of the synthetic safe rows has
   not been done.

### Consequences for the next phases

- Treat the in-distribution numbers as an upper bound. Every later model must also report
  leave-one-source-out results and be compared against the shortcut baselines (source only
  0.619, length only 0.557 validation ROC-AUC).
- The Hinglish claim rests on synthetic data only until the hand-collected real Indian test
  set exists; that set is the honest measure and the highest-value next data task.
- Audit the synthetic "safe" hard negatives for label noise (manual review or an LLM judge)
  before Phase 4 trains on them: mislabeled rows teach the model the wrong boundary.
- Ideas ranked by expected value: (a) build the real Indian set and evaluate every model on
  it; (b) since the product targets SMS/WhatsApp, evaluate an SMS-only training mix and treat
  the email corpora as auxiliary; (c) strip corpus artifacts (quote markers, years, currency
  symbols, email headers) and re-check leave-one-source-out; (d) in Phase 4, check whether a
  multilingual transformer transfers across sources better than TF-IDF.

### Notes on the process

- The first full run used a Logistic Regression grid topping out at C=100, and its optimum
  sat on that edge (validation F1 still rising, 0.9777). The grid was extended to C=1000 and
  the entire protocol re-run from a clean MLflow store. The optimum moved to C=1000 with a
  validation F1 gain of only +0.0005, i.e. a plateau, so the grid was not extended further.
  That first run's test F1 was 0.9695 (Logistic Regression) and 0.9699 (SVM); the tables below
  are from the final run. The extension was motivated by the validation trend, but the first
  run's test numbers had already been seen, so treat the final test scores as reported once
  per model on the final configuration, not as a blind estimate.
- The threshold is tuned on the same validation rows used for selection, so validation F1 is
  slightly optimistic; test F1 is the fair number.
- Only the first 2,000 characters of each message are used (speed). The median training
  message is 435 characters, but some emails are far longer and are truncated.

<!-- baseline:start -->
_Generated by `python -m src.training.baseline` (seed 42, first 2,000 characters of the masked text). Selection used 3,129 real validation rows; the 3,418-row real test set was scored once per model._

#### Comparison on the real test set (scam = positive class)

| Model | Selected configuration | Val F1 (real) | Test precision | Test recall | Test F1 | Test ROC-AUC | Test PR-AUC | FP / FN | Test F1 @ default thr |
|---|---|---|---|---|---|---|---|---|---|
| TF-IDF + Logistic Regression | word+char, C=1000, cw=None | 0.9782 | 0.9709 | 0.9690 | 0.9699 | 0.9982 | 0.9960 | 30 / 32 | 0.9707 |
| TF-IDF + Linear SVM | word+char, C=1, cw=None | 0.9788 | 0.9709 | 0.9690 | 0.9699 | 0.9983 | 0.9962 | 30 / 32 | 0.9712 |
| TF-IDF + Logistic Regression + source-balanced weights (experiment) | word+char, C=1000, sample weights | 0.9777 | 0.9708 | 0.9661 | 0.9684 | 0.9980 | 0.9955 | 30 / 35 | 0.9683 |
| TF-IDF + Linear SVM + source-balanced weights (experiment) | word+char, C=1, sample weights | 0.9772 | 0.9708 | 0.9671 | 0.9689 | 0.9980 | 0.9955 | 30 / 34 | 0.9688 |

#### Confusion matrices (test set)

| Model | TN (safe->safe) | FP (safe->scam) | FN (scam->safe) | TP (scam->scam) | Threshold |
|---|---|---|---|---|---|
| TF-IDF + Logistic Regression | 2,356 | 30 | 32 | 1,000 | -0.777 |
| TF-IDF + Linear SVM | 2,356 | 30 | 32 | 1,000 | -0.091 |

#### Test set by source

| Model | Source | Rows | Scam rows | Precision | Recall | F1 | False-positive rate | ROC-AUC |
|---|---|---|---|---|---|---|---|---|
| TF-IDF + Logistic Regression | hf_phishing_texts | 2,604 | 944 | 0.9735 | 0.9725 | 0.9730 | 0.0151 | 0.9983 |
| TF-IDF + Logistic Regression | uci_sms_spam | 814 | 88 | 0.9425 | 0.9318 | 0.9371 | 0.0069 | 0.9950 |
| TF-IDF + Linear SVM | hf_phishing_texts | 2,604 | 944 | 0.9735 | 0.9725 | 0.9730 | 0.0151 | 0.9984 |
| TF-IDF + Linear SVM | uci_sms_spam | 814 | 88 | 0.9425 | 0.9318 | 0.9371 | 0.0069 | 0.9953 |

#### Test set by language (real data; nearly degenerate, see note)

| Model | Language | Rows | Scam rows | Precision | Recall | F1 | FPR |
|---|---|---|---|---|---|---|---|
| TF-IDF + Logistic Regression | en | 3,416 | 1,031 | 0.9708 | 0.9690 | 0.9699 | 0.0126 |
| TF-IDF + Logistic Regression | hinglish_guess | 1 | 0 | n/a | n/a | n/a | 0.0000 |
| TF-IDF + Logistic Regression | other | 1 | 1 | 1.0000 | 1.0000 | 1.0000 | n/a |
| TF-IDF + Linear SVM | en | 3,416 | 1,031 | 0.9708 | 0.9690 | 0.9699 | 0.0126 |
| TF-IDF + Linear SVM | hinglish_guess | 1 | 0 | n/a | n/a | n/a | 0.0000 |
| TF-IDF + Linear SVM | other | 1 | 1 | 1.0000 | 1.0000 | 1.0000 | n/a |

#### Test set by scam type (real data; nearly degenerate, see note)

| Model | Scam type | Rows | Scam rows | Precision | Recall | F1 | FPR |
|---|---|---|---|---|---|---|---|
| TF-IDF + Logistic Regression | generic_spam | 88 | 88 | 1.0000 | 0.9318 | 0.9647 | n/a |
| TF-IDF + Logistic Regression | none | 2,386 | 0 | n/a | n/a | n/a | 0.0126 |
| TF-IDF + Logistic Regression | unknown | 944 | 944 | 1.0000 | 0.9725 | 0.9860 | n/a |
| TF-IDF + Linear SVM | generic_spam | 88 | 88 | 1.0000 | 0.9318 | 0.9647 | n/a |
| TF-IDF + Linear SVM | none | 2,386 | 0 | n/a | n/a | n/a | 0.0126 |
| TF-IDF + Linear SVM | unknown | 944 | 944 | 1.0000 | 0.9725 | 0.9860 | n/a |

#### Diagnostic only: synthetic validation rows (never a real-data result)

By language:

| Model | Language | Rows | Scam rows | Precision | Recall | F1 | FPR |
|---|---|---|---|---|---|---|---|
| TF-IDF + Logistic Regression | bn_en | 17 | 9 | 1.0000 | 1.0000 | 1.0000 | 0.0000 |
| TF-IDF + Logistic Regression | en | 44 | 22 | 1.0000 | 0.9545 | 0.9767 | 0.0000 |
| TF-IDF + Logistic Regression | hi | 37 | 20 | 0.8696 | 1.0000 | 0.9302 | 0.1765 |
| TF-IDF + Logistic Regression | hinglish | 120 | 55 | 0.9123 | 0.9455 | 0.9286 | 0.0769 |
| TF-IDF + Logistic Regression | mr_en | 22 | 7 | 0.8750 | 1.0000 | 0.9333 | 0.0667 |
| TF-IDF + Logistic Regression | ta_en | 27 | 14 | 0.9286 | 0.9286 | 0.9286 | 0.0769 |
| TF-IDF + Logistic Regression | te_en | 25 | 9 | 0.7500 | 1.0000 | 0.8571 | 0.1875 |
| TF-IDF + Linear SVM | bn_en | 17 | 9 | 1.0000 | 0.8889 | 0.9412 | 0.0000 |
| TF-IDF + Linear SVM | en | 44 | 22 | 1.0000 | 0.9545 | 0.9767 | 0.0000 |
| TF-IDF + Linear SVM | hi | 37 | 20 | 0.8696 | 1.0000 | 0.9302 | 0.1765 |
| TF-IDF + Linear SVM | hinglish | 120 | 55 | 0.9123 | 0.9455 | 0.9286 | 0.0769 |
| TF-IDF + Linear SVM | mr_en | 22 | 7 | 0.8750 | 1.0000 | 0.9333 | 0.0667 |
| TF-IDF + Linear SVM | ta_en | 27 | 14 | 0.9286 | 0.9286 | 0.9286 | 0.0769 |
| TF-IDF + Linear SVM | te_en | 25 | 9 | 0.7500 | 1.0000 | 0.8571 | 0.1875 |

By scam type:

| Model | Scam type | Rows | Scam rows | Precision | Recall | F1 | FPR |
|---|---|---|---|---|---|---|---|
| TF-IDF + Logistic Regression | courier_customs | 20 | 20 | 1.0000 | 1.0000 | 1.0000 | n/a |
| TF-IDF + Logistic Regression | electricity_bill | 19 | 19 | 1.0000 | 0.9474 | 0.9730 | n/a |
| TF-IDF + Logistic Regression | fake_bank_otp | 21 | 21 | 1.0000 | 0.9048 | 0.9500 | n/a |
| TF-IDF + Logistic Regression | fake_kyc | 25 | 25 | 1.0000 | 0.9200 | 0.9583 | n/a |
| TF-IDF + Logistic Regression | job_offer | 14 | 14 | 1.0000 | 1.0000 | 1.0000 | n/a |
| TF-IDF + Logistic Regression | loan_offer | 20 | 20 | 1.0000 | 1.0000 | 1.0000 | n/a |
| TF-IDF + Logistic Regression | lottery | 17 | 17 | 1.0000 | 1.0000 | 1.0000 | n/a |
| TF-IDF + Logistic Regression | none | 156 | 0 | n/a | n/a | n/a | 0.0833 |
| TF-IDF + Linear SVM | courier_customs | 20 | 20 | 1.0000 | 1.0000 | 1.0000 | n/a |
| TF-IDF + Linear SVM | electricity_bill | 19 | 19 | 1.0000 | 0.9474 | 0.9730 | n/a |
| TF-IDF + Linear SVM | fake_bank_otp | 21 | 21 | 1.0000 | 0.8571 | 0.9231 | n/a |
| TF-IDF + Linear SVM | fake_kyc | 25 | 25 | 1.0000 | 0.9200 | 0.9583 | n/a |
| TF-IDF + Linear SVM | job_offer | 14 | 14 | 1.0000 | 1.0000 | 1.0000 | n/a |
| TF-IDF + Linear SVM | loan_offer | 20 | 20 | 1.0000 | 1.0000 | 1.0000 | n/a |
| TF-IDF + Linear SVM | lottery | 17 | 17 | 1.0000 | 1.0000 | 1.0000 | n/a |
| TF-IDF + Linear SVM | none | 156 | 0 | n/a | n/a | n/a | 0.0833 |

#### Leave-one-source-out (train without the source, score on it; hyperparameters frozen)

F1 / precision / recall use the threshold tuned in-distribution (source-balanced rows use their own tuned threshold). ROC-AUC and PR-AUC do not depend on a threshold.

| Model | Held-out source | Variant | Rows | ROC-AUC | PR-AUC | F1 | Precision | Recall |
|---|---|---|---|---|---|---|---|---|
| TF-IDF + Logistic Regression | hf_phishing_texts | in-distribution | 2,604 | 0.9983 | 0.9970 | 0.9730 | 0.9735 | 0.9725 |
| TF-IDF + Logistic Regression | hf_phishing_texts | leave-one-source-out | 2,604 | 0.6374 | 0.5503 | 0.4929 | 0.5079 | 0.4788 |
| TF-IDF + Logistic Regression | hf_phishing_texts | source-balanced (LOSO) | 2,604 | 0.6407 | 0.5536 | 0.5036 | 0.4929 | 0.5148 |
| TF-IDF + Linear SVM | hf_phishing_texts | in-distribution | 2,604 | 0.9984 | 0.9971 | 0.9730 | 0.9735 | 0.9725 |
| TF-IDF + Linear SVM | hf_phishing_texts | leave-one-source-out | 2,604 | 0.6369 | 0.5509 | 0.4926 | 0.5120 | 0.4746 |
| TF-IDF + Linear SVM | hf_phishing_texts | source-balanced (LOSO) | 2,604 | 0.6413 | 0.5543 | 0.5018 | 0.4820 | 0.5233 |
| TF-IDF + Logistic Regression | synthetic_llm (diagnostic) | in-distribution | 292 | 0.9835 | 0.9819 | 0.9357 | 0.9097 | 0.9632 |
| TF-IDF + Logistic Regression | synthetic_llm (diagnostic) | leave-one-source-out | 292 | 0.7304 | 0.7045 | 0.6770 | 0.5860 | 0.8015 |
| TF-IDF + Logistic Regression | synthetic_llm (diagnostic) | source-balanced (LOSO) | 292 | 0.7335 | 0.7143 | 0.6732 | 0.6059 | 0.7574 |
| TF-IDF + Linear SVM | synthetic_llm (diagnostic) | in-distribution | 292 | 0.9841 | 0.9825 | 0.9319 | 0.9091 | 0.9559 |
| TF-IDF + Linear SVM | synthetic_llm (diagnostic) | leave-one-source-out | 292 | 0.7262 | 0.6988 | 0.6708 | 0.5847 | 0.7868 |
| TF-IDF + Linear SVM | synthetic_llm (diagnostic) | source-balanced (LOSO) | 292 | 0.7270 | 0.7017 | 0.6731 | 0.5966 | 0.7721 |
| TF-IDF + Logistic Regression | uci_sms_spam | in-distribution | 814 | 0.9950 | 0.9781 | 0.9371 | 0.9425 | 0.9318 |
| TF-IDF + Logistic Regression | uci_sms_spam | leave-one-source-out | 814 | 0.9489 | 0.8360 | 0.4528 | 0.2968 | 0.9545 |
| TF-IDF + Logistic Regression | uci_sms_spam | source-balanced (LOSO) | 814 | 0.9457 | 0.8278 | 0.4665 | 0.3137 | 0.9091 |
| TF-IDF + Linear SVM | uci_sms_spam | in-distribution | 814 | 0.9953 | 0.9791 | 0.9371 | 0.9425 | 0.9318 |
| TF-IDF + Linear SVM | uci_sms_spam | leave-one-source-out | 814 | 0.9504 | 0.8436 | 0.4523 | 0.2975 | 0.9432 |
| TF-IDF + Linear SVM | uci_sms_spam | source-balanced (LOSO) | 814 | 0.9474 | 0.8300 | 0.4505 | 0.2971 | 0.9318 |

#### Highest-weight features

| Model | Scam | Safe |
|---|---|---|
| TF-IDF + Logistic Regression | char__ ! , char__ !, char__ . , char__ ., char__! , word__free, word__click here, word__click, word__customs, word__2005, word__phone, char__ £ | word__enron, char__.., char__ i , char__i , char__ >, char__enr, char__ enr, char__.. , char__ > , char__ enro, char__enro, word__branch |
| TF-IDF + Linear SVM | char__ ! , char__ !, char__ . , char__ ., char__! , word__click here, word__customs, word__click, word__free, char__ £, word__2005, word__phone | word__enron, char__ i , char__.., char__i , char__ >, word__branch, char__enr, char__ enr, char__ enro, char__enro, char__nro, char__ >  |

Top tuning trials, TF-IDF + Logistic Regression (30 trials on real validation rows):

| Features | C | Class weight | Val F1 | Val PR-AUC |
|---|---|---|---|---|
| word+char | 1000 | None | 0.9782 | 0.9949 |
| word+char | 1000 | balanced | 0.9782 | 0.9949 |
| word+char | 100 | balanced | 0.9777 | 0.9947 |
| word+char | 100 | None | 0.9777 | 0.9947 |
| word+char | 10 | None | 0.9761 | 0.9941 |

Top tuning trials, TF-IDF + Linear SVM (24 trials on real validation rows):

| Features | C | Class weight | Val F1 | Val PR-AUC |
|---|---|---|---|---|
| word+char | 1 | None | 0.9788 | 0.9950 |
| word+char | 1 | balanced | 0.9782 | 0.9948 |
| word+char | 10 | None | 0.9777 | 0.9951 |
| word+char | 10 | balanced | 0.9777 | 0.9951 |
| word+char | 0.1 | balanced | 0.9745 | 0.9919 |

_Hand-collected real Indian test set: not built yet, so no Hinglish result exists._
<!-- baseline:end -->

---

## Data quality (Phase 3.5): scam definition, audit and data inputs

### Scam vs spam: how much of "spam" is fraud?

Every row below was tagged by the assistant (Claude) reading the message against
`docs/label_rubric.md`; the project owner did not tag rows. Tags: `fraud` = fake prize/award
lures and call-back pretexts; `promo` = legitimate-style marketing (ringtones, chat lines,
competitions, deals); `service` = transactional or personal messages.

| Source | Rows tagged | fraud | promo | service | promo:fraud |
|---|---:|---:|---:|---:|---:|
| UCI SMS spam, random 100-row spot check (`data/raw/uci_sms/spot_check_100_tagged.csv`) | 100 | 34 | 57 | 9 | 1.7 : 1 |
| India SMS, random 100-row spot check (60 were spam, 40 ham; `spot_check_100_tagged.csv`) | 60 spam | 1 | 54 | 5 | 54 : 1 (from a single fraud row; very wide interval) |

### UCI subtype rule (`src/preprocessing/uci_spam.py`)

- The rule was **fitted on the assistant's own 100 UCI tags** and then extended after the
  assistant read all 546 unique UCI spam rows by hand (every row the rule called fraud, and all
  the rest). Agreement with those tags is **97 / 100**; this is a fit on the same rows, not a
  held-out accuracy. The 3 misses are personal messages called `promo` that the tags call `service`.
- Applied to all 546 unique UCI spam rows (Phase 2 deduplicated frame): promo 324, fraud 163,
  service 59 (59% / 30% / 11%).
- Owner spot check of 20 random rule-called-fraud rows (seed 2026, drawn from 220 exact-text-unique fraud-tagged rows): all 20 judged correct by the owner (20/20).

---

### Synthetic label audit (final)

Signals: blind cross-family LLM judge (Groq gpt-oss-120b judged Gemini rows, Gemini 3.5 flash-lite judged Groq rows),
out-of-fold TF-IDF classifier, urgency+link rule, and a random control sample. 162 flagged rows and 100 control
rows were read against `docs/label_rubric.md` by the assistant; the draft outcome was 39 flips and 18 removals.
The dataset author was then shown 30 of those rows without the assistant's decisions, examined only two of them closely (a partial check, not a full blind review) and ruled on the disputed ones (`docs/synthetic_audit_overrides.csv`):
domain-mismatch and OTP-use rows accepted as scam or removed; urgency-only and real-bank-domain rows removed rather than
flipped, so the model is not taught that genuine bank-domain messages are scams. The same rules were then applied to every
safe row by script (`safe_rule_violations`), adding 42 more decisions.

| | Rows |
|---|---:|
| Generated (195 batches) / kept after the generator's own filters | 1,950 / 1,654 |
| Reviewed (by hand or by rule) | 304 |
| Removed / flipped (33 safe to scam, 2 scam to safe) | 74 / 35 |
| Audited dataset | 1,580 (797 scam, 783 safe) |
| Never flagged and never read (`unreviewed`) | 1,350 |

**The owner review was partial.** The 30-row sample got "keep" as a default for rows that were not examined closely;
only rows 9 and 21 were actively reviewed by the owner, so the 33% raw agreement (10 of 30) is **not a meaningful
agreement rate** and is not used anywhere. The sample was also stratified 10/10/10 by the assistant's decision, so it
could not estimate a population rate even with full attention.

After the audit, no safe row in the audited set breaks the link/OTP rules (checked with `safe_rule_violations`).
The generator prompt now forbids mismatched domains and OTP instructions in safe messages
(`SAFE_LINK_RULE`, `SAFE_OTP_RULE`) and drops violating safe messages at generation time. A future regeneration
has not been run, so that prompt change is untested against a live model.

### India SMS (`junioralive/india-spam-sms-classification`) in the pipeline

2,266 rows loaded, 2,052 after merge deduplication, 1,875 after masking, near-duplicate removal (135) and overlap
with the reference (5). Kept: 1,267 ham (WhatsApp stock-group chat), 598 promo, 9 service and 1 fraud row
(split 1,311 / 282 / 282 into train / val / test). It adds almost no scam rows, so under policy D it acts as an
all-safe source: leave-one-source-out for India is not evaluable (no scam rows in test) and the "India" source
identifies the safe class by itself. Treat its contribution as a false-positive benchmark and a confound to check, not as scam evidence.

<!-- phase35:start -->
## Data quality (Phase 3.5): ablation ladder and before/after

Run date: 2026-09-26. Everything below is produced by `python -m src.training.ladder` (validation only),
`python -m src.training.phase35_final` (the chosen level, full Phase 3 protocol, test set scored once) and
`python -m src.training.phase35_report` (this text).

### Ladder (validation data only; the test split is never read)

Levels are cumulative: **L0** Phase 3 data as it was (old spam=scam definition); **L1** + audited synthetic labels;
**L2a** + scam-definition policy D (legit promotions and service notices withheld from training, kept as a
false-positive benchmark) + India SMS rows; **L3** + text normalisation (quote markers, reply boilerplate,
years to `<YEAR>`, currency to `<CUR>`); **L4** + drop web-crawl rows and pipeline notices; **L5** + drop
Enron-internal email. **L2b** is a contrast branch (promotions and service notices relabelled `safe` and
used as hard negatives) and is not eligible for selection. Every level is scored with the same fixed classifier
(TF-IDF word+char, logistic regression C=1000, Phase 3's selection), so differences come from the data.

| Level | Train rows | Val rows | Val F1 | Val ROC-AUC | Short-slice F1 (n) | Fingerprints scam / safe | Scam-signal share | Audit | Source-ID acc (majority) | LOSO AUC HF | LOSO AUC UCI | Promo/service flagged |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| L0 | 15,978 | 3,129 | 0.978 | 0.998 | 0.945 (1,157) | 2 / 10 | 33% | fail | 0.953 (0.762) | 0.652 | 0.953 | 85% (n=52) |
| L1 | 15,916 | 3,129 | 0.978 | 0.998 | 0.948 (1,157) | 2 / 11 | 37% | fail | 0.953 (0.762) | 0.634 | 0.951 | 85% (n=52) |
| L2a | 16,536 | 3,268 | 0.977 | 0.999 | 0.941 (1,290) | 2 / 11 | 30% | fail | 0.927 (0.729) | 0.663 | 0.998 | 68% (n=143) |
| L2b | 17,227 | 3,411 | 0.963 | 0.996 | 0.882 (1,430) | 2 / 9 | 30% | fail | 0.922 (0.699) | 0.628 | 0.978 | 12% (n=143) |
| L3 | 16,512 | 3,259 | 0.976 | 0.998 | 0.939 (1,288) | 0 / 8 | 33% | fail | 0.929 (0.729) | 0.638 | 0.995 | 75% (n=142) |
| L4 | 16,119 | 3,181 | 0.975 | 0.998 | 0.940 (1,241) | 0 / 10 | 30% | fail | 0.927 (0.722) | 0.650 | 0.996 | 77% (n=142) |
| L5 | 14,473 | 2,817 | 0.974 | 0.998 | 0.937 (1,216) | 0 / 9 | 30% | fail | 0.924 (0.686) | 0.659 | 0.997 | 73% (n=142) |

Reading notes: validation sets differ between levels (labels and rows change), so F1 is not comparable across
levels and was **not** used for selection. "Promo/service flagged" is the share of legitimate promotions and
service notices in validation that the level's model calls scam: under L0 and L1 those rows were *labelled*
scam (old definition), so a high rate is not an error there. L0 reproduces Phase 3 exactly (validation F1
0.9782, same audit result), which confirms the ladder is measuring the data and not the harness.

Top word-audit features per level (fingerprints are corpus artifacts, see `src/training/feature_audit.py`):

- **L0** scam: http, phone, click, your, our, com, free, 2005, mobile, click here, viagra, here, info, txt  
  safe: enron, 2002, thanks, url url, language, ok, that, 2001, wrote, enron com, vince, university, my, so  
  fingerprints scam: 2005, 2004; safe: enron, 2002, 2001, wrote, enron com, vince, university, gt, linguistics, lt gt
- **L1** scam: http, phone, your, click, our, com, free, 2005, mobile, viagra, click here, here, info, claim  
  safe: enron, 2002, thanks, url url, language, ok, that, wrote, 2001, enron com, branch, vince, university, my  
  fingerprints scam: 2005, 2004; safe: enron, 2002, wrote, 2001, enron com, vince, university, gt, linguistics, lt gt, conference
- **L2a** scam: http, phone, your, click, com, our, 2005, click here, free, viagra, claim, pay, info, re  
  safe: enron, 2002, thanks, url url, language, ok, wrote, enron com, 2001, branch, vince, tomorrow, university, attached  
  fingerprints scam: 2005, 2004; safe: enron, 2002, wrote, enron com, 2001, vince, university, linguistics, gt, conference, houston
- **L2b** scam: http, com, our, phone, click here, your, 2005, viagra, pay, re, email, remove, software, 2004  
  safe: enron, 2002, thanks, click url, url url, language, wrote, branch, enron com, ok, 2001, tomorrow, vince, university  
  fingerprints scam: 2005, 2004; safe: enron, 2002, wrote, enron com, 2001, vince, university, linguistics, gt
- **L3** scam: http, phone, your, click, com, our, click here, free, viagra, info, claim, re, software, online  
  safe: enron, thanks, url url, language, ok, enron com, branch, vince, tomorrow, attached, that, university, date, so  
  fingerprints scam: none; safe: enron, enron com, vince, university, linguistics, gt, houston, lt gt
- **L4** scam: http, phone, your, click, com, our, click here, free, viagra, claim, info, re, link, software  
  safe: enron, thanks, language, ok, enron com, branch, vince, attached, tomorrow, university, that, so, edu, linguistics  
  fingerprints scam: none; safe: enron, enron com, vince, university, linguistics, gt, houston, lt gt, university of, wrote
- **L5** scam: http, com, phone, click, your, our, click here, free, viagra, link, re, info, claim, pay  
  safe: thanks, language, ok, branch, university, tomorrow, that, attached, linguistics, so, edu, my, gt, vince  
  fingerprints scam: none; safe: university, linguistics, gt, vince, lt gt, university of, wrote, conference, lt

### Selection (rule fixed before the ladder ran)

The rule is in the docstring of `src/training/ladder.py`: success means the feature audit PASSES (zero
fingerprints in the top-30 of both classes and a scam-signal share of at least 50%); the chosen level is the first
successful level on the path L0, L1, L2a, L3, L4, L5; if none succeeds, the level with the fewest fingerprints is
chosen and the phase is reported as **not meeting its success criterion**. (One L0-only timing run preceded the full
ladder; it reproduced the audit already recorded for Phase 3 and informed no choice.)

**Outcome: no level passed. Criterion met: False. Chosen by the fallback rule: L3.**
Fingerprints in the top-30 (scam / safe): L0 2/10, L1 2/11, L2a 2/11, L2b 2/9, L3 0/8, L4 0/10, L5 0/9.
The scam-signal share never reached 50% (best 37%).
Year masking removed the scam-side year fingerprints (`2004`, `2005`) from L3 on. What remains is mostly on the
safe side and comes from HF "safe" email: linguistics-list mail (`linguistics`, `university`, `conference`),
HTML entities (`gt`, `lt`), the name `vince` and, until Enron rows are dropped at L5, `enron`. The scam side is
dominated by generic web-spam words (`http`, `click`, `viagra`, `phone`) that are not fingerprints in the pre-registered
lexicon but are not the Indian-scam signals the project cares about either. These are handed to Phase 4.

### Full Phase 3 protocol on the chosen level (L3), test set scored once

Test sets differ from Phase 3's: the "after" test set contains India SMS rows, excludes legitimate
promotions and service notices (withheld), and drops rows removed by normalisation and leakage trimming
(`3,418` test rows before, `3,529` after). Numbers are not a like-for-like
accuracy comparison; they show what the new definition and cleaning do. "Before" uses the old spam=scam definition.

| Model | Before: test F1 / ROC-AUC | After: test F1 / ROC-AUC | After, short messages (<=300 chars) | After: legit promo/service flagged (test) |
|---|---:|---:|---:|---:|
| Logistic regression | 0.9699 / 0.9982 | 0.9699 / 0.9978 | 0.9237 / 0.9927 (n=1,363) | 78% (n=153) |
| Linear SVM | 0.9699 / 0.9983 | 0.9718 / 0.9979 | 0.9231 / 0.9931 (n=1,363) | 76% (n=153) |

| Model | Held-out source | Before: in-dist AUC | Before: LOSO AUC | After: in-dist AUC | After: LOSO AUC |
|---|---:|---:|---:|---:|---:|
| LR | HF texts | 0.998 | 0.637 | 0.998 | 0.632 |
| LR | synthetic | 0.983 | 0.730 | 0.973 | 0.711 |
| LR | UCI SMS | 0.995 | 0.949 | 1.000 | 0.993 |
| SVM | HF texts | 0.998 | 0.637 | 0.998 | 0.625 |
| SVM | synthetic | 0.984 | 0.726 | 0.974 | 0.704 |
| SVM | UCI SMS | 0.995 | 0.950 | 1.000 | 0.992 |

Highest-weight classifier features (top 10 per class; the word-only audit above is the pass/fail view):

- LR Before: scam `char__ ! `, `char__ !`, `char__ . `, `char__ .`, `char__! `, `word__free`, `word__click here`, `word__click`, `word__customs`, `word__2005`; safe `word__enron`, `char__..`, `char__ i `, `char__i `, `char__ >`, `char__enr`, `char__ enr`, `char__.. `, `char__ > `, `char__ enro`
- LR After: scam `char__! `, `word__re`, `char__ ' `, `word__click here`, `word__com`, `word__click`, `word__http`, `word__your`, `char__ '`, `word__for you`; safe `word__enron`, `char__ i `, `word__branch`, `char__i `, `word__url url`, `char__ i`, `char__enr`, `char__ enr`, `char__'s`, `char__ enro`
- SVM Before: scam `char__ ! `, `char__ !`, `char__ . `, `char__ .`, `char__! `, `word__click here`, `word__customs`, `word__click`, `word__free`, `char__ £`; safe `word__enron`, `char__ i `, `char__..`, `char__i `, `char__ >`, `word__branch`, `char__enr`, `char__ enr`, `char__ enro`, `char__enro`
- SVM After: scam `char__! `, `word__re`, `char__ ' `, `word__click here`, `word__com`, `word__click`, `word__http`, `char__ '`, `word__your`, `word__for you`; safe `word__enron`, `char__ i `, `word__branch`, `word__url url`, `char__i `, `char__ i`, `char__enr`, `char__ enr`, `char__ enro`, `char__enro`

### What the numbers say

- **The pre-registered success criterion was not met.** No level passes the feature audit. Artifact reduction did
  what it targets (the scam-side year fingerprints `2004` and `2005` disappear at L3, Enron rows leave at L5) but the
  safe side keeps mailing-list and HTML fingerprints, and the scam class is still described by generic web-spam words
  rather than Indian-scam cues. The word audit model is only one view; it says the corpora, not the labels, still
  drive the top features.
- **Headline accuracy did not change.** Test F1 stays about 0.97 and the leave-one-source-out AUC on HF texts is
  0.632 (Phase 3: 0.637). The source confound, which is the main reason cross-source transfer is poor, was not
  reduced by these steps. Do not read the after-numbers as an improvement.
- **UCI leave-one-source-out AUC rises from about 0.95 to 0.99** because UCI is now "fraud vs ham" (fraud lures are
  easy to separate) instead of "spam vs ham"; it is a change of task, not of model quality.
- **Policy D leaves legitimate promotions flagged.** Models trained without ever seeing promotions flag
  68% of validation promotions and service notices as scam under L2a (n=143) and
  78% on the test benchmark (LR, n=153). The contrast level L2b, which labels them safe, flags only
  12% on validation (validation F1 0.963 vs 0.977; not directly comparable because
  the label sets differ). The ladder's selection rule did not use this benchmark, so it does not reflect the project's stated
  goal of not flagging marketing; this is a decision for Phase 4 (policy D vs A).
- **India SMS adds a safe-only source**, so it is a confound to watch rather than evidence about scams.
- **Short messages (<=300 chars)** score lower than the full test set (F1 about 0.92 vs 0.97) and are the fairer
  target for SMS; the Hinglish gap is still open because no hand-collected real Indian test set exists.


Word-only audit model on the chosen level's training data: fingerprints scam 0 / safe 8,
scam-signal share 33%, audit fail.
<!-- phase35:end -->

<!-- phase35b:start -->
### Phase 4 data configuration check: L3b = L3 normalisation + policy A (validation only, run once)

Requested after the ladder because policy D left most legitimate promotions flagged. Same fixed classifier and the same
validation-only protocol as the ladder; the test split was not scored. This is an extra check outside the ladder's
pre-registered selection rule, so it does not change the ladder outcome above.

| Level | Fingerprints scam / safe | Scam-signal share | Legit promo/service flagged | ...by source | LOSO AUC HF | LOSO AUC UCI | Val F1 / short-slice F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| L3 (policy D) | 0 / 8 | 33% | 75% (n=142) | India SMS 72% / UCI SMS 79% | 0.638 | 0.995 | 0.976 / 0.939 |
| L3b (policy A) | 0 / 8 | 33% | 14% (n=142) | India SMS 6% / UCI SMS 29% | 0.600 | 0.974 | 0.956 / 0.864 |

Source identifiability (text alone predicts the source): 0.921 accuracy against
0.698 for always guessing the largest source.

India SMS is all-safe under policy A (1 scam row), so leave-one-source-out AUC cannot be computed for it. The check for a
"source means safe" shortcut:

- **India SMS** (281 validation rows, 1 scam): no AUC exists, so the flag rate is compared between a model trained on the source and one that never saw it. Overall 2% vs 23%; promotions and service notices (n=90) 6% vs 63%; everything else (chat, n=191) 1% vs 5%.

How to read it: the chat rows are rarely flagged either way, so the model does not need to have seen India to keep them safe. The promotions are different: they are rarely flagged when India promotions are in training and mostly flagged
when they are not, so the leniency toward promotions is learned from these examples and its transfer to other senders is
unproven (UCI promotions, which are in training, are still flagged 29%). A real
Indian test set is needed to measure that.

**Verdict:** no serious problem. The feature audit still fails (fingerprints 0 / 8, scam-signal share 33%, the same as L3),
the flag rate on legitimate promotions falls from 75% to 14%, and the price is a lower validation F1 (the task is harder
and the label sets differ) and a lower short-message F1. Watch items for Phase 4: leave-one-source-out AUC on HF texts is a little lower
(single validation run, no error bars), promotion leniency depends on India promotions being in training, and 29% of UCI promotions are still flagged.
L3b is the Phase 4 data configuration.
<!-- phase35b:end -->

<!-- phase4-baseline:start -->
## Baselines re-run on the Phase 4 data configuration (L3b)

Run by `python -m src.training.phase4_baseline` (unchanged Phase 3 protocol on `data/processed_phase4/`: tuning on real validation rows, test scored once per model). Train 17,201 / validation 3,401 real + 280 synthetic / test 3,682 (real only). This is the like-for-like baseline for the transformers: the Phase 3.5 numbers earlier in this file belong to L3 (policy D) on a different test set. "Promo/service flagged" is the share of the 153 held-out legitimate promotion and service-notice test rows (labelled `safe` under policy A) that the model calls scam. Short = raw text of at most 300 characters.

| Model | Operating point | Threshold | Precision | Recall | F1 | ROC-AUC | PR-AUC | FP / FN | Short-message F1 | Promo/service flagged |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| TF-IDF + Logistic Regression | F1-tuned threshold (Phase 3.5 protocol) | -0.374 | 0.9434 | 0.9542 | 0.9487 | 0.9948 | 0.9881 | 55 / 44 | 0.8365 | 18% |
| TF-IDF + Logistic Regression | recall-first threshold (recall >= 0.97 on real validation) | -0.895 | 0.9277 | 0.9625 | 0.9448 | 0.9948 | 0.9881 | 72 / 36 | 0.8371 | 20% |
| TF-IDF + Linear SVM | F1-tuned threshold (Phase 3.5 protocol) | -0.023 | 0.9510 | 0.9500 | 0.9505 | 0.9947 | 0.9878 | 47 / 48 | 0.8419 | 19% |
| TF-IDF + Linear SVM | recall-first threshold (recall >= 0.97 on real validation) | -0.149 | 0.9315 | 0.9635 | 0.9473 | 0.9947 | 0.9878 | 68 / 35 | 0.8378 | 22% |

Threshold transfer: the recall-first rule keeps recall >= 0.97 on validation by construction (logreg 0.9709, SVM 0.9709), but on the test set recall is 0.9625 (logreg) and 0.9635 (SVM): a threshold chosen on validation does not hold its recall on new data.

By source, recall-first threshold:

| Model | Source | Rows | Scam rows | Precision | Recall | F1 | FPR |
|---|---|---:|---:|---:|---:|---:|---:|
| TF-IDF + Logistic Regression | hf_phishing_texts | 2590 | 937 | 0.9678 | 0.9616 | 0.9647 | 0.0181 |
| TF-IDF + Logistic Regression | kaggle_india_spam_sms | 280 | 0 | n/a | n/a | n/a | 0.0500 |
| TF-IDF + Logistic Regression | uci_sms_spam | 812 | 23 | 0.4510 | 1.0000 | 0.6216 | 0.0355 |
| TF-IDF + Linear SVM | hf_phishing_texts | 2590 | 937 | 0.9730 | 0.9626 | 0.9678 | 0.0151 |
| TF-IDF + Linear SVM | kaggle_india_spam_sms | 280 | 0 | n/a | n/a | n/a | 0.0464 |
| TF-IDF + Linear SVM | uci_sms_spam | 812 | 23 | 0.4340 | 1.0000 | 0.6053 | 0.0380 |

Leave-one-source-out (train without the source, score it; F1 uses the F1-tuned in-distribution threshold). The India SMS source has no scam rows in test, so it cannot be evaluated this way:

| Model | Held-out source | Variant | Rows | ROC-AUC | PR-AUC | F1 |
|---|---|---|---:|---:|---:|---:|
| TF-IDF + Logistic Regression | hf_phishing_texts | in-distribution | 2590 | 0.9964 | 0.9945 | 0.9659 |
| TF-IDF + Logistic Regression | hf_phishing_texts | leave-one-source-out | 2590 | 0.6019 | 0.5072 | 0.0660 |
| TF-IDF + Linear SVM | hf_phishing_texts | in-distribution | 2590 | 0.9965 | 0.9947 | 0.9668 |
| TF-IDF + Linear SVM | hf_phishing_texts | leave-one-source-out | 2590 | 0.5977 | 0.5055 | 0.0560 |
| TF-IDF + Logistic Regression | synthetic_llm (diagnostic only) | in-distribution | 280 | 0.9716 | 0.9733 | 0.9028 |
| TF-IDF + Logistic Regression | synthetic_llm (diagnostic only) | leave-one-source-out | 280 | 0.7055 | 0.7083 | 0.5630 |
| TF-IDF + Linear SVM | synthetic_llm (diagnostic only) | in-distribution | 280 | 0.9729 | 0.9748 | 0.9181 |
| TF-IDF + Linear SVM | synthetic_llm (diagnostic only) | leave-one-source-out | 280 | 0.7042 | 0.7035 | 0.5333 |
| TF-IDF + Logistic Regression | uci_sms_spam | in-distribution | 812 | 0.9976 | 0.9279 | 0.6389 |
| TF-IDF + Logistic Regression | uci_sms_spam | leave-one-source-out | 812 | 0.9711 | 0.4108 | 0.2366 |
| TF-IDF + Linear SVM | uci_sms_spam | in-distribution | 812 | 0.9976 | 0.9186 | 0.6479 |
| TF-IDF + Linear SVM | uci_sms_spam | leave-one-source-out | 812 | 0.9707 | 0.4227 | 0.2683 |
<!-- phase4-baseline:end -->

<!-- phase4:start -->
## Transformer fine-tuning (Phase 4)

Data configuration L3b (L3 normalisation + policy A). Train 17,201 / validation 3,681 (3,401 real + 280 synthetic) / test 3,682 rows (real only, 26.1% scam, 153 legitimate promotion/service rows). Trained on Colab (cuda, torch 2.11.0+cu128, transformers 5.17.0), seed 42, max 6 epochs with early stopping (patience 2) on real-validation PR-AUC, class-weighted loss, max length 256. Decision threshold = highest threshold with recall >= 0.97 on real validation scams: distilbert-base-uncased 0.0189, google/muril-base-cased 0.0091. Model exported: **distilbert-base-uncased** (chosen by real-validation PR-AUC before the test set was scored).

### Real test set, all systems (scam = positive)

Baselines were re-run on the same L3b data (`src/training/phase4_baseline.py`), so this is like for like. The Phase 3.5 numbers in the section above belong to L3 (policy D) on a different test set and are **not** comparable. Recall-first rows use the same rule and target as the transformers.

| System | Threshold | Precision | Recall | F1 | ROC-AUC | PR-AUC | FP / FN | Short-message F1 | Promo/service flagged |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| TF-IDF + Logistic Regression (recall-first threshold) | -0.895 | 0.9277 | 0.9625 | 0.9448 | 0.9948 | 0.9881 | 72 / 36 | 0.8371 | 20% |
| TF-IDF + Linear SVM (recall-first threshold) | -0.149 | 0.9315 | 0.9635 | 0.9473 | 0.9947 | 0.9878 | 68 / 35 | 0.8378 | 22% |
| TF-IDF + Logistic Regression (F1-tuned threshold, Phase 3.5 protocol) | -0.374 | 0.9434 | 0.9542 | 0.9487 | 0.9948 | 0.9881 | 55 / 44 | 0.8365 | 18% |
| TF-IDF + Linear SVM (F1-tuned threshold, Phase 3.5 protocol) | -0.023 | 0.9510 | 0.9500 | 0.9505 | 0.9947 | 0.9878 | 47 / 48 | 0.8419 | 19% |
| **distilbert-base-uncased** (recall-first threshold) | 0.019 | 0.9333 | 0.9625 | 0.9477 | 0.9955 | 0.9901 | 66 / 36 | 0.8264 | 22% |
| **google/muril-base-cased** (recall-first threshold) | 0.009 | 0.9143 | 0.9667 | 0.9397 | 0.9957 | 0.9894 | 87 / 32 | 0.8086 | 32% |

95% bootstrap intervals for the transformers:

| Model | Precision (95% CI) | Recall (95% CI) | F1 (95% CI) | ROC-AUC (95% CI) |
|---|---|---|---|---|
| distilbert-base-uncased | 0.9333 (0.9178 to 0.9488) | 0.9625 (0.9502 to 0.9747) | 0.9477 (0.9377 to 0.9571) | 0.9955 (0.9934 to 0.9971) |
| google/muril-base-cased | 0.9143 (0.8966 to 0.9304) | 0.9667 (0.9545 to 0.9773) | 0.9397 (0.9287 to 0.9504) | 0.9957 (0.9941 to 0.9971) |

Paired difference on the same test rows (positive = transformer better):

| Comparison (paired, same test rows) | dF1 (95% CI) | dRecall (95% CI) | dROC-AUC (95% CI) |
|---|---|---|---|
| distilbert-base-uncased minus TF-IDF + Logistic Regression | +0.0029 (-0.0064 to +0.0128) | +0.0000 (-0.0107 to +0.0120) | +0.0007 (-0.0012 to +0.0025) |
| distilbert-base-uncased minus TF-IDF + Linear SVM | +0.0004 (-0.0085 to +0.0097) | -0.0010 (-0.0114 to +0.0104) | +0.0007 (-0.0012 to +0.0026) |
| google/muril-base-cased minus TF-IDF + Logistic Regression | -0.0050 (-0.0157 to +0.0053) | +0.0042 (-0.0084 to +0.0164) | +0.0009 (-0.0007 to +0.0026) |
| google/muril-base-cased minus TF-IDF + Linear SVM | -0.0075 (-0.0181 to +0.0026) | +0.0031 (-0.0092 to +0.0157) | +0.0010 (-0.0007 to +0.0027) |

### By source (recall-first threshold)

| System | Source | Rows | Scam rows | Precision | Recall | F1 | FPR |
|---|---|---:|---:|---:|---:|---:|---:|
| TF-IDF + Logistic Regression (recall-first) | hf_phishing_texts | 2590 | 937 | 0.9678 | 0.9616 | 0.9647 | 0.0181 |
| TF-IDF + Logistic Regression (recall-first) | kaggle_india_spam_sms | 280 | 0 | n/a | n/a | n/a | 0.0500 |
| TF-IDF + Logistic Regression (recall-first) | uci_sms_spam | 812 | 23 | 0.4510 | 1.0000 | 0.6216 | 0.0355 |
| TF-IDF + Linear SVM (recall-first) | hf_phishing_texts | 2590 | 937 | 0.9730 | 0.9626 | 0.9678 | 0.0151 |
| TF-IDF + Linear SVM (recall-first) | kaggle_india_spam_sms | 280 | 0 | n/a | n/a | n/a | 0.0464 |
| TF-IDF + Linear SVM (recall-first) | uci_sms_spam | 812 | 23 | 0.4340 | 1.0000 | 0.6053 | 0.0380 |
| distilbert-base-uncased | hf_phishing_texts | 2590 | 937 | 0.9804 | 0.9626 | 0.9715 | 0.0109 |
| distilbert-base-uncased | kaggle_india_spam_sms | 280 | 0 | n/a | n/a | n/a | 0.0286 |
| distilbert-base-uncased | uci_sms_spam | 812 | 23 | 0.3548 | 0.9565 | 0.5176 | 0.0507 |
| google/muril-base-cased | hf_phishing_texts | 2590 | 937 | 0.9773 | 0.9658 | 0.9716 | 0.0127 |
| google/muril-base-cased | kaggle_india_spam_sms | 280 | 0 | n/a | n/a | n/a | 0.0393 |
| google/muril-base-cased | uci_sms_spam | 812 | 23 | 0.2949 | 1.0000 | 0.4554 | 0.0697 |

### Leave-one-source-out

Each model is retrained without the source and scored on it. Baseline: Phase 3 protocol (its F1-tuned in-distribution threshold). Transformers: at most 3 epochs per run, in-distribution recall-first threshold. Synthetic rows are validation rows (the test set has none) and are diagnostic only.

| System | Held-out source | Rows | ROC-AUC trained on it | ROC-AUC never seen | PR-AUC never seen | F1 never seen (in-distribution threshold) |
|---|---|---:|---:|---:|---:|---:|
| TF-IDF + Logistic Regression | hf_phishing_texts | 2590 | 0.9964 | 0.6019 | 0.5072 | 0.0660 |
| TF-IDF + Linear SVM | hf_phishing_texts | 2590 | 0.9965 | 0.5977 | 0.5055 | 0.0560 |
| TF-IDF + Logistic Regression | synthetic_llm (diagnostic only) | 280 | 0.9716 | 0.7055 | 0.7083 | 0.5630 |
| TF-IDF + Linear SVM | synthetic_llm (diagnostic only) | 280 | 0.9729 | 0.7042 | 0.7035 | 0.5333 |
| TF-IDF + Logistic Regression | uci_sms_spam | 812 | 0.9976 | 0.9711 | 0.4108 | 0.2366 |
| TF-IDF + Linear SVM | uci_sms_spam | 812 | 0.9976 | 0.9707 | 0.4227 | 0.2683 |
| distilbert-base-uncased | hf_phishing_texts | 2590 | 0.9978 | 0.5487 | 0.4757 | 0.2638 |
| distilbert-base-uncased | uci_sms_spam | 812 | 0.9931 | 0.9463 | 0.4115 | 0.1002 |
| distilbert-base-uncased | synthetic_llm (diagnostic only) | 280 | 0.9510 | 0.6112 | 0.6028 | 0.6723 |
| google/muril-base-cased | hf_phishing_texts | 2590 | 0.9978 | 0.5307 | 0.4198 | 0.5313 |
| google/muril-base-cased | uci_sms_spam | 812 | 0.9913 | 0.9756 | 0.4012 | 0.0551 |
| google/muril-base-cased | synthetic_llm (diagnostic only) | 280 | 0.9625 | 0.6021 | 0.5851 | 0.6698 |

Mitigation trigger (HF LOSO ROC-AUC below 0.75 or gap above 0.15): **fired** for distilbert, multilingual; a source-adversarial proposal is waiting for the owner's decision, and nothing was run.

### Recall-first trade-off (real validation rows only; not used to pick anything but the 0.97 row)

| Model | Recall target | Threshold | Precision | FPR | FP / FN | Promo/service flagged |
|---|---:|---:|---:|---:|---:|---:|
| distilbert-base-uncased | 0.95 | 0.6874 | 0.9725 | 0.0096 | 24 / 44 | 6% |
| distilbert-base-uncased | 0.97 | 0.0189 | 0.9538 | 0.0167 | 42 / 26 | 15% |
| distilbert-base-uncased | 0.99 | 0.0002 | 0.7649 | 0.1085 | 272 / 8 | 83% |
| google/muril-base-cased | 0.95 | 0.7200 | 0.9593 | 0.0144 | 36 / 44 | 11% |
| google/muril-base-cased | 0.97 | 0.0091 | 0.9303 | 0.0259 | 65 / 26 | 23% |
| google/muril-base-cased | 0.99 | 0.0028 | 0.8119 | 0.0817 | 205 / 8 | 70% |

### Diagnostic and unbuilt sets

- distilbert-base-uncased, **diagnostic only**, 280 synthetic validation rows: precision 0.9197, recall 0.8936, F1 0.9065, FPR 0.0791.
- google/muril-base-cased, **diagnostic only**, 280 synthetic validation rows: precision 0.8874, recall 0.9504, F1 0.9178, FPR 0.1223.
- Real Indian test set: **not built**, so there is no real Hinglish result.

### ONNX export (selected model; latency from the Colab CPU, not deployment hardware)

| Graph | Size (MB) | Test F1 | Test ROC-AUC | Median ms (1 msg) | p95 ms | Seconds per 1000 msgs (batch 32) |
|---|---:|---:|---:|---:|---:|---:|
| ONNX fp32 | 267.9 | 0.9482 | 0.9955 | 172.5 | 364.2 | 193.4 |
| ONNX int8 (dynamic) | 67.3 | 0.9443 | 0.9947 | 120.9 | 245.7 | 137.6 |

int8 vs fp32 on the full test set at the same threshold: label agreement 0.9919, max probability difference 0.8308. Standalone tokenizer matched the HF tokenizer on 200 rows. Error analysis: `docs/error_analysis_phase4.md`.
<!-- phase4:end -->

### Owner decisions after Phase 4 (2026-09-28)

**Headline, stated plainly: fine-tuning did not beat the TF-IDF baseline on this data.** DistilBERT's test F1 (0.9477) and ROC-AUC (0.9955) are
within noise of both TF-IDF baselines (paired 95% CIs straddle zero throughout), and leave-one-source-out generalisation to the held-out HF email
corpus is *worse* for both transformers (0.549 DistilBERT, 0.531 MuRIL) than for TF-IDF (about 0.60). The extra training cost bought no measured gain.

**Mitigation: not run now.** Both models tripped the pre-registered trigger (HF leave-one-source-out ROC-AUC below 0.75), so by that rule a fix was
"due". The owner chose not to run any of it yet, for three reasons:

1. The transformer did not beat TF-IDF in the first place, so spending Colab compute to patch its generalisation gap is a lower priority than other
   open work.
2. The HF leave-one-source-out metric measures whether the model generalises to a different corpus of **old email**, which is not the product's
   target channel (SMS / WhatsApp). A held-out email split is the wrong yardstick to optimise against; a held-out SMS/WhatsApp split would be the
   right one, and none of the current sources give a clean one (UCI is the only other SMS source and is already in training).
3. The real Indian test set does not exist yet. Any mitigation would be tuned and judged using the same public corpora that created the fingerprint
   problem, with no way to check whether it actually helps on real Indian SMS/WhatsApp messages. Building that test set is more valuable than tuning
   against a metric that itself doesn't match the target.

**Recorded as future work**, in priority order the owner can revisit once a real Indian test set exists or the product direction calls for it:

| Option | What it does | Cost | Open caveat |
|---|---|---|---|
| Source-adversarial training | Gradient-reversal head predicting data source from `[CLS]`, pushing the encoder to drop source-identifying features | ~1 extra fine-tune run per model + its LOSO runs | Source correlates with label (India SMS is ~all-safe, UCI ~96% safe), so this also strips some real signal; the reversal weight needs tuning on LOSO validation, not test |
| Source-balanced sampling per class | Re-weight training rows so no source dominates a class | Cheap (no retraining architecture change) | Phase 3 already showed plain re-weighting did not help TF-IDF; low expectation it helps here either |
| Drop the email corpus from training | Treat HF email as auxiliary/excluded, train mainly on SMS-like sources | Cheap, but shrinks training data substantially | Matches the actual product target (SMS/WhatsApp) better than the current mix, but removes most of the scam-labelled rows |

**Quantization: investigated, see below.** **Deployment model: recommended below.** Hub upload deferred to the deployment phase (Phase 9); the
trained model stays local for now.

### Quantization check: rows where int8 and fp32 disagree by more than 0.2

Recomputed locally from the downloaded `onnx_fp32/model.onnx` and `final_model/model_quantized.onnx` on all 3,682 real test rows (the
notebook only kept the aggregate stats above, not per-row values).

| | Count | Share of test set |
|---|---:|---:|
| \|p_int8 - p_fp32\| > 0.05 | 72 | 2.0% |
| \|p_int8 - p_fp32\| > 0.1 | 51 | 1.4% |
| \|p_int8 - p_fp32\| > 0.2 | 36 | 1.0% |
| ...of those, threshold-crossing label flips | 8 | 0.22% |

**What the 36 largest-divergence rows have in common:**
- **All 8 label flips go the same direction: safe -> scam.** Quantization never turned a real scam into a missed one among these rows; every flip
  is a false alarm introduced on a message fp32 called safe (p_fp32 < 0.02) that int8 pushed above the very low recall-first threshold (0.019).
  One of the 8 is a legitimate-promotion benchmark row (a UCI "get free content" style message); the model card and API should note this even
  though it is a rare event.
- **Quantization mostly pushes probabilities up, not down:** about 70% (25/36) of the divergent rows moved toward "scam" under int8, versus 30%
  moving toward "safe". This matches the precision drop seen in the aggregate table (recall unchanged 0.9625 -> 0.9625, precision 0.9343 -> 0.9268):
  the extra false positives are quantization noise, not lost recall.
- **Short-to-medium, ambiguous messages dominate:** median length among the 36 rows is 145 characters (vs. the whole test set's median of several
  hundred); several are single-line marketing-ish or fragmentary text ("Take some small dose tablet for fever", "500 free text msgs...", "Adult 18
  Content Your video will be with you shortly") where fp32 itself was already uncertain (p_fp32 well away from 0 or 1). Quantization noise shows up
  where the model was least confident to begin with, not on clear-cut cases.
- **No single source dominates**, but legitimate-promotion (benchmark) rows are overrepresented: 13 of 36 (36%) are benchmark rows, versus 4.2%
  (153/3,682) of the whole test set. UCI SMS is also overrepresented (16/36 = 44%, vs 22% of test). The HF email corpus is underrepresented
  (15/36 = 42%, vs 70% of test) — quantization noise concentrates on the short, promotion-like, non-email message style the product actually targets.

**Recommendation: ship int8, but don't show raw probabilities in the UI.** The accuracy cost is small and one-sided in the safer direction (false
alarms, never missed scams, in this sample), and the size/speed win is large (267.9 MB -> 67.3 MB, ~30% faster median CPU latency). But a raw
probability is not a stable or meaningful number here: the decision threshold itself is 0.019 (recall-first), so "3% probability" already means
"flagged as scam," which will read as wrong to a user expecting probabilities to track intuition; and quantization moves exactly the kind of
near-boundary short message the product needs to get right by up to 0.88 in probability without changing very many final labels. **The UI should
show risk bands (e.g. low / medium / high, or the labelled verdict) derived from the fixed threshold and the validation operating-point table
above, not the raw score.** This also matches the model card's existing note that probabilities are not calibrated.

### Deployment recommendation (for Phase 9)

**Recommendation: TF-IDF + Linear SVM as the primary classifier; do not deploy DistilBERT (fp32 or int8) yet.** Reasoning, following directly
from the numbers already measured in this phase:

| Metric | TF-IDF + Linear SVM | DistilBERT int8 | Winner |
|---|---:|---:|---|
| Test F1 | 0.9473 | 0.9443 | TF-IDF (within noise either way) |
| Test ROC-AUC | 0.9947 | 0.9947 | tie |
| Short-message F1 | 0.8378 | ~0.826 (fp32; int8 not separately re-measured on the short slice) | TF-IDF |
| Legit-promo flagged | 22% | 22%+ (fp32 22%; int8 likely similar or slightly worse given the false-positive skew above) | tie or TF-IDF |
| HF leave-one-source-out AUC | 0.598 | ~0.55 (fp32 not separately measured; full-precision DistilBERT was 0.549) | TF-IDF, clearly |
| Model size | A few MB (joblib) | 67.3 MB (int8) / 267.9 MB (fp32) | TF-IDF, by two orders of magnitude |
| CPU latency (batch 1) | Sub-millisecond to low single-digit ms (sparse dot product; not re-measured this phase) | 121 ms median (int8, Colab's 2-core CPU) | TF-IDF, by roughly two orders of magnitude |

TF-IDF ties or wins on every accuracy metric measured (all differences are within the paired bootstrap noise band) and clearly wins on
generalisation to held-out email and on every resource metric. Phase 4's own headline finding is that fine-tuning did not beat the baseline;
deploying the much heavier, slower model anyway would spend the free-tier API's CPU and memory budget on a model that has not earned it. **Ship
TF-IDF + Linear SVM now.** Keep the trained DistilBERT artifacts (fp32 and int8, both local) as a documented option to reconsider once either
holds: (a) the real Indian test set exists and shows a real Hinglish advantage for the transformer, or (b) the mitigation work (source-adversarial
training, etc., recorded as future work above) closes the leave-one-source-out gap enough to change this comparison. If redundancy/failover is
wanted at deployment time regardless of which model is primary, TF-IDF is also the natural fallback for a transformer-based service, not the
other way around, given how much cheaper and more available it is to keep warm.

<!-- phase6:start -->
**Run date:** 2026-09-28  
**Model:** `paraphrase-multilingual-MiniLM-L12-v2`  
**Eval set:** `data/knowledge_base/eval_set.json` (40 written messages the entries were not built from, 20 real messages from existing project datasets that neither author wrote, 3 labelled `no_match`)

Top-1/top-3 hit rate = fraction of *matched* rows (excludes `no_match` rows) where the expected pattern id is the top retrieved result / within the top 3:

| Text variant | Split | n | Top-1 hit rate | Top-3 hit rate |
|---|---|---|---|---|
| phrases | Overall | 57 | 68% | 86% |
| phrases | Written | 40 | 78% | 90% |
| phrases | Real | 17 | 47% | 76% |
| phrases_how | Overall | 57 | 68% | 89% |
| phrases_how | Written | 40 | 80% | 95% |
| phrases_how | Real | 17 | 41% | 76% |

**Chosen embedding text variant: `phrases_how`** (higher combined written+real top-1/top-3 hit rate on this eval set).

No-confident-match threshold, swept over the same eval set and picked to best separate matched rows (should be confident) from `no_match` rows (should not be), scoring the *average* of the two rates below so the much larger matched group can't dominate the choice - "matched confident rate" is how often a real pattern's top-1 similarity clears the threshold, "no_match decline rate" is how often an unrelated message's top-1 similarity correctly falls below it. Only 3 `no_match` examples exist in this eval set, so this threshold is a coarse estimate, not a tuned one - the similarity distributions of matched and unrelated messages overlap substantially for this model on short text, and a larger no_match set (a natural next step for expanding this eval set) would sharpen it:

| Text variant | Chosen threshold | Matched confident rate | No_match decline rate |
|---|---|---|---|
| phrases | 0.51 | 53% | 100% |
| phrases_how | 0.49 | 58% | 100% |

**`RAGEngine` default: `text_variant="phrases_how"`, `min_confident_similarity=0.49`.**

**Overlap risk (stated honestly):** both the knowledge base's `typical_phrases` and the 40 "written" evaluation messages were authored by the same person with the same general knowledge of these scam patterns, using deliberately different wording - this is not an independent, blind evaluation like the real Indian test set from earlier phases. The 20 "real" messages (drawn from UCI SMS and the India SMS dataset, never used to write the knowledge base) are the closer approximation to a genuine generalisation test, and their hit rate is reported separately for exactly that reason. The embedding-text variant and the no-confident-match threshold were both selected by looking at this same eval set, so the final numbers for the chosen configuration are slightly optimistic, not a blind test.
<!-- phase6:end -->



<!-- phase8:start -->
## Screenshot OCR (Phase 8)

**Run date:** 2026-09-30  
**OCR:** EasyOCR 1.7.2, CPU only, languages `en,hi` (default), hybrid recognition (see below)  
**Hardware for timings:** this dev machine: Intel Xeon E-2224G (4 cores, torch using 4 threads), 32 GB RAM. This is not deployment hardware.  
**Reproduce:** `python -m src.ocr.evaluate`

### Generated sample screenshots (synthetic, easier than real)

Four 720x1280 screenshots rendered with Pillow (`src/ocr/sample_screenshots.py`) plus an optional
fifth in Devanagari (rendered with the Windows Nirmala UI font). They show an Android SMS or
WhatsApp-style screen with a status bar, contact header, "Today" chip, bubbles with timestamps,
"Delivered"/tick receipts and an input bar. Ground truth is the contact name followed by each
bubble's text. **CER** is Levenshtein distance divided by ground-truth length, after collapsing
whitespace. **Chrome leaked** counts UI strings (status bar, timestamps, receipts, input hint)
still present after cleaning. Verdicts come from the real TF-IDF classifier and URL rules with the
template explainer (no API calls).

**Important caveat:** these images are clean and generated. They use one font, no emoji, no avatars
and no JPEG artefacts. The hybrid recognition, the URL repair and the I/1 fix below were all developed
by looking at OCR output on these same images. So they are a development set, not a held-out test,
and the numbers below are an optimistic upper bound. The real-screenshot check further down is
the honest measure.

**First attempt (single EasyOCR reader with `["en", "hi"]`, i.e. the Devanagari recognizer for
everything):**

| Sample | CER | Keyword recall | URL exact | Chrome leaked | Verdict / risk |
|---|---|---|---|---|---|
| sms_kyc_scam_en | 0.188 | 0.75 | NO | 2 | scam / medium |
| whatsapp_lottery_scam_hinglish | 0.104 | 0.80 | - | 2 | scam / high |
| sms_lunch_safe_en | 0.168 | 0.75 | - | 2 | safe / low |
| whatsapp_dark_parcel_scam_en | 0.141 | 0.80 | NO | 2 | scam / medium |
| sms_kyc_scam_hi (Devanagari) | 0.367 | 1.00 | - | 2 | scam / medium |

Failure modes observed:
- The Devanagari recognizer emits Devanagari digits for Latin digits ("२४ hours", "Rs ४९९९").
- It reads ":" as the visarga "ः".
- It drops "-", "." and ":" inside links: `http://sbi-kyc-verify.tk/update` came out as
  `httpillsbi kyc verify tklupdate`. With the link lost, the URL analyzer saw nothing and both
  link scams dropped from high to medium risk.
- The English recognizer gets the digits and hyphens right, but both models read "/" as "l"/"I".
- Rendering at 1.5x or 2x resolution did not fix the "/" misreads and doubled detection time,
  so that approach was rejected.

**Final (hybrid recognition + cleaning fixes):**

| Sample | Theme | CER | Keyword recall | URL exact | Chrome leaked | OCR conf. | OCR s (warm) | Expected | Verdict / risk |
|---|---|---|---|---|---|---|---|---|---|
| sms_kyc_scam_en | sms_light | 0.019 | 1.00 | yes | 0 | 0.86 | 3.7 | scam | scam / high |
| whatsapp_lottery_scam_hinglish | whatsapp_light | 0.012 | 1.00 | - | 0 | 0.84 | 4.2 | scam | scam / high |
| sms_lunch_safe_en | sms_light | 0.031 | 1.00 | - | 0 | 0.84 | 3.2 | safe | safe / low |
| whatsapp_dark_parcel_scam_en | whatsapp_dark | 0.005 | 1.00 | yes | 0 | 0.84 | 3.4 | scam | scam / high |
| sms_kyc_scam_hi (Devanagari) | sms_light | 0.000 | 1.00 | - | 0 | 0.83 | 3.6 | scam | scam / medium |

What changed:
1. **Hybrid recognition.** Boxes are detected once and read by the English model. Only boxes it reads
   with confidence < 0.5 are re-read by the Devanagari model, whose reading is kept only if it
   contains at least 2 Devanagari letters. On these samples, the English model scored Devanagari
   boxes 0.02-0.32 and clean Latin boxes 0.55-1.0. Running the Devanagari model on every box
   took 7.0-9.4s per image. The confidence gate brought that down to 3.2-4.2s.
2. **Cleaning fixes:** Devanagari digits become ASCII; "ः" after Latin becomes ":"; "|" after
   Devanagari becomes "।"; "I"/"l" touching a digit or before "pm" becomes "1" (never inside URLs);
   URL repair handles "http:lI"/"http:ll" → "http://", a missing dot before a known TLD, and
   "tklupdate" → "tk/update".

**Remaining errors (all 5 samples):**
- Dropped or changed punctuation ("customer;" for "customer,", missing sentence full stops).
- In the safe sample, the single-letter word "I" in "Great, I will book" was **never detected**
  by the CRAFT text detector (no box at all), so cleaning cannot recover it.
- Dark mode is detected by mean luminance < 110, and the image is inverted before OCR. The dark
  sample was inverted and read as well as the light ones.

**Timing and memory (this machine):**
- Model load: about 6s warm from disk. The first run also downloads 313 MB: CRAFT detector 83 MB,
  Devanagari recognizer 215 MB, English recognizer 15 MB.
- OCR per 720x1280 image, warm: 3.2-4.2s. Detection alone is about 2.6-3.5s of that.
- Process memory: 303 MB after importing torch + EasyOCR, 637 MB after loading the hybrid engine,
  683 MB after 4 images. Peak working set: 1.58 GB.
- In the end-to-end cold demo (`python -m src.pipeline --image <dark sample>`), OCR took 8.4s
  including model load, and the first RAG query took 11.7s (embedding model warm-up). Both are
  one-time costs that Phase 9 should pay at startup.

### Real phone screenshots (manual check)

**Not yet run.** This needs 3-5 real screenshots from the owner in `data/real_screenshots/` (see
PROGRESS.md, Phase 8 "YOU DO"). Results will be recorded here, separately from the generated
images above, using the summary table printed by `python -m src.ocr.check_real_screenshots`
(it contains no message text).
<!-- phase8:end -->

<!-- phase9:start -->
## Backend API (Phase 9): local measurements

**Run date:** 2026-09-30  
**Where:** local only, on the same dev machine as Phase 8 (Intel Xeon E-2224G, 4 cores, 32 GB RAM, Windows).
This is not the deployment hardware. The Docker image was not built (Docker isn't installed here), and
the API has not been deployed yet (see docs/deployment.md).  
**Setup:** `uvicorn api.main:create_app --factory --workers 1` with the production runtime flags
(`HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, `EASYOCR_DOWNLOAD_ENABLED=0`). Every model loaded from
local caches with downloads disabled. Supabase was deliberately unset.

**Startup:** 21.8 s from launch to ready. That breaks down as the classifier (hash-verified) 2.7 s, the
URL analyzer under 0.1 s, RAG (index check + warm-up query) 11.6 s, and OCR (load + warm-up image) 7.5 s.

**Requests (curl.exe, one at a time, warm):**

| Request | Result | Server-side stage times (ms) |
|---|---|---|
| `/analyze/text`, English KYC scam with link | scam / high, Groq explainer, `fake_kyc_update` matched, link defanged | classify 22.8, URLs 19.0, RAG 23.0, explain 1661.6 |
| `/analyze/text`, Hinglish lunch message | safe / low, Groq explainer | classify 2.2, RAG 18.2, explain 1301.0 |
| `/analyze/image`, dark-mode parcel scam screenshot | scam / high, `courier_customs_fee`, OCR quality "good", dark mode detected | validate 5.9, OCR 3514.7, RAG 24.2, explain 1531.3 |
| `/analyze/image`, text file renamed `.png` | 415 `unsupported_type` | - |
| `/analyze/text`, whitespace only | 422 `empty_text` | - |
| `/feedback` (Supabase unset) | 503 `feedback_not_configured` | - |
| 20 more text requests within a minute | 17 x 422, then 3 x 429 `rate_limited` with `Retry-After` (limit of 20/min, including 3 earlier requests) | - |

**Process memory** (Windows working set after startup and the requests above): **1.78 GB**, peak
**2.65 GB**, private bytes 2.08 GB. A Hugging Face CPU Basic Space has 16 GB, so this fits with large
headroom. The ZeroGPU host's RAM is undocumented. Linux RSS will differ somewhat from the Windows
working set, so measure on the host after deploying.

**Estimated Docker image size: about 2.4 GB.**
- The Python packages from `requirements-api.txt` and their dependencies measure 1,505 MB (116
  distributions, measured on Windows wheels; Linux CPU wheels are similar in size).
- EasyOCR models: 300 MB. MiniLM embedding model: about 460 MB. SVM model: 11 MB. Chroma index:
  under 1 MB.
- The `python:3.11-slim` base is about 125 MB.
- This is an estimate. It will be replaced with the real size once the image is built.

**Log privacy check on the real server log:** 0 occurrences of any message text, OCR text, link,
filename or client IP. The only IP in the log is uvicorn's own bind address at startup.

**Live feedback round trip (real Supabase project, local API, 2026-09-30):**
- `/analyze/text` on the KYC scam returned scam / high (Groq explainer).
- `/feedback` returned **201** in 733 ms.
- The row read back holds exactly `id, prediction_id, user_verdict, predicted_verdict,
  predicted_risk_level, input_type, classifier_model, explainer_path, matched_pattern, created_at`.
- 0 of 8 message phrases were found in the row. The only reference to the content is the knowledge
  base pattern id `fake_kyc_update`.
<!-- phase9:end -->

<!-- langfix:start -->
## Explainer output language fix (2026-09-30, between Phases 9 and 10)

**Symptom (found in Phase 9):** "Bhai kal 1 baje lunch pe milte hain, office ke paas wale cafe mein?" got an
English explanation.

**Cause:** language detection, not the prompt or the template.
- The explainer had its own 36-word Hinglish list, separate from the Phase 2 tagger, and only "hain" matched.
- A second, smaller gap in the prompt: `red_flags` was the one text field not told which language to use.

**Fix:**
- The explainer now uses the Phase 2 tagger, where Devanagari must be at least 20% of the letters.
- It uses that tagger's curated 89-word list plus 46 extra words (135 in total). Each extra word was checked against
  21,145 real English messages. The Phase 2 list itself is unchanged, so the stored data tags stay
  reproducible.
- Messages over 60 words need 3 distinct marker words instead of 2.
- The prompt now names the language for every text field and adds a script rule (Latin-only for
  Hinglish, Devanagari for Hindi).

**Detector comparison.** The share tagged Hinglish, plus the share tagged Hindi for the new detector:

| Set | n | Old explainer list | Phase 2 list | New (extended + long-text rule) | New -> hi |
|---|---|---|---|---|---|
| Synthetic rows labelled "hinglish", held-out half | 324 | 57.4% | 64.5% | 66.7% | 0.0% |
| Synthetic rows labelled "en" | 262 | 1.5% | 1.5% | 1.9% | 0.0% |
| Synthetic mr_en/bn_en/te_en/ta_en | 512 | 1.4% | 2.7% | 6.1% | 0.0% |
| Real English, train+val+test | 21,145 | 0.0% (0) | 0.0% (0) | 0.01% (2) | 0.0% |

The extended list alone flagged 11 real English messages. Adding the long-text rule cut that to 2.

**How to read these numbers:**
- **The "hinglish" synthetic label is noisy.** In a manual review of 45 misses from the *dev* half,
  about 40 were plain Indian-English SMS (e.g. "Dear customer, Rs 14,899 has been debited..."). The
  generator's language check only required "not Devanagari". Only 2 were real code-mixed misses
  ("...bhai", "...3 lakh limit ke liye..."), and both are now caught. So 66.7% is a lower bound on
  real Hinglish recall, not an estimate of it.
- **Hindi recall (100%) is not evidence.** Synthetic Hindi rows were kept only if the Phase 2 tagger
  called them Hindi.
- **The 60-word cutoff was picked while looking at the same real-English set**, so "2 false
  positives" is slightly optimistic. The rule had no effect on the held-out Hinglish rows.
- The rise to 6.1% on other code-mixed styles (mainly Marathi-English, which shares words with
  Hindi) means some of those messages now get a Hinglish instead of an English reply. That's
  arguably closer to the user's language, but still a known limitation.

**Live check with real Groq, full pipeline:**

| Message | Verdict | Path | Explanation / advice language | Red flags language |
|---|---|---|---|---|
| Hinglish scam: "Aapka bijli connection aaj raat 9 baje kat jayega ... Turant is link par payment karein: http://bijli-bill-update.top/pay" | scam / high | groq | Hinglish (Latin script) | **English** |
| Hinglish safe: "Bhai kal 1 baje lunch pe milte hain, office ke paas wale cafe mein?" | safe / low | groq | Hinglish (Latin script) | (none) |

One remaining partial: despite the new instruction, Groq wrote the scam's red flags in English.
The explanation and advice, which are the main user-facing text, were fully Hinglish. This is one
sample, so no rate is claimed.
<!-- langfix:end -->

<!-- phase10:start -->
## Web frontend (Phase 10): local checks

**Run date:** 2026-10-01
**Where:** local dev machine (same as Phases 8-9), Windows, Node 22.16, Next.js 16.3.7 static export.
Browser checks used headless Microsoft Edge driven by playwright-core. The API ran locally with
Supabase deliberately unset and `CORS_ORIGINS=http://localhost:3000`. Not tested yet: a real
phone, a manual screen-reader pass, and Lighthouse.

**Automated tests (`cd web && npm test`):** 176 Vitest tests in 13 files, all passing.
- axe-core: 0 violations on 8 views (analyze page in demo mode, with a text result, with a
  screenshot result, and the About page, each in English and Hindi). jsdom can't compute colour
  contrast, so axe's contrast rule is off there.
- Contrast is checked from the CSS tokens instead: 20 colour pairs x 2 themes, all at least 4.5:1
  (WCAG AA, normal text).

**Browser walkthrough (production build): 30 of 30 checks passed.**

| Mode | What was checked |
|---|---|
| Live (build with `NEXT_PUBLIC_API_URL=http://127.0.0.1:7860`, real API, real Groq) | Inputs enabled after `/health`; no banner. CSP blocked a `fetch` to another origin. Empty text rejected in the browser. Loading status shown. Focus moves to the result heading. Risk band has words. No anchors in the result. Feedback showed the 503 "isn't available" message and disabled its buttons. A text file sent as `image/png` got 415 `unsupported_type`, shown as a friendly message with a reference ID. The dark-mode screenshot sample showed its OCR text (207 characters) and its defanged link `hxxp://indiapost-redeliver[.]top/pay`. The Hindi switch set `<html lang="hi">`. The Devanagari sample's explanation had `lang="hi"`, Noto Sans Devanagari and a 28 px line height. No unexpected console errors. At 360 px wide (dark theme), neither page scrolls sideways. |
| Unreachable (same build, API stopped) | Banner says "the server is unreachable". Text box disabled. The recorded sample result is labelled and feedback is hidden. Retry announces "Still unreachable". |
| Not hosted (build without an API URL: the configuration that will be deployed first) | Banner says "The live backend is not hosted yet" and has no retry button. A screenshot sample shows its recorded result. The About page loads. No console errors. |

One live result, for a typed message that isn't one of the samples ("URGENT: Your SBI account is
blocked. Share the OTP you just received with our officer to unblock it today."): **scam / medium**.

**Build output (demo-only build):**
- `web/out/` is 1,712 KB on disk.
- All JavaScript chunks together are 669,674 bytes, or 201,109 bytes gzipped as one stream (a
  rough indicator, not per-request transfer size).
- Fonts are 11 self-hosted `.woff2` subset files, 612 KB in total. A browser downloads only the
  subsets its text needs.
- The sample screenshots are 216 KB.

**Problems found and fixed during the checks:**
- The API can return `length_required` (411), which the plan's error list missed. A test that scans
  the API source for error codes caught it.
- `errorMessage("heading")` returned the error heading's own text. Lookups now accept only the
  documented codes.
- The draft About page said 22% of genuine promotions are flagged. The deployed SVM uses the
  F1-tuned threshold (-0.0235 in `svm.joblib`), which flags **19%**; 22% belongs to the
  recall-first threshold. The table now shows both rows, and the deployed one is marked.
- Next 16.3's static export writes the About page's prefetch data to
  `about/__next.about/__PAGE__.txt`, but the client requests `about/__next.about.__PAGE__.txt`, so
  the request returned 404 on a plain static server. Navigation still worked through a fallback.
  Link prefetching is now off, and the 404 is gone.
- The favicon was missing (404). Added `app/icon.svg`.
<!-- phase10:end -->

<!-- phase10redesign:start -->
## Web frontend redesign (Phase 10): before / after

**Run date:** 2026-10-01. **Stack after:** Tailwind CSS 4.3.3, shadcn/ui components on radix-ui 1.6.7, motion 13.4.6,
lucide-react 1.49.0, sonner 2.0.8, next-themes 0.4.6 (all pinned exactly). CSS Modules removed.
**Where:** local dev machine; production static builds served by `python -m http.server` (no compression, so
transfer sizes below are computed, not served).

**Lighthouse 13.5.0, desktop preset** (simulated throttling, headless Chrome 154), demo-only build (the configuration
that will be deployed first). One run per page, so expect a few points of run-to-run variation in Performance.

| Page | Version | Performance | Accessibility | Best Practices | SEO | LCP | TBT | CLS |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `/` | before | 98 | 100 | 100 | 100 | 1,028 ms | 0 ms | 0.000 |
| `/` | after | 94 | 100 | 100 | 100 | 1,652 ms | 0 ms | 0.000 |
| `/about/` | before | 99 | 100 | 100 | 100 | 1,043 ms | 0 ms | 0.000 |
| `/about/` | after | 96 | 100 | 100 | 100 | 1,450 ms | 0 ms | 0.000 |

Targets (Accessibility 100, Best Practices 100, Performance 90+) are met. The cost is LCP: on `/` the LCP
element is the demo banner's paragraph in both versions, and Lighthouse's "element render delay" for it rose from
246 ms to 531 ms (simulated slow CPU). The likely cause is more JavaScript to parse before that paint.

**JavaScript loaded by each page's HTML** (script tags in the exported HTML, gzip level 9 per file, summed):

| Page | Before (raw / gzip) | After (raw / gzip) | Change (gzip) |
|---|---:|---:|---:|
| `/` | 659,160 / 201,531 bytes | 924,717 / 287,721 bytes | +86,190 bytes (+43%) |
| `/about/` | 626,090 / 191,537 bytes | 821,155 / 256,754 bytes | +65,217 bytes (+34%) |
| All JS files in the export | 669,674 / 204,902 bytes | (21 files) / 324,207 bytes | +119,305 bytes |

CSS per page: 4,370 → 11,570 bytes gzipped. Motion's animation features and the toast renderer are loaded after
first paint (not in the table's first-load numbers). Before that change the home page was 302,333 bytes gzipped.

**Tests:** 232 Vitest tests pass (was 176). New tests cover: the gauge (labelled image, no digits, no
`meter`/`aria-valuenow`), the System / Light / Dark switch (default System, remembered, works with storage blocked),
the empty state, the loading skeleton (hidden from screen readers), error icons, the privacy dialog, toasts, axe
on the loading, error, dialog and dark-theme states, the 3:1 contrast of graphics and input borders, and the
Devanagari CSS rule. Contrast: 41 colour pairs per theme (32 text pairs at 4.5:1, 9 graphic pairs at 3:1), all pass in light and dark.

**Browser walkthrough on the production build, 30 of 30 checks pass:** 20 live (real local API, real Groq: about
3 calls), 5 with the API stopped, 5 on the demo-only build. 0 CSP violations other than the deliberate test fetch.

**Screenshots:** `docs/screenshots/before/` and `docs/screenshots/after/` (31 each, same script). Loading, error,
feedback and "server unreachable" states were captured with the API stubbed in the browser by the recorded real
responses (no LLM calls); see `docs/screenshots/README.md`.

**Problems found and fixed during the redesign:**
- **Devanagari font token referred to itself.** The theme token was named `--font-deva`, the same name as
  next/font's variable, so Tailwind emitted `--font-deva: var(--font-deva, ...)`. Hindi text could lose its
  font. Renamed to `--font-devanagari`; a test now guards it. The real-API walkthrough caught it.
- **Utilities overrode the Devanagari line height.** Classes like `text-sm` set their own line height, which beat
  the 1.75 rule in Tailwind's base layer. The rule now sits outside the layers and uses
  `:lang(hi):not(:lang(hi-Latn))`. Measured in the browser afterwards: Devanagari text 1.75 (headings 1.5),
  English and Hinglish 1.43-1.60, the inspected link stays monospace.
- **Exit animations duplicated the result.** While a result faded out, two cards (and two `result-heading` ids)
  were briefly in the page. Exit animations were removed; entrance animations stay.
- **About page scrolled sideways at 360 px.** Grid items kept their tables' minimum width. Fixed with `min-w-0`.
- **The shadcn CLI added an unplanned npm dependency (`cn`).** Removed; a local `cn()` uses the pinned clsx and
  tailwind-merge.
<!-- phase10redesign:end -->

## Android app (Phase 11): local and on-device checks

**Run date:** 2026-10-01
**Where:** local dev machine (same as Phases 8-10), Flutter 3.47.5 / Dart 3.13.4, Gradle 9.3.1,
Android SDK 36, NDK 28.2.13676358. Device: the owner's OPPO CPH2269 (Android 11 / API 30,
720 x 1600 px at 320 dpi = 360 x 800 dp), over USB with `adb reverse tcp:7860 tcp:7860`. The API ran
locally with the real Groq/Gemini keys and Supabase configured. Debug build only: no release APK
has been built yet (needs the owner's signing key).

**Automated checks (`cd mobile`):** `flutter analyze`: no issues. `flutter test`: 103 tests in 8
files, all passing. They include WCAG AA contrast for every risk colour in both themes (risk text
on its tint, on the card and on the panel background >= 4.5:1; gauge colour on its tint >= 3:1),
and a 360 dp / Hindi / dark / 1.3x-text render with no overflow.

**On-device walkthrough (debug APK, real API):**

| Check | Result |
|---|---|
| Launch, `/health` through `adb reverse` | No server banner (live). Dark theme followed the system setting. |
| English KYC sample (typed text, 137 characters) | scam / high, 3 warning signs, Groq explanation; link shown as `hxxp://sbi-kyc-verify[.]tk/update`, not tappable. |
| Text shared while the app was open (Hinglish electricity cut-off) | Opened a new result directly, labelled "Shared from another app: text". scam / high. Explanation in Hinglish; the 5 warning signs came back in English (the known Phase 9 follow-up). One Back press returned to Home. |
| Text shared with the app stopped (Hindi KYC, 100 characters) | Result on screen within 8 s of the share, including the debug cold start (polled every 2 s). scam / high, Hindi warning signs and explanation with the Devanagari line height. |
| Screenshot via the system photo picker (Hindi KYC sample, 26,590 bytes) | scam / medium, Hindi warning signs and explanation. API time 5,381 ms (OCR 3,966.5 ms, explainer 1,342.9 ms). The picker's cache copy was deleted after reading. |
| Hindi interface | App bar, verdict, labels and samples in Hindi; content unchanged. |
| Screenshot share via `adb` (`content://media/...`) | "The shared item couldn't be read". The log shows `SecurityException ... has no access`: `adb shell` can't grant read access to another app's media item. A test-harness limit, not an app bug; a real app's share grants access. **Not yet checked: a real share from WhatsApp / Gallery** (YOU DO). |

**Other measurements:**
- Text analysis on the API: 1,336.7 ms and 1,393.8 ms (two requests).
- API startup this run: 67.3 s (`startup_complete`), longer than the 21.8 s in Phase 9. The cause
  was not investigated.
- First Android build: 569 s for `assembleDebug`, with Gradle and its dependencies downloaded
  first. Debug APK: 171,746,055 bytes (debug builds include the JIT runtime; the release size is not
  measured yet).
- The API log for the session had no message text, links or IPs (the only `http://` line is
  Uvicorn's own startup line).

**Problems found on the phone and fixed (each now has a regression test):**
- App name cut off in the app bar at 360 dp ("Scam Message Chec..."): now scales to fit.
- The "Explanation written by an AI model (Groq)" note was cut off (a Material `Chip` doesn't wrap):
  replaced by a pill that wraps.
- Letter spacing on small Hindi headings split Devanagari conjuncts ("न ती जा"): off for Hindi.
- The gauge's Low / High labels touched the ends of the arc: more space below the arc.
- A failed image share was labelled "Shared from another app: text": failed shares have no label now.
- **"Can't reach the analysis server" stayed on screen while checks succeeded.** On a debug cold
  start, the app's 4 s `/health` timeout ran out although the API answered in 0.6 ms. Any successful
  API response now marks the server reachable. The test was confirmed to fail without the fix.
- image_picker's empty cache folder was left behind; it is now removed too.

**Found by tests before the device run (fixed):** two RenderFlex overflows at phone width
(screenshot buttons; link panel header in Hindi at 1.3x text) and hidden ink effects inside tinted panels.

**Seen on the phone, not an app issue (Phase 12):** a Hindi warning sign read
"संदेहास्पद लिंक (<URL>)". The explainer repeated the API's link-masking placeholder.
