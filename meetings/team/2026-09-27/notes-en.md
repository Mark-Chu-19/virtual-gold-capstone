# Sep 27 team alignment — notes

**When:** Sunday 2026-09-27, 22:00 · last session before the client meeting
**Present:** (to fill in)
**Agenda:** [`agenda-en.html`](agenda-en.html) · the two items moved out are in [`deferred-en.md`](deferred-en.md)

Four items: three settled, item 4 not adopted and carried forward.

---

## 1. Category list — settled

**Take the five tiers from Yudi's document; do not start a separate list.** Two formatting changes only:

**(a) Split each tier row into single ids**, because a labeller can only put one value on one span.

| Yudi's tier | Split into |
|---|---|
| High (personal) | `government_id` `credential` `financial_account` `medical` |
| High (business) | `business_confidential` (kept as one) |
| Medium | `person_private` `contact_personal` |
| Low | `location` `date_time` `org` `demographic` |
| Public | `person_public` `contact_public` |

**(b) Add a "can the model decide this one?" column** (Zhexuan's contribution). This is not the same as a low threshold: Yudi's High is a bar of 0.2, so health information the model is only 0.1 sure about still goes out as-is; marking it "model cannot decide" stops it regardless of score. **Item 4's approach runs on this column.**

**Renamed:** `health` → `medical`. Zhexuan's API contract carries both `regulated:health` (medical information) and `/healthz` (is the service alive), so the word meant two things in one document.

**Two departures from Yudi's text, pending his sign-off:**
- `quantity` was added (amounts, percentages) — his five tiers have no category for numbers
- `org` was flattened to Low — he had "organisation names" at Low and "company names in a public context" at Public; the simplification loses that distinction

**Three things confirmed alongside it:**
- Loose-bar items tighten when they cluster (city + gender + date of birth identifies 87%)
- Classifying amounts is left to the model, not written as a rule
- `confidential_marking` is a marking on the message, not a word in it

**Known gap:** `business_confidential` is the only one of the five regulated categories we cannot detect. **It needs a term list from the client.**

## 2. What gets recorded when labelling — settled

Six items per span:

| Field | Values |
|---|---|
| Position | start and end offsets |
| Type | `phone` / `person` / `company`… |
| Category | an id from the item-1 list |
| **Right answer** | **must mask** / **either way is fine** / **must not mask** |
| Source | executive typed it / body / quoted thread / signature / not sure |
| Entity id | Sarah and Sarah Chen share one |

Plus one field for the whole message: `marked confidential`.

**The right answer takes three values, not two.** The third is necessary — some items break the job if masked (mask the dates and scheduling fails; mask the company name and a lookup fails). Both cases were already flagged in red in Karina's own document; the earlier format simply could not express them.

**Also settled: a quoted thread does not count as "source unclear".** Its source is perfectly clear — the previous message. "Not sure" is reserved for what we genuinely cannot place. Otherwise almost every executive email would be blocked whole, purely for having quoted history.

## 3. What to do when the model is unsure — settled

- Keep **one** bar, not two
- Below the bar, **mask it anyway**, but tag it "not sure"
- Those tags **are the data on how much we over-masked**; no second mechanism needed
- `PENDING_REVIEW` (human review) **stays in the API spec but is switched off in this version**

**Reasoning:** human review exists because masking the wrong thing is expensive. The redact-and-restore argument is that it is cheap. If it is cheap, it does not justify a person's time.

**Effect:** Yudi's "without per-item human review" contribution claim survives, and Zhexuan's mechanism is not discarded — only switched off, so the contract does not change if the client later wants it.

## 4. Once masked, has it still left — not adopted, carried forward

**Outcome: option B is not taken.** The topic is carried to the next meeting.

The agenda recommended B — hold back only the **section** containing the regulated item rather than the whole email — on the grounds that A (hold the whole email) and C (mask and send everything) differ on a legal question while B holds under either answer. The team decided against it.

**Consequence worth noting:** without B, **A and C remain unresolved**. That means:

- How coarse the policy gate should be **cannot be settled until the client answers**
- Until then that part of the architecture cannot be built
- It also changes what we say to the client — we cannot claim the design works whatever they answer, so the question goes back to them as it stands

**Which makes getting an answer more important, not less:** "If an email has health or financial information in it and we replace it with placeholders, can the rest go to the cloud? Or must the whole message stay local?" 

---

## Actions

| # | Item | Owner | Due |
|---|---|---|---|
| 1 | Write the category list up properly, including the gate column | Yudi | (to fill in) |
| 2 | Sign off or correct the `quantity` and `org` changes | Yudi | (to fill in) |
| 3 | Write the labelling guide from the six fields; start on the 100 emails | Karina | (to fill in) |
| 4 | Add the single bar and the "not sure" tag to the API spec; mark `PENDING_REVIEW` disabled | Zhexuan | (to fill in) |
| 5 | Ask the client for the confidential term list | Yudi | client meeting |
| 6 | **Ask the client: once replaced with placeholders, can the rest of the email go to the cloud** — item 4 turns on this | Mark | client meeting |
| 7 | Carry item 4 (policy-gate granularity) to the next meeting | everyone | next meeting |

## Not yet recorded

- Who presents what at the 18:00 client meeting today
- Whether this meeting produced any further actions
