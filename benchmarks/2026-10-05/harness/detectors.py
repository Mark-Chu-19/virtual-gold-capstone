"""
Baseline Detectors: Rule-based patterns + Microsoft Presidio pattern recognizers.
Runs purely locally on CPU without downloading external NLP models.
"""

import re
from typing import List, Dict, Any

# Attempt to load Presidio pattern recognizers
PRESIDIO_AVAILABLE = False
try:
    from presidio_analyzer import RecognizerRegistry
    registry = RecognizerRegistry()
    registry.load_predefined_recognizers(nlp_engine=None)
    # Filter out recognizers that depend on spacy NLP engine
    presidio_recognizers = [r for r in registry.recognizers if r.name != "SpacyRecognizer"]
    PRESIDIO_AVAILABLE = True
except Exception as e:
    presidio_recognizers = []
    PRESIDIO_AVAILABLE = False

# Regex patterns for rules
RULE_PATTERNS = [
    ("PHONE", re.compile(r'(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b')),
    ("EMAIL", re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')),
    ("SSN", re.compile(r'\b\d{3}-\d{2}-\d{4}\b')),
    ("ACCOUNT", re.compile(r'\b\d{4}[- ]\d{4}[- ]\d{2,4}\b')),
    ("CREDIT_CARD", re.compile(r'\b(?:\d{4}[- ]){3}\d{4}\b')),
    ("AMOUNT", re.compile(r'\$\d+(?:,\d{3})*(?:\.\d+)?(?:\s*(?:[MBKk]|million|billion|RSUs))?')),
    ("PERSON_PREFIX", re.compile(r'\b(?:Mr\.|Mrs\.|Ms\.|Dr\.)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b')),
    ("HEADER_SENDER", re.compile(r'From:\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\s+<')),
    ("HEADER_RECIPIENT", re.compile(r'To:\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\s+<')),
]

def run_baseline_detection(text: str) -> List[Dict[str, Any]]:
    """
    Runs combined Rules + Presidio pattern recognizers.
    Returns list of candidate spans with start, end, text, category, detector.
    Resolves overlaps deterministically.
    """
    candidates = []

    # 1. Presidio Pattern Recognizers
    if PRESIDIO_AVAILABLE and presidio_recognizers:
        for r in presidio_recognizers:
            try:
                results = r.analyze(text=text, entities=r.supported_entities)
                for res in results:
                    candidates.append({
                        "start": res.start,
                        "end": res.end,
                        "text": text[res.start:res.end],
                        "category": res.entity_type,
                        "detector": f"presidio_{r.name.lower()}",
                        "raw_score": res.score
                    })
            except Exception:
                pass

    # 2. Rule-based regexes
    for cat, pat in RULE_PATTERNS:
        for m in pat.finditer(text):
            # If group 1 exists (e.g. Header sender or Person Prefix), use group 1 span
            if m.groups() and m.group(1):
                s, e = m.start(1), m.end(1)
            else:
                s, e = m.start(), m.end()
            candidates.append({
                "start": s,
                "end": e,
                "text": text[s:e],
                "category": cat,
                "detector": "regex_rule",
                "raw_score": 0.8
            })

    # Deduplicate and sort
    return merge_and_deduplicate_spans(candidates, text)

def merge_and_deduplicate_spans(spans: List[Dict[str, Any]], text: str) -> List[Dict[str, Any]]:
    """
    Deduplicates identical spans and resolves overlapping spans deterministically
    (preferring longer span, or first detector).
    """
    if not spans:
        return []

    # Filter invalid spans
    valid = []
    for s in spans:
        start = s.get("start", 0)
        end = s.get("end", 0)
        if start < 0 or end <= start or end > len(text):
            continue
        # Ensure text matches
        span_text = s.get("text", "")
        if not span_text or text[start:end] != span_text:
            s["text"] = text[start:end]
        valid.append(s)

    # Sort by start asc, end desc (longer first)
    valid.sort(key=lambda x: (x["start"], -x["end"]))

    merged = []
    for s in valid:
        if not merged:
            merged.append(s)
            continue
        prev = merged[-1]
        # Check exact duplicate
        if s["start"] == prev["start"] and s["end"] == prev["end"]:
            continue
        # Check overlap
        if s["start"] < prev["end"]:
            # If current span extends beyond previous, extend previous or keep longer
            if s["end"] > prev["end"]:
                # Merge into longer span
                prev["end"] = s["end"]
                prev["text"] = text[prev["start"]:prev["end"]]
            # else s is completely inside prev, skip it
        else:
            merged.append(s)

    return merged
