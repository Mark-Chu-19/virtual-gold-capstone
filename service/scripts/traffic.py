"""Traffic generator for the dashboard and the demo.

    python scripts/traffic.py --rate 5 --duration 120 --key dev-key

Sends a mix of synthetic requests (a private phone number next to a public support line, clean
text, a Social-Security-like number, a restore call) to a running service. All data is fictional.
Combine with the stub fault file to show the degraded path:  echo down > /tmp/vg_fault
"""
from __future__ import annotations

import argparse
import asyncio
import random
import time

import httpx

SAMPLES = [
    "Please call me on my cell, 412-555-0182. Our support line is 800-555-0199.",
    "Quarterly numbers look fine, nothing sensitive in this one.",
    "My SSN is 123-45-6789, please update the payroll record.",
    "Contact dana@example.test about Project Falcon before Thursday.",
    "Reach the office at (617) 555-0142 or the helpdesk at 888-555-0100.",
]


async def one(client: httpx.AsyncClient, stats: dict) -> None:
    body = {"purpose": "Summarize this email",
            "email": {"subject": "Update", "body": random.choice(SAMPLES)},
            "mapping": {"retain": True}}
    try:
        r = await client.post("/v1/redactions", json=body)
        stats[r.status_code] = stats.get(r.status_code, 0) + 1
        if r.status_code == 200 and random.random() < 0.3:
            rid = r.json()["request_id"]
            await client.post(f"/v1/redactions/{rid}/restore", json={"reply_text": "[PHONE_1]"})
            if random.random() < 0.5:
                await client.delete(f"/v1/redactions/{rid}")
    except httpx.HTTPError:
        stats["error"] = stats.get("error", 0) + 1


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8080")
    ap.add_argument("--key", required=True)
    ap.add_argument("--rate", type=float, default=5, help="requests per second")
    ap.add_argument("--duration", type=float, default=60, help="seconds")
    a = ap.parse_args()
    stats: dict = {}
    async with httpx.AsyncClient(base_url=a.url, headers={"Authorization": f"Bearer {a.key}"},
                                 timeout=30) as client:
        end, tasks = time.monotonic() + a.duration, []
        while time.monotonic() < end:
            tasks.append(asyncio.create_task(one(client, stats)))
            await asyncio.sleep(random.expovariate(a.rate))
        await asyncio.gather(*tasks)
    print("sent", sum(stats.values()), "requests; status counts:", stats)


if __name__ == "__main__":
    asyncio.run(main())
