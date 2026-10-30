"""
Pipeline orchestration for privacy redaction:
- Experiment A: Rules + Presidio baseline
- Experiment B: Baseline + Model candidate detection (Union)
- Experiment C: Union + Contextual private/public assessment (Two-call pipeline)
- Replacement with reversible placeholders
- Restoration with unissued token checking
- Degraded fallback path
"""

import json
import re
from typing import Dict, Any, List, Tuple, Optional
from detectors import run_baseline_detection, merge_and_deduplicate_spans
from model_client import ModelClient

DETECTION_SYSTEM_PROMPT = """You are a sensitive information detector for an enterprise privacy redaction service.
Your task is to identify all potentially sensitive, personal, or confidential spans of text in the provided document.
Look for:
- Personal Identifiable Information (individual names, personal email addresses, personal phone numbers, home addresses)
- Financial and account identifiers (bank accounts, credit cards, SSN, passport numbers)
- Confidential business statements or facts (merger negotiations, unannounced facility closures, executive compensation numbers, proprietary project secrets, financial liabilities)
- Security credentials (passwords, PINs, secret keys, auth tokens)
Do NOT include published corporate contact numbers (e.g. 1-800 toll-free lines), public corporate support emails, or publicly known facts.
Return a valid JSON object matching this exact schema:
{
  "candidates": [
    {
      "text": "exact substring from document",
      "category": "PERSON | EMAIL | PHONE | IDENTIFIER | CREDENTIAL | FACT | ADDRESS | AMOUNT",
      "reason": "brief explanation"
    }
  ]
}
Output valid JSON only. Do not wrap in markdown or code blocks."""

ASSESSMENT_SYSTEM_PROMPT = """You are a contextual privacy classifier for an enterprise privacy redaction system.
You are given a document and a list of candidate spans flagged as potentially sensitive.
For each candidate span, evaluate its context in the document and classify whether it is:
- "PRIVATE": personal PII, private mobile phone, confidential business secret, internal financial target, credentials. Must be redacted.
- "PUBLIC": published company contact (e.g. toll-free hotline, corporate switchboard), public department email, public company name, or public fact. Safe to retain.

For each candidate, output:
- "candidate_id": integer ID matching the candidate list
- "verdict": "PRIVATE" or "PUBLIC"
- "confidence": float between 0.50 and 1.00 indicating your confidence in the verdict (1.0 = absolute certainty)
- "reasoning": one concise sentence explaining why this candidate is private or public in this context.

Return valid JSON matching this exact schema:
{
  "assessments": [
    {
      "candidate_id": 0,
      "verdict": "PRIVATE",
      "confidence": 0.95,
      "reasoning": "..."
    }
  ]
}
Output valid JSON only. Do not wrap in markdown or code blocks."""

# Sensitivity Tier Thresholds (Provisional policy frozen on Dev data)
# Lower threshold for higher potential harm
TIER_THRESHOLDS = {
    "HIGH": 0.30,    # SSN, IDENTIFIER, CREDENTIAL, FACT
    "MEDIUM": 0.50,  # PERSON, PHONE, EMAIL, ADDRESS
    "LOW": 0.70      # AMOUNT, DATE, ORG, etc.
}

CATEGORY_TO_TIER = {
    "IDENTIFIER": "HIGH",
    "SSN": "HIGH",
    "CREDENTIAL": "HIGH",
    "FACT": "HIGH",
    "PERSON": "MEDIUM",
    "PHONE": "MEDIUM",
    "EMAIL": "MEDIUM",
    "ADDRESS": "MEDIUM",
    "AMOUNT": "LOW",
    "DATE": "LOW",
    "ORG": "LOW"
}

def get_tier_for_category(category: str) -> str:
    cat = category.upper()
    for key, tier in CATEGORY_TO_TIER.items():
        if key in cat:
            return tier
    return "MEDIUM"

def parse_json_safely(raw_text: Optional[str]) -> Optional[Dict[str, Any]]:
    if not raw_text:
        return None
    cleaned = raw_text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()
    try:
        return json.loads(cleaned)
    except Exception:
        # Try finding outermost { ... }
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(cleaned[start:end+1])
            except Exception:
                pass
        return None

def align_model_candidates(candidates_raw: List[Dict[str, Any]], doc_text: str) -> Tuple[List[Dict[str, Any]], int, int]:
    """
    Validates candidates from model output against doc_text:
    - Finds exact offset ranges for candidate['text']
    - Rejects hallucinated strings that do not exist in doc_text
    Returns: (valid_spans, valid_count, discarded_count)
    """
    valid_spans = []
    discarded = 0
    
    for c in candidates_raw:
        cand_text = c.get("text", "")
        if not cand_text or not isinstance(cand_text, str):
            discarded += 1
            continue
        
        # Search in doc_text
        idx = doc_text.find(cand_text)
        if idx == -1:
            # Substring does not exist in document
            discarded += 1
            continue
        
        category = c.get("category", "SENSITIVE").upper()
        # Find all occurrences and add them or first occurrence
        occ_start = idx
        while occ_start != -1:
            occ_end = occ_start + len(cand_text)
            valid_spans.append({
                "start": occ_start,
                "end": occ_end,
                "text": cand_text,
                "category": category,
                "detector": "model_detection",
                "reason": c.get("reason", "")
            })
            occ_start = doc_text.find(cand_text, occ_end)

    valid_spans = merge_and_deduplicate_spans(valid_spans, doc_text)
    return valid_spans, len(valid_spans), discarded

def apply_redaction(doc_text: str, spans_to_redact: List[Dict[str, Any]]) -> Tuple[str, Dict[str, str]]:
    """
    Replaces spans with deterministic placeholders like [PHONE_1], [PERSON_1].
    Returns (redacted_text, placeholder_map).
    """
    sorted_spans = sorted(spans_to_redact, key=lambda x: x["start"])
    placeholder_map = {}
    category_counters = {}
    
    # Build replacements in reverse order of text offset to preserve indices
    reverse_spans = sorted(sorted_spans, key=lambda x: x["start"], reverse=True)
    redacted = doc_text
    
    # Pre-assign tokens in forward order
    span_tokens = []
    for s in sorted_spans:
        cat = s.get("category", "REDACTED").upper()
        # simplify category tag
        tag = "DATA"
        for known in ["PERSON", "PHONE", "EMAIL", "IDENTIFIER", "CREDENTIAL", "FACT", "ADDRESS", "AMOUNT", "SSN"]:
            if known in cat:
                tag = known
                break
        count = category_counters.get(tag, 0) + 1
        category_counters[tag] = count
        token = f"[{tag}_{count}]"
        span_tokens.append((s, token))
        placeholder_map[token] = doc_text[s["start"]:s["end"]]

    # Replace from end to beginning
    for s, token in reversed(span_tokens):
        start, end = s["start"], s["end"]
        redacted = redacted[:start] + token + redacted[end:]

    return redacted, placeholder_map

def restore_text(redacted_text: str, placeholder_map: Dict[str, str]) -> Tuple[str, List[str]]:
    """
    Restores text using stored mapping.
    Flags any unissued/unknown placeholders (e.g. [PHONE_99]).
    """
    restored = redacted_text
    for token, orig in placeholder_map.items():
        restored = restored.replace(token, orig)
    
    # Check for remaining unknown tokens
    token_pattern = re.compile(r'\[[A-Z_]+_\d+\]')
    remaining = token_pattern.findall(restored)
    flagged_unissued = [t for t in remaining if t not in placeholder_map]
    
    return restored, flagged_unissued

def run_experiment_pipeline(
    doc: Dict[str, Any],
    client: ModelClient,
    model: str,
    stage: str = "C" # "A", "B", or "C"
) -> Dict[str, Any]:
    """
    Runs redaction pipeline for a single document.
    Returns full trace including intermediate candidates, timings, costs,
    redacted text, placeholder map, degraded status, and assessments.
    """
    doc_id = doc["id"]
    text = doc["text"]
    task = doc.get("task", "")
    
    trace = {
        "doc_id": doc_id,
        "model": model,
        "stage": stage,
        "degraded": False,
        "degraded_reason": None,
        "stage1_latency_s": 0.0,
        "stage2_latency_s": 0.0,
        "total_latency_s": 0.0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "cost_usd": 0.0,
        "baseline_spans": [],
        "model_detection_spans": [],
        "union_spans": [],
        "assessed_candidates": [],
        "redacted_spans": [],
        "redacted_text": "",
        "placeholder_map": {},
        "raw_stage1_response": None,
        "raw_stage2_response": None,
        "invalid_spans_discarded": 0,
        "failures": []
    }

    # Step 1: Baseline detection (Rules + Presidio)
    baseline_spans = run_baseline_detection(text)
    trace["baseline_spans"] = baseline_spans

    if stage == "A":
        # Pure Baseline
        redacted_spans = baseline_spans
        redacted_text, p_map = apply_redaction(text, redacted_spans)
        trace["redacted_spans"] = redacted_spans
        trace["redacted_text"] = redacted_text
        trace["placeholder_map"] = p_map
        return trace

    # Step 2: Model Detection (Call 1)
    call1_messages = [
        {"role": "system", "content": DETECTION_SYSTEM_PROMPT},
        {"role": "user", "content": f"Task: {task}\n\nDocument text:\n{text}"}
    ]
    call1_res = client.chat_completion(model, call1_messages)
    trace["stage1_latency_s"] = call1_res["latency_s"]
    trace["prompt_tokens"] += call1_res["prompt_tokens"]
    trace["completion_tokens"] += call1_res["completion_tokens"]
    trace["cost_usd"] += call1_res["cost_usd"]
    trace["raw_stage1_response"] = call1_res.get("content")

    if not call1_res["success"]:
        # Fallback to baseline
        trace["degraded"] = True
        trace["degraded_reason"] = f"Stage 1 Call Failed: {call1_res.get('error')}"
        trace["redacted_spans"] = baseline_spans
        redacted_text, p_map = apply_redaction(text, baseline_spans)
        trace["redacted_text"] = redacted_text
        trace["placeholder_map"] = p_map
        trace["failures"].append(trace["degraded_reason"])
        return trace

    parsed_stage1 = parse_json_safely(call1_res.get("content"))
    if not parsed_stage1 or "candidates" not in parsed_stage1:
        trace["degraded"] = True
        trace["degraded_reason"] = "Stage 1 Unparseable JSON output"
        trace["redacted_spans"] = baseline_spans
        redacted_text, p_map = apply_redaction(text, baseline_spans)
        trace["redacted_text"] = redacted_text
        trace["placeholder_map"] = p_map
        trace["failures"].append(trace["degraded_reason"])
        return trace

    model_spans, valid_cnt, discarded_cnt = align_model_candidates(
        parsed_stage1.get("candidates", []), text
    )
    trace["model_detection_spans"] = model_spans
    trace["invalid_spans_discarded"] += discarded_cnt

    # Combine into union
    union_spans = merge_and_deduplicate_spans(baseline_spans + model_spans, text)
    trace["union_spans"] = union_spans

    if stage == "B":
        # Baseline + Model Detection (Mask everything in union)
        redacted_spans = union_spans
        redacted_text, p_map = apply_redaction(text, redacted_spans)
        trace["redacted_spans"] = redacted_spans
        trace["redacted_text"] = redacted_text
        trace["placeholder_map"] = p_map
        trace["total_latency_s"] = trace["stage1_latency_s"]
        return trace

    # Step 3: Contextual Assessment (Call 2)
    if not union_spans:
        # Nothing detected by any detector
        trace["redacted_spans"] = []
        trace["redacted_text"] = text
        trace["placeholder_map"] = {}
        trace["total_latency_s"] = trace["stage1_latency_s"]
        return trace

    candidates_payload = [
        {"candidate_id": i, "text": s["text"], "category": s.get("category", "SENSITIVE")}
        for i, s in enumerate(union_spans)
    ]
    call2_user_content = (
        f"Document:\n{text}\n\n"
        f"Candidates to assess:\n{json.dumps(candidates_payload, indent=2)}"
    )
    call2_messages = [
        {"role": "system", "content": ASSESSMENT_SYSTEM_PROMPT},
        {"role": "user", "content": call2_user_content}
    ]
    call2_res = client.chat_completion(model, call2_messages)
    trace["stage2_latency_s"] = call2_res["latency_s"]
    trace["prompt_tokens"] += call2_res["prompt_tokens"]
    trace["completion_tokens"] += call2_res["completion_tokens"]
    trace["cost_usd"] += call2_res["cost_usd"]
    trace["total_latency_s"] = trace["stage1_latency_s"] + trace["stage2_latency_s"]
    trace["raw_stage2_response"] = call2_res.get("content")

    if not call2_res["success"]:
        # Fallback: mask all union spans conservatively and mark degraded
        trace["degraded"] = True
        trace["degraded_reason"] = f"Stage 2 Call Failed: {call2_res.get('error')}"
        trace["redacted_spans"] = union_spans
        redacted_text, p_map = apply_redaction(text, union_spans)
        trace["redacted_text"] = redacted_text
        trace["placeholder_map"] = p_map
        trace["failures"].append(trace["degraded_reason"])
        return trace

    parsed_stage2 = parse_json_safely(call2_res.get("content"))
    if not parsed_stage2 or "assessments" not in parsed_stage2:
        trace["degraded"] = True
        trace["degraded_reason"] = "Stage 2 Unparseable JSON output"
        trace["redacted_spans"] = union_spans
        redacted_text, p_map = apply_redaction(text, union_spans)
        trace["redacted_text"] = redacted_text
        trace["placeholder_map"] = p_map
        trace["failures"].append(trace["degraded_reason"])
        return trace

    assessments_by_id = {}
    for a in parsed_stage2.get("assessments", []):
        cid = a.get("candidate_id")
        if cid is not None:
            assessments_by_id[cid] = a

    # Apply decision policy
    spans_to_redact = []
    assessed_records = []
    for i, s in enumerate(union_spans):
        a = assessments_by_id.get(i)
        cat = s.get("category", "MEDIUM")
        tier = get_tier_for_category(cat)
        threshold = TIER_THRESHOLDS.get(tier, 0.50)

        if a:
            verdict = a.get("verdict", "PRIVATE").upper()
            conf = float(a.get("confidence", 0.50))
            # Compute probability private
            p_private = conf if verdict == "PRIVATE" else (1.0 - conf)
            reason = a.get("reasoning", "")
        else:
            # Missing assessment for candidate -> conservative fallback
            verdict = "PRIVATE"
            p_private = 1.0
            reason = "Candidate omitted by assessment model; conservative fallback to PRIVATE"

        should_redact = (p_private >= threshold)
        if should_redact:
            spans_to_redact.append(s)

        assessed_records.append({
            "candidate_id": i,
            "start": s["start"],
            "end": s["end"],
            "text": s["text"],
            "category": cat,
            "tier": tier,
            "threshold": threshold,
            "verdict": verdict,
            "raw_score": p_private,
            "should_redact": should_redact,
            "reasoning": reason
        })

    trace["assessed_candidates"] = assessed_records
    trace["redacted_spans"] = spans_to_redact
    redacted_text, p_map = apply_redaction(text, spans_to_redact)
    trace["redacted_text"] = redacted_text
    trace["placeholder_map"] = p_map

    return trace
