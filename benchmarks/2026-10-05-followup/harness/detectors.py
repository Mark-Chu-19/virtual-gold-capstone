"""
Baseline Detectors: Rule-based patterns + Microsoft Presidio pattern recognizers + Name Propagation
+ Optional Stage 1 GLiNER Zero-Shot Span Extractor (Config B / Baseline-B0).
"""

import re
from typing import List, Dict, Any, Set, Optional

# Canonical 18 Gold Label Types & Tier Mapping (Section 6.1 of VPC_MODEL_EVALUATION_PLAN.md)
CATEGORY_ALIASES: Dict[str, str] = {
    "HEADER_SENDER": "PERSON",
    "HEADER_RECIPIENT": "PERSON",
    "PERSON_PREFIX": "PERSON",
    "SSN": "GOV_ID",
    "US_SSN": "GOV_ID",
    "UK_NHS": "GOV_ID",
    "ACCOUNT": "FIN_ACCOUNT",
    "BANK": "FIN_ACCOUNT",
    "IBAN_CODE": "FIN_ACCOUNT",
    "US_BANK_NUMBER": "FIN_ACCOUNT",
    "CREDIT_CARD": "CARD",
    "PASSWORD": "CREDENTIAL",
    "API_KEY": "CREDENTIAL",
    "IDENTIFIER": "ID_NUMBER",
    "US_DRIVER_LICENSE": "ID_NUMBER",
    "US_PASSPORT": "ID_NUMBER",
    "US_ITIN": "ID_NUMBER",
    "MEDICAL": "HEALTH",
    "MEDICAL_LICENSE": "ID_NUMBER",
    "CONFIDENTIAL": "FACT",
    "COMPANY": "ORG",
    "ORGANIZATION": "ORG",
    "EMAIL_ADDRESS": "EMAIL",
    "PHONE_NUMBER": "PHONE",
    "MONEY": "AMOUNT",
    "PROJECT_CODENAME": "CODENAME",
    "DATE_OF_BIRTH": "DOB",
}

CANONICAL_CATEGORY_TO_TIER: Dict[str, str] = {
    # Canonical Gold HIGH Tier (7 entity types + 1 clause type = 8 gold types)
    "GOV_ID": "HIGH",
    "FIN_ACCOUNT": "HIGH",
    "CARD": "HIGH",
    "CREDENTIAL": "HIGH",
    "ID_NUMBER": "HIGH",
    "HEALTH": "HIGH",
    "CODENAME": "HIGH",
    "FACT": "HIGH",
    # Canonical Gold MEDIUM Tier (5 gold types)
    "PERSON": "MEDIUM",
    "EMAIL": "MEDIUM",
    "PHONE": "MEDIUM",
    "ADDRESS": "MEDIUM",
    "DOB": "MEDIUM",
    # Canonical Gold LOW Tier (5 gold types + auxiliary context tags)
    "ORG": "LOW",
    "LOCATION": "LOW",
    "AMOUNT": "LOW",
    "URL": "LOW",
    "IP_ADDRESS": "LOW",
    "DATE": "LOW",
    "DATE_TIME": "LOW",
    "QUANTITY": "LOW",
}

def normalize_category(category: str) -> str:
    if not category:
        return "PERSON"
    cat = category.strip().upper().replace(" ", "_").replace("-", "_")
    if cat in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[cat]
    if cat in CANONICAL_CATEGORY_TO_TIER:
        return cat
    for alias, target in sorted(CATEGORY_ALIASES.items(), key=lambda x: len(x[0]), reverse=True):
        if alias in cat:
            return target
    for canon in sorted(CANONICAL_CATEGORY_TO_TIER.keys(), key=len, reverse=True):
        if canon in cat:
            return canon
    return cat

def get_tier_for_category(category: str) -> str:
    norm_cat = normalize_category(category)
    return CANONICAL_CATEGORY_TO_TIER.get(norm_cat, "MEDIUM")

def _category_precedence_rank(category: str) -> int:
    """
    Precedence for span merging (Section 5.3):
    FACT (4) > HIGH-tier entity (3) > MEDIUM-tier entity (2) > LOW-tier (1)
    """
    norm_cat = normalize_category(category)
    if norm_cat == "FACT":
        return 4
    tier = CANONICAL_CATEGORY_TO_TIER.get(norm_cat, "MEDIUM")
    if tier == "HIGH":
        return 3
    if tier == "MEDIUM":
        return 2
    return 1

# Cache for loaded GLiNER models
_GLINER_CACHE: Dict[str, Any] = {}

GLINER_LABEL_MAP: Dict[str, str] = {
    "person": "PERSON",
    "email": "EMAIL",
    "phone number": "PHONE",
    "address": "ADDRESS",
    "date of birth": "DOB",
    "social security number": "GOV_ID",
    "bank account": "FIN_ACCOUNT",
    "credit card": "CARD",
    "password": "CREDENTIAL",
    "id number": "ID_NUMBER",
    "medical condition": "HEALTH",
    "project codename": "CODENAME",
    "organization": "ORG",
    "location": "LOCATION",
    "money amount": "AMOUNT",
    "url": "URL",
    "ip address": "IP_ADDRESS",
}

def run_gliner_detection(
    text: str,
    model_id: str = "urchade/gliner_multi_pii-v1",
    threshold: float = 0.35
) -> List[Dict[str, Any]]:
    """
    Stage 1 GLiNER Encoder Augmentation (Section 5.3):
    Uses 220-word sliding-window chunks with 40-word overlap and remaps character offsets
    to document coordinates. Spans carry detector='gliner_ner' and has_high_tier_rule_hit=False.
    """
    if not text or not text.strip():
        return []
    try:
        from gliner import GLiNER
    except ImportError as e:
        raise RuntimeError(f"GLiNER is not installed in active Python environment: {e}")

    if model_id not in _GLINER_CACHE:
        _GLINER_CACHE[model_id] = GLiNER.from_pretrained(model_id)
    model = _GLINER_CACHE[model_id]

    labels = list(GLINER_LABEL_MAP.keys())
    word_matches = list(re.finditer(r'\S+', text))
    if not word_matches:
        return []

    chunk_words = 220
    overlap_words = 40
    step = max(1, chunk_words - overlap_words)

    raw_spans: List[Dict[str, Any]] = []
    idx = 0
    while idx < len(word_matches):
        end_idx = min(len(word_matches), idx + chunk_words)
        char_start = word_matches[idx].start()
        char_end = word_matches[end_idx - 1].end()
        chunk_text = text[char_start:char_end]

        preds = model.predict_entities(chunk_text, labels=labels, threshold=threshold)
        for p in preds:
            s_off = char_start + int(p["start"])
            e_off = char_start + int(p["end"])
            if 0 <= s_off < e_off <= len(text):
                raw_label = str(p.get("label", "")).lower()
                norm_cat = GLINER_LABEL_MAP.get(raw_label, normalize_category(raw_label))
                span_txt = text[s_off:e_off]
                if norm_cat == "PERSON" and (span_txt in NAME_STOPWORDS or len(span_txt.strip()) < 3):
                    continue
                raw_spans.append({
                    "start": s_off,
                    "end": e_off,
                    "text": span_txt,
                    "category": norm_cat,
                    "detector": "gliner_ner",
                    "raw_score": round(float(p.get("score", threshold)), 4),
                    "has_high_tier_rule_hit": False,
                })
        if end_idx >= len(word_matches):
            break
        idx += step

    return merge_and_deduplicate_spans(raw_spans, text)

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
    ("EMAIL", re.compile(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+')),
    ("URL", re.compile(r'https?://\S+')),
    ("IP_ADDRESS", re.compile(r'\b\d{1,3}(?:\.\d{1,3}){3}\b')),
    ("SSN", re.compile(r'\b\d{3}-\d{2}-\d{4}\b')),
    ("FIN_ACCOUNT", re.compile(r'\b[A-Z]{2}\d{2}(?: ?\d{4}){4,7}\b')),
    ("ACCOUNT", re.compile(r'\b\d{4}[- ]\d{4}[- ]\d{2,4}\b')),
    ("PHONE", re.compile(r'(?:\+\d{1,3}[ .-]?)?(?:\(\d{3}\)|\d{2,4})[ .-]\d{3,4}[ .-]\d{3,5}')),
    ("PHONE", re.compile(r'\b(?:ext\.?|x)\s?\d{3,5}\b')),
    ("CREDIT_CARD", re.compile(r'\b(?:\d{4}[- ]){3}\d{4}\b')),
    ("CARD", re.compile(r'(?i)(?<=ending in )\d{4}|(?<=ending )\d{4}')),
    ("AMOUNT", re.compile(r'(?:[$€£]|EUR |USD |人民币 ?)\s?[\d,.]+(?:\s?(?:[KMB]|million|billion|万元|RSUs))?(?:/\w+)?')),
    ("AMOUNT", re.compile(r'\b\d+(?:\.\d+)?%')),
    ("ID_NUMBER", re.compile(r'\b[A-Z]{1,5}-?\d{4,}(?:-\d+)*\b')),
    ("ID_NUMBER", re.compile(r'\b\d{6,}\b')),
    ("PERSON_PREFIX", re.compile(r'\b(?:Mr\.|Mrs\.|Ms\.|Dr\.)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b')),
    ("HEADER_SENDER", re.compile(r'From:\s+([A-Z][a-z]+,\s+[A-Z][a-z]+(?:\s+[A-Z]\.?)?)\b')),
    ("HEADER_SENDER", re.compile(r'From:\s+([A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+)(?:\s+<|\s*$)')),
    ("HEADER_RECIPIENT", re.compile(r'To:\s+([A-Z][a-z]+,\s+[A-Z][a-z]+(?:\s+[A-Z]\.?)?)\b')),
    ("HEADER_RECIPIENT", re.compile(r'To:\s+([A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+)(?:\s+<|\s*$)')),
    ("ORG", re.compile(r'\b([A-Z][A-Za-z0-9&.-]+(?:[ \t]+[A-Za-z0-9&.-]+)*[ \t]+(?:Company|Corporation|Corp\.?|Inc\.?|LLC|Ltd\.?|Partners|Holdings))\b')),
    # Health & Clinical Indicators
    ("HEALTH", re.compile(r'(?i)\b(?:diagnosed with|diagnosis of|diagnosed as)\s+[^,.\n]+')),
    ("HEALTH", re.compile(r'(?i)\b(?:chemotherapy|radiation therapy|outpatient surgery|surgical rehabilitation)\b')),
    ("HEALTH", re.compile(r'(?i)\b(?:fractured|broken|torn)\s+(?:his|her|my|their)?\s+[a-z]+(?:\s+[a-z]+)?(?:\s*,\s*requiring\s+surgery)?\b')),
    ("HEALTH", re.compile(r'(?i)\b(?:treated for|hospitalized for|admitted for)\s+[^,.\n]+')),
    ("HEALTH", re.compile(r'(?i)\b(?:cardiology|oncology|orthopedic|neurology|psychiatry)\b')),
    ("HEALTH", re.compile(r'(?i)\b(?:stress test|mri scan|ct scan|biopsy|colonoscopy)\b')),
    ("HEALTH", re.compile(r'(?i)\b(?:diabetic|diab[eé]tica|diabetes|hypertension|epilepsy)\b')),
    ("HEALTH", re.compile(r'(?i)Do not eat or drink after midnight before your [^,.\n]+')),
    # Contextual third-party colleague/team mentions
    ("PERSON", re.compile(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+on\s+(?:my|our|the)\s+team\b')),
    ("PERSON", re.compile(r'\b(?:ask|contact|reach out to|talk to|speak with|email|call|check with|loop in)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b')),
    ("PERSON", re.compile(r'\b(?:copied|copying|looping in)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b')),
    ("PERSON", re.compile(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+will\s+(?:cover|handle|lead|manage|send|review|prepare|take)\b')),
    ("PERSON", re.compile(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+has\s+(?:agreed|prepared|sent|confirmed|the|been)\b')),
]

# Filtering wordlists for Name Propagation
SALUTATION_SIGN_OFF_WORDS: Set[str] = {
    'Thanks', 'Thank', 'Best', 'Regards', 'Sincerely', 'Cheers', 'Warmly', 'Yours',
    'Respectfully', 'Faithfully', 'Cordially', 'Morning', 'Afternoon', 'Evening',
    'Hello', 'Hi', 'Hey', 'Dear', 'Mr', 'Mrs', 'Ms', 'Dr', 'Prof', 'Hope', 'Please', 'Good',
    'All', 'Everyone', 'Team'
}

DEPARTMENT_WORDS: Set[str] = {
    'Team', 'Hotline', 'Support', 'Care', 'Escalations', 'Service', 'Services',
    'Intake', 'Admin', 'Helpdesk', 'Desk', 'Operations', 'Department', 'Security',
    'Compliance', 'Legal', 'Billing', 'Payroll', 'Recruiting', 'Talent', 'Sales',
    'Marketing', 'System', 'Systems', 'Notification', 'Notifications', 'Alert',
    'Alerts', 'Info', 'Office', 'Corporate', 'HR', 'Center', 'Board', 'Committee',
    'Management', 'Group', 'Workflow', 'Division'
}

COMPANY_WORDS: Set[str] = {
    'Inc', 'LLC', 'Corp', 'Corporation', 'Ltd', 'Co', 'Technologies', 'Solutions',
    'Partners', 'Capital', 'Holdings', 'Amazon', 'Google', 'Microsoft', 'Apple',
    'Halvorsen', 'Castell', 'Delmar', 'Keane', 'Porter'
}

CALENDAR_STOPWORDS: Set[str] = {
    'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday',
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
    'January', 'February', 'March', 'April', 'June', 'July', 'August', 'September',
    'October', 'November', 'December', 'Q1', 'Q2', 'Q3', 'Q4'
}

NAME_STOPWORDS: Set[str] = SALUTATION_SIGN_OFF_WORDS | DEPARTMENT_WORDS | COMPANY_WORDS | CALENDAR_STOPWORDS | {
    'The', 'This', 'That', 'These', 'Those', 'From', 'To', 'Cc', 'Bcc', 'Subject', 'Date',
    'Sent', 'Mobile', 'Phone', 'Fax', 'Tel', 'Email', 'Mail', 'Message', 'Thread', 'Update',
    'Note', 'Attachment', 'Original', 'Customer'
}

def run_name_propagation(text: str) -> List[Dict[str, Any]]:
    """
    Extracts person names from email headers, salutations, and sign-offs,
    and propagates full names and distinctive name tokens throughout the document.
    """
    full_names = set()
    first_names = set()
    
    # 1. From / To / Cc / Bcc headers (handles inverted names and multi-recipient headers)
    for m in re.finditer(r'(?:From|To|Cc|Bcc):\s*([^\n\r]+)', text):
        raw_header = m.group(1).strip()
        inv_match = re.match(r'^([A-Z][a-z]+),\s+([A-Z][a-z]+(?:\s+[A-Z]\.?)?)(?:\s+<.*>)?$', raw_header)
        if inv_match:
            last, first = inv_match.group(1), inv_match.group(2)
            first_clean = first.split()[0]
            full_names.add(f"{last}, {first}")
            full_names.add(f"{first} {last}")
            if len(first.split()) > 1:
                full_names.add(f"{first_clean} {last}")
            if first_clean not in NAME_STOPWORDS and len(first_clean) >= 3:
                first_names.add(first_clean)
            if last not in NAME_STOPWORDS and len(last) >= 3:
                first_names.add(last)
        else:
            for part in re.split(r'[,;]', raw_header):
                clean_part = part.strip()
                match_disp = re.search(r'^\"?([^<]+?)\"?\s*<', clean_part)
                if match_disp:
                    name_cand = match_disp.group(1).strip('\"\' ')
                    words = name_cand.split()
                    if not any(w in DEPARTMENT_WORDS or w in COMPANY_WORDS for w in words):
                        if 2 <= len(words) <= 3 and all(w[0].isupper() for w in words if w.isalpha()):
                            full_names.add(name_cand)
                            if words[0] not in NAME_STOPWORDS and len(words[0]) >= 3:
                                first_names.add(words[0])
                            if words[-1] not in NAME_STOPWORDS and len(words[-1]) >= 3:
                                first_names.add(words[-1])

    # 2. Quoted From headers
    for m in re.finditer(r'(?:From|wrote):\s*([A-Z][a-z]+(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-z]+)+)', text):
        cand = m.group(1).strip()
        words = cand.split()
        if not any(w in DEPARTMENT_WORDS or w in COMPANY_WORDS for w in words):
            full_names.add(cand)
            if words[0] not in NAME_STOPWORDS and len(words[0]) >= 3:
                first_names.add(words[0])
            if words[-1] not in NAME_STOPWORDS and len(words[-1]) >= 3:
                first_names.add(words[-1])

    # 3. Salutations: Hi [Name], Hello [Name], Dear [Prefix] [Name]
    for m in re.finditer(r'(?:^|\n)(?:Hi|Hello|Hey)\s+([A-Z][a-z]+)\b', text):
        cand = m.group(1).strip()
        if cand not in NAME_STOPWORDS and len(cand) >= 3:
            first_names.add(cand)
            
    for m in re.finditer(r'(?:^|\n)Dear\s+(?:(?:Mr\.|Mrs\.|Ms\.|Dr\.)\s+)?([A-Z][a-z]+)\b', text):
        cand = m.group(1).strip()
        if cand not in NAME_STOPWORDS and len(cand) >= 3:
            first_names.add(cand)

    # 4. Sign-offs: Thanks,\n[Name] or Best regards,\n[Name]
    for m in re.finditer(r'(?:Thanks|Best|Regards|Sincerely|Cheers|Warmly|Yours)[^\n]*\n+([A-Z][a-z]+(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-z]+)?)\b', text):
        cand = m.group(1).strip()
        words = cand.split()
        if not any(w in NAME_STOPWORDS for w in words):
            if len(words) > 1:
                full_names.add(cand)
                first_names.add(words[0])
                first_names.add(words[-1])
            elif len(cand) >= 3:
                first_names.add(cand)

    # 5. Professional Signature Blocks: Name preceding Title / Company / Email
    TITLE_COMPANY_KEYWORDS = {
        'Counsel', 'Attorney', 'Legal', 'Director', 'Manager', 'Officer', 'President',
        'Vice', 'VP', 'Executive', 'Lead', 'Engineer', 'Specialist', 'Consultant',
        'Partner', 'Associate', 'Analyst', 'Coordinator', 'Company', 'Corp', 'Inc', 'LLC'
    }
    for m in re.finditer(r'(?:^|\n)([A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+)\n+(?:[^\n]*(?:' + '|'.join(TITLE_COMPANY_KEYWORDS) + r')|Email\s*[-:])', text):
        cand = m.group(1).strip()
        words = cand.split()
        if not any(w in NAME_STOPWORDS for w in words):
            full_names.add(cand)
            first_clean = words[0]
            last_clean = words[-1]
            if first_clean not in NAME_STOPWORDS and len(first_clean) >= 3:
                first_names.add(first_clean)
            if last_clean not in NAME_STOPWORDS and len(last_clean) >= 3:
                first_names.add(last_clean)

    # 6. Standalone first name immediately preceding full signature line:
    for m in re.finditer(r'(?:^|\n)([A-Z][a-z]{2,15})\n+([A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+)\b', text):
        first_cand = m.group(1).strip()
        full_cand = m.group(2).strip()
        if first_cand not in NAME_STOPWORDS and full_cand.startswith(first_cand):
            first_names.add(first_cand)
            full_names.add(full_cand)
            words = full_cand.split()
            if words[-1] not in NAME_STOPWORDS and len(words[-1]) >= 3:
                first_names.add(words[-1])

    spans = []
    # Match full names in text
    for n in full_names:
        for m in re.finditer(r'\b' + re.escape(n) + r'\b', text):
            spans.append({
                'start': m.start(),
                'end': m.end(),
                'text': text[m.start():m.end()],
                'category': 'PERSON',
                'detector': 'regex_name_propagation',
                'raw_score': 0.85
            })
    # Match single names in text
    for t in first_names:
        for m in re.finditer(r'\b' + re.escape(t) + r'\b', text):
            spans.append({
                'start': m.start(),
                'end': m.end(),
                'text': text[m.start():m.end()],
                'category': 'PERSON',
                'detector': 'regex_name_propagation',
                'raw_score': 0.80
            })

    return spans

def run_baseline_detection(text: str) -> List[Dict[str, Any]]:
    """
    Runs combined Rules + Presidio pattern recognizers + Name Propagation.
    Returns list of candidate spans with start, end, text, category, detector,
    and has_high_tier_rule_hit. Resolves overlaps deterministically.
    """
    candidates = []

    # 1. Presidio Pattern Recognizers
    if PRESIDIO_AVAILABLE and presidio_recognizers:
        for r in presidio_recognizers:
            try:
                results = r.analyze(text=text, entities=r.supported_entities)
                for res in results:
                    norm_cat = normalize_category(res.entity_type)
                    candidates.append({
                        "start": res.start,
                        "end": res.end,
                        "text": text[res.start:res.end],
                        "category": norm_cat,
                        "detector": f"presidio_{r.name.lower()}",
                        "raw_score": res.score,
                        "has_high_tier_rule_hit": (get_tier_for_category(norm_cat) == "HIGH" and norm_cat != "FACT")
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
            cand_text = text[s:e]
            norm_cat = normalize_category(cat)
            if norm_cat == "PERSON" and (cand_text in NAME_STOPWORDS or len(cand_text) < 3):
                continue
            candidates.append({
                "start": s,
                "end": e,
                "text": cand_text,
                "category": norm_cat,
                "detector": "regex_rule",
                "raw_score": 0.8,
                "has_high_tier_rule_hit": (get_tier_for_category(norm_cat) == "HIGH" and norm_cat != "FACT")
            })

    # 3. Name Propagation (headers, salutations, sign-offs)
    name_spans = run_name_propagation(text)
    for ns in name_spans:
        ns["category"] = normalize_category(ns.get("category", "PERSON"))
        ns["has_high_tier_rule_hit"] = False
    candidates.extend(name_spans)

    # Deduplicate and sort
    return merge_and_deduplicate_spans(candidates, text)

def merge_and_deduplicate_spans(spans: List[Dict[str, Any]], text: str) -> List[Dict[str, Any]]:
    """
    Deduplicates identical spans and resolves overlapping spans deterministically:
    - Normalizes categories to the 18 canonical gold types
    - Preserves detector provenance and propagates has_high_tier_rule_hit
    - Applies category precedence (FACT > HIGH > MEDIUM > LOW) when merging
    """
    if not spans:
        return []

    # Filter invalid spans and normalize categories
    valid = []
    for s in spans:
        s_copy = dict(s)
        start = s_copy.get("start", 0)
        end = s_copy.get("end", 0)
        if start < 0 or end <= start or end > len(text):
            continue
        span_text = s_copy.get("text", "")
        if not span_text or text[start:end] != span_text:
            s_copy["text"] = text[start:end]
        norm_cat = normalize_category(s_copy.get("category", "PERSON"))
        s_copy["category"] = norm_cat
        if "has_high_tier_rule_hit" not in s_copy:
            det_str = s_copy.get("detector", "")
            is_rule = any(d in det_str for d in ("regex", "presidio"))
            s_copy["has_high_tier_rule_hit"] = bool(
                is_rule and get_tier_for_category(norm_cat) == "HIGH" and norm_cat != "FACT"
            )
        valid.append(s_copy)

    # Sort by start asc, end desc (longer first), higher category precedence first
    valid.sort(key=lambda x: (x["start"], -x["end"], -_category_precedence_rank(x["category"])))

    merged = []
    def merge_metadata(target: Dict[str, Any], source: Dict[str, Any]):
        d1 = set(filter(None, target.get("detector", "").split(",")))
        d2 = set(filter(None, source.get("detector", "").split(",")))
        union_dets = d1.union(d2)
        if union_dets:
            target["detector"] = ",".join(sorted(union_dets))
        target["has_high_tier_rule_hit"] = bool(
            target.get("has_high_tier_rule_hit", False) or source.get("has_high_tier_rule_hit", False)
        )
        # Upgrade category if source has strictly higher privacy tier precedence
        if _category_precedence_rank(source.get("category", "")) > _category_precedence_rank(target.get("category", "")):
            target["category"] = source["category"]

    for s in valid:
        if not merged:
            merged.append(s)
            continue
        prev = merged[-1]
        # Check exact duplicate
        if s["start"] == prev["start"] and s["end"] == prev["end"]:
            merge_metadata(prev, s)
            continue
        # Check overlap
        if s["start"] < prev["end"]:
            if s["end"] > prev["end"]:
                prev["end"] = s["end"]
                prev["text"] = text[prev["start"]:prev["end"]]
            merge_metadata(prev, s)
        else:
            merged.append(s)

    return merged
