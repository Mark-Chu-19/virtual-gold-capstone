"""Generate the demo_w5 batch: about a dozen PII-bearing requests for the
midpoint CLI demo (TODO.md item 14a-i, docs/research/synthetic-data-schema-en.md).

Each record mixes a real, public reference (a filing or price fact for a real
ticker) with a synthetic, confidential trading context that carries planted
PII. Nothing here is a real person, account, or phone number. No network
calls: the "real_filing" reference is just the citation (ticker, filing type,
period), not the filing text itself, which is enough for the CLI demo and for
testing that the gateway redacts the confidential half of the request.

Run: python3 src/synthetic_data/generate_demo_batch.py
Writes: data/synthetic/demo_w5.jsonl
"""
import json
import os

OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "synthetic", "demo_w5.jsonl")

# Clearly fake identities. Never a real person, never reused outside this file.
FAKE_PEOPLE = [
    {"name": "John Meraz", "phone": "555-019-2231", "account": "4471-2209"},
    {"name": "Priya Anand", "phone": "555-042-8871", "account": "5820-3391"},
    {"name": "David Okafor", "phone": "555-071-6640", "account": "3390-7712"},
    {"name": "Wang Liling", "phone": "555-098-4423", "account": "6104-2258"},
    {"name": "Sara Fenwick", "phone": "555-016-9902", "account": "2287-9940"},
    {"name": "Marcus Adeyemi", "phone": "555-063-1187", "account": "7745-1023"},
]

# Real public tickers and filing citations (citation only, not the filing text).
FILINGS = [
    {"ticker": "AAPL", "company": "Apple", "filing": "10-Q", "period": "2026-Q2", "topic": "services-revenue trend"},
    {"ticker": "MSFT", "company": "Microsoft", "filing": "10-K", "period": "FY2026", "topic": "cloud segment margin"},
    {"ticker": "NVDA", "company": "NVIDIA", "filing": "8-K", "period": "2026-09", "topic": "data-center guidance update"},
    {"ticker": "TSLA", "company": "Tesla", "filing": "10-Q", "period": "2026-Q2", "topic": "delivery numbers"},
    {"ticker": "JPM", "company": "JPMorgan", "filing": "10-K", "period": "FY2026", "topic": "net interest income"},
    {"ticker": "AMZN", "company": "Amazon", "filing": "10-Q", "period": "2026-Q2", "topic": "AWS growth rate"},
]

STRATEGIES = [
    "add {ticker} to 8% if it breaks the 200-day",
    "trim {ticker} by half if it closes below the 50-day",
    "hold {ticker} through earnings, stop-loss at 12% down",
    "rotate out of {ticker} into cash if guidance disappoints",
    "scale into {ticker} in three tranches over two weeks",
    "keep {ticker} core position, sell covered calls monthly",
]


def build_record(idx, person, filing, strategy_template):
    strategy = strategy_template.format(ticker=filing["ticker"])
    confidential_text = (
        f"for my current position, contact {person['name']} at {person['phone']} "
        f"or account {person['account']} if you need to confirm, strategy note: {strategy}"
    )
    public_text = (
        f"Based on {filing['company']}'s latest {filing['filing']} ({filing['period']}), "
        f"what does the {filing['topic']} mean"
    )
    query = f"{public_text} {confidential_text}?"

    planted_pii = []
    for value, ptype in (
        (person["name"], "PERSON"),
        (person["phone"], "PHONE"),
        (person["account"], "ACCOUNT"),
    ):
        start = query.index(value)
        planted_pii.append({"type": ptype, "value": value, "start": start, "end": start + len(value)})

    return {
        "id": f"synth-demo-{idx:04d}",
        "batch": "demo_w5",
        "query": query,
        "sensitivity": "confidential",
        "query_split": {"public_text": public_text, "confidential_text": confidential_text},
        "source_type": "real_filing",
        "source_ref": f"{filing['ticker']} {filing['filing']} {filing['period']}",
        "document_text": None,
        "ground_truth_answer": None,
        "planted_pii": planted_pii,
        "expected_redaction": True,
        "notes": "generated for the W7 midpoint CLI demo, TODO 14a-i",
    }


def main():
    records = []
    idx = 1
    for person, filing, strategy in zip(
        (FAKE_PEOPLE * 2)[:12], (FILINGS * 2)[:12], (STRATEGIES * 2)[:12]
    ):
        records.append(build_record(idx, person, filing, strategy))
        idx += 1

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"Wrote {len(records)} records to {os.path.abspath(OUT_PATH)}")


if __name__ == "__main__":
    main()
