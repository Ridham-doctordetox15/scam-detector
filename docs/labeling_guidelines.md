# Labeling guidelines: real Indian test set

Goal: 100-200 **real** messages, labelled by hand, used only to *evaluate* the
model (never to train or tune it). The public datasets are almost entirely
English, so this set is the only honest measure of Hinglish and Indian-scam
performance.

## Files

| What | Where |
|---|---|
| Template (copy it) | `docs/real_indian_test_template.csv` |
| Your filled-in CSV | `data/real_indian/messages.csv` (this folder is gitignored, never commit it) |
| Build command | `python -m src.preprocessing.real_indian_test data/real_indian/messages.csv` |

## Columns

| Column | Allowed values |
|---|---|
| `text` | The message, 5-2000 characters. Copy it exactly (typos included), after removing personal information (below). |
| `label` | `scam` or `safe` |
| `scam_type` | For `scam`: `fake_kyc`, `lottery`, `courier_customs`, `job_offer`, `electricity_bill`, `loan_offer`, `fake_bank_otp`, or `other`. For `safe`: leave blank. |
| `language` | `en`, `hi` (Devanagari), `hinglish` (Hindi in Roman letters), `ta_en`, `te_en`, `bn_en`, `mr_en`, `gu_en`, `kn_en`, `ml_en`, `pa_en`, native-script `ta`/`te`/`bn`/`mr`/`gu`/`kn`/`ml`/`pa`, or `other` |
| `channel` | `sms`, `whatsapp` or `email` |
| `collected_from` | Coarse origin, e.g. `own inbox`, `family forward`, `public scam-awareness page`. No names. |
| `notes` | Optional. Not stored by the build script. |

The two rows in the template have `collected_from` = `example`; the script ignores
them, so you can leave them or delete them.

## What to collect

- **Aim for balance:** roughly half scam, half safe (at least 25% of each).
- **Safe messages must be hard negatives too:** genuine bank OTPs and debit alerts,
  real courier tracking updates, actual electricity-bill reminders, HR interview
  messages, and everyday Hinglish chat. If the safe set is only casual chat, the
  test says nothing about scam-lookalikes.
- **Spread the scam types** across the seven categories, and across languages and
  channels. Do not include 20 copies of one template: near-duplicates are removed
  automatically and your count will shrink.
- **Sources you can use:** your own inbox/SMS/WhatsApp spam folder, messages
  friends and family send you to ask "is this a scam?" (with their permission),
  and public scam-awareness pages that quote real messages (RBI, cybercrime.gov.in,
  bank fraud alerts, news reports).

## Deciding the label

- `scam`: the message tries to get money, an OTP/PIN/password, personal data, an app
  installation or a click through deception (fake urgency, fake prize, fake
  authority, unsolicited job or loan).
- `safe`: a legitimate message, including legitimate marketing from a known sender.
- If you are not sure, **leave the message out**. Ambiguous labels hurt the test more
  than a smaller set does.
- Label by what the message *is*, not by whether you personally lost money.

## Removing personal information (do this *before* saving the CSV)

The build script refuses rows where it detects the items marked (auto) and reports the
CSV line number. Names and addresses cannot be detected automatically, so check those
yourself.

| Remove or replace | How |
|---|---|
| **Your own or a friend's name**, address, employer | Replace with a generic one: `Rahul` -> `Amit`, or delete. Scammers' greetings like "Dear Mr. Sharma" become "Dear customer". |
| **Aadhaar** (auto), **PAN** (auto) | Replace the digits/letters with random ones of the same shape. |
| **Bank account / card numbers** (auto) | Replace with random digits of the same length, or `XXXX1234`. |
| **E-mail and UPI addresses** (auto) | Replace with a fake in the same format, e.g. `name@fakebank`. If a scammer's fake address is the whole point of the row, pass `--allow email`. |
| **Real OTPs, tracking IDs, order IDs** | OTPs are masked to `<OTP>` automatically. Replace anything that could identify an account or shipment. A 12-digit tracking/reference number looks like an Aadhaar number to the checker; change a few digits, or pass `--allow aadhaar` if you are sure it is only a tracking ID. |
| **Phone numbers** | Fine to keep. The build step masks them to `<PHONE>` and never stores the raw number. |
| **URLs** | Keep scam URLs (the URL analyzer needs them), but delete query strings with tokens or personal IDs (`?user=...&token=...`). Never click them. |
| **Third parties in chats** (WhatsApp) | Include only the single suspicious message, not surrounding conversation. Get the sender's permission for forwards. |

Do **not** paste screenshots or real chat exports into the CSV. Copy just the message text.

## Checking your work

```
python -m src.preprocessing.real_indian_test data/real_indian/messages.csv
```

It prints every problem with its CSV line number, and warnings such as "marked
hinglish but the text is mostly Devanagari". When it succeeds it writes
`data/processed/real_indian_test.parquet` and a report showing how many rows were
dropped as duplicates of training data.

## Rules for using the set

1. Never train, fine-tune, tune thresholds or pick models on it. Evaluate on it once
   per finished model and record the result in `results.md`.
2. Re-run the build command whenever the train/val/test splits are rebuilt.
3. Do not commit the CSV. Only aggregate results go in the README and `results.md`.
