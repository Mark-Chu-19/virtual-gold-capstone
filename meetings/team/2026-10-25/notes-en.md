# Team meeting, Sunday 2026-10-25

Before the Oct 26 client meeting. Agenda: [`agenda-en.html`](agenda-en.html). Chinese version: [`notes-zh.md`](notes-zh.md).

**Attendees:** Mark, Yudi, Zhexuan, Karina. Anmol was absent.

## Decisions

1. **Anmol's VPC report goes to the client unchanged.** Anmol was absent, so nobody rewrites it. The client page states the facts on its own: the runs used hosted open-weight model APIs and the service is not yet deployed in a VPC. Its wording, the 24 local `file://` links and the §7 sentence on the CMU OpenRouter allocation wait for Anmol (TODO B72).
2. **The client reviews Yudi's policy-0.1.3.** 22 categories: `BANK_ACCOUNT` becomes `ACCOUNT_NUMBER`, `ADDRESS_PUBLIC` is new, and the Public threshold rises from 0.5 to 0.8. It is Yudi's proposal; he thinks it is more accurate and wants the client's view. His branch is merged only after the client confirms (B71). Anmol's leak figures were measured under his own 3-tier rules, so the client page says they will be re-run under the confirmed table (B69).
3. **API v2 is shown as Zhexuan's proposal.** He wants the client's view on the two modes and the token format (client page Q5). His PR #10 was reviewed and merged on 2026-10-26 (see below).
4. **Broken links.** The two documents Zhexuan's briefing links to are in PR #10, so they are now on main under `docs/api/`. The repository is private, so the client page names the folder instead of linking.
5. **Karina's dataset (PR #9) stays on policy 0.1.1.** She built it on 0.1.1 on purpose, because 0.1.3 is only a proposal. So it is not out of date and does not wait for Yudi's branch. If the client confirms 0.1.3, she regenerates `service_type` and `tier`.
   - She reports that she has reviewed every row. The PR does not show it yet: the "Karina check" column is empty and all 100 emails still say `gt_status: draft` (B74).
   - Tell the client about the dataset the way her README does.
   - The 86 must-redact spans in the Low tier (67 ORG, 12 CITY, 6 DATE, 1 AGE), dates of birth, deal counterparties and the 39 ID numbers go to the client with the tier table (Q1).
   - The `NON_PERSON_WORDS` fix for mailbox names is for later (B75).
6. **Order tomorrow:** Yudi first, then Anmol, then Karina and Zhexuan.

## After the meeting (2026-10-26)

- **PR #10 (Zhexuan, API v2) approved and squash-merged as `ade699b`.** 128 tests pass, 2 skipped, in a clean environment.
  - Security review: tokens are bound to tenant, type, conversation and key version; one group cannot restore another's tokens; closing a conversation blocks restore in both modes; nothing secret is logged; v2 is off unless `VG_TOKEN_KEYS` is set, and v1 is unchanged.
  - Follow-ups (B73): ordinary bracketed text such as `[VGA]` or `[Item_1]` is rejected as a token, to be fixed before any real-email demo; `/readyz` degrades v1 when Redis is down; the idempotency fingerprint is an unsalted hash; unused format-1 code; a misleading error for oversized purposes.
- **Client page** `meetings/client/2026-10-26/agenda-{en,zh}.html`: progress, detail sections for each workstream, questions Q1–Q6 with answer fields.

## Open

- **Decided 2026-10-26:** Anmol's report §7 names the $50 CMU OpenRouter allocation through the professor, and the 2026-09-27 decision says not to raise the CMU route with the client. Mark skips that sentence when presenting.
- Karina pushes her review into PR #9 (B74). Until then the client page says "an LLM proposed the labels, and a person checks every one".
