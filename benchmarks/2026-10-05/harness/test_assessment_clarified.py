import urllib.request
import json
from pathlib import Path

env = {}
for line in Path("virtual-gold-capstone/.env").read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()

API_KEY = env.get("OPENROUTER_API_KEY")

ASSESSMENT_PROMPT = """You are a contextual privacy classifier for an enterprise privacy redaction system.
You are given a document and a list of candidate spans flagged as potentially sensitive.
For each candidate span, evaluate its context in the document and classify whether it is:
- "PRIVATE": personal PII, private mobile phone, confidential business secret, internal financial target, credentials. Must be redacted.
- "PUBLIC": published company contact (e.g. toll-free hotline, corporate switchboard), public department email, public company name, or public fact. Safe to retain.

For each candidate, output:
- "candidate_id": integer ID matching the candidate list
- "verdict": "PRIVATE" or "PUBLIC"
- "confidence": float between 0.50 and 1.00 indicating your confidence in the verdict (1.0 = absolute certainty)
- "reasoning": one concise sentence explaining why this candidate is private or public in this context.

Return valid JSON matching this schema:
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
Output valid JSON only. Do not wrap in markdown or backticks."""

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
    {"candidate_id": 1, "text": "800-555-0100", "category": "PHONE"}
]

user_content = f"Document:\n{test_text}\n\nCandidates:\n{json.dumps(candidates, indent=2)}"

def call(model):
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": ASSESSMENT_PROMPT},
            {"role": "user", "content": user_content}
        ],
        "temperature": 0.0,
        "max_tokens": 1000,
        "response_format": {"type": "json_object"}
    }
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())

for m in ["meta-llama/llama-3.1-8b-instruct", "qwen/qwen-2.5-7b-instruct", "x-ai/grok-4.20"]:
    d = call(m)
    c = d.get("choices", [{}])[0].get("message", {}).get("content", "")
    print(f"=== {m} ===")
    parsed = json.loads(c)
    for a in parsed.get("assessments", []):
        v = a.get("verdict")
        conf = float(a.get("confidence", 0.5))
        # Normalized raw privacy probability
        p_priv = conf if v == "PRIVATE" else (1.0 - conf)
        print(f"  ID {a.get('candidate_id')}: verdict={v}, conf={conf:.2f} -> P(private)={p_priv:.2f} | reason={a.get('reasoning')}")
