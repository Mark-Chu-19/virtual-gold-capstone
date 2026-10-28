# Team meeting, Tuesday 2026-10-27

After the Oct 26 client meeting. Agenda: [`agenda-en.html`](agenda-en.html). Chinese version: [`notes-zh.md`](notes-zh.md). Source for the client meeting: [`notes-gemini-en.pdf`](../../client/2026-10-26/notes-gemini-en.pdf).

## What the client decided on Oct 26

- **Tier table approved** (Aarvin: represents severity correctly, no blockers). Mark said the commercial categories are weak and asked the team for proposals on Slack.
- **Restore design changed.** The client does not generate request IDs. The server generates an identifier when it redacts, returns it with the redacted text, and the client sends it back to restore. Redaction serves the primary user only (Inderpal).
- **Encryption for restore**, one key per conversation and request.
- **Integration with their agent targeted for Monday Nov 2**, then testing.
- **One local model, no switching at runtime** (Aarvin).
- Not answered: Q1 details (dates of birth, deal counterparties, ID numbers, Low items kept alone), Q2 leak targets, Q3 where the service runs, Q4 documents and routing, Q5 placeholder details, Q6 SOW signature.

The Gemini notes have errors (test-set counts, the 86 Low-tier items, whose rules scored 66%, Qwen's size, how the key works). The agenda lists the corrections; use them in the Slack summary.

## Decisions

1. **Restore design.**
   - The server generates the identifier. Zhexuan says the v2 change can be done by Friday Oct 30.
   - Name: **Session Hash ID**.
   - **One key per request**, created by the server (option B).
   - Mode for now: **`mapping`**.
   - Anmol sends the flow diagram to Aarvin as soon as he can.
   - Open: "per request" and the word "Session" in the name point different ways, and a reply that mixes placeholders from earlier turns would need several IDs to restore. Anmol and Zhexuan settle this between them; to be confirmed afterwards.
2. **Integration.** **Monday Nov 2 is a contract test only; full integration moves one week, to Nov 9** (option C).
   - Moving the prototype's prompts into the service, and where the service is hosted, both depend on when the compute resources Anmol requested from CMU arrive.
   - Anmol tests several models once the resources are in and picks the best one.
3. **Tier table.**
   - Yudi opened **PR #11** (tier table only). It was reviewed and squash-merged on 2026-10-28 as `6b1f3c7`, so **main is policy 0.1.3**: the 22 categories and tiers match `tier-table-client-review-en.docx`. 130 tests pass, Presidio included.
   - The 8 detection fixes stay on `feat/privacy-detection-fixes`, to be checked one by one on the 60 development emails before merging. The branch merges cleanly on top of main (137 tests pass).
   - Anmol integrates and tests both: main as the baseline, the branch as the fixed version.
4. **Karina's dataset (PR #9) moves to 0.1.3.** Comment posted on PR #9 on 2026-10-28:
   - 11 `BANK_ACCOUNT` spans become `ACCOUNT_NUMBER`.
   - The employer's bill-to address becomes `ADDRESS_PUBLIC`. Karina also decides whether two other office addresses do.
   - README goes from 0.1.1 to 0.1.3.
   - The 39 `ID_NUMBER` spans and the 1 `URL` span need no change. 0.1.3 has no category for them, and `in_policy: false` / `tier: high` matches what the service does with unknown types.
   - Her review is still not pushed (B74).
5. **Q1 defaults** (dates of birth, counterparties, ID numbers, Low alone) were not discussed. They go back to the client on Nov 2.

## Action items

| Who | What | By |
|---|---|---|
| Zhexuan | Server-generated Session Hash ID in v2, one per request, `mapping` mode | Fri Oct 30 |
| Anmol | Flow diagram to Aarvin; agree per-request vs. session with Zhexuan first | as soon as possible |
| Anmol | CMU resources; then prompts into the service, hosting, model choice | when the resources arrive |
| Zhexuan | Contract test for Nov 2 | Mon Nov 2 |
| Karina | Relabel to 0.1.3 per the PR #9 comment; push the review (B74); score the 60 development emails | |
| Yudi | Check the 8 fixes on the 60 development emails, then a PR for `feat/privacy-detection-fixes` | |
| Mark | Slack summary (with the Gemini corrections) and the revised timeline; Nov 2 questions incl. Q1 | |

## Open

- Per request or per conversation, and whether the name Session Hash ID fits (Anmol, Zhexuan).
- No date for the CMU resources, so Nov 9 is not certain either. The Nov 2 contract test needs no GPU and need not wait for them.
- No date for choosing the model; Aarvin wants one.
- CMU came up in front of the client on Oct 26. The 2026-09-27 rule not to raise the CMU route was not formally revisited.
