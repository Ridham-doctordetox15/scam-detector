# Label rubric for the synthetic data audit

Used by the blind LLM judge and by the human/assistant reviewers (Phase 3.5). The judge never
sees the original label.

## Definitions

A message is a **scam** if it tries to obtain money, an OTP/PIN/password, personal or bank
details, an app installation or a click, through deception or pressure. Typical forms:

- a fake prize, lottery or KBC win;
- a fake authority (bank, police, customs, courier, electricity board);
- a threat (account blocked, power cut, arrest) combined with a tight deadline;
- an unsolicited job or loan that needs a fee, deposit or "registration";
- a request to "verify" or "update" details or an OTP through a link or phone number.

A message is **safe** if it is informational or personal and asks for none of that: a genuine OTP
or transaction alert (including "do not share this OTP"), a delivery or bill notice without a
payment link or threat, an interview or meeting message, ordinary chat.

## Scam vs spam (project definition)

This project detects **scams and fraud**, not marketing. Three kinds of message are kept apart
in the data (the `subtype` column) even though the binary label has only `scam` and `safe`:

| Kind | Definition | Binary label (target definition) |
|---|---|---|
| **fraud** (scam) | Deceives the reader to get money, an OTP/credentials or a risky action: fake prize or award, fake authority, threats with tight deadlines, "call this number to claim", fees for jobs or loans | `scam` |
| **promo** (spam) | Commercial promotion from an identifiable business with a real offer, even if unsolicited or pushy: telecom recharge and data offers, retailer sales, credit-card or loan offers on the bank's own channel, ringtone or chat-line subscriptions with disclosed prices | `safe` (unwanted, but not a scam) |
| **service** | Transactional or informational notice, or an ordinary personal message that a source mislabelled as spam: genuine OTP, usage or missed-call notice, order confirmation, chat | `safe` |

Practical tests:

- A **fake prize or award** ("you have won a 1 crore prize / a 350 pound award, call 09066... to
  claim") is fraud, even when it also sells something.
- A message that names a real business, states a real offer and has no deception is a **promo**.
- A "you have a new voicemail / missed call, call this number" lure is fraud; a genuine operator
  missed-call notice is service.
- The public spam corpora use "spam" to mean *unsolicited or commercial*, which is broader than
  "scam". Rows from those corpora keep their source label until they are re-labelled with this
  definition; see `results.md` for how much of each source is promo vs fraud.

## Decisions

| Decision | Meaning |
|---|---|
| `keep` | The label is right. |
| `flip` | The label is wrong; change scam to safe or safe to scam. |
| `remove` | Genuinely ambiguous (a careful reader could go either way): drop the row rather than guess. |

## Working rules for hard cases

1. **Asks for an OTP or credentials** (send/verify/enter your OTP, confirm bank details): scam,
   unless it is a genuine OTP delivery ("your OTP is 1234, do not share it").
2. **Link on an unrelated domain** (a bill payment or lottery link on `uidai.gov.in`, a loan offer
   on the wrong bank's domain, look-alike domains): scam.
3. **Threat plus a tight deadline** ("tonight", "within 5 minutes", "today only"): scam.
4. **Threat with a normal deadline or a date, no link, or a link on the sender's own domain**: keep
   the label if it reads like a genuine notice; otherwise `remove` (ambiguous).
5. **Fee-free promotional offers** from a named bank or brand pointing to its own site: safe.
6. **Someone asking about a job or a deposit** (a seeker, not an offer): safe.
7. When in doubt between keeping and flipping, prefer `remove`.

## Reviewing the 30-row sample

The file `review_sample_30.csv` shows `row_id`, `text` and the current label. Fill the
`my_decision` column with `keep`, `flip` or `remove`; use `notes` for anything unclear. The
assistant's decisions are kept in a separate key file and are not revealed until you return the
CSV, so your review is independent.
