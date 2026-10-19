"""Pseudonymisation (`pseudonymize`). Privacy Research.

Same as the 0.4.2 stub, plus one rule: every variant of a header person ("Dana Whitfield",
"Dana", "Whitfield") shares one placeholder, and the mapping restores it to the full name.
Ambiguous parts (a first name two header people share) keep their own placeholder.
"""
from __future__ import annotations

from ..contracts.fields import email_to_dict, iter_fields, set_field
from ..contracts.types import Decision, EmailIn, LabelState, PseudonymResult, SpanOut
from .names import alias_table, clean_person_name


def _ph_type(entity_type: str) -> str:
    return entity_type.split("_")[0]


def _header_people(email: EmailIn) -> list[str]:
    raw = [email.from_.name if email.from_ else None]
    raw += [a.name for a in email.to] + [a.name for a in email.cc]
    return [n for n in (clean_person_name(r) for r in raw) if n]


def pseudonymize(purpose: str, email: EmailIn, decisions: list[Decision],
                 labels: LabelState) -> PseudonymResult:
    fields = iter_fields(purpose, email)
    aliases = alias_table(_header_people(email))
    mapping: dict[str, str] = {}
    spans: list[SpanOut] = []
    placeholder_for: dict[int, str] = {}

    ordered = sorted(decisions, key=lambda d: (d.candidate.field, d.candidate.start))
    for d in ordered:  # numbering in document order
        c = d.candidate
        if d.action == "redact":
            original = fields[c.field][c.start:c.end]
            t = _ph_type(c.type)
            person = aliases.get(original.strip()) if t == "PERSON" else None
            key = f"{t}|{(person or original).strip().lower()}"
            ph = labels.labels.get(key)
            if ph is None:
                labels.counters[t] = labels.counters.get(t, 0) + 1
                ph = f"[{t}_{labels.counters[t]}]"
                labels.labels[key] = ph
            if person:  # later requests in the session that only say "Dana" reuse the label
                for alias, full in aliases.items():
                    if full == person:
                        labels.labels.setdefault(f"{t}|{alias.lower()}", ph)
            mapping[ph] = person or mapping.get(ph, original)
            placeholder_for[id(d)] = ph
        spans.append(SpanOut(field=c.field, start=c.start, end=c.end, type=c.type, tier=d.tier,
                             action=d.action, confidence=d.confidence,
                             detectors=sorted(c.detectors), reason=d.reason))

    out_fields = dict(fields)
    for d in sorted(ordered, key=lambda d: (d.candidate.field, -d.candidate.start)):
        if d.action == "redact":  # right to left, so earlier offsets stay valid
            c = d.candidate
            text = out_fields[c.field]
            out_fields[c.field] = text[:c.start] + placeholder_for[id(d)] + text[c.end:]
    email_dict = email_to_dict(email)
    for path, text in out_fields.items():
        if path != "purpose":
            set_field(email_dict, path, text)
    return PseudonymResult(redacted_purpose=out_fields["purpose"], redacted_email=email_dict,
                           spans=spans, mapping=mapping)
