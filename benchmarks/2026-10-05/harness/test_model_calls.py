import urllib.request
import urllib.error
import json
import time
from pathlib import Path

# Load API key safely from .env
env = {}
for line in Path("virtual-gold-capstone/.env").read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()

API_KEY = env.get("OPENROUTER_API_KEY")

DETECTION_SYSTEM_PROMPT = """You are a sensitive information detector for an executive privacy redaction service.
Your task is to identify all potentially sensitive or confidential spans of text in the provided document.
Look for:
- Personal Identifiable Information (individual names, personal email addresses, personal phone numbers, home addresses)
- Financial and account identifiers (bank accounts, credit cards, SSN, passport numbers)
- Confidential business statements or facts (merger negotiations, unannounced facility closures, executive compensation numbers, proprietary project secrets, financial liabilities)
- Security credentials (passwords, PINs, secret keys, auth tokens)
Do NOT include published corporate contact numbers (e.g. 1-800 toll-free lines), public corporate support emails, or publicly known facts.
Return a valid JSON object matching this exact schema:
{
  "candidates": [
    {
      "text": "exact substring from document",
      "category": "PERSON | EMAIL | PHONE | IDENTIFIER | CREDENTIAL | FACT | ADDRESS | AMOUNT",
      "reason": "brief explanation"
    }
  ]
}
Output valid JSON only. Do not wrap in markdown or code blocks."""

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

def call_openrouter(model: str, messages: list, temperature: float = 0.0, max_tokens: int = 1000):
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"}
    }
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://cmu.edu/capstone",
            "X-Title": "VirtualGold-Model-Benchmark"
        }
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode())
    latency = time.perf_counter() - t0
    
    choice = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    usage = data.get("usage", {})
    cost = usage.get("cost", 0.0)
    provider = data.get("provider", "unknown")
    returned_model = data.get("model", model)
    
    return {
        "content": choice,
        "latency_s": latency,
        "usage": usage,
        "cost_usd": cost,
        "provider": provider,
        "model": returned_model,
        "raw_response": data
    }

# Test sample
test_text = (
    "From: Sarah Jenkins <sarah.jenkins@vg-partners.com>\n"
    "To: David Ross <david.ross@vg-partners.com>\n"
    "Subject: Rescheduling our strategy sync\n\n"
    "Can we push our strategy sync to Thursday 3 PM? If anything urgent comes up before then, "
    "reach me on my personal cell at 415-555-0182. For general scheduling changes, you can also "
    "contact our corporate desk at 800-555-0100."
)

models = [
    "meta-llama/llama-3.1-8b-instruct",
    "qwen/qwen-2.5-7b-instruct",
    "x-ai/grok-4.20"
]

print("=== TESTING STAGE 1 DETECTION ===")
for m in models:
    print(f"\n--- Model: {m} ---")
    try:
        res = call_openrouter(
            m,
            [
                {"role": "system", "content": DETECTION_SYSTEM_PROMPT},
                {"role": "user", "content": f"Document text:\n{test_text}"}
            ]
        )
        print(f"Latency: {res['latency_s']:.2f}s | Cost: ${res['cost_usd']:.6f} | Provider: {res['provider']}")
        print("Output preview:", res['content'][:200])
        parsed = json.loads(res['content'])
        print(f"Parsed {len(parsed.get('candidates', []))} candidates:")
        for c in parsed.get("candidates", []):
            print("  ", c.get("text"), "->", c.get("category"))
    except Exception as e:
        print("ERROR:", e)

