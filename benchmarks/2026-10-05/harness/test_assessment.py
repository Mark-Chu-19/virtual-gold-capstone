import urllib.request
import json
import time
from pathlib import Path

env = {}
for line in Path("virtual-gold-capstone/.env").read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()

API_KEY = env.get("OPENROUTER_API_KEY")

ASSESSMENT_SYSTEM_PROMPT = """You are a contextual privacy assessment classifier.
You are given a document and a list of candidate spans flagged as potentially sensitive.
For each candidate span, evaluate its context in the document and assess whether it is PRIVATE (should be redacted to protect privacy or confidentiality) or PUBLIC (safe to share with an external cloud assistant, such as a published company hotline, generic department mailbox, public company name, or public fact).
For each candidate, output:
- "candidate_id": integer ID corresponding to the candidate in the input list
- "verdict": "PRIVATE" or "PUBLIC"
- "raw_score": float between 0.0 and 1.0 representing your estimated probability that this span is PRIVATE in this context (1.0 = definitely private / must redact, 0.0 = definitely public / safe to retain)
- "reasoning": brief explanation
Return a valid JSON object matching this exact schema:
{
  "assessments": [
    {
      "candidate_id": 0,
      "verdict": "PRIVATE" | "PUBLIC",
      "raw_score": 0.95,
      "reasoning": "..."
    }
  ]
}
Output valid JSON only. Do not wrap in markdown or code blocks."""

test_text = (
    "From: Sarah Jenkins <sarah.jenkins@vg-partners.com>\n"
    "To: David Ross <david.ross@vg-partners.com>\n"
    "Subject: Rescheduling our strategy sync\n\n"
    "Can we push our strategy sync to Thursday 3 PM? If anything urgent comes up before then, "
    "reach me on my personal cell at 415-555-0182. For general scheduling changes, you can also "
    "contact our corporate desk at 800-555-0100."
)

candidates = [
    {"candidate_id": 0, "text": "415-555-0182", "category": "PHONE"},
    {"candidate_id": 1, "text": "800-555-0100", "category": "PHONE"},
    {"candidate_id": 2, "text": "Sarah Jenkins", "category": "PERSON"}
]

user_content = f"Document:\n{test_text}\n\nCandidates to assess:\n{json.dumps(candidates, indent=2)}"

def call(model):
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": ASSESSMENT_SYSTEM_PROMPT},
            {"role": "user", "content": user_content}
        ],
        "temperature": 0.0,
        "max_tokens": 1000,
        "response_format": {"type": "json_object"}
    }
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode())
    return data

for m in ["meta-llama/llama-3.1-8b-instruct", "qwen/qwen-2.5-7b-instruct", "x-ai/grok-4.20"]:
    d = call(m)
    c = d.get("choices", [{}])[0].get("message", {}).get("content", "")
    print(f"=== {m} ===")
    parsed = json.loads(c)
    for a in parsed.get("assessments", []):
        print(f"  ID {a.get('candidate_id')}: verdict={a.get('verdict')}, score={a.get('raw_score')}, reason={a.get('reasoning')[:60]}...")
