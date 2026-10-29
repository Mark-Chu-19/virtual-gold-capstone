"""Rule-based detection (`detect_rules`). Privacy Research.

Covers patterns with a fixed shape and what Presidio cannot know:
phone numbers and extensions, email addresses, SSN-shaped IDs, card numbers (Luhn-checked),
money amounts, US postal addresses, values after a label (account, ID, secret), project code
names, the client's term list (project code names, deal names, counterparties), and every
occurrence of the names given in the from / to / cc header fields.
"""
from __future__ import annotations

import re

from ..contracts.components import ContextStore
from ..contracts.types import Candidate, Segment
from .names import clean_person_name, is_role_mailbox, name_parts

_SCALE = r"(?:k|K|m|M|mm|MM|bn|B|thousand|million|billion)"
_NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"

# US postal addresses. Home or office cannot be told from the text, so every match is
# ADDRESS_HOME (Medium) and the model's score decides; a publicly listed office address scores low
# and is kept (the model's own label for it is ADDRESS_PUBLIC, Public tier).
_STATES = ("AL|AK|AZ|AR|CA|CO|CT|DE|DC|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|"
           "NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY")
_SUFFIX = (r"Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Way|Court|Ct|Place|Pl|"
           r"Terrace|Ter|Circle|Cir|Parkway|Pkwy|Highway|Hwy|Square|Sq")
_WORD = r"(?:[A-Z][a-zA-Z.'-]*|\d+(?:st|nd|rd|th))"
_UNIT = r"(?:,?\s*(?:Apt|Apartment|Suite|Ste|Unit|Floor|Fl|#)\.?\s*#?[A-Za-z0-9-]+)?"
_CITY_STATE_ZIP = rf"[A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+){{0,2}},?\s+(?:{_STATES})\s+\d{{5}}(?:-\d{{4}})?\b"
_ADDRESS = (rf"\b\d{{1,6}}(?:\s+{_WORD}){{1,4}}\s+(?:{_SUFFIX})\b\.?{_UNIT}(?:,\s*{_CITY_STATE_ZIP})?"
            rf"|\bP\.?\s?O\.?\s?Box\s+\d+\b(?:,\s*{_CITY_STATE_ZIP})?"
            rf"|\b{_CITY_STATE_ZIP}")
_MONEY = (rf"(?:[$€£¥]\s?(?:{_NUM})(?:\s?{_SCALE}\b)?"
          rf"|\b(?:USD|EUR|GBP|CNY)\s?(?:{_NUM})(?:\s?{_SCALE}\b)?"
          rf"|\b(?:{_NUM})\s?(?:million|billion|thousand)\b(?:\s(?:dollars|euros|pounds))?"
          rf"|\b(?:{_NUM})\s(?:dollars|euros|pounds)\b)")

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("PHONE_PERSONAL", re.compile(r"(?<!\d)(?:\+?1[-. ]?)?\(?\d{3}\)?[-. ]\d{3}[-. ]\d{4}(?!\d)")),
    # Extensions: "ext. 204", "extension 204", or a bare lower-case "x4521" that starts a word.
    # The bare form must not follow a hyphen or bracket, so codes ("US-EN-6403-X501") and user
    # agents ("(X11; Linux") are not taken for extensions.
    ("PHONE_PERSONAL", re.compile(r"(?i:\b(?:ext\.?|extension)\s?\d{2,5}\b)|(?<![^\s,;:])x\d{2,5}\b")),
    ("EMAIL_PERSONAL", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]*\w")),
    ("GOV_ID", re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")),
    # Card numbers start with 2-6 (Mastercard 2-series, Amex 3, Visa 4, Mastercard 5, Discover 6),
    # so order and ticket numbers that pass Luhn by chance are not taken for cards.
    ("CARD_NUMBER", re.compile(r"(?<!\d)[2-6](?:[ -]?\d){12,15}(?!\d)")),
    # AMOUNT is Medium: "$20 lunch" and an unreleased reserve look alike, so the model's
    # contextual score decides.
    # A range ("$400K to $750K") is one amount; a sign belongs to it ("-$1.22M"). Percentages
    # (margins, retention, raises) are business figures of the same kind.
    ("AMOUNT", re.compile(
        rf"-?{_MONEY}(?:\s?(?:to|-|–)\s?-?{_MONEY})?"
        rf"|\b(?:{_NUM})\s?%"
        rf"|(?:人民币|RMB)\s?(?:{_NUM})\s?[万亿]?元?|(?:{_NUM})\s?[万亿]元")),
    ("ADDRESS_HOME", re.compile(_ADDRESS)),
]

# ---- values after a label --------------------------------------------------------------------
# Account, ID and secret values have no fixed shape; the label in front of them ("Account:",
# "Invoice No.", "passcode") says what they are. Each pattern marks the value only (group "v").
_GAP = r"(?:\s*\([A-Za-z]+\))?\s*(?:is\s+|was\s+)?[:#]?\s*"   # "Routing (ABA): ", "account is "
_DIGITS = r"\d[\d \-]{4,30}\d"                                  # "4402 1187 9930", "0091-448217"
_ID_VALUE = r"[A-Z0-9][A-Za-z0-9\u200b]*(?:[-:/][A-Za-z0-9\u200b]+|[ ]\d[\d\u200b]*)*"
_ID_LABEL = (r"(?i:reference|ref|invoice|case|matter|claim|ticket|order|confirmation|booking|"
             r"report|policy|member|patient|mrn|employee|tracking|meeting|store|loan|application)")
VALUE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("ACCOUNT_NUMBER", re.compile(
        rf"\b(?i:account|acct|a/c|routing|aba|clabe)\b(?i:\s+(?:no\.?|number|#))?{_GAP}(?P<v>{_DIGITS})")),
    ("ACCOUNT_NUMBER", re.compile(
        r"\b(?i:account|acct)\b[^\n.]{0,25}?\bending(?:\s+in)?\s+(?P<v>\d{4})\b")),
    ("CARD_NUMBER", re.compile(
        r"\b(?i:card|amex|visa|mastercard|discover)\b[^\n.]{0,25}?\bending(?:\s+in)?\s+(?P<v>\d{4})\b")),
    ("GOV_ID", re.compile(
        r"\b(?:SSN|Social Security(?i:\s+(?:no\.?|number))?|Tax ID|TIN|EIN|ITIN)\b"
        r"(?:\s+(?:on file|is|was))?\s*[:#]?\s*(?P<v>\d[\d \-]{2,20}\d)")),
    ("GOV_ID", re.compile(
        r"(?:\b(?i:driver'?s?\s+licen[cs]e)|\bDL)(?i:\s+(?:no\.?|number|#))?\s*:?\s*"
        r"(?P<v>(?:[A-Z]{2}\s)?[A-Z]{0,2}\d[A-Z0-9\-]{4,})")),
    ("ID_NUMBER", re.compile(
        rf"\b{_ID_LABEL}\b(?i:\s+(?:no\.?|number|id|#))?\s*[:#]?\s*#?(?P<v>{_ID_VALUE})")),
    ("ID_NUMBER", re.compile(rf"\b(?:ID|No\.|Number)\s*[:#]?\s*#?(?P<v>{_ID_VALUE})")),
    ("ID_NUMBER", re.compile(r"(?P<v>#\d[\d-]{3,})")),
    # Prefixed codes with no label: "INV-2026-0917", "ER-88213", "XK4-882-913".
    ("ID_NUMBER", re.compile(r"\b(?P<v>[A-Z][A-Z0-9]{0,5}-\d[A-Z0-9]*(?:-[A-Z0-9]+)*)\b")),
    ("CREDENTIAL", re.compile(
        r"\b(?i:passcode|password|pass code|pin|otp|one-time code|verification code|security code|"
        r"access code|api key|secret key|access key|token)\b\s*(?:is\s+)?:?\s*"
        r"(?P<v>[A-Za-z0-9][A-Za-z0-9_\-]{3,})")),
    # A link that carries a secret in its query string, and keys in the common "xx_live_..." form.
    ("CREDENTIAL", re.compile(
        r"(?P<v>https?://[^\s<>\"']*[?&](?i:token|key|api_?key|pwd|pass(?:word)?|sig|signature|auth|"
        r"code|access_token|secret)=[^\s<>\"']*[^\s<>\"'.,;)])")),
    ("CREDENTIAL", re.compile(r"\b(?P<v>[a-z]{2,6}[-_](?:live|prod|test)[-_][A-Za-z0-9]{12,})\b")),
]
_PERIOD_OR_YEAR = re.compile(r"(?:Q[1-4]|H[12]|FY)\b.*|(?:19|20)\d{2}")


def _value_ok(etype: str, value: str) -> bool:
    """Labelled values must contain a digit (drops "pin the doc", "in order to"). IDs are not a
    fiscal period or a bare year, and need four digits ("COVID-19" is not one), except a short
    mixed code such as a booking reference ("K7QX2M")."""
    if not re.search(r"\d", value):
        return False
    if etype == "ID_NUMBER":
        mixed_code = len(value) >= 5 and "-" not in value and re.search(r"[A-Z]", value)
        return (not _PERIOD_OR_YEAR.fullmatch(value)
                and sum(ch.isdigit() for ch in value) >= (2 if mixed_code else 4))
    return True


TERM_TYPE = "CODENAME"  # High tier in config/policy.yaml

# ---- project code names ----------------------------------------------------------------------
# "Project Kestrel" names a code name; afterwards the bare "Kestrel" is used ("the NDA for
# Kestrel"), which spaCy reads as a person. Both are CODENAME. The client's term list still covers
# names without the prefix ("Harbor Light").
_PROJECT = re.compile(r"\b(?:Project|Operation|Initiative)\s+(?P<name>[A-Z][a-z]{2,})\b")
_NOT_A_NAME = {"Manager", "Management", "Lead", "Team", "Plan", "Update", "Updates", "Status",
               "Review", "Office", "Director", "Kickoff", "Charter", "Owner", "Sponsor", "Scope",
               "Budget", "Timeline", "Overview", "Summary", "Proposal", "Meeting", "Report"}


def _codename_candidates(segments: list[Segment]) -> list[Candidate]:
    names = {m.group("name") for seg in segments for m in _PROJECT.finditer(seg.text)} - _NOT_A_NAME
    if not names:
        return []
    rx = re.compile(r"\b(?:(?:Project|Operation|Initiative)\s+)?(?:"
                    + "|".join(re.escape(n) for n in sorted(names)) + r")\b")
    return [Candidate(field=seg.field, start=m.start(), end=m.end(), type="CODENAME",
                      detectors={"rules"}, hint="project_name")
            for seg in segments for m in rx.finditer(seg.text)]

# ---- names from the header -----------------------------------------------------------------
# The sender's and recipients' names are known from the header, so every place they appear
# (sign-off, greeting, quoted thread) can be found without relying on NER. Presidio misses a
# lone sign-off such as "- Dana" because it has no surrounding sentence. Name rules: names.py.
HEADER_NAME_FIELD = re.compile(r"^email\.(?:from|to\[\d+\]|cc\[\d+\])\.name$")


def header_names(segments: list[Segment]) -> set[str]:
    """Full names and their capitalised parts from the from / to / cc name fields. A name sent
    from a role mailbox (no-reply@, billing@) is a system sender and is skipped."""
    addresses = {s.field: s.text for s in segments if s.field.endswith(".address")}
    names: set[str] = set()
    for seg in segments:
        full = clean_person_name(seg.text) if HEADER_NAME_FIELD.match(seg.field) else None
        if full and is_role_mailbox(addresses.get(seg.field.removesuffix(".name") + ".address")):
            continue
        if full:
            names |= {full} | name_parts(full)
    return names


def _header_name_candidates(segments: list[Segment]) -> list[Candidate]:
    names = header_names(segments)
    if not names:
        return []
    alts = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
    rx = re.compile(rf"(?<!\w)(?:{alts})(?!\w)")  # case-sensitive: names are capitalised
    return [Candidate(field=seg.field, start=m.start(), end=m.end(), type="PERSON",
                      detectors={"rules"}, hint="header_name")
            for seg in segments for m in rx.finditer(seg.text)]


# Toll-free numbers and role mailboxes are business contact points, so they get the Public type
# (kept unless the model is fairly sure); a person's own number or mailbox stays Medium.
_TOLL_FREE = re.compile(r"^(?:\+?1[-. ]?)?\(?8(?:00|33|44|55|66|77|88)\)?[-. ]")


def contact_type(etype: str, text: str) -> str:
    if etype == "PHONE_PERSONAL" and _TOLL_FREE.match(text):
        return "PHONE_PUBLIC"
    if etype == "EMAIL_PERSONAL" and is_role_mailbox(text):
        return "EMAIL_PUBLIC"
    return etype


def luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d = d * 2 - 9 if d * 2 > 9 else d * 2
        total += d
        alt = not alt
    return total % 10 == 0


def _term_pattern(terms: set[str]) -> re.Pattern[str] | None:
    if not terms:
        return None
    alts = "|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True))
    return re.compile(rf"(?<!\w)(?:{alts})(?!\w)", re.IGNORECASE)


def detect_rules(segments: list[Segment], ctx: ContextStore) -> list[Candidate]:
    """Sync, CPU-only, no side effects. Offsets index each segment's original field text."""
    terms = _term_pattern(ctx.term_list)
    out: list[Candidate] = []
    for seg in segments:
        for etype, rx in PATTERNS:
            for m in rx.finditer(seg.text):
                if etype == "CARD_NUMBER" and not luhn_ok(re.sub(r"\D", "", m.group())):
                    continue
                out.append(Candidate(field=seg.field, start=m.start(), end=m.end(),
                                     type=contact_type(etype, m.group()), detectors={"rules"}))
        for etype, rx in VALUE_PATTERNS:
            for m in rx.finditer(seg.text):
                if _value_ok(etype, m.group("v")):
                    out.append(Candidate(field=seg.field, start=m.start("v"), end=m.end("v"),
                                         type=etype, detectors={"rules"}))
        if terms:
            for m in terms.finditer(seg.text):
                out.append(Candidate(field=seg.field, start=m.start(), end=m.end(), type=TERM_TYPE,
                                     detectors={"rules"}, hint="term_list_match"))
    return out + _header_name_candidates(segments) + _codename_candidates(segments)


# ---- confidential markers -------------------------------------------------------------------
# Ready but NOT wired in: raising every span inside a marked paragraph to the High threshold
# needs the decision step to see passage positions, which the 0.4.2 `decide` signature does not
# carry. See privacy/README.md, "Contract requests".
MARKERS = ("strictly confidential", "confidential", "board only", "board-only", "do not forward",
           "don't forward", "not for distribution", "internal only", "privileged",
           "attorney-client", "under NDA", "embargoed")
_MARKER_RE = _term_pattern(set(MARKERS))
_PARA_BREAK = re.compile(r"\n\s*\n")


def marked_passages(segments: list[Segment]) -> list[tuple[str, int, int]]:
    """(field, start, end) of every blank-line-separated paragraph containing a marker."""
    out = []
    for seg in segments:
        start = 0
        for brk in [*_PARA_BREAK.finditer(seg.text), None]:
            end = brk.start() if brk else len(seg.text)
            if _MARKER_RE and _MARKER_RE.search(seg.text, start, end):
                out.append((seg.field, start, end))
            if brk:
                start = brk.end()
    return out
