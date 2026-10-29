"""Strategy table: start from main's rules + Presidio and add each strategy of this branch, alone
and cumulatively, scoring the union on the 60 development emails.

Every strategy is a switch (monkeypatch) on this branch's code. With all switches off the
detectors behave like main, so the first row should match a run of eval_detectors.py on main.
The switches name private functions in privacy/rules.py and presidio.py: when those change,
update STRATEGIES and configure() here.

Usage, from the repo root with the service virtualenv:
    service/.venv/bin/python service/scripts/eval/strategy_table.py [--out DIR]
"""
import argparse, json, re, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
ap = argparse.ArgumentParser()
ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "out" / "strategy_table")
OUT = ap.parse_args().out.resolve()
DATA = REPO / "data/baseline/baseline_v1.1_dev.jsonl"
sys.path.insert(0, str(REPO / "service"))
from vg_redactor.contracts.policy import Policy  # noqa: E402
from vg_redactor.contracts.types import RedactionRequestV3  # noqa: E402
from vg_redactor.privacy import FileContextStore, detect_rules, make_detect_presidio  # noqa: E402
from vg_redactor.privacy import names as N, presidio as P, rules as R  # noqa: E402
from vg_redactor.privacy.merge import make_merge  # noqa: E402
from vg_redactor.stubs.components import segment  # noqa: E402

policy = Policy.load(REPO / "service/config/policy.yaml")
ctx = FileContextStore.load(REPO / "service/config/context_store.yaml", policy.high_types())
merge = make_merge(policy)
emails = [json.loads(l) for l in open(DATA)]
gold = {e["id"]: e for e in emails}
segs = {e["id"]: segment(*(lambda r: (r.purpose, r.email))(RedactionRequestV3.model_validate(e["request"])))
        for e in emails}


class CachedAnalyzer:
    """Runs Presidio once per text; the switches only filter and retype its results."""
    def __init__(self):
        from presidio_analyzer import AnalyzerEngine
        self.engine, self.cache = AnalyzerEngine(), {}

    def get_supported_entities(self, language):
        return self.engine.get_supported_entities(language)

    def analyze(self, text, **kw):
        key = (text, tuple(kw["entities"]))
        if key not in self.cache:
            self.cache[key] = self.engine.analyze(text=text, **kw)
        return self.cache[key]


presidio = make_detect_presidio(CachedAnalyzer())

# ---- main's versions of what the branch changed -------------------------------------------------
MAIN_PHONE = re.compile(r"(?<!\d)(?:\+?1[-. ]?)?\(?\d{3}\)?[-. ]\d{3}[-. ]\d{4}(?!\d)")
MAIN_AMOUNT = re.compile(R._MONEY)
NEW_WORDS = {"alerts", "updates", "billing", "hotline", "center", "centre", "airlines", "airways"}
PAT0, VAL0, WORDS0 = list(R.PATTERNS), list(R.VALUE_PATTERNS), set(N.NON_PERSON_WORDS)
CONTACT, CODENAMES, HEADER_NAMES, UNQUOTE = (R.contact_type, R._codename_candidates, R.header_names,
                                             R.unquote)


def header_names_no_mailbox_check(segments):
    names = set()
    for seg in segments:
        full = N.clean_person_name(seg.text) if R.HEADER_NAME_FIELD.match(seg.field) else None
        if full:
            names |= {full} | N.name_parts(full)
    return names


STRATEGIES = [  # (key, label, group)
    ("address", "Address rule", "8 fixes"),
    ("licence", "Presidio licence filter", "8 fixes"),
    ("fiscal", "Presidio: Q3/FY not a place", "8 fixes"),
    ("account", "Account / card value after label", "new"),
    ("gov", "SSN / Tax ID / licence after label", "new"),
    ("id", "ID numbers (label or prefix code)", "new"),
    ("cred", "Credentials (passcode, token link, key)", "new"),
    ("codename", "Project X code names", "new"),
    ("amount", "Amount ranges, signs, %, 万元", "new"),
    ("mailbox", "Role-mailbox senders not people", "new"),
    ("public", "Toll-free / role mailbox as PUBLIC", "new"),
    ("datedigit", "Presidio: dates need a digit", "new"),
    ("quotes", "Remove > quote markers before detection", "new"),
]
VALUE_KEY = {"ACCOUNT_NUMBER": "account", "CARD_NUMBER": "account", "GOV_ID": "gov",
             "ID_NUMBER": "id", "CREDENTIAL": "cred"}


def configure(on):
    pats = []
    for t, rx in PAT0:
        if t == "ADDRESS_HOME" and "address" not in on:
            continue
        if t == "PHONE_PERSONAL" and "ext" not in rx.pattern and "quotes" not in on:
            rx = MAIN_PHONE
        if t == "AMOUNT" and "amount" not in on:
            rx = MAIN_AMOUNT
        pats.append((t, rx))
    R.PATTERNS[:] = pats
    R.VALUE_PATTERNS[:] = [(t, rx) for t, rx in VAL0 if VALUE_KEY[t] in on]
    R._codename_candidates = CODENAMES if "codename" in on else (lambda s: [])
    R.header_names = HEADER_NAMES if "mailbox" in on else header_names_no_mailbox_check
    N.NON_PERSON_WORDS.clear()
    N.NON_PERSON_WORDS.update(WORDS0 if "mailbox" in on else WORDS0 - NEW_WORDS)
    R.unquote = P.unquote = UNQUOTE if "quotes" in on else (lambda s: (s, {}))
    R.contact_type = P.contact_type = CONTACT if "public" in on else (lambda t, s: t)

    def keep(entity, score, span):
        if entity == "US_DRIVER_LICENSE" and "licence" in on:
            return score >= P._LICENSE_MIN_SCORE or len(span) >= P._LICENSE_MIN_LEN
        if entity == "LOCATION" and "fiscal" in on:
            return not P._PERIOD.fullmatch(span)
        if entity == "DATE_TIME" and "datedigit" in on:
            return any(ch.isdigit() for ch in span)
        return True
    P._keep = keep


RANK = {"public": 0, "low": 1, "medium": 2, "high": 3}


def tier_recall(rows, tier):
    tot = ok = 0
    for x in rows:
        for s in gold[x["id"]]["spans"]:
            if s["ground_truth"] != "redact" or s["tier"] != tier or s["type"] == "FACT":
                continue
            tot += 1
            hs = [d for d in x["spans"] if d["field"] == s["field"] and d["start"] < s["field_end"]
                  and s["field_start"] < d["end"]]
            cov = set().union(*[range(max(d["start"], s["field_start"]), min(d["end"], s["field_end"])) for d in hs])
            ok += len(cov) >= 0.95 * (s["field_end"] - s["field_start"])
    return ok / tot


def retain_masked(rows):
    return sum(any(d["field"] == s["field"] and d["start"] < s["field_end"] and s["field_start"] < d["end"]
                   and d["tier"] != "public" for d in x["spans"])
               for x in rows for s in gold[x["id"]]["spans"] if s["ground_truth"] != "redact")


def run(on):
    configure(on)
    rows = [{"id": e["id"], "spans": [{"field": c.field, "start": c.start, "end": c.end, "type": c.type,
                                       "tier": policy.tier_of(c.type)}
                                      for c in merge(detect_rules(segs[e["id"]], ctx), presidio(segs[e["id"]]))]}
            for e in emails]
    pred, rep = OUT / "pred.jsonl", OUT / "rep.json"
    pred.write_text("".join(json.dumps(r) + "\n" for r in rows))
    subprocess.run([sys.executable, str(REPO / "data/baseline/score.py"), str(DATA), str(pred), "--out", str(rep)],
                   check=True, capture_output=True)
    m = json.loads(rep.read_text())
    return {"recall": m["recall"], "high": tier_recall(rows, "high"), "medium": tier_recall(rows, "medium"),
            "leak": m["leak_rate"], "extra": m["extra_masks"], "retain": retain_masked(rows)}


OUT.mkdir(parents=True, exist_ok=True)
base = run(set())
results = {"baseline": base, "alone": {}, "cumulative": {}}
on = set()
for key, _, _ in STRATEGIES:
    results["alone"][key] = run({key})
    on.add(key)
    results["cumulative"][key] = run(set(on))
(OUT / "incremental.json").write_text(json.dumps(results, indent=2))

H = f"{'':44}{'recall':>8}{'high':>6}{'med':>6}{'leak':>6}{'extra':>7}{'retain':>8}"
fmt = lambda r: (f"{r['recall']:>8.1%}{r['high']:>6.0%}{r['medium']:>6.0%}{r['leak']:>6.0%}"
                 f"{r['extra']:>7}{r['retain']:>8}")
print(H); print(f"{'main baseline (all off)':44}" + fmt(base))
for kind in ("alone", "cumulative"):
    print(f"\n{kind.upper()}")
    for key, label, group in STRATEGIES:
        print(f"{('+ ' + label)[:43]:44}" + fmt(results[kind][key]))
