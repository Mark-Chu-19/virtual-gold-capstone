"""Pseudonymisation with consistent aliases within one redaction.

Every unambiguous variant of a header person ("Dana Whitfield", "Dana", "Whitfield")
shares one placeholder and restores to the full name. Ambiguous aliases retain their
own labels. V3 supplies a fresh LabelState for each request; no aliases survive it.
Label keys use a per-process HMAC so they do not contain original entity text.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

from ..contracts.fields import email_to_dict, iter_fields, set_field
from ..contracts.placeholders import literal_placeholders, next_placeholder
from ..contracts.types import Decision, EmailIn, LabelState, PseudonymResult, SpanOut
from .names import alias_table, ambiguous_parts, clean_person_name


# A fresh process key prevents recovering label keys with an unkeyed dictionary hash.
_LABEL_KEY = secrets.token_bytes(32)


def _ph_type(entity_type: str) -> str:
    return entity_type.split("_")[0]


def label_key(ph_type: str, value: str) -> str:
    """Session key for one entity: "{TYPE}|<hmac>", never the value itself."""
    digest = hmac.new(_LABEL_KEY, value.strip().lower().encode("utf-8"), hashlib.sha256)
    return f"{ph_type}|{digest.hexdigest()[:32]}"


AMBIGUOUS = ""  # alias-slot value: this name part has belonged to more than one person


def _alias_key(ph_type: str, alias: str) -> str:
    """Alias slots live apart from value slots, so marking an alias ambiguous never
    touches the label of the bare value."""
    return label_key(ph_type, "\x00alias\x00" + alias)


def _header_people(email: EmailIn) -> list[str]:
    raw = [email.from_.name if email.from_ else None]
    raw += [a.name for a in email.to] + [a.name for a in email.cc]
    return [n for n in (clean_person_name(r) for r in raw) if n]


def pseudonymize(purpose: str, email: EmailIn, decisions: list[Decision],
                 labels: LabelState) -> PseudonymResult:
    fields = iter_fields(purpose, email)
    people = _header_people(email)
    aliases = alias_table(people)
    ambiguous = ambiguous_parts(people)
    for part in ambiguous:  # seen as two people here: never resolve it to one person again
        labels.labels[_alias_key("PERSON", part)] = AMBIGUOUS
    mapping = literal_placeholders(fields.values(), labels)
    spans: list[SpanOut] = []
    placeholder_for: dict[int, str] = {}

    ordered = sorted(decisions, key=lambda d: (d.candidate.field, d.candidate.start))
    for d in ordered:  # numbering in document order
        c = d.candidate
        if d.action == "redact":
            original = fields[c.field][c.start:c.end]
            value = original.strip()
            t = _ph_type(c.type)
            person = aliases.get(value) if t == "PERSON" else None
            ph = None
            if t == "PERSON" and person is None and value not in ambiguous:
                ph = labels.labels.get(_alias_key(t, value)) or None  # alias from earlier email
            key = label_key(t, person or value)
            ph = ph or labels.labels.get(key)
            if ph is None:
                ph = next_placeholder(t, labels)
                labels.labels[key] = ph
            if person:  # remember aliases within this redaction
                for alias, full in aliases.items():
                    if full == person:
                        slot = _alias_key(t, alias)
                        current = labels.labels.get(slot)
                        if current is None:
                            labels.labels[slot] = ph
                        elif current not in (ph, AMBIGUOUS):  # the alias now names two people
                            labels.labels[slot] = AMBIGUOUS
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
