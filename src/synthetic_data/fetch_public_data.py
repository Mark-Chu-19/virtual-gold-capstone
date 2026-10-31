"""Pull real, public financial data for the vertical scenario's public layer:
SEC EDGAR filings (10-K, 10-Q, 8-K) and recent price history, for the same
tickers used in data/synthetic/demo_w5.jsonl.

This does NOT touch the client's data or anything confidential, everything
here is already public information a government agency (SEC) or a market
data provider publishes for free. It is the real half of the vertical
scenario, the confidential half (positions, strategy notes) stays synthetic
(see generate_demo_batch.py).

Requires internet access. If this is run inside a sandboxed environment with
a restrictive network allowlist, it will fail with a 403 or a connection
error before it does anything, run it from a normal terminal instead.

Install once: pip install requests yfinance beautifulsoup4

Run: python3 src/synthetic_data/fetch_public_data.py
Writes:
  data/real/filings/{TICKER}_{FORM}_{DATE}.txt   (plain-text filing body)
  data/real/filings/index.json                    (what was fetched, for reuse)
  data/real/market/{TICKER}.csv                   (1-year daily price history)
"""
import json
import os
import time

import requests

try:
    import yfinance as yf
except ImportError:
    yf = None

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

# SEC requires a descriptive User-Agent with contact info, or it blocks you.
# Replace the email below with your own before running.
SEC_HEADERS = {"User-Agent": "virtual-gold-capstone research karina@example.edu"}

TICKERS = ["AAPL", "MSFT", "NVDA", "TSLA", "JPM", "AMZN"]
FORM_TYPES = ["10-Q", "10-K", "8-K"]
FILINGS_PER_TICKER = 2  # most recent N filings across the form types above

BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "real")
FILINGS_DIR = os.path.join(BASE_DIR, "filings")
MARKET_DIR = os.path.join(BASE_DIR, "market")


def get_cik(ticker):
    """Map a ticker to its SEC CIK number using the official lookup table."""
    resp = requests.get("https://www.sec.gov/files/company_tickers.json", headers=SEC_HEADERS, timeout=15)
    resp.raise_for_status()
    table = resp.json()
    for row in table.values():
        if row["ticker"].upper() == ticker.upper():
            return str(row["cik_str"]).zfill(10)
    raise ValueError(f"ticker {ticker} not found in SEC's company_tickers.json")


def get_recent_filings(cik, form_types, limit):
    """Return up to `limit` recent filings of the given form types for one CIK."""
    resp = requests.get(f"https://data.sec.gov/submissions/CIK{cik}.json", headers=SEC_HEADERS, timeout=15)
    resp.raise_for_status()
    recent = resp.json()["filings"]["recent"]
    out = []
    for i, form in enumerate(recent["form"]):
        if form in form_types:
            out.append(
                {
                    "form": form,
                    "date": recent["filingDate"][i],
                    "accession": recent["accessionNumber"][i].replace("-", ""),
                    "primary_doc": recent["primaryDocument"][i],
                }
            )
        if len(out) >= limit:
            break
    return out


def fetch_filing_text(cik, filing):
    """Download one filing's primary document and strip it to plain text."""
    cik_int = str(int(cik))  # EDGAR archive paths use the un-padded CIK
    url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{filing['accession']}/{filing['primary_doc']}"
    resp = requests.get(url, headers=SEC_HEADERS, timeout=20)
    resp.raise_for_status()
    if BeautifulSoup is not None and filing["primary_doc"].endswith((".htm", ".html")):
        soup = BeautifulSoup(resp.text, "html.parser")
        # Modern SEC filings are inline XBRL: an <ix:header> block holds every
        # tagged accounting fact, date, and dimension member as raw metadata.
        # It never renders in a browser, but a plain get_text() pulls it in
        # anyway and buries the real narrative under thousands of lines of
        # "us-gaap:...", "P1Y", context IDs, etc. Strip it before extracting.
        for tag in soup.find_all(["ix:header", "ix:hidden", "ix:references", "ix:resources"]):
            tag.decompose()
        for tag in soup.select('[style*="display:none"], [style*="display: none"]'):
            tag.decompose()
        text = soup.get_text(separator="\n")
        # Collapse the excess blank lines HTML-to-text conversion leaves behind.
        text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    else:
        text = resp.text
    return text


def fetch_filings():
    os.makedirs(FILINGS_DIR, exist_ok=True)
    index = []
    for ticker in TICKERS:
        print(f"[{ticker}] looking up CIK...")
        cik = get_cik(ticker)
        filings = get_recent_filings(cik, FORM_TYPES, FILINGS_PER_TICKER)
        for filing in filings:
            print(f"[{ticker}] fetching {filing['form']} filed {filing['date']}...")
            try:
                text = fetch_filing_text(cik, filing)
            except Exception as e:
                print(f"  skipped, {e}")
                continue
            fname = f"{ticker}_{filing['form'].replace('/', '-')}_{filing['date']}.txt"
            with open(os.path.join(FILINGS_DIR, fname), "w", encoding="utf-8") as f:
                f.write(text)
            index.append({"ticker": ticker, "file": fname, **filing})
            time.sleep(0.3)  # stay well under SEC's rate limit (10 req/s)
    with open(os.path.join(FILINGS_DIR, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)
    print(f"Wrote {len(index)} filings to {os.path.abspath(FILINGS_DIR)}")


def fetch_market_data():
    if yf is None:
        print("yfinance not installed, skipping market data (pip install yfinance)")
        return
    os.makedirs(MARKET_DIR, exist_ok=True)
    for ticker in TICKERS:
        print(f"[{ticker}] fetching 1y price history...")
        df = yf.Ticker(ticker).history(period="1y")
        df.to_csv(os.path.join(MARKET_DIR, f"{ticker}.csv"))
    print(f"Wrote market data to {os.path.abspath(MARKET_DIR)}")


if __name__ == "__main__":
    fetch_filings()
    fetch_market_data()
