"""Compare v2 token preservation through a local Ollama model using synthetic text only.

Run from service/: python scripts/evaluate_tokens.py --model llama3:8b
No cloud calls, no notebooks changed. Real-model quality still requires human review.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import time
from collections import Counter
from pathlib import Path

import httpx

TOKEN = re.compile(r'\[VG[^\]\r\n]*\]')
SAMPLES = [
    'Please call 202-555-0102 about account 123-45-6789.',
    'Send the update to dana@example.test and call 303-555-0103.',
    'Use 202-555-0102 first, then 303-555-0103. Repeat 202-555-0102 in the notes.',
]
TASKS = {
    'copy': 'Return the message below exactly, with no introduction or formatting.',
    'reply': ('Write a short reply acknowledging the contact details in the message. '
              'Include every distinct protected token at least once.'),
}


def preservation(source: str, output: str) -> dict:
    """Missing tokens and unexpected tokens are separate from restore's cryptographic result."""
    expected = Counter(TOKEN.findall(source))
    actual = Counter(TOKEN.findall(output))
    return {'expected_tokens': sum(expected.values()),
            'distinct_expected': len(expected),
            'distinct_preserved': len(expected.keys() & actual.keys()),
            'all_distinct_preserved': expected.keys() <= actual.keys(),
            'copy_multiplicity_preserved': not (expected - actual),
            'unexpected_tokens': sum(n for t, n in actual.items() if t not in expected),
            'extra_occurrences': sum((actual - expected).values()),
            'exact_copy': source == output}


async def evaluate(args):
    key = os.environ.get('VG_EVAL_API_KEY')
    if not key:
        raise SystemExit('Set VG_EVAL_API_KEY to an authorized service API key')
    async with httpx.AsyncClient(timeout=120) as client:
        for mode in ('mapping', 'aes_siv'):
            for index, sample in enumerate(SAMPLES):
                response = await client.post(args.service.rstrip('/') + '/v2/redactions',
                    headers={'Authorization': 'Bearer ' + key},
                    json={'purpose': 'Protect contact details for a synthetic preservation test',
                          'email': {'body': sample}, 'group_id': 'synthetic-eval',
                          'tokenization': {'mode': mode}})
                response.raise_for_status()
                text = response.json()['redacted_email']['body']
                for task, instruction in TASKS.items():
                    current = text
                    for hop in range(1, args.hops + 1):
                        started = time.perf_counter()
                        generated = await client.post(args.ollama.rstrip('/') + '/api/generate',
                            json={'model': args.model, 'stream': False,
                                  'options': {'temperature': 0, 'seed': 42},
                                  'system': ('Protected [VG:...] tokens are opaque atomic references. '
                                             'Never alter their characters. Do not infer their contents.'),
                                  'prompt': instruction + '\n\n' + current})
                        generated.raise_for_status()
                        result = generated.json()
                        output = result['response']
                        restored = await client.post(args.service.rstrip('/') + '/v2/restorations',
                            headers={'Authorization': 'Bearer ' + key}, json={'text': output})
                        restored.raise_for_status()
                        yield {'mode': mode, 'sample': index, 'task': task, 'hop': hop,
                               'model': result.get('model', args.model), 'temperature': 0, 'seed': 42,
                               **preservation(text, output),
                               'restore_decision': restored.json()['restore_decision'],
                               'prompt_tokens': result.get('prompt_eval_count'),
                               'output_tokens': result.get('eval_count'),
                               'latency_ms': round((time.perf_counter() - started) * 1000),
                               'redacted_input': text, 'model_output': output}
                        current = output


async def main(args):
    # Exclusive creation avoids accidentally overwriting prior experiment evidence.
    with Path(args.output).open('x', encoding='utf-8') as file:
        async for row in evaluate(args):
            file.write(json.dumps(row, ensure_ascii=False) + '\n')
            file.flush()
            print(json.dumps({k: v for k, v in row.items()
                              if k not in ('redacted_input', 'model_output')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--service', default='http://127.0.0.1:8080')
    parser.add_argument('--ollama', default='http://127.0.0.1:11434')
    parser.add_argument('--model', required=True)
    parser.add_argument('--hops', type=int, default=3)
    parser.add_argument('--output', default='token-evaluation.jsonl')
    args = parser.parse_args()
    if args.hops < 1:
        parser.error('--hops must be positive')
    asyncio.run(main(args))
