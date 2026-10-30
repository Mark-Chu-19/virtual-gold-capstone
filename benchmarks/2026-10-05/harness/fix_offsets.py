import json

def verify_and_realign(docs):
    for doc in docs:
        text = doc["text"]
        doc_id = doc["id"]
        for span_type in ["private_spans", "public_spans"]:
            for span in doc.get(span_type, []):
                target = span["text"]
                s = span["start"]
                e = span["end"]
                # Check if exact match at current offset
                if text[s:e] == target:
                    continue
                # If not, find all occurrences of target in text
                occurrences = []
                idx = 0
                while True:
                    idx = text.find(target, idx)
                    if idx == -1:
                        break
                    occurrences.append((idx, idx + len(target)))
                    idx += 1
                if not occurrences:
                    print(f"ERROR: '{target}' NOT FOUND ANYWHERE IN {doc_id} text!")
                elif len(occurrences) == 1:
                    span["start"] = occurrences[0][0]
                    span["end"] = occurrences[0][1]
                    print(f"Realigned {doc_id} {span_type} '{target}': was [{s}:{e}], now [{span['start']}:{span['end']}]")
                else:
                    # Pick closest occurrence
                    closest = min(occurrences, key=lambda occ: abs(occ[0] - s))
                    span["start"] = closest[0]
                    span["end"] = closest[1]
                    print(f"Realigned (multi) {doc_id} {span_type} '{target}': was [{s}:{e}], now [{span['start']}:{span['end']}]")

from generate_dataset import DEV_DOCS, TEST_DOCS
verify_and_realign(DEV_DOCS)
verify_and_realign(TEST_DOCS)

# Now check all
def validate(docs, name):
    for doc in docs:
        text = doc["text"]
        for span_type in ["private_spans", "public_spans"]:
            for span in doc.get(span_type, []):
                s, e, t = span["start"], span["end"], span["text"]
                assert text[s:e] == t, f"Still mismatched in {doc['id']}: expected '{t}', got '{text[s:e]}'"
    print(f"ALL {name} SPANS VERIFIED 100% EXACT!")

validate(DEV_DOCS, "DEV")
validate(TEST_DOCS, "TEST")

# Save directly
from pathlib import Path
data_dir = Path("virtual-gold-capstone/benchmarks/2026-10-05/data")
data_dir.mkdir(parents=True, exist_ok=True)

dev_inputs = [{"id": d["id"], "domain": d["domain"], "task": d["task"], "text": d["text"]} for d in DEV_DOCS]
test_inputs = [{"id": d["id"], "domain": d["domain"], "task": d["task"], "text": d["text"]} for d in TEST_DOCS]
dev_gold = [{"id": d["id"], "private_spans": d["private_spans"], "public_spans": d["public_spans"]} for d in DEV_DOCS]
test_gold = [{"id": d["id"], "private_spans": d["private_spans"], "public_spans": d["public_spans"]} for d in TEST_DOCS]

with open(data_dir / "synthetic_documents_dev.json", "w") as f:
    json.dump(dev_inputs, f, indent=2)
with open(data_dir / "synthetic_documents_test.json", "w") as f:
    json.dump(test_inputs, f, indent=2)
with open(data_dir / "gold_annotations_dev.json", "w") as f:
    json.dump(dev_gold, f, indent=2)
with open(data_dir / "gold_annotations_test.json", "w") as f:
    json.dump(test_gold, f, indent=2)

print("Saved verified files to disk.")
