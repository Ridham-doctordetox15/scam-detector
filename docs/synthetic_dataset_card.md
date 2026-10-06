---
license: cc-by-4.0
language:
- en
- hi
- ta
- te
- bn
- mr
pretty_name: Indian Scam SMS (synthetic, audited)
size_categories:
- 1K<n<10K
task_categories:
- text-classification
tags:
- scam-detection
- phishing
- sms
- code-mixed
- hinglish
- synthetic
configs:
- config_name: default
  data_files:
  - split: train
    path: data/synthetic_audited.csv
---

# Indian Scam SMS (synthetic, audited)

1,580 short messages that imitate SMS and WhatsApp scams and their **genuine look-alikes** in Indian
English, Hindi (Devanagari), Hinglish and four Roman-script code-mixed styles (Tamil, Telugu, Bengali,
Marathi with English). Every row was written by a large language model and then audited for label noise.
It exists to train and stress-test scam detectors on the *hard negatives* that public datasets lack:
real-looking bank, courier, bill and job messages that are **not** scams.

**This is synthetic data. Do not use it to estimate real-world accuracy.** Evaluate on real messages.

## Fields

| Field | Meaning |
|---|---|
| `row_id` | 12-character SHA-1 prefix of the original generated text (stable key for the audit) |
| `text` | The message |
| `label` | `scam` or `safe` after the audit |
| `original_label` | The label the generator was asked for, before the audit |
| `scam_type` | `fake_kyc`, `lottery`, `courier_customs`, `job_offer`, `electricity_bill`, `loan_offer`, `fake_bank_otp`, `unknown` (a row flipped to scam) or `none` |
| `language` | Requested style: `hinglish`, `en`, `hi`, `ta_en`, `te_en`, `bn_en`, `mr_en` |
| `generator` | `provider/model` that wrote the row |
| `topic` | The category the generator was asked to write (for `safe` rows, the genuine counterpart of a scam type, or `everyday`) |
| `audit_action` | `keep`, `flip` (label changed) or `unreviewed` (see below) |

## Composition

- **Labels:** 797 scam, 783 safe.
- **Generators:** `gemini/gemini-3.5-flash-lite` (861 rows); `gemini/gemini-3.7-flash` (19 rows); `groq/openai/gpt-oss-120b` (700 rows).
- **Languages:** `hinglish` 639, `en` 262, `hi` 167, `bn_en` 135, `mr_en` 127, `te_en` 125, `ta_en` 125.
- **Topics (scam / safe):** `courier_customs` 112 / 87, `electricity_bill` 119 / 89, `everyday` 2 / 104, `fake_bank_otp` 114 / 99, `fake_kyc` 110 / 101, `job_offer` 112 / 98, `loan_offer` 115 / 104, `lottery` 113 / 101.
- **Length:** median 137 characters (min 57, max 422).

## How it was made

1. **Generation.** Prompts asked for batches of 10 messages of one *(label, topic, language)*. Scam batches
   cover seven scam types; safe batches ask for the genuine counterpart (for example a real bank OTP
   alert or an electricity-bill reminder) or ordinary everyday messages. Regional code-mixed styles were
   routed to Gemini only, because a pilot showed Groq's model wrote plain English for them. Prompts forbid
   placeholder-looking numbers and require invented phone numbers and domains in scam rows.
   195 batches produced 1,950 messages.
2. **Generator-side filters.** Length outside 15-700 characters, placeholder-looking numbers, script or
   style mismatch (for example Hinglish written in Devanagari) and exact duplicates removed
   296 messages, leaving 1,654.
3. **Label-noise audit.** LLMs often make "genuine" messages read like scams (and the reverse), so every
   row was screened by three automatic signals: a blind judge from the *other* provider (the judge never
   saw the requested label), an out-of-fold TF-IDF classifier that disagreed with the label, and a rule that
   flags "safe" messages combining urgency with a link or phone number. 162 flagged rows and
   100 random unflagged control rows were then read one by one against the written rubric
   (`label_rubric.md`) and marked **keep**, **flip** or **remove** (ambiguous: dropped).
4. **Hard-negative rules.** A safe message must not link a bank, government or retailer domain that does not
   fit the message (for example a loan offer on `uidai.gov.in`) and must not tell the reader to act on an OTP
   (enter, use, verify or keep one ready, or hand it to a courier). These rules were written down after
   review of a 30-row sample and then applied to *every* safe row by a script
   (`safe_rule_violations` in the code repository); 42 further rows were removed or
   flipped that way.
5. **Result.** 304 rows were reviewed by hand or by a rule, 74 were removed and 35
   were flipped (33 safe to scam, 2 scam to safe). The original label of
   every row is kept in `original_label`.

## Quality and known problems

- **Who labelled.** The audit decisions were made by an AI assistant (Claude) following the rubric, not by
  human annotators. The dataset author was shown a 30-row sample without the assistant's decisions, but
  examined only two of those rows closely (most answers were defaults given without close reading) and then
  ruled on the disputed cases. The human check was therefore **partial, not a full blind check**, and
  **no agreement rate is reported**; none should be inferred.
- **Most rows were not read.** 1,350 of 1,580 rows are `unreviewed`: no signal flagged them and
  nobody read them; only the hard-negative rules were applied to them. In the first review pass none of the
  100 random control rows needed a label change, which suggests but does not prove that label noise among the
  unflagged rows is small. That pass predates the hard-negative rules, which later removed
  10 rows the pass had kept. Expect some mislabelled rows.
- **Shortcuts.** Scam rows use invented domains and phone numbers, safe rows use real official domains.
  A model can learn "known brand domain means safe", which fails against real phishing on look-alike
  domains. Language style, topic and sentence templates also correlate with the label.
- **Language quality.** Regional code-mixed text was written by models and not checked by native
  speakers. Marathi, Bengali, Tamil and Telugu rows may be unnatural.
- **Not real traffic.** Real scams are messier, shorter or longer, and change over time.

## Intended use

Training and stress-testing scam or phishing classifiers as a *supplement* to real data, studying
hard negatives, and evaluating label-noise methods. Not for evaluating deployed systems, and not for
producing convincing scams: phone numbers and domains are invented, and nothing here is a template
for real-world fraud.

## License and terms

The dataset is released under **CC BY 4.0**. The messages were generated with third-party model APIs
(Groq-hosted `openai/gpt-oss-120b` and Google Gemini models, see `generator` per row). Those providers'
terms apply to their outputs and may restrict some uses, for example using Gemini outputs to develop
models that compete with Gemini. **CC BY 4.0 does not override those terms; you are responsible for
checking them for your use.** Filter on `generator` if you need to exclude one provider's rows.

## Citation

If you use this dataset, please link the repository and the AI Scam & Phishing Message Detector
project that produced it.
