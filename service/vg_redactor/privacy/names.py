"""Shared helper: names of the people in an email's header (from / to / cc).

Used by `detect_rules` (find every occurrence) and `pseudonymize` (give every variant of one
person the same placeholder). A helper, not a component.
"""
from __future__ import annotations

import re

# Names that are also everyday words; matching them everywhere would hit "I will send it".
COMMON_WORD_NAMES = {"Will", "May", "Mark", "June", "April", "August", "Grace", "Hope", "Bill",
                     "Rose", "Faith", "Joy", "Sue", "Pat", "Art", "Rich", "Frank", "Bob"}
# A header "name" containing one of these is a mailbox or team, not a person.
NON_PERSON_WORDS = {"team", "support", "office", "desk", "group", "department", "dept", "admin",
                    "info", "sales", "service", "services", "help", "helpdesk", "hr", "it",
                    "finance", "legal", "noreply", "no-reply", "inc", "llc", "ltd", "corp",
                    "company", "board", "committee", "operations", "notifications", "alerts",
                    "updates", "billing", "hotline", "center", "centre", "airlines", "airways"}
# Role mailboxes (RFC 2142 style): a header name sent from one of these is a system or team
# sender ("Concur Expense" <no-reply@...>, "BGE Billing" <ebill@...>), not a person.
_ROLE_LOCAL = re.compile(
    r"^(?:no-?reply|do-?not-?reply|alerts?|notifications?|notify|updates?|news(?:letter)?|"
    r"e?bill(?:ing)?|invoices?|reports?|status|info|insights|benefits|support|help(?:desk)?|"
    r"admin|hr|payroll|careers|jobs|marketing|sales|service|team|mailer-daemon|postmaster|"
    r"webmaster|digest|intake)$")
_TOKEN = re.compile(r"[A-Z][a-zA-Z'’-]+")


def is_role_mailbox(address: str | None) -> bool:
    """True when the local part, or one of its parts ("fdic-updates", "ethics-intake"), is a
    role word."""
    if not address or "@" not in address:
        return False
    local = address.split("@", 1)[0].lower()
    return any(_ROLE_LOCAL.match(p) for p in [local, *re.split(r"[._+-]", local)])


def clean_person_name(raw: str | None) -> str | None:
    """Normalised full name, or None when the header name is empty or a team mailbox."""
    if not raw:
        return None
    full = " ".join(raw.replace(",", " ").split())
    if not full or {w.lower() for w in full.split()} & NON_PERSON_WORDS:
        return None
    return full


def name_parts(full: str) -> set[str]:
    """Capitalised parts usable as aliases ("Dana Whitfield" -> {"Dana", "Whitfield"})."""
    return {t for t in _TOKEN.findall(full) if len(t) > 1 and t not in COMMON_WORD_NAMES}


def ambiguous_parts(full_names: list[str]) -> set[str]:
    """Name parts that belong to more than one person ("Dana" in Dana Whitfield and Dana Lee)."""
    owners: dict[str, set[str]] = {}
    for full in set(full_names):
        for part in name_parts(full):
            owners.setdefault(part, set()).add(full)
    return {part for part, fulls in owners.items() if len(fulls) > 1}


def alias_table(full_names: list[str]) -> dict[str, str]:
    """alias -> full name. A part shared by two different people ("Dana" in Dana Whitfield and
    Dana Lee) is ambiguous and left out, so two people are never merged into one."""
    owners: dict[str, set[str]] = {}
    for full in set(full_names):
        for alias in {full} | name_parts(full):
            owners.setdefault(alias, set()).add(full)
    return {alias: next(iter(fulls)) for alias, fulls in owners.items() if len(fulls) == 1}
