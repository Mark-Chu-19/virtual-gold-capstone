# Financial data sources: what we can freely use (F32 / TODO 14a)

**Owner:** Karina · **Status:** research complete, recommendation ready for team review

Answers the question TODO.md item 32 and the Sep 18 agenda's item 4 pose: what is freely usable, what license does it carry, and which set has answers we can actually score against.

## Public source data (the "public" layer of the vertical scenario)

| Source | What it gives us | License / access | Notes |
|---|---|---|---|
| SEC EDGAR | Real 10-K, 10-Q, 8-K filings, any public company | Public domain, no license, government publication | Free API, but requires a descriptive User-Agent header with a real contact email or it blocks the request; unofficial rate limit around 10 req/s. Already working, see `src/synthetic_data/fetch_public_data.py`. |
| Yahoo Finance (via `yfinance`) | Daily price history, any ticker | No official license, unofficial/undocumented endpoint | Not sanctioned by Yahoo for redistribution, tolerated for research use, not for a commercial product. Fine for this capstone. |
| Alpha Vantage | Daily price history, any ticker | Free tier, documented terms | Cleaner licensing story than Yahoo if that ever matters, but needs a free API key and is rate-limited (5 calls/min, 500/day). We used yfinance since it needs no signup; switch here if Yahoo ever becomes a blocker. |

## Finance QA benchmarks (the "accuracy_benchmark" batch, scorable ground truth)

| Dataset | License | Ground truth | Size / content | Fit |
|---|---|---|---|---|
| [FinanceBench](https://huggingface.co/datasets/PatronusAI/financebench) | CC BY-NC 4.0 (non-commercial) | Yes, gold answer plus justification plus evidence citation | 150 examples, built from real 10-K/10-Q/8-K filings (3M, Adobe, Amazon, and others) | Good content fit, real filing-grounded questions, but the non-commercial license is a real constraint if any of this ever reaches Virtual Gold's production system after the capstone, not just the class deliverable. |
| [FinQA](https://github.com/czyssrs/FinQA) | MIT | Yes, gold reasoning program and gold execution result, not just a bare answer | Numerical reasoning over financial report tables and text | **Recommended.** Fully permissive license, no commercial restriction at all, and the ground truth is more rigorous than a plain answer string, we can score both the final number and whether the reasoning steps hold up. |
| [TAT-QA](https://github.com/NExTplusplus/TAT-QA) | CC BY 4.0 (attribution required) | Yes, test-set ground truth was released in a 2024 update, held back before that | 16,552 questions over 2,757 hybrid table-plus-text contexts from real financial reports | Permissive and large, viable second choice if FinQA's table format doesn't fit our harness cleanly. |

## Recommendation

Use **FinQA** as the accuracy_benchmark source. MIT license means zero licensing risk for the team or the client, and its reasoning-program ground truth lets us score more than just "did the model get the number right", we can check whether it reasoned correctly. Pull a small labeled sample (not the full set) and format it into the `accuracy_benchmark` batch defined in `docs/research/synthetic-data-schema-en.md`, `ground_truth_answer` filled in from FinQA's gold execution result.

Keep FinanceBench in reserve: if the team ever wants filing-grounded questions with human-written justifications specifically (closer in style to the vertical trading scenario than FinQA's table-heavy questions), it's usable for the class deliverable, just flag the non-commercial license before it goes anywhere near a client handoff.

## One thing for the team to weigh in on

FinanceBench's CC BY-NC 4.0 license is fine for coursework but would need to be swapped out (for FinQA or TAT-QA) if any evaluation code or data built on it is expected to carry forward into something Virtual Gold uses commercially. Worth a one-line mention in the client email so this isn't a surprise later.
