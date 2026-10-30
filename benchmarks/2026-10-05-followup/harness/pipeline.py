"""
Pipeline orchestration for Virtual Gold Privacy Redaction & VPC Model Evaluation:
- Baseline-A: Rules + Presidio baseline (stage="A")
- Baseline-B0: Rules + Presidio + GLiNER zero-shot encoder baseline, 0 LLM calls (stage="B0")
- Stage-B-Union: Baseline (+ optional GLiNER) + Stage 1 LLM candidate union (stage="B")
- Config A: Standard Symmetric 2-Stage LLM pipeline (stage="C")
- Config B: +GLiNER Stage 1 Augmentation + 2-Stage LLM pipeline (use_gliner=True)
- Config C: Single-Pass Merged Prompt (stage="1PASS")
- Config D: Asymmetric Co-Resident Stage 1 Extractor + Stage 2 Policy Verifier (stage2_model!=model)
Implements all release-blocking fixes from Section 2 of VPC_MODEL_EVALUATION_PLAN.md.
"""

import json
import re
import time
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from detectors import (
    run_baseline_detection,
    run_gliner_detection,
    merge_and_deduplicate_spans,
    normalize_category,
    get_tier_for_category,
    CANONICAL_CATEGORY_TO_TIER,
)
from model_client import (
    UnifiedModelClient,
    STAGE1_DETECTION_JSON_SCHEMA,
    STAGE2_ASSESSMENT_JSON_SCHEMA,
    SINGLE_PASS_JSON_SCHEMA,
)
from calibration import EmpiricalCalibrator, compute_multi_detector_score

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
CALIBRATION_PROFILE = CONFIG_DIR / "calibration_profile_v1.json"

# Fix #2: Default to Mode C-Raw (uncalibrated raw p_private) so the broken global
# calibration_profile_v1.json ([0.0, 0.2) -> 0.6000) never deadlocks Stage 2 unmasking.
DEFAULT_CALIBRATOR = EmpiricalCalibrator()

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

def load_prompt(filename: str) -> str:
    p = PROMPTS_DIR / filename
    if p.exists():
        return p.read_text().strip()
    raise FileNotFoundError(f"Prompt file not found: {p}")

def get_prompts(version: str = "v2") -> Tuple[str, str]:
    if version == "v2":
        return load_prompt("detection_prompt_v2.txt"), load_prompt("assessment_prompt_v2.txt")
    return load_prompt("detection_prompt.txt"), load_prompt("assessment_prompt.txt")

def get_single_pass_prompt() -> str:
    return load_prompt("single_pass_prompt_v2.txt")

DETECTION_SYSTEM_PROMPT, ASSESSMENT_SYSTEM_PROMPT = get_prompts("v2")

# Sensitivity Tier Thresholds (Reconciled with Midterm Deck Slide 11 consensus)
TIER_THRESHOLDS = {
    "HIGH": 0.20,    # GOV_ID, FIN_ACCOUNT, CARD, CREDENTIAL, ID_NUMBER, HEALTH, CODENAME, FACT
    "MEDIUM": 0.50,  # PERSON, PHONE, EMAIL, ADDRESS, DOB
    "LOW": 0.50      # ORG, LOCATION, AMOUNT, URL, IP_ADDRESS (preserved when isolated, redacted if combined)
}

CATEGORY_TO_TIER = CANONICAL_CATEGORY_TO_TIER

def parse_json_safely(raw_text: Optional[str]) -> Optional[Dict[str, Any]]:
    if not raw_text:
        return None
    cleaned = raw_text.strip()
    # Strip <think>...</think> blocks if any reasoning model emits inline tags
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()
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
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(cleaned[start:end+1])
            except Exception:
                pass
        return None

def align_model_candidates(
    candidates_raw: List[Dict[str, Any]],
    doc_text: str,
    detector_tag: str = "model_detection"
) -> Tuple[List[Dict[str, Any]], int, int]:
    valid_spans = []
    discarded = 0

    for c in candidates_raw:
        cand_text = c.get("text", "")
        if not cand_text or not isinstance(cand_text, str):
            discarded += 1
            continue

        idx = doc_text.find(cand_text)
        if idx == -1:
            discarded += 1
            continue

        category = normalize_category(c.get("category", "PERSON"))
        occ_idx = c.get("occurrence_index")

        matches: List[Tuple[int, int]] = []
        if cand_text.replace(" ", "").isalnum():
            for m in re.finditer(r'\b' + re.escape(cand_text) + r'\b', doc_text):
                matches.append((m.start(), m.end()))
        if not matches:
            occ_start = idx
            while occ_start != -1:
                occ_end = occ_start + len(cand_text)
                matches.append((occ_start, occ_end))
                occ_start = doc_text.find(cand_text, occ_end)

        if isinstance(occ_idx, int) and 1 <= occ_idx <= len(matches):
            selected_matches = [matches[occ_idx - 1]]
        else:
            selected_matches = matches

        for s_off, e_off in selected_matches:
            valid_spans.append({
                "start": s_off,
                "end": e_off,
                "text": doc_text[s_off:e_off],
                "category": category,
                "detector": detector_tag,
                "reason": c.get("reason", ""),
                "confidence": c.get("confidence", 0.90),
                "has_high_tier_rule_hit": False,
            })

    valid_spans = merge_and_deduplicate_spans(valid_spans, doc_text)
    return valid_spans, len(valid_spans), discarded

def apply_redaction(doc_text: str, spans_to_redact: List[Dict[str, Any]]) -> Tuple[str, Dict[str, str]]:
    sorted_spans = sorted(spans_to_redact, key=lambda x: x["start"])
    placeholder_map = {}
    category_counters = {}

    redacted = doc_text
    span_tokens = []
    for s in sorted_spans:
        cat = normalize_category(s.get("category", "REDACTED"))
        tag = cat if cat in CANONICAL_CATEGORY_TO_TIER else "DATA"
        count = category_counters.get(tag, 0) + 1
        category_counters[tag] = count
        token = f"[{tag}_{count}]"
        span_tokens.append((s, token))
        placeholder_map[token] = doc_text[s["start"]:s["end"]]

    for s, token in reversed(span_tokens):
        start, end = s["start"], s["end"]
        redacted = redacted[:start] + token + redacted[end:]

    return redacted, placeholder_map

def restore_text(redacted_text: str, placeholder_map: Dict[str, str]) -> Tuple[str, List[str]]:
    restored = redacted_text
    for token, orig in placeholder_map.items():
        restored = restored.replace(token, orig)

    token_pattern = re.compile(r'\[[A-Z_]+_\d+\]')
    remaining = token_pattern.findall(restored)
    flagged_unissued = [t for t in remaining if t not in placeholder_map]

    return restored, flagged_unissued

def restore_service_response(redacted_text: str, placeholder_map: Dict[str, str]) -> Dict[str, Any]:
    """
    Gateway restoration contract: if unissued, corrupted, or mutated tokens
    are found in the restored text, fail-closed and return status NEEDS_REVIEW.
    """
    restored, flagged_unissued = restore_text(redacted_text, placeholder_map)
    if flagged_unissued:
        return {
            "status": "NEEDS_REVIEW",
            "restored_text": None,
            "flagged_unissued": flagged_unissued,
            "error": "Restoration aborted: unissued or corrupted placeholders detected in response"
        }
    return {
        "status": "READY",
        "restored_text": restored,
        "flagged_unissued": []
    }

def _parse_model_spec(
    model: str,
    stage: str,
    use_gliner: bool,
    gliner_model: str,
    stage2_model: Optional[str]
) -> Tuple[str, Optional[str], str, bool, str]:
    """
    Supports composite model specifiers for CLI convenience:
    - 'baseline_a' -> stage='A'
    - 'baseline_b0_pii' -> stage='B0', use_gliner=True, gliner_model='urchade/gliner_multi_pii-v1'
    - 'baseline_b0_large' -> stage='B0', use_gliner=True, gliner_model='urchade/gliner_large-v2.1'
    - '<model>+gliner' -> Config B with gliner_multi_pii-v1
    - '<model>+gliner_large' -> Config B with gliner_large-v2.1
    - '<model>+1pass' -> Config C (stage='1PASS')
    - '<stage1_model>::<stage2_model>' -> Config D (Asymmetric pair)
    """
    m = model.strip()
    if m.lower() == "baseline_a":
        return m, None, "A", False, gliner_model
    if m.lower() == "baseline_b0_pii":
        return m, None, "B0", True, "urchade/gliner_multi_pii-v1"
    if m.lower() == "baseline_b0_large":
        return m, None, "B0", True, "urchade/gliner_large-v2.1"

    if "+gliner_large" in m:
        m = m.replace("+gliner_large", "")
        use_gliner = True
        gliner_model = "urchade/gliner_large-v2.1"
    elif "+gliner" in m:
        m = m.replace("+gliner", "")
        use_gliner = True
        gliner_model = "urchade/gliner_multi_pii-v1"

    if "+1pass" in m:
        m = m.replace("+1pass", "")
        stage = "1PASS"

    if "::" in m:
        s1_m, s2_m = m.split("::", 1)
        return s1_m.strip(), s2_m.strip(), stage, use_gliner, gliner_model

    return m, (stage2_model or m), stage, use_gliner, gliner_model


def _evaluate_candidate_decisions(
    union_spans: List[Dict[str, Any]],
    assessments_by_id: Dict[int, Dict[str, Any]],
    calibrator: EmpiricalCalibrator,
    tier_thresholds: Dict[str, float],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Implements Section 2.2, 2.3, and 2.4 of VPC_MODEL_EVALUATION_PLAN.md:
    - Deterministic Lock strictly uses s.get('has_high_tier_rule_hit', False) (Fix #4)
    - Omitted candidates fail closed across all tiers (Fix #3a, #3c)
    - Ambiguous scores (0.35 <= p_private <= 0.65) fail closed on HIGH and MEDIUM tiers (Fix #3b)
    - Rule/Context conflicts invoke compute_multi_detector_score with GLiNER/model corroboration (Fix #3)
    """
    identifying_candidates = [
        s for s in union_spans if get_tier_for_category(s.get("category", "")) in ("HIGH", "MEDIUM")
    ]
    has_identifying_context = len(identifying_candidates) > 0
    low_tier_count = sum(1 for s in union_spans if get_tier_for_category(s.get("category", "")) == "LOW")
    is_low_tier_cluster = (low_tier_count >= 3)

    spans_to_redact = []
    assessed_records = []

    for i, s in enumerate(union_spans):
        a = assessments_by_id.get(i)
        cat = normalize_category(s.get("category", "PERSON"))
        s["category"] = cat
        tier = get_tier_for_category(cat)
        threshold = tier_thresholds.get(tier, TIER_THRESHOLDS.get(tier, 0.50))
        detector = s.get("detector", "")

        is_rule_hit = any(d in detector for d in ("regex", "presidio"))
        is_model_det_hit = any(tag in detector for tag in ("model", "gliner"))

        # Fix #4: Deterministic lock applies ONLY when a High-tier non-FACT regex/Presidio rule fired
        is_deterministic_lock = bool(s.get("has_high_tier_rule_hit", False))

        if is_deterministic_lock:
            verdict = "PRIVATE"
            p_private = 1.0
            calibrated_score = None
            score_method = "deterministic_policy_override"
            should_redact = True
            reason = "High-tier deterministic identifier/credential policy lock (bypasses contextual unmasking)"
        elif a is None:
            # Fix #3a: Omitted candidate fails closed across all tiers
            verdict = "OMITTED"
            p_private = 1.0
            calibrated_score = None
            score_method = "omitted_fail_closed_override"
            should_redact = True
            reason = "Candidate omitted by Stage 2 assessment model; fail-closed override"
        else:
            verdict = str(a.get("verdict", "PRIVATE")).upper()
            try:
                conf = float(a.get("confidence", 0.50))
            except (ValueError, TypeError):
                conf = 0.50
            conf = max(0.0, min(1.0, conf))
            p_private = conf if verdict == "PRIVATE" else (1.0 - conf)

            is_ambiguous = (0.35 <= p_private <= 0.65)
            is_conflict = (verdict == "PUBLIC" and is_rule_hit and tier in ("HIGH", "MEDIUM") and not is_ambiguous)

            if is_ambiguous:
                # Fix #3b: Ambiguous score fails closed on HIGH and MEDIUM tiers
                calibrated_score = None
                score_method = "ambiguous_fail_closed_override"
                should_redact = True if tier in ("HIGH", "MEDIUM") else (has_identifying_context or is_low_tier_cluster)
                reason = f"Ambiguous Stage 2 score (p_private={p_private:.2f}); fail-closed override"
            elif is_conflict:
                # Fix #3: Rule/Context conflict uses multi-detector agreement against fixed TIER_THRESHOLDS
                ens_score, ens_method = compute_multi_detector_score(is_rule_hit, is_model_det_hit, verdict, conf)
                calibrated_score = ens_score
                score_method = ens_method
                fixed_thresh = TIER_THRESHOLDS.get(tier, 0.50)
                should_redact = (ens_score >= fixed_thresh)
                reason = f"Rule/context conflict resolved via {ens_method}: score={ens_score:.4f} vs threshold={fixed_thresh}"
            else:
                calibrated_score, score_method = calibrator.predict(p_private)
                reason = a.get("reasoning", "")
                should_redact = (calibrated_score >= threshold)

        # Fix #3c: Low-Tier Isolation Guard excludes OMITTED candidates so omitted candidates stay redacted
        if tier == "LOW" and verdict != "OMITTED":
            if not (has_identifying_context or is_low_tier_cluster):
                should_redact = False
                reason = (reason + "; preserved as isolated low-tier item under combination rule").lstrip("; ")

        s["calibrated_score"] = calibrated_score
        s["score"] = calibrated_score if calibrated_score is not None else p_private
        s["raw_score"] = p_private
        s["score_method"] = score_method
        s["tier"] = tier

        if should_redact:
            spans_to_redact.append(s)

        assessed_records.append({
            "candidate_id": i,
            "start": s["start"],
            "end": s["end"],
            "text": s["text"],
            "category": cat,
            "detector": detector,
            "has_high_tier_rule_hit": is_deterministic_lock,
            "tier": tier,
            "threshold": threshold,
            "verdict": verdict,
            "raw_score": p_private,
            "calibrated_score": calibrated_score,
            "score_method": score_method,
            "should_redact": should_redact,
            "reasoning": reason,
        })

    return spans_to_redact, assessed_records


def run_experiment_pipeline(
    doc: Dict[str, Any],
    client: UnifiedModelClient,
    model: str,
    stage: str = "C",
    prompt_version: str = "v2",
    calibrator: Optional[EmpiricalCalibrator] = None,
    tier_thresholds: Optional[Dict[str, float]] = None,
    use_gliner: bool = False,
    gliner_model: str = "urchade/gliner_multi_pii-v1",
    gliner_threshold: float = 0.35,
    stage2_model: Optional[str] = None,
    use_structured_outputs: bool = True,
) -> Dict[str, Any]:
    if calibrator is None:
        calibrator = DEFAULT_CALIBRATOR
    eff_thresholds = tier_thresholds or TIER_THRESHOLDS

    s1_model, s2_model, eff_stage, eff_use_gliner, eff_gliner_model = _parse_model_spec(
        model, stage, use_gliner, gliner_model, stage2_model
    )

    doc_id = doc["id"]
    text = doc["text"]
    task = doc.get("task", "")

    det_prompt, assess_prompt = get_prompts(prompt_version)

    trace: Dict[str, Any] = {
        "doc_id": doc_id,
        "model": model,
        "stage1_model": s1_model,
        "stage2_model": s2_model,
        "stage": eff_stage,
        "use_gliner": eff_use_gliner,
        "gliner_model": eff_gliner_model if eff_use_gliner else None,
        "prompt_version": prompt_version,
        "degraded": False,
        "operational_failure": False,
        "infrastructure_failure": False,
        "degraded_reason": None,
        "gliner_latency_s": 0.0,
        "stage1_latency_s": 0.0,
        "stage2_latency_s": 0.0,
        "total_latency_s": 0.0,
        "load_duration_s": 0.0,
        "eval_duration_s": 0.0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "cost_usd": 0.0,
        "stage1_telemetry": None,
        "stage2_telemetry": None,
        "baseline_spans": [],
        "gliner_spans": [],
        "model_detection_spans": [],
        "union_spans": [],
        "assessed_candidates": [],
        "redacted_spans": [],
        "redacted_text": "",
        "placeholder_map": {},
        "raw_stage1_response": None,
        "raw_stage2_response": None,
        "invalid_spans_discarded": 0,
        "failures": [],
    }

    t_b0 = time.perf_counter()
    baseline_spans = run_baseline_detection(text)
    trace["baseline_spans"] = baseline_spans
    b_elapsed = time.perf_counter() - t_b0

    if eff_stage == "A":
        redacted_spans = baseline_spans
        redacted_text, p_map = apply_redaction(text, redacted_spans)
        trace["redacted_spans"] = redacted_spans
        trace["redacted_text"] = redacted_text
        trace["placeholder_map"] = p_map
        trace["total_latency_s"] = b_elapsed
        return trace

    gliner_spans: List[Dict[str, Any]] = []
    if eff_use_gliner or eff_stage == "B0":
        t_g0 = time.perf_counter()
        gliner_spans = run_gliner_detection(text, model_id=eff_gliner_model, threshold=gliner_threshold)
        trace["gliner_latency_s"] = time.perf_counter() - t_g0
        trace["gliner_spans"] = gliner_spans

    if eff_stage == "B0":
        union_b0 = merge_and_deduplicate_spans(baseline_spans + gliner_spans, text)
        trace["union_spans"] = union_b0
        redacted_text, p_map = apply_redaction(text, union_b0)
        trace["redacted_spans"] = union_b0
        trace["redacted_text"] = redacted_text
        trace["placeholder_map"] = p_map
        trace["total_latency_s"] = b_elapsed + trace["gliner_latency_s"]
        return trace

    # Config C: Single-Pass Merged Prompt (stage == "1PASS")
    if eff_stage == "1PASS":
        sp_prompt = get_single_pass_prompt()
        pre_spans = merge_and_deduplicate_spans(baseline_spans + gliner_spans, text)
        baseline_payload = [
            {"baseline_id": i, "text": s["text"], "category": s["category"]}
            for i, s in enumerate(pre_spans)
        ]
        sp_user_content = (
            f"Task: {task}\n\n"
            f"Document:\n{text}\n\n"
            f"Baseline candidates:\n{json.dumps(baseline_payload, indent=2)}"
        )
        sp_messages = [
            {"role": "system", "content": sp_prompt},
            {"role": "user", "content": sp_user_content},
        ]
        sp_res = client.chat_completion(
            s1_model,
            sp_messages,
            json_schema=SINGLE_PASS_JSON_SCHEMA if use_structured_outputs else None,
        )
        trace["stage1_latency_s"] = sp_res["latency_s"]
        trace["total_latency_s"] = trace["gliner_latency_s"] + sp_res["latency_s"]
        trace["prompt_tokens"] += sp_res["prompt_tokens"]
        trace["completion_tokens"] += sp_res["completion_tokens"]
        trace["cost_usd"] += sp_res["cost_usd"]
        trace["raw_stage1_response"] = sp_res.get("content")
        trace["stage1_telemetry"] = {
            k: sp_res.get(k)
            for k in (
                "model_requested", "model_returned", "provider", "quantization",
                "finish_reason", "reasoning_tokens", "visible_completion_tokens",
                "attempts", "failure_type"
            )
        }

        if not sp_res["success"]:
            trace["degraded"] = True
            trace["operational_failure"] = (sp_res.get("failure_type") == "operational")
            trace["infrastructure_failure"] = (sp_res.get("failure_type") == "infrastructure")
            trace["degraded_reason"] = f"1-Pass Call Failed: {sp_res.get('error')}"
            trace["redacted_spans"] = pre_spans
            redacted_text, p_map = apply_redaction(text, pre_spans)
            trace["redacted_text"] = redacted_text
            trace["placeholder_map"] = p_map
            trace["failures"].append(trace["degraded_reason"])
            return trace

        parsed_sp = parse_json_safely(sp_res.get("content"))
        if not parsed_sp or ("baseline_assessments" not in parsed_sp and "new_private_spans" not in parsed_sp):
            trace["degraded"] = True
            trace["operational_failure"] = True
            trace["degraded_reason"] = "1-Pass Unparseable JSON output"
            trace["redacted_spans"] = pre_spans
            redacted_text, p_map = apply_redaction(text, pre_spans)
            trace["redacted_text"] = redacted_text
            trace["placeholder_map"] = p_map
            trace["failures"].append(trace["degraded_reason"])
            return trace

        new_spans_raw = parsed_sp.get("new_private_spans", [])
        new_spans, _, discarded_cnt = align_model_candidates(new_spans_raw, text, detector_tag="model_detection_1pass")
        trace["model_detection_spans"] = new_spans
        trace["invalid_spans_discarded"] += discarded_cnt

        union_spans = merge_and_deduplicate_spans(pre_spans + new_spans, text)
        trace["union_spans"] = union_spans

        # Map baseline assessments and new private spans into assessments_by_id
        base_map = {
            a.get("baseline_id"): a
            for a in parsed_sp.get("baseline_assessments", [])
            if a.get("baseline_id") is not None
        }
        assessments_by_id: Dict[int, Dict[str, Any]] = {}
        for i, u_span in enumerate(union_spans):
            # Check if u_span matches a baseline span index
            matched_base_idx = None
            for b_idx, b_span in enumerate(pre_spans):
                if max(u_span["start"], b_span["start"]) < min(u_span["end"], b_span["end"]):
                    matched_base_idx = b_idx
                    break
            if matched_base_idx is not None and matched_base_idx in base_map:
                assessments_by_id[i] = base_map[matched_base_idx]
            elif "model_detection_1pass" in u_span.get("detector", ""):
                assessments_by_id[i] = {
                    "candidate_id": i,
                    "verdict": "PRIVATE",
                    "confidence": float(u_span.get("confidence", 0.90)),
                }

        spans_to_redact, assessed_records = _evaluate_candidate_decisions(
            union_spans, assessments_by_id, calibrator, eff_thresholds
        )
        trace["assessed_candidates"] = assessed_records
        trace["redacted_spans"] = spans_to_redact
        redacted_text, p_map = apply_redaction(text, spans_to_redact)
        trace["redacted_text"] = redacted_text
        trace["placeholder_map"] = p_map
        return trace

    # Standard 2-Stage Pipeline (Config A / Config B / Config D)
    call1_messages = [
        {"role": "system", "content": det_prompt},
        {"role": "user", "content": f"Task: {task}\n\nDocument text:\n{text}"}
    ]
    call1_res = client.chat_completion(
        s1_model,
        call1_messages,
        json_schema=STAGE1_DETECTION_JSON_SCHEMA if use_structured_outputs else None,
    )
    trace["stage1_latency_s"] = call1_res["latency_s"]
    trace["load_duration_s"] += call1_res.get("load_duration_s", 0.0)
    trace["eval_duration_s"] += call1_res.get("eval_duration_s", 0.0)
    trace["prompt_tokens"] += call1_res["prompt_tokens"]
    trace["completion_tokens"] += call1_res["completion_tokens"]
    trace["cost_usd"] += call1_res["cost_usd"]
    trace["raw_stage1_response"] = call1_res.get("content")
    trace["stage1_telemetry"] = {
        k: call1_res.get(k)
        for k in (
            "model_requested", "model_returned", "provider", "quantization",
            "finish_reason", "reasoning_tokens", "visible_completion_tokens",
            "attempts", "failure_type"
        )
    }

    fallback_stage1_spans = merge_and_deduplicate_spans(baseline_spans + gliner_spans, text)

    if not call1_res["success"]:
        trace["degraded"] = True
        trace["operational_failure"] = (call1_res.get("failure_type") == "operational")
        trace["infrastructure_failure"] = (call1_res.get("failure_type") == "infrastructure")
        trace["degraded_reason"] = f"Stage 1 Call Failed: {call1_res.get('error')}"
        trace["redacted_spans"] = fallback_stage1_spans
        redacted_text, p_map = apply_redaction(text, fallback_stage1_spans)
        trace["redacted_text"] = redacted_text
        trace["placeholder_map"] = p_map
        trace["total_latency_s"] = trace["gliner_latency_s"] + trace["stage1_latency_s"]
        trace["failures"].append(trace["degraded_reason"])
        return trace

    parsed_stage1 = parse_json_safely(call1_res.get("content"))
    if not parsed_stage1 or "candidates" not in parsed_stage1:
        trace["degraded"] = True
        trace["operational_failure"] = True
        trace["degraded_reason"] = "Stage 1 Unparseable JSON output"
        trace["redacted_spans"] = fallback_stage1_spans
        redacted_text, p_map = apply_redaction(text, fallback_stage1_spans)
        trace["redacted_text"] = redacted_text
        trace["placeholder_map"] = p_map
        trace["total_latency_s"] = trace["gliner_latency_s"] + trace["stage1_latency_s"]
        trace["failures"].append(trace["degraded_reason"])
        return trace

    model_spans, valid_cnt, discarded_cnt = align_model_candidates(
        parsed_stage1.get("candidates", []), text
    )
    trace["model_detection_spans"] = model_spans
    trace["invalid_spans_discarded"] += discarded_cnt

    union_spans = merge_and_deduplicate_spans(baseline_spans + gliner_spans + model_spans, text)
    trace["union_spans"] = union_spans

    if eff_stage == "B":
        redacted_spans = union_spans
        redacted_text, p_map = apply_redaction(text, redacted_spans)
        trace["redacted_spans"] = redacted_spans
        trace["redacted_text"] = redacted_text
        trace["placeholder_map"] = p_map
        trace["total_latency_s"] = trace["gliner_latency_s"] + trace["stage1_latency_s"]
        return trace

    if not union_spans:
        trace["redacted_spans"] = []
        trace["redacted_text"] = text
        trace["placeholder_map"] = {}
        trace["total_latency_s"] = trace["gliner_latency_s"] + trace["stage1_latency_s"]
        return trace

    candidates_payload = [
        {"candidate_id": i, "text": s["text"], "category": s.get("category", "PERSON")}
        for i, s in enumerate(union_spans)
    ]
    call2_user_content = (
        f"Document:\n{text}\n\n"
        f"Candidates to assess:\n{json.dumps(candidates_payload, indent=2)}"
    )
    call2_messages = [
        {"role": "system", "content": assess_prompt},
        {"role": "user", "content": call2_user_content}
    ]
    call2_res = client.chat_completion(
        s2_model or s1_model,
        call2_messages,
        json_schema=STAGE2_ASSESSMENT_JSON_SCHEMA if use_structured_outputs else None,
    )
    trace["stage2_latency_s"] = call2_res["latency_s"]
    trace["load_duration_s"] += call2_res.get("load_duration_s", 0.0)
    trace["eval_duration_s"] += call2_res.get("eval_duration_s", 0.0)
    trace["prompt_tokens"] += call2_res["prompt_tokens"]
    trace["completion_tokens"] += call2_res["completion_tokens"]
    trace["cost_usd"] += call2_res["cost_usd"]
    trace["total_latency_s"] = trace["gliner_latency_s"] + trace["stage1_latency_s"] + trace["stage2_latency_s"]
    trace["raw_stage2_response"] = call2_res.get("content")
    trace["stage2_telemetry"] = {
        k: call2_res.get(k)
        for k in (
            "model_requested", "model_returned", "provider", "quantization",
            "finish_reason", "reasoning_tokens", "visible_completion_tokens",
            "attempts", "failure_type"
        )
    }

    if not call2_res["success"]:
        trace["degraded"] = True
        trace["operational_failure"] = (call2_res.get("failure_type") == "operational")
        trace["infrastructure_failure"] = (call2_res.get("failure_type") == "infrastructure")
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
        trace["operational_failure"] = True
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

    spans_to_redact, assessed_records = _evaluate_candidate_decisions(
        union_spans, assessments_by_id, calibrator, eff_thresholds
    )

    trace["assessed_candidates"] = assessed_records
    trace["redacted_spans"] = spans_to_redact
    redacted_text, p_map = apply_redaction(text, spans_to_redact)
    trace["redacted_text"] = redacted_text
    trace["placeholder_map"] = p_map

    return trace
