#!/usr/bin/env python3
"""Rules-only reference detector. It sets the floor every model update must beat.

Usage: python baseline_regex.py baseline_v1.jsonl > pred_regex.jsonl
"""
import json, re, sys

PATTERNS = [
    ("EMAIL", r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),
    ("URL", r"https?://\S+"),
    ("IP_ADDRESS", r"\b\d{1,3}(?:\.\d{1,3}){3}\b"),
    ("GOV_ID", r"\b\d{3}-\d{2}-\d{4}\b"),
    ("FIN_ACCOUNT", r"\b[A-Z]{2}\d{2}(?: ?\d{4}){4,7}\b"),                 # IBAN
    ("PHONE", r"(?:\+\d{1,3}[ .-]?)?(?:\(\d{3}\)|\d{2,4})[ .-]\d{3,4}[ .-]\d{3,5}"),
    ("PHONE", r"\b(?:ext\.?|x)\s?\d{3,5}\b"),
    ("CARD", r"(?i)(?<=ending in )\d{4}|(?<=ending )\d{4}"),
    ("AMOUNT", r"(?:[$€£]|EUR |USD |人民币 ?)\s?[\d,.]+(?:\s?(?:[KMB]|million|billion|万元))?(?:/\w+)?"),
    ("AMOUNT", r"\b\d+(?:\.\d+)?%"),
    ("ID_NUMBER", r"\b[A-Z]{1,5}-?\d{4,}(?:-\d+)*\b"),
    ("ID_NUMBER", r"\b\d{6,}\b"),
]
COMPILED = [(t, re.compile(p)) for t, p in PATTERNS]

def detect(text):
    spans = []
    for t, rx in COMPILED:
        for m in rx.finditer(text):
            spans.append({"start": m.start(), "end": m.end(), "type": t, "score": 1.0})
    return spans

if __name__ == "__main__":
    for line in open(sys.argv[1], encoding="utf-8"):
        rec = json.loads(line)
        print(json.dumps({"id": rec["id"], "spans": detect(rec["text"])}))
